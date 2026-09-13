"""
Bushfire spread cellular automaton (stochastic 2D CA, Moore neighbourhood).

Minimal implementation of the model in checkpoint1-bushfire-ca-roadmap.md §4.

States:  EMPTY=0  FUEL=1  BURNING=2  BURNT=3
Rule:    a burning cell i tries to ignite each neighbour j with
             P(i -> j) = clip(beta * w(theta_ij) * f_j, 0, 1)
         and j ignites if any of its burning neighbours succeeds.
         With beta=1, kappa=0, f=1 this is exactly site percolation.
"""
import numpy as np

EMPTY, FUEL, BURNING, BURNT = 0, 1, 2, 3

# The 8 Moore offsets (dy, dx). A burning cell at (y, x) can ignite (y+dy, x+dx).
OFFSETS = [(dy, dx) for dy in (-1, 0, 1) for dx in (-1, 0, 1) if (dy, dx) != (0, 0)]


def wind_kernel(kappa=0.0, phi=0.0):
    """von Mises weight for each of the 8 spread directions, normalised so the
    mean over directions is 1. phi is the wind direction in radians, 0 = east
    (+x), angles measured anticlockwise with north = +y (i.e. -dy)."""
    thetas = np.array([np.arctan2(-dy, dx) for dy, dx in OFFSETS])
    w = np.exp(kappa * np.cos(thetas - phi))
    return w / w.mean()


def _shift(a, dy, dx):
    """Return b with b[y+dy, x+dx] = a[y, x]; cells shifted in from outside are 0
    (absorbing boundaries)."""
    L = a.shape[0]
    out = np.zeros_like(a)
    ys, yd = (slice(0, L - dy), slice(dy, L)) if dy >= 0 else (slice(-dy, L), slice(0, L + dy))
    xs, xd = (slice(0, L - dx), slice(dx, L)) if dx >= 0 else (slice(-dx, L), slice(0, L + dx))
    out[yd, xd] = a[ys, xs]
    return out


def make_landscape(L, p, rng, fuel_mask=None, f_treat=0.2):
    """Random landscape: each cell holds fuel with prob p. Returns (state, fuel_load).
    fuel_mask (bool LxL) marks treated cells whose load is reduced to f_treat."""
    state = np.where(rng.random((L, L)) < p, FUEL, EMPTY).astype(np.uint8)
    f = (state == FUEL).astype(float)
    if fuel_mask is not None:
        f[fuel_mask & (state == FUEL)] = f_treat
    return state, f


def ignite(state, rng, where="random"):
    """Set the ignition. 'random' = one random FUEL cell, 'centre' = middle cell,
    'left_edge' = every FUEL cell in column 0 (standard percolation spanning test)."""
    L = state.shape[0]
    if where == "left_edge":
        col = state[:, 0] == FUEL
        state[col, 0] = BURNING
    elif where == "centre":
        state[L // 2, L // 2] = BURNING
    else:
        ys, xs = np.nonzero(state == FUEL)
        if len(ys) == 0:
            return state
        k = rng.integers(len(ys))
        state[ys[k], xs[k]] = BURNING
    return state


def step(state, f, rng, beta=1.0, weights=None, tau=1, age=None):
    """One synchronous update. Returns (new_state, new_age)."""
    if weights is None:
        weights = np.ones(8)
    burning = (state == BURNING).astype(float)
    if not burning.any():
        return state, age
    no_ignite = np.ones_like(f)
    for (dy, dx), w in zip(OFFSETS, weights):
        p_ij = np.clip(beta * w * f, 0.0, 1.0)      # target-cell fuel load f_j
        no_ignite *= 1.0 - _shift(burning, dy, dx) * p_ij
    p_ignite = 1.0 - no_ignite
    new = state.copy()
    catches = (state == FUEL) & (rng.random(state.shape) < p_ignite)
    # burn duration
    if age is None:
        age = np.zeros(state.shape, dtype=np.int32)
    age = age + (state == BURNING)
    new[(state == BURNING) & (age >= tau)] = BURNT
    new[catches] = BURNING
    return new, age


def run_fire(L=128, p=0.5, beta=1.0, kappa=0.0, phi=0.0, tau=1, seed=0,
             ignition="random", fuel_mask=None, f_treat=0.2, record=False):
    """Run one fire to extinction. Returns a dict of metrics (and frames if record)."""
    rng = np.random.default_rng(seed)
    state, f = make_landscape(L, p, rng, fuel_mask, f_treat)
    initial_fuel = (state == FUEL).sum()
    state = ignite(state, rng, ignition)
    weights = wind_kernel(kappa, phi)
    frames = [state.copy()] if record else None
    age = None
    steps = 0
    while (state == BURNING).any():
        state, age = step(state, f, rng, beta, weights, tau, age)
        steps += 1
        if record:
            frames.append(state.copy())
    burnt = state == BURNT
    out = dict(
        burned_frac=burnt.sum() / (L * L),
        burned_of_fuel=burnt.sum() / max(initial_fuel, 1),
        steps=steps,
        span_lr=bool(burnt[:, 0].any() and burnt[:, -1].any()),
        span_tb=bool(burnt[0, :].any() and burnt[-1, :].any()),
        seed=seed,
    )
    out["span"] = out["span_lr"] or out["span_tb"]
    if record:
        out["frames"] = frames
    return out


if __name__ == "__main__":
    r = run_fire(L=64, p=0.5, seed=1, ignition="centre")
    print({k: v for k, v in r.items() if k != "frames"})
