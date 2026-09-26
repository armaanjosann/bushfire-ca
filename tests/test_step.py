"""Step function and run_fire (project-context.md §3.3, §3.7, §4.1, §8).
SPEC-03.
"""

import dataclasses

import numpy as np
import pytest

from src.model import (
    BURNING,
    BURNT,
    EMPTY,
    FUEL,
    NEIGHBOURS,
    Config,
    RunResult,
    initial_grids,
    run_fire,
    wind_weights,
)


# --- slow reference implementation -----------------------------------------
#
# Independent, unoptimised re-implementation of §3.3: no bounding box, the
# eight shifted masks are computed over the whole L x L grid every step. It
# still draws exactly one rng.random((L, L)) per step, in the same position
# in the loop as run_fire, so the rng stream stays in lockstep with the
# bounding-box path and results are directly comparable cell-for-cell. This
# is the check the spec's Notes section calls "not optional" — the bounding
# box is the likeliest place for a boundary off-by-one to hide.


def _reference_run(cfg):
    rng = np.random.default_rng(cfg.seed)
    L = cfg.L
    max_steps = cfg.max_steps if cfg.max_steps is not None else 8 * L
    state, f = initial_grids(cfg, rng)
    burn_clock = np.zeros((L, L), dtype=np.uint8)
    weights = wind_weights(cfg.kappa, cfg.phi, cfg.diagonal_factor)

    step_number = 0
    truncated = False
    while True:
        burning = state == BURNING
        if not burning.any():
            break
        if step_number >= max_steps:
            truncated = True
            break
        step_number += 1

        draws = rng.random((L, L))
        fuel_mask = state == FUEL

        no_ignite_prob = np.ones((L, L), dtype=np.float64)
        for i, (dy, dx) in enumerate(NEIGHBOURS):
            shifted = np.zeros((L, L), dtype=bool)
            h, w = L, L
            sy0, sy1 = max(0, -dy), h - max(0, dy)
            sx0, sx1 = max(0, -dx), w - max(0, dx)
            dy0, dy1 = max(0, dy), h - max(0, -dy)
            dx0, dx1 = max(0, dx), w - max(0, -dx)
            shifted[dy0:dy1, dx0:dx1] = burning[sy0:sy1, sx0:sx1]
            p_d = np.clip(cfg.beta * weights[i] * f, 0.0, 1.0)
            no_ignite_prob *= np.where(shifted, 1.0 - p_d, 1.0)

        p_ignite = np.where(fuel_mask, 1.0 - no_ignite_prob, 0.0)
        ignite_mask = fuel_mask & (draws < p_ignite)

        burn_clock[burning] += 1
        newly_burnt = burning & (burn_clock >= cfg.tau)
        state[newly_burnt] = BURNT
        state[ignite_mask] = BURNING

    burned_cells = int(np.count_nonzero(state == BURNT))
    still_burning_cells = int(np.count_nonzero(state == BURNING))
    return state, step_number, truncated, burned_cells, still_burning_cells


@pytest.mark.parametrize(
    "kwargs",
    [
        dict(L=48, p=0.6, seed=0),
        dict(L=48, p=0.6, kappa=2.0, phi=0.9, diagonal_factor=True, seed=1),
        dict(L=48, p=0.45, seed=2, settlement=True, condition="none"),
        dict(L=48, p=1.0, beta=1.0, kappa=0.0, diagonal_factor=False, seed=3),
        dict(L=32, p=0.6, ignition="edge", regime="PERCOLATION", beta=1.0,
             kappa=0.0, diagonal_factor=False, tau=1, b=0.0, seed=4),
    ],
)
def test_bounding_box_matches_full_grid_reference(kwargs):
    cfg = Config(**kwargs)
    ref_state, ref_steps, ref_truncated, ref_burned, ref_still = _reference_run(cfg)
    result = run_fire(cfg, capture_scar=True)

    assert result.steps == ref_steps
    assert result.truncated == ref_truncated
    assert result.burned_cells == ref_burned
    assert result.still_burning_cells == ref_still
    np.testing.assert_array_equal(result.scar, ref_state)


# --- behaviour ---------------------------------------------------------


def test_runs_to_extinction():
    """A fire at p=0.6, L=128 runs to extinction with truncated == False."""
    cfg = Config(L=128, p=0.6, seed=0)
    result = run_fire(cfg)
    assert result.truncated is False


def test_no_external_rng_accepted():
    import inspect

    params = inspect.signature(run_fire).parameters
    assert "rng" not in params
    assert list(params) == ["cfg", "capture_scar"]


def test_max_steps_none_resolves_to_eight_l():
    cfg_default = Config(L=64, p=0.6, seed=0)
    cfg_explicit = Config(L=64, p=0.6, seed=0, max_steps=8 * 64)
    r_default = run_fire(cfg_default)
    r_explicit = run_fire(cfg_explicit)
    assert r_default.steps == r_explicit.steps
    assert r_default.truncated == r_explicit.truncated
    assert r_default.burned_cells == r_explicit.burned_cells


def test_truncation_excludes_still_burning_from_burned():
    cfg = Config(L=64, p=0.9, seed=1, max_steps=2)
    result = run_fire(cfg)
    assert result.truncated is True
    assert result.still_burning_cells > 0
    assert result.steps == 2


def test_p_zero_returns_zero_burn_without_raising():
    cfg = Config(L=64, p=0.0, seed=0)
    result = run_fire(cfg)
    assert result.burned_cells == 0
    assert result.still_burning_cells == 0
    assert result.steps == 0
    assert result.truncated is False


def test_raw_fields_populated_random_cell():
    cfg = Config(L=64, p=0.5, seed=0, ignition="random_cell")
    result = run_fire(cfg)
    assert result.n_cells == 64 * 64
    assert result.n_occupied > 0
    assert result.n_treated == 0
    assert result.ignition_y is not None
    assert result.ignition_x is not None
    assert result.burned_cells >= 0
    assert result.still_burning_cells >= 0
    assert isinstance(result.steps, int)
    assert isinstance(result.truncated, bool)


def test_raw_fields_ignition_null_under_edge():
    cfg = Config(
        L=64, p=0.5, seed=0, ignition="edge",
        regime="PERCOLATION", beta=1.0, kappa=0.0, diagonal_factor=False,
        tau=1, b=0.0,
    )
    result = run_fire(cfg)
    assert result.ignition_y is None
    assert result.ignition_x is None


def test_capture_scar_false_returns_none():
    cfg = Config(L=64, p=0.5, seed=0)
    result = run_fire(cfg, capture_scar=False)
    assert result.scar is None
    assert result.ignition_step is None


def test_capture_scar_true_ignition_step_matches_scar():
    cfg = Config(L=64, p=0.5, seed=0, ignition="random_cell")
    result = run_fire(cfg, capture_scar=True)

    burned_or_burning = np.isin(result.scar, [BURNING, BURNT])
    np.testing.assert_array_equal(result.ignition_step >= 0, burned_or_burning)

    iy, ix = result.ignition_y, result.ignition_x
    assert result.ignition_step[iy, ix] == 0


def test_derived_fields_dataclass_defaults_are_none():
    # The RunResult *declaration* defaults the derived fields to None
    # (SPEC-03). run_fire itself populates them since SPEC-04 (DEC-006,
    # DEC-021) — that behaviour is tested in tests/test_metrics.py.
    fields = {f.name: f.default for f in dataclasses.fields(RunResult)}
    for name in (
        "burned_fraction", "burned_fraction_of_fuel", "spanned",
        "reached_edge", "settlement_reached", "settlement_reached_step",
    ):
        assert fields[name] is None
