"""Tests for initial_grids (project-context.md §3.2, §3.5, §3.6). SPEC-02."""

import numpy as np
import pytest

from src import model
from src.model import Config, SETTLEMENT_SIDE, initial_grids


def _treating_spy():
    """A geometries.generate stand-in that treats an exact n_treat cells
    deterministically from rng, honouring the n_treat==0 / I6 contract."""

    def spy(condition, rng, occupied, n_treat, **params):
        mask = np.zeros(occupied.shape, dtype=bool)
        if n_treat == 0:
            return mask
        idx = rng.choice(np.flatnonzero(occupied), size=n_treat, replace=False)
        mask.flat[idx] = True
        return mask

    return spy


# --- state/f consistency (AC1) ---------------------------------------------


def test_state_f_consistency(monkeypatch):
    monkeypatch.setattr(model.geometries, "generate", _treating_spy())
    cfg = Config(L=64, p=0.5, settlement=True, condition="random", b=0.2, seed=4)
    state, f = initial_grids(cfg, np.random.default_rng(cfg.seed))

    non_fuel = (state == model.EMPTY) | (state == model.SETTLEMENT)
    assert np.all(f[non_fuel] == 0.0)

    fuel_like = (state == model.FUEL) | (state == model.BURNING)
    assert set(np.unique(f[fuel_like]).tolist()) <= {1.0, cfg.f_treat}


def test_treatment_changes_f_only_not_state(monkeypatch):
    monkeypatch.setattr(model.geometries, "generate", _treating_spy())
    cfg = Config(L=64, p=0.6, condition="random", b=0.3, seed=9)
    state, f = initial_grids(cfg, np.random.default_rng(cfg.seed))

    occupied = state == model.FUEL
    treated = f == cfg.f_treat
    assert np.all(occupied[treated])
    untreated_occupied = occupied & ~treated
    assert np.all(f[untreated_occupied] == 1.0)


# --- settlement placement (AC2, AC4) ---------------------------------------


def _settlement_block_bounds(L, side):
    centre = L // 2
    lo = centre - side // 2
    hi = lo + side
    return lo, hi


def test_settlement_block_default_side():
    L = 256
    cfg = Config(L=L, p=0.5, settlement=True, seed=1)
    state, f = initial_grids(cfg, np.random.default_rng(cfg.seed))

    lo, hi = _settlement_block_bounds(L, SETTLEMENT_SIDE)
    block = state[lo:hi, lo:hi]
    assert block.shape == (SETTLEMENT_SIDE, SETTLEMENT_SIDE)
    assert np.all(block == model.SETTLEMENT)
    assert np.all(f[lo:hi, lo:hi] == 0.0)
    assert (state == model.SETTLEMENT).sum() == SETTLEMENT_SIDE ** 2


def test_settlement_block_explicit_side():
    L = 256
    side = 32
    cfg = Config(L=L, p=0.5, settlement=True, geometry_params={"settlement_side": side}, seed=1)
    state, f = initial_grids(cfg, np.random.default_rng(cfg.seed))

    lo, hi = _settlement_block_bounds(L, side)
    block = state[lo:hi, lo:hi]
    assert block.shape == (side, side)
    assert np.all(block == model.SETTLEMENT)
    assert np.all(f[lo:hi, lo:hi] == 0.0)
    assert (state == model.SETTLEMENT).sum() == side ** 2


def test_no_settlement_cells_when_disabled():
    cfg = Config(L=64, p=0.5, settlement=False, seed=1)
    state, f = initial_grids(cfg, np.random.default_rng(cfg.seed))
    assert not np.any(state == model.SETTLEMENT)


# --- generate call site (AC3) ----------------------------------------------


def test_generate_receives_phi_and_default_settlement_side(monkeypatch):
    captured = {}

    def spy(condition, rng, occupied, n_treat, **params):
        captured["condition"] = condition
        captured["params"] = params
        return np.zeros(occupied.shape, dtype=bool)

    monkeypatch.setattr(model.geometries, "generate", spy)
    cfg = Config(L=32, p=0.5, condition="random", b=0.2, phi=1.23, seed=3)
    initial_grids(cfg, np.random.default_rng(cfg.seed))

    assert captured["condition"] == "random"
    assert captured["params"]["phi"] == cfg.phi
    assert captured["params"]["settlement_side"] == SETTLEMENT_SIDE


def test_generate_receives_explicit_settlement_side(monkeypatch):
    captured = {}

    def spy(condition, rng, occupied, n_treat, **params):
        captured["params"] = params
        return np.zeros(occupied.shape, dtype=bool)

    monkeypatch.setattr(model.geometries, "generate", spy)
    cfg = Config(
        L=64,
        p=0.5,
        settlement=True,
        condition="random",
        b=0.2,
        geometry_params={"settlement_side": 32},
        seed=3,
    )
    initial_grids(cfg, np.random.default_rng(cfg.seed))

    assert captured["params"]["settlement_side"] == 32


def test_phi_in_geometry_params_raises():
    cfg = Config(L=32, p=0.5, condition="random", b=0.1, geometry_params={"phi": 0.5}, seed=1)
    with pytest.raises(ValueError, match="phi"):
        initial_grids(cfg, np.random.default_rng(cfg.seed))


# --- occupancy sampling (AC5) -----------------------------------------------


def test_occupancy_matches_probability_over_seeds():
    L = 64
    p = 0.4
    n_seeds = 150
    n_cells = L * L - SETTLEMENT_SIDE ** 2
    expected = p * n_cells

    counts = []
    for seed in range(n_seeds):
        cfg = Config(L=L, p=p, settlement=True, seed=seed)
        state, _ = initial_grids(cfg, np.random.default_rng(seed))
        counts.append(int((state == model.FUEL).sum()))

    mean_count = np.mean(counts)
    std_of_mean = np.sqrt(n_cells * p * (1 - p)) / np.sqrt(n_seeds)
    assert abs(mean_count - expected) < 5 * std_of_mean


# --- b=0 fuel load (AC6) -----------------------------------------------------


@pytest.mark.parametrize(
    "condition", ["none", "random", "patches", "strips_perp", "strips_para", "buffer"]
)
def test_b_zero_fuel_is_binary(condition):
    settlement = condition == "buffer"
    cfg = Config(L=64, p=0.5, condition=condition, b=0.0, settlement=settlement, seed=1)
    state, f = initial_grids(cfg, np.random.default_rng(cfg.seed))
    assert set(np.unique(f).tolist()) <= {0.0, 1.0}


def test_b_zero_identical_across_conditions_same_seed():
    seed = 3
    outcomes = {}
    for condition in ["none", "random", "patches", "strips_perp", "strips_para"]:
        cfg = Config(L=64, p=0.5, condition=condition, b=0.0, seed=seed)
        outcomes[condition] = initial_grids(cfg, np.random.default_rng(seed))

    base_state, base_f = outcomes["none"]
    for condition, (state, f) in outcomes.items():
        assert np.array_equal(state, base_state), condition
        assert np.array_equal(f, base_f), condition


# --- ignition (AC7, AC8, AC9) ------------------------------------------------


def test_edge_ignition_burns_row0_fuel_only():
    cfg = Config(L=64, p=0.6, ignition="edge", regime="STUDY", settlement=False, seed=2)
    state, f = initial_grids(cfg, np.random.default_rng(cfg.seed))

    assert not np.any(state[0] == model.FUEL)
    assert not np.any(state[1:] == model.BURNING)


def test_random_cell_ignites_exactly_one_fuel_cell():
    cfg = Config(L=64, p=0.5, ignition="random_cell", seed=5)
    state, f = initial_grids(cfg, np.random.default_rng(cfg.seed))

    burning = np.argwhere(state == model.BURNING)
    assert burning.shape[0] == 1
    y, x = burning[0]
    assert f[y, x] > 0.0


def test_p_zero_random_cell_no_burn_no_raise():
    cfg = Config(L=64, p=0.0, ignition="random_cell", seed=1)
    state, f = initial_grids(cfg, np.random.default_rng(cfg.seed))
    assert not np.any(state == model.BURNING)


# --- determinism (AC10) ------------------------------------------------------


def test_determinism_same_config_and_seed(monkeypatch):
    monkeypatch.setattr(model.geometries, "generate", _treating_spy())
    cfg = Config(L=64, p=0.5, condition="random", b=0.2, settlement=True, seed=11)

    s1, f1 = initial_grids(cfg, np.random.default_rng(cfg.seed))
    s2, f2 = initial_grids(cfg, np.random.default_rng(cfg.seed))

    assert np.array_equal(s1, s2)
    assert np.array_equal(f1, f2)
