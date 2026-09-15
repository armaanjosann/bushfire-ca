"""Treatment geometry generators (project-context.md §4.2).

SPEC-09 implements dispatch and the "none"/"random" conditions; SPEC-10 adds
"patches"/"strips_perp"/"strips_para"; SPEC-11 adds "buffer".
"""

import numpy as np


def generate(condition: str, rng, occupied: np.ndarray, n_treat: int, **params) -> np.ndarray:
    """Stub. SPEC-09 implements dispatch; SPEC-10 and SPEC-11 add conditions."""
    if n_treat == 0:
        return np.zeros(occupied.shape, dtype=bool)   # the I6 contract: no rng draw
    raise NotImplementedError("treatment geometries land in SPEC-09")
