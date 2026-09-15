---
id: SPEC-16
title: Experiments 3 and 4, and the lattice frame-invariance check
status: not started
owner: Aaron
reviewer: Armaan
phase: P5 — Full experiments (Sprint 3)
depends_on: [SPEC-13]
implements: [§6.2 Exp 3, §6.2 Exp 4, §10.1 D3, §7 I11]
issue:
branch: spec/SPEC-16-experiments-3-4
pr:
decisions: []
---

# SPEC-16 — Experiments 3 and 4, and frame invariance

## Objective

`results/exp3.parquet` and `results/exp4.parquet` exist, and there is a measured answer to whether axis-aligned strips couple to the lattice in a way a diagonal wind does not.

## Context to read

- `workflow-rules.md`
- `project-context.md` §6.2 Exp 3 and Exp 4, §10.1 D3 (why `phi` is not swept and what replaces it), §7 I11, §6.1
- `checkpoint1-bushfire-ca-roadmap.md` §2 SQ1, §5 Exp 3 and Exp 4

## Scope

**In scope**

- **Experiment 3:** `STUDY`, `kappa ∈ {0, 1, 2, 4}` × 7 conditions at `b = 0.15`, `p_rel = +0.05`, `L = 256`, R = 200, `random_cell` ignition, settlement on.
- **Experiment 4:** `STUDY`, `f_treat ∈ {0, .2, .4}` × `beta ∈ {.7, .8, .9}`, reduced condition set, `random_cell`, settlement on.
- **I11:** at `b = 0.15`, `p_rel = +0.05`, `kappa = 2`, `L = 256`, R = 200, compare the `strips_perp − strips_para` gap at `phi = 0` against `phi = π/4` with the geometry rotated to match.
- Wiring `run.py --exp 3` and `--exp 4`.

**Out of scope**

- Sweeping `phi` as an experimental dimension — §10.1 D3 resolved this to a single verification check. Do not add an axis.
- Figures — SPEC-17.
- Any change to a geometry generator to support rotation. If `strips_perp` at `phi = π/4` does not already produce bands perpendicular to the wind, that is a SPEC-10 defect — **raise a DEC**, do not patch it here.

## Files

**May touch**

- `src/experiments.py` — the `exp3`, `exp4` and I11 grid builders
- `run.py`
- `results/exp3.parquet`, `results/exp4.parquet`, `results/i11_frame.parquet`
- `tests/test_invariants.py` — only `test_i11`

**Must not touch**

- `src/model.py`, `src/geometries.py`, `src/metrics.py`, `src/analysis.py`, `figures/`
- Any invariant test other than I11

## Interface contract

No new interface. Uses `run_configs` (SPEC-05) and `resolve_p` (SPEC-06).

## Behaviour

- Experiment 3 is SQ1 in full: is the ranking of treatment arrangements wind-dependent? Settlement is on, so both the landscape-scale and asset-scale responses are available across `kappa`.
- Experiment 4 exists to show the conclusions are not artefacts of fixed parameter choices. Keep the condition set reduced — it is a sensitivity check, not a second main experiment.
- `p_rel = +0.05` resolves through `resolve_p` against the untreated `STUDY` threshold **at the matching `kappa`** (§6.1, §2 O4). Experiment 3 sweeps `kappa`, so this is four different thresholds, not one. That is the single most likely error in this spec.
- **I11 has two reportable outcomes and neither costs an axis** (§10.1 D3): overlapping confidence intervals on the two gaps ⟹ one line in Methods stating the frame-invariance check passed; non-overlapping ⟹ a *measured* lattice artefact with a magnitude attached, which goes in Limitations. Write the test to report the magnitude either way, not merely to pass.

## Acceptance criteria

- [ ] `results/exp3.parquet` and `results/exp4.parquet` exist, `truncated == False`, `run_id` unique.
- [ ] Experiment 3 rows at each `kappa` resolved `p` against that `kappa`'s threshold — verified by comparing `p` to the `pc_estimates.parquet` row per `kappa`.
- [ ] Experiment 3 covers all four `kappa` values × seven conditions at `b = 0.15`.
- [ ] Experiment 4 covers the full `f_treat × beta` cross at the declared reduced condition set.
- [ ] `results/i11_frame.parquet` exists with both `phi` arms at R = 200.
- [ ] `test_i11` reports the two gaps, their confidence intervals, and whether they overlap — and the PR body states which outcome was observed.
- [ ] `settlement_reached` is non-null throughout both experiments.

## Invariants

- [ ] **I11 lattice frame invariance** — the `strips_perp − strips_para` gap does not depend on whether the wind is axis-aligned; measured, with the magnitude reported either way.

## Verification

```bash
python run.py --exp 3
python run.py --exp 4
pytest -q tests/test_invariants.py -k i11
python - <<'PY'
import pandas as pd
d3 = pd.read_parquet("results/exp3.parquet")
print(d3.groupby(["kappa","condition"]).burned_fraction.mean().unstack().round(3))
print(d3.groupby(["kappa","condition"]).settlement_reached.mean().unstack().round(3))
PY
```

## Definition of done

- [ ] Acceptance criteria all met
- [ ] Named invariants pass locally
- [ ] Every deviation logged in `decisions-log.md`, IDs listed in `decisions:` above
- [ ] Any contract change applied to `project-context.md` in this same PR
- [ ] `status` updated in this file and in `progress-tracker.md`
- [ ] Both parquets committed with a real `code_version`
- [ ] PR open, linked to the issue — status `in review`
- [ ] Reviewed by `reviewer` and merged — status `done` (human only)

## Notes and risks

- **These are the first two items in the descope order** — Experiment 4 first, then Experiment 3. Both are bundled here because, once SPEC-05's harness and SPEC-06's resolver exist, each is a grid definition and a run. If the Thursday sync finds this spec still in progress, drop Experiment 4 rather than debugging into the following week (roadmap §8).
- Experiment 4 is described in the roadmap as "half a day, high marks-per-hour". It directly serves the "interpret critically, identify limitations" criterion, so it is cheap marks — but only if the rest of Sprint 3 landed.
- §10.1 D3's reasoning is worth keeping in view: the lattice has 4-fold symmetry and the strips are axis-aligned, so an axis-aligned wind can in principle couple to the lattice in a way a diagonal wind does not. That is a soundness question about the implementation, not a research question, which is exactly why it is one check rather than an experimental dimension.
