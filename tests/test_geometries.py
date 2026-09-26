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


def test_every_schema_condition_has_a_generator():
    # SPEC-09 shipped none/random, SPEC-10 the clustering family, SPEC-11
    # buffer; a condition the schema knows but nobody implemented would
    # raise NotImplementedError from generate at the first b > 0 run
    assert IMPLEMENTED == CONDITIONS


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
def test_reserved_params_are_accepted(condition, n_treat):
    # every generator tolerates both keys (DEC-007, DEC-008)
    if condition == "none" and n_treat > 0:
        pytest.skip("none takes no budget")
    # L=64 so a 32-side block leaves room for rings (buffer)
    mask = generate(condition, _rng(), _occupied_with_block(L=64, side=32), n_treat, phi=0.7, settlement_side=32)
    assert mask.dtype == bool


@pytest.mark.parametrize("condition", ["none", "random", "patches"])
@pytest.mark.parametrize("n_treat", [0, 40])
def test_reserved_params_are_ignored_by_non_strip_conditions(condition, n_treat):
    # none, random and patches use neither key; the strip conditions use
    # phi (DEC-008) and buffer uses settlement_side (DEC-007) by
    # construction, and are tested in their own sections below
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


# ===========================================================================
# SPEC-10 — clustering-scale family: patches, strips_perp, strips_para
# ===========================================================================

from src.geometries import CLUSTERING_LEVELS, _band_coordinate  # noqa: E402


def _component_sizes(mask):
    """Sizes of the 8-connected components of a bool mask (test-only; no
    scipy in the project)."""
    L_y, L_x = mask.shape
    seen = np.zeros_like(mask)
    sizes = []
    for y0, x0 in zip(*np.nonzero(mask)):
        if seen[y0, x0]:
            continue
        stack = [(y0, x0)]
        seen[y0, x0] = True
        n = 0
        while stack:
            y, x = stack.pop()
            n += 1
            for dy in (-1, 0, 1):
                for dx in (-1, 0, 1):
                    yy, xx = y + dy, x + dx
                    if 0 <= yy < L_y and 0 <= xx < L_x and mask[yy, xx] and not seen[yy, xx]:
                        seen[yy, xx] = True
                        stack.append((yy, xx))
        sizes.append(n)
    return sizes


def _along_fraction(mask, dy, dx):
    """Fraction of treated cells whose (dy, dx) neighbour is also treated,
    over cells whose neighbour is inside the grid."""
    L_y, L_x = mask.shape
    ys, xs = np.nonzero(mask)
    ok = (ys + dy >= 0) & (ys + dy < L_y) & (xs + dx >= 0) & (xs + dx < L_x)
    ys, xs = ys[ok], xs[ok]
    return mask[ys + dy, xs + dx].mean()


def _full(L=128):
    return np.ones((L, L), dtype=bool)


# --- registration -----------------------------------------------------------


def test_clustering_levels_are_the_nine_of_section_6_2():
    assert len(CLUSTERING_LEVELS) == 9
    assert [c for c, _ in CLUSTERING_LEVELS].count("patches") == 3
    assert [c for c, _ in CLUSTERING_LEVELS].count("strips_perp") == 3
    assert [c for c, _ in CLUSTERING_LEVELS].count("strips_para") == 3
    for condition, params in CLUSTERING_LEVELS:
        assert condition in IMPLEMENTED
        (key, value), = params.items()
        assert key == ("k" if condition == "patches" else "w")
        assert value in (4, 8, 16)


def test_all_nine_levels_hit_budget_exactly_over_seeds():
    # acceptance: >=50 seeds at p in {0.4, 0.55, 0.7}, b in {0.05, 0.15, 0.30}
    L = 64
    for condition, params in CLUSTERING_LEVELS:
        for p in (0.4, 0.55, 0.7):
            for b in (0.05, 0.15, 0.30):
                for seed in range(50):
                    occ = _occupied(seed=seed, L=L, p=p)
                    n_treat = round(b * int(occ.sum()))
                    mask = generate(condition, _rng(seed), occ, n_treat, phi=0.0, settlement_side=16, **params)
                    assert int((mask & occ).sum()) == n_treat, (condition, params, p, b, seed)
                    assert not (mask & ~occ).any()


# --- patches ----------------------------------------------------------------


def test_patches_k16_low_budget_exercises_trim():
    occ = _occupied(seed=0, L=64, p=0.5)
    n_treat = round(0.05 * int(occ.sum()))       # ~100 cells, one block covers ~128
    mask = generate("patches", _rng(), occ, n_treat, k=16)
    assert int(mask.sum()) == n_treat
    # everything treated sits inside a single 16x16 footprint
    ys, xs = np.nonzero(mask)
    assert ys.max() - ys.min() < 16 and xs.max() - xs.min() < 16


def test_patches_blocks_are_k_by_k_and_inside_the_grid():
    # p=1 and a budget below one block: the treated set is one full k x k
    # block minus trimmed cells, so its bounding box is exactly k x k
    L, k = 64, 8
    occ = _full(L)
    mask = generate("patches", _rng(5), occ, k * k - 3, k=k)
    ys, xs = np.nonzero(mask)
    assert ys.max() - ys.min() == k - 1 and xs.max() - xs.min() == k - 1
    assert int(mask.sum()) == k * k - 3


def test_patches_default_k_is_4():
    occ = _occupied()
    assert np.array_equal(
        generate("patches", _rng(), occ, 60),
        generate("patches", _rng(), occ, 60, k=4),
    )


def test_patches_ignores_phi_and_settlement_side():
    occ = _occupied()
    plain = generate("patches", _rng(), occ, 80, k=8)
    extra = generate("patches", _rng(), occ, 80, k=8, phi=0.7, settlement_side=32)
    assert np.array_equal(plain, extra)


@pytest.mark.parametrize("k", [0, -1, 2.5, "4", True, None])
def test_patches_rejects_bad_k(k):
    with pytest.raises(ValueError):
        generate("patches", _rng(), _occupied(), 10, k=k)


def test_patches_rejects_k_larger_than_grid():
    with pytest.raises(ValueError):
        generate("patches", _rng(), _occupied(L=32), 10, k=33)


def test_patches_raises_rather_than_loops(monkeypatch):
    monkeypatch.setattr(geometries, "_MAX_PATCH_PLACEMENTS", 2)
    with pytest.raises(RuntimeError):
        generate("patches", _rng(), _occupied(), 200, k=4)


def test_component_size_increases_with_clustering_scale():
    # §11: random (scale 1) -> patches(4) -> patches(8) -> patches(16)
    L, p, b = 128, 0.55, 0.15
    means = []
    for condition, params in [("random", {}), ("patches", {"k": 4}), ("patches", {"k": 8}), ("patches", {"k": 16})]:
        sizes = []
        for seed in range(3):
            occ = _occupied(seed=seed, L=L, p=p)
            n_treat = round(b * int(occ.sum()))
            sizes += _component_sizes(generate(condition, _rng(seed), occ, n_treat, **params))
        means.append(np.mean(sizes))
    assert means[0] < means[1] < means[2] < means[3], means


# --- strips: geometry of the band coordinate --------------------------------


def test_band_coordinate_orientation_at_0_quarter_and_half_pi():
    ys, xs = np.indices((16, 16), dtype=float)
    r = 1 / np.sqrt(2)
    # perp: bands indexed by the along-wind coordinate
    assert np.allclose(_band_coordinate((16, 16), 0.0, False), xs)              # east wind: bands are columns
    assert np.allclose(_band_coordinate((16, 16), np.pi / 2, False), -ys)       # north wind: bands are rows
    assert np.allclose(_band_coordinate((16, 16), np.pi / 4, False), (xs - ys) * r)
    # para: bands indexed by the across-wind coordinate (rotated 90 degrees)
    assert np.allclose(_band_coordinate((16, 16), 0.0, True), ys)
    assert np.allclose(_band_coordinate((16, 16), np.pi / 2, True), xs)
    assert np.allclose(_band_coordinate((16, 16), np.pi / 4, True), (xs + ys) * r)


# --- strips: the public masks -----------------------------------------------


@pytest.mark.parametrize(
    "phi, perp_along, para_along",
    [
        (0.0, (1, 0), (0, 1)),            # east wind: perp bands run down columns, para along rows
        (np.pi / 2, (0, 1), (1, 0)),      # north wind: the reverse
        (np.pi / 4, (1, 1), (1, -1)),     # diagonal wind: diagonal bands, both conditions
    ],
    ids=["phi=0", "phi=pi/2", "phi=pi/4"],
)
def test_strip_orientation_on_full_lattice(phi, perp_along, para_along):
    # DEC-008: bands at any phi. On a full lattice a band of width 4 shows
    # up as: along-band neighbour almost always treated, across-band
    # neighbour treated only ~3/4 of the time.
    L, w = 128, 4
    n_treat = round(0.3 * L * L)
    perp = generate("strips_perp", _rng(1), _full(L), n_treat, w=w, phi=phi)
    para = generate("strips_para", _rng(1), _full(L), n_treat, w=w, phi=phi)
    assert int(perp.sum()) == n_treat and int(para.sum()) == n_treat
    across_perp = (perp_along[1], -perp_along[0])
    across_para = (para_along[1], -para_along[0])
    assert _along_fraction(perp, *perp_along) > 0.95
    assert _along_fraction(perp, *across_perp) < 0.85
    assert _along_fraction(para, *para_along) > 0.95
    assert _along_fraction(para, *across_para) < 0.85


def test_strips_perp_and_para_at_phi0_are_orthogonal_with_same_budget():
    L, w = 64, 8
    for seed in range(3):
        occ = _occupied(seed=seed, L=L, p=0.55)
        n_treat = round(0.15 * int(occ.sum()))
        perp = generate("strips_perp", _rng(seed), occ, n_treat, w=w, phi=0.0)
        para = generate("strips_para", _rng(seed), occ, n_treat, w=w, phi=0.0)
        assert int(perp.sum()) == int(para.sum()) == n_treat
        # a column band's cells share x; a row band's share y
        assert len(np.unique(np.nonzero(perp)[1])) < len(np.unique(np.nonzero(perp)[0]))
        assert len(np.unique(np.nonzero(para)[0])) < len(np.unique(np.nonzero(para)[1]))


def test_strip_phase_varies_with_seed_and_is_reproducible():
    L = 64
    n_treat = round(0.3 * L * L)
    a = generate("strips_perp", _rng(0), _full(L), n_treat, w=4, phi=0.0)
    b = generate("strips_perp", _rng(0), _full(L), n_treat, w=4, phi=0.0)
    c = generate("strips_perp", _rng(1), _full(L), n_treat, w=4, phi=0.0)
    assert np.array_equal(a, b)
    assert not np.array_equal(a, c)


def test_strips_use_phi():
    occ = _occupied(L=64)
    n_treat = round(0.15 * int(occ.sum()))
    east = generate("strips_perp", _rng(0), occ, n_treat, w=4, phi=0.0)
    north = generate("strips_perp", _rng(0), occ, n_treat, w=4, phi=np.pi / 2)
    assert not np.array_equal(east, north)


def test_strips_default_w_is_4_and_phi_is_0():
    occ = _occupied(L=64)
    assert np.array_equal(
        generate("strips_perp", _rng(), occ, 100),
        generate("strips_perp", _rng(), occ, 100, w=4, phi=0.0),
    )


@pytest.mark.parametrize("w", [0, -2, 3.0, "8", False])
def test_strips_reject_bad_w(w):
    with pytest.raises(ValueError):
        generate("strips_perp", _rng(), _occupied(), 10, w=w)


def test_strip_bisection_terminates_over_the_experiment_1_grid():
    # w x b x p x phi of the Exp 1 / Exp 2 grids, at L=128 for speed and one
    # combination at the real L=256; exact budget every time
    for w in (4, 8, 16):
        for b in (0.05, 0.10, 0.15, 0.20, 0.25, 0.30):
            for p in (0.40, 0.50, 0.60, 0.70):
                for phi in (0.0, -np.pi / 2):
                    occ = _occupied(seed=3, L=128, p=p)
                    n_treat = round(b * int(occ.sum()))
                    for condition in ("strips_perp", "strips_para"):
                        mask = generate(condition, _rng(3), occ, n_treat, w=w, phi=phi)
                        assert int(mask.sum()) == n_treat, (condition, w, b, p, phi)
    occ = _occupied(seed=0, L=256, p=0.55)
    n_treat = round(0.15 * int(occ.sum()))
    assert int(generate("strips_perp", _rng(0), occ, n_treat, w=16, phi=-np.pi / 2).sum()) == n_treat


def test_strips_raise_rather_than_loop_when_bracket_impossible(monkeypatch):
    # a band mask that never covers anything can never reach the budget
    monkeypatch.setattr(geometries, "_band_mask", lambda *a, **k: np.zeros((32, 32), dtype=bool))
    occ = _occupied()
    with pytest.raises(RuntimeError):
        # budget well above one band's worth, so the bisection path is taken
        generate("strips_perp", _rng(), occ, int(occ.sum()) // 2, w=4, phi=0.0)


def test_strips_full_budget_is_touching_bands():
    occ = _occupied(L=64)
    mask = generate("strips_para", _rng(), occ, int(occ.sum()), w=4, phi=0.3)
    assert np.array_equal(mask, occ)


def test_strips_sub_band_budget_is_one_thinned_band_at_random_position():
    # DEC-024: below one band's worth, a single full-width band at a uniform
    # random position, thinned at random — the patches rule, not a band
    # pushed off the grid edge
    L, w = 64, 8
    n_treat = round(0.6 * w * L)                 # 60% of one band on a full lattice
    starts = set()
    for seed in range(12):
        mask = generate("strips_perp", _rng(seed), _full(L), n_treat, w=w, phi=0.0)
        assert int(mask.sum()) == n_treat
        xs = np.unique(np.nonzero(mask)[1])
        assert xs.max() - xs.min() < w              # one band's width
        assert mask.any(axis=0)[xs.min():xs.max() + 1].all()
        # thinned, so along-band adjacency is well below 1
        assert 0.4 < _along_fraction(mask, 1, 0) < 0.8
        starts.add(int(xs.min()))
    assert len(starts) > 3                          # position varies with seed
    assert max(starts) - min(starts) > w            # and is not pinned to one edge


# ===========================================================================
# SPEC-11 — buffer
# ===========================================================================

from src.model import BURNING, FUEL, SETTLEMENT, Config, initial_grids, run_fire  # noqa: E402


def _chebyshev_from_block(L, side):
    lo = L // 2 - side // 2
    hi = lo + side
    ys, xs = np.indices((L, L))
    dy = np.maximum(np.maximum(lo - ys, ys - (hi - 1)), 0)
    dx = np.maximum(np.maximum(lo - xs, xs - (hi - 1)), 0)
    return np.maximum(dy, dx)


def _ring_from_initial_grids(L, side):
    """The 1-cell ring around the settlement block as initial_grids actually
    places it — the generator must agree with the model, not with a
    re-derivation in this file."""
    cfg = Config(L=L, settlement=True, geometry_params={"settlement_side": side})
    state, _ = initial_grids(cfg, np.random.default_rng(0))
    block = state == SETTLEMENT
    ys, xs = np.nonzero(block)
    ring = np.zeros((L, L), dtype=bool)
    ring[ys.min() - 1:ys.max() + 2, xs.min() - 1:xs.max() + 2] = True
    return ring & ~block


def _occupied_with_block(seed=0, L=64, p=0.5, side=16):
    occ = _occupied(seed=seed, L=L, p=p)
    occ[_chebyshev_from_block(L, side) == 0] = False
    return occ


def test_buffer_requires_settlement_side():
    with pytest.raises(ValueError, match="settlement_side"):
        generate("buffer", _rng(), _occupied_with_block(), 50, phi=0.0)


@pytest.mark.parametrize("side", [0, -4, 2.5, "16", None])
def test_buffer_rejects_bad_settlement_side(side):
    with pytest.raises(ValueError):
        generate("buffer", _rng(), _occupied_with_block(), 50, settlement_side=side)


def test_buffer_rejects_side_that_does_not_fit():
    with pytest.raises(ValueError, match="fit"):
        generate("buffer", _rng(), _occupied_with_block(L=32), 10, settlement_side=40)


def test_buffer_config_without_settlement_raises_at_config():
    # §4.4: caught at construction, never reaches the generator
    with pytest.raises(ValueError):
        Config(L=64, condition="buffer", b=0.1, settlement=False)


def test_buffer_is_contiguous_annulus_except_outer_ring():
    L, side = 64, 16
    dist = _chebyshev_from_block(L, side)
    occ = _full(L)
    occ[dist == 0] = False
    ring = lambda r: int((dist == r).sum())
    # two full rings plus half of the third
    n_treat = ring(1) + ring(2) + ring(3) // 2
    mask = generate("buffer", _rng(1), occ, n_treat, settlement_side=side)
    assert int(mask.sum()) == n_treat
    assert mask[dist == 1].all() and mask[dist == 2].all()      # complete inner rings
    assert int(mask[dist == 3].sum()) == ring(3) // 2            # partial outer ring
    assert not mask[dist == 0].any() and not mask[dist > 3].any()


def test_buffer_outer_ring_fill_is_random_and_seeded():
    L, side = 64, 16
    dist = _chebyshev_from_block(L, side)
    occ = _full(L)
    occ[dist == 0] = False
    n_treat = int((dist == 1).sum()) + int((dist == 2).sum()) // 2
    a = generate("buffer", _rng(0), occ, n_treat, settlement_side=side)
    b = generate("buffer", _rng(0), occ, n_treat, settlement_side=side)
    c = generate("buffer", _rng(1), occ, n_treat, settlement_side=side)
    assert np.array_equal(a, b)
    assert not np.array_equal(a, c)
    assert np.array_equal(a[dist == 1], c[dist == 1])            # inner ring identical


def test_buffer_first_ring_matches_the_block_initial_grids_places():
    # the generator and initial_grids must agree on where the block is,
    # for every side SPEC-12's pilot will try (DEC-007)
    L = 128
    for side in (8, 16, 32, 48):
        ring1 = _ring_from_initial_grids(L, side)
        occ = _full(L)
        occ[_chebyshev_from_block(L, side) == 0] = False
        mask = generate("buffer", _rng(), occ, int(ring1.sum()), settlement_side=side)
        assert np.array_equal(mask, ring1)


def test_buffer_grows_from_the_32_block_not_the_default():
    L = 96
    occ = _full(L)
    occ[_chebyshev_from_block(L, 32) == 0] = False
    mask = generate("buffer", _rng(), occ, 4 * (32 + 1), settlement_side=32)
    assert np.array_equal(mask, _ring_from_initial_grids(L, 32))
    assert not np.array_equal(mask, _ring_from_initial_grids(L, 16))
    # and the 16-ring lies inside the 32-block, so nothing there is treated
    assert not mask[_ring_from_initial_grids(L, 16)].any()


def test_buffer_never_treats_inside_the_block_even_if_occupied_there():
    L, side = 64, 16
    occ = _occupied(seed=2, L=L, p=0.6)                # block region occupied
    dist = _chebyshev_from_block(L, side)
    n_treat = int((occ & (dist > 0)).sum()) // 3
    mask = generate("buffer", _rng(), occ, n_treat, settlement_side=side)
    assert not mask[dist == 0].any()
    assert int(mask.sum()) == n_treat


def test_buffer_skips_empty_cells_and_meets_budget_over_seeds():
    # acceptance: >=50 seeds at b in {0.05, 0.15, 0.30}, p in {0.4, 0.55, 0.7}
    L, side = 64, 16
    dist = _chebyshev_from_block(L, side)
    for p in (0.4, 0.55, 0.7):
        for b in (0.05, 0.15, 0.30):
            for seed in range(50):
                occ = _occupied_with_block(seed=seed, L=L, p=p, side=side)
                n_treat = round(b * int(occ.sum()))
                mask = generate("buffer", _rng(seed), occ, n_treat, phi=0.0, settlement_side=side)
                assert int(mask.sum()) == n_treat, (p, b, seed)
                assert not (mask & ~occ).any()
                # annulus: every treated cell's ring index is <= the outermost,
                # and every occupied cell on a strictly inner ring is treated
                r = int(dist[mask].max())
                assert (mask | ~occ)[(dist > 0) & (dist < r)].all()


def test_buffer_truncates_at_lattice_edge_and_meets_budget():
    L, side = 64, 16
    occ = _occupied_with_block(seed=4, L=L, p=0.5, side=side)
    mask = generate("buffer", _rng(), occ, int(occ.sum()), settlement_side=side)   # everything
    assert np.array_equal(mask, occ)
    # rings had to reach every edge to get there
    assert mask[0, :].any() and mask[-1, :].any() and mask[:, 0].any() and mask[:, -1].any()


def test_buffer_unachievable_budget_raises_clearly():
    L, side = 64, 16
    occ = _occupied(seed=5, L=L, p=0.5)                # includes cells inside the block
    with pytest.raises(ValueError, match="unachievable"):
        generate("buffer", _rng(), occ, int(occ.sum()), settlement_side=side)


def test_buffer_ignores_phi():
    occ = _occupied_with_block()
    a = generate("buffer", _rng(), occ, 150, settlement_side=16, phi=0.0)
    b = generate("buffer", _rng(), occ, 150, settlement_side=16, phi=0.7)
    assert np.array_equal(a, b)


def test_buffer_through_run_fire_wraps_the_settlement():
    for seed in range(3):
        cfg = Config(L=64, p=0.55, settlement=True, condition="buffer", b=0.15, seed=seed)
        state, f = initial_grids(cfg, np.random.default_rng(cfg.seed))
        occupied = (state == FUEL) | (state == BURNING)
        treated = occupied & (f == cfg.f_treat)
        assert int(treated.sum()) == round(cfg.b * int(occupied.sum()))
        dist = _chebyshev_from_block(cfg.L, 16)
        assert not treated[state == SETTLEMENT].any()
        # everything occupied on ring 1 is treated at this budget
        assert treated[(dist == 1) & occupied].all()
        result = run_fire(cfg)
        assert result.n_treated == int(treated.sum())


def test_buffer_ignition_inside_the_ring_is_allowed():
    # §3.6: do not exclude ignition regions. Over many seeds some fires
    # must start inside the treated annulus.
    inside = 0
    for seed in range(60):
        cfg = Config(L=64, p=0.55, settlement=True, condition="buffer", b=0.30, seed=seed)
        state, f = initial_grids(cfg, np.random.default_rng(cfg.seed))
        by, bx = np.nonzero(state == BURNING)
        if by.size and f[by[0], bx[0]] == cfg.f_treat:
            inside += 1
    assert inside > 0
