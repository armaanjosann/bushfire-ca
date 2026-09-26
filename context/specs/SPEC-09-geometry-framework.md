---
id: SPEC-09
title: Geometry framework, none, random
status: not started
owner: Armaan
reviewer: Aaron
phase: P3 — Treatment geometries (Sprint 2)
depends_on: [SPEC-02]
implements: [§4.2]
issue:
branch: spec/SPEC-09-geometry-framework
pr:
decisions: [DEC-007, DEC-008]
---

# SPEC-09 — Geometry framework, `none`, `random`

## Objective

`generate` dispatches by condition and the two baseline conditions hit their budget exactly, with the budget, placement and null-treatment contracts enforced in code rather than in prose.

## Context to read

- `workflow-rules.md`
- `project-context.md` §4.2 (the generator contract — all of it), §2 O1/O2, §3.2 (why occupancy is drawn first), §7 I6/I7/I8, §11 (clustering scale)

## Scope

**In scope**

- `generate(condition, rng, occupied, n_treat, **params)` dispatch, replacing SPEC-01's stub.
- `"none"`: all-False, requires `n_treat == 0`.
- `"random"`: `n_treat` occupied cells uniformly without replacement. Exact. Clustering scale 1.
- The shared budget/placement assertions every generator must satisfy.
- Tests for I6, I7, I8.

**Out of scope**

- `patches`, `strips_perp`, `strips_para` — SPEC-10. `buffer` — SPEC-11.
- Computing `n_treat` — the caller does that (§4.2); SPEC-02 owns the call site.
- Anything in `model.py`.

## Files

**May touch**

- `src/geometries.py`
- `tests/test_geometries.py`
- `tests/test_invariants.py` — only `test_i6`, `test_i7`, `test_i8`

**Must not touch**

- `src/model.py`, `src/metrics.py`, `src/experiments.py`, `src/analysis.py`, `figures/`
- Any invariant test other than I6, I7, I8

## Interface contract

As `project-context.md` §4.2 — do not redesign. SPEC-01's stub already matches it and SPEC-02 already calls it.

```python
Generator = Callable[..., np.ndarray]   # -> bool[L, L], True where treated
def generate(condition: str, rng, occupied: np.ndarray, n_treat: int, **params) -> np.ndarray
```

## Behaviour

Three contracts that every generator in SPEC-09, SPEC-10 and SPEC-11 must satisfy. Implement them once here as shared helpers so the later specs inherit them rather than reimplementing them:

- **Budget.** `(mask & occupied).sum() == n_treat` where exactly achievable, otherwise within `max(1, ceil(0.01 * n_treat))`. The **realised** count is what `n_treated` records and what the efficiency metric divides by — never the nominal `b` (§4.2, §11).
- **Placement.** A generator never marks a non-occupied cell. Assert `(mask & ~occupied).sum() == 0` before returning.
- **Null treatment.** `n_treat == 0` returns an all-False mask for every condition, **identically** — and returns it **before touching `rng`**.

Also: **reserved params** (DEC-007, DEC-008). SPEC-02's call site always passes `phi` and `settlement_side` in `**params`, alongside the condition's own parameters. `generate` and every generator must accept both keys; a generator that does not use them ignores them. `none` and `random` use neither.

That last one deserves the emphasis `project-context.md` §7 gives it. The natural way to write a generator draws from `rng` even when `n_treat == 0`, which desynchronises the stream and makes the `b=0` baselines differ between conditions for no physical reason. The early return must be the first statement of every generator, and the I6 test is byte-equality of results across every condition at `b=0` on a fixed seed.

## Acceptance criteria

- [ ] `generate("none", ...)` with `n_treat > 0` raises.
- [ ] `generate("random", ...)` hits `n_treat` exactly, for `n_treat` from 1 to `occupied.sum()`.
- [ ] `generate("random", ...)` with `n_treat == occupied.sum()` treats every occupied cell and no other.
- [ ] Every condition at `n_treat == 0` returns an all-False mask.
- [ ] An unknown condition string raises with a message listing the valid conditions.
- [ ] The placement assertion is live in the shipped code, not only in tests.
- [ ] The budget helper is shared, so SPEC-10 and SPEC-11 cannot each invent their own tolerance.
- [ ] `generate("none" | "random", ..., phi=0.7, settlement_side=32)` returns the same mask as the call without those keys, including at `n_treat == 0` (DEC-007, DEC-008).

## Invariants

- [ ] **I6 null treatment** — same seed, every condition, `b=0` ⟹ byte-identical results. Catches accidental rng consumption inside generators.
- [ ] **I7 budget parity** — `n_treated` within tolerance of `round(b * n_occupied)` for every condition; asserted in the generator and again over a results frame.
- [ ] **I8 treatment placement** — `mask & ~occupied` is empty.

## Verification

```bash
pytest -q tests/test_geometries.py
pytest -q tests/test_invariants.py -k "i6 or i7 or i8"
python - <<'PY'
import numpy as np
from src.geometries import generate
rng = np.random.default_rng(0)
occ = rng.random((64,64)) < 0.5
for c in ("none","random"):
    m = generate(c, np.random.default_rng(7), occ, 0)
    print(c, m.sum(), "rng untouched" )
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

- **I6 is the one to get right**, and the failure it catches is silent: the `b=0` baselines drift apart between conditions, every efficiency number is computed against a slightly wrong reference, and nothing raises. Write the test first.
- This spec can start as soon as SPEC-02 merges. It does not wait for the step function, which is what makes the two work tracks genuinely parallel through Sprint 1 and 2.
- `random` is the null model of the clustering-scale axis (§11) at scale 1. The whole primary analysis is a comparison against it, so "exact" here means exact, not within tolerance.
