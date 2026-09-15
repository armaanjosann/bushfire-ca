---
id: SPEC-13
title: Experiment 1 — geometry × budget
status: not started
owner: Aaron
reviewer: Armaan
phase: P5 — Full experiments (Sprint 3)
depends_on: [SPEC-12]
implements: [§6.2 Exp 1, §6.1]
issue:
branch: spec/SPEC-13-experiment-1
pr:
decisions: []
---

# SPEC-13 — Experiment 1: geometry × budget

## Objective

`results/exp1.parquet` exists at full replicates: 12 condition-levels × 7 budgets × 4 fuel densities × 2 wind strengths, `L=256`, R=200, settlement on. This is the dataset the primary research question is answered from.

## Context to read

- `workflow-rules.md`
- `project-context.md` §6.2 Exp 1 and the 12-condition-level note, §6.1 (resolving `p_rel`), §6.3 (compute), §4.4 (which configs are legal), §11
- `checkpoint1-bushfire-ca-roadmap.md` §2 (primary RQ, SQ1, SQ2, SQ4), §4.5

## Scope

**In scope**

- The Experiment 1 grid: conditions `none`, `random`, `patches(k=4,8,16)`, `strips_perp(w=4,8,16)`, `strips_para(w=4,8,16)`, `buffer`; `b ∈ {0, .05, .10, .15, .20, .25, .30}`; `p_rel ∈ {−0.05, 0, +0.05}` plus absolute `p = 0.70`; `kappa ∈ {0, 2}`; `L = 256`; R = 200; `random_cell` ignition; settlement on.
- Running it to `results/exp1.parquet`.
- Wiring `run.py --exp 1`.

**Out of scope**

- Threshold estimation from this data — Exp 2 (SPEC-14) measures per-condition `p_c`, and it uses edge ignition to do so.
- Tail fitting — SPEC-15. Wind sweep beyond `kappa ∈ {0,2}` — SPEC-16.
- Any figure — SPEC-17.
- Changing a geometry — SPEC-09 through SPEC-11 are `done` by now.

## Files

**May touch**

- `src/experiments.py` — the `exp1` grid builder and entry point
- `run.py`
- `results/exp1.parquet`

**Must not touch**

- `src/model.py`, `src/geometries.py`, `src/metrics.py`, `src/analysis.py`, `figures/`
- `context/project-context.md`

## Interface contract

No new interface. Uses `run_configs` (SPEC-05) and `resolve_p` (SPEC-06).

## Behaviour

- **`none` only exists at `b = 0`**, so the effective condition count varies by budget (§6.2). Build the grid accordingly rather than emitting configs that §4.4 will reject.
- `p_rel` values resolve through `resolve_p` at **config-build time**, against the untreated `STUDY` threshold at the matching `kappa` (§6.1). The resolved absolute value goes in `p`, the offset in `p_rel`. Absolute `p = 0.70` is the only hard-coded density, and it carries `p_rel = null`.
- If `pc_estimates.parquet` lacks a needed row, `resolve_p` raises and the grid build fails. That is correct behaviour — do not catch it and substitute a literature value (§6.1).
- Settlement is on for the whole experiment, so `settlement_reached` is populated on every row. That is what SQ4 is answered from.
- `n_treated` is realised, not nominal — the efficiency metric divides by it (§11).

## Acceptance criteria

- [ ] `python run.py --exp 1` produces `results/exp1.parquet` with `truncated == False` on every row.
- [ ] Row count matches the grid the builder declares, and `run_id` is unique.
- [ ] `none` appears only at `b == 0`; every other condition appears at every budget.
- [ ] Every `p_rel` row's `p` equals the resolved threshold plus the offset, to floating tolerance.
- [ ] The `p = 0.70` rows carry `p_rel` as null.
- [ ] `spanned` is null on every row; `reached_edge` and `settlement_reached` are non-null on every row.
- [ ] `n_treated / n_occupied` is within tolerance of `b` for every row (I7 over the frame).
- [ ] Wall time is consistent with §6.3's ~28 core-hours estimate; a large overshoot means the bounding box regressed.

## Invariants

- [ ] None owned. I7 and I10 must hold over this frame.

## Verification

```bash
python run.py --exp 1
python - <<'PY'
import pandas as pd
df = pd.read_parquet("results/exp1.parquet")
assert not df.truncated.any() and df.run_id.is_unique
assert df.spanned.isna().all() and df.settlement_reached.notna().all()
assert set(df.loc[df.condition=="none","b"]) == {0.0}
print(df.groupby(["condition","b"]).burned_fraction.mean().unstack().round(3))
PY
```

## Definition of done

- [ ] Acceptance criteria all met
- [ ] Named invariants pass locally
- [ ] Every deviation logged in `decisions-log.md`, IDs listed in `decisions:` above
- [ ] Any contract change applied to `project-context.md` in this same PR
- [ ] `status` updated in this file and in `progress-tracker.md`
- [ ] `results/exp1.parquet` committed with a real `code_version`
- [ ] PR open, linked to the issue — status `in review`
- [ ] Reviewed by `reviewer` and merged — status `done` (human only)

## Notes and risks

- **Never descoped.** This answers the primary RQ and SQ1, SQ2 and SQ4 (roadmap §2). If Sprint 3 is compressed, Experiments 3 and 4 go first.
- ~28 core-hours, under two hours across 16 cores (§6.3). Start it early enough on the Monday that a failure leaves time to rerun.
- The most likely silent failure is a `p_rel` resolved against the wrong threshold — the `PERCOLATION` one, or a `STUDY` one at the wrong `kappa` (§2 O4). The acceptance check comparing `p` against the resolved value is what catches it, so do not skip it.
- SPEC-14 and SPEC-16 both depend on this being merged. It is the widest point of the dependency graph.
