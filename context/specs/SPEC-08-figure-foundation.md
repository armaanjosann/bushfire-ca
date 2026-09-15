---
id: SPEC-08
title: Figure foundation and the validation figure
status: not started
owner: Armaan
reviewer: Aaron
phase: P2 — Harness and validation (Sprint 1)
depends_on: [SPEC-07]
implements: [§9, §10.1 D5]
issue:
branch: spec/SPEC-08-figure-foundation
pr:
decisions: [DEC-001]
---

# SPEC-08 — Figure foundation and the validation figure

## Objective

`figures/make_figures.py` exists with its shared style and dispatch, and produces the validation figure: `P(span)` vs `p` across `L ∈ {128, 256, 512}` with the finite-size-scaling crossing and `P_C_LITERATURE` marked.

## Context to read

- `workflow-rules.md` — especially §7 (do not commit generated figures unless asked) and §9
- `project-context.md` §9 (`make_figures.py` reads from `results/` and nothing else), §10.1 D5, §6.1, §4.6
- `checkpoint1-bushfire-ca-roadmap.md` §5 Exp 0, §13

## Scope

**In scope**

- `figures/make_figures.py`: shared matplotlib style, a figure registry, and a CLI selecting one figure or all.
- The validation figure, as the objective describes.
- A short caption string per figure, stored next to the figure function, so the report and the code cannot drift.

**Out of scope**

- Every results figure — SPEC-17.
- Running anything. `make_figures.py` **must never call `run_fire`** (§9).
- Re-estimating `p_c` — read it from `results/pc_estimates.parquet`.

## Files

**May touch**

- `figures/make_figures.py`
- `tests/test_figures.py`

**Must not touch**

- `src/` — anything at all
- `results/` — read-only from here

## Interface contract

New, and SPEC-17 is written against it:

```python
FIGURES: dict[str, Callable[[], "Figure"]]        # name -> builder
def build(name: str, outdir: str = "figures/out") -> str: ...
def build_all(outdir: str = "figures/out") -> list[str]: ...
```

## Behaviour

- Every builder reads from `results/` and returns a figure. No simulation, no `run_fire`, no recomputation of a threshold.
- The validation figure marks both the measured FSS crossing and `P_C_LITERATURE = 0.407`, and its caption states that the latter is a validation target only.
- **The `PERCOLATION` threshold must never appear in a table or panel alongside a `STUDY` threshold** (§10.1 D5, §2 O4). The report states once that the two are different by construction and not comparable; this figure is where that statement is anchored.
- Output goes to `figures/out/`, which is gitignored. Figures are not committed unless a spec asks (`workflow-rules.md` §7).

## Acceptance criteria

- [ ] `python figures/make_figures.py --figure validation` writes a file and exits 0.
- [ ] `grep -n "run_fire" figures/make_figures.py` returns nothing.
- [ ] The figure shows three `L` curves, the crossing, and the literature marker, each labelled.
- [ ] The builder raises a clear error if `results/exp0.parquet` or `results/pc_estimates.parquet` is missing, rather than producing an empty plot.
- [ ] Re-running the builder twice produces byte-identical output.
- [ ] A test asserts the registry is non-empty and every registered builder is callable.

## Invariants

- [ ] None owned.

## Verification

```bash
python figures/make_figures.py --figure validation
grep -n "run_fire" figures/make_figures.py && echo "FAIL: figures must not simulate" || echo "ok"
pytest -q tests/test_figures.py
```

## Definition of done

- [ ] Acceptance criteria all met
- [ ] Named invariants pass locally
- [ ] Every deviation logged in `decisions-log.md`, IDs listed in `decisions:` above
- [ ] Any contract change applied to `project-context.md` in this same PR
- [ ] `status` updated in this file and in `progress-tracker.md`
- [ ] PR open, linked to the issue — status `in review`
- [ ] Reviewed by `reviewer` and merged — status `done` (human only)

## Notes and risks

- **Gate G0 closes here.** Sprint 1 is done when this figure exists. If it does not by the Sunday sync, P3 starts anyway but the validation claim is unproven and everything downstream is provisional.
- Gate G−1 is cleared (DEC-001): the facilitator accepted percolation as the baseline, so this figure is the agreed replication deliverable rather than a provisional one.
- Deciding the shared style now is worth an hour — SPEC-17 produces eight or more figures and restyling them at the end of Sprint 3 is exactly the kind of work that gets skipped and shows.
- This figure is the unit's replication deliverable made visible (roadmap §13). It is the one figure that is certain to be in the report.
