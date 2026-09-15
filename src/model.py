"""Core model contracts: Config, RunResult, wind_weights.

The step function, run_fire and initial_grids land in SPEC-02 and SPEC-03.
"""

from dataclasses import dataclass, field

import numpy as np

# Neighbour offsets, (dy, dx). Fixed order — weights in wind_weights() are
# indexed by this order and it must never be re-sorted (project-context.md §3.4).
NEIGHBOURS = [(-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1)]

DIAGONAL_FACTOR = 1.0 / np.sqrt(2.0)

# Validation target only — never a grid value or a substitute for a measured p_c.
P_C_LITERATURE = 0.407


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
