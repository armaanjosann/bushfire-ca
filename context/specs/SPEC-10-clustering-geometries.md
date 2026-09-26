---
id: SPEC-10
title: Clustering-scale family — patches, strips_perp, strips_para
status: not started
owner: Armaan
reviewer: Aaron
phase: P3 — Treatment geometries (Sprint 2)
depends_on: [SPEC-09]
implements: [§4.2, §10.1 D2, §11]
issue:
branch: spec/SPEC-10-clustering-geometries
pr:
decisions: [DEC-007, DEC-008]
---

# SPEC-10 — Clustering-scale family

## Objective

Nine condition-levels exist — `patches(k)` and `strips_perp(w)` / `strips_para(w)` for `k, w ∈ {4, 8, 16}` — each hitting `n_treat` within the shared tolerance, so the clustering-scale axis of the primary analysis is continuous across both geometry families.

## Context to read

- `workflow-rules.md`
- `project-context.md` §4.2 (the three condition rows and their construction), §10.1 D2 (why `w` is swept), §11 (clustering scale — what this spec exists to make continuous), §6.2 (the 12 condition-levels)

## Scope

**In scope**

- `"patches"`, parameter `k ∈ {4, 8, 16}`.
- `"strips_perp"`, parameter `w ∈ {4, 8, 16}`.
- `"strips_para"`, parameter `w ∈ {4, 8, 16}`.
- Registering all nine levels so an experiment grid can enumerate them.

**Out of scope**

- `buffer` — SPEC-11.
- The shared budget, placement and null-treatment helpers — SPEC-09 owns them; **use them, do not reimplement them**.
- Choosing which conditions go into which experiment — SPEC-13 onward.

## Files

**May touch**

- `src/geometries.py`
- `tests/test_geometries.py`

**Must not touch**

- `src/model.py`, `src/metrics.py`, `src/experiments.py`, `src/analysis.py`, `figures/`
- `tests/test_invariants.py` — I6, I7, I8 belong to SPEC-09; they must keep passing, and if one breaks the fix is here but the test is not yours to edit (`workflow-rules.md` §6)

## Interface contract

As `project-context.md` §4.2 — do not redesign. Parameters arrive through `**params`: `k` for `patches`, `w` for both strip conditions. SPEC-02's call site also always passes `phi` (= `cfg.phi`) and `settlement_side` (DEC-007, DEC-008): both strip conditions use `phi`; `patches` ignores both; the strip conditions ignore `settlement_side`.

## Behaviour

Construction is specified in §4.2 and is not to be reinterpreted:

- **`patches`** — place `k × k` blocks at uniformly random top-left positions (they may overlap) until covered occupied cells ≥ `n_treat`; then randomly un-treat the excess. Record the actual count.
- **`strips_perp`** — bands of width `w` running perpendicular to `phi`, evenly spaced; **bisect on spacing** until the occupied-cell count hits `n_treat`. The band phase offset is drawn uniformly **per replicate**.
- **`strips_para`** — the identical construction rotated 90°. Same shape, same budget, different orientation — that is the entire point, and it is what isolates orientation from geometry.

Further:

- **Strips are built at any `phi`, not only axis-aligned** (DEC-008). `strips_perp` bands run perpendicular to `phi` and `strips_para` bands parallel to it for any `phi`, including `phi = π/4` (diagonal bands), using the §3.4 direction convention (`phi = 0` is east, array `+y` is south). `w` is the band width measured perpendicular to the band. I11 (SPEC-16) depends on this.
- `w` is a swept clustering-scale level, **not a fixed default** (§10.1 D2). The default of 4 in §4.2 exists so a config is constructible, not so the sweep is skipped.
- Tolerance and the realised-count rule come from SPEC-09's shared helper: within `max(1, ceil(0.01 * n_treat))`, and `n_treated` records the realised count.
- The early return on `n_treat == 0`, before touching `rng`, applies to all three (I6).

## Acceptance criteria

- [ ] All nine levels are constructible and each satisfies the budget tolerance over ≥50 seeds at `p ∈ {0.4, 0.55, 0.7}` and `b ∈ {0.05, 0.15, 0.30}`.
- [ ] At `phi = 0`, `strips_perp` and `strips_para` at the same `w`, `b` and seed produce masks that are transposes of each other in shape statistics — same treated count within tolerance, orthogonal band orientation.
- [ ] The bisection on spacing terminates for every `(w, b, p)` combination in the Experiment 1 grid, and raises rather than looping if it cannot converge.
- [ ] A test checks band orientation at `phi ∈ {0, π/4, π/2}`: at `phi = π/4` both strip conditions produce diagonal bands (perpendicular and parallel to the wind respectively) and meet the budget tolerance (DEC-008).
- [ ] `patches` output does not depend on `phi` or `settlement_side`.
- [ ] Band phase offset differs across replicates at the same config but is reproducible for a given seed.
- [ ] `patches` with `k=16` at low `b` still hits the budget — the un-treat-the-excess step is exercised.
- [ ] Mean connected-component size increases monotonically across `random` → `patches(4)` → `patches(8)` → `patches(16)`, confirming the clustering-scale axis is ordered as §11 claims.
- [ ] I6, I7, I8 still pass for all nine levels.

## Invariants

- [ ] None owned. I6, I7 and I8 (SPEC-09) must continue to pass across all nine new levels — extend the parametrisation of SPEC-09's tests only if SPEC-09 wrote them to be extended; otherwise raise a DEC.

## Verification

```bash
pytest -q tests/test_geometries.py
pytest -q tests/test_invariants.py -k "i6 or i7 or i8"
python - <<'PY'
import numpy as np
from src.geometries import generate
rng = np.random.default_rng(0); occ = rng.random((256,256)) < 0.55
n = int(round(0.15 * occ.sum()))
for cond, kw in [("random",{}),("patches",{"k":4}),("patches",{"k":16}),
                 ("strips_perp",{"w":4}),("strips_para",{"w":16})]:
    m = generate(cond, np.random.default_rng(1), occ, n, **kw)
    print(f"{cond}{kw}: treated={int((m&occ).sum())} target={n}")
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

- **This spec is what makes the primary analysis a curve rather than a bar chart.** §10.1 D2 resolved to sweep `w` precisely so that `random` (scale 1), `patches` (scale `k`) and `strips` (scale `w`) sit on one continuous axis. Fixing `w` at 4 would leave that axis with three points from patches and one isolated strip, and the geometry comparison degenerates.
- The bisection is the fiddly part. At high `b` and low `p` the spacing that hits the budget may be below `w`, meaning bands overlap — decide what that means and state it, rather than letting the bisection silently converge on nonsense.
- Cost of the D2 decision, for context: Experiment 1 goes from 8 to 12 condition-levels, roughly 28 core-hours, under two hours across 16 cores. Not a reason to descope.
