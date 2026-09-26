---
id: SPEC-14
title: Experiment 2 — threshold shift
status: not started
owner: Armaan
reviewer: Aaron
phase: P5 — Full experiments (Sprint 3)
depends_on: [SPEC-06, SPEC-13, SPEC-19]
implements: [§6.2 Exp 2, §6.1, §2 O4]
issue:
branch: spec/SPEC-14-experiment-2
pr:
decisions: [DEC-003, DEC-004, DEC-005, DEC-011, DEC-012]
---

# SPEC-14 — Experiment 2: threshold shift

## Objective

Per-condition `STUDY` thresholds are measured with finite-size scaling and appended to `results/pc_estimates.parquet`, answering the crux of the primary research question: does treatment arrangement move `p_c`, or only rescale burned area?

## Context to read

- `workflow-rules.md`
- `project-context.md` §6.2 Exp 2, **the Experiment 2 selection rule**, and the note on edge ignition; §6.1 including the **edge-ignition wind convention**; §2 O4; §4.6
- `spec-plan.md` §6 — the uncosted compute for this experiment
- `checkpoint1-bushfire-ca-roadmap.md` §2 (primary RQ), §5 Exp 2

## Scope

**In scope**

- Applying the §6.2 selection rule, fixed in advance (DEC-012), to Experiment 1. That picks the best `patches` level and the best `strips_perp` level.
- **Declaring the fine `p` sweep range and step explicitly** — see Behaviour.
- The grid: `STUDY`, `kappa = 0`, `phi = -π/2`, at `b = 0.15` over three treated conditions: `random`, the selected `patches(k*)` and the selected `strips_perp(w*)`. `L ∈ {128, 256, 512}`, R = 500, **`edge` ignition**, no settlement.
- Running it to `results/exp2.parquet` and appending per-condition rows to `pc_estimates.parquet`.
- **No `none` arm.** The untreated reference is Experiment 0b's `kappa = 0` threshold (SPEC-19), measured with identical settings.

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
- **Selection rule (§6.2, DEC-012), applied as written.** Take the lowest mean `burned_fraction` in Experiment 1 at `b = 0.15`, `p_rel = +0.05`, `kappa = 0`, separately among `patches(k=4,8,16)` and among `strips_perp(w=4,8,16)`. `random` is always included. Exactly one level per family is measured, which keeps the `pc_estimates` key unique, since the key has no `k`/`w` column. State the selected `k*`, `w*` and the Experiment 1 numbers behind them in the PR body.
- **`kappa = 0`, `phi = -π/2`** (§6.1 convention). At `kappa = 0` the wind has no effect. `phi` only orients `strips_perp`, so its bands run across the spanning direction, and the settings match SPEC-19's `kappa = 0` arm apart from condition and `b`.
- **The sweep range and step must be declared in the grid builder, not left implicit.** Centre each condition's sweep on the SPEC-19 `kappa = 0` threshold, ±0.05 at step 0.005 (21 points). Treatment only lowers fuel load, so a treated threshold is expected at or above the untreated one. If a crossing falls outside the range, shift that condition's range and rerun it; never extrapolate. See Notes for why this matters.
- Rows land in `pc_estimates.parquet` with `regime="STUDY"` and the correct `condition`, `b` and `kappa`. Under §2 O4 these are the thresholds that govern `STUDY` runs; the `PERCOLATION` row governs nothing here and must not be compared against them in any table.

## Acceptance criteria

- [ ] The grid builder declares the sweep range, step and point count as explicit constants.
- [ ] `results/exp2.parquet` exists with `truncated == False` and unique `run_id`.
- [ ] Every row has `ignition == "edge"`, `settlement == False`, `b == 0.15`, `kappa == 0`, `phi == -π/2`, and `condition != "none"`.
- [ ] `reached_edge` is null on every row; `spanned` is non-null on every row.
- [ ] `pc_estimates.parquet` holds exactly one `STUDY` `fss_crossing` row per `(condition, b=0.15, kappa=0)`: one `patches`, one `strips_perp`, one `random`.
- [ ] For each of the three conditions, `pc_estimates.parquet` gains one `method="fss_crossing"` row with `L` null and three per-`L` `method="var_peak"` rows (SPEC-06 row identity, DEC-004), each with a stderr, and `resolve_p` resolves each condition's key without raising.
- [ ] Each condition's `P(span)` curve crosses across the three `L` values, and the crossing is inside the swept range — if it is not, the range was wrong and the sweep is rerun, not extrapolated.
- [ ] The PR body names `k*` and `w*` and the Experiment 1 numbers that selected them under the §6.2 rule.

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

- **The compute here is not small** (§6.3). Three conditions × 500 replicates × three lattice sizes is `1500n` runs per `L` for an `n`-point sweep, and at `L=512` each point costs about 3.3 core-hours. A 21-point sweep is about 77 core-hours, roughly 4.8 hours across 16 cores. That is an overnight run, not something to start on the Sunday. **This is why the range must be declared rather than chosen generously.**
- This experiment is the crux of the primary RQ. A threshold shift is a change in the system's critical point; no shift with reduced burned area is a change in amplitude. Both are publishable answers, and the report should be written to accept either.
- `p_c` is a property of the rule and the lattice, not of the ignition mode. That is why SPEC-15 can legitimately use these edge-ignition estimates as the `p` for its point-ignition tail runs.
