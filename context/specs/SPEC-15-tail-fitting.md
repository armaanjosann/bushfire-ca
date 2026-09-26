---
id: SPEC-15
title: Tail fitting and Experiment 2b
status: not started
owner: Armaan
reviewer: Aaron
phase: P5 — Full experiments (Sprint 3)
depends_on: [SPEC-14, SPEC-19]
implements: [§6.2 Exp 2b, §10.2 O4, §4.6]
issue:
branch: spec/SPEC-15-tail-fitting
pr:
decisions: [DEC-005, DEC-012]
---

# SPEC-15 — Tail fitting and Experiment 2b

## Objective

Burn-size distributions are fitted by maximum likelihood with `x_min` chosen by KS distance, reporting the exponent **together with the fitted cutoff**, over R = 10,000 runs per condition at each condition's measured `p_c`. This answers SQ3.

## Context to read

- `workflow-rules.md`
- `project-context.md` §10.2 O4 (**the protocol, fixed in advance; only the replicate count is open**), §6.2 Exp 2b, §6.1, §4.6
- `checkpoint1-bushfire-ca-roadmap.md` §2 SQ3

## Scope

**In scope**

- Clauset–Shalizi–Newman maximum-likelihood tail fitting in `src/analysis.py`, with `x_min` selected by KS distance.
- Fitting an exponent **and** a cutoff term.
- The Experiment 2b grid (§6.2, §10.2 O4, DEC-012): `STUDY`, `L = 256`, `random_cell` ignition, no settlement, `kappa = 0`, `phi = -π/2`, R = 10,000, over four conditions:
  - `none` at `b = 0`, with `p` = the Experiment 0b `kappa = 0` threshold (SPEC-19)
  - `random`, `patches(k*)` and `strips_perp(w*)` at `b = 0.15`, each with `p` = its own Experiment 2 threshold. `k*` and `w*` are the levels SPEC-14 measured.
- Applying the §10.2 O4 gate and recording its outcome in `project-context.md`.

**Out of scope**

- `estimate_pc` — SPEC-06 owns it; this spec reads its output.
- Any new experiment beyond 2b.
- Figures — SPEC-17 plots these fits.

## Files

**May touch**

- `src/analysis.py` — the tail-fitting functions
- `src/experiments.py` — the `exp2b` grid builder and entry point
- `run.py`
- `results/exp2b.parquet`, `results/tail_fits.parquet`
- `context/project-context.md` §10.2 O4 — **required if the gate changes the replicate count**
- `context/decisions-log.md`

**Must not touch**

- `src/model.py`, `src/geometries.py`, `src/metrics.py`, `figures/`
- Any section of `project-context.md` other than §10.2 O4

## Interface contract

New, and SPEC-17 plots from it:

```python
def fit_tail(sizes: np.ndarray) -> dict:
    """CSN MLE fit. Returns at least: x_min, alpha, alpha_stderr, cutoff,
    n_tail, decades_above_xmin, ks_distance."""
def write_tail_fits(rows, path: str = "results/tail_fits.parquet") -> None: ...
```

No new dependency. `powerlaw` and `scipy` are not in the project's allowed set — implement the MLE and the KS selection in numpy, or **stop and raise a DEC** (`workflow-rules.md` §6: *the work would need a new dependency*).

## Behaviour

- `p` for each condition is that condition's **measured threshold**, read through `resolve_p(0.0, ...)` from its `fss_crossing` row (DEC-004). For treated conditions the key is `(STUDY, condition, 0.15, 0)` from Experiment 2; for `none` it is `(STUDY, none, 0, 0)` from Experiment 0b. Read `k*` and `w*` from `results/exp2.parquet`'s `geometry_params`, never re-select them. `phi = -π/2` matches the orientation under which those thresholds were measured (§6.1). A threshold is a property of the rule and the lattice, not of the ignition mode, so an edge-ignition estimate is the correct `p` for point-ignition tail runs (§10.2 O4). Do not re-estimate it here.
- **Report the exponent together with the fitted cutoff.** SQ3 asks whether treatment truncates the tail or changes its exponent, and a fit with no cutoff term cannot distinguish the two (§10.2 O4). A result reported as an exponent alone does not answer the question it was run to answer.
- **Gate G2.** The replicate count is the only thing still open at this point. If the fits show `x_min` sitting so high that fewer than ~2 decades of tail survive above it, raise R to 50,000 for the two headline conditions and narrow the condition set accordingly — then record the outcome in §10.2 O4 in this same PR, with a DEC entry.
- Experiment 1 stays at R = 200 and is not inflated to serve this fit; R = 200 is correctly sized for confidence intervals on the mean (§10.2 O4).

## Acceptance criteria

- [ ] `fit_tail` recovers a known exponent from synthetic power-law data with a known `x_min`, to within the returned stderr.
- [ ] `fit_tail` recovers a known cutoff from synthetic truncated power-law data, and reports a cutoff consistent with "none" on untruncated data.
- [ ] `results/exp2b.parquet` exists with 40,000 rows (4 conditions × 10,000), `truncated == False`.
- [ ] `results/tail_fits.parquet` has one row per condition with `alpha`, `alpha_stderr`, `cutoff`, `x_min`, `n_tail`, `decades_above_xmin`.
- [ ] `decades_above_xmin` is reported for every condition, and the G2 decision is recorded against it.
- [ ] No import of `scipy`, `powerlaw`, or any package outside the allowed set.
- [ ] If R was raised to 50,000, §10.2 O4 records it and the DEC entry names the commit.

## Invariants

- [ ] None owned. I10 must hold over the 2b frame.

## Verification

```bash
python run.py --exp 2b
python - <<'PY'
import pandas as pd
print(pd.read_parquet("results/tail_fits.parquet").round(3).to_string())
PY
python -c "import ast,sys; src=open('src/analysis.py').read(); bad=[n for n in ('scipy','powerlaw','numba','torch') if n in src]; print('FAIL',bad) if bad else print('deps ok')"
pytest -q tests/test_analysis.py -k tail
```

## Definition of done

- [ ] Acceptance criteria all met
- [ ] Named invariants pass locally
- [ ] Every deviation logged in `decisions-log.md`, IDs listed in `decisions:` above
- [ ] **§10.2 O4 updated in `project-context.md` in this same PR, recording the gate outcome**
- [ ] `status` updated in this file and in `progress-tracker.md`
- [ ] PR open, linked to the issue — status `in review`
- [ ] Reviewed by `reviewer` and merged — status `done` (human only)

## Notes and risks

- **Implementing CSN in numpy alone is the real risk in this spec.** The MLE for a discrete power law and the KS sweep over candidate `x_min` are both short, but they are easy to get subtly wrong and a wrong exponent looks entirely plausible. Validate against synthetic data with a known answer before running anything, and keep those tests in the suite.
- ~8 core-hours, about 35 minutes across 16 cores (§6.3). Cheap enough that it is scheduled unconditionally rather than treated as optional — but it sits behind Experiment 2, which is not cheap.
- Third in the descope order. If Sprint 3 compresses, this goes after Experiments 4 and 3.
- §10.2 O4 is explicit that this decision genuinely could not be made earlier: sizing a tail fit requires knowing whether the distribution is heavy-tailed at all, roughly where `x_min` sits, and how far the finite-size cutoff intrudes. None of that exists before Experiment 2.
