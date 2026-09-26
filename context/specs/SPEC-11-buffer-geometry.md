---
id: SPEC-11
title: Buffer geometry
status: in review
owner: Armaan
reviewer: Aaron
phase: P3 — Treatment geometries (Sprint 2)
depends_on: [SPEC-02, SPEC-09]
implements: [§4.2, §3.6]
issue: "#11"
branch: spec/SPEC-11-buffer-geometry
pr:
decisions: [DEC-007, DEC-026]
---

# SPEC-11 — `buffer`

## Objective

The targeted asset-protection condition exists: concentric rings grown outward from the settlement block until the budget is met, with the final partial ring filled at random.

## Context to read

- `workflow-rules.md`
- `project-context.md` §4.2 (the `buffer` row), §3.6 (settlement, and the instruction not to exclude ignition regions), §4.4 (`buffer` requires `settlement=True`), §11
- `checkpoint1-bushfire-ca-roadmap.md` §2 SQ4 — what this condition is for

## Scope

**In scope**

- `"buffer"`: grow concentric rings outward from the settlement block, one cell of thickness at a time, until covered occupied cells ≥ `n_treat`; fill the final partial ring at random.
- Registering it as a condition.

**Out of scope**

- The other five conditions — SPEC-09, SPEC-10.
- Placing the settlement — SPEC-02.
- Deciding `SETTLEMENT_SIDE` — §10.2 O1, SPEC-12.
- The shared budget, placement and null-treatment helpers — SPEC-09's.

## Files

**May touch**

- `src/geometries.py`
- `tests/test_geometries.py`

**Must not touch**

- `src/model.py`, `src/metrics.py`, `src/experiments.py`, `src/analysis.py`, `figures/`
- `tests/test_invariants.py`

## Interface contract

As `project-context.md` §4.2 — do not redesign; do not add a parameter to the signature. `buffer` takes no condition-specific parameters. It locates the settlement block as the square of side `params["settlement_side"]` centred at `(L//2, L//2)` (§3.6). SPEC-02's call site always supplies `settlement_side`: `cfg.geometry_params["settlement_side"]` if set, else `SETTLEMENT_SIDE` (DEC-007). Do not import `SETTLEMENT_SIDE` into the generator or infer the block from `occupied`, because the side varies per config in SPEC-12's pilot. `buffer` ignores `phi`.

## Behaviour

- Rings grow outward from the settlement block by Chebyshev distance, one cell of thickness at a time.
- Only occupied cells count toward the budget; the ring may cross `EMPTY` cells, which are skipped, not treated (§4.2, I8).
- Growth stops at the first ring whose inclusion reaches or exceeds `n_treat`; that final ring is then filled at random to land on the budget.
- Rings that run off the lattice edge are truncated, not wrapped — boundaries are non-periodic (§3.1).
- Requires `settlement=True`; §4.4 already raises on the config, so this generator may assume a settlement exists but should assert it rather than produce a mask around nothing.
- The early return on `n_treat == 0`, before touching `rng` (I6).

## Acceptance criteria

- [x] The mask is a contiguous annulus around the settlement block, except for the randomly filled outermost ring.
- [x] No treated cell is inside the settlement block.
- [x] No treated cell is unoccupied (I8).
- [x] Budget met within the shared tolerance over ≥50 seeds at `b ∈ {0.05, 0.15, 0.30}` and `p ∈ {0.4, 0.55, 0.7}`.
- [x] At a budget large enough that rings reach the lattice edge, the generator truncates and still meets the budget, or raises a clear error if the budget is unachievable.
- [x] `n_treat == 0` returns all-False without touching `rng`.
- [x] With `settlement_side=32` in params, rings grow from the 32-side block, not the default (DEC-007).
- [x] Constructing a `buffer` config with `settlement=False` raises at `Config` construction (§4.4), not here.

## Invariants

- [x] None owned. I6, I7 and I8 must continue to pass with `buffer` in the condition set.

## Verification

```bash
pytest -q tests/test_geometries.py -k buffer
pytest -q tests/test_invariants.py -k "i6 or i7 or i8"
python - <<'PY'
import numpy as np
from src.model import Config, initial_grids, SETTLEMENT_SIDE
from src.geometries import generate
cfg = Config(L=256, p=0.55, settlement=True, condition="buffer", b=0.15, seed=0)
s,f = initial_grids(cfg, np.random.default_rng(0))
occ = (s == 1)
n = int(round(0.15*occ.sum()))
m = generate("buffer", np.random.default_rng(1), occ, n, phi=0.0, settlement_side=SETTLEMENT_SIDE)
print("treated", int((m&occ).sum()), "target", n, "outside-occupied", int((m&~occ).sum()))
PY
```

## Definition of done

- [x] Acceptance criteria all met
- [x] Named invariants pass locally
- [x] Every deviation logged in `decisions-log.md`, IDs listed in `decisions:` above
- [x] Any contract change applied to `project-context.md` in this same PR
- [ ] `status` updated in this file and in `progress-tracker.md`
- [ ] PR open, linked to the issue — status `in review`
- [ ] Reviewed by `reviewer` and merged — status `done` (human only)

## Notes and risks

- **Do not exclude ignition regions.** Ignition under `"random_cell"` may land inside the buffer ring, and that is correct: excluding it would bias the comparison in favour of buffer geometries (§3.6), which is exactly the result SQ4 is trying to test honestly.
- `buffer` sits **off** the clustering-scale axis (§4.2, §11). It is the targeted condition, not a point on the curve, and the report should not plot it as one.
- This is the SQ4 condition and the project's insurance against a boring result (roadmap §11). It is last in the descope order among the geometries, but it is not free — budget a real day.
- `SETTLEMENT_SIDE` is still provisional while this is implemented. Write the generator so that changing it in SPEC-12 requires no change here: it reads the side from `params` (DEC-007).
