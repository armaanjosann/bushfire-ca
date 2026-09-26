---
id: SPEC-01
title: Repo skeleton, entry point, and model contracts
status: in review
owner: Aaron
reviewer: Armaan
phase: P0 — Foundation (Sprint 1)
depends_on: []
implements: [§9, §4.7, §4.1, §4.4, §3.4, §8]
issue:
branch: spec/SPEC-01-foundation
pr:
decisions: [DEC-002]
---

# SPEC-01 — Repo skeleton, entry point, and model contracts

## Objective

The repository has its final shape, `pytest` runs, `run.py` dispatches every experiment, and the two pure contract pieces of `model.py` — `Config` with its regime validation, and `wind_weights` — exist and are tested. Nothing simulates yet.

## Context to read

- `workflow-rules.md` — all of it
- `project-context.md` §9 (repository layout), §4.7 (`run.py`), §4.1 (`Config`, `wind_weights` signatures), §4.4 (config validation), §3.4 (wind kernel), §8 (implementation constraints)
- `project-context.md` §7 (the invariant table — for the placeholder test names only, not to implement)

## Scope

**In scope**

- The directory tree of §9, with `src/` a package (`src/__init__.py`).
- `src/model.py`: `NEIGHBOURS`, `DIAGONAL_FACTOR`, `P_C_LITERATURE`, `Config` (frozen dataclass, fields exactly as §4.1), `Config.__post_init__` raising on every case in §4.4, and `wind_weights`.
- `run.py`: `argparse` over `--exp {0,1,2,2b,3,4,all}`, dispatching to `src/experiments.py` entry points that raise `NotImplementedError` naming the spec that will implement them.
- Empty-but-importable `src/metrics.py`, `src/analysis.py`, `figures/make_figures.py`.
- `src/geometries.py`: the `generate` **stub only** — see Interface contract.
- `tests/test_invariants.py` with eleven placeholder tests `test_i1` … `test_i11`, each `@pytest.mark.xfail(strict=False)` with a reason naming the spec that will make it pass.
- `tests/test_model.py` with real tests for `Config` validation and `wind_weights`.
- `.gitignore`, `requirements.txt`, `results/.gitkeep`, `report/.gitkeep`.

**Out of scope**

- `initial_grids` and anything that places fuel, settlement or ignition — SPEC-02.
- The step function, `run_fire`, `RunResult` — SPEC-03.
- Any real treatment geometry — SPEC-09, SPEC-10, SPEC-11.
- Metrics bodies — SPEC-04. Parquet, `run_id`, `code_version` — SPEC-05. Figures — SPEC-08.

## Files

**May touch**

- `run.py`, `requirements.txt`, `.gitignore`
- `src/__init__.py`, `src/model.py`, `src/geometries.py`, `src/metrics.py`, `src/experiments.py`, `src/analysis.py`
- `figures/make_figures.py`
- `tests/__init__.py`, `tests/test_invariants.py`, `tests/test_model.py`
- `results/.gitkeep`, `report/.gitkeep`

**Must not touch**

- `CLAUDE.md`, `context/project-context.md`, `context/workflow-rules.md`, `context/spec-plan.md`
- Any other spec file, or any tracker row other than SPEC-01's

## Interface contract

`Config` and `wind_weights` are **as `project-context.md` §4.1 — do not redesign**. Field names, defaults and types come from there verbatim.

The geometry stub is new and becomes what SPEC-02 is written against. It must match §4.2 exactly:

```python
# src/geometries.py
def generate(condition: str, rng, occupied: np.ndarray, n_treat: int, **params) -> np.ndarray:
    """Stub. SPEC-09 implements dispatch; SPEC-10 and SPEC-11 add conditions."""
    if n_treat == 0:
        return np.zeros(occupied.shape, dtype=bool)   # the I6 contract: no rng draw
    raise NotImplementedError("treatment geometries land in SPEC-09")
```

Returning all-False for `n_treat == 0` **before touching `rng`** is the I6 contract (§7) and lets SPEC-02 be developed at `b = 0`. Raising otherwise means any accidental reliance on treatment before SPEC-09 fails loudly instead of silently running an untreated landscape.

## Behaviour

- `Config` is `frozen=True`. `__post_init__` validates only; it assigns nothing. `max_steps=None` stays `None` — the `8 * L` default is resolved at use site in `run_fire` (SPEC-03), not here.
- Validation raises `ValueError` with a message naming the offending field, for every case listed in §4.4. One test per case.
- `wind_weights(kappa, phi, diagonal_factor) -> np.ndarray` of shape `(8,)`, indexed by the `NEIGHBOURS` order of §3.4, which is a contract and is not to be re-ordered. `theta = atan2(-dy, dx)`. Normalise so the **mean over the eight directions is 1** — see §3.4 on why not sum.
- `run.py` exits 0 only when an experiment actually ran. Until SPEC-07 lands, every `--exp` raises.
- `.gitignore` must **not** exclude `results/` — it is tracked (`workflow-rules.md` §9). It **should** exclude generated figure output, since figures are not committed unless a spec asks (`workflow-rules.md` §7).

## Acceptance criteria

- [x] `pytest` collects and runs; `test_i1` … `test_i11` are present and reported as xfail.
- [x] Every case in §4.4 has a test asserting `Config(...)` raises.
- [x] `wind_weights(0.0, 0.0, False)` is `np.ones(8)`.
- [x] `wind_weights(k, phi, d).mean() == 1` to within 1e-12 for a sample across `k ∈ {0,1,2,4}`, `phi ∈ {0, π/4, π/2}`, `d ∈ {True, False}`.
- [x] With `diagonal_factor=True` and `kappa=0`, the four diagonal weights equal each other and are smaller than the four axial weights.
- [x] `python run.py --exp 0` exits non-zero with a `NotImplementedError` naming SPEC-07.
- [x] `python -c "import src.model, src.geometries, src.metrics, src.experiments, src.analysis, figures.make_figures"` succeeds.
- [x] No dependency outside numpy, matplotlib, pandas, pyarrow, pytest.

## Invariants

- [x] None owned. This spec **creates** the I1–I11 placeholder file so that an unowned invariant shows up as a permanently-failing test rather than as an absence.

## Verification

```bash
pytest -q
python run.py --exp 0; echo "exit=$?"
python -c "from src.model import wind_weights; import numpy as np; print(wind_weights(2.0,0.0,True), wind_weights(2.0,0.0,True).mean())"
git check-ignore -v results/.gitkeep; echo "expect: no match (results is tracked)"
```

## Definition of done

- [x] Acceptance criteria all met
- [x] Named invariants pass locally
- [x] Every deviation logged in `decisions-log.md`, IDs listed in `decisions:` above
- [x] Any contract change applied to `project-context.md` in this same PR (none needed — no contract changed)
- [x] `status` updated in this file and in `progress-tracker.md`
- [ ] PR open, linked to the issue — status `in review`
- [ ] Reviewed by `reviewer` and merged — status `done` (human only)

## Notes and risks

- **Mean-1, not sum-1.** Sum-1 normalisation would couple wind strength to overall flammability and confound `kappa` with `beta` (§3.4). This is the single easiest thing to get wrong in this spec.
- The `theta` negation exists because `+y` is down in array coordinates and north-up in physical coordinates. Dropping it silently mirrors the wind.
- `wind_weights` does not need to know the regime. §4.4 already forbids `diagonal_factor=True` under `PERCOLATION`, so the §2 O3 requirement is enforced at construction.
- **The unit's GitHub requirements have not been released.** They could mandate a repo layout, branch or commit convention, or restrict what may be committed — which would collide with §9 and `workflow-rules.md` §8 and §9. Build to the spec as written; the §9 layout is conventional and low-regret. If the document lands before this merges, read its repository clause first, and raise a DEC for any conflict rather than quietly conforming.
- `requirements.txt` is not in the §9 tree. It is added here because SPEC-18's clean-clone check needs it, and it records existing dependencies rather than adding any. If the reviewer disagrees, that is a DEC entry, not a silent removal.
