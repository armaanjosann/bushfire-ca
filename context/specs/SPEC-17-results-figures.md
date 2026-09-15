---
id: SPEC-17
title: Results figures
status: not started
owner: Armaan
reviewer: Aaron
phase: P6 — Delivery (Sprint 3 → 4)
depends_on: [SPEC-13, SPEC-14, SPEC-15, SPEC-16]
implements: [§9, §11, §10.1 D5]
issue:
branch: spec/SPEC-17-results-figures
pr:
decisions: []
---

# SPEC-17 — Results figures

## Objective

Every figure the report cites is produced by `figures/make_figures.py` from `results/` alone, by one command, with no notebook anywhere in the chain.

## Context to read

- `workflow-rules.md` — §7 and §9
- `project-context.md` §9, §11 (clustering scale, efficiency), §10.1 D5, §4.1 (`capture_scar`)
- `checkpoint1-bushfire-ca-roadmap.md` §2 (the RQ and four SQs), §4.5 (response variables), §13 (assessment criteria)

## Scope

**In scope**, building on SPEC-08's registry and shared style:

- **Clustering-scale curve** — burned fraction against clustering scale (`random` = 1, `patches` = `k`, `strips` = `w`), by budget. The primary analysis axis (§11).
- **Efficiency by condition** — `(burned_fraction[b=0] − burned_fraction[b]) / (n_treated / n_cells)` (§11). Divides by realised `n_treated`, never nominal `b`.
- **Threshold shift** — measured `p_c` per condition with confidence intervals, from `pc_estimates.parquet`.
- **Burn-size distributions** — log-log survival curves with the fitted exponent and cutoff overlaid, from `tail_fits.parquet`.
- **SQ4 trade-off** — mean burned area against `P(settlement reached)`, one point per condition. This is where the trade-off either appears or does not.
- **Wind interaction** — `kappa` × condition, from Experiment 3.
- **Sensitivity panel** — `f_treat` × `beta`, from Experiment 4.
- **Illustrative burn scars** — a hand-picked handful of configs, plus a space-time view, for the qualitative-evidence criterion.
- A caption per figure, stored beside its builder.

**Out of scope**

- The validation figure — SPEC-08 owns it and it stays as-is.
- Running anything, re-estimating any threshold, or re-fitting any tail.
- Writing the report.

## Files

**May touch**

- `figures/make_figures.py`
- `results/scars_illustrative.npz` — the hand-picked scars only
- `tests/test_figures.py`

**Must not touch**

- `src/` — anything at all
- Any results parquet from SPEC-07 or SPEC-13 through SPEC-16

## Interface contract

As SPEC-08's registry — register new builders in `FIGURES`, do not redesign the dispatch.

## Behaviour

- **`make_figures.py` reads from `results/` and never calls `run_fire`** (§9). The one exception is generating the illustrative scars, and even that must be a separate, explicitly-invoked step that writes `results/scars_illustrative.npz` — the figure builder then reads the npz like any other result.
- **Scars are captured for a hand-picked handful of configurations only**, never for a sweep (§4.1). Name the configs explicitly in code.
- **The `PERCOLATION` threshold must never appear in a table or panel alongside a `STUDY` threshold** (§10.1 D5, §2 O4). If a figure would put them side by side, it is the wrong figure.
- Every figure that shows a treated condition labels the **realised** budget, not the nominal one.
- Each builder raises a clear error when its input parquet is missing, rather than plotting an empty axis.

## Acceptance criteria

- [ ] `python figures/make_figures.py --all` builds every registered figure and exits 0.
- [ ] `grep -n "run_fire" figures/make_figures.py` returns nothing outside the explicitly-separated scar-capture step.
- [ ] Every figure has a caption string beside its builder.
- [ ] No figure places a `PERCOLATION` `p_c` alongside a `STUDY` `p_c`.
- [ ] The efficiency figure divides by `n_treated / n_cells`, verified by reading the code.
- [ ] The SQ4 figure plots both response variables for every condition, so the trade-off is visible or its absence is.
- [ ] `results/scars_illustrative.npz` is under 5 MB and contains only the named configs.
- [ ] Re-running `--all` twice produces byte-identical output.
- [ ] A test asserts every registered builder is callable and every one that the report cites is registered.

## Invariants

- [ ] None owned. All eleven must still pass in the full suite at this point.

## Verification

```bash
python figures/make_figures.py --all
pytest -q tests/test_figures.py
grep -n "run_fire" figures/make_figures.py
ls -la figures/out/ results/scars_illustrative.npz
```

## Definition of done

- [ ] Acceptance criteria all met
- [ ] Named invariants pass locally
- [ ] Every deviation logged in `decisions-log.md`, IDs listed in `decisions:` above
- [ ] Any contract change applied to `project-context.md` in this same PR
- [ ] `status` updated in this file and in `progress-tracker.md`
- [ ] `results/scars_illustrative.npz` committed; `figures/out/` **not** committed
- [ ] PR open, linked to the issue — status `in review`
- [ ] Reviewed by `reviewer` and merged — status `done` (human only)

## Notes and risks

- **The SQ4 figure is the one that decides whether this project has an interesting result.** The roadmap expects the arrangement minimising mean burned area is *not* the one minimising `P(settlement reached)`. If the trade-off is there, it is the headline; if it is not, that is still a finding and the figure is what shows it honestly.
- **Figure count is a guess.** The unit's report format and marking rubric have not been released. Eight figure families is sized from roadmap §4.5, not from a stated requirement. If a shorter report is required, cut figures — do not rebuild them; every one reads from committed parquet and can be dropped without touching `results/`.
- The qualitative evidence criterion (roadmap §13) is satisfied by the scars and the space-time view, and by nothing else in the figure set. Do not drop them for time.
- Restyling eight figures at the end of Sprint 3 is the classic way to lose a day. SPEC-08 set the shared style precisely so this spec does not have to.
- The efficiency metric is where the ranking is least obvious (roadmap §4.5), so it is worth plotting with confidence intervals rather than as bare means.
