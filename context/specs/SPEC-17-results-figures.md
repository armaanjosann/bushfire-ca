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
decisions: [DEC-009, DEC-010, DEC-013]
---

# SPEC-17 — Results figures

## Objective

Every figure the report cites is produced by `figures/make_figures.py` from `results/` alone, by one command, with no notebook anywhere in the chain.

## Context to read

- `workflow-rules.md` — §7 and §9
- `project-context.md` §9, §11 (clustering scale, efficiency), §10.1 D5, §4.1 (`capture_scar`, `ignition_step`)
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
- **Illustrative burn scars**, read from `results/scars_illustrative.npz`, which SPEC-13 captures (DEC-009), for the qualitative-evidence criterion.
- **Space-time view** of the illustrative scars, drawn from the `ignition_step` arrays in `results/scars_illustrative.npz`: for example, cells coloured by ignition step, or front snapshots at a few steps (DEC-013). Cells with `-1` never burned and are drawn as unburnt.
- A caption per figure, stored beside its builder.

**Out of scope**

- The validation figure — SPEC-08 owns it and it stays as-is.
- Running anything, re-estimating any threshold, or re-fitting any tail. Capturing scars is SPEC-13's (DEC-009).
- Writing the report.

## Files

**May touch**

- `figures/make_figures.py`
- `tests/test_figures.py`

**Must not touch**

- `src/` — anything at all
- Any results parquet from SPEC-07 or SPEC-13 through SPEC-16
- `results/scars_illustrative.npz`: read only; SPEC-13 writes it

## Interface contract

As SPEC-08's registry — register new builders in `FIGURES`, do not redesign the dispatch.

## Behaviour

- **`make_figures.py` reads from `results/` and never calls `run_fire`** (§9), with no exception. The scar figure reads `results/scars_illustrative.npz` like any other result; capturing it is SPEC-13's (DEC-009).
- **The `PERCOLATION` threshold must never appear in a table or panel alongside a `STUDY` threshold** (§10.1 D5, §2 O4). If a figure would put them side by side, it is the wrong figure.
- Every figure that shows a treated condition labels the **realised** budget, not the nominal one.
- Each builder raises a clear error when its input parquet is missing, rather than plotting an empty axis.

## Acceptance criteria

- [ ] `python figures/make_figures.py --all` builds every registered figure and exits 0.
- [ ] `grep -nE "run_fire|capture_scar" figures/make_figures.py` returns nothing.
- [ ] Every figure has a caption string beside its builder.
- [ ] No figure places a `PERCOLATION` `p_c` alongside a `STUDY` `p_c`.
- [ ] The efficiency figure divides by `n_treated / n_cells`, verified by reading the code.
- [ ] The SQ4 figure plots both response variables for every condition, so the trade-off is visible or its absence is.
- [ ] The scar figure and the space-time view both read `results/scars_illustrative.npz`, and raise a clear error if it or its `ignition_step` arrays are missing.
- [ ] Re-running `--all` twice produces byte-identical output.
- [ ] A test asserts every registered builder is callable and every one that the report cites is registered.

## Invariants

- [ ] None owned. All eleven must still pass in the full suite at this point.

## Verification

```bash
python figures/make_figures.py --all
pytest -q tests/test_figures.py
grep -nE "run_fire|capture_scar" figures/make_figures.py && echo "FAIL: model call in figures" || echo "ok"
ls -la figures/out/ results/scars_illustrative.npz
```

## Definition of done

- [ ] Acceptance criteria all met
- [ ] Named invariants pass locally
- [ ] Every deviation logged in `decisions-log.md`, IDs listed in `decisions:` above
- [ ] Any contract change applied to `project-context.md` in this same PR
- [ ] `status` updated in this file and in `progress-tracker.md`
- [ ] `figures/out/` **not** committed
- [ ] PR open, linked to the issue — status `in review`
- [ ] Reviewed by `reviewer` and merged — status `done` (human only)

## Notes and risks

- **The SQ4 figure is the one that decides whether this project has an interesting result.** The roadmap expects the arrangement minimising mean burned area is *not* the one minimising `P(settlement reached)`. If the trade-off is there, it is the headline; if it is not, that is still a finding and the figure is what shows it honestly.
- **Figure count is a guess.** The unit's report format and marking rubric have not been released. Eight figure families is sized from roadmap §4.5, not from a stated requirement. If a shorter report is required, cut figures — do not rebuild them; every one reads from committed parquet and can be dropped without touching `results/`.
- The qualitative evidence criterion (roadmap §13) is satisfied by the scars and the space-time view (DEC-013). Do not drop them for time.
- Restyling eight figures at the end of Sprint 3 is the classic way to lose a day. SPEC-08 set the shared style precisely so this spec does not have to.
- The efficiency metric is where the ranking is least obvious (roadmap §4.5), so it is worth plotting with confidence intervals rather than as bare means.
