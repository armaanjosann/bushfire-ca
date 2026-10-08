"""Metrics and scar statistics (project-context.md §3.5, §3.6, §4.3, §5).
SPEC-04.
"""

import math

import numpy as np
import pytest

from src.metrics import (
    burned_fraction,
    burned_fraction_of_fuel,
    centroid_projection,
    reached_edge,
    scar_centroid,
    scar_second_moments,
    settlement_ring,
    spanned,
)
from src.model import (
    BURNING,
    BURNT,
    EMPTY,
    FUEL,
    SETTLEMENT,
    SETTLEMENT_SIDE,
    Config,
    initial_grids,
    run_fire,
)


def _grid(L=32, fill=FUEL):
    return np.full((L, L), fill, dtype=np.int8)


# --- fractions --------------------------------------------------------------


def test_burned_fraction():
    assert burned_fraction(25, 100) == 0.25
    assert burned_fraction(0, 100) == 0.0


def test_burned_fraction_of_fuel():
    assert burned_fraction_of_fuel(25, 50) == 0.5


def test_burned_fraction_of_fuel_zero_fuel_is_zero_not_error():
    assert burned_fraction_of_fuel(0, 0) == 0.0


# --- spanned ----------------------------------------------------------------


def test_spanned_true_with_one_burnt_cell_in_last_row():
    L = 32
    state = _grid(L)
    state[L - 1, 7] = BURNT
    assert spanned(state) is True


def test_spanned_false_with_none_in_last_row():
    L = 32
    state = _grid(L)
    state[L - 2, :] = BURNT          # everything but the last row
    assert spanned(state) is False


def test_spanned_ignores_burning_cells():
    L = 32
    state = _grid(L)
    state[L - 1, 3] = BURNING
    assert spanned(state) is False


# --- reached_edge -----------------------------------------------------------


@pytest.mark.parametrize(
    "y, x",
    [(0, 10), (31, 10), (10, 0), (10, 31)],
    ids=["top", "bottom", "left", "right"],
)
def test_reached_edge_true_for_each_edge_separately(y, x):
    state = _grid(32)
    state[y, x] = BURNT
    assert reached_edge(state) is True


def test_reached_edge_false_for_interior_scar():
    state = _grid(32)
    state[1:31, 1:31] = BURNT        # all interior, no edge cell
    assert reached_edge(state) is False


# --- settlement_ring --------------------------------------------------------


@pytest.mark.parametrize("L, side", [(64, 16), (256, 16), (128, 32), (64, 9)])
def test_settlement_ring_size_and_placement(L, side):
    ring = settlement_ring(L, side)
    assert ring.shape == (L, L)
    assert ring.dtype == bool
    assert ring.sum() == 4 * (side + 1)

    cfg = Config(L=L, settlement=True, geometry_params={"settlement_side": side})
    state, _ = initial_grids(cfg, np.random.default_rng(0))
    block = state == SETTLEMENT
    assert block.sum() == side * side
    # none of the ring is inside the block, and the ring is exactly the
    # block's 1-cell dilation minus the block
    assert not (ring & block).any()
    ys, xs = np.nonzero(block)
    lo_y, hi_y, lo_x, hi_x = ys.min(), ys.max(), xs.min(), xs.max()
    expected = np.zeros((L, L), dtype=bool)
    expected[lo_y - 1:hi_y + 2, lo_x - 1:hi_x + 2] = True
    expected &= ~block
    assert np.array_equal(ring, expected)


# --- scar shape -------------------------------------------------------------


def test_scar_centroid_of_symmetric_scar_is_its_centre():
    state = _grid(32, fill=EMPTY)
    state[10:15, 20:27] = BURNT      # rows 10..14, cols 20..26
    cy, cx = scar_centroid(state)
    assert cy == pytest.approx(12.0)
    assert cx == pytest.approx(23.0)


def test_scar_centroid_ignores_non_burnt_cells():
    state = _grid(32, fill=EMPTY)
    state[10:15, 20:27] = BURNT
    state[0, 0] = BURNING
    state[31, 31] = FUEL
    assert scar_centroid(state) == pytest.approx((12.0, 23.0))


def test_scar_centroid_of_empty_scar_is_nan():
    cy, cx = scar_centroid(_grid(32, fill=EMPTY))
    assert math.isnan(cy) and math.isnan(cx)


def test_scar_second_moments_wider_in_x_gives_var_x_gt_var_y():
    state = _grid(32, fill=EMPTY)
    state[14:18, 4:28] = BURNT       # 4 tall, 24 wide
    var_y, var_x = scar_second_moments(state)
    assert var_x > var_y
    assert var_y == pytest.approx(np.var(np.arange(4)))
    assert var_x == pytest.approx(np.var(np.arange(24)))


def test_scar_second_moments_of_empty_scar_is_zero():
    assert scar_second_moments(_grid(32, fill=EMPTY)) == (0.0, 0.0)


# --- centroid_projection ----------------------------------------------------


def test_centroid_projection_phi_zero_is_plus_x():
    assert centroid_projection((10.0, 15.0), (10.0, 10.0), 0.0) == pytest.approx(5.0)
    assert centroid_projection((15.0, 10.0), (10.0, 10.0), 0.0) == pytest.approx(0.0)


def test_centroid_projection_minus_half_pi_is_plus_y():
    # §6.1: phi = -pi/2 blows from row 0 towards row L-1, i.e. +y
    phi = -np.pi / 2
    assert centroid_projection((15.0, 10.0), (10.0, 10.0), phi) == pytest.approx(5.0)
    assert centroid_projection((10.0, 15.0), (10.0, 10.0), phi) == pytest.approx(0.0)


def test_centroid_projection_matches_wind_kernel_convention():
    # the direction wind_weights favours must be the direction that projects
    # positively, for an off-axis phi too
    from src.model import NEIGHBOURS, wind_weights

    phi = 0.7
    w = wind_weights(kappa=4.0, phi=phi, diagonal_factor=False)
    dy, dx = NEIGHBOURS[int(np.argmax(w))]
    assert centroid_projection((dy, dx), (0, 0), phi) > 0
    assert centroid_projection((-dy, -dx), (0, 0), phi) < 0


# --- run_fire derived fields (DEC-006) ---------------------------------------


def test_run_fire_random_cell_nulls():
    r = run_fire(Config(L=64, p=0.5, ignition="random_cell", seed=1))
    assert r.spanned is None
    assert isinstance(r.reached_edge, bool)
    assert isinstance(r.burned_fraction, float)
    assert isinstance(r.burned_fraction_of_fuel, float)
    assert r.burned_fraction == pytest.approx(r.burned_cells / r.n_cells)
    assert r.burned_fraction_of_fuel == pytest.approx(r.burned_cells / r.n_occupied)


def test_run_fire_edge_nulls():
    r = run_fire(Config(L=64, p=0.5, ignition="edge", seed=1))
    assert r.reached_edge is None
    assert isinstance(r.spanned, bool)


def test_run_fire_no_settlement_gives_none_for_both_settlement_fields():
    r = run_fire(Config(L=64, p=0.5, settlement=False, seed=1))
    assert r.settlement_reached is None
    assert r.settlement_reached_step is None


def test_run_fire_settlement_gives_bool_and_consistent_step():
    reached_any = False
    for seed in range(8):
        r = run_fire(Config(L=64, p=0.6, settlement=True, seed=seed))
        assert isinstance(r.settlement_reached, bool)
        if r.settlement_reached:
            reached_any = True
            assert isinstance(r.settlement_reached_step, int)
            assert 0 <= r.settlement_reached_step <= r.steps
        else:
            assert r.settlement_reached_step is None
    assert reached_any, "no seed reached the settlement; test is not exercising the ring"


def test_run_fire_settlement_reached_matches_scar_against_ring():
    # if any BURNT cell sits on the ring the fire reached it, and vice versa
    # (tau=1, so every ignited ring cell is BURNT at extinction)
    for seed in range(8):
        cfg = Config(L=64, p=0.6, settlement=True, seed=seed)
        r = run_fire(cfg, capture_scar=True)
        ring = settlement_ring(cfg.L, SETTLEMENT_SIDE)
        assert r.settlement_reached == bool((r.scar[ring] == BURNT).any())
        if r.settlement_reached:
            first = int(r.ignition_step[ring & (r.scar == BURNT)].min())
            assert r.settlement_reached_step == first


def test_run_fire_settlement_side_override_checks_the_32_ring(monkeypatch):
    # DEC-007: geometry_params["settlement_side"] wins over SETTLEMENT_SIDE.
    # Build a p=1 deterministic fire (no rng in play once the fuel bed is
    # full) so the reach step is exactly the Chebyshev distance to the ring.
    cfg = Config(
        L=96, p=1.0, beta=1.0, kappa=0.0, diagonal_factor=False,
        settlement=True, geometry_params={"settlement_side": 32}, seed=0,
    )
    r = run_fire(cfg, capture_scar=True)
    assert r.settlement_reached is True
    ring32 = settlement_ring(cfg.L, 32)
    ring16 = settlement_ring(cfg.L, 16)
    # the 16-ring lies inside the 32-block, so it can never burn; if the
    # default were used the check would be looking at settlement cells
    assert (r.scar[ring16] == SETTLEMENT).all()
    assert r.settlement_reached_step == int(r.ignition_step[ring32].min())


def test_run_fire_ignition_on_ring_is_reached_at_step_zero():
    # a random_cell ignition landing on the ring counts (project-context.md
    # §3.6: "at any time during the run"), recorded as step 0 (DEC-020)
    L, side = 64, 16
    ring = settlement_ring(L, side)
    ys, xs = np.nonzero(ring)
    target = (int(ys[0]), int(xs[0]))
    for seed in range(200):
        cfg = Config(L=L, p=0.5, settlement=True, seed=seed)
        state, _ = initial_grids(cfg, np.random.default_rng(seed))
        by, bx = np.nonzero(state == BURNING)
        if by.size and ring[by[0], bx[0]]:
            r = run_fire(cfg)
            assert r.settlement_reached is True
            assert r.settlement_reached_step == 0
            return
    pytest.skip("no seed in range ignited on the ring")


def test_run_fire_zero_fuel_derived_fields():
    r = run_fire(Config(L=64, p=0.0, ignition="random_cell", seed=0))
    assert r.burned_fraction == 0.0
    assert r.burned_fraction_of_fuel == 0.0
    assert r.reached_edge is False
    assert r.spanned is None
