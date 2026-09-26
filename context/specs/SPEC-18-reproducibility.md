---
id: SPEC-18
title: Reproducibility gate
status: not started
owner: Aaron
reviewer: Armaan
phase: P6 — Delivery (Sprint 4)
depends_on: [SPEC-08, SPEC-17, SPEC-20, SPEC-21]
implements: [§4.7, §9, §8]
issue:
branch: spec/SPEC-18-reproducibility
pr:
decisions: [DEC-016, DEC-017]
---

# SPEC-18 — Reproducibility gate

## Objective

From a clean clone, `python run.py --exp all`, `pytest` and every notebook all succeed, and every figure in the report is confirmed to have come from that run.

## Context to read

- `workflow-rules.md` — §9 (results and data) and §10 (the pre-submission check)
- `project-context.md` §4.7 (single entry point), §9 (layout, `results/` tracked, the notebook clause), §8
- `decisions-log.md` — DEC-016, DEC-017 (notebooks committed with outputs)
- `checkpoint1-bushfire-ca-roadmap.md` §7 (the non-negotiable), §8 (Sprint 4)

## Scope

**In scope**

- A clean-clone reproduction run: fresh clone, fresh environment from `requirements.txt`, `python run.py --exp all`, `pytest`.
- Auditing `code_version` across every committed parquet for placeholders and for SHAs that do not exist in the repository history.
- Confirming `results/` is within the expected 10–20 MB and no file exceeds 50 MB.
- Confirming no scar arrays were bulk-committed.
- Deleting exploratory and scratch runs from `results/`.
- Confirming every figure in the report maps to a registered builder in `make_figures.py` — including the figures displayed in the notebooks, which consume the same registry (DEC-016).
- Executing all three notebooks end to end on the clean clone with a fresh kernel, and confirming each is committed with outputs stored and sequential execution counts (DEC-017).
- Fixing whatever the audit breaks, within the files listed below.

**Out of scope**

- Writing or editing the report text.
- Adding features, refactoring, or improving anything the audit does not flag (`workflow-rules.md` §7).
- Rerunning an experiment to change a result. If a result cannot be reproduced, that is a **stop condition** — raise it, do not quietly regenerate.

## Files

**May touch**

- `run.py`, `requirements.txt`, `.gitignore`, `README.md`
- `notebooks/*.ipynb` — re-execution and committed outputs only; no content or structure changes (SPEC-20 and SPEC-21 own those)
- `results/` — deletions of exploratory runs only
- `tests/` — only to fix a test broken by the clean-clone environment
- `context/decisions-log.md`

**Must not touch**

- `src/model.py`, `src/geometries.py`, `src/metrics.py`, `src/analysis.py` — unless a clean-clone failure requires it, and then with a DEC entry
- `context/project-context.md`
- Any committed results parquet's contents — append-only (`workflow-rules.md` §9)

## Interface contract

No new interface. `python run.py --exp all` must already exist from SPEC-01, and be wired by SPEC-07, SPEC-19 (`0b`, before `1`) and SPEC-13 through SPEC-16.

## Behaviour

- The clean clone is a **genuine fresh clone into a fresh directory with a fresh environment** — not `git clean` in the working tree. Half of what this check catches is a file that was never committed.
- `--exp all` must run every experiment in dependency order, and must fail loudly rather than skip an experiment whose inputs are missing.
- The `code_version` audit checks each distinct value against `git cat-file -e`. A SHA that is not in history means results were committed from an uncommitted working tree, which invalidates the reproducibility claim for those rows.
- Exploratory and scratch runs are deleted before submission. Only runs backing a reported figure or a validation claim are committed (`workflow-rules.md` §9).
- If a figure in the report has no builder in `make_figures.py`, either the builder is added (SPEC-17's territory — raise it) or the figure comes out of the report. It does not ship unexplained.
- **A notebook that does not run top to bottom on the clean clone is a failure of this gate**, exactly as a failing test is. Re-execute and commit the outputs; if it cannot be made to run, that is a stop condition, not something to paper over by stripping outputs.
- `notebooks/01` calls `run_fire` in one demonstration cell (DEC-018); `02` and `03` call it nowhere. The audit checks that, since a results notebook that simulates has stopped reading from `results/`.

## Acceptance criteria

- [ ] A fresh clone into a new directory, a fresh environment from `requirements.txt`, then `python run.py --exp all` exits 0.
- [ ] `pytest` passes with all eleven invariants I1–I11 green — none xfail, none skipped.
- [ ] `python figures/make_figures.py --all` exits 0 on that clean clone.
- [ ] All three notebooks execute end to end with a fresh kernel, exit 0, and are committed with outputs stored and sequential execution counts.
- [ ] `notebooks/01` contains exactly one `run_fire` cell; `notebooks/02` and `03` contain none.
- [ ] No `.ipynb_checkpoints/` directory is committed.
- [ ] Every distinct `code_version` in `results/` resolves to a commit in history; none is a placeholder.
- [ ] `du -sh results/` is within 10–20 MB and no single file exceeds 50 MB.
- [ ] No parquet contains a scar array column.
- [ ] Every figure referenced in the report maps to exactly one registered builder, listed in the PR body.
- [ ] `README.md` states the one command that reproduces everything, and the order the notebooks are read in.

## Invariants

- [ ] **All of I1–I11 pass**, in the full suite, on the clean clone. This is the only point in the project where that is checked as a whole.

## Verification

```bash
cd $(mktemp -d) && git clone <repo> repro && cd repro
python -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt
python run.py --exp all && pytest -q && python figures/make_figures.py --all
for nb in notebooks/*.ipynb; do jupyter nbconvert --to notebook --execute --inplace "$nb" || exit 1; done
git diff --stat notebooks/   # non-empty means committed outputs were stale
python - <<'PY'
import glob, subprocess, pandas as pd
vs = set()
for f in glob.glob("results/*.parquet"):
    d = pd.read_parquet(f, columns=["code_version"]); vs |= set(d.code_version.unique())
    assert "scar" not in pd.read_parquet(f).columns, f
for v in vs:
    r = subprocess.run(["git","cat-file","-e",f"{v}^{{commit}}"], capture_output=True)
    print(v, "OK" if r.returncode==0 else "NOT IN HISTORY")
PY
du -sh results/
```

## Definition of done

- [ ] Acceptance criteria all met
- [ ] All eleven invariants pass on the clean clone
- [ ] Every deviation logged in `decisions-log.md`, IDs listed in `decisions:` above
- [ ] Any contract change applied to `project-context.md` in this same PR
- [ ] `status` updated in this file and in `progress-tracker.md`
- [ ] PR open, linked to the issue — status `in review`
- [ ] Reviewed by `reviewer` and merged — status `done` (human only)

## Notes and risks

- **Budget a full day, not an hour.** The roadmap calls the reproducibility guarantee one of the two things that reliably separates strong reports from average ones, and the failures this catches — an uncommitted file, a placeholder `code_version`, a figure with no builder — are each individually cheap to fix and collectively a day's work if they all surface at once.
- **The technical specification was released on 18 September and this spec has not yet been fully reconciled with it.** Two things are still open: the suggested repository layout (`src/`, `utils/`, `data/`, `notebooks/`) differs from ours, pending the unit's answer on whether it is a hard requirement; and the repository must be made public for assessment, which is not currently in this gate's scope. Re-read this spec against the submission instructions when they land, and add the visibility change as a final step. It is the last spec in the plan, so there is no slack behind a surprise here.
- Run this gate **before** the Thursday submission, not on it. Roadmap §8 targets Thu 8 Oct with Friday as buffer, and explicitly says not to plan on using the buffer.
- A result that will not reproduce is a stop condition (`workflow-rules.md` §6), not a thing to regenerate quietly. If the numbers move, the report's numbers were wrong and that matters more than the deadline.
- This spec depends on SPEC-08 as well as SPEC-17 so that the validation figure is inside the clean-clone chain — without that edge, the project's replication deliverable is the one figure never checked end-to-end.
