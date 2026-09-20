"""Core model contracts: Config, RunResult, wind_weights, run_fire."""

from dataclasses import dataclass, field

import numpy as np

from src import geometries

# Neighbour offsets, (dy, dx). Fixed order — weights in wind_weights() are
# indexed by this order and it must never be re-sorted (project-context.md §3.4).
NEIGHBOURS = [(-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1)]

DIAGONAL_FACTOR = 1.0 / np.sqrt(2.0)

# Validation target only — never a grid value or a substitute for a measured p_c.
P_C_LITERATURE = 0.407

# Cell state codes, int8 (project-context.md §3.1).
EMPTY = 0
FUEL = 1
BURNING = 2
BURNT = 3
SETTLEMENT = 4

# Provisional. Bound by the pilot in project-context.md §10.2 O1, owned by
# SPEC-12. Do not resolve it here (workflow-rules.md §7) — this is only the
# default used when geometry_params lacks an explicit "settlement_side".
SETTLEMENT_SIDE = 16


@dataclass(frozen=True)
class Config:
    # lattice
    L: int = 256
    # regime
    regime: str = "STUDY"              # "STUDY" | "PERCOLATION"
    # fuel
    p: float = 0.45                    # occupancy probability
    f_treat: float = 0.2
    # rule
    beta: float = 0.8
    kappa: float = 0.0
    phi: float = 0.0
    tau: int = 1
    diagonal_factor: bool = True
    # treatment
    condition: str = "none"            # see §4.2
    b: float = 0.0                     # fraction of OCCUPIED cells treated
    geometry_params: dict = field(default_factory=dict)
    # setup
    ignition: str = "random_cell"      # "random_cell" | "edge"
    settlement: bool = False
    max_steps: int | None = None       # default 8 * L, resolved in run_fire
    # reproducibility
    seed: int = 0

    def __post_init__(self):
        if self.regime == "PERCOLATION":
            if self.beta != 1.0:
                raise ValueError(
                    "PERCOLATION regime requires beta == 1.0, got "
                    f"beta={self.beta!r}"
                )
            if self.kappa != 0.0:
                raise ValueError(
                    "PERCOLATION regime requires kappa == 0.0, got "
                    f"kappa={self.kappa!r}"
                )
            if self.diagonal_factor is True:
                raise ValueError(
                    "PERCOLATION regime requires diagonal_factor == False, got "
                    f"diagonal_factor={self.diagonal_factor!r}"
                )
            if self.tau != 1:
                raise ValueError(
                    f"PERCOLATION regime requires tau == 1, got tau={self.tau!r}"
                )
            if self.b != 0:
                raise ValueError(
                    f"PERCOLATION regime requires b == 0, got b={self.b!r}"
                )
            if self.ignition != "edge":
                raise ValueError(
                    "PERCOLATION regime requires ignition == 'edge', got "
                    f"ignition={self.ignition!r}"
                )

        if self.condition == "buffer" and self.settlement is False:
            raise ValueError(
                "condition == 'buffer' requires settlement == True, got "
                f"settlement={self.settlement!r}"
            )

        if self.condition == "none" and self.b != 0:
            raise ValueError(
                f"condition == 'none' requires b == 0, got b={self.b!r}"
            )

        if self.b < 0 or self.b > 1:
            raise ValueError(f"b must be in [0, 1], got b={self.b!r}")

        if self.p < 0 or self.p > 1:
            raise ValueError(f"p must be in [0, 1], got p={self.p!r}")

        if self.tau < 1:
            raise ValueError(f"tau must be >= 1, got tau={self.tau!r}")

        if self.L < 32:
            raise ValueError(f"L must be >= 32, got L={self.L!r}")


def wind_weights(kappa: float, phi: float, diagonal_factor: bool) -> np.ndarray:
    """Von Mises wind kernel weights, shape (8,), indexed by NEIGHBOURS order.

    Normalised so the mean over the eight directions is 1 (not sum 1) — see
    project-context.md §3.4 on why sum-1 would confound kappa with beta.
    """
    dy = np.array([d[0] for d in NEIGHBOURS], dtype=np.float64)
    dx = np.array([d[1] for d in NEIGHBOURS], dtype=np.float64)
    theta = np.arctan2(-dy, dx)

    raw = np.exp(kappa * np.cos(theta - phi))
    if diagonal_factor:
        is_diagonal = (dy != 0) & (dx != 0)
        raw = np.where(is_diagonal, raw * DIAGONAL_FACTOR, raw)

    return raw / raw.mean()


def initial_grids(cfg: Config, rng) -> tuple[np.ndarray, np.ndarray]:
    """Build the initial (state, f) grids per project-context.md §3.2.

    Rng-stream note (SPEC-02 notes and risks): occupancy is drawn with a
    single rng.random((L, L)) call over the *whole* lattice, and the
    settlement footprint (if any) is carved out and overwritten to
    SETTLEMENT/f=0 afterwards, rather than drawing only over non-settlement
    cells. This keeps the shape of the occupancy draw — and so the rng
    stream it consumes — independent of whether a settlement is present or
    how large it is, which I2 (determinism) and I6 (null treatment) both
    depend on.
    """
    L = cfg.L
    side = cfg.geometry_params.get("settlement_side", SETTLEMENT_SIDE)

    settlement_mask = np.zeros((L, L), dtype=bool)
    if cfg.settlement:
        half = side // 2
        centre = L // 2
        lo = centre - half
        hi = lo + side
        settlement_mask[lo:hi, lo:hi] = True

    occupied_draw = rng.random((L, L)) < cfg.p
    state = np.where(occupied_draw, FUEL, EMPTY).astype(np.int8)
    f = np.where(occupied_draw, 1.0, 0.0)

    state[settlement_mask] = SETTLEMENT
    f[settlement_mask] = 0.0

    occupied = state == FUEL

    if "phi" in cfg.geometry_params:
        raise ValueError(
            "geometry_params must not contain 'phi'; cfg.phi is the single "
            "source of wind direction (project-context.md §4.2, DEC-008)"
        )

    n_treat = round(cfg.b * occupied.sum())
    params = {**cfg.geometry_params, "phi": cfg.phi, "settlement_side": side}
    mask = geometries.generate(cfg.condition, rng, occupied, n_treat, **params)
    f[mask] = cfg.f_treat

    if cfg.ignition == "edge":
        row0 = state[0]
        state[0] = np.where(row0 == FUEL, BURNING, row0)
    elif cfg.ignition == "random_cell":
        fuel_ys, fuel_xs = np.nonzero(state == FUEL)
        if fuel_ys.size > 0:
            idx = rng.integers(fuel_ys.size)
            state[fuel_ys[idx], fuel_xs[idx]] = BURNING
    else:
        raise ValueError(f"unknown ignition mode: {cfg.ignition!r}")

    return state, f


@dataclass
class RunResult:
    """§5 schema fields minus the config echo (SPEC-03 Interface contract).

    Raw fields are always populated by run_fire (DEC-006). Derived fields
    default to None here and are filled in by SPEC-04's metrics.py.
    """

    n_cells: int
    n_occupied: int
    n_treated: int
    ignition_y: int | None
    ignition_x: int | None
    burned_cells: int
    still_burning_cells: int
    steps: int
    truncated: bool
    burned_fraction: float | None = None
    burned_fraction_of_fuel: float | None = None
    spanned: bool | None = None
    reached_edge: bool | None = None
    settlement_reached: bool | None = None
    settlement_reached_step: int | None = None
    scar: np.ndarray | None = None
    ignition_step: np.ndarray | None = None


def _pad_bbox(y_min, y_max, x_min, x_max, L):
    """Tight box around (y_min..y_max, x_min..x_max), padded 1 cell, clipped
    to the grid (project-context.md §8) — the clip is what makes the
    absorbing boundary fall out for free instead of needing explicit wrap
    handling."""
    y0 = max(0, int(y_min) - 1)
    y1 = min(L, int(y_max) + 2)
    x0 = max(0, int(x_min) - 1)
    x1 = min(L, int(x_max) + 2)
    return y0, y1, x0, x1


def _bounding_box(burning_mask, L):
    """Padded bounding box of a boolean mask, or None if it is empty."""
    ys, xs = np.nonzero(burning_mask)
    if ys.size == 0:
        return None
    return _pad_bbox(ys.min(), ys.max(), xs.min(), xs.max(), L)


def _shifted(mask, dy, dx):
    """mask shifted so out[y, x] = mask[y - dy, x - dx]; cells shifted in
    from outside the array read as False — the non-periodic, absorbing
    boundary (project-context.md §3.1), not a wraparound."""
    h, w = mask.shape
    out = np.zeros_like(mask)
    sy0, sy1 = max(0, -dy), h - max(0, dy)
    sx0, sx1 = max(0, -dx), w - max(0, dx)
    dy0, dy1 = max(0, dy), h - max(0, -dy)
    dx0, dx1 = max(0, dx), w - max(0, -dx)
    out[dy0:dy1, dx0:dx1] = mask[sy0:sy1, sx0:sx1]
    return out


def run_fire(cfg: Config, capture_scar: bool = False) -> RunResult:
    """Run one fire to extinction (project-context.md §3.3, §3.7, §8).

    Pure in cfg: builds its own generator from cfg.seed and never accepts an
    external rng, which is what makes two calls on the same Config produce
    an identical RunResult (I2). The Bernoulli draw is one rng.random((L, L))
    call per step — the full grid, matching §3.3/§8's "over the whole grid"
    — so the bounding-box restriction below (which only scopes the shifted-
    mask arithmetic, the expensive part) doesn't change the rng stream and
    a step-for-step full-grid implementation reaches the same result.
    """
    rng = np.random.default_rng(cfg.seed)
    L = cfg.L
    max_steps = cfg.max_steps if cfg.max_steps is not None else 8 * L

    state, f = initial_grids(cfg, rng)

    occupied = (state == FUEL) | (state == BURNING)
    n_occupied = int(occupied.sum())
    n_treated = (
        int(np.count_nonzero(occupied & (f == cfg.f_treat))) if cfg.b > 0 else 0
    )

    ignition_y = ignition_x = None
    if cfg.ignition == "random_cell":
        ys, xs = np.nonzero(state == BURNING)
        if ys.size > 0:
            ignition_y, ignition_x = int(ys[0]), int(xs[0])

    burn_clock = np.zeros((L, L), dtype=np.uint8)

    ignition_step = None
    if capture_scar:
        ignition_step = np.full((L, L), -1, dtype=np.int32)
        ignition_step[state == BURNING] = 0

    weights = wind_weights(cfg.kappa, cfg.phi, cfg.diagonal_factor)

    bbox = _bounding_box(state == BURNING, L)
    step_number = 0
    truncated = False

    while bbox is not None:
        if step_number >= max_steps:
            truncated = True
            break
        step_number += 1

        draws = rng.random((L, L))

        y0, y1, x0, x1 = bbox
        sub_state = state[y0:y1, x0:x1]
        sub_f = f[y0:y1, x0:x1]
        sub_burn_clock = burn_clock[y0:y1, x0:x1]
        sub_draws = draws[y0:y1, x0:x1]

        sub_burning = sub_state == BURNING
        fuel_mask = sub_state == FUEL

        no_ignite_prob = np.ones(sub_state.shape, dtype=np.float64)
        for i, (dy, dx) in enumerate(NEIGHBOURS):
            shifted_burning = _shifted(sub_burning, dy, dx)
            p_d = np.clip(cfg.beta * weights[i] * sub_f, 0.0, 1.0)
            no_ignite_prob *= np.where(shifted_burning, 1.0 - p_d, 1.0)

        p_ignite = np.where(fuel_mask, 1.0 - no_ignite_prob, 0.0)
        ignite_mask = fuel_mask & (sub_draws < p_ignite)

        sub_burn_clock[sub_burning] += 1
        newly_burnt = sub_burning & (sub_burn_clock >= cfg.tau)
        sub_state[newly_burnt] = BURNT
        sub_state[ignite_mask] = BURNING

        if capture_scar:
            ignition_step[y0:y1, x0:x1][ignite_mask] = step_number

        new_y, new_x = np.nonzero(sub_state == BURNING)
        if new_y.size == 0:
            bbox = None
        else:
            bbox = _pad_bbox(
                new_y.min() + y0, new_y.max() + y0,
                new_x.min() + x0, new_x.max() + x0,
                L,
            )

    burned_cells = int(np.count_nonzero(state == BURNT))
    still_burning_cells = int(np.count_nonzero(state == BURNING))

    return RunResult(
        n_cells=L * L,
        n_occupied=n_occupied,
        n_treated=n_treated,
        ignition_y=ignition_y,
        ignition_x=ignition_x,
        burned_cells=burned_cells,
        still_burning_cells=still_burning_cells,
        steps=step_number,
        truncated=truncated,
        scar=state.copy() if capture_scar else None,
        ignition_step=ignition_step if capture_scar else None,
    )
