"""Invariants I1-I11 (project-context.md §7).

Each is a permanently-failing placeholder until the spec named in its reason
implements it, so an unowned invariant shows up as a failing test rather than
an absence (SPEC-01).
"""

import dataclasses

import numpy as np
import pytest

from src.model import BURNING, BURNT, Config, run_fire


@pytest.mark.xfail(reason="I1 percolation limit lands in SPEC-07", strict=False)
def test_i1():
    raise NotImplementedError


def test_i2_determinism():
    """Run any config twice; every RunResult field equal (project-context.md
    §7 I2)."""
    cfg = Config(L=96, p=0.5, kappa=2.0, diagonal_factor=True, seed=7)
    r1 = run_fire(cfg, capture_scar=True)
    r2 = run_fire(cfg, capture_scar=True)

    for f in dataclasses.fields(r1):
        v1, v2 = getattr(r1, f.name), getattr(r2, f.name)
        if isinstance(v1, np.ndarray):
            assert np.array_equal(v1, v2), f"field {f.name} differs"
        else:
            assert v1 == v2, f"field {f.name} differs: {v1!r} != {v2!r}"


def test_i3_deterministic_front_is_square():
    """p=1, beta=1, kappa=0, diagonal_factor=False: front expands exactly 1
    cell/step in Chebyshev distance from the ignition cell (project-context.md
    §7 I3, §3.7 O6 — Chebyshev growth is asserted only in this
    diagonal_factor=False case)."""
    L = 41
    cfg = Config(
        L=L, p=1.0, beta=1.0, kappa=0.0, diagonal_factor=False,
        ignition="random_cell", seed=3,
    )
    result = run_fire(cfg, capture_scar=True)

    iy, ix = result.ignition_y, result.ignition_x
    ys, xs = np.indices((L, L))
    chebyshev = np.maximum(np.abs(ys - iy), np.abs(xs - ix))

    burned_or_burning = np.isin(result.scar, [BURNING, BURNT])
    # Everything within range of the run should have ignited by exactly its
    # Chebyshev distance, and nothing else should have ignited at all.
    np.testing.assert_array_equal(result.ignition_step >= 0, burned_or_burning)
    np.testing.assert_array_equal(
        result.ignition_step[burned_or_burning],
        chebyshev[burned_or_burning],
    )


def test_i9_conservation():
    """burned_cells + still_burning_cells <= n_occupied, and no cell leaves
    BURNT (project-context.md §7 I9)."""
    for seed in range(5):
        cfg = Config(L=64, p=0.55, seed=seed)
        result = run_fire(cfg)
        assert result.burned_cells + result.still_burning_cells <= result.n_occupied

    # Truncate hard enough that cells are still BURNING at cutoff, and
    # confirm burned_cells excludes them (project-context.md §3.7).
    cfg = Config(L=64, p=0.9, max_steps=2, seed=1)
    result = run_fire(cfg)
    assert result.truncated is True
    assert result.still_burning_cells > 0
    assert result.burned_cells + result.still_burning_cells <= result.n_occupied


@pytest.mark.slow
def test_i4_isotropy():
    """kappa=0: scar second moments in x and y equal within a 99% CI over
    200 replicates (project-context.md §7 I4). SPEC-04.

    STUDY defaults at p=0.55, L=128, unbounded: fires are partial (mean
    burned fraction ~0.5) so the check is on real scar shapes, not on a
    fully burnt square. Seeds are fixed, so the test is deterministic; the
    CI is 99% so that a re-seeding is unlikely to flip it (DEC-022).
    """
    from src.metrics import scar_second_moments

    R = 200
    diffs = np.empty(R)
    sizes = np.empty(R)
    for seed in range(R):
        cfg = Config(L=128, p=0.55, kappa=0.0, seed=seed)
        result = run_fire(cfg, capture_scar=True)
        var_y, var_x = scar_second_moments(result.scar)
        diffs[seed] = var_x - var_y
        sizes[seed] = 0.5 * (var_x + var_y)

    # the scars must be non-trivial for the comparison to mean anything
    assert sizes.mean() > 100.0

    mean = diffs.mean()
    se = diffs.std(ddof=1) / np.sqrt(R)
    assert abs(mean) < 2.576 * se, (
        f"anisotropic at kappa=0: mean(var_x - var_y) = {mean:.2f} ± {se:.2f}"
    )


@pytest.mark.slow
def test_i5_wind_monotonicity():
    """Mean scar centroid projection on phi strictly increasing over
    kappa in {0, 1, 2, 4} (project-context.md §7 I5). SPEC-04.

    Measured in a bounded-time design — p=1.0, max_steps=30, L=128, phi=0,
    R=200 per kappa — so the displacement reflects the kernel alone. Run to
    extinction the measure is confounded: at kappa=0 the fire burns the
    whole lattice and its centroid sits at the centre regardless of
    ignition, and at kappa=4 the plume either dies or hits the edge, so the
    unbounded means are not monotone (DEC-022, with the numbers).
    """
    from src.metrics import centroid_projection, scar_centroid

    R = 200
    kappas = [0.0, 1.0, 2.0, 4.0]
    means = []
    ses = []
    for kappa in kappas:
        proj = np.empty(R)
        for seed in range(R):
            cfg = Config(
                L=128, p=1.0, kappa=kappa, phi=0.0, max_steps=30, seed=seed
            )
            result = run_fire(cfg, capture_scar=True)
            assert result.burned_cells > 0
            origin = (result.ignition_y, result.ignition_x)
            proj[seed] = centroid_projection(
                scar_centroid(result.scar), origin, cfg.phi
            )
        means.append(proj.mean())
        ses.append(proj.std(ddof=1) / np.sqrt(R))

    for i in range(len(kappas) - 1):
        assert means[i] < means[i + 1], (
            f"not monotone: kappa={kappas[i]} -> {means[i]:.2f}±{ses[i]:.2f}, "
            f"kappa={kappas[i + 1]} -> {means[i + 1]:.2f}±{ses[i + 1]:.2f}"
        )
    # and the whole ordering is well separated, not a coin flip
    assert means[-1] - means[0] > 10 * max(ses)


def _result_fields(result):
    """RunResult as a dict, arrays included, for byte-equality checks."""
    return {f.name: getattr(result, f.name) for f in dataclasses.fields(result)}


def _assert_identical(a, b, label):
    for name, va in _result_fields(a).items():
        vb = getattr(b, name)
        if isinstance(va, np.ndarray):
            assert np.array_equal(va, vb), f"{label}: field {name!r} differs"
        else:
            assert va == vb, f"{label}: field {name!r} differs ({va!r} != {vb!r})"


# Every condition code path, with the geometry_params it would carry in the
# experiments. At b=0 the params are irrelevant — generate must return
# before reading them — which is exactly what I6 checks. SPEC-10 and
# SPEC-11 need not touch this list: their conditions are already here.
_I6_CONDITIONS = {
    "none": {},
    "random": {},
    "patches": {"k": 8},
    "strips_perp": {"w": 4},
    "strips_para": {"w": 4},
    "buffer": {},
}


@pytest.mark.parametrize("settlement", [False, True], ids=["open", "settlement"])
def test_i6_null_treatment(settlement):
    """Same seed, every condition, b=0 ⟹ byte-identical results
    (project-context.md §7 I6). Catches a generator that draws from rng
    before checking n_treat == 0. SPEC-09.

    "buffer" requires settlement=True (§4.4), so it is compared only in the
    settlement group; every other condition is compared in both.
    """
    for seed in (0, 1):
        reference = None
        for condition, params in _I6_CONDITIONS.items():
            if condition == "buffer" and not settlement:
                continue
            cfg = Config(
                L=64, p=0.55, kappa=2.0, condition=condition, b=0.0,
                geometry_params=params, settlement=settlement, seed=seed,
            )
            result = run_fire(cfg, capture_scar=True)
            assert result.n_treated == 0
            if reference is None:
                reference = result
            else:
                _assert_identical(
                    result, reference, f"seed={seed} condition={condition!r}"
                )


def test_i7_budget_parity():
    """n_treated within tolerance of round(b * n_occupied) for every
    implemented condition (project-context.md §7 I7). SPEC-09.

    This is the generator half of I7 — asserted live in generate and
    checked here end-to-end through run_fire. The "again over a results
    frame" half needs a results frame and lands with the harness (SPEC-05,
    DEC-023).
    """
    from src.geometries import IMPLEMENTED, budget_tolerance

    for condition in IMPLEMENTED:
        if condition == "none":
            continue
        for b in (0.05, 0.10, 0.15, 0.30):
            for p in (0.4, 0.6):
                for seed in range(3):
                    cfg = Config(
                        L=64, p=p, condition=condition, b=b, seed=seed,
                        settlement=(condition == "buffer"),   # §4.4
                    )
                    result = run_fire(cfg)
                    nominal = round(b * result.n_occupied)
                    assert abs(result.n_treated - nominal) <= budget_tolerance(nominal), (
                        f"{condition} b={b} p={p} seed={seed}: "
                        f"n_treated={result.n_treated}, nominal={nominal}"
                    )
                    if condition == "random":
                        assert result.n_treated == nominal   # exact, §4.2


def test_i8_treatment_placement():
    """mask & ~occupied is empty for every implemented condition
    (project-context.md §7 I8). SPEC-09."""
    from src.geometries import IMPLEMENTED, generate

    for seed in range(3):
        rng = np.random.default_rng(seed)
        occupied = rng.random((64, 64)) < 0.5
        # a settlement block of the default side is never occupied (§3.6);
        # carving it out keeps the field consistent for every condition
        occupied[24:40, 24:40] = False
        n_occ = int(occupied.sum())
        for condition in IMPLEMENTED:
            for n_treat in (0, 1, n_occ // 10, n_occ // 2, n_occ):
                if condition == "none" and n_treat > 0:
                    continue
                mask = generate(
                    condition, np.random.default_rng(seed), occupied, n_treat,
                    phi=0.0, settlement_side=16,   # what the call site always passes
                )
                assert mask.dtype == bool and mask.shape == occupied.shape
                assert not (mask & ~occupied).any(), (
                    f"{condition} n_treat={n_treat} seed={seed} treated an unoccupied cell"
                )


@pytest.mark.xfail(reason="I9 conservation lands in SPEC-03", strict=False)
def test_i9():
    raise NotImplementedError


@pytest.mark.xfail(reason="I10 no truncation lands in SPEC-06", strict=False)
def test_i10():
    raise NotImplementedError


@pytest.mark.xfail(reason="I11 lattice frame invariance lands in SPEC-16", strict=False)
def test_i11():
    raise NotImplementedError
