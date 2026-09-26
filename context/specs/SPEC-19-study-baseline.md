---
id: SPEC-19
title: Experiment 0b — untreated STUDY baseline thresholds
status: not started
owner: Aaron
reviewer: Armaan
phase: P2 — Harness and validation (Sprint 1 → 2)
depends_on: [SPEC-05, SPEC-06]
implements: [§6.1, §6.2 Exp 0b]
issue:
branch: spec/SPEC-19-study-baseline
pr:
decisions: [DEC-011]
---

# SPEC-19 — Experiment 0b: untreated `STUDY` baseline thresholds

## Objective

`results/pc_estimates.parquet` holds a measured untreated `STUDY` threshold (`condition="none"`, `b=0`) at each of `kappa ∈ {0, 1, 2, 4}`. Every threshold-relative grid can then resolve `p_rel`: the §10.2 O1 pilot, Experiments 1 and 3, and the fixed `p` of Experiment 4. Without this spec, SPEC-12 onward cannot build a grid (DEC-003, resolved by DEC-011).

## Context to read

- `workflow-rules.md`
- `project-context.md` §6.1 (governing threshold, **edge-ignition wind convention**), §6.2 Exp 0b and the note on edge ignition, §6.3 (cost), §3.4 (wind kernel), §3.5 (edge ignition), §4.6, §2 O4
- SPEC-06 — `estimate_pc`, `write_pc_estimates`, `resolve_p` and the row identity (DEC-004)

## Scope

**In scope**

- **Pre-pass:** `STUDY`, `condition="none"`, `b=0`, `phi=-π/2`, edge ignition, `L=128`, R=100, `p ∈ [0.30, 0.90]` step 0.01, at each `kappa`, written to `results/exp0b_prepass.parquet`. From it, each `kappa`'s sweep centre is the smallest `p` at which `P(span) ≥ 0.5`, rounded to the nearest 0.005. The builder derives the centre deterministically from that file.
- **Main sweep:** the same settings at each `kappa ∈ {0, 1, 2, 4}`. 21 points, centre ± 0.05 at step 0.005; `L ∈ {128, 256, 512}`; R=500. Written to `results/exp0b.parquet`.
- Feeding each `kappa`'s frame to `estimate_pc` and appending rows to `pc_estimates.parquet` with `regime="STUDY"`, `condition="none"`, `b=0`, that `kappa`.
- Wiring `run.py --exp 0b`. Add a `run_exp0b` entry point and insert `"0b"` into `EXPERIMENTS` directly after `"0"`, so `--exp all` runs it before Experiment 1.

**Out of scope**

- Any treated condition. Treated thresholds are Experiment 2 (SPEC-14).
- The `PERCOLATION` threshold (SPEC-07).
- Figures. A baseline-threshold panel, if wanted, belongs to SPEC-17.
- Changing the estimator or resolver (SPEC-06).

## Files

**May touch**

- `src/experiments.py` — the `exp0b` pre-pass and sweep builders and the `run_exp0b` entry point only
- `run.py` — the `"0b"` entry only
- `results/exp0b_prepass.parquet`, `results/exp0b.parquet`, `results/pc_estimates.parquet`
- `tests/test_exp0b.py`

**Must not touch**

- `src/model.py`, `src/geometries.py`, `src/metrics.py`, `src/analysis.py`, `figures/`
- `tests/test_invariants.py`

## Interface contract

No new public interface. Uses `run_configs` (SPEC-05) and `estimate_pc` / `write_pc_estimates` (SPEC-06) as they stand.

## Behaviour

- `STUDY` settings throughout: `beta=0.8`, `diagonal_factor=True`, `f_treat=0.2`, `tau=1`, no settlement. Only `ignition="edge"` and `phi=-π/2` differ from the `STUDY` defaults.
- **`phi = -π/2` is the convention in §6.1, not a choice for this spec to revisit.** The wind blows from row 0 towards row `L-1`, so the ignited edge is upwind. A 90° lattice rotation is an exact symmetry of the rule, so the threshold equals the one at `phi = 0`, which the `random_cell` experiments use. The same `phi` is used at `kappa = 0`, where it has no physical effect, so every arm is built the same way.
- The sweep range is declared by the builder, never widened silently. If a `kappa`'s crossing falls outside its range, re-centre on the observed crossing and rerun that arm. Do not extrapolate.
- `P_C_LITERATURE` appears nowhere in this spec's code (§6.1). These thresholds are `STUDY` values and are never tabulated alongside the `PERCOLATION` one (§10.1 D5).

## Acceptance criteria

- [ ] `python run.py --exp 0b` writes `results/exp0b_prepass.parquet` and `results/exp0b.parquet`, with `truncated == False` on every row of both.
- [ ] `results/exp0b.parquet` has 126,000 rows (4 `kappa` × 21 `p` × 3 `L` × 500), with unique `run_id`.
- [ ] Every row has `regime == "STUDY"`, `condition == "none"`, `b == 0`, `beta == 0.8`, `diagonal_factor == True`, `ignition == "edge"`, `settlement == False`, and `phi == -π/2`.
- [ ] `spanned` is non-null and `reached_edge` is null on every row.
- [ ] For each `kappa`, `pc_estimates.parquet` gains one `fss_crossing` row with `L` null and three `var_peak` rows (DEC-004). `resolve_p(0.0, regime="STUDY", condition="none", b=0.0, kappa=k)` returns without raising for every `k ∈ {0, 1, 2, 4}`.
- [ ] Each `kappa`'s crossing lies strictly inside its declared sweep range.
- [ ] `tests/test_exp0b.py` asserts that `wind_weights(kappa, -π/2, True)` equals `wind_weights(kappa, 0, True)` with the 90° clockwise rotation permutation of `NEIGHBOURS` applied, for `kappa ∈ {1, 2, 4}`. This is the exact symmetry §6.1 relies on.
- [ ] The PR body lists the four sweep centres and the four measured thresholds with stderr.

## Invariants

- [ ] None owned. I10 must hold over both new frames.

## Verification

```bash
python run.py --exp 0b
pytest -q tests/test_exp0b.py
python - <<'PY'
import pandas as pd
df = pd.read_parquet("results/exp0b.parquet")
assert not df.truncated.any() and df.run_id.is_unique and len(df) == 126_000
pc = pd.read_parquet("results/pc_estimates.parquet")
print(pc[(pc.regime == "STUDY") & (pc.condition == "none")].sort_values(["kappa", "method"]))
from src.analysis import resolve_p
for k in (0, 1, 2, 4):
    print(k, resolve_p(0.0, regime="STUDY", condition="none", b=0.0, kappa=k))
PY
```

## Definition of done

- [ ] Acceptance criteria all met
- [ ] Named invariants pass locally
- [ ] Every deviation logged in `decisions-log.md`, IDs listed in `decisions:` above
- [ ] Any contract change applied to `project-context.md` in this same PR
- [ ] `status` updated in this file and in `progress-tracker.md`
- [ ] `results/exp0b_prepass.parquet`, `results/exp0b.parquet` and the updated `pc_estimates.parquet` committed with a real `code_version`
- [ ] PR open, linked to the issue — status `in review`
- [ ] Reviewed by `reviewer` and merged — status `done` (human only)

## Notes and risks

- **Compute:** about 26 core-hours per `kappa` arm, about 103 core-hours in total, about 6.5 hours across 16 cores (§6.3). It is dominated by `L=512`, as in SPEC-07. Run all four arms at `L ∈ {128, 256}` first, check that each crossing sits inside its range, and only then commit the `L=512` arms. This is an overnight run in the same week as SPEC-07's, so schedule the two against each other.
- This spec sits on the critical path. SPEC-12, and through it SPEC-13 to 16, cannot build a grid until it merges. Start it the moment SPEC-06 merges.
- At `kappa = 4` some directions carry very low ignition probability, and the threshold may sit high. If the pre-pass shows no `P(span) ≥ 0.5` below `p = 0.90`, stop and raise a DEC rather than widen past `p = 1`.
- Experiment 2 (SPEC-14) reuses this spec's `kappa = 0` arm as its untreated reference. Its treated arms use identical settings apart from condition and `b`, so do not change any `phi`, `R` or `L` choice here without a DEC.
