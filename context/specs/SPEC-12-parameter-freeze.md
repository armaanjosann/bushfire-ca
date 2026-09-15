---
id: SPEC-12
title: Settlement-size pilot, coarse Experiment 1, parameter freeze
status: not started
owner: Aaron
reviewer: Armaan
phase: P4 — Parameter freeze (Sprint 2)
depends_on: [SPEC-05, SPEC-06, SPEC-10, SPEC-11, SPEC-19]
implements: [§10.2 O1, §3.6, §6.2 Exp 1]
issue:
branch: spec/SPEC-12-parameter-freeze
pr:
decisions: [DEC-003, DEC-007, DEC-011, DEC-015]
---

# SPEC-12 — Settlement pilot, coarse Experiment 1, parameter freeze

## Objective

`SETTLEMENT_SIDE` is fixed by evidence and written into `project-context.md` §3.6 as a constant with its justification; a coarse `A(geometry, b)` heatmap exists; and §10 carries no open item except O4.

## Context to read

- `workflow-rules.md` — especially §5 (**the contract rule**) and §6
- `project-context.md` §10.2 O1 (the pilot and its decision rule), §3.6 (settlement, and the `settlement_side` key), §6.2 Exp 1 and the Experiment 2 selection rule, §6.1 (the pilot's `p_rel` resolves against Experiment 0b, SPEC-19)
- `checkpoint1-bushfire-ca-roadmap.md` §8 (Sprint 2 exit: *parameters locked and justified in writing*)

## Scope

**In scope**

- The pilot: side ∈ {8, 16, 32, 48} × `kappa` ∈ {0, 2}, at `b = 0`, `condition = "none"`, `p_rel = +0.05`, `L = 256`, R = 50. ~800 runs, well under half an hour. Side is varied per config through `geometry_params={"settlement_side": side}` (DEC-007), which SPEC-02 (placement), SPEC-04 (ring) and SPEC-11 (buffer) already read, so each side gets a distinct `run_id` and no model code changes for the pilot.
- Applying the §10.2 O1 decision rule and fixing `SETTLEMENT_SIDE`.
- Editing `project-context.md` §3.6 and §10.2 in this same PR, with a DEC entry.
- A coarse Experiment 1 pass over a reduced grid, to locate the interesting region of `(geometry, b)`.
- A coarse heatmap figure.

**Out of scope**

- Experiment 1 at full replicates — SPEC-13.
- Resolving §10.2 O4 (burn-size replicate count) — SPEC-15, and it is not yet decidable.
- Changing any §4 signature or §5 column.

## Files

**May touch**

- `src/model.py` — the `SETTLEMENT_SIDE` constant only. The pilot varies side through `geometry_params["settlement_side"]` (DEC-007), so no other change to placement or the ring check is needed or permitted
- `src/experiments.py` — the pilot and coarse-Exp-1 grid builders
- `figures/make_figures.py` — the coarse heatmap builder **only**. This is an agreed exception:
  figures are Armaan's component under roadmap §9, so add one registered builder and change
  nothing else in that file. Armaan reviews this PR, which is what makes the exception safe.
- `run.py`
- `results/pilot_settlement.parquet`, `results/exp1_coarse.parquet`
- `context/project-context.md` §3.6 and §10.2 — **required**, per the contract rule
- `context/decisions-log.md` — a new DEC entry

**Must not touch**

- `src/geometries.py`, `src/metrics.py`, `src/analysis.py`
- `src/model.py` beyond the `SETTLEMENT_SIDE` constant
- Any other section of `project-context.md`

## Interface contract

No new interface. Uses `run_configs` (SPEC-05) and `resolve_p` (SPEC-06).

## Behaviour

**The decision rule is already fixed** by §10.2 O1 and must not be reinterpreted after seeing the pilot:

1. Take the **smallest** side whose baseline `P(settlement_reached)` falls in **[0.3, 0.8]**.
2. Reject any side for which `n_occupied` differs by more than 1% from the no-settlement case at the same `p`.
3. If no side satisfies both, the discriminating variable is wrong rather than the size: switch the SQ4 metric to `settlement_reached_step` — time-to-reach, which does not saturate — and record that change.

Then:

- Write the chosen value into §3.6 as a constant with the justification attached. The pilot is a **Methods paragraph, not a result**.
- **This is the one spec that is expected to change the specification.** `workflow-rules.md` §5 applies in full: `project-context.md` is edited in this same PR, and the DEC entry names the sections changed plus the commit SHA.
- The coarse Exp 1 pass exists to locate the interesting region so the full run in SPEC-13 is not the first time anyone looks at the data. Reduce replicates and the `b` grid, not the condition set.

## Acceptance criteria

- [ ] `results/pilot_settlement.parquet` exists with 800 rows and `truncated == False`.
- [ ] Baseline `P(settlement_reached)` is reported per side and per `kappa`.
- [ ] `n_occupied` drift versus the no-settlement case is computed and reported per side.
- [ ] `SETTLEMENT_SIDE` in `src/model.py` equals the value the decision rule selects, and the provisional marker is removed.
- [ ] `project-context.md` §3.6 states the chosen value with its justification; §10.2 O1 is marked resolved.
- [ ] A DEC entry exists naming the sections changed and the commit SHA.
- [ ] `results/exp1_coarse.parquet` exists and a coarse `A(geometry, b)` heatmap builds.
- [ ] `project-context.md` §10 has no item with status open except O4.

## Invariants

- [ ] None owned. I10 (`truncated == False`) must hold over both new frames.

## Verification

```bash
python run.py --exp pilot
python run.py --exp 1-coarse
python figures/make_figures.py --figure exp1-coarse
python - <<'PY'
import pandas as pd
d = pd.read_parquet("results/pilot_settlement.parquet")
print(d.groupby(["geometry_params","kappa"]).settlement_reached.mean())
print(d.groupby("geometry_params").n_occupied.mean())
PY
grep -n "SETTLEMENT_SIDE" src/model.py context/project-context.md
```

## Definition of done

- [ ] Acceptance criteria all met
- [ ] Named invariants pass locally
- [ ] Every deviation logged in `decisions-log.md`, IDs listed in `decisions:` above
- [ ] **Contract change applied to `project-context.md` §3.6 and §10.2 in this same PR**
- [ ] `status` updated in this file and in `progress-tracker.md`
- [ ] PR open, linked to the issue — status `in review`
- [ ] Reviewed by `reviewer` and merged — status `done` (human only)

## Notes and risks

- **Gate G1 — the parameter freeze — closes with this PR.** After it, a methodological choice is a choice made after seeing results, which is not defensible in the report. `project-context.md` §10 is explicit: nothing may still be open after the Sprint 2 freeze.
- The decision rule is fixed **before** the pilot runs, deliberately. If the outcome is inconvenient, take branch 3 of the rule — do not renegotiate branches 1 and 2 against the data.
- The pilot has two failure modes it is designed to catch: too small and `settlement_reached` saturates near 0 or 1 and cannot discriminate between geometries, which kills SQ4; too large and the settlement is a hole big enough to shift the effective occupancy.
- This is the merge point of the two work tracks. If SPEC-02's call into `geometries.generate` and SPEC-09's implementation have drifted, this is where it surfaces — which is why the §4.2 signature was frozen in SPEC-01.
