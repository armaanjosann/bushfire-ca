"""Core model contracts: Config, RunResult, wind_weights.

The step function and run_fire land in SPEC-03.
"""

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
