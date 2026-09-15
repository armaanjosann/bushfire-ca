---
id: SPEC-05
title: Experiment harness — schema, parallel runner, resume
status: not started
owner: Aaron
reviewer: Armaan
phase: P2 — Harness and validation (Sprint 1)
depends_on: [SPEC-03, SPEC-04]
implements: [§4.5, §5, §8]
issue:
branch: spec/SPEC-05-experiment-harness
pr:
decisions: []
---

# SPEC-05 — Experiment harness

## Objective

A list of `Config`s goes in; `results/exp{N}.parquet` comes out with every §5 column present and correctly typed, written in parallel, and resumable after an interruption.

## Context to read

- `workflow-rules.md` — especially §9 (results and data)
- `project-context.md` §4.5 (`experiments.py` contract), §5 (the full results schema — all of it), §8 (no global state), §6.3 (compute), §4.1 (`RunResult`), §4.3 (metrics)

## Scope

**In scope**

- `run_id`: a deterministic hash of the full config. Primary key, and the basis of resume.
- `code_version`: the git short SHA at run time.
- Assembling one schema row per run from `Config` + `RunResult` + `metrics.py`.
- The parallel runner: `multiprocessing.Pool`, **chunked by config, not by replicate**.
- Parquet writing to `results/exp{N}.parquet`, one row per run.
- Resume: if the output file exists, skip configs whose `run_id` is already present.
- `wall_ms` per run.
- Nullable `Int32` / nullable boolean dtypes per §5.

**Out of scope**

- Defining any experiment grid — SPEC-07 and SPEC-12 through SPEC-16 each build their own.
- `p_c` estimation and the `p_rel` resolver — SPEC-06.
- Any analysis, assertion over a finished frame, or figure.
- Changing `RunResult` or any §4 signature.

## Files

**May touch**

- `src/experiments.py`
- `run.py` — only to wire the dispatch to real functions
- `tests/test_experiments.py`

**Must not touch**

- `src/model.py`, `src/metrics.py`, `src/geometries.py`, `src/analysis.py`, `figures/`
- `context/project-context.md` §5 — **this spec implements the schema, it does not get to change it**

## Interface contract

As `project-context.md` §4.5. This spec additionally defines, and later specs are written against:

```python
def run_configs(cfgs: list[Config], out_path: str, resume: bool = True) -> pd.DataFrame: ...
def config_run_id(cfg: Config) -> str: ...
def code_version() -> str: ...
```

## Behaviour

- **This spec owns §5 and nothing else may change a column** (`workflow-rules.md` §7). Every later experiment spec supplies configs and touches nothing about the row.
- `run_id` is a hash of every field of `Config`, including `geometry_params`, computed from a canonical serialisation so it is stable across processes and Python runs. A `run_id` that varies between machines breaks resume silently.
- `geometry_params` is stored JSON-encoded as a string (§5).
- Nullable columns use pandas nullable dtypes — `Int32`, nullable boolean — never `-1` or `False` sentinels. `spanned`, `reached_edge`, `settlement_reached`, `settlement_reached_step`, `ignition_y`, `ignition_x` all have null cases; see SPEC-04 and §3.5.
- `budget_basis` is written as the literal `"occupied"` (§2 O2, §5), recorded explicitly so the alternative would be distinguishable if ever run.
- `n_treated` is the **realised** treated count returned by the generator, not `round(b * n_occupied)`. Efficiency divides by this (§4.2, §11).
- Chunk by config so that the replicates of one config land together and a partial run resumes on a config boundary.
- Results are **append-only**. A rerun appends through the resume path or writes a new file; a committed parquet is never mutated (`workflow-rules.md` §9).
- No module-level `np.random`, no global mutable state (§8). Each worker builds its own generator from `cfg.seed` via `run_fire`.

## Acceptance criteria

- [ ] Every column in §5 is present, with the stated dtype, for a small smoke grid.
- [ ] `config_run_id` is stable across processes, across two Python invocations, and across a `Pool` worker.
- [ ] Two different configs never collide on `run_id` over a 5,000-config grid.
- [ ] Killing the runner partway and rerunning produces the union of rows with no duplicate `run_id`.
- [ ] `code_version` is a real git short SHA; the runner refuses to write if it cannot obtain one.
- [ ] Null cases are actually null: under `"random_cell"`, `spanned` is `<NA>`; under `"edge"`, `reached_edge` and `ignition_y`/`ignition_x` are `<NA>`.
- [ ] `budget_basis == "occupied"` on every row.
- [ ] A 16-worker run of 200 configs is faster than serial by a factor of at least 8.

## Invariants

- [ ] None owned. I7 is asserted over the results frame in SPEC-09; this spec must make `n_treated` available for that assertion to be possible.

## Verification

```bash
pytest -q tests/test_experiments.py
python - <<'PY'
import pandas as pd
df = pd.read_parquet("results/smoke.parquet")
print(df.dtypes.to_string())
print(df[["run_id","code_version","budget_basis","spanned","reached_edge"]].head())
assert df.run_id.is_unique
PY
```

## Definition of done

- [ ] Acceptance criteria all met
- [ ] Named invariants pass locally
- [ ] Every deviation logged in `decisions-log.md`, IDs listed in `decisions:` above
- [ ] Any contract change applied to `project-context.md` in this same PR
- [ ] `status` updated in this file and in `progress-tracker.md`
- [ ] `results/smoke.parquet` **deleted** before the PR — only runs backing a reported figure or a validation claim get committed (`workflow-rules.md` §9)
- [ ] PR open, linked to the issue — status `in review`
- [ ] Reviewed by `reviewer` and merged — status `done` (human only)

## Notes and risks

- **A placeholder `code_version` committed alongside real results is invisible until submission** and is a `workflow-rules.md` §9 violation. Make the runner refuse to write rather than fall back to `"unknown"`. SPEC-18 audits this, but by then the runs are expensive to redo.
- §5 is described in `project-context.md` as the most load-bearing contract in the project. Implement it once, exactly, here.
- Scars are never stored for a sweep (§4.1). The runner should not even offer `capture_scar` as a grid-level option; SPEC-17 captures a hand-picked handful separately.
- Expected total across all experiments is 10–20 MB. A single file over 50 MB means something is being written per-replicate that should not be — stop and raise it (`workflow-rules.md` §9).
