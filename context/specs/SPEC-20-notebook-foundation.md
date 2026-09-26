---
id: SPEC-20
title: Notebook foundation and the model-and-validation notebook
status: not started
owner: Aaron
reviewer: Armaan
phase: P2 — Harness and validation (Sprint 2)
depends_on: [SPEC-08]
implements: [§9]
issue:
branch: spec/SPEC-20-notebook-foundation
pr:
decisions: [DEC-016, DEC-017, DEC-018]
---

# SPEC-20 — Notebook foundation and the model-and-validation notebook

## Objective

`notebooks/` exists with its conventions fixed, and `notebooks/01-model-and-validation.ipynb` gives a readable account of the model — the update rule, a live demonstration run, the invariant suite, and the Exp 0 validation figure — executed top to bottom with outputs committed.

## Context to read

- `workflow-rules.md` — §7 (scope guards, the no-committed-figures rule), §9
- `project-context.md` §9 (layout and the notebook clause), §3.3 (transition rule), §3.4 (wind kernel), §7 (I1–I11), §4.1 (`Config`, `run_fire`, `capture_scar`)
- `decisions-log.md` — DEC-016, DEC-017, DEC-018
- SPEC-08 — the `FIGURES` registry and the shared style this notebook consumes

## Scope

**In scope**

- `notebooks/` with the numbered-sequence convention and a short `notebooks/README.md` stating the running order and that every notebook is committed with outputs.
- `notebooks/01-model-and-validation.ipynb`:
  - the CA state set and transition rule written as equations in markdown, matching §3.3 symbol for symbol;
  - the wind kernel (§3.4) shown as a labelled 3×3 array, with the mean-1 normalisation stated;
  - a **live demonstration run** at small `L` (≤ 128), rendered as a space-time view or a short animation from `ignition_step` (DEC-018);
  - the invariant suite explained — what I1–I11 assert and why — with the `pytest` output shown, not re-implemented;
  - the Exp 0 validation figure, imported from SPEC-08's registry, with the finite-size-scaling crossing and `P_C_LITERATURE` interpreted in prose.
- `jupyter` and `ipykernel` added to `requirements.txt` (DEC-016).
- `.gitignore` entries for `.ipynb_checkpoints/`.

**Out of scope**

- The results notebooks — SPEC-21 owns `02` and `03`.
- Any new figure builder. Figures come from SPEC-08's registry; a figure the registry lacks is SPEC-08's or SPEC-17's, raised, not written here.
- Any change to `src/`, to a results parquet, or to `figures/make_figures.py`.
- Converting `make_figures.py` into a notebook. The script stays the canonical figure producer (§9); notebooks consume it.

## Files

**May touch**

- `notebooks/01-model-and-validation.ipynb`
- `notebooks/README.md`
- `requirements.txt`
- `.gitignore`
- `context/decisions-log.md`

**Must not touch**

- `src/` — anything at all
- `figures/make_figures.py` — SPEC-08 and SPEC-17 own it
- `results/` — read-only
- `context/project-context.md` — §9 is already amended by DEC-016 and DEC-018

## Interface contract

No new interface. The notebook consumes SPEC-08's registry as-is:

```python
from figures.make_figures import FIGURES      # name -> builder returning a Figure
FIGURES["validation"]()                        # displays inline; does not write to disk
```

Builders return a `Figure`, so a notebook displays them without touching `build()` or `figures/out/`. **Do not redesign the registry to suit the notebook.**

## Behaviour

- **The notebook is a consumer, not a second source of truth.** Every figure comes from `FIGURES`; every number quoted in prose comes from `results/` or from a cell that computed it visibly. No figure is reproduced by hand-written plotting code that duplicates a registered builder.
- **The live demonstration is the one permitted `run_fire` call in the presentation layer** (DEC-018). It is bounded at `L ≤ 128`, runs in under ten seconds, uses a fixed seed, and is labelled in markdown as a demonstration, not a result. No reported quantity comes from it.
- **`make_figures.py` still may not call `run_fire`** (§9). That rule is unchanged; the exception is scoped to notebooks and to this cell.
- The notebook is committed **with outputs stored** (DEC-017), executed top to bottom in order, with no out-of-order execution counts.
- Markdown carries the explanation. A notebook that is a sequence of code cells with no prose does not satisfy what this spec is for.
- Equations are LaTeX in markdown cells, and the symbols match §3.3. A symbol that differs from the specification is a defect.

## Acceptance criteria

- [ ] `notebooks/01-model-and-validation.ipynb` exists and is committed with outputs stored.
- [ ] Restart-and-run-all from a clean kernel completes with no error, after `python run.py --exp 0` has been run.
- [ ] Execution counts are sequential from 1, with no gaps or out-of-order cells.
- [ ] Every figure in the notebook is obtained from `FIGURES`, except the live demonstration render.
- [ ] Exactly one cell calls `run_fire`, at `L ≤ 128`, with a fixed seed, and it is labelled as a demonstration.
- [ ] The transition rule appears as equations whose symbols match `project-context.md` §3.3.
- [ ] `pytest` output for the invariant suite is shown in the notebook, not re-implemented in it.
- [ ] `requirements.txt` includes `jupyter` and `ipykernel`; `pip install -r requirements.txt` in a fresh environment is sufficient to run the notebook.
- [ ] `.ipynb_checkpoints/` is gitignored and no checkpoint file is committed.
- [ ] `notebooks/README.md` states the running order and the prerequisite `run.py` commands.

## Invariants

- [ ] None owned. The notebook *explains* I1–I11; `tests/test_invariants.py` remains the only place they are asserted.

## Verification

```bash
python run.py --exp 0
jupyter nbconvert --to notebook --execute --inplace notebooks/01-model-and-validation.ipynb
python - <<'PY'
import json
nb = json.load(open("notebooks/01-model-and-validation.ipynb"))
codes = [c for c in nb["cells"] if c["cell_type"] == "code"]
ns = [c["execution_count"] for c in codes]
assert ns == list(range(1, len(ns) + 1)), f"non-sequential execution: {ns}"
assert any(c["outputs"] for c in codes), "no outputs stored"
fires = sum("run_fire" in "".join(c["source"]) for c in codes)
assert fires == 1, f"expected exactly one run_fire cell, found {fires}"
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

- **This notebook doubles as the demonstration artefact** for the 5% presentation: the rubric asks for the model ready to run with all outputs available, and a notebook that runs the model live at small `L` is exactly that. Build it with the ten-minute demo in mind and the presentation needs almost no separate preparation.
- **It is also the individual code-understanding evidence for the model side.** Whoever writes the prose here is the one who will be asked, at the demonstration, how the update rule works. That is an argument for Aaron writing it by hand rather than delegating it.
- Committed outputs make for ugly diffs. That is accepted (DEC-017) — a marker opening a stripped notebook sees empty cells. Keep the notebook's figures few and small so the committed file stays well under a megabyte.
- **The repository layout question is still open with the unit** (the released specification suggests `src/`, `utils/`, `data/`, `notebooks/`). `notebooks/` matches either way, which is why this spec is safe to do before that answer arrives. Do not restructure anything else pre-emptively.
