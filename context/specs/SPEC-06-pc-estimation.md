---
id: SPEC-06
title: p_c estimation, finite-size scaling, and the p_rel resolver
status: not started
owner: Armaan
reviewer: Aaron
phase: P2 — Harness and validation (Sprint 1)
depends_on: [SPEC-05]
implements: [§4.6, §6.1]
issue:
branch: spec/SPEC-06-pc-estimation
pr:
decisions: [DEC-004]
---

# SPEC-06 — `p_c` estimation, FSS, and the `p_rel` resolver

## Objective

`estimate_pc` returns a threshold and its standard error from a sweep; `results/pc_estimates.parquet` exists with one row per measured condition; and any experiment specified as `p_c ± δ` can resolve that to an absolute `p` at config-build time.

## Context to read

- `workflow-rules.md`
- `project-context.md` §6.1 (**`p_c` is a measured value, never a constant** — the single most important rule in the document), §4.6 (`analysis.py` contract), §2 O4, §5 (the frame these read), §7 I10, §10.1 D5

## Scope

**In scope**

- `estimate_pc(df, condition, regime) -> (p_c, stderr)` from the crossing of `P(span)` or `P(reached_edge)` across `L`, cross-checked against the peak of `Var(burned_fraction)`.
- Writing `results/pc_estimates.parquet` with columns `regime, condition, b, kappa, L, p_c, p_c_stderr, method`, with the row identity defined in Behaviour (DEC-004).
- A resolver turning `(regime, condition, b, kappa, p_rel)` into an absolute `p`.
- The `truncated == False` assertion applied to every input frame (I10).

**Out of scope**

- Running any experiment — SPEC-07 and SPEC-14 supply the frames.
- Tail fitting and the burn-size distribution — SPEC-15.
- Plotting the FSS crossing — SPEC-08.
- Deciding the fine sweep range for Experiment 2 — SPEC-14.

## Files

**May touch**

- `src/analysis.py`
- `tests/test_analysis.py`
- `tests/test_invariants.py` — only `test_i10`

**Must not touch**

- `src/model.py`, `src/metrics.py`, `src/geometries.py`, `src/experiments.py`, `figures/`
- Any invariant test other than I10

## Interface contract

As `project-context.md` §4.6 for `estimate_pc`. The resolver is new and every experiment spec from SPEC-12 onward is written against it:

```python
def estimate_pc(df, condition: str, regime: str) -> tuple[float, float]: ...
def write_pc_estimates(rows, path: str = "results/pc_estimates.parquet") -> None: ...

def resolve_p(p_rel: float, *, regime: str, condition: str, b: float, kappa: float,
              path: str = "results/pc_estimates.parquet") -> float:
    """Absolute p for an offset from the governing threshold.
    Selects the single method == "fss_crossing" row (L null) matching
    (regime, condition, b, kappa). Raises if pc_estimates.parquet is missing,
    if no row matches, or if more than one row matches. Never falls back."""
```

## Behaviour

- **`P_C_LITERATURE = 0.407` must not appear anywhere in this file.** It is used in exactly one place in the codebase — SPEC-07's validation assertion (§6.1). If it appears here, the spec has been implemented wrongly.
- The governing `p_c` for a `STUDY` experiment is the untreated (`condition="none"`, `b=0`) `STUDY` threshold at the matching `kappa`, unless the experiment says otherwise (§6.1). The lookup key is therefore `(regime, condition, b, kappa)`, **never `condition` alone** — the `PERCOLATION` threshold governs no `STUDY` run (§2 O4), and conflating them is named in `project-context.md` as the most likely silent error in this project.
- **Row identity in `pc_estimates.parquet`** (DEC-004; no column is added, removed or renamed). For each measured `(regime, condition, b, kappa)`, `write_pc_estimates` writes:
  - one **per-`L` row** for each lattice size, `L` set, `method = "var_peak"`: the peak of `Var(burned_fraction)` at that `L`, i.e. the cross-check;
  - exactly one **`method = "fss_crossing"` row with `L` null** (nullable `Int32`): the value `estimate_pc` returns, from the crossing across all `L`. This is the governing threshold.

  `(regime, condition, b, kappa, method, L)` is unique; `write_pc_estimates` raises rather than append a duplicate.
- `resolve_p` reads **only** the `fss_crossing` row with null `L` matching `(regime, condition, b, kappa)` exactly, never a per-`L` row. **Zero matches raises; more than one match raises.**
- `resolve_p` **raises** when the row is missing. It does not warn, does not default, and does not fall back to the literature value (§6.1).
- Record which method produced each estimate in the `method` column, so the crossing estimate and the variance-peak cross-check are distinguishable in the report.
- Assert `truncated == False` over every input frame before estimating anything. If it fires, the fix is to raise `max_steps` and rerun, **not** to filter the rows out (§3.7, §7 I10).

## Acceptance criteria

- [ ] `estimate_pc` recovers a known threshold from a synthetic sweep built with a logistic `P(span)` centred at a chosen `p`, to within the returned stderr.
- [ ] The variance-peak cross-check agrees with the crossing estimate on that synthetic data.
- [ ] `pc_estimates.parquet` has exactly the §4.6 columns.
- [ ] `resolve_p` raises a clear exception when the file is missing.
- [ ] `resolve_p` raises when the file exists but lacks the `(regime, condition, b, kappa)` row.
- [ ] `resolve_p` for a `STUDY` request never returns a `PERCOLATION` row's value, even when `condition` matches.
- [ ] `write_pc_estimates` for one measured key over three `L` values writes three `var_peak` rows with `L` set and one `fss_crossing` row with `L` null, and raises on a duplicate `(regime, condition, b, kappa, method, L)`.
- [ ] When per-`L` and `fss_crossing` rows both exist for a key, `resolve_p` uses the `fss_crossing` value.
- [ ] `resolve_p` raises when two `fss_crossing` rows match the same key.
- [ ] `grep -rn "0.407\|P_C_LITERATURE" src/analysis.py` returns nothing.
- [ ] An input frame containing a `truncated == True` row raises.

## Invariants

- [ ] **I10 no truncation** — `truncated` is False across every reported frame; the assertion lives in `analysis.py` (§7).

## Verification

```bash
pytest -q tests/test_analysis.py
pytest -q tests/test_invariants.py -k i10
grep -rn "0\.407\|P_C_LITERATURE" src/analysis.py && echo "FAIL: literature constant leaked into analysis" || echo "ok"
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

- Row identity and `resolve_p`'s selection rule are fixed by DEC-004. SPEC-07, SPEC-14 and SPEC-15 are written against it.
- **This spec is on the critical path twice** — once for Experiment 0, once for Experiment 2 — and everything specified as `p_rel` is blocked until it works. The project roadmap already flags "analysis harder than the model" as a high risk. Start it the moment SPEC-05 merges; do not leave it for Sprint 3.
- Test against synthetic sweeps with a known answer before trusting it on real data. A `p_c` estimator that is quietly biased produces plausible numbers that no later check will catch.
- The crossing method needs at least three lattice sizes to be meaningful. If Experiment 0's `L=512` arm is descoped for compute reasons, this estimator degrades to two points and the stderr becomes unreliable — say so rather than reporting it as though nothing changed.
