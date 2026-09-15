---
id: SPEC-03
title: Step function and run_fire
status: not started
owner: Aaron
reviewer: Armaan
phase: P1 — Model core (Sprint 1)
depends_on: [SPEC-01, SPEC-02]
implements: [§3.3, §3.7, §4.1, §8]
issue:
branch: spec/SPEC-03-step-function
pr:
decisions: [DEC-006, DEC-013]
---

# SPEC-03 — Step function and `run_fire`

## Objective

A fire runs to extinction on the lattice, deterministically for a given config, with no per-cell Python loop anywhere in the step. `RunResult` exists and carries every non-config field of the §5 schema.

## Context to read

- `workflow-rules.md`
- `project-context.md` §3.3 (transition rule and its semantics), §3.7 (truncation), §4.1 (`run_fire`, `RunResult`, `capture_scar`), §3.4 (wind weights, already built in SPEC-01), §8 (vectorisation and the bounding box), §5 (the field list `RunResult` must carry), §7 I2/I3/I9

## Scope

**In scope**

- The synchronous step: eight shifted burning masks, running product of `(1 − P_d)`, one Bernoulli draw over the grid.
- `burn_clock` and the `tau` transition to `BURNT`.
- `run_fire(cfg, capture_scar=False) -> RunResult`, creating its own `np.random.default_rng(cfg.seed)` internally.
- Resolving `max_steps = 8 * L` when `cfg.max_steps is None`.
- `truncated` and `still_burning_cells`.
- The bounding-box restriction (§8) with 1-cell padding, and precomputed shifted-slice index pairs.
- `RunResult` as a dataclass with exactly the §5 fields minus the config echo, plus `scar`.
- Populating the **raw outcome fields** of `RunResult` inside `run_fire` (DEC-006): `n_cells`, `n_occupied`, `n_treated` (realised, from the initialised grids), `ignition_y`, `ignition_x` (null under `"edge"`), `burned_cells`, `still_burning_cells`, `steps`, `truncated`, `scar`, and `ignition_step` (DEC-013). The **derived fields** (`burned_fraction`, `burned_fraction_of_fuel`, `spanned`, `reached_edge`, `settlement_reached`, `settlement_reached_step`) are declared on the dataclass here with default `None` and populated by SPEC-04.
- Tests for I2, I3, I9.

**Out of scope**

- Computing derived metrics and the per-step settlement-ring check — `burned_fraction`, `burned_fraction_of_fuel`, `reached_edge`, `spanned`, `settlement_reached`, `settlement_reached_step` are SPEC-04's. SPEC-04 is permitted to edit `run_fire`'s result assembly and add the ring check to the loop (DEC-006); leave those fields `None` here.
- Assembling a parquet row, `run_id`, `code_version`, `wall_ms` — SPEC-05.
- Any treatment geometry — SPEC-09 onward.

## Files

**May touch**

- `src/model.py`
- `tests/test_invariants.py` — only `test_i2`, `test_i3`, `test_i9`
- `tests/test_step.py`

**Must not touch**

- `src/geometries.py`, `src/metrics.py`, `src/analysis.py`, `src/experiments.py`, `figures/`
- Any invariant test other than I2, I3, I9

## Interface contract

As `project-context.md` §4.1 — do not redesign:

```python
@dataclass
class RunResult:
    ...        # exactly the fields in the schema of §5, minus the config echo
    scar: np.ndarray | None = None
    ignition_step: np.ndarray | None = None   # int32[L, L], -1 where never burning (DEC-013)

def run_fire(cfg: Config, capture_scar: bool = False) -> RunResult: ...
```

`run_fire` is pure with respect to `cfg`: same config, same result, always. It **must not accept an external generator** — that is what makes I2 possible.

## Behaviour

Implement §3.3 exactly. The semantics that must be preserved, restated only because each one is a distinct way to get this wrong:

- Ignition probabilities come from the burning set **at the start of the step**. A cell ignited this step does not spread until the next step.
- A cell that becomes `BURNT` this step **did** get to attempt ignition this step — step 2 runs before step 4.
- `EMPTY`, `BURNT` and `SETTLEMENT` never ignite. Only `FUEL` can.
- `P_d(j) = clip(beta * w_d * f[j], 0.0, 1.0)`, and `P(j ignites) = 1 − Π_d (1 − P_d(j))` over directions whose source neighbour is burning. Accumulate the product over the eight shifted masks, then **one** Bernoulli draw over the whole grid — not eight draws.
- Terminate when no `BURNING` cells remain, or at `step == max_steps`.
- On truncation: `truncated = True`, and cells still `BURNING` are counted in `still_burning_cells`. **`burned_cells` counts `BURNT` only.** Folding still-burning cells into the burned total was the throwaway prototype's bug (§3.7).
- `capture_scar=True` returns the final state grid **and** `ignition_step`. `ignition_step` is an `int32[L, L]` grid holding the step at which each cell first became `BURNING`: `0` for the cells ignited at `t=0`, `-1` for cells that never burned (§4.1, DEC-013). Both are `None` when `capture_scar=False`, and tracking `ignition_step` must cost nothing on that path. Default False, and callers must never request it for a sweep (§4.1).

## Acceptance criteria

- [ ] A fire at `p = 0.6`, `L = 128` runs to extinction with `truncated == False`.
- [ ] No Python-level loop over cells anywhere in the step; the only loop is over the eight neighbour offsets and over time.
- [ ] `run_fire` called twice on the same `Config` returns equal values in every field.
- [ ] `run_fire` does not accept, and cannot be passed, an external `rng`.
- [ ] `cfg.max_steps is None` resolves to `8 * cfg.L`.
- [ ] A run truncated by an artificially low `max_steps` reports `truncated == True` and non-zero `still_burning_cells`, and `burned_cells` excludes them.
- [ ] `p = 0` returns a zero-burn run without raising.
- [ ] Every run populates `n_cells`, `n_occupied`, `n_treated`, `burned_cells`, `still_burning_cells`, `steps`, `truncated`; `ignition_y`/`ignition_x` are set under `"random_cell"` and `None` under `"edge"` (DEC-006).
- [ ] With `capture_scar=True`, `ignition_step >= 0` exactly where `scar` is `BURNING` or `BURNT`, and the ignition cells are `0`. Under the I3 settings, `ignition_step` equals Chebyshev distance from the ignition cell. With `capture_scar=False`, `scar` and `ignition_step` are both `None` (DEC-013).
- [ ] The bounding-box path gives results identical to a full-grid path on the same seed (keep a slow reference implementation in the test file for this comparison).

## Invariants

- [ ] **I2 determinism** — run any config twice; every `RunResult` field equal.
- [ ] **I3 deterministic front** — `p=1, beta=1, kappa=0, diagonal_factor=False`: the front is a square expanding exactly 1 cell/step in Chebyshev distance. Assert Chebyshev growth **only** in the `diagonal_factor=False` case; with it True the front is not square (§2 O3, O6).
- [ ] **I9 conservation** — `burned_cells + still_burning_cells <= n_occupied`, and no cell leaves `BURNT`.

## Verification

```bash
pytest -q tests/test_step.py
pytest -q tests/test_invariants.py -k "i2 or i3 or i9"
python - <<'PY'
import time
from src.model import Config, run_fire
for L in (128, 256):
    cfg = Config(L=L, p=0.6, seed=0)
    t=time.perf_counter(); r=run_fire(cfg); dt=(time.perf_counter()-t)*1000
    print(L, r.burned_cells, r.steps, r.truncated, f"{dt:.0f} ms")
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

- **This is the largest and most consequential spec in the project.** Everything downstream is numbers this function produced. If any spec is worth hand-writing rather than handing to an agent, it is this one.
- The bounding-box optimisation is where the bulk of the speedup lives (§8), and it is also the easiest place to introduce an off-by-one that only shows up as a fire that mysteriously stops at a boundary. The slow reference implementation in the test file is not optional — SPEC-07's `L=512` arm is roughly 68 core-hours and is not something to run twice.
- Outcome-field ownership is split with SPEC-04 (DEC-006): this spec fills the raw fields, SPEC-04 fills the derived ones and adds the per-step settlement-ring check. Keep the loop structured so that check can be added without changing the step rule.
- Boundaries are absorbing and non-periodic (§3.1). Fire leaving the domain simply leaves. Do not wrap.
- Target performance from §6.3: ~44 ms at `L=128`, ~760 ms at `L=256`, ~8 s at `L=512` on one throttled core, unoptimised. Materially slower than that on your hardware means the bounding box is not working.
