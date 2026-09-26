# progress-tracker.md

Status of every spec. One row per spec, sorted by ID. The spec set and its phases come from `spec-plan.md`; that file is planning and goes stale on purpose, this one is live.

**How to edit.** Change only your own spec's row. Keep it to a single line — the row format is deliberately fixed so that two people editing different rows do not conflict. Do not reflow, re-sort or reformat the table.

Status here must match the `status:` field in the spec's frontmatter, and both are updated in the same commit. **If they disagree, the frontmatter is correct and this file is stale.** Column names match the spec frontmatter fields, so this table can be generated from `context/specs/*.md` later if maintaining it by hand becomes annoying.

## Status legend

Full definitions in `workflow-rules.md` §4.

| Status | Means |
|---|---|
| `not started` | Spec written, no work begun |
| `in progress` | Branch exists, implementation under way |
| `in review` | PR open, named invariants pass locally |
| `done` | Reviewed by the other team member and merged to `main` |
| `blocked` | Stopped under `workflow-rules.md` §6 — needs a decision from us |

**Agents never set `done`.** Only the reviewer, after merge.

## Specs

| Spec | Title | Owner | Phase | Status | Depends on | PR | Decisions |
|---|---|---|---|---|---|---|---|
| SPEC-01 | Repo skeleton, entry point, model contracts | Aaron | P0 — Foundation | `in review` | — |  | DEC-002 |
| SPEC-02 | Lattice initialisation, ignition, settlement | Aaron | P0 — Foundation | `in review` | SPEC-01 |  | DEC-007, DEC-008 |
| SPEC-03 | Step function and `run_fire` | Aaron | P1 — Model core | `in review` | SPEC-01, SPEC-02 |  | DEC-006, DEC-013 |
| SPEC-04 | Metrics and scar statistics | Armaan | P1 — Model core | `not started` | SPEC-03 |  | DEC-006, DEC-007 |
| SPEC-05 | Experiment harness | Aaron | P2 — Harness & validation | `not started` | SPEC-03, SPEC-04 |  | DEC-006, DEC-009 |
| SPEC-06 | `p_c` estimation, FSS, `p_rel` resolver | Armaan | P2 — Harness & validation | `not started` | SPEC-05 |  | DEC-004 |
| SPEC-07 | Experiment 0: percolation validation | Aaron | P2 — Harness & validation | `not started` | SPEC-05, SPEC-06 |  | DEC-001, DEC-004, DEC-014 |
| SPEC-08 | Figure foundation, validation figure | Armaan | P2 — Harness & validation | `not started` | SPEC-07 |  | DEC-001, DEC-016, DEC-017 |
| SPEC-09 | Geometry framework, `none`, `random` | Armaan | P3 — Treatment geometries | `in progress` | SPEC-02 |  | DEC-007, DEC-008 |
| SPEC-10 | `patches`, `strips_perp`, `strips_para` | Armaan | P3 — Treatment geometries | `not started` | SPEC-09 |  | DEC-007, DEC-008 |
| SPEC-11 | `buffer` | Armaan | P3 — Treatment geometries | `not started` | SPEC-02, SPEC-09 |  | DEC-007 |
| SPEC-12 | Settlement pilot, coarse Exp 1, freeze | Aaron | P4 — Parameter freeze | `not started` | SPEC-05, SPEC-06, SPEC-10, SPEC-11, SPEC-19 |  | DEC-003, DEC-007, DEC-011, DEC-015 |
| SPEC-13 | Experiment 1: geometry × budget | Aaron | P5 — Full experiments | `not started` | SPEC-12 |  | DEC-003, DEC-009, DEC-011, DEC-013, DEC-015 |
| SPEC-14 | Experiment 2: threshold shift | Armaan | P5 — Full experiments | `not started` | SPEC-06, SPEC-13, SPEC-19 |  | DEC-003, DEC-004, DEC-005, DEC-011, DEC-012 |
| SPEC-15 | Tail fitting, Experiment 2b | Armaan | P5 — Full experiments | `not started` | SPEC-14, SPEC-19 |  | DEC-005, DEC-012 |
| SPEC-16 | Experiments 3 and 4, frame invariance | Aaron | P5 — Full experiments | `not started` | SPEC-13 |  | DEC-003, DEC-008, DEC-011, DEC-015 |
| SPEC-17 | Results figures | Armaan | P6 — Delivery | `not started` | SPEC-13, SPEC-14, SPEC-15, SPEC-16 |  | DEC-009, DEC-010, DEC-013, DEC-016, DEC-017 |
| SPEC-18 | Reproducibility gate | Aaron | P6 — Delivery | `not started` | SPEC-08, SPEC-17, SPEC-20, SPEC-21 |  | DEC-016, DEC-017 |
| SPEC-19 | Experiment 0b: untreated STUDY baseline thresholds | Aaron | P2 — Harness & validation | `not started` | SPEC-05, SPEC-06 |  | DEC-011 |
| SPEC-20 | Notebook foundation, model-and-validation notebook | Aaron | P2 — Harness & validation | `not started` | SPEC-08 |  | DEC-016, DEC-017, DEC-018 |
| SPEC-21 | Results notebooks: geometries, thresholds, tails | Armaan | P6 — Delivery | `not started` | SPEC-17, SPEC-20 |  | DEC-016, DEC-017 |

## Blocked

Anything `blocked`, with the open DEC entry behind it. First item at the next sync.

| Spec | Blocked since | DEC | Waiting on |
|---|---|---|---|
| — | | | Nothing blocked. DEC-003, DEC-005 and DEC-010 were resolved by DEC-011, DEC-012 and DEC-013 on 2026-09-15. |

## Phase summary

Optional roll-up, updated at the Monday and Thursday syncs.

| Phase | Specs | Done | In review | In progress | Blocked |
|---|---|---|---|---|---|
| P0 — Foundation | 2 | 0 | 0 | 0 | 0 |
| P1 — Model core | 2 | 0 | 0 | 0 | 0 |
| P2 — Harness & validation | 5 | 0 | 0 | 0 | 0 |
| P3 — Treatment geometries | 3 | 0 | 0 | 0 | 0 |
| P4 — Parameter freeze | 1 | 0 | 0 | 0 | 0 |
| P5 — Full experiments | 4 | 0 | 0 | 0 | 0 |
| P6 — Delivery | 2 | 0 | 0 | 0 | 0 |
| **Total** | **19** | **0** | **0** | **0** | **0** |
