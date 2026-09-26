---
id: SPEC-21
title: Results notebooks — geometries, thresholds and tails
status: not started
owner: Armaan
reviewer: Aaron
phase: P6 — Delivery (Sprint 4)
depends_on: [SPEC-17, SPEC-20]
implements: [§9, §11]
issue:
branch: spec/SPEC-21-results-notebooks
pr:
decisions: [DEC-016, DEC-017]
---

# SPEC-21 — Results notebooks: geometries, thresholds and tails

## Objective

`notebooks/02-treatment-geometries.ipynb` and `notebooks/03-thresholds-and-tails.ipynb` present the project's results as a coherent argument — figure, interpretation, and the question each one answers — executed top to bottom with outputs committed.

## Context to read

- `workflow-rules.md` — §7, §9
- `project-context.md` §9 (layout and the notebook clause), §11 (clustering scale, efficiency), §10.1 D5
- `checkpoint1-bushfire-ca-roadmap.md` §2 (the RQ and four SQs), §4.5 (response variables), §13
- SPEC-08 and SPEC-17 — the `FIGURES` registry, which supplies every figure here
- SPEC-20 — the notebook conventions this spec follows
- `decisions-log.md` — DEC-016, DEC-017

## Scope

**In scope**

- **`02-treatment-geometries.ipynb`** — the contribution:
  - a visual gallery of every condition at a fixed budget, so a reader sees what `patches`, `strips_perp`, `strips_para`, `buffer` and `random` actually look like on the lattice;
  - the clustering-scale curve (§11), with the reading of it in prose;
  - efficiency by condition, stating that it divides by realised `n_treated`;
  - the SQ4 trade-off — mean burned area against `P(settlement reached)`;
  - illustrative scars and the space-time view.
- **`03-thresholds-and-tails.ipynb`** — the physics:
  - the threshold shift per condition with confidence intervals, and the §10.1 D5 statement that `PERCOLATION` and `STUDY` thresholds are not comparable;
  - burn-size distributions log-log with fitted exponent **and** cutoff, and what the cutoff means for SQ3;
  - the Exp 3 wind interaction and the Exp 4 sensitivity panel;
  - the I11 frame-invariance result, either way it came out.
- A closing cell in `03` stating the limitations the report will carry.

**Out of scope**

- Writing or registering any figure builder — SPEC-17 owns them. A missing figure is raised against SPEC-17, not drawn here.
- Running any experiment, re-estimating a threshold, re-fitting a tail, or capturing a scar.
- The model walkthrough and the validation figure — SPEC-20 owns those.
- Writing the report.

## Files

**May touch**

- `notebooks/02-treatment-geometries.ipynb`
- `notebooks/03-thresholds-and-tails.ipynb`
- `notebooks/README.md` — the running order only
- `context/decisions-log.md`

**Must not touch**

- `src/` — anything at all
- `figures/make_figures.py`
- `results/` — read-only
- `notebooks/01-model-and-validation.ipynb`

## Interface contract

As SPEC-20: consume `FIGURES` from `figures.make_figures`. Register nothing, redesign nothing.

## Behaviour

- **Neither notebook calls `run_fire`.** The live-demonstration exception (DEC-018) is scoped to SPEC-20's notebook `01` and does not extend here. The geometry gallery calls `geometries.generate` on a lattice, which is not a simulation and is permitted.
- Every figure comes from `FIGURES`. Every number quoted in prose is read from `results/` in a visible cell.
- **A `PERCOLATION` threshold never appears beside a `STUDY` threshold** (§10.1 D5), in a figure, a table or a sentence.
- Every treated condition is labelled by its **realised** budget, not the nominal one.
- Each figure is followed by prose saying what it shows and which research question it bears on. A figure with no interpretation beneath it is not finished.
- Both notebooks are committed with outputs stored, executed top to bottom, execution counts sequential (DEC-017).
- Where a result is null or ambiguous, it is reported as such. An honest negative on SQ4 is a finding; a figure quietly dropped is not.

## Acceptance criteria

- [ ] Both notebooks exist, committed with outputs stored.
- [ ] Restart-and-run-all from a clean kernel completes with no error, after `python run.py --exp all`.
- [ ] Execution counts are sequential from 1 in each notebook.
- [ ] `grep -c run_fire` over both notebooks returns 0.
- [ ] Every figure comes from `FIGURES`, except the geometry gallery.
- [ ] Every figure is followed by at least one markdown cell of interpretation.
- [ ] No cell or markdown text places a `PERCOLATION` `p_c` beside a `STUDY` `p_c`.
- [ ] Every figure the report cites appears in one of the three notebooks.
- [ ] `notebooks/README.md` lists all three notebooks in running order with their prerequisite commands.

## Invariants

- [ ] None owned. All eleven must still pass in the full suite at this point.

## Verification

```bash
python run.py --exp all
for nb in notebooks/02-treatment-geometries.ipynb notebooks/03-thresholds-and-tails.ipynb; do
  jupyter nbconvert --to notebook --execute --inplace "$nb" || exit 1
  grep -c "run_fire" "$nb" | grep -qx 0 || { echo "FAIL: $nb simulates"; exit 1; }
done
python - <<'PY'
import json
for p in ["notebooks/02-treatment-geometries.ipynb", "notebooks/03-thresholds-and-tails.ipynb"]:
    nb = json.load(open(p))
    codes = [c for c in nb["cells"] if c["cell_type"] == "code"]
    ns = [c["execution_count"] for c in codes]
    assert ns == list(range(1, len(ns) + 1)), f"{p}: non-sequential {ns}"
    assert any(c["outputs"] for c in codes), f"{p}: no outputs stored"
print("ok")
PY
```

## Definition of done

- [ ] Acceptance criteria all met
- [ ] Every deviation logged in `decisions-log.md`, IDs listed in `decisions:` above
- [ ] `status` updated in this file and in `progress-tracker.md`
- [ ] PR open, linked to the issue — status `in review`
- [ ] Reviewed by `reviewer` and merged — status `done` (human only)

## Notes and risks

- **This is the individual code-understanding evidence for the analysis side**, the mirror of SPEC-20. Whoever writes the interpretation here is the one who will be asked about thresholds and tail fits at the demonstration.
- **Sprint 4 is three days.** These notebooks depend on SPEC-17, which depends on all four experiment specs, so they are the last thing in the project and have no slack behind them. Scaffold both files with their markdown headings and empty cells during Sprint 3, so Sprint 4 is filling in figures rather than deciding structure.
- If the report must shrink, **cut figures from the report, not from the notebooks.** The five-page limit is on prose; the notebooks are where the full evidence lives, and the rubric assesses them separately.
- Splitting the results across two notebooks rather than one is deliberate: `02` is the contribution and `03` is the physics, which matches the report's structure and lets a marker find the novel work without reading the whole analysis.
