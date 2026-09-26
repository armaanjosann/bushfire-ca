"""Treatment geometry generators (project-context.md §4.2).

SPEC-09 implements dispatch, the shared budget / placement / null-treatment
contracts, and the "none" / "random" conditions. SPEC-10 adds "patches",
"strips_perp", "strips_para"; SPEC-11 adds "buffer". Later generators are
registered in _GENERATORS and inherit the contracts from generate(); they
must not re-implement the checks or invent their own tolerance.

Every generator has the signature

    generator(rng, occupied, n_treat, **params) -> bool[L, L]

and is only ever reached through generate(), which has already returned for
n_treat == 0 (before any rng draw — the I6 contract), validated the
condition, and will assert placement (I8) and budget (I7) on the result.
Reserved keys "phi" and "settlement_side" are always present in **params
(DEC-007, DEC-008); a generator that does not use them ignores them.
"""

from math import ceil

import numpy as np

# Every condition the schema knows (project-context.md §4.2), in the order of
# the clustering-scale axis (§11), with buffer off the axis at the end.
CONDITIONS = ("none", "random", "patches", "strips_perp", "strips_para", "buffer")

# Keys SPEC-02's call site always passes alongside a condition's own params.
RESERVED_PARAMS = ("phi", "settlement_side")


# --- shared contracts -------------------------------------------------------


def budget_tolerance(n_treat: int) -> int:
    """Permitted |realised - n_treat| where exact is not achievable:
    max(1, ceil(0.01 * n_treat)) (project-context.md §4.2). The single
    tolerance every generator is held to."""
    return max(1, ceil(0.01 * n_treat))


def check_mask(mask: np.ndarray, occupied: np.ndarray, n_treat: int, condition: str) -> np.ndarray:
    """The placement (I8) and budget (I7) assertions, live in shipped code.

    Returns mask unchanged so a generator can end with
    ``return check_mask(...)``. Raises AssertionError, not ValueError: a
    failure here is a bug in a generator, never bad input.
    """
    if mask.dtype != bool or mask.shape != occupied.shape:
        raise AssertionError(
            f"{condition}: mask must be bool with shape {occupied.shape}, "
            f"got {mask.dtype} {mask.shape}"
        )
    stray = int(np.count_nonzero(mask & ~occupied))
    if stray:
        raise AssertionError(
            f"{condition}: {stray} treated cell(s) are not occupied (I8)"
        )
    realised = int(np.count_nonzero(mask & occupied))
    if abs(realised - n_treat) > budget_tolerance(n_treat):
        raise AssertionError(
            f"{condition}: realised {realised} treated cells, budget {n_treat}, "
            f"tolerance {budget_tolerance(n_treat)} (I7)"
        )
    return mask


# --- generators -------------------------------------------------------------


def _none(rng, occupied, n_treat, **params):
    """all-False. Requires n_treat == 0 — reached only when it is not."""
    raise ValueError(
        f"condition 'none' requires n_treat == 0, got n_treat={n_treat}"
    )


def _random(rng, occupied, n_treat, **params):
    """n_treat occupied cells uniformly without replacement. Exact.
    Clustering scale 1 — the null model of the §11 axis."""
    ys, xs = np.nonzero(occupied)
    idx = rng.choice(ys.size, size=n_treat, replace=False)
    mask = np.zeros(occupied.shape, dtype=bool)
    mask[ys[idx], xs[idx]] = True
    return mask


def _trim_to_budget(mask, occupied, n_treat, rng):
    """Un-treat uniformly chosen excess cells so (mask & occupied).sum()
    == n_treat exactly. The shared last step of every clustered generator
    (§4.2 "randomly un-treat the excess"; DEC-024 for strips)."""
    mask = mask & occupied
    excess = int(np.count_nonzero(mask)) - n_treat
    if excess > 0:
        ys, xs = np.nonzero(mask)
        drop = rng.choice(ys.size, size=excess, replace=False)
        mask[ys[drop], xs[drop]] = False
    return mask


def _positive_int(params, key, default, condition):
    value = params.get(key, default)
    if value is None:
        raise ValueError(f"condition {condition!r} requires parameter {key!r}")
    if not isinstance(value, (int, np.integer)) or isinstance(value, bool) or value < 1:
        raise ValueError(
            f"condition {condition!r}: {key} must be a positive int, got {value!r}"
        )
    return int(value)


# Placement cap for patches: a run needing more blocks than this is a bug
# (or a k larger than the grid), not a slow config. At L=256, k=4, the
# full-budget worst case needs ~4e4 placements.
_MAX_PATCH_PLACEMENTS = 1_000_000


def _patches(rng, occupied, n_treat, **params):
    """k x k blocks at uniformly random top-left positions, overlapping
    allowed, until covered occupied cells >= n_treat; then randomly
    un-treat the excess (§4.2). Clustering scale k.

    Blocks are placed wholly inside the grid (top-left in [0, L-k] on each
    axis), so every block covers exactly k*k cells (DEC-025). Ignores phi
    and settlement_side.
    """
    k = _positive_int(params, "k", 4, "patches")
    L_y, L_x = occupied.shape
    if k > min(L_y, L_x):
        raise ValueError(f"patches: k={k} exceeds the grid {occupied.shape}")

    covered = np.zeros(occupied.shape, dtype=bool)
    count = 0
    placements = 0
    while count < n_treat:
        if placements >= _MAX_PATCH_PLACEMENTS:
            raise RuntimeError(
                f"patches: {placements} placements without reaching n_treat={n_treat}"
            )
        y = int(rng.integers(0, L_y - k + 1))
        x = int(rng.integers(0, L_x - k + 1))
        block = covered[y:y + k, x:x + k]
        occ = occupied[y:y + k, x:x + k]
        count += int(np.count_nonzero(occ & ~block))
        block |= True
        placements += 1

    return _trim_to_budget(covered, occupied, n_treat, rng)


def _band_coordinate(shape, phi, parallel):
    """Per-cell coordinate that indexes the bands: distance along the wind
    for strips_perp (bands run across it), across the wind for strips_para
    (bands run along it). Unit scale, so a band of width w in this
    coordinate is w cells wide measured perpendicular to the band.

    Uses the §3.4 convention: phi = 0 is east (+x), array +y is south, so
    the downwind unit vector in (y, x) is (-sin phi, cos phi) and the
    across-wind one is (cos phi, sin phi).
    """
    ys, xs = np.indices(shape, dtype=np.float64)
    if parallel:
        return xs * np.sin(phi) + ys * np.cos(phi)
    return xs * np.cos(phi) - ys * np.sin(phi)


def _band_mask(t, t_min, w, spacing, phase):
    """Bands of width w every `spacing` along t, the first starting at
    t_min + phase * spacing. Cells inside a band are True."""
    return ((t - t_min - phase * spacing) % spacing) < w


_STRIP_BISECTION_STEPS = 64


def _strips(rng, occupied, n_treat, parallel, **params):
    """Bands of width w, evenly spaced, perpendicular (strips_perp) or
    parallel (strips_para) to phi; spacing found by bisection so the
    occupied-cell count hits n_treat (§4.2, DEC-008). Clustering scale w.

    The band phase offset is one uniform draw per replicate (§4.2). The
    spacing is bounded below by w — touching bands, full coverage — so
    bands never overlap. Bisection lands on the smallest count >= n_treat
    reachable by moving the spacing; the residual (at most one band-edge's
    worth of cells) is trimmed at random. Below one band's worth of budget
    no spacing can hit n_treat, so a single band is placed at a uniform
    random position and thinned at random — the same rule §4.2 gives
    patches for its excess (DEC-024). Ignores settlement_side.
    """
    condition = "strips_para" if parallel else "strips_perp"
    w = _positive_int(params, "w", 4, condition)
    # SPEC-02's call site always passes phi (DEC-008); the default matches
    # Config.phi so a bare generate() call is still constructible (DEC-025).
    phi = float(params.get("phi", 0.0))

    phase = float(rng.random())          # the per-replicate offset, in [0, 1)

    t = _band_coordinate(occupied.shape, phi, parallel)
    t_min = float(t.min())
    extent = float(t.max()) - t_min

    def count(spacing):
        return int(np.count_nonzero(_band_mask(t, t_min, w, spacing, phase) & occupied))

    # Sub-band budget: one full band, fully on the grid, at a uniform random
    # position, thinned to n_treat (DEC-024).
    start = t_min + phase * max(extent - w, 0.0)
    one_band = (t >= start) & (t < start + w)
    if int(np.count_nonzero(one_band & occupied)) >= n_treat:
        return _trim_to_budget(one_band, occupied, n_treat, rng)

    # lo: touching bands, everything treated — always >= n_treat since
    # n_treat <= occupied.sum(). hi: grow until the count drops below the
    # budget; for spacing beyond the grid's extent the single remaining band
    # slides off the grid, so this always terminates.
    lo = float(w)
    hi = extent + w
    grow = 0
    while count(hi) >= n_treat:
        hi *= 2.0
        grow += 1
        if grow > 80:
            raise RuntimeError(
                f"{condition}: no spacing brackets n_treat={n_treat} (w={w}, phi={phi})"
            )

    n_lo = count(lo)
    for _ in range(_STRIP_BISECTION_STEPS):
        if n_lo == n_treat:
            break
        mid = 0.5 * (lo + hi)
        n_mid = count(mid)
        if n_mid >= n_treat:
            lo, n_lo = mid, n_mid
        else:
            hi = mid
    if n_lo < n_treat:
        raise RuntimeError(
            f"{condition}: bisection failed to converge (w={w}, phi={phi}, n_treat={n_treat})"
        )

    return _trim_to_budget(_band_mask(t, t_min, w, lo, phase), occupied, n_treat, rng)


def _strips_perp(rng, occupied, n_treat, **params):
    return _strips(rng, occupied, n_treat, parallel=False, **params)


def _strips_para(rng, occupied, n_treat, **params):
    return _strips(rng, occupied, n_treat, parallel=True, **params)


_GENERATORS = {
    "none": _none,
    "random": _random,
    "patches": _patches,
    "strips_perp": _strips_perp,
    "strips_para": _strips_para,
}

# The nine clustering-scale levels of §6.2 / §10.1 D2, so an experiment grid
# can enumerate them: (condition, geometry_params).
CLUSTERING_LEVELS = tuple(
    [("patches", {"k": k}) for k in (4, 8, 16)]
    + [("strips_perp", {"w": w}) for w in (4, 8, 16)]
    + [("strips_para", {"w": w}) for w in (4, 8, 16)]
)

# Conditions with a live generator. Tests iterate this so SPEC-10 and SPEC-11
# extend coverage by registering, not by editing tests.
IMPLEMENTED = tuple(c for c in CONDITIONS if c in _GENERATORS)


# --- dispatch ---------------------------------------------------------------


def generate(condition: str, rng, occupied: np.ndarray, n_treat: int, **params) -> np.ndarray:
    """Treatment mask for one run (project-context.md §4.2).

    Order matters and is the whole point of this function:

    1. validate the condition string — cheap, no rng, and an unknown
       condition should fail whether or not there is a budget;
    2. n_treat == 0 → all-False, identically for every condition, before
       any generator runs and before rng is touched (I6);
    3. validate n_treat against the occupied count;
    4. dispatch, then assert placement and budget on the result (I8, I7).
    """
    if condition not in CONDITIONS:
        raise ValueError(
            f"unknown condition {condition!r}; valid conditions are "
            + ", ".join(repr(c) for c in CONDITIONS)
        )

    if n_treat == 0:
        return np.zeros(occupied.shape, dtype=bool)

    n_occupied = int(np.count_nonzero(occupied))
    if n_treat < 0 or n_treat > n_occupied:
        raise ValueError(
            f"n_treat must be in [0, {n_occupied}] (the occupied count), "
            f"got {n_treat}"
        )

    generator = _GENERATORS.get(condition)
    if generator is None:
        raise NotImplementedError(
            f"condition {condition!r} is not implemented yet "
            "(patches/strips land in SPEC-10, buffer in SPEC-11)"
        )

    mask = generator(rng, occupied, n_treat, **params)
    return check_mask(mask, occupied, n_treat, condition)
