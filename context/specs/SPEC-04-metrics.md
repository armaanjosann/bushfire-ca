---
id: SPEC-04
title: Metrics and scar statistics
status: not started
owner: Armaan
reviewer: Aaron
phase: P1 — Model core (Sprint 1)
depends_on: [SPEC-03]
implements: [§4.3, §3.5, §3.6]
issue:
branch: spec/SPEC-04-metrics
pr:
decisions: []
---

# SPEC-04 — Metrics and scar statistics

## Objective

Pure functions turning a finished run into every response variable the results schema needs, plus the scar-shape statistics that the two physics invariants are measured from.

## Context to read

- `workflow-rules.md`
- `project-context.md` §4.3 (`metrics.py` contract), §3.5 (which metric is meaningful under which ignition mode), §3.6 (the settlement ring rule), §5 (the columns these feed), §7 I4/I5

## Scope

**In scope**

- `burned_fraction`, `burned_fraction_of_fuel`.
- `reached_edge` — did any cell in any of the four edge rows/columns burn.
- `spanned` — did any cell in row `L−1` burn.
- `settlement_reached` and `settlement_reached_step`.
- Scar second moments in x and y (for I4), scar centroid and its projection on `phi` (for I5).
- Tests for I4 and I5.

**Out of scope**

- Anything that runs a fire — call `run_fire` in tests only.
- Writing parquet or deciding dtypes — SPEC-05.
- `p_c` estimation, tail fitting, finite-size scaling — SPEC-06 and SPEC-15.
- Plotting — SPEC-08 and SPEC-17.

## Files

**May touch**

- `src/metrics.py`
- `tests/test_metrics.py`
- `tests/test_invariants.py` — only `test_i4`, `test_i5`

**Must not touch**

- `src/model.py`, `src/geometries.py`, `src/experiments.py`, `src/analysis.py`, `figures/`
- Any invariant test other than I4, I5

## Interface contract

`project-context.md` §4.3 specifies the module's character but not its signatures, so this spec defines them and later specs are written against them.

```python
# src/metrics.py — pure; arrays in, numbers out. No I/O, no plotting.
def burned_fraction(burned_cells: int, n_cells: int) -> float: ...
def burned_fraction_of_fuel(burned_cells: int, n_occupied: int) -> float: ...
def reached_edge(state: np.ndarray) -> bool: ...
def spanned(state: np.ndarray) -> bool: ...
def settlement_ring(L: int, side: int) -> np.ndarray: ...          # bool mask, 1-cell ring
def scar_second_moments(state: np.ndarray) -> tuple[float, float]: ...   # (var_y, var_x)
def scar_centroid(state: np.ndarray) -> tuple[float, float]: ...          # (y, x)
def centroid_projection(centroid, origin, phi: float) -> float: ...
```

If a function here needs something `RunResult` does not carry, **stop and raise a DEC** rather than widening `RunResult` — that is SPEC-03's contract and SPEC-05's schema.

## Behaviour

- **Null semantics are the point of this spec** (§3.5). `spanned` is meaningless under `"random_cell"` and must reach the results row as `null`, not `False`. `reached_edge` under `"edge"` is trivially true and must be `null`, not `True`. These functions return a value or `None`; SPEC-05 writes it into a nullable column. Never substitute a sentinel.
- `settlement_reached` is True iff any cell in the **1-cell-wide ring immediately surrounding** the settlement block enters state `BURNING` at any point during the run (§3.6) — not the block itself, which never burns. `settlement_reached_step` is the step at which it first happens, else `None`. Detecting this requires a per-step check, so expose the ring mask here and have SPEC-03's loop consult it; if that requires a change to `run_fire`, raise a DEC.
- `burned_fraction_of_fuel` with `n_occupied == 0` returns `0.0`, not a division error.
- Scar statistics are computed over `BURNT` cells.

## Acceptance criteria

- [ ] Every function is pure: no file access, no plotting, no global state, no rng.
- [ ] `spanned` on a hand-built grid with one burnt cell in row `L−1` is True; with none, False.
- [ ] `reached_edge` is True for a burnt cell in each of the four edges, tested separately.
- [ ] `settlement_ring(L, side)` has exactly `4*(side+1)` cells and none of them is inside the block.
- [ ] `burned_fraction_of_fuel(0, 0) == 0.0`.
- [ ] `scar_centroid` of a symmetric hand-built scar is its geometric centre.
- [ ] `scar_second_moments` of a scar wider in x than y returns `var_x > var_y`.

## Invariants

- [ ] **I4 isotropy** — at `kappa=0`, scar second moments in x and y are equal within a confidence interval over ≥200 replicates.
- [ ] **I5 wind monotonicity** — the mean scar centroid projection on `phi` is strictly increasing over `kappa ∈ {0,1,2,4}`.

## Verification

```bash
pytest -q tests/test_metrics.py
pytest -q tests/test_invariants.py -k "i4 or i5"
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

- **This is the most likely place in the project to write a boolean where the schema wants a null.** A `False` where §5 says `null` will not raise, will not look wrong in a dataframe, and will quietly corrupt every spanning statistic in Experiment 2.
- I4 and I5 are statistical, so they need replicates and will be the slowest tests in the suite. Keep them at `L = 128` and mark them so they can be deselected during fast iteration — but they must run in the full `pytest` of SPEC-18.
- I5 is a monotonicity claim over four points, so it is sensitive to replicate count. If it fails marginally, raise the replicate count before concluding the wind kernel is wrong — and record which you did.
