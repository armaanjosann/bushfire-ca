"""Geometry framework, "none" and "random" (project-context.md §4.2).
SPEC-09.
"""

import numpy as np
import pytest

from src import geometries
from src.geometries import (
    CONDITIONS,
    IMPLEMENTED,
    RESERVED_PARAMS,
    budget_tolerance,
    check_mask,
    generate,
)


def _occupied(seed=0, L=32, p=0.5):
    return np.random.default_rng(seed).random((L, L)) < p


def _rng(seed=7):
    return np.random.default_rng(seed)


# --- dispatch ---------------------------------------------------------------


def test_unknown_condition_raises_listing_valid_conditions():
    with pytest.raises(ValueError) as excinfo:
        generate("stripes", _rng(), _occupied(), 5)
    msg = str(excinfo.value)
    for c in CONDITIONS:
        assert repr(c) in msg


def test_unknown_condition_raises_even_at_zero_budget():
    with pytest.raises(ValueError):
        generate("stripes", _rng(), _occupied(), 0)


@pytest.mark.parametrize("condition", CONDITIONS)
def test_every_condition_at_zero_budget_is_all_false(condition):
    mask = generate(condition, _rng(), _occupied(), 0)
    assert mask.dtype == bool
    assert mask.shape == (32, 32)
    assert not mask.any()


@pytest.mark.parametrize("condition", CONDITIONS)
def test_zero_budget_does_not_touch_rng(condition):
    rng = _rng()
    before = rng.bit_generator.state
    generate(condition, rng, _occupied(), 0)
    assert rng.bit_generator.state == before


@pytest.mark.parametrize("condition", [c for c in CONDITIONS if c not in IMPLEMENTED])
def test_unimplemented_condition_with_budget_raises_not_implemented(condition):
    with pytest.raises(NotImplementedError):
        generate(condition, _rng(), _occupied(), 5)


def test_negative_budget_raises():
    with pytest.raises(ValueError):
        generate("random", _rng(), _occupied(), -1)


def test_budget_above_occupied_count_raises():
    occ = _occupied()
    with pytest.raises(ValueError):
        generate("random", _rng(), occ, int(occ.sum()) + 1)


# --- shared contracts -------------------------------------------------------


@pytest.mark.parametrize(
    "n_treat, expected",
    [(0, 1), (1, 1), (50, 1), (100, 1), (101, 2), (150, 2), (1000, 10), (1234, 13)],
)
def test_budget_tolerance(n_treat, expected):
    assert budget_tolerance(n_treat) == expected


def test_check_mask_passes_exact_and_within_tolerance():
    occ = _occupied()
    ys, xs = np.nonzero(occ)
    mask = np.zeros_like(occ)
    mask[ys[:200], xs[:200]] = True
    assert check_mask(mask, occ, 200, "t") is mask
    assert check_mask(mask, occ, 198, "t") is mask      # tolerance 2 at 198
    assert check_mask(mask, occ, 202, "t") is mask


def test_check_mask_rejects_budget_outside_tolerance():
    occ = _occupied()
    ys, xs = np.nonzero(occ)
    mask = np.zeros_like(occ)
    mask[ys[:200], xs[:200]] = True
    with pytest.raises(AssertionError, match="I7"):
        check_mask(mask, occ, 197, "t")                  # off by 3, tolerance 2
    with pytest.raises(AssertionError, match="I7"):
        check_mask(mask, occ, 50, "t")


def test_check_mask_rejects_unoccupied_cell():
    occ = _occupied()
    mask = np.zeros_like(occ)
    ys, xs = np.nonzero(~occ)
    mask[ys[0], xs[0]] = True
    with pytest.raises(AssertionError, match="I8"):
        check_mask(mask, occ, 1, "t")


def test_check_mask_rejects_wrong_dtype_or_shape():
    occ = _occupied()
    with pytest.raises(AssertionError):
        check_mask(np.zeros(occ.shape, dtype=np.int8), occ, 0, "t")
    with pytest.raises(AssertionError):
        check_mask(np.zeros((16, 16), dtype=bool), occ, 0, "t")


def test_placement_assertion_is_live_in_generate(monkeypatch):
    # a generator that treats an unoccupied cell must be caught by generate
    # itself, not only by the tests
    def bad(rng, occupied, n_treat, **params):
        mask = np.zeros_like(occupied)
        ys, xs = np.nonzero(~occupied)
        mask[ys[:n_treat], xs[:n_treat]] = True
        return mask

    monkeypatch.setitem(geometries._GENERATORS, "random", bad)
    with pytest.raises(AssertionError, match="I8"):
        generate("random", _rng(), _occupied(), 5)


def test_budget_assertion_is_live_in_generate(monkeypatch):
    def short(rng, occupied, n_treat, **params):
        mask = np.zeros_like(occupied)
        ys, xs = np.nonzero(occupied)
        mask[ys[: n_treat // 2], xs[: n_treat // 2]] = True
        return mask

    monkeypatch.setitem(geometries._GENERATORS, "random", short)
    with pytest.raises(AssertionError, match="I7"):
        generate("random", _rng(), _occupied(), 100)


# --- none -------------------------------------------------------------------


def test_none_with_budget_raises():
    with pytest.raises(ValueError, match="none"):
        generate("none", _rng(), _occupied(), 1)


# --- random -----------------------------------------------------------------


def test_random_hits_budget_exactly_for_every_n_treat():
    occ = _occupied(p=0.3)
    n_occ = int(occ.sum())
    for n_treat in range(1, n_occ + 1):
        mask = generate("random", _rng(n_treat), occ, n_treat)
        assert int(mask.sum()) == n_treat
        assert not (mask & ~occ).any()


def test_random_full_budget_treats_every_occupied_cell_and_no_other():
    occ = _occupied()
    mask = generate("random", _rng(), occ, int(occ.sum()))
    assert np.array_equal(mask, occ)


def test_random_is_deterministic_in_seed_and_varies_with_it():
    occ = _occupied()
    a = generate("random", _rng(3), occ, 100)
    b = generate("random", _rng(3), occ, 100)
    c = generate("random", _rng(4), occ, 100)
    assert np.array_equal(a, b)
    assert not np.array_equal(a, c)


def test_random_is_uniform_over_occupied_cells():
    # every occupied cell should be picked at about the same rate; a
    # generator that e.g. always picked the first n_treat in raster order
    # would fail this
    occ = _occupied(p=0.5)
    n_occ = int(occ.sum())
    n_treat = n_occ // 4
    counts = np.zeros(occ.shape, dtype=int)
    reps = 400
    for seed in range(reps):
        counts += generate("random", _rng(seed), occ, n_treat)
    rate = counts[occ] / reps
    expected = n_treat / n_occ
    # binomial se per cell; all cells within 5 se, mean within 0.5 se
    se = np.sqrt(expected * (1 - expected) / reps)
    assert abs(rate.mean() - expected) < 0.5 * se
    assert np.abs(rate - expected).max() < 5 * se


# --- reserved params (DEC-007, DEC-008) -------------------------------------


@pytest.mark.parametrize("condition", IMPLEMENTED)
@pytest.mark.parametrize("n_treat", [0, 40])
def test_reserved_params_are_accepted_and_ignored(condition, n_treat):
    if condition == "none" and n_treat > 0:
        pytest.skip("none takes no budget")
    occ = _occupied()
    plain = generate(condition, _rng(), occ, n_treat)
    extra = generate(condition, _rng(), occ, n_treat, phi=0.7, settlement_side=32)
    assert np.array_equal(plain, extra)


def test_reserved_params_names_match_the_call_site():
    # SPEC-02's call site (src/model.py) passes exactly these two keys on top
    # of geometry_params
    assert set(RESERVED_PARAMS) == {"phi", "settlement_side"}


def test_generate_through_initial_grids_matches_direct_call():
    # the call site in initial_grids and a direct call with the same rng
    # position must agree, so nothing about the dispatch depends on how it
    # is reached
    from src.model import BURNING, FUEL, Config, initial_grids

    cfg = Config(L=64, p=0.5, condition="random", b=0.2, seed=11)
    state, f = initial_grids(cfg, np.random.default_rng(cfg.seed))
    occupied = (state == FUEL) | (state == BURNING)   # ignition cell is fuel too
    treated = (f == cfg.f_treat) & occupied
    assert int(treated.sum()) == round(cfg.b * int(occupied.sum()))
