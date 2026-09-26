# spec-plan.md — implementation blueprint

**Planning document. Not binding on agents.** Precedence is unchanged (`workflow-rules.md` §1): `project-context.md` wins, then the spec, then the roadmap. This file sits *outside* that ladder — it is the map the two of us agreed on, and the moment a spec is written the spec supersedes what this file says about it. Nothing here is a contract. Do not implement from it.

Its job is to answer three questions before any spec is written: **what are the units of work, in what order, and who is blocked on whom.**

- 18 specs, 6 phases, mapped onto the roadmap's four sprints.
- Every §4 module contract, §5 schema column, §6 experiment, §7 invariant and §10 open item is owned by exactly one spec. The coverage check is §7 of this file.
- Owners follow the roadmap §9 component split. The reviewer is always the other person.

---

## 1. Shape of the plan

The project has one hard sequencing fact: **`p_c` is measured, never assumed** (`project-context.md` §6.1). That makes the dependency graph a diamond, not a line.

```
                          SPEC-01 foundation
                                 |
                          SPEC-02 initialisation
                        /                       \
        Aaron: model + harness            Armaan: geometries
        03 -> 05 -> 07 -> 08                 09 -> 10 -> 11
              \        \                       /
               04       06 (p_c) --- 08 --- G0 validation gate
                                        \   /
                                    SPEC-12  (settlement pilot + coarse Exp 1)
                                         |   G1 PARAMETER FREEZE  Sun 28 Sep
                                    SPEC-13  Exp 1 full
                                    /        \
                         SPEC-14 Exp 2      SPEC-16 Exp 3 & 4
                              |
                         SPEC-15 Exp 2b     G2 replicate-count gate
                              \            /
                               SPEC-17 figures
                                     |
                               SPEC-18 repro gate
```

Two tracks run in parallel from SPEC-02 onward and do not touch the same files until SPEC-12. That is the whole point of the split: neither of you should ever be waiting on the other inside Sprint 1 or 2.

The longest chain is twelve specs — 01 → 02 → 03 → 04 → 05 → 06 → 12 → 13 → 14 → 15 → 17 → 18 — across roughly 23 days. That is under two days per spec on the critical path with no slack, which is why the descope order below is decided now rather than in week three.

**The critical path is the analysis side, not the model side.** Roadmap §11 already names this ("Analysis harder than the model — High"). SPEC-06 (`p_c` estimation) appears on the critical path twice — once for Experiment 0, once for Experiment 2 — and everything specified as `p_rel` is blocked until it works. It is scheduled in Sprint 1, deliberately, not Sprint 3.

---

## 2. Phases

| Phase | Name | Specs | Window | Exit condition |
|---|---|---|---|---|
| P0 | Foundation | 01–02 | Tue 15 – Wed 16 Sep | `pytest` runs; `Config` rejects an inconsistent regime; `python run.py --exp 0` reaches "not implemented" cleanly |
| P1 | Model core | 03–04 | Wed 16 – Fri 18 Sep | A fire runs to extinction and I2, I3, I9 pass |
| P2 | Harness & validation | 05–08 | Fri 18 – Sun 20 Sep | **G0** — `p_c` recovered under `PERCOLATION` within 0.01 of 0.407, validation figure exists |
| P3 | Treatment geometries | 09–11 | Mon 21 – Thu 24 Sep | All six conditions hit budget; I6, I7, I8 pass |
| P4 | Parameter freeze | 12 | Fri 25 – Sun 27 Sep | **G1** — `SETTLEMENT_SIDE` fixed, coarse Exp 1 heatmap exists, §10 has no open items |
| P5 | Full experiments | 13–16 | Mon 28 Sep – Sun 4 Oct | **G2** — all experiment parquets written, `truncated` false throughout |
| P6 | Delivery | 17–18 | Sun 4 – Wed 7 Oct | Clean clone reproduces every figure |

Dates are a day tighter than roadmap §8 in places because the roadmap's "Mon 15 Sep" is a Tuesday. The sprint boundaries and the Thu 8 Oct submission are unchanged.

**Descope order**, decided now so it is not decided under pressure (roadmap §8: *anything not working by the Thursday sync gets descoped rather than debugged*). Drop from the bottom up: SPEC-16 Experiment 4 → SPEC-16 Experiment 3 → SPEC-15 Experiment 2b → SPEC-11 buffer. Never descope SPEC-08 (the replication deliverable) or SPEC-14 (the primary RQ).

---

## 3. The specs

Sizing: **S** ≈ half a day, **M** ≈ 1–2 days, **L** ≈ 2–3 days.

### P0 — Foundation

#### SPEC-01 — Repo skeleton, entry point, and model contracts
- **Owner** Aaron · **Reviewer** Armaan · **Size** M · **Depends on** —
- **Implements** §4.1 (`Config`), §4.4 (validation), §3.4 (`wind_weights`), §4.7 (`run.py`), §9 (layout)
- **Objective.** The repository has its final shape, `pytest` runs, and the two pure contract pieces of `model.py` — `Config` with its regime validation, and `wind_weights` — exist and are tested. Nothing simulates yet.
- **Why bundled.** `Config` and `wind_weights` are both pure, both small, and both are contracts every later spec is written against. Shipping them with the skeleton means Armaan's track is unblocked on day one rather than day three.
- **Key content.** Directory tree per §9; `run.py --exp {0,1,2,2b,3,4,all}` dispatching to stubs that raise `NotImplementedError`; `tests/test_invariants.py` with the I1–I11 skeleton (all `xfail`); `Config.__post_init__` raising on every case in §4.4; `wind_weights` with mean-1 normalisation and the fixed `NEIGHBOURS` ordering.
- **Traps.** The normalisation is **mean 1, not sum 1** (§3.4). `DIAGONAL_FACTOR` is forced off under `PERCOLATION` (§2 O3).

#### SPEC-02 — Lattice initialisation, ignition, settlement
- **Owner** Aaron · **Reviewer** Armaan · **Size** M · **Depends on** 01
- **Implements** §3.1, §3.2, §3.5, §3.6 (placement only), §4.1 (`initial_grids`)
- **Objective.** `initial_grids(cfg, rng)` returns a valid `(state, f)` pair for every regime, with the settlement placed, occupancy drawn, treatment applied and the ignition set alight.
- **Key content.** The §3.2 ordering is the whole spec: settlement → occupancy → treatment → ignition, in that order, because the geometry generator must see realised occupancy (§2 O1/O2). Both ignition modes. `SETTLEMENT_SIDE` enters as a module constant with a `# provisional, fixed by SPEC-12` marker.
- **Interface note.** This spec calls `geometries.generate` before it exists. Define the call site against the §4.2 signature and have SPEC-01 ship a `generate` stub that returns an all-False mask; SPEC-09 fills it in. Do not invent a different signature.
- **Traps.** Treatment changes `f`, never `state` (§3.2 step 3). No `FUEL` cell at all ⟹ return a zero-burn run, not an exception (§3.5).

### P1 — Model core

#### SPEC-03 — Step function and `run_fire`
- **Owner** Aaron · **Reviewer** Armaan · **Size** L · **Depends on** 01, 02
- **Implements** §3.3, §3.7, §4.1 (`run_fire`), §8 (vectorisation, bounding box)
- **Invariants owned** I2 determinism, I3 deterministic front, I9 conservation
- **Objective.** A fire runs to extinction, deterministically for a given config, with no per-cell Python loop anywhere.
- **Key content.** Synchronous update; ignition probabilities from the burning set *at the start of the step*; the running product of `(1 - P_d)` over 8 shifted masks and one Bernoulli draw; `burn_clock` and `tau`; the bounding-box restriction with 1-cell padding; `max_steps = 8*L` and the `truncated` / `still_burning_cells` split.
- **Traps.** A cell becoming `BURNT` this step **still attempts ignition this step** — step 2 runs before step 4. `burned_cells` counts `BURNT` only; folding in `still_burning` was the prototype bug (§3.7). `run_fire` must build its own RNG from `cfg.seed` and must not accept an external generator — I2 depends on it.
- **Largest spec in the project.** If any spec is worth hand-writing rather than handing to an agent, it is this one.

#### SPEC-04 — Metrics and scar statistics
- **Owner** Armaan · **Reviewer** Aaron · **Size** M · **Depends on** 03
- **Implements** §4.3 (`metrics.py`)
- **Invariants owned** I4 isotropy, I5 wind monotonicity
- **Objective.** Pure functions turning a finished run into every response variable in §4.5 of the roadmap, plus the scar-shape statistics the two physics invariants need.
- **Key content.** Burned fraction of lattice and of fuel; `reached_edge`; `spanned`; `settlement_reached` as the 1-cell ring rule (§3.6) and `settlement_reached_step`; scar second moments in x and y; scar centroid and its projection on `phi`.
- **Traps.** `spanned` under `random_cell` is `null`, not `False`; `reached_edge` under `edge` is `null`, not `True` (§3.5). This is the most likely place to silently write a boolean where the schema wants a null.
- **No I/O, no plotting.** Functions take arrays and return numbers.

### P2 — Harness and validation

#### SPEC-05 — Experiment harness
- **Owner** Aaron · **Reviewer** Armaan · **Size** L · **Depends on** 03, 04
- **Implements** §4.5 (`experiments.py`), §5 (the full results schema), §8, `workflow-rules.md` §9
- **Objective.** A list of configs goes in; `results/expN.parquet` comes out with every §5 column correctly typed, written in parallel, resumable.
- **Key content.** `run_id` as a deterministic hash of the full config; `code_version` from the git short SHA; `multiprocessing.Pool` chunked **by config, not by replicate**; resume by skipping `run_id`s already present; nullable `Int32` dtypes rather than `-1` sentinels; `wall_ms`.
- **Why it owns the schema.** §5 is the most load-bearing contract in the project and needs exactly one implementation. Every later experiment spec supplies configs and touches nothing about the row.
- **Traps.** A placeholder `code_version` committed alongside real results is a `workflow-rules.md` §9 violation that is invisible until submission. Assert it is a real SHA before writing.

#### SPEC-06 — `p_c` estimation, finite-size scaling, and the `p_rel` resolver
- **Owner** Armaan · **Reviewer** Aaron · **Size** L · **Depends on** 05
- **Implements** §4.6 (`analysis.py`), §6.1
- **Invariants owned** I10 no truncation
- **Objective.** `estimate_pc(df, condition, regime)` returns `(p_c, stderr)`; `results/pc_estimates.parquet` exists; and any experiment specified as `p_c ± δ` can resolve that to an absolute `p` at config-build time.
- **Key content.** Crossing of `P(span)` / `P(reached_edge)` across `L`, cross-checked against the peak of `Var(burned_fraction)`; the `method` column recording which; the resolver that reads `pc_estimates.parquet` and **raises** when the row is missing.
- **Traps.** This is where §6.1 is either honoured or quietly broken. `P_C_LITERATURE = 0.407` may appear in exactly one place in the codebase — SPEC-08's assertion. If it appears in this file, the spec is wrong. And the `PERCOLATION` threshold governs no `STUDY` run (§2 O4): the lookup key is `(regime, condition, b, kappa, L)`, never just `condition`.
- **On the critical path twice.** Start it the moment SPEC-05 merges.

#### SPEC-07 — Experiment 0: percolation validation run
- **Owner** Aaron · **Reviewer** Armaan · **Size** M · **Depends on** 05, 06
- **Implements** §6.2 Exp 0
- **Invariants owned** I1 percolation limit
- **Objective.** `results/exp0.parquet` exists and the measured `p_c` at `L=512` is within 0.01 of `P_C_LITERATURE`.
- **Key content.** `PERCOLATION` grid: `p ∈ [0.30, 0.60]` step 0.005, `L ∈ {128, 256, 512}`, R=500, `edge` ignition. ~93k runs; §6.3 puts this at roughly 25 core-hours dominated by `L=512`, so run the two smaller sizes first and confirm the transition before committing to 512.
- **This is the replication deliverable** (roadmap §13). It is the one spec that never gets descoped.

#### SPEC-08 — Figure foundation and the validation figure
- **Owner** Armaan · **Reviewer** Aaron · **Size** M · **Depends on** 07
- **Implements** §9 (`figures/make_figures.py`), §10.1 D5
- **Objective.** `make_figures.py` exists with its shared style and dispatch, and produces the validation figure: `P(span)` vs `p` across `L ∈ {128,256,512}` with the FSS crossing and `P_C_LITERATURE` marked.
- **Traps.** `make_figures.py` reads from `results/` and **never** calls `run_fire` (§9). Generated figures are not committed unless a spec asks (`workflow-rules.md` §7).
- **Gate G0 closes here.** Sprint 1 is done when this figure exists.

### P3 — Treatment geometries

#### SPEC-09 — Geometry framework, `none`, `random`
- **Owner** Armaan · **Reviewer** Aaron · **Size** M · **Depends on** 02
- **Implements** §4.2 (dispatch and contract), the `none` and `random` conditions
- **Invariants owned** I6 null treatment, I7 budget parity, I8 treatment placement
- **Objective.** `generate(condition, rng, occupied, n_treat, **params)` dispatches correctly and the two baseline conditions hit their budget exactly.
- **Traps.** **I6 is the one to get right.** A generator that draws from `rng` when `n_treat == 0` desynchronises the stream and makes the `b=0` baselines differ between conditions for no physical reason. Every generator returns an all-False mask **before touching `rng`**. The spec should require this as the first line of every generator, and the test should be byte-equality across all six conditions at `b=0` with a fixed seed.
- Can start as soon as SPEC-02 merges — it does not wait for the step function.

#### SPEC-10 — Clustering-scale family: `patches`, `strips_perp`, `strips_para`
- **Owner** Armaan · **Reviewer** Aaron · **Size** L · **Depends on** 09
- **Implements** §4.2 those three conditions, §10.1 D2
- **Objective.** Nine condition-levels exist (`k ∈ {4,8,16}`, `w ∈ {4,8,16}` × two orientations), each hitting `n_treat` within tolerance.
- **Key content.** Patches: random `k×k` blocks until coverage ≥ `n_treat`, then randomly un-treat the excess. Strips: bands of width `w`, bisect on spacing to hit the budget, **phase offset drawn uniformly per replicate**. `strips_para` is the same construction rotated 90°.
- **Traps.** `w` is a swept clustering-scale level, not a default (D2) — the clustering-scale axis of the primary analysis (§11) is what this spec exists to make continuous. Tolerance is `max(1, ceil(0.01 * n_treat))`, and `n_treated` records the **realised** count, which is what the efficiency metric divides by — never `b`.

#### SPEC-11 — `buffer`
- **Owner** Armaan · **Reviewer** Aaron · **Size** M · **Depends on** 09, 02
- **Implements** §4.2 `buffer`
- **Objective.** Concentric rings grown outward from the settlement block until the budget is met, final partial ring filled at random.
- **Traps.** Requires `settlement=True` (validated in §4.4). Ignition under `random_cell` may land **inside** the buffer ring — do not exclude regions, that biases the comparison toward buffer geometries (§3.6).
- **The SQ4 condition.** This is the project's insurance against a boring result (roadmap §11), so it is last in the descope order among the geometries but it is not free.

### P4 — Parameter freeze

#### SPEC-12 — Settlement-size pilot and the coarse Experiment 1 pass
- **Owner** Aaron · **Reviewer** Armaan · **Size** M · **Depends on** 05, 06, 10, 11
- **Implements** §10.2 O1, roadmap §8 Sprint 2 exit
- **Objective.** `SETTLEMENT_SIDE` is fixed by evidence and written into §3.6 as a constant with its justification; a coarse `A(geometry, b)` heatmap exists; `project-context.md` §10 has no open items left except O4.
- **Key content.** The pilot is ~800 runs: side ∈ {8,16,32,48} × `kappa` ∈ {0,2}, `b=0`, `condition="none"`, `p_rel=+0.05`, `L=256`, R=50. The decision rule is **already fixed** (§10.2 O1) — smallest side with baseline `P(settlement_reached)` in [0.3, 0.8], rejecting any side whose `n_occupied` moves more than 1% from the no-settlement case; if none qualifies, switch the SQ4 metric to `settlement_reached_step`.
- **Contract change required.** Whatever the pilot returns, `project-context.md` §3.6 and §10.2 are edited in this same PR, with a DEC entry (`workflow-rules.md` §5, the contract rule). This is the one spec that is *expected* to change the specification.
- **Gate G1 — parameter freeze, Sun 27 Sep.** After this, a methodological choice made is a choice made after seeing results, which is not defensible in the report.

### P5 — Full experiments

#### SPEC-13 — Experiment 1: geometry × budget
- **Owner** Aaron · **Reviewer** Armaan · **Size** L · **Depends on** 12
- **Implements** §6.2 Exp 1
- **Objective.** `results/exp1.parquet` — 12 condition-levels × 7 budgets × 4 `p` values × 2 `kappa`, `L=256`, R=200, settlement on. ~28 core-hours, under two hours across 16 cores.
- **Answers** the primary RQ and SQ1, SQ2, SQ4. **Never descoped.**
- **Traps.** `none` only exists at `b=0`, so the effective condition count varies by budget — build the grid accordingly rather than emitting invalid configs that §4.4 will reject. `p_rel` values resolve through SPEC-06's resolver; absolute `p=0.70` is the only hard-coded one.

#### SPEC-14 — Experiment 2: threshold shift
- **Owner** Armaan · **Reviewer** Aaron · **Size** M · **Depends on** 13, 06
- **Implements** §6.2 Exp 2, §6.1
- **Objective.** Per-condition `STUDY` thresholds measured and appended to `pc_estimates.parquet`.
- **Key content.** Best 3 conditions from Exp 1 at `b=0.15` plus `none`; fine `p` sweep; `L ∈ {128,256,512}`; R=500; **`edge` ignition** — a spanning measure is required and point ignition cannot provide one (§6.2 note).
- **The crux of the primary RQ**: does arrangement move `p_c`, or only rescale `A`?

#### SPEC-15 — Tail fitting and Experiment 2b
- **Owner** Armaan · **Reviewer** Aaron · **Size** L · **Depends on** 14
- **Implements** §6.2 Exp 2b, §10.2 O4
- **Objective.** Clauset–Shalizi–Newman MLE fits with `x_min` by KS distance, reporting **exponent together with fitted cutoff**, over R=10,000 runs at each condition's measured `p_c`.
- **Gate G2.** The replicate count is the only thing still open at this point. If fewer than ~2 decades of tail survive above `x_min`, raise R to 50,000 for the two headline conditions and narrow the set — then record the outcome in §10.2 O4 in the same PR.
- **Traps.** Reporting an exponent with no cutoff term cannot distinguish truncation from an exponent change, which is exactly what SQ3 asks. The `p` for these point-ignition runs comes from the **edge-ignition** Exp 2 estimate — a threshold is a property of the rule and lattice, not the ignition mode.

#### SPEC-16 — Experiments 3 and 4, and the frame-invariance check
- **Owner** Aaron · **Reviewer** Armaan · **Size** M · **Depends on** 13
- **Implements** §6.2 Exp 3, §6.2 Exp 4, §10.1 D3
- **Invariants owned** I11 lattice frame invariance
- **Objective.** `results/exp3.parquet` and `results/exp4.parquet`, plus a measured answer to whether axis-aligned strips couple to the lattice.
- **Key content.** Exp 3: `kappa ∈ {0,1,2,4}` × 7 conditions at `b=0.15`, `p_rel=+0.05`, settlement on — SQ1 in full. Exp 4: `f_treat ∈ {0,.2,.4}` × `beta ∈ {.7,.8,.9}`, reduced condition set. I11: compare the `strips_perp − strips_para` gap at `phi=0` against `phi=π/4` with geometry rotated to match, R=200 at one operating point.
- **Both outcomes of I11 are reportable** — overlapping CIs give one line in Methods, non-overlapping gives a measured lattice artefact with a magnitude for Limitations. Neither costs an experimental axis.
- **Bundled** because once SPEC-05's harness and SPEC-06's resolver exist, each of these is a grid definition and a run. First two items in the descope order.

### P6 — Delivery

#### SPEC-17 — Results figures
- **Owner** Armaan · **Reviewer** Aaron · **Size** L · **Depends on** 13, 14, 15, 16
- **Implements** roadmap §4.5, §13 (qualitative *and* quantitative evidence)
- **Objective.** Every figure the report cites is produced by `make_figures.py` from `results/` alone.
- **Figure set.** Clustering-scale curve (the primary analysis axis, §11); efficiency `ΔA / (n_treated/n_cells)` by condition; `p_c` shift by condition with CIs; burn-size distributions log-log with fitted exponent and cutoff; SQ4 scatter — mean burned area against `P(settlement reached)`, which is where the trade-off either appears or does not; `kappa` × condition interaction; sensitivity panel; and illustrative burn scars for a hand-picked handful of configs.
- **Traps.** The `PERCOLATION` `p_c` must never appear in a table alongside a `STUDY` threshold (§10.1 D5). Scars come from `capture_scar=True` on a few named configs only — never a sweep (§4.1).

#### SPEC-18 — Reproducibility gate
- **Owner** Aaron · **Reviewer** Armaan · **Size** M · **Depends on** 08, 17
- **Implements** §4.7, §9, `workflow-rules.md` §9, §10
- **Objective.** From a clean clone, `python run.py --exp all` and `pytest` both succeed, and every figure in the report is confirmed to have come from that run.
- **Key content.** Audit `code_version` across every committed parquet for placeholders; confirm `results/` is under 50 MB with no scar arrays bulk-committed; delete exploratory runs; confirm no figure originates from a notebook cell that no longer exists.
- **Roadmap §7 calls this one of the two things that reliably separates strong reports from average ones.** Budget a full day, not an hour.

---

## 4. Summary table

| Spec | Title | Owner | Reviewer | Phase | Size | Depends on | Implements | Invariants |
|---|---|---|---|---|---|---|---|---|
| SPEC-01 | Repo skeleton, entry point, model contracts | Aaron | Armaan | P0 | M | — | §4.1, §4.4, §3.4, §4.7, §9 | — |
| SPEC-02 | Lattice initialisation, ignition, settlement | Aaron | Armaan | P0 | M | 01 | §3.1, §3.2, §3.5, §3.6 | — |
| SPEC-03 | Step function and `run_fire` | Aaron | Armaan | P1 | L | 01, 02 | §3.3, §3.7, §4.1, §8 | I2, I3, I9 |
| SPEC-04 | Metrics and scar statistics | Armaan | Aaron | P1 | M | 03 | §4.3 | I4, I5 |
| SPEC-05 | Experiment harness | Aaron | Armaan | P2 | L | 03, 04 | §4.5, §5, §8 | — |
| SPEC-06 | `p_c` estimation, FSS, `p_rel` resolver | Armaan | Aaron | P2 | L | 05 | §4.6, §6.1 | I10 |
| SPEC-07 | Experiment 0: percolation validation | Aaron | Armaan | P2 | M | 05, 06 | §6.2 Exp 0 | I1 |
| SPEC-08 | Figure foundation, validation figure | Armaan | Aaron | P2 | M | 07 | §9, §10.1 D5 | — |
| SPEC-09 | Geometry framework, `none`, `random` | Armaan | Aaron | P3 | M | 02 | §4.2 | I6, I7, I8 |
| SPEC-10 | `patches`, `strips_perp`, `strips_para` | Armaan | Aaron | P3 | L | 09 | §4.2, §10.1 D2 | — |
| SPEC-11 | `buffer` | Armaan | Aaron | P3 | M | 02, 09 | §4.2 | — |
| SPEC-12 | Settlement pilot, coarse Exp 1, freeze | Aaron | Armaan | P4 | M | 05, 06, 10, 11 | §10.2 O1 | — |
| SPEC-13 | Experiment 1: geometry × budget | Aaron | Armaan | P5 | L | 12 | §6.2 Exp 1 | — |
| SPEC-14 | Experiment 2: threshold shift | Armaan | Aaron | P5 | M | 06, 13 | §6.2 Exp 2, §6.1 | — |
| SPEC-15 | Tail fitting, Experiment 2b | Armaan | Aaron | P5 | L | 14 | §6.2 Exp 2b, §10.2 O4 | — |
| SPEC-16 | Experiments 3 and 4, frame invariance | Aaron | Armaan | P5 | M | 13 | §6.2 Exp 3/4, §10.1 D3 | I11 |
| SPEC-17 | Results figures | Armaan | Aaron | P6 | L | 13, 14, 15, 16 | roadmap §4.5, §13 | — |
| SPEC-18 | Reproducibility gate | Aaron | Armaan | P6 | M | 08, 17 | §4.7, §9 | — |

**Load balance.** Aaron 9 specs (01, 02, 03, 05, 07, 12, 13, 16, 18), Armaan 9 (04, 06, 08, 09, 10, 11, 14, 15, 17). Aaron front-loads in Sprint 1; Armaan front-loads in Sprint 3. That asymmetry is real and worth checking against Armaan's actual availability before agreeing this plan (roadmap §14).

---

## 5. Gates

Four points where work stops until a human decides. Three are ours; one is the facilitator's.

| Gate | When | Blocks | Decision |
|---|---|---|---|
| **G−1** | ~~Checkpoint 1~~ — **cleared Mon 14 Sep** | ~~SPEC-07, SPEC-08~~ | Roadmap §10 Q1 answered: the facilitator accepted percolation as the baseline. §10.1 D5 stands, P2 proceeds as planned. See DEC-001. |
| **G0** | End Sprint 1 | Everything in P3+ substantively | Measured `p_c` within 0.01 of 0.407, validation figure exists. If the transition is not where the prototype said, stop and debug the model rather than proceeding. |
| **G1** | Sun 27 Sep | SPEC-13 onward | `SETTLEMENT_SIDE` fixed by the §10.2 O1 pilot rule; parameters frozen and justified in writing; `project-context.md` §10 carries no open item but O4. |
| **G2** | After SPEC-14 | SPEC-15's replicate count | §10.2 O4 — R=10,000 or 50,000, decided on how many decades of tail survive above `x_min`. |

G−1 is cleared (DEC-001), so P2 proceeds as planned and G0 is now the first gate with teeth.

**Four of the six facilitator questions in roadmap §10 remain unanswered**, because the Checkpoint 1 conversation stayed at the level of the approach. None blocks a spec, but two bite late: **Q4 — expected report length and figure count** sizes SPEC-17, which currently plans eight figure families; and **Q6 — when and in what format the demonstration is assessed** sizes the Sprint 4 checklist, which is three days long. Both are cheap to ask by email now and expensive to discover in the final week. Q3 (how much realism is expected) and Q5 (whether multi-season regrowth is worth doing) are scope questions that the plan has already answered by staying abstract and treating regrowth as out of scope; getting them confirmed is a nice-to-have.

### Pending external input

The unit has said that technical requirements, report format, the marking rubric and submission instructions **including GitHub requirements** will be released shortly. None of this exists yet, so four specs carry an assumption that a document could overturn. Recorded here so the exposure is known rather than discovered:

| Unknown | Can still move | Exposure |
|---|---|---|
| Report format, length, figure count | SPEC-17 | Eight figure families is a guess. A short-report requirement means cutting, not rebuilding — the figures come from committed parquet either way. **Low.** |
| Marking rubric | SPEC-17, the report split | Could shift emphasis between qualitative and quantitative evidence. Nothing in the code changes. **Low.** |
| Submission instructions | SPEC-18 | Changes what "submitted" means and what the clean-clone gate has to prove. **Low — but it is the last spec, so a surprise there has no slack behind it.** |
| **GitHub requirements** | SPEC-01, `workflow-rules.md` §8, §9 | The real one. A mandated repo layout, branch or commit convention, or a "code only, no data" rule would collide with decisions already made. **Medium.** |

**Do not wait for the document.** SPEC-01 is low-regret: the §9 layout is conventional, and the parts that are expensive to change later — the results schema (§5) and the module contracts (§4) — are untouched by anything a report-format or rubric document can say. Build it now and adapt the cosmetics if required.

The one decision most likely to collide is **`results/` being tracked in git** (`workflow-rules.md` §9). It is a deliberate choice — the parquet is part of the record, not a build artefact — but a GitHub requirement capping repo size or asking for code only would override it, and by then the files exist. If the released requirements say anything about repository contents, check that clause first. Re-read the pending sections against SPEC-01 before it merges, and against SPEC-17 and SPEC-18 when the document lands; raise a DEC for anything that conflicts rather than quietly conforming.

---

## 6. Compute — two numbers the specs should check before running

`project-context.md` §6.3 costs Experiment 1 (~28 core-hours) and Experiment 2b (~8 core-hours), and concludes no HPC is required. That conclusion looks right, but two experiments are uncosted and one of them is larger than everything else in the project put together.

**Experiment 0**, from the §6.2 grid — `p ∈ [0.30,0.60]` step 0.005 is 61 values, × R=500, × three lattice sizes:

| `L` | Runs | ms/run (§6.3) | Core-hours |
|---|---|---|---|
| 128 | 30,500 | 44 | 0.4 |
| 256 | 30,500 | 760 | 6.4 |
| 512 | 30,500 | 8,000 | **67.8** |
| | | | **≈ 75 total** |

That is ~4.7 hours across 16 cores — fine on the 9800X3D, but **2.7× Experiment 1**, and it lands in Sprint 1 rather than Sprint 3. SPEC-07 should run `L ∈ {128, 256}` first, confirm the transition, and only then commit the `L=512` arm. The bounding-box optimisation (§8) matters most here and is worth having landed in SPEC-03 before this runs.

**Experiment 2** is uncosted because "fine `p` sweep" has no stated extent. Four conditions × 500 replicates × three `L` × *n* values is `2000n` runs per `L`; at `L=512` each value of *n* costs 4.4 core-hours. A 40-point sweep would be ~178 core-hours at `L=512` alone. SPEC-14 must state the sweep range and step explicitly — and since it is a *fine* sweep around thresholds Experiment 1 has already located, something like 21 points over ±0.05 is the intent, not a rerun of Exp 0's range. Even that costs ~93 core-hours (5.8 h across 16 cores), so it is a scheduled overnight run, not something to start on the Sunday.

Neither finding changes the conclusion that Kaya is not needed. Both change what a spec should say before someone starts a run on Friday night.

---

## 7. Coverage check

Every contract in `project-context.md` is owned by exactly one spec. Gaps here are the thing this document exists to catch.

**§4 module contracts** — §4.1 `Config`/`wind_weights` → 01, `initial_grids` → 02, `run_fire`/`RunResult` → 03 · §4.2 → 09, 10, 11 · §4.3 → 04 · §4.4 → 01 · §4.5 → 05 · §4.6 → 06, with tail fitting in 15 · §4.7 → 01, audited by 18.

**§5 results schema** — entirely SPEC-05. No other spec may change a column (`workflow-rules.md` §7).

**§6 experiments** — Exp 0 → 07 · Exp 1 coarse → 12, full → 13 · Exp 2 → 14 · Exp 2b → 15 · Exp 3 → 16 · Exp 4 → 16.

**§7 invariants** — I1 → 07 · I2, I3, I9 → 03 · I4, I5 → 04 · I6, I7, I8 → 09 · I10 → 06 · I11 → 16. All eleven owned; SPEC-01 creates the test file with all eleven `xfail`, so an unowned invariant is visible as a permanently-failing test rather than as an absence.

**§10 items** — D2 → 10 · D3 → 16 · D5 → 08 and 17 · O1 → 12 (contract change expected) · O4 → 15 (contract change expected).

**Roadmap sub-questions** — SQ1 → 16 · SQ2 → 13 · SQ3 → 15 · SQ4 → 11, 13, 17.

### The shared-file convention

Five pairs of specs that the dependency graph does not order against each other touch `src/experiments.py` and `run.py`, and they have different owners — SPEC-07 against SPEC-14 and SPEC-15, SPEC-14 and SPEC-15 against SPEC-16. In practice the sprints separate them, but the graph does not, so the convention is structural rather than temporal:

**Every experiment spec adds its own `exp{N}` grid builder and its own `run.py` dispatch entry, and changes no other function in either file.** Additions to different parts of a file merge; edits to a shared helper do not. If an experiment spec finds itself needing to change something an earlier experiment spec wrote, that is a stop condition (`workflow-rules.md` §6), not a merge conflict to resolve by hand.

One deliberate exception: SPEC-12 registers a single builder in `figures/make_figures.py`, which is Armaan's file under roadmap §9. Armaan reviews that PR.

### Two seams to watch

**`RunResult` vs the schema.** §4.1 defines `RunResult` as "exactly the fields in §5, minus the config echo", which means SPEC-03 defines the fields and SPEC-05 assembles the row. Those two specs must not each decide what a field means. SPEC-03 writes the dataclass; SPEC-05 echoes the config and writes dtypes; neither invents a column.

**`geometries.generate` before it exists.** SPEC-02 calls it in Sprint 1; SPEC-09 implements it in Sprint 2. SPEC-01 ships the stub against the §4.2 signature. If the stub's signature drifts from §4.2, the two tracks diverge silently and the merge in SPEC-12 is where it surfaces — which is the worst possible time.

---

## 8. What this plan does not cover

- **The report.** Roadmap §9 splits the sections between you; they are not specs and do not go in the tracker as such. Decide at the Monday sync whether you want tracker rows for them anyway — Sprint 4 is three days and a report section that nobody owns is the classic way to lose them.
- **The demonstration.** Roadmap §8 wants it rehearsed twice. Not a spec; put it on the Sprint 4 checklist.
- **GitHub issues.** `workflow-rules.md` §8 requires each PR to link an issue. Create the 18 issues when the specs are written, not before.
- **Extensions.** Multi-season fuel regrowth, multiple ignitions, `L=1024` on Kaya. All out of scope unless a gate frees up time, which it will not.

---

## 9. Using this file

1. Agree or amend it at the Monday sync. Disagree in writing first (roadmap §14).
2. Write the 18 spec files from `spec-template.md` into `context/specs/`, one per row of §4. The template fields map onto this table directly.
3. Fill `progress-tracker.md` from the same table, all rows `not started`.
4. From then on, **this file goes stale on purpose.** The specs and the tracker are live; this is the record of what was planned and why, which is useful in the report's collaboration section and useless as a source of truth.
