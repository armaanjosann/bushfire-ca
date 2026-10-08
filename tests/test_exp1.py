"""SPEC-13: Experiment 1 grid, frame checks and illustrative scars.

The thresholds are read from the committed results/pc_estimates.parquet
(Experiment 0b), the same file the real run resolves against.
"""

import json

import numpy as np
import pandas as pd
import pytest

from src import experiments
from src.analysis import resolve_p
from src.experiments import (
    EXP1_B,
    EXP1_LEVELS,
    EXP1_P_ABS,
    EXP1_R,
    SCAR_LEVELS,
    config_run_id,
    exp1_grid,
    exp1_points,
    scar_configs,
)
from src.model import SETTLEMENT_SIDE


@pytest.fixture(scope="module")
def grid():
    return exp1_grid(replicates=2)


def test_grid_size_matches_section_6_2(grid):
    cfgs, p_rels = grid
    n_points = 2 * 4 * (1 + len(EXP1_LEVELS) * len(EXP1_B))
    assert n_points == 536 and len(EXP1_LEVELS) == 11
    assert len(cfgs) == len(p_rels) == n_points * 2


def test_none_only_at_zero_budget_and_every_level_at_every_budget(grid):
    cfgs, _ = grid
    assert {c.b for c in cfgs if c.condition == "none"} == {0.0}
    assert all(c.b > 0 for c in cfgs if c.condition != "none")
    for cond, prm in EXP1_LEVELS:
        bs = {c.b for c in cfgs if c.condition == cond
              and {k: v for k, v in c.geometry_params.items() if k != "settlement_side"} == prm}
        assert bs == set(EXP1_B), (cond, prm)


def test_fixed_settings_and_explicit_settlement_side(grid):
    for c in grid[0]:
        assert (c.regime, c.L, c.ignition, c.settlement, c.phi) == ("STUDY", 256, "random_cell", True, 0.0)
        assert (c.beta, c.f_treat, c.tau, c.diagonal_factor) == (0.8, 0.2, 1, True)
        assert c.geometry_params["settlement_side"] == SETTLEMENT_SIDE   # DEC-015


def test_p_resolves_against_the_matching_kappa(grid):
    cfgs, p_rels = grid
    for c, rel in zip(cfgs, p_rels):
        if rel is None:
            assert c.p == EXP1_P_ABS
        else:
            want = resolve_p(rel, regime="STUDY", condition="none", b=0.0, kappa=c.kappa)
            assert c.p == pytest.approx(want, abs=1e-12)
    # and never against the PERCOLATION threshold
    assert min(c.p for c in cfgs) > 0.41


def test_points_are_the_eight_operating_points():
    pts = exp1_points()
    assert len(pts) == 8
    assert sum(rel is None for _, _, rel in pts) == 2
    assert {k for k, _, _ in pts} == {0.0, 2.0}


def test_missing_threshold_raises(tmp_path):
    empty = tmp_path / "pc.parquet"
    with pytest.raises(FileNotFoundError):
        exp1_grid(pc_path=str(empty), replicates=1)


def test_seeds_unique_and_staged_runs_resume_into_full(grid):
    small, _ = exp1_grid(replicates=1)
    ids2 = {config_run_id(c) for c in grid[0]}
    assert len(ids2) == len(grid[0])
    assert {config_run_id(c) for c in small} <= ids2
    assert len({c.seed for c in grid[0]}) == len(grid[0])


def test_replicates_bounds():
    with pytest.raises(ValueError):
        exp1_grid(replicates=0)
    with pytest.raises(ValueError):
        exp1_grid(replicates=EXP1_R + 1)


def test_staged_run_end_to_end_passes_frame_checks(tmp_path):
    # R=1 over the whole grid: 536 real runs at L=256, every acceptance check applied
    df = experiments.run_exp1(out_path=str(tmp_path / "exp1.parquet"), replicates=1)
    assert len(df) == 536
    assert df["spanned"].isna().all() and df["settlement_reached"].notna().all()


def test_frame_check_catches_a_wrong_threshold(tmp_path):
    cfgs, p_rels = exp1_grid(replicates=1)
    keep = [i for i, c in enumerate(cfgs) if c.kappa == 0.0 and c.condition in ("none", "random")]
    sub, rels = [cfgs[i] for i in keep], [p_rels[i] for i in keep]
    df = experiments.run_configs(sub, str(tmp_path / "x.parquet"), p_rel=rels)
    bad = df.copy()
    bad.loc[bad["p_rel"] == 0.0, "p"] = 0.4064            # the PERCOLATION threshold
    with pytest.raises(AssertionError, match="resolved threshold"):
        experiments._check_exp1_frame(bad, len(bad))


def test_scar_configs_are_rows_of_experiment_1(grid):
    full_ids = {config_run_id(c) for c in exp1_grid(replicates=1)[0]}
    named = scar_configs()
    assert len(named) == len(SCAR_LEVELS) <= 8
    assert {config_run_id(c) for c in named} <= full_ids


def test_scars_npz_contents_and_determinism(tmp_path):
    a, b = tmp_path / "a.npz", tmp_path / "b.npz"
    ids = experiments.run_scars(out_path=str(a))
    assert experiments.run_scars(out_path=str(b)) == ids
    assert a.stat().st_size < 5e6
    with np.load(a) as za, np.load(b) as zb:
        assert list(za["run_ids"]) == ids
        assert set(za.files) == {"run_ids"} | {f"{r}__{k}" for r in ids for k in ("scar", "ignition_step", "config")}
        for r in ids:
            assert za[f"{r}__scar"].shape == (256, 256) and za[f"{r}__scar"].dtype == np.int8
            assert za[f"{r}__ignition_step"].dtype == np.int32
            assert np.array_equal(za[f"{r}__scar"], zb[f"{r}__scar"])
            assert np.array_equal(za[f"{r}__ignition_step"], zb[f"{r}__ignition_step"])
            cfg = json.loads(str(za[f"{r}__config"]))
            assert cfg["L"] == 256 and cfg["settlement"] is True
