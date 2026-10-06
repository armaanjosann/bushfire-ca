"""SPEC-15: Experiment 2b grid, runner and the G2 gate.

Experiment 2 (SPEC-14) has not run yet, so these tests build a stand-in
`exp2.parquet` and `pc_estimates.parquet` in a temporary directory. The real
thresholds are only ever read through `resolve_p`, so a stand-in exercises the
same path the real run will take.
"""

import json
import math

import numpy as np
import pandas as pd
import pytest

from src import experiments
from src.analysis import TAIL_COLUMNS, write_pc_estimates
from src.experiments import (
    EXP2B_PHI,
    EXP2B_R_RAISED,
    EXP2B_SEED_BASE,
    config_run_id,
    exp2b_available_levels,
    exp2b_grid,
    exp2b_levels,
)

P_C = {("none", 0.0): 0.477, ("random", 0.15): 0.501, ("patches", 0.15): 0.493,
       ("strips_perp", 0.15): 0.512}


def _write_exp2(path, patches=({"k": 8},), strips=({"w": 4},)):
    rows = [{"condition": "random", "b": 0.15, "geometry_params": "{}"}]
    rows += [{"condition": "patches", "b": 0.15, "geometry_params": json.dumps(g)} for g in patches]
    rows += [{"condition": "strips_perp", "b": 0.15, "geometry_params": json.dumps(g)} for g in strips]
    rows += [{"condition": "patches", "b": 0.30, "geometry_params": json.dumps({"k": 16})}]  # other b: ignored
    pd.DataFrame(rows).to_parquet(path, index=False)


def _write_pc(path, skip=()):
    rows = [{"regime": "STUDY", "condition": c, "b": b, "kappa": 0.0, "L": None, "p_c": p,
             "p_c_stderr": 0.001, "method": "fss_crossing"}
            for (c, b), p in P_C.items() if c not in skip]
    write_pc_estimates(rows, path)


@pytest.fixture
def inputs(tmp_path):
    exp2, pc = tmp_path / "exp2.parquet", tmp_path / "pc.parquet"
    _write_exp2(exp2)
    _write_pc(pc)
    return str(exp2), str(pc)


def test_levels_need_experiment_2(tmp_path):
    with pytest.raises(FileNotFoundError, match="Experiment 2"):
        exp2b_levels(str(tmp_path / "missing.parquet"))


def test_levels_are_read_from_experiment_2_not_reselected(inputs):
    assert exp2b_levels(inputs[0]) == [
        ("none", {}, 0.0), ("random", {}, 0.15),
        ("patches", {"k": 8}, 0.15), ("strips_perp", {"w": 4}, 0.15),
    ]


def test_levels_refuse_an_ambiguous_experiment_2(tmp_path):
    path = tmp_path / "exp2.parquet"
    _write_exp2(path, patches=({"k": 4}, {"k": 8}))
    with pytest.raises(LookupError, match="exactly one 'patches'"):
        exp2b_levels(str(path))


def test_grid_shape_and_fixed_settings(inputs):
    cfgs, p_rels = exp2b_grid(*inputs, replicates=7)
    assert len(cfgs) == 4 * 7 and p_rels == [0.0] * len(cfgs)
    for c in cfgs:
        assert (c.regime, c.L, c.kappa, c.phi, c.ignition, c.settlement) == \
               ("STUDY", 256, 0.0, EXP2B_PHI, "random_cell", False)
        assert (c.beta, c.f_treat, c.tau, c.diagonal_factor) == (0.8, 0.2, 1, True)
        assert c.p == pytest.approx(P_C[(c.condition, c.b)])   # each at its own threshold
    assert len({config_run_id(c) for c in cfgs}) == len(cfgs)


def test_a_condition_without_a_threshold_is_dropped_never_substituted(tmp_path):
    """DEC-041/042: a condition whose threshold could not be measured is excluded
    and reported, and no other condition's p is used in its place."""
    exp2, pc = tmp_path / "exp2.parquet", tmp_path / "pc.parquet"
    _write_exp2(exp2)
    _write_pc(pc, skip=("strips_perp",))

    runnable, dropped = exp2b_available_levels(str(exp2), str(pc))
    assert [c for c, _, _ in runnable] == ["none", "random", "patches"]
    assert dropped == [("strips_perp", "LookupError")]

    cfgs, _ = exp2b_grid(str(exp2), str(pc), replicates=3)
    assert {c.condition for c in cfgs} == {"none", "random", "patches"}
    for c in cfgs:
        assert c.p == pytest.approx(P_C[(c.condition, c.b)])


def test_grid_raises_when_no_condition_has_a_threshold(tmp_path):
    exp2, pc = tmp_path / "exp2.parquet", tmp_path / "pc.parquet"
    _write_exp2(exp2)
    # a valid pc file that holds no row any Experiment 2b condition could use
    write_pc_estimates([{"regime": "PERCOLATION", "condition": "none", "b": 0.0, "kappa": 0.0,
                         "L": None, "p_c": 0.4064, "p_c_stderr": 0.0005, "method": "fss_crossing"}], pc)
    with pytest.raises(LookupError, match="no Experiment 2b condition"):
        exp2b_grid(str(exp2), str(pc), replicates=3)


def test_seeds_are_tied_to_the_full_condition_list(tmp_path):
    """A dropped condition must not shift the others' seed streams, so a later
    run that includes it reproduces the runs made today."""
    exp2, pc_all, pc_some = tmp_path / "exp2.parquet", tmp_path / "all.parquet", tmp_path / "some.parquet"
    _write_exp2(exp2)
    _write_pc(pc_all)
    _write_pc(pc_some, skip=("strips_perp",))
    seeds = lambda pc: {(c.condition, c.seed) for c in exp2b_grid(str(exp2), str(pc), replicates=4)[0]}
    partial = seeds(pc_some)
    assert partial <= seeds(pc_all)
    assert {c for c, _ in partial} == {"none", "random", "patches"}


def test_g2_escalation_extends_the_same_runs(inputs):
    """Seeds are laid out so 50,000 replicates *contain* the 10,000: the
    escalation resumes into the same file instead of rerunning."""
    small, _ = exp2b_grid(*inputs, replicates=5, conditions=["none", "strips_perp"])
    big, _ = exp2b_grid(*inputs, replicates=9, conditions=["none", "strips_perp"])
    assert {config_run_id(c) for c in small} <= {config_run_id(c) for c in big}
    by_cond = {c.condition: c.seed for c in big}
    assert by_cond["strips_perp"] - EXP2B_SEED_BASE >= 3 * EXP2B_R_RAISED   # 4th level
    assert {c.condition for c in big} == {"none", "strips_perp"}


def test_grid_rejects_bad_requests(inputs):
    with pytest.raises(ValueError):
        exp2b_grid(*inputs, replicates=0)
    with pytest.raises(ValueError):
        exp2b_grid(*inputs, replicates=EXP2B_R_RAISED + 1)
    with pytest.raises(ValueError, match="unknown"):
        exp2b_grid(*inputs, replicates=3, conditions=["buffer"])


def test_staged_run_end_to_end_records_no_fits(inputs, tmp_path, capsys):
    out, fits_path = tmp_path / "exp2b.parquet", tmp_path / "tail_fits.parquet"
    fits = experiments.run_exp2b(*inputs, out_path=str(out), fits_path=str(fits_path),
                                 replicates=60, size=64)
    assert not fits_path.exists()
    assert len(pd.read_parquet(out)) == 4 * 60
    assert set(fits["condition"]) == {"none", "random", "patches", "strips_perp"}
    assert (fits["alpha_stderr"] > 0).all()
    assert "Gate G2" in capsys.readouterr().out


def test_full_run_records_one_fit_per_condition(inputs, tmp_path, monkeypatch):
    # shrink what counts as "full" so the real recording path runs in seconds
    monkeypatch.setattr(experiments, "EXP2B_L", 64)
    monkeypatch.setattr(experiments, "EXP2B_R", 60)
    out, fits_path = tmp_path / "exp2b.parquet", tmp_path / "tail_fits.parquet"
    experiments.run_exp2b(*inputs, out_path=str(out), fits_path=str(fits_path),
                          replicates=60, size=64)
    fits = pd.read_parquet(fits_path)
    assert list(fits.columns) == TAIL_COLUMNS
    assert len(fits) == 4 and fits["condition"].is_unique
    assert (fits["experiment"] == "2b").all() and (fits["replicates"] == 60).all()
    assert (fits["x_max"] == 64 * 64).all()
    assert fits["decades_above_xmin"].notna().all()
    # resuming does not rerun anything and refuses to record the same fits twice
    with pytest.raises(ValueError, match="duplicate"):
        experiments.run_exp2b(*inputs, out_path=str(out), fits_path=str(fits_path),
                              replicates=60, size=64)
    assert len(pd.read_parquet(out)) == 4 * 60


def test_i10_holds_over_the_committed_2b_frame():
    """I10 over the frame Experiment 2b actually reported, not a synthetic one (SPEC-15)."""
    from src.analysis import assert_not_truncated

    frame = pd.read_parquet("results/exp2b.parquet")
    assert len(frame) == 30_000 and frame["condition"].nunique() == 3
    assert_not_truncated(frame)
