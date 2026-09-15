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
| SPEC-01 | Repo skeleton, entry point, model contracts | Aaron | P0 — Foundation | `not started` | — |  |  |
| SPEC-02 | Lattice initialisation, ignition, settlement | Aaron | P0 — Foundation | `not started` | SPEC-01 |  |  |
| SPEC-03 | Step function and `run_fire` | Aaron | P1 — Model core | `not started` | SPEC-01, SPEC-02 |  |  |
| SPEC-04 | Metrics and scar statistics | Armaan | P1 — Model core | `not started` | SPEC-03 |  |  |
| SPEC-05 | Experiment harness | Aaron | P2 — Harness & validation | `not started` | SPEC-03, SPEC-04 |  |  |
| SPEC-06 | `p_c` estimation, FSS, `p_rel` resolver | Armaan | P2 — Harness & validation | `not started` | SPEC-05 |  |  |
| SPEC-07 | Experiment 0: percolation validation | Aaron | P2 — Harness & validation | `not started` | SPEC-05, SPEC-06 |  |  |
| SPEC-08 | Figure foundation, validation figure | Armaan | P2 — Harness & validation | `not started` | SPEC-07 |  |  |
| SPEC-09 | Geometry framework, `none`, `random` | Armaan | P3 — Treatment geometries | `not started` | SPEC-02 |  |  |
| SPEC-10 | `patches`, `strips_perp`, `strips_para` | Armaan | P3 — Treatment geometries | `not started` | SPEC-09 |  |  |
| SPEC-11 | `buffer` | Armaan | P3 — Treatment geometries | `not started` | SPEC-02, SPEC-09 |  |  |
| SPEC-12 | Settlement pilot, coarse Exp 1, freeze | Aaron | P4 — Parameter freeze | `not started` | SPEC-05, SPEC-06, SPEC-10, SPEC-11 |  |  |
| SPEC-13 | Experiment 1: geometry × budget | Aaron | P5 — Full experiments | `not started` | SPEC-12 |  |  |
| SPEC-14 | Experiment 2: threshold shift | Armaan | P5 — Full experiments | `not started` | SPEC-06, SPEC-13 |  |  |
| SPEC-15 | Tail fitting, Experiment 2b | Armaan | P5 — Full experiments | `not started` | SPEC-14 |  |  |
| SPEC-16 | Experiments 3 and 4, frame invariance | Aaron | P5 — Full experiments | `not started` | SPEC-13 |  |  |
| SPEC-17 | Results figures | Armaan | P6 — Delivery | `not started` | SPEC-13, SPEC-14, SPEC-15, SPEC-16 |  |  |
| SPEC-18 | Reproducibility gate | Aaron | P6 — Delivery | `not started` | SPEC-08, SPEC-17 |  |  |

## Blocked

Anything `blocked`, with the open DEC entry behind it. First item at the next sync.

| Spec | Blocked since | DEC | Waiting on |
|---|---|---|---|
|  |  |  |  |

## Phase summary

Optional roll-up, updated at the Monday and Thursday syncs.

| Phase | Specs | Done | In review | In progress | Blocked |
|---|---|---|---|---|---|
| P0 — Foundation | 2 | 0 | 0 | 0 | 0 |
| P1 — Model core | 2 | 0 | 0 | 0 | 0 |
| P2 — Harness & validation | 4 | 0 | 0 | 0 | 0 |
| P3 — Treatment geometries | 3 | 0 | 0 | 0 | 0 |
| P4 — Parameter freeze | 1 | 0 | 0 | 0 | 0 |
| P5 — Full experiments | 4 | 0 | 0 | 0 | 0 |
| P6 — Delivery | 2 | 0 | 0 | 0 | 0 |
| **Total** | **18** | **0** | **0** | **0** | **0** |
