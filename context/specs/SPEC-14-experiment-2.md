---
id: SPEC-14
title: Experiment 2 — threshold shift
status: not started
owner: Armaan
reviewer: Aaron
phase: P5 — Full experiments (Sprint 3)
depends_on: [SPEC-06, SPEC-13]
implements: [§6.2 Exp 2, §6.1, §2 O4]
issue:
branch: spec/SPEC-14-experiment-2
pr:
decisions: []
---

# SPEC-14 — Experiment 2: threshold shift

## Objective

Per-condition `STUDY` thresholds are measured with finite-size scaling and appended to `results/pc_estimates.parquet`, answering the crux of the primary research question: does treatment arrangement move `p_c`, or only rescale burned area?

## Context to read

- `workflow-rules.md`
- `project-context.md` §6.2 Exp 2 **and its note on why this experiment uses edge ignition**, §6.1, §2 O4, §4.6
- `spec-plan.md` §6 — the uncosted compute for this experiment
- `checkpoint1-bushfire-ca-roadmap.md` §2 (primary RQ), §5 Exp 2

## Scope

**In scope**

- Selecting the best 3 conditions from Experiment 1, plus `none`, at `b = 0.15`.
- **Declaring the fine `p` sweep range and step explicitly** — see Behaviour.
- The grid: `STUDY`, those 4 conditions, `L ∈ {128, 256, 512}`, R = 500, **`edge` ignition**, no settlement.
- Running it to `results/exp2.parquet` and appending per-condition rows to `pc_estimates.parquet`.

**Out of scope**

- Tail statistics — SPEC-15, which consumes the thresholds this spec produces.
- Changing `estimate_pc` — SPEC-06 owns it.
- Figures — SPEC-17.

## Files

**May touch**

- `src/experiments.py` — the `exp2` grid builder and entry point
- `run.py`
- `results/exp2.parquet`, `results/pc_estimates.parquet`

**Must not touch**

- `src/model.py`, `src/geometries.py`, `src/metrics.py`, `src/analysis.py`, `figures/`

## Interface contract

No new interface. Uses `run_configs` (SPEC-05), `estimate_pc` and `write_pc_estimates` (SPEC-06).

## Behaviour

- **Edge ignition, by design** (§6.2 note). Estimating a percolation threshold requires a spanning measure, and point ignition cannot provide one. This differs from Experiment 1 deliberately; it is not an inconsistency to fix.
- No settlement, since spanning is a landscape-scale measure.
- "Best 3 conditions" means best by mean burned fraction at `b = 0.15` in Experiment 1 at the matching `kappa`. State the selection rule and the resulting three conditions in the PR body so the choice is traceable rather than post-hoc.
- **The sweep range and step must be declared in the grid builder, not left implicit.** `project-context.md` says only "fine `p` sweep". Because Experiment 1 has already located each condition's region, the intent is a narrow sweep — roughly ±0.05 around the expected threshold at a step of 0.005, about 21 points — not a rerun of Experiment 0's range. See Notes for why this matters.
- Rows land in `pc_estimates.parquet` with `regime="STUDY"` and the correct `condition`, `b` and `kappa`. Under §2 O4 these are the thresholds that govern `STUDY` runs; the `PERCOLATION` row governs nothing here and must not be compared against them in any table.

## Acceptance criteria

- [ ] The grid builder declares the sweep range, step and point count as explicit constants.
- [ ] `results/exp2.parquet` exists with `truncated == False` and unique `run_id`.
- [ ] Every row has `ignition == "edge"`, `settlement == False`, `b == 0.15` except the `none` rows at `b == 0`.
- [ ] `reached_edge` is null on every row; `spanned` is non-null on every row.
- [ ] Four `STUDY` rows appear in `pc_estimates.parquet`, each with a stderr and a `method`.
- [ ] Each condition's `P(span)` curve crosses across the three `L` values, and the crossing is inside the swept range — if it is not, the range was wrong and the sweep is rerun, not extrapolated.
- [ ] The PR body names the three selected conditions and the Experiment 1 numbers that selected them.

## Invariants

- [ ] None owned. I10 must hold over this frame.

## Verification

```bash
python run.py --exp 2
python - <<'PY'
import pandas as pd
df = pd.read_parquet("results/exp2.parquet")
assert not df.truncated.any() and df.spanned.notna().all()
print(df.groupby(["condition","L","p"]).spanned.mean().unstack(1).head(20))
pc = pd.read_parquet("results/pc_estimates.parquet")
print(pc[pc.regime=="STUDY"])
PY
```

## Definition of done

- [ ] Acceptance criteria all met
- [ ] Named invariants pass locally
- [ ] Every deviation logged in `decisions-log.md`, IDs listed in `decisions:` above
- [ ] Any contract change applied to `project-context.md` in this same PR
- [ ] `status` updated in this file and in `progress-tracker.md`
- [ ] `results/exp2.parquet` and the updated `pc_estimates.parquet` committed
- [ ] PR open, linked to the issue — status `in review`
- [ ] Reviewed by `reviewer` and merged — status `done` (human only)

## Notes and risks

- **The compute here is not small and `project-context.md` does not cost it.** Four conditions × 500 replicates × three lattice sizes is `2000n` runs per `L` for an `n`-point sweep; at `L=512` each point costs ~4.4 core-hours. A 21-point sweep is ~93 core-hours — about 5.8 hours across 16 cores, so an overnight run, not something to start on the Sunday. A 40-point sweep would be ~178 core-hours. **This is why the range must be declared rather than chosen generously.**
- This experiment is the crux of the primary RQ. A threshold shift is a change in the system's critical point; no shift with reduced burned area is a change in amplitude. Both are publishable answers, and the report should be written to accept either.
- `p_c` is a property of the rule and the lattice, not of the ignition mode. That is why SPEC-15 can legitimately use these edge-ignition estimates as the `p` for its point-ignition tail runs.
