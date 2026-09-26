---
id: SPEC-02
title: Lattice initialisation, ignition, settlement
status: in review
owner: Aaron
reviewer: Armaan
phase: P0 — Foundation (Sprint 1)
depends_on: [SPEC-01]
implements: [§3.1, §3.2, §3.5, §3.6, §4.1]
issue:
branch: spec/SPEC-02-initialisation
pr:
decisions: [DEC-007, DEC-008]
---

# SPEC-02 — Lattice initialisation, ignition, settlement

## Objective

`initial_grids(cfg, rng)` returns a valid `(state, f)` pair for either regime, with the settlement placed, occupancy drawn, treatment applied and the ignition set alight — ready for a step function that does not exist yet.

## Context to read

- `workflow-rules.md`
- `project-context.md` §3.1 (lattice and state codes), §3.2 (initialisation order), §3.5 (ignition modes), §3.6 (settlement), §4.1 (`initial_grids` signature), §4.2 (the `generate` contract this calls into), §2 O1/O2/O5

## Scope

**In scope**

- `initial_grids(cfg, rng) -> tuple[np.ndarray, np.ndarray]` returning `(state, f)`.
- Settlement placement: a filled square of side `side` centred at `(L//2, L//2)`, state `SETTLEMENT`, `f = 0`, where `side = cfg.geometry_params.get("settlement_side", SETTLEMENT_SIDE)` (DEC-007).
- Occupancy draw at probability `p` over non-settlement cells.
- Computing `n_treat = round(b * occupied.sum())` and calling `geometries.generate` with it, passing `phi` and the resolved `settlement_side` in `**params` (see Behaviour; DEC-007, DEC-008).
- Applying the returned mask to `f` only.
- Both ignition modes of §3.5, and returning the ignition coordinates for `random_cell`.
- `SETTLEMENT_SIDE` as a module constant in `src/model.py`, marked provisional.

**Out of scope**

- Any treatment geometry other than the `n_treat == 0` path — SPEC-09, SPEC-10, SPEC-11 fill in `generate`.
- Stepping the fire, `burn_clock`, truncation — SPEC-03.
- Deciding the value of `SETTLEMENT_SIDE` — that is §10.2 O1, owned by SPEC-12. **Do not resolve it here** (`workflow-rules.md` §7).
- Recording `ignition_y` / `ignition_x` into a results row — SPEC-05 does the row.

## Files

**May touch**

- `src/model.py`
- `tests/test_model.py`, `tests/test_initialisation.py`

**Must not touch**

- `src/geometries.py` — the stub is SPEC-01's, the implementation is SPEC-09's
- `src/experiments.py`, `src/analysis.py`, `src/metrics.py`, `figures/`
- `context/project-context.md` unless a contract genuinely changes (then §5 of `workflow-rules.md` applies)

## Interface contract

As `project-context.md` §4.1 — do not redesign:

```python
def initial_grids(cfg: Config, rng) -> tuple[np.ndarray, np.ndarray]: ...  # (state, f)
```

`state` is `int8` using the §3.1 codes. `f` is `float64`. The ignition coordinates are needed by the results row but `initial_grids` returns only the two grids per §4.1; hold them on the caller side in SPEC-03 by having `run_fire` locate the single `BURNING` cell after initialisation, or raise a DEC if that proves unworkable rather than widening the signature.

## Behaviour

**The ordering in §3.2 is the whole spec** and is not negotiable:

1. Place the settlement, if `cfg.settlement`.
2. Draw occupancy: each non-settlement cell independently `FUEL` with probability `p`, else `EMPTY`.
3. Apply the treatment mask: masked occupied cells get `f = f_treat`.
4. Ignite.

**The `generate` call site** (DEC-007, DEC-008) is `generate(cfg.condition, rng, occupied, n_treat, **{**cfg.geometry_params, "phi": cfg.phi, "settlement_side": side})`. `cfg.phi` is the only source of wind direction: if `cfg.geometry_params` contains a `"phi"` key, raise rather than let either value silently win. Generators that do not use `phi` or `settlement_side` ignore them (SPEC-09).

Occupancy is drawn **before** treatment because the generator must see realised occupancy to hit an exact budget in occupied cells (§2 O1, O2). `b` is a fraction of **occupied** cells, never of the lattice.

- Treatment changes `f` only. It never changes `state` (§3.2 step 3).
- `EMPTY` and `SETTLEMENT` cells have `f = 0.0`; occupied untreated `f = 1.0`; occupied treated `f = f_treat`.
- `"edge"`: every `FUEL` cell in row 0 becomes `BURNING` at `t = 0`.
- `"random_cell"`: one `FUEL` cell uniformly at random. Settlement-adjacent cells are eligible; `EMPTY` cells are not. **Do not exclude any region** — excluding buffer interiors would bias the comparison toward buffer geometries (§3.6).
- If no `FUEL` cell exists, initialise with nothing burning and let SPEC-03 return a zero-burn run. Do not raise (§3.5).

## Acceptance criteria

- [x] `state` and `f` are consistent: every `EMPTY`/`SETTLEMENT` cell has `f == 0`; every `FUEL` cell has `f` in `{1.0, f_treat}`.
- [x] Settlement block is exactly `side²` cells, centred, all state `SETTLEMENT`, and no occupancy draw touched it. Tested both with `geometry_params` lacking `settlement_side` (`side == SETTLEMENT_SIDE`) and with an explicit `settlement_side` (e.g. 32).
- [x] `generate` receives `phi == cfg.phi` and `settlement_side == side` in its params (checked with a stub/spy), and a `"phi"` key inside `geometry_params` raises.
- [x] With `settlement=False`, no cell is in state `SETTLEMENT`.
- [x] `n_occupied` is within sampling error of `p * (L² − settlement area)` over ≥100 seeds.
- [x] At `b = 0`, `f` contains only `0.0` and `1.0`, for every condition.
- [x] `"edge"` leaves every `FUEL` cell of row 0 `BURNING` and nothing else burning.
- [x] `"random_cell"` leaves exactly one cell `BURNING`, and it was `FUEL`.
- [x] `p = 0` with `"random_cell"` returns grids with nothing burning, and raises nothing.
- [x] Same `cfg` and same seed ⟹ identical `(state, f)`.

## Invariants

- [x] None owned outright. This spec must not break I6 — call `generate` with `n_treat` and let it return early; do not draw from `rng` on the treatment path yourself when `b == 0`.

## Verification

```bash
pytest -q tests/test_initialisation.py
python - <<'PY'
from src.model import Config, initial_grids
import numpy as np
for ig in ("edge","random_cell"):
    cfg = Config(L=64, p=0.5, ignition=ig, settlement=(ig=="random_cell"), seed=1)
    s,f = initial_grids(cfg, np.random.default_rng(cfg.seed))
    print(ig, np.bincount(s.ravel()+0, minlength=5), sorted(set(f.ravel().tolist()))[:4])
PY
```

## Definition of done

- [x] Acceptance criteria all met
- [x] Named invariants pass locally
- [x] Every deviation logged in `decisions-log.md`, IDs listed in `decisions:` above
- [x] Any contract change applied to `project-context.md` in this same PR (none needed — no contract changed)
- [x] `status` updated in this file and in `progress-tracker.md`
- [ ] PR open, linked to the issue — status `in review`
- [ ] Reviewed by `reviewer` and merged — status `done` (human only)

## Notes and risks

- The settlement side is read from `geometry_params["settlement_side"]` when present (DEC-007), so SPEC-12's pilot can vary it per config without touching this code. `phi` reaches the generators through the call site above (DEC-008).
- **`SETTLEMENT_SIDE = 16` is provisional.** Mark the constant with a comment pointing at §10.2 O1 and SPEC-12. Resolving it here is a `workflow-rules.md` §7 violation.
- Drawing occupancy over the settlement block and then overwriting it changes the rng stream relative to masking it out first. Pick one, state it in the docstring, and keep it stable — I2 and I6 both depend on a stable stream.
- This spec calls an interface that SPEC-09 has not implemented. That is deliberate. If the §4.2 signature does not fit what you need here, **stop and raise a DEC** rather than changing it — SPEC-09 through SPEC-11 are being written against it in parallel.
