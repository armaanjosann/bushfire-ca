---
id: SPEC-07
title: Experiment 0 — percolation validation run
status: not started
owner: Aaron
reviewer: Armaan
phase: P2 — Harness and validation (Sprint 1)
depends_on: [SPEC-05, SPEC-06]
implements: [§6.2 Exp 0, §6.1, §1]
issue:
branch: spec/SPEC-07-experiment-0
pr:
decisions: [DEC-001, DEC-004, DEC-014]
---

# SPEC-07 — Experiment 0: percolation validation run

## Objective

`results/exp0.parquet` exists, and the finite-size-scaling crossing estimate of `p_c` under the `PERCOLATION` regime is within 0.01 of `P_C_LITERATURE` (§7 I1, DEC-014). This is the project's replication deliverable.

## Context to read

- `workflow-rules.md`
- `project-context.md` §1 (why the `PERCOLATION` regime exists and why its settings are not negotiable), §6.2 Exp 0, §6.1, §4.4 (validation that enforces the regime), §7 I1, §10.1 D5
- `spec-plan.md` §6 — the compute arithmetic for this experiment

## Scope

**In scope**

- The Experiment 0 config grid: `PERCOLATION`, `p ∈ [0.30, 0.60]` step 0.005 (61 values), `L ∈ {128, 256, 512}`, R=500, `edge` ignition, no settlement.
- Running it through SPEC-05's harness to `results/exp0.parquet`.
- Feeding the frame to SPEC-06's `estimate_pc` and appending the rows to `results/pc_estimates.parquet`.
- The I1 assertion.
- Wiring `run.py --exp 0`.

**Out of scope**

- The validation figure — SPEC-08.
- Any `STUDY` run, any treatment, any settlement.
- Changing the estimator — SPEC-06 owns it.

## Files

**May touch**

- `src/experiments.py` — the `exp0` grid builder and entry point only
- `run.py` — the `--exp 0` wiring
- `results/exp0.parquet`, `results/pc_estimates.parquet`
- `tests/test_invariants.py` — only `test_i1`

**Must not touch**

- `src/model.py`, `src/metrics.py`, `src/geometries.py`, `src/analysis.py`, `figures/`
- Any invariant test other than I1

## Interface contract

No new interface. Uses `run_configs` (SPEC-05) and `estimate_pc` / `write_pc_estimates` (SPEC-06) as they stand.

## Behaviour

- The `PERCOLATION` settings are fixed by §1 and enforced by §4.4: `beta=1.0`, `kappa=0.0`, `diagonal_factor=False`, `b=0`, `tau=1`, `ignition="edge"`. **Changing any of them breaks the exact reduction to site percolation and destroys the validation.** Build the grid so that §4.4 would reject anything else.
- Under these settings the model reduces exactly to site percolation on a Moore-neighbourhood square lattice, so the burned region is precisely the connected cluster containing the ignition. That is the claim the figure in SPEC-08 asserts.
- `P_C_LITERATURE = 0.407` is used **here and nowhere else** (§6.1): the I1 assertion that the measured value is within tolerance of it. It is never a grid value and never a substitute for a measured `p_c`.
- Rows land in `pc_estimates.parquet` with `regime="PERCOLATION"`, `condition="none"`, `b=0`, `kappa=0`, using SPEC-06's row identity (DEC-004). Under §2 O4 these govern no `STUDY` run.

## Acceptance criteria

- [ ] `python run.py --exp 0` produces `results/exp0.parquet` with 91,500 rows (61 × 500 × 3) and `truncated == False` throughout.
- [ ] Every row has `regime == "PERCOLATION"`, `beta == 1.0`, `kappa == 0.0`, `diagonal_factor == False`, `b == 0`, `ignition == "edge"`.
- [ ] `reached_edge` is null on every row; `spanned` is non-null on every row.
- [ ] Four rows are appended to `pc_estimates.parquet` (DEC-004): three per-`L` rows (`method="var_peak"`, `L` ∈ {128, 256, 512}) and one `method="fss_crossing"` row with `L` null.
- [ ] The `fss_crossing` row is within 0.01 of 0.407, as I1 is worded in `project-context.md` §7 (DEC-014). The `L=512` `var_peak` value is reported alongside it as a cross-check and is not asserted.
- [ ] `P(span)` is monotonically increasing in `p` within noise at each `L`.
- [ ] `code_version` on every row is a real short SHA.

## Invariants

- [ ] **I1 percolation limit** — the `fss_crossing` `p_c` across `L ∈ {128, 256, 512}` within 0.01 of `P_C_LITERATURE` (DEC-014).

## Verification

```bash
python run.py --exp 0
pytest -q tests/test_invariants.py -k i1
python - <<'PY'
import pandas as pd
df = pd.read_parquet("results/exp0.parquet")
assert not df.truncated.any()
print(len(df), df.L.unique(), df.p.nunique())
print(df.groupby(["L","p"]).spanned.mean().unstack(0).loc[0.38:0.44])
print(pd.read_parquet("results/pc_estimates.parquet"))
PY
```

## Definition of done

- [ ] Acceptance criteria all met
- [ ] Named invariants pass locally
- [ ] Every deviation logged in `decisions-log.md`, IDs listed in `decisions:` above
- [ ] Any contract change applied to `project-context.md` in this same PR
- [ ] `status` updated in this file and in `progress-tracker.md`
- [ ] `results/exp0.parquet` and `results/pc_estimates.parquet` committed, with a real `code_version`
- [ ] PR open, linked to the issue — status `in review`
- [ ] Reviewed by `reviewer` and merged — status `done` (human only)

## Notes and risks

- **This is the largest compute job in the project and `project-context.md` §6.3 does not cost it.** From the §6.2 grid at the §6.3 timings: `L=128` ≈ 0.4 core-hours, `L=256` ≈ 6.4, `L=512` ≈ **67.8** — about 75 core-hours total, ~4.7 h across 16 cores, and 2.7× Experiment 1. Run `L ∈ {128, 256}` first, confirm the transition sits near 0.41, and only then commit the `L=512` arm. The bounding-box optimisation from SPEC-03 matters more here than anywhere else.
- **Gate G−1 is cleared** (DEC-001, 14 Sep): the facilitator accepted percolation as the baseline, so §10.1 D5 stands and this spec is unblocked. The constraint it carries still binds — the threshold measured here governs no `STUDY` result (§2 O4) and must never appear in a table alongside a `STUDY` threshold.
- The prototype reproduced a transition at `p ≈ 0.41` at `L=128`. If the full run does not, stop and debug the model — do not proceed into P3 on a broken baseline.
- **Never descoped.** This is the unit's "replicate a known baseline" assessment criterion (roadmap §13).
