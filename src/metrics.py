"""Pure summary functions over a finished run (project-context.md §4.3).

Arrays in, numbers out. No I/O, no plotting, no rng, no global state.
Signatures are the SPEC-04 interface contract; later specs are written
against them.

Every scar-shaped quantity here is computed over BURNT cells only, matching
burned_cells in run_fire (SPEC-03 §3.7): a cell still BURNING at truncation
is not part of the scar (DEC-019).
"""

import numpy as np

from src.model import BURNT


def burned_fraction(burned_cells: int, n_cells: int) -> float:
    """burned_cells / n_cells (project-context.md §5)."""
    return burned_cells / n_cells


def burned_fraction_of_fuel(burned_cells: int, n_occupied: int) -> float:
    """burned_cells / n_occupied, or 0.0 when there was no fuel at all —
    a zero-burn run, not a division error (project-context.md §3.5)."""
    if n_occupied == 0:
        return 0.0
    return burned_cells / n_occupied


def reached_edge(state: np.ndarray) -> bool:
    """Did any cell in any of the four edge rows/columns burn
    (project-context.md §3.5, "random_cell" metric)."""
    burnt = state == BURNT
    return bool(
        burnt[0, :].any()
        or burnt[-1, :].any()
        or burnt[:, 0].any()
        or burnt[:, -1].any()
    )


def spanned(state: np.ndarray) -> bool:
    """Did any cell in row L-1 burn (project-context.md §3.5, "edge"
    metric — fire ignited along row 0)."""
    return bool((state[-1, :] == BURNT).any())


def settlement_ring(L: int, side: int) -> np.ndarray:
    """Bool mask of the 1-cell-wide ring immediately surrounding the
    settlement block (project-context.md §3.6).

    The block itself is placed by initial_grids at rows/cols
    [L//2 - side//2, L//2 - side//2 + side); this mirrors that placement so
    the two can never disagree. The ring has 4 * (side + 1) cells and none
    of them is inside the block.
    """
    half = side // 2
    lo = L // 2 - half
    hi = lo + side
    ring = np.zeros((L, L), dtype=bool)
    ring[lo - 1:hi + 1, lo - 1:hi + 1] = True
    ring[lo:hi, lo:hi] = False
    return ring


def scar_second_moments(state: np.ndarray) -> tuple[float, float]:
    """(var_y, var_x) of the BURNT cell coordinates (project-context.md §7
    I4). (0.0, 0.0) for an empty scar."""
    ys, xs = np.nonzero(state == BURNT)
    if ys.size == 0:
        return 0.0, 0.0
    return float(np.var(ys)), float(np.var(xs))


def scar_centroid(state: np.ndarray) -> tuple[float, float]:
    """(y, x) mean of the BURNT cell coordinates (project-context.md §7 I5).
    (nan, nan) for an empty scar — there is no centre to report."""
    ys, xs = np.nonzero(state == BURNT)
    if ys.size == 0:
        return float("nan"), float("nan")
    return float(ys.mean()), float(xs.mean())


def centroid_projection(centroid, origin, phi: float) -> float:
    """Displacement of centroid from origin projected onto the downwind
    direction phi, in cells (project-context.md §7 I5).

    Both points are (y, x) in array coordinates. The wind kernel (§3.4,
    wind_weights) measures direction as theta = arctan2(-dy, dx), so the
    downwind unit vector in (y, x) is (-sin phi, cos phi): phi = 0 blows
    towards +x, phi = -pi/2 towards +y (row 0 -> row L-1, the §6.1 edge-
    ignition convention).
    """
    cy, cx = centroid
    oy, ox = origin
    return float((cy - oy) * (-np.sin(phi)) + (cx - ox) * np.cos(phi))
