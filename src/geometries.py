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


_GENERATORS = {
    "none": _none,
    "random": _random,
}

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
