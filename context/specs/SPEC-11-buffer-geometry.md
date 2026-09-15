---
id: SPEC-11
title: Buffer geometry
status: not started
owner: Armaan
reviewer: Aaron
phase: P3 — Treatment geometries (Sprint 2)
depends_on: [SPEC-02, SPEC-09]
implements: [§4.2, §3.6]
issue:
branch: spec/SPEC-11-buffer-geometry
pr:
decisions: []
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

As `project-context.md` §4.2 — do not redesign. `buffer` takes no geometry parameters; it needs to know where the settlement is, which it derives from the grid rather than from a new argument. If that is not derivable from `occupied` alone, **raise a DEC** rather than adding a parameter to the §4.2 signature — SPEC-02, SPEC-09 and SPEC-10 are all written against it.

## Behaviour

- Rings grow outward from the settlement block by Chebyshev distance, one cell of thickness at a time.
- Only occupied cells count toward the budget; the ring may cross `EMPTY` cells, which are skipped, not treated (§4.2, I8).
- Growth stops at the first ring whose inclusion reaches or exceeds `n_treat`; that final ring is then filled at random to land on the budget.
- Rings that run off the lattice edge are truncated, not wrapped — boundaries are non-periodic (§3.1).
- Requires `settlement=True`; §4.4 already raises on the config, so this generator may assume a settlement exists but should assert it rather than produce a mask around nothing.
- The early return on `n_treat == 0`, before touching `rng` (I6).

## Acceptance criteria

- [ ] The mask is a contiguous annulus around the settlement block, except for the randomly filled outermost ring.
- [ ] No treated cell is inside the settlement block.
- [ ] No treated cell is unoccupied (I8).
- [ ] Budget met within the shared tolerance over ≥50 seeds at `b ∈ {0.05, 0.15, 0.30}` and `p ∈ {0.4, 0.55, 0.7}`.
- [ ] At a budget large enough that rings reach the lattice edge, the generator truncates and still meets the budget, or raises a clear error if the budget is unachievable.
- [ ] `n_treat == 0` returns all-False without touching `rng`.
- [ ] Constructing a `buffer` config with `settlement=False` raises at `Config` construction (§4.4), not here.

## Invariants

- [ ] None owned. I6, I7 and I8 must continue to pass with `buffer` in the condition set.

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
m = generate("buffer", np.random.default_rng(1), occ, n)
print("treated", int((m&occ).sum()), "target", n, "outside-occupied", int((m&~occ).sum()))
PY
```

## Definition of done

- [ ] Acceptance criteria all met
- [ ] Named invariants pass locally
- [ ] Every deviation logged in `decisions-log.md`, IDs listed in `decisions:` above
- [ ] Any contract change applied to `project-context.md` in this same PR
- [ ] `status` updated in this file and in `progress-tracker.md`
- [ ] PR open, linked to the issue — status `in review`
- [ ] Reviewed by `reviewer` and merged — status `done` (human only)

## Notes and risks

- **Do not exclude ignition regions.** Ignition under `"random_cell"` may land inside the buffer ring, and that is correct: excluding it would bias the comparison in favour of buffer geometries (§3.6), which is exactly the result SQ4 is trying to test honestly.
- `buffer` sits **off** the clustering-scale axis (§4.2, §11). It is the targeted condition, not a point on the curve, and the report should not plot it as one.
- This is the SQ4 condition and the project's insurance against a boring result (roadmap §11). It is last in the descope order among the geometries, but it is not free — budget a real day.
- `SETTLEMENT_SIDE` is still provisional while this is implemented. Write the generator so that changing it in SPEC-12 requires no change here.
