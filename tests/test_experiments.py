"""SPEC-05: experiment harness — schema, run_id, parallel runner, resume."""

import math
import multiprocessing
import os
import re
import subprocess
import sys
import textwrap
import time
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from src import experiments
from src.model import Config

REPO = Path(__file__).resolve().parent.parent

# Written out from project-context.md §5, independently of experiments.SCHEMA.
EXPECTED_DTYPES = {
    "run_id": "str", "code_version": "str", "seed": "int64", "regime": "str",
    "L": "int32", "p": "float64", "p_rel": "float64", "condition": "str",
    "geometry_params": "str", "b": "float64", "budget_basis": "str",
    "f_treat": "float64", "beta": "float64", "kappa": "float64",
    "phi": "float64", "tau": "float64", "diagonal_factor": "bool",
    "ignition": "str", "ignition_y": "Int32", "ignition_x": "Int32",
    "settlement": "bool", "n_cells": "int32", "n_occupied": "int32",
    "n_treated": "int32", "burned_cells": "int32",
    "still_burning_cells": "int32", "burned_fraction": "float64",
    "burned_fraction_of_fuel": "float64", "spanned": "boolean",
    "reached_edge": "boolean", "settlement_reached": "boolean",
    "settlement_reached_step": "Int32", "steps": "int32",
    "truncated": "bool", "wall_ms": "float64",
}


def _smoke_grid() -> list[Config]:
    """Small grid touching every null case: both regimes, both ignitions, settlement on and off."""
    perc = dict(regime="PERCOLATION", beta=1.0, kappa=0.0, diagonal_factor=False,
                tau=1, ignition="edge")
    side = {"settlement_side": 8}
    cfgs = []
    for seed in range(3):
        cfgs += [
            Config(L=32, p=0.5, seed=seed, **perc),
            Config(L=32, p=0.6, seed=seed, condition="random", b=0.15),
            Config(L=32, p=0.6, seed=seed, condition="patches", b=0.15,
                   geometry_params={"k": 4}),
            Config(L=32, p=0.6, seed=seed, condition="strips_perp", b=0.15,
                   geometry_params={"w": 4}, kappa=2.0),
            Config(L=32, p=0.6, seed=seed, condition="buffer", b=0.15,
                   settlement=True, geometry_params=side),
            Config(L=32, p=0.6, seed=seed, condition="none", settlement=True,
                   geometry_params=side),
            Config(L=32, p=0.6, seed=seed, ignition="edge", phi=-math.pi / 2),
        ]
    return cfgs


@pytest.fixture(scope="module")
def smoke(tmp_path_factory):
    path = tmp_path_factory.mktemp("smoke") / "smoke.parquet"
    cfgs = _smoke_grid()
    df = experiments.run_configs(cfgs, str(path))
    return cfgs, path, df


# --- schema -----------------------------------------------------------------


def test_every_column_present_with_stated_dtype(smoke):
    cfgs, path, df = smoke
    for frame in (df, pd.read_parquet(path)):  # in memory and after the parquet round trip
        assert list(frame.columns) == list(EXPECTED_DTYPES)
        assert {c: str(t) for c, t in frame.dtypes.items()} == EXPECTED_DTYPES
    assert len(df) == len(cfgs)
    assert df.run_id.is_unique


def test_rows_echo_the_config(smoke):
    cfgs, _, df = smoke
    for cfg, (_, row) in zip(cfgs, df.iterrows()):
        assert row.run_id == experiments.config_run_id(cfg)
        assert (row.seed, row.L, row.p, row.b) == (cfg.seed, cfg.L, cfg.p, cfg.b)
        assert (row.regime, row.condition, row.ignition) == (cfg.regime, cfg.condition, cfg.ignition)
        assert (row.beta, row.kappa, row.phi, row.tau) == (cfg.beta, cfg.kappa, cfg.phi, cfg.tau)
        assert row.settlement == cfg.settlement and row.diagonal_factor == cfg.diagonal_factor
        assert row.n_cells == cfg.L * cfg.L


def test_null_cases_are_actually_null(smoke):
    _, _, df = smoke
    rc = df[df.ignition == "random_cell"]
    edge = df[df.ignition == "edge"]
    assert len(rc) and len(edge)
    assert rc.spanned.isna().all() and rc.reached_edge.notna().all()
    assert rc.ignition_y.notna().all() and rc.ignition_x.notna().all()
    assert edge.reached_edge.isna().all() and edge.spanned.notna().all()
    assert edge.ignition_y.isna().all() and edge.ignition_x.isna().all()
    no_settlement = df[~df.settlement]
    assert no_settlement.settlement_reached.isna().all()
    assert no_settlement.settlement_reached_step.isna().all()
    with_settlement = df[df.settlement]
    assert with_settlement.settlement_reached.notna().all()
    # step is null exactly where the ring was never reached
    reached = with_settlement.settlement_reached.astype(bool)
    assert with_settlement.settlement_reached_step[reached].notna().all()
    assert with_settlement.settlement_reached_step[~reached].isna().all()


def test_budget_basis_is_occupied(smoke):
    assert (smoke[2].budget_basis == "occupied").all()


def test_geometry_params_is_json_string(smoke):
    _, _, df = smoke
    import json
    assert json.loads(df[df.condition == "patches"].geometry_params.iloc[0]) == {"k": 4}
    assert (df[df.condition == "random"].geometry_params == "{}").all()


def test_frame_i7_budget_parity(smoke):
    """I7 over the results frame (DEC-023): n_treated is the realised count, within tolerance of the budget."""
    _, _, df = smoke
    nominal = np.round(df.b * df.n_occupied).astype(int)
    tol = np.maximum(1, np.ceil(0.01 * nominal)).astype(int)
    assert ((df.n_treated - nominal).abs() <= tol).all()
    assert (df.n_treated[df.b == 0] == 0).all()
    assert (df.n_treated <= df.n_occupied).all()
    assert (df.burned_cells + df.still_burning_cells <= df.n_occupied).all()  # I9


def test_outcome_fields_are_copied_from_run_result(smoke):
    from src.model import run_fire
    cfgs, _, df = smoke
    for cfg, (_, row) in list(zip(cfgs, df.iterrows()))[:7]:
        res = run_fire(cfg)
        assert row.n_treated == res.n_treated
        assert row.burned_cells == res.burned_cells
        assert row.burned_fraction == res.burned_fraction
        assert row.steps == res.steps and row.truncated == res.truncated


# --- run_id -----------------------------------------------------------------


def _id_in_worker(cfg):
    return experiments.config_run_id(cfg)


def _representative_cfgs():
    return [
        Config(),
        Config(L=64, p=0.41, seed=7, condition="patches", b=0.2, geometry_params={"k": 8, "z": [1, 2]}),
        Config(L=128, phi=-math.pi / 2, kappa=2.0, ignition="edge", seed=99),
    ]


def test_run_id_stable_across_processes_and_hash_seeds():
    cfgs = _representative_cfgs()
    here = [experiments.config_run_id(c) for c in cfgs]
    code = textwrap.dedent("""
        import math
        from src.model import Config
        from src import experiments as ex
        cfgs = [
            Config(),
            Config(L=64, p=0.41, seed=7, condition="patches", b=0.2, geometry_params={"k": 8, "z": [1, 2]}),
            Config(L=128, phi=-math.pi / 2, kappa=2.0, ignition="edge", seed=99),
        ]
        print(",".join(ex.config_run_id(c) for c in cfgs))
    """)
    for hash_seed in ("0", "1", "12345"):
        env = {**os.environ, "PYTHONHASHSEED": hash_seed}
        out = subprocess.run([sys.executable, "-c", code], cwd=REPO, env=env,
                             capture_output=True, text=True, check=True).stdout.strip()
        assert out.split(",") == here
    with multiprocessing.Pool(2) as pool:
        assert pool.map(_id_in_worker, cfgs) == here


def test_run_id_is_canonical():
    base = Config(L=64, p=0.5, geometry_params={"k": 4, "z": 1})
    assert experiments.config_run_id(base) == experiments.config_run_id(
        Config(L=64, p=0.5, geometry_params={"z": 1, "k": 4}))            # key order
    assert experiments.config_run_id(Config(L=np.int64(64), p=np.float64(0.5),
                                            geometry_params={"k": np.int64(4), "z": 1})) \
        == experiments.config_run_id(base)                                 # numpy scalars
    assert experiments.config_run_id(Config(p=1)) == experiments.config_run_id(Config(p=1.0))
    assert experiments.config_run_id(Config(phi=0.0)) == experiments.config_run_id(Config(phi=-0.0))


@pytest.mark.parametrize("change", [
    {"seed": 1}, {"L": 64}, {"p": 0.46}, {"beta": 0.7}, {"kappa": 1.0},
    {"phi": 1.0}, {"tau": 2}, {"diagonal_factor": False}, {"f_treat": 0.4},
    {"ignition": "edge"}, {"settlement": True}, {"max_steps": 100},
    {"condition": "random", "b": 0.1}, {"geometry_params": {"k": 4}},
])
def test_every_field_moves_run_id(change):
    assert experiments.config_run_id(Config(**change)) != experiments.config_run_id(Config())


def test_no_collisions_over_5000_configs():
    cfgs = []
    for seed in range(50):
        for p in np.arange(0.30, 0.60, 0.03):
            for L in (128, 256):
                for cond, params in (("none", {}), ("patches", {"k": 4}), ("patches", {"k": 8}),
                                     ("strips_perp", {"w": 4}), ("strips_perp", {"w": 8})):
                    b = 0.0 if cond == "none" else 0.15
                    cfgs.append(Config(L=L, p=float(p), seed=seed, condition=cond, b=b,
                                       geometry_params=params))
    assert len(cfgs) == 5000
    assert len({experiments.config_run_id(c) for c in cfgs}) == 5000


# --- code_version -----------------------------------------------------------


def test_code_version_is_the_real_git_short_sha():
    v = experiments.code_version()
    assert re.fullmatch(r"[0-9a-f]{7,40}", v)
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=REPO, capture_output=True,
                          text=True, check=True).stdout.strip()
    assert head.startswith(v)


def test_runner_refuses_to_write_without_a_code_version(tmp_path, monkeypatch):
    def broken():
        raise RuntimeError("no git")
    monkeypatch.setattr(experiments, "code_version", broken)
    out = tmp_path / "x.parquet"
    with pytest.raises(RuntimeError):
        experiments.run_configs([Config(L=32)], str(out))
    assert not out.exists()


def test_code_version_rejects_non_sha_output(monkeypatch):
    class R:
        stdout = "unknown\n"
    monkeypatch.setattr(experiments.subprocess, "run", lambda *a, **k: R())
    with pytest.raises(RuntimeError):
        experiments.code_version()


def test_code_version_column_is_the_sha(smoke):
    assert (smoke[2].code_version == experiments.code_version()).all()


# --- p_rel (DEC-029, DEC-030) ------------------------------------------------


def test_p_rel_defaults_to_null_and_is_not_part_of_run_id(tmp_path):
    cfgs = [Config(L=32, p=0.5, seed=s) for s in range(3)]
    df = experiments.run_configs(cfgs, str(tmp_path / "a.parquet"))
    assert df.p_rel.isna().all()
    df2 = experiments.run_configs(cfgs, str(tmp_path / "b.parquet"), p_rel=[0.05, None, -0.05])
    assert list(df2.run_id) == list(df.run_id)
    assert df2.p_rel.isna().tolist() == [False, True, False]
    assert df2.p_rel.iloc[0] == 0.05 and df2.p_rel.iloc[2] == -0.05
    assert df2.p.tolist() == [0.5] * 3  # the harness does not touch p


def test_p_rel_length_mismatch_raises(tmp_path):
    with pytest.raises(ValueError):
        experiments.run_configs([Config(L=32)], str(tmp_path / "x.parquet"), p_rel=[0.0, 0.1])
    assert not (tmp_path / "x.parquet").exists()


def test_p_rel_stays_paired_with_its_config_across_resume(tmp_path):
    path = str(tmp_path / "x.parquet")
    cfgs = [Config(L=32, p=0.5, seed=s) for s in range(4)]
    experiments.run_configs(cfgs[1:3], path, p_rel=[0.1, 0.2])
    df = experiments.run_configs(cfgs, path, p_rel=[0.0, 0.1, 0.2, 0.3])
    by_seed = df.set_index("seed").p_rel
    assert by_seed.to_dict() == {1: 0.1, 2: 0.2, 0: 0.0, 3: pytest.approx(0.3)}


# --- append-only and resume --------------------------------------------------


def test_duplicate_configs_in_input_raise(tmp_path):
    with pytest.raises(ValueError):
        experiments.run_configs([Config(L=32), Config(L=32)], str(tmp_path / "x.parquet"))


def test_resume_false_refuses_to_overwrite(tmp_path):
    path = str(tmp_path / "x.parquet")
    experiments.run_configs([Config(L=32)], path)
    before = Path(path).read_bytes()
    with pytest.raises(FileExistsError):
        experiments.run_configs([Config(L=32, seed=1)], path, resume=False)
    assert Path(path).read_bytes() == before


def test_resume_skips_done_runs_and_keeps_old_rows(tmp_path, monkeypatch):
    path = str(tmp_path / "x.parquet")
    cfgs = [Config(L=32, p=0.55, seed=s) for s in range(6)]
    first = experiments.run_configs(cfgs[:3], path)

    ran = []
    real = experiments._run_chunk

    def spy(task):
        ran.extend(c.seed for c, _ in task[0])
        return real(task)
    monkeypatch.setattr(experiments, "_run_chunk", spy)
    monkeypatch.setattr(experiments, "WORKERS", 1)

    df = experiments.run_configs(cfgs, path)
    assert sorted(ran) == [3, 4, 5]                       # only the missing ones ran
    assert df.run_id.is_unique and len(df) == 6
    pd.testing.assert_frame_equal(df.iloc[:3].reset_index(drop=True), first)  # old rows untouched, wall_ms included

    ran.clear()
    again = experiments.run_configs(cfgs, path)           # nothing left to do
    assert ran == [] and len(again) == 6


_KILL_SCRIPT = textwrap.dedent("""
    import sys
    from src import experiments as ex
    from src.model import Config
    ex.WORKERS = 2
    ex.FLUSH_SECONDS = 0.0   # checkpoint after every chunk
    cfgs = [Config(L=96, p=0.42, seed=s, ignition="edge", regime="PERCOLATION", beta=1.0,
                   kappa=0.0, diagonal_factor=False) for s in range(600)]
    if __name__ == "__main__":
        ex.run_configs(cfgs, sys.argv[1])
""")


def _kill_cfgs():
    return [Config(L=96, p=0.42, seed=s, ignition="edge", regime="PERCOLATION", beta=1.0,
                   kappa=0.0, diagonal_factor=False) for s in range(600)]


def test_killed_run_resumes_to_the_union_with_no_duplicates(tmp_path):
    path = tmp_path / "killed.parquet"
    script = tmp_path / "kill_me.py"
    script.write_text(_KILL_SCRIPT)
    proc = subprocess.Popen([sys.executable, str(script), str(path)], cwd=REPO,
                            env={**os.environ, "PYTHONPATH": str(REPO)})
    n_at_kill = 0
    deadline = time.monotonic() + 120
    while time.monotonic() < deadline and proc.poll() is None:
        try:
            n_at_kill = len(pd.read_parquet(path))
        except (OSError, ValueError):   # not there yet, or mid-rename
            n_at_kill = 0
        if n_at_kill > 0:
            break
        time.sleep(0.02)
    proc.kill()
    proc.wait()
    assert 0 < n_at_kill < 600, "run finished or never checkpointed before the kill; test is not exercising a partial run"

    partial = pd.read_parquet(path)                      # intact after a hard kill
    assert partial.run_id.is_unique and 0 < len(partial) < 600

    cfgs = _kill_cfgs()
    resumed = experiments.run_configs(cfgs, str(path))
    assert len(resumed) == 600 and resumed.run_id.is_unique
    assert set(resumed.run_id) == {experiments.config_run_id(c) for c in cfgs}
    pd.testing.assert_frame_equal(resumed.iloc[:len(partial)].reset_index(drop=True), partial)

    clean = experiments.run_configs(cfgs, str(tmp_path / "clean.parquet"))
    cols = [c for c in resumed.columns if c != "wall_ms"]
    a = resumed[cols].sort_values("run_id").reset_index(drop=True)
    b = clean[cols].sort_values("run_id").reset_index(drop=True)
    pd.testing.assert_frame_equal(a, b)                  # same rows as an uninterrupted run


def test_exception_mid_run_keeps_completed_chunks(tmp_path, monkeypatch):
    path = tmp_path / "x.parquet"
    real = experiments._run_chunk
    calls = []

    def flaky(task):
        calls.append(1)
        if len(calls) == 3:
            raise RuntimeError("boom")
        return real(task)
    monkeypatch.setattr(experiments, "_run_chunk", flaky)
    monkeypatch.setattr(experiments, "WORKERS", 1)
    monkeypatch.setattr(experiments, "MAX_CHUNK", 2)
    cfgs = [Config(L=32, p=0.55, seed=s) for s in range(8)]
    with pytest.raises(RuntimeError):
        experiments.run_configs(cfgs, str(path))
    assert len(pd.read_parquet(path)) == 4              # chunks 1 and 2 of size 2 survived
    monkeypatch.setattr(experiments, "_run_chunk", real)
    assert len(experiments.run_configs(cfgs, str(path))) == 8


# --- parallel speed-up --------------------------------------------------------


def _percolation_cfgs(n, L):
    return [Config(L=L, p=0.42, seed=s, ignition="edge", regime="PERCOLATION", beta=1.0,
                   kappa=0.0, diagonal_factor=False) for s in range(n)]


def _serial_vs_parallel(tmp_path, monkeypatch, cfgs, workers):
    monkeypatch.setattr(experiments, "WORKERS", 1)
    t0 = time.perf_counter()
    serial = experiments.run_configs(cfgs, str(tmp_path / "serial.parquet"))
    t_serial = time.perf_counter() - t0

    monkeypatch.setattr(experiments, "WORKERS", workers)
    t0 = time.perf_counter()
    par = experiments.run_configs(cfgs, str(tmp_path / "par.parquet"))
    t_par = time.perf_counter() - t0

    cols = [c for c in serial.columns if c != "wall_ms"]
    pd.testing.assert_frame_equal(serial[cols], par[cols])   # same rows, same order
    print(f"serial {t_serial:.1f}s, {workers} workers {t_par:.1f}s, speed-up {t_serial / t_par:.1f}x")
    return t_serial / t_par


@pytest.mark.skipif((os.cpu_count() or 1) < 4, reason="needs at least 4 cores")
def test_parallel_is_faster_and_identical_to_serial(tmp_path, monkeypatch):
    workers = min(16, os.cpu_count())
    assert _serial_vs_parallel(tmp_path, monkeypatch, _percolation_cfgs(200, 128), workers) >= 2
