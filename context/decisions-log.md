# decisions-log.md

Every ambiguity, conflict, deviation and contract change, in one place. Written by whoever hits it — human or agent.

## When to write an entry

Triggers are listed in `workflow-rules.md` §5. In short: the spec was ambiguous, the spec conflicted with `project-context.md`, the spec could not be implemented as written, a contract needed to change, an open item in `project-context.md` §10 was hit, or the implementation deviated from the spec in any way at all.

## Rules

- **Append-only.** Never edit a past entry. To change a decision, write a new entry and mark the old one `superseded by DEC-NNN`.
- **IDs are sequential and never reused**: DEC-001, DEC-002, …
- **The contract rule.** If a decision changes anything specified in `project-context.md`, that file is edited **in the same pull request**, and the entry names the sections changed and the commit SHA. The log explains *why*; `project-context.md` states *what*. A decision recorded only here leaves the specification silently wrong.
- An entry with `Status: open` is a question for the two of us, not a decision. The spec it came from is `blocked` until the entry is resolved.
- Newest entries at the bottom. To find entries for a spec, grep its ID.

## Entry template

Copy this block, do not edit it in place.

```markdown
### DEC-NNN — <short title>

- **Date:** YYYY-MM-DD
- **Raised by:** <name, or "agent on SPEC-NN">
- **Spec:** SPEC-NN
- **Type:** ambiguity | conflict | deviation | contract change | scope
- **Status:** open | resolved | superseded by DEC-NNN

**Situation.** What was encountered, and where. Enough that someone reading it in three weeks knows what was in front of you.

**Decision.** What was decided. If `open`, write "none yet — needs a call from Aaron and/or Armaan" and state the options.

**Rationale.** Why this over the alternative. One or two sentences.

**Context impact.** Sections of `project-context.md` changed, or `none`.

**Commit.** <short SHA, or `pending`>
```

---

## Log

<!-- Entries below, oldest first. -->

### DEC-001 — Percolation baseline accepted by the facilitator

- **Date:** 2026-09-15
- **Raised by:** Aaron
- **Spec:** pre-spec — affects SPEC-07, SPEC-08
- **Type:** ambiguity
- **Status:** resolved

**Situation.** `project-context.md` §10.1 D5 kept the `PERCOLATION` `p_c` in the report as validation only, but marked the whole decision *contingent on the facilitator*: roadmap §10 Q1 asked whether recovering the known site-percolation threshold counts as "replicating a known baseline", given that percolation and the forest-fire model are not in the CITS4403 lecture notes. If the answer had been "the baseline must come from covered material", D5 was void and the validation strategy needed replanning from scratch — which would have voided SPEC-07 and SPEC-08 and rebuilt phase P2.

Asked at the Checkpoint 1 lab, Mon 14 Sep 2026. Aaron presented the breakdown: percolation as the baseline to validate against, then controlled burns and their spatial patterns, the critical-point-versus-amplitude question, and settlement modelling. The facilitator raised no objection and said he was happy with the approach.

**Decision.** D5 stands as written. The `PERCOLATION` validation is the project's replication component. SPEC-07 and SPEC-08 are unblocked; gate G−1 in `spec-plan.md` §5 is cleared.

**Rationale.** The contingency existed only to avoid building phase P2 on a baseline the unit would not accept. The facilitator accepted the approach as presented, with percolation named explicitly as the baseline.

**Caveat, recorded deliberately.** The approval was general rather than a specific answer to Q1 as worded. The constraint in D5 therefore still binds in full: the `PERCOLATION` threshold governs no `STUDY` result (§2 O4), must never appear in a table alongside a `STUDY` threshold, and the report must state once that the two are different by construction and not comparable.

**Context impact.** none — §10.1 D5 is unchanged; only its contingency is discharged.

**Commit.** pending

### DEC-002 — `run.py` experiment-to-spec mapping for placeholder errors

- **Date:** 2026-09-15
- **Raised by:** agent on SPEC-01
- **Spec:** SPEC-01
- **Type:** ambiguity
- **Status:** resolved

**Situation.** SPEC-01 specifies that `run.py` dispatches `--exp {0,1,2,2b,3,4,all}` to `src/experiments.py` entry points that each raise `NotImplementedError` naming the spec that will implement them, and gives only one concrete acceptance criterion: `--exp 0` must name SPEC-07. It does not say which spec ID the other five entry points (`1`, `2`, `2b`, `3`, `4`) should name.

**Decision.** Named each entry point after the spec whose title in `progress-tracker.md` matches that experiment: `1` → SPEC-13 (Experiment 1: geometry × budget), `2` → SPEC-14 (Experiment 2: threshold shift), `2b` → SPEC-15 (tail fitting, Experiment 2b), `3` and `4` → SPEC-16 (Experiments 3 and 4). `--exp all` runs every entry point in sequence, so it currently fails on the first (`0` → SPEC-07) until SPEC-07 lands.

**Rationale.** This mapping is already unambiguous from `progress-tracker.md`'s spec titles; no design choice was actually open, just a lookup SPEC-01 didn't spell out inline. Recorded so a future spec doesn't have to re-derive it or wonder whether the message wording is a contract.

**Context impact.** none — this is an implementation detail of an error message, not a schema, signature or invariant.

**Commit.** pending

### DEC-003 — No untreated `STUDY` threshold is measured before any `p_rel` grid needs it

- **Date:** 2026-09-15
- **Raised by:** agent (spec review pass)
- **Spec:** SPEC-12, SPEC-13, SPEC-14, SPEC-16
- **Type:** conflict
- **Status:** superseded by DEC-011

**Situation.** `project-context.md` §6.1 says the governing `p_c` for a `STUDY` experiment is the untreated (`condition="none"`, `b=0`) `STUDY` threshold at the matching `kappa`, and that resolving a `p_rel` against a missing row must raise. The only `STUDY` threshold measurement in §6.2 is Experiment 2. That leaves four gaps:

1. **Circular dependency.** The settlement pilot (§10.2 O1, `p_rel=+0.05`, `kappa ∈ {0,2}`) and the coarse Exp 1 pass (SPEC-12), and Experiment 1 itself (SPEC-13, `p_rel ∈ {−0.05, 0, +0.05}`, `kappa ∈ {0,2}`), all run **before** Experiment 2. Exp 2 has to come after them because it picks the "best 3 conditions" from Exp 1 (SPEC-14 depends on SPEC-13). So when SPEC-12 and SPEC-13 build their grids, no untreated `STUDY` row exists, and `resolve_p` raises by design.
2. **Experiment 2's `kappa` is not stated** in §6.2.
3. **Experiment 3** (§6.2) resolves `p_rel=+0.05` at `kappa ∈ {0,1,2,4}`. Nothing measures the untreated threshold at `kappa = 1` or `4`.
4. **Experiment 4** varies `beta ∈ {.7,.8,.9}` (and `f_treat`). §6.2 gives it no `p` at all. §6.1's "at the matching `kappa`" rule ignores `beta`, even though changing `beta` changes the threshold (the same reasoning as §2 O4).

**Decision.** None yet. Needs a call from Aaron and/or Armaan. Options:

- **(A) Reviewer's suggested fix.** Add an untreated `STUDY` threshold measurement (`condition="none"`, `b=0`, `edge` ignition, fine `p` sweep, FSS over `L ∈ {128,256,512}`) at every `kappa` a `p_rel` grid uses (0, 1, 2, 4), and at every `beta` Exp 4 needs if Exp 4 is threshold-relative. Schedule it before SPEC-12, as a new spec or a new experiment arm, with SPEC-12 depending on it. Edit §6.1/§6.2 to say so, and state Exp 2's `kappa` explicitly. Cost from the §6.3 timings: roughly 1.1 core-hours per sweep point per arm at `L=512`, so about 140 core-hours at `L=512` for six arms × 21 points. That is an overnight run and needs scheduling.
- **(B)** Move only Exp 2's `none` arm ahead of SPEC-12, at `kappa ∈ {0,2}`. Then specify Exp 3 at `kappa ∈ {1,4}` and Exp 4 in absolute `p`, or against the `kappa`-matched / `beta=0.8` threshold. This changes §6.2.
- **(C)** Replace `p_rel` with absolute `p` in the pilot, Exp 1, Exp 3 and Exp 4. This changes §6.2 and §10.2 O1, and gives up the threshold-relative design.

Under any option, Exp 4 also needs a stated `p` rule: absolute, against the `beta`-matched threshold, or against the `beta=0.8` threshold.

**Rationale.** Every fix changes §6.1/§6.2 (and possibly the §10.2 O1 pilot), which are contracts in `project-context.md`. Agents may not change them or guess (`workflow-rules.md` §5–§7). SPEC-12, SPEC-13, SPEC-14 and SPEC-16 are set `blocked` until this is decided.

**Context impact.** None yet. The decision will change §6.1 and §6.2, and possibly §10.2 O1.

**Commit.** pending

### DEC-004 — `pc_estimates.parquet` row identity and `resolve_p` selection

- **Date:** 2026-09-15
- **Raised by:** agent (spec review pass)
- **Spec:** SPEC-06 (also SPEC-07, SPEC-14, SPEC-15)
- **Type:** ambiguity
- **Status:** resolved — the I1 binding (SPEC-07 asserting the `L=512` `var_peak` row) is superseded by DEC-014; the row identity stands

**Situation.** §4.6 fixes the columns of `pc_estimates.parquet` (`regime, condition, b, kappa, L, p_c, p_c_stderr, method`) but not what one row is. The FSS crossing is a property of all `L` together, yet SPEC-07 expected "one row per `L`, plus the FSS crossing estimate". `resolve_p`'s key `(regime, condition, b, kappa)` would therefore match several rows, and SPEC-06 did not say which one wins.

**Decision.** No column is added or changed. For each measured `(regime, condition, b, kappa)`:

- one per-`L` row per lattice size, with `L` set and `method="var_peak"` (the `Var(burned_fraction)` peak cross-check);
- exactly one `method="fss_crossing"` row with `L` null (nullable `Int32`). This row holds the `estimate_pc` value and is the governing threshold.

`(regime, condition, b, kappa, method, L)` is unique, and `write_pc_estimates` raises on a duplicate. `resolve_p` selects only the `fss_crossing` row with null `L`, and raises on zero matches or more than one. SPEC-06 (Scope, Interface, Behaviour, ACs), SPEC-07 (Behaviour, ACs, I1), SPEC-14 (AC) and SPEC-15 (Behaviour) are aligned to this.

**Flag for a human.** `project-context.md` §7 I1 reads "Measured `p_c` at `L=512` within 0.01 of `P_C_LITERATURE`". Under this row identity, SPEC-07 asserts that against the `L=512` `var_peak` row, which is the literal reading. If I1 was meant to bind the FSS crossing (the value §6.1 treats as *the* measured `p_c`), then §7 I1's wording should change, and SPEC-07's AC with it. §4.6 also does not say `L` may be null; a line there may be wanted. Neither is edited here.

**Rationale.** This makes `resolve_p` deterministic and fail-loud without touching the §4.6 column list or the §5 schema. It keeps the per-`L` cross-check and the governing crossing estimate distinguishable, as §4.6 and SPEC-06 already required.

**Context impact.** None. §7 I1 and §4.6 wording are flagged above for a possible human edit.

**Commit.** pending

### DEC-005 — Experiment 2b conditions have no guaranteed measured threshold

- **Date:** 2026-09-15
- **Raised by:** agent (spec review pass)
- **Spec:** SPEC-15 (also SPEC-14)
- **Type:** conflict
- **Status:** superseded by DEC-012

**Situation.** §6.2 Exp 2b and §10.2 O4 set `p` to "the measured per-condition `p_c` from Experiment 2" for the conditions `none`, `random`, the best clustered condition from Exp 1, and `strips_perp`, all at `b=0.15`. But:

1. Experiment 2 measures only "best 3 conditions at `b=0.15`, plus `none`" (§6.2). `random`, `strips_perp` and the best clustered condition are not guaranteed to be among them. Without a row, §6.1 forbids inventing a `p`.
2. `strips_perp`'s `w` is not stated, and `w ∈ {4,8,16}` is swept per §10.1 D2.
3. `none` at `b=0.15` is rejected by §4.4 (`condition == "none"` requires `b == 0`).
4. Exp 2b's `kappa` is not stated. This is tied to DEC-003.

**Decision.** None yet. Needs a call from Aaron and/or Armaan. Options:

- **(A) Reviewer's suggested fix.** Widen Exp 2's condition set so every Exp 2b condition is measured: `none` at `b=0`, `random`, `strips_perp` at a stated `w`, and the best clustered condition, at `b=0.15`. Edit §6.2 Exp 2 and Exp 2b and the §10.2 O4 protocol. Cost: each extra condition adds roughly 23 core-hours at `L=512` on a 21-point sweep (§6.3 timings).
- **(B)** Restrict Exp 2b to conditions Exp 2 actually measured (`none` plus the selected three). This edits §6.2 Exp 2b and §10.2 O4, and may weaken SQ3's `random` / `strips_perp` contrast.

Under either option: state `none` at `b=0` in Exp 2b, fix `strips_perp`'s `w` (e.g. its best Exp 1 level, or `w=4`), and state `kappa`.

**Rationale.** §10.2 O4's protocol is described as "fixed in advance", and §6.2 is a contract. Changing the condition set, `w` or `b` is a `project-context.md` decision, not a spec edit. SPEC-15 is set `blocked`. SPEC-14 carries a pointer because option (A) changes its grid; it is already blocked by DEC-003.

**Context impact.** None yet. The decision will change §6.2 (Exp 2, Exp 2b) and §10.2 O4.

**Commit.** pending

### DEC-006 — Ownership of `RunResult` outcome fields

- **Date:** 2026-09-15
- **Raised by:** agent (spec review pass)
- **Spec:** SPEC-03, SPEC-04, SPEC-05
- **Type:** ambiguity
- **Status:** resolved

**Situation.** §4.1 defines `RunResult` as the §5 fields minus the config echo, but no spec was permitted to populate the outcome fields. SPEC-03 declared the dataclass and put derived metrics out of scope. SPEC-04 wrote the metric functions but was forbidden from touching `src/model.py`, and was told to raise a DEC if the per-step settlement-ring check needed a `run_fire` change, which it does. SPEC-05 assembled rows but also could not touch `src/model.py`. As a result, `burned_fraction`, `burned_fraction_of_fuel`, `spanned`, `reached_edge`, `settlement_reached` and `settlement_reached_step` had no owner, and neither did the per-step ring check.

**Decision.**

- **SPEC-03** populates the raw fields in `run_fire`: `n_cells`, `n_occupied`, `n_treated`, `ignition_y`/`ignition_x`, `burned_cells`, `still_burning_cells`, `steps`, `truncated`, `scar`. It declares the derived fields with default `None`.
- **SPEC-04** may now touch `src/model.py`, limited to `run_fire` result assembly and the per-step settlement-ring check. It populates the derived fields through the `metrics.py` functions, with the §3.5 nulls.
- **SPEC-05** copies the fields into the row and recomputes nothing.

No signature, field or column changes.

**Rationale.** SPEC-04 comes after SPEC-03 and owns the metric functions. Putting assembly there avoids a circular dependency (SPEC-03 cannot call functions that do not yet exist) and leaves §4.1 intact.

**Context impact.** none

**Commit.** pending

### DEC-007 — Settlement side carried in `geometry_params["settlement_side"]`

- **Date:** 2026-09-15
- **Raised by:** agent (spec review pass)
- **Spec:** SPEC-12 (also SPEC-02, SPEC-04, SPEC-09, SPEC-10, SPEC-11)
- **Type:** ambiguity
- **Status:** resolved

**Situation.** SPEC-12's pilot varies the settlement side over {8, 16, 32, 48}, but the side existed only as the module constant `SETTLEMENT_SIDE`. `Config` (§4.1) has no field for it, and SPEC-12 may only change the constant. Mutating a module constant per run would bypass `run_id`, break determinism across `Pool` workers, and violate the §8 ban on global mutable state. The pilot had no way to carry the side into a run.

**Decision.** Add an optional key `geometry_params["settlement_side"]` (int), defaulting to `SETTLEMENT_SIDE` when absent.

- **SPEC-02** reads it for placement and always passes the resolved value into `generate`'s `**params`.
- **SPEC-04** reads it for the settlement ring.
- **SPEC-11** (`buffer`) reads it from `params`.
- **SPEC-09 and SPEC-10** generators accept and ignore it.
- **SPEC-12**'s pilot sets it per config, so each side hashes to a distinct `run_id`. SPEC-12's may-touch list states that no other model change is needed.

`geometry_params` is already a free dict in §4.1 and a JSON string in §5, so no signature or column changes.

**Flag for a human.** §3.6 (and the §4.2 params table) do not mention this key. A one-line addition to `project-context.md` §3.6 documenting it may be wanted; that is for a human to add, and it is not done here. Also note that a config setting the key explicitly to the default hashes to a different `run_id` than one omitting it, so each experiment should pick one convention.

**Rationale.** This is the smallest carrier that works inside the existing contracts, keeps `run_fire` pure in `cfg`, and gives the pilot distinct `run_id`s.

**Context impact.** None. A §3.6 line is suggested above, pending a human.

**Commit.** pending

### DEC-008 — `phi` passed to geometry generators

- **Date:** 2026-09-15
- **Raised by:** agent (spec review pass)
- **Spec:** SPEC-02, SPEC-10 (also SPEC-09, SPEC-16)
- **Type:** ambiguity
- **Status:** resolved

**Situation.** §4.2 builds `strips_perp` bands "perpendicular to `phi`", but `generate(condition, rng, occupied, n_treat, **params)` never received `phi`. SPEC-02's call site passed only the geometry parameters, and SPEC-10 did not require strips off the axes. I11 (SPEC-16) compares strips at `phi=π/4` "with the geometry rotated to match", which was therefore unimplementable.

**Decision.**

- **SPEC-02's call site** is `generate(cfg.condition, rng, occupied, n_treat, **{**cfg.geometry_params, "phi": cfg.phi, "settlement_side": side})`. A `"phi"` key inside `geometry_params` raises, because `cfg.phi` is the single source.
- **SPEC-10** builds both strip conditions at any `phi`, including `π/4`, with a test at `phi ∈ {0, π/4, π/2}`.
- **Other generators** ignore `phi`, and SPEC-09 requires every generator to tolerate the key.

The §4.2 signature is unchanged.

**Rationale.** `phi` already lives on `Config`, and `**params` is the existing channel into generators. Passing it there makes §4.2's construction and I11 implementable without touching a contract.

**Context impact.** none

**Commit.** pending

### DEC-009 — Illustrative scar capture moved from SPEC-17 to SPEC-13

- **Date:** 2026-09-15
- **Raised by:** agent (spec review pass)
- **Spec:** SPEC-17, SPEC-13 (also SPEC-05)
- **Type:** conflict
- **Status:** resolved

**Situation.** SPEC-17 put illustrative scar capture, which calls `run_fire(capture_scar=True)`, in a "separate step" alongside `figures/make_figures.py`, and its AC grep tolerated `run_fire` in that file. That contradicts `project-context.md` §9 and `workflow-rules.md` §9: `make_figures.py` reads from `results/` only and never calls `run_fire`. SPEC-17 is also barred from `src/`, so it had nowhere legitimate to put the capture.

**Decision.** Capture moves to SPEC-13:

- configs from Exp 1's grid, named explicitly in `src/experiments.py`;
- `run.py --exp scars`, included in `--exp all`;
- writes `results/scars_illustrative.npz` (committed, under 5 MB).

SPEC-17 only reads the npz. Its AC and verification grep now require that `run_fire` and `capture_scar` do not appear in `make_figures.py`. SPEC-05's note is updated to point at SPEC-13.

**Rationale.** SPEC-13 rather than SPEC-16: SPEC-16 is first in the descope order, while the scar figure is the qualitative-evidence deliverable SPEC-17 says not to drop. SPEC-13 is never descoped, is on the same owner's track, is already a SPEC-17 dependency, and its grid supplies the configs.

**Context impact.** none

**Commit.** pending

### DEC-010 — A space-time view needs per-step history that `RunResult` does not carry

- **Date:** 2026-09-15
- **Raised by:** agent (spec review pass)
- **Spec:** SPEC-17
- **Type:** contract change
- **Status:** superseded by DEC-013

**Situation.** SPEC-17 scoped "a space-time view" alongside the illustrative scars. §4.1 `RunResult.scar` is only the final state grid. No per-step state and no per-cell ignition time is recorded, and `make_figures.py` may not run the model (§9). A final grid alone cannot produce a space-time view, so the figure is not buildable under the current contract.

**Decision.** None yet. Needs a call from Aaron and/or Armaan. The space-time view is removed from SPEC-17's scope until this is decided. Options:

- **(A)** Extend §4.1 so that `capture_scar=True` also returns a per-cell ignition-step grid (e.g. `int32[L, L]`, null or `-1` where unburnt; the representation needs deciding), which SPEC-13 stores in the npz. This is a §4.1 contract change: edit `project-context.md`, SPEC-03 (return it), SPEC-13 (store it) and SPEC-17 (plot it).
- **(B)** Drop the space-time view, so the qualitative-evidence criterion rests on the final scars alone.
- **(C)** Produce it outside `make_figures.py` with a separate script. This conflicts with §4.7/§9's rule that every report figure comes from the single entry point and `results/`, so it is not recommended.

**Rationale.** Any way of restoring the view changes a §4.1 contract, which agents may not do (`workflow-rules.md` §6–§7). SPEC-17 is not blocked; the rest of its scope stands.

**Context impact.** None yet. Option (A) would change §4.1.

**Commit.** pending

### DEC-011 — Experiment 0b: untreated `STUDY` thresholds measured before any `p_rel` grid

- **Date:** 2026-09-15
- **Raised by:** Aaron (decision); applied to the specs by agent
- **Spec:** new SPEC-19; SPEC-12, SPEC-13, SPEC-14, SPEC-16 (also SPEC-15, SPEC-18)
- **Type:** contract change
- **Status:** resolved — supersedes DEC-003

**Situation.** DEC-003: no untreated `STUDY` threshold existed before the pilot, Experiment 1 and Experiment 3 needed one. Experiment 2's `kappa` was unstated, and Experiment 4 varied `beta` with no `p` rule.

**Decision.** DEC-003 option (A), trimmed:

- **New Experiment 0b, owned by new SPEC-19** (`depends_on: [SPEC-05, SPEC-06]`). SPEC-12 now depends on it. Settings: `STUDY`, `condition="none"`, `b=0`, `kappa ∈ {0,1,2,4}`, `phi=-π/2`, edge ignition, `L ∈ {128,256,512}`, R=500. Each arm is a 21-point sweep (±0.05, step 0.005) around a centre found by an `L=128` pre-pass. It is wired as `run.py --exp 0b`, ahead of Experiment 1.
- **Edge-ignition wind convention.** `STUDY` threshold sweeps use `phi=-π/2`, so the ignited row 0 is the upwind edge. A 90° lattice rotation is an exact symmetry of the rule (Moore neighbourhood, diagonal factor, von Mises kernel). So for untreated fuel the threshold equals the one at `phi=0`, and `pc_estimates.parquet` needs no `phi` column. §3.5's row-0 definition is unchanged.
- **Experiment 2 runs at `kappa=0`, `phi=-π/2`.** Its untreated reference is Experiment 0b's `kappa=0` row, so it drops its own `none` arm.
- **Experiment 4 runs at `kappa=2` with one absolute `p`.** `p` = the Experiment 0b `kappa=2` threshold + 0.05, held fixed across every `beta`, with `p_rel` null. No threshold arm is measured per `beta`.

**Rationale.** Option (B) collapses into (A), because Experiment 3 needs `kappa` 1 and 4 anyway. Option (C) abandons the threshold-relative design. Sharing the `kappa=0` arm with Experiment 2 saves about 26 core-hours. A sensitivity check should hold the landscape fixed while `beta` varies, so Experiment 4 needs no extra arms.

**Context impact.** `project-context.md` §3.5 (edge ignition used by Exp 0, 0b, 2), §4.7 and §9 (`--exp 0b`), §6.1 (Exp 0b bullet, governing threshold, wind convention), §6.2 (Exp 0b row, Exp 2 row, Exp 4 row, Exp 4 note), §6.3 (cost), §10.2 O1 (pilot resolves against Exp 0b).

**Commit.** pending

### DEC-012 — Experiment 2 condition set fixed in advance; Experiment 2b conditions all measured

- **Date:** 2026-09-15
- **Raised by:** Aaron (decision); applied to the specs by agent
- **Spec:** SPEC-14, SPEC-15 (also SPEC-13)
- **Type:** contract change
- **Status:** resolved — supersedes DEC-005

**Situation.** DEC-005: Experiment 2b's conditions (`random`, the best clustered condition, `strips_perp`) were not guaranteed to have an Experiment 2 threshold. `strips_perp`'s `w` was unset, `none` at `b=0.15` was illegal, and `kappa` was unstated.

**Decision.**

- **Experiment 2's "best 3 conditions + `none`" is replaced by a set fixed in advance.** At `b=0.15`, `kappa=0`, `phi=-π/2` it measures `random`, the best `patches` level and the best `strips_perp` level. `none` comes from Experiment 0b (DEC-011).
- **Selection rule, stated before Experiment 1 runs.** Lowest mean `burned_fraction` in Experiment 1 at `b=0.15`, `p_rel=+0.05`, `kappa=0`, taken separately among `k ∈ {4,8,16}` and among `w ∈ {4,8,16}`.
- **Experiment 2b conditions:**
  - `none` at `b=0`, with `p` from Experiment 0b `kappa=0`;
  - `random`, `patches(k*)`, `strips_perp(w*)` at `b=0.15`, each with `p` from its own Experiment 2 row.

  All at `kappa=0`, `phi=-π/2`.
- **Key uniqueness.** Only one level per condition family is ever thresholded, so the `(regime, condition, b, kappa)` key stays unique even though it has no `k`/`w` column.

**Rationale.** It keeps four sweep arms, the same as before, so it costs nothing extra; the untreated arm moves to Experiment 0b. It guarantees every Experiment 2b condition a measured `p`. It keeps a single slot chosen from the data in each clustered family, while the rule itself stays fixed in advance, as §10.2 O4 requires.

**Context impact.** `project-context.md` §6.2 (Exp 2 row, Exp 2b row, selection rule note), §10.2 O4 (Experiment 2b protocol).

**Commit.** pending

### DEC-013 — `RunResult.ignition_step` for the space-time view

- **Date:** 2026-09-15
- **Raised by:** Aaron (decision); applied to the specs by agent
- **Spec:** SPEC-03, SPEC-13, SPEC-17
- **Type:** contract change
- **Status:** resolved — supersedes DEC-010

**Situation.** DEC-010: SPEC-17's space-time view needs per-step history, but `RunResult` carried only the final state grid.

**Decision.** DEC-010 option (A). `RunResult` gains `ignition_step: np.ndarray | None`: an `int32[L, L]` grid of the step each cell first became `BURNING` (0 for ignition cells, `-1` if never). It is populated only when `capture_scar=True` and is never written to a parquet, so the §5 rule against sentinels does not apply.

- **SPEC-03** fills it inside the step loop.
- **SPEC-13** stores it in `results/scars_illustrative.npz` alongside each scar.
- **SPEC-17** plots the space-time view from it.

**Rationale.** SPEC-03 has not started, so adding the field now costs one assignment per step on the capture path. Adding it after SPEC-03 merges would reopen the step loop. It restores a second qualitative-evidence figure.

**Context impact.** `project-context.md` §4.1 (`RunResult` field and the note under it).

**Commit.** pending

### DEC-014 — I1 binds the finite-size-scaling crossing, not the `L=512` row

- **Date:** 2026-09-15
- **Raised by:** Aaron (decision); applied to the specs by agent
- **Spec:** SPEC-07
- **Type:** contract change
- **Status:** resolved — supersedes the I1 part of DEC-004

**Situation.** DEC-004 flagged that §7 I1 ("measured `p_c` at `L=512` within 0.01 of `P_C_LITERATURE`") read literally binds the single-size `var_peak` row. A single-size effective threshold is offset from the infinite-lattice value by roughly `a·L^(-1/ν)`, with `ν = 4/3`. At `L=512` that is about `0.009·a`, the same order as the 0.01 tolerance, so I1 could fail on a correct model.

**Decision.** I1 asserts the `fss_crossing` estimate across `L ∈ {128,256,512}` within 0.01 of `P_C_LITERATURE`. The `L=512` `var_peak` value is reported as a cross-check and is not asserted. SPEC-07's objective, acceptance criteria and invariant are updated to match.

**Rationale.** The crossing is the estimator of the infinite-lattice threshold, which the literature value describes, and §6.1 already treats it as *the* measured `p_c`.

**Context impact.** `project-context.md` §7 I1.

**Commit.** pending

### DEC-015 — Documenting `settlement_side` and nullable `L` in `project-context.md`

- **Date:** 2026-09-15
- **Raised by:** Aaron (decision); applied to the specs by agent
- **Spec:** SPEC-12, SPEC-13, SPEC-16 (follow-up to DEC-004, DEC-007)
- **Type:** contract change
- **Status:** resolved

**Situation.** DEC-007 introduced `geometry_params["settlement_side"]`, but §3.6 did not document it. A config that writes the default explicitly also hashes to a different `run_id` from one that omits it. DEC-004 introduced a null `L` on `fss_crossing` rows that §4.6 did not mention.

**Decision.**

- **§3.6** documents the key and its default.
- **Convention:** grid builders for `settlement=True` runs always set the key explicitly, and runs without a settlement omit it. SPEC-13 and SPEC-16 state this.
- **§4.6** documents the row identity and the nullable `L`.

**Rationale.** Keeps the specification the single source of what these values mean, and makes `run_id` independent of how a builder happened to spell the default.

**Context impact.** `project-context.md` §3.6, §4.6.

**Commit.** pending

### DEC-016 — Jupyter notebooks adopted as the presentation layer

- **Date:** 2026-09-20
- **Raised by:** Aaron 
- **Spec:** SPEC-08, SPEC-17, SPEC-18, SPEC-20, SPEC-21
- **Type:** contract change
- **Status:** resolved

**Situation.** The unit's technical specification and rubric were released on 18 September, after the repository structure and analysis workflow were settled. The code rubric assesses "Use of Jupyter Notebook as a Communication Tool" as one of seven criteria. The project had no notebooks: `figures/make_figures.py` was the sole presentation layer, and SPEC-17's objective explicitly required "no notebook anywhere in the chain".

**Decision.** A `notebooks/` directory is added, holding three numbered notebooks that **consume** the SPEC-08 figure registry rather than duplicating it:

- `01-model-and-validation.ipynb` — SPEC-20, owner Aaron, depends on SPEC-08
- `02-treatment-geometries.ipynb` — SPEC-21, owner Armaan, depends on SPEC-17
- `03-thresholds-and-tails.ipynb` — SPEC-21

`figures/make_figures.py` remains the canonical figure producer and the thing SPEC-18's clean-clone gate runs. Notebooks add prose, equations and interpretation on top of it. `jupyter` and `ipykernel` are added to `requirements.txt`; the `workflow-rules.md` §7 no-new-dependency rule is scoped to the **model**, which stays Python + NumPy only.

The split into two specs rather than one is deliberate: `01` depends on SPEC-08 (Sprint 2) and `02`/`03` on SPEC-17 (Sprint 4), so bundling them would block the early notebook behind the late one. It also gives each team member an owned notebook PR, which the rubric assesses individually.

**Rationale.** The existing architecture already separates simulation from presentation — experiments write parquet, figures read parquet — so a notebook layer sits on the existing seam without touching `src/`, the results schema, any experiment spec, or any invariant. SPEC-08's builders return a `Figure`, which displays inline unchanged, so no interface changes. The cost is authoring, not engineering.

**Context impact.** `project-context.md` §9 (layout gains `notebooks/`; the figure clause is restated to scope it to `make_figures.py`).

**Commit.** pending

### DEC-017 — Notebooks are committed with outputs stored

- **Date:** 2026-09-20
- **Raised by:** Aaron
- **Spec:** SPEC-08, SPEC-17, SPEC-20, SPEC-21
- **Type:** contract change
- **Status:** resolved

**Situation.** `workflow-rules.md` §7 forbids committing generated figures, and §9 keeps `figures/out/` gitignored. A notebook committed with its outputs stored is, in effect, committed figures. A notebook committed with outputs stripped opens as empty cells for anyone who does not run it.

**Decision.** The three notebooks are committed **with outputs stored**, executed top to bottom with sequential execution counts. This is an explicit exception to §7, scoped to `notebooks/*.ipynb` and to nothing else; `figures/out/` stays gitignored and generated figures stay uncommitted. `.ipynb_checkpoints/` is gitignored.

Consequently the "re-running produces byte-identical output" criterion in SPEC-08 and SPEC-17 is scoped to the **figure files produced by `make_figures.py`**, not to notebook files, whose metadata will never be byte-stable.

**Rationale.** A marker opening a stripped notebook sees no analysis. The criterion being assessed is communication, and an unexecuted notebook communicates nothing. The diff noise is real but bounded: three files, touched at the end of the project, kept small by reusing registry figures rather than embedding large images.

**Context impact.** `project-context.md` §9 (the notebook clause states the exception).

**Commit.** pending

### DEC-018 — Notebook `01` may call `run_fire` for a live demonstration; `make_figures.py` still may not

- **Date:** 2026-09-20
- **Raised by:** Aaron
- **Spec:** SPEC-20 (and SPEC-21 by exclusion)
- **Type:** contract change
- **Status:** resolved

**Situation.** `project-context.md` §9 and `workflow-rules.md` §9 state that the presentation layer reads from `results/` and never calls `run_fire`. The rubric asks for interactive elements in the notebook, and the project demonstration requires the model ready to run live. A notebook that only replays stored figures satisfies neither. Read literally, the existing rule forbids the live demonstration and an agent implementing SPEC-20 would hit a §6 stop condition.

**Decision.** The prohibition is scoped to `figures/make_figures.py`, which **must never call `run_fire`**, unchanged. `notebooks/01-model-and-validation.ipynb` may call `run_fire` in **exactly one cell**, bounded at `L ≤ 128`, with a fixed seed, completing in under ten seconds, labelled in markdown as a demonstration. No reported quantity may come from it. Notebooks `02` and `03` may not call `run_fire` at all; the geometry gallery's calls to `geometries.generate` are not simulation and are permitted.

**Rationale.** The rule exists so that no reported number can come from an unrecorded run. A seeded, bounded, explicitly-labelled demonstration that feeds nothing into the report does not threaten that, and it is what makes the notebook a demonstration rather than a slideshow. Scoping the exception to one cell in one notebook, checkable by a grep in SPEC-20's verification, keeps it from widening.

**Context impact.** `project-context.md` §9 (the figure clause and the notebook clause).

**Commit.** pending

### DEC-019 — Scar metrics count `BURNT` cells only; still-burning cells at truncation are excluded

- **Date:** 2026-09-26
- **Raised by:** Armaan (agent-assisted, SPEC-04)
- **Spec:** SPEC-04
- **Type:** ambiguity
- **Status:** resolved

**Situation.** §3.5 defines `spanned` and `reached_edge` as "did any cell ... burn", and SPEC-04 says scar statistics are computed over `BURNT` cells, but neither says what to do with cells still `BURNING` when a run is truncated (§3.7). SPEC-03 already settled the same question for `burned_cells` (`BURNT` only; folding in `still_burning` was the prototype bug).

**Decision.** Every function in `src/metrics.py` that reads a state grid — `spanned`, `reached_edge`, `scar_second_moments`, `scar_centroid` — counts `BURNT` cells only, matching `burned_cells`. A truncated run's still-burning cells contribute to `still_burning_cells` and nothing else. For the experiments this is moot: G2 requires `truncated` false throughout, and with `tau=1` every ignited cell is `BURNT` at extinction.

**Rationale.** One rule for all scar-shaped quantities, and the same rule SPEC-03 chose, so `burned_fraction` and `spanned` can never disagree about which cells count.

**Context impact.** none

**Commit.** pending

### DEC-020 — Settlement ring check includes step 0

- **Date:** 2026-09-26
- **Raised by:** Armaan (agent-assisted, SPEC-04)
- **Spec:** SPEC-04
- **Type:** ambiguity
- **Status:** resolved

**Situation.** §3.6 says `settlement_reached` is True iff a ring cell enters `BURNING` "at any time during the run". Under `"random_cell"` ignition the ignition cell may itself lie on the ring (§3.6 forbids excluding regions from ignition), in which case it is `BURNING` at `t=0` before any step runs. SPEC-04 specifies only the per-step check.

**Decision.** `run_fire` checks the ring against the initial state before the loop and, if a ring cell is already burning, sets `settlement_reached=True`, `settlement_reached_step=0`. The per-step check then tests only newly-ignited cells in the current bounding box, so it costs one small boolean `and` per step and never touches `rng`.

**Rationale.** A fire that starts on the settlement's doorstep has reached it; recording it as step 0 keeps `settlement_reached_step` a true first-reach time rather than a first-reach-after-step-1 time.

**Context impact.** none

**Commit.** pending

### DEC-021 — SPEC-03's `test_derived_fields_default_none` rewritten (may-touch deviation)

- **Date:** 2026-09-26
- **Raised by:** Armaan (agent-assisted, SPEC-04)
- **Spec:** SPEC-04 (test belongs to SPEC-03)
- **Type:** deviation
- **Status:** resolved

**Situation.** `tests/test_step.py::test_derived_fields_default_none` (SPEC-03) asserted that `run_fire` returns every derived field as `None`. SPEC-04's acceptance criteria require the opposite (DEC-006), so the test fails the moment SPEC-04 is implemented. `tests/test_step.py` is not in SPEC-04's may-touch list. The `workflow-rules.md` §6 stop condition ("an invariant fails and the fix lies outside your spec's permitted files") does not strictly apply — it is a unit test, not an invariant, and the fix is a direct consequence of DEC-006 — but the file boundary is crossed.

**Decision.** The test is renamed `test_derived_fields_dataclass_defaults_are_none` and now asserts what SPEC-03 actually owns: the `RunResult` *declaration* defaults those fields to `None`. The populated-by-`run_fire` behaviour is tested in `tests/test_metrics.py`. No other line of `tests/test_step.py` changed beyond the two imports the new test needs.

**Rationale.** Leaving a permanently-failing test, or deleting it silently, would both be worse than a one-function edit that keeps SPEC-03's intent and points at where the behaviour is now tested. Flagged here so the SPEC-03 owner sees it in review.

**Context impact.** none

**Commit.** pending

### DEC-022 — I5 is measured in a bounded-time design; I4 operating point fixed

- **Date:** 2026-09-26
- **Raised by:** Armaan (agent-assisted, SPEC-04)
- **Spec:** SPEC-04
- **Type:** ambiguity
- **Status:** resolved

**Situation.** §7 I5 states the mean scar centroid projection on `phi` is strictly increasing over `kappa ∈ {0, 1, 2, 4}` but fixes no operating point, and SPEC-04 says only "L=128" and "raise the replicate count before concluding the wind kernel is wrong". Measured on runs to extinction the invariant does **not** hold at any fuel density tried, and not marginally (L=128, `phi=0`, `"random_cell"`, STUDY defaults; mean projection in cells ± se):

| `p` | `max_steps` | R | κ=0 | κ=1 | κ=2 | κ=4 | monotone |
|---|---|---|---|---|---|---|---|
| 0.50 | ∞ | 60 | −0.9 ± 3.8 | 30.0 ± 3.3 | 20.6 ± 2.8 | 8.6 ± 1.1 | no |
| 0.60 | ∞ | 60 | −6.8 ± 4.7 | 29.8 ± 2.8 | 28.8 ± 3.2 | 23.4 ± 3.0 | no |
| 0.70 | ∞ | 100 | −1.5 ± 3.7 | 9.9 ± 3.2 | 39.2 ± 2.3 | 37.8 ± 2.5 | no |
| 1.00 | 30 | 100 | −0.3 ± 0.6 | 4.3 ± 0.5 | 14.4 ± 0.5 | 16.8 ± 0.6 | **yes** |
| 0.80 | 30 | 100 | −0.1 ± 0.5 | 8.0 ± 0.5 | 15.8 ± 0.5 | 16.7 ± 0.5 | yes (marginal) |

The unbounded failure is not the kernel. Two boundary effects dominate: above threshold a `kappa=0` fire burns the whole lattice, so its centroid is the lattice centre whatever the ignition, and a `kappa=4` plume with mean-1-normalised weights has near-zero crosswind/upwind spread, so it either dies in a sparse fuel bed or runs into the downwind edge, both of which cap its displacement. Neither is what I5 is about.

**Decision.**

- **I5** runs at `p=1.0`, `max_steps=30`, `L=128`, `phi=0`, `"random_cell"`, R=200 per `kappa`, STUDY defaults otherwise (`beta=0.8`, so the runs are still stochastic). The test asserts strict monotonicity of the four means and that the κ=4 − κ=0 gap exceeds ten standard errors. The runs are truncated by construction; the test uses `max_steps` for the purpose the field exists (§3.7).
- **I4** runs at `p=0.55`, `L=128`, `kappa=0`, R=200, to extinction; mean burned fraction ≈ 0.5 so scars are partial and the isotropy check is on real shapes. It asserts the 99% CI of mean(`var_x − var_y`) contains 0 and that mean scar variance exceeds 100 (non-trivial scars). At R=40 the same point read 13 ± 5, which is what the spec's "raise the replicate count first" clause is for; at R=200 it is 1.9 ± 2.4.
- Both tests carry `@pytest.mark.slow` and take about 5 s and 2.5 s. The `slow` marker is **not registered** because `pytest.ini` is outside SPEC-04's may-touch list; pytest warns but runs. A three-line `pytest.ini` registering it is wanted and is a human's to add.

**Rationale.** A bounded-time measurement is the only one that isolates the wind kernel from the lattice boundary and from extinction, which are the subjects of other invariants (I1, I9) and of the experiments themselves. Reading I5 as a statement about the kernel is also the only reading under which it is an invariant at all rather than a result.

**Context impact.** none — §7 I5's wording is unchanged; the operating point is recorded here and in the test docstring. If the team prefers §7 to state the operating point, that is a one-line human edit.

**Commit.** pending

### DEC-023 — I7's "over a results frame" half deferred to SPEC-05

- **Date:** 2026-09-26
- **Raised by:** Armaan (SPEC-09)
- **Spec:** SPEC-09 (and SPEC-05)
- **Type:** ambiguity
- **Status:** resolved

**Situation.** §7 I7 reads "assert in the generator and again over the results frame", and SPEC-09 owns the I7 test. There is no results frame until the harness (SPEC-05) writes one, and SPEC-09 may not touch `src/experiments.py`.

**Decision.** `tests/test_invariants.py::test_i7_budget_parity` covers the generator half: `check_mask` asserts the budget live inside `generate`, and the test re-checks `n_treated` against `round(b * n_occupied)` end-to-end through `run_fire` for every condition in `geometries.IMPLEMENTED`. The frame half — the same check over every row of a written parquet — is SPEC-05's to add when the frame exists; it can be a second assertion in the same test function.

Two smaller points from the same spec, recorded here rather than in separate entries:

- `generate` validates the condition string **before** the `n_treat == 0` early return, so an unknown condition raises even at `b = 0`. SPEC-01's stub returned all-False for any string at zero budget. An unknown string is not a condition, and failing at config time is cheaper than failing at the first `b > 0` run.
- `geometries.IMPLEMENTED` (the conditions with a registered generator) and `geometries.CONDITIONS` (every condition the schema knows) are module-level tuples so SPEC-10 and SPEC-11 extend test coverage by registering a generator, not by editing SPEC-09's tests. No §4.2 signature changes.

**Numbering note.** DEC-019 to DEC-022 are on the SPEC-04 branch, in flight at the same time as this one. Whichever merges second will need a trivial conflict resolution at the end of this file.

**Context impact.** none

**Commit.** pending

### DEC-024 — Strips: bisection then random trim; sub-band budgets place one thinned band

- **Date:** 2026-09-26
- **Raised by:** Armaan (SPEC-10)
- **Spec:** SPEC-10
- **Type:** ambiguity
- **Status:** resolved

**Situation.** §4.2 builds the strip conditions by bisecting on band spacing "until the occupied-cell count hits `n_treat`". Two things the construction does not say. (1) The count is a step function of spacing: at `phi = 0` every band edge sits on an integer column, so moving the spacing changes the count by whole columns (~140 occupied cells at `L=256`, `p=0.55`), while the shared tolerance at `b=0.15` is ~55 cells. Bisection alone cannot always land within tolerance. (2) Below one band's worth of budget no spacing hits `n_treat` at all: at `w=16`, `b=0.05`, `L=256` a single full band holds ~1.25× the budget. SPEC-10's notes ask for this to be decided and stated rather than left to the bisection.

**Decision.**

- **Spacing is bounded below by `w`.** Touching bands are full coverage, which already exceeds any budget, so bands never overlap and the "spacing below `w`" case in SPEC-10's notes cannot arise.
- **Bisection then trim.** The bisection (64 steps, or fewer when it lands exactly) finds the largest spacing whose count is still `>= n_treat`; the excess is then un-treated uniformly at random inside the bands, so the realised count is exact. This is the rule §4.2 already gives `patches` for its excess, applied to strips. It costs at most one band-edge's worth of cells: measured over the Experiment 1 grid at `L=256` (20 seeds, `phi = -π/2`), mean 0.3–3.2 % of `n_treat`, worst 7.6 %, with the largest values at `b=0.05` where there are fewest bands.
- **Sub-band budgets.** If a single full band already holds `>= n_treat` occupied cells, one band of width `w` is placed at a uniform random position along the band coordinate, fully on the grid, and thinned at random to `n_treat`. The alternative — letting the bisection push the spacing past the grid so the last band slides off the far edge — was implemented first and rejected: it pins the band to the downwind edge on every replicate, which under `"random_cell"` ignition makes that treatment protect nothing for a reason that has nothing to do with geometry. In the Experiment 1 grid this branch is taken **only** for `strips_perp`/`strips_para` at `w=16`, `b=0.05` (all 20 of 20 seeds at both `p=0.45` and `p=0.70`), where the band is thinned by ~25 %. No other `(w, b)` cell reaches it.
- **Phase.** One `rng.random()` draw per replicate is the phase: offset `phase * spacing` in the bisection branch, position `phase * (extent - w)` in the single-band branch. The bracket search and bisection are pure in that draw; the trim is the only other rng use.
- **Raises rather than loops.** The bracket search doubles the spacing at most 80 times and the bisection runs at most 64 steps; either limit raises `RuntimeError`.

**Flag for the report.** `strips(w=16)` at `b=0.05` is a single band with a quarter of its cells removed, which is a different object from the multi-band pattern at every other budget. Methods should say so in one line; the clustering-scale reading of that one cell is weaker than the rest of the axis.

**Context impact.** none — §4.2's construction text is unchanged; this records how its two silent cases are resolved.

**Commit.** pending

### DEC-025 — Defaults and placement details for the clustered generators

- **Date:** 2026-09-26
- **Raised by:** Armaan (SPEC-10)
- **Spec:** SPEC-10 (touches SPEC-09's tests)
- **Type:** deviation
- **Status:** resolved

Small decisions from the same spec, recorded together.

- **`patches` defaults `k=4`; strips default `phi=0.0` when the key is absent.** §4.2 gives `w` a default of 4 "so a config is constructible" but gives `k` none, and DEC-008 says the call site always passes `phi`. SPEC-09's I7 and I8 tests iterate `geometries.IMPLEMENTED` calling `generate` with no parameters at all, and SPEC-10 may not edit them. Both defaults mirror an existing default (`w=4`, `Config.phi=0.0`) and are never relied on by an experiment grid, which always sets `k`/`w` explicitly and passes `cfg.phi`.
- **`patches` blocks are placed wholly inside the grid** — top-left uniform on `[0, L-k]` per axis — so every block covers exactly `k*k` cells. §4.2 says "uniformly random top-left positions" without saying whether a block may hang off the edge; whole blocks keep the clustering scale honest at the boundary. `k > L` raises.
- **`geometries.CLUSTERING_LEVELS`** is a tuple of the nine `(condition, params)` levels of §6.2 so an experiment grid enumerates them from one place. Additive; no signature change.
- **SPEC-09's `test_reserved_params_are_accepted_and_ignored`** asserted every implemented condition returns the same mask with and without `phi`/`settlement_side`. That is false for strips by construction (DEC-008). It is split into "accepted" (every condition) and "ignored" (`none`, `random`, `patches`), with strips' use of `phi` tested on its own. `tests/test_geometries.py` is in SPEC-10's may-touch list.
- **Realised counts are exact** for all nine levels, not merely within tolerance, because every path ends in the shared trim. The budget helper's tolerance therefore only ever bites if a future generator skips the trim.

**Context impact.** none

**Commit.** pending

### DEC-026 — Buffer: block placement, unachievable budgets, and SPEC-09's tests made extensible

- **Date:** 2026-09-26
- **Raised by:** Armaan (SPEC-11)
- **Spec:** SPEC-11 (touches SPEC-09's tests on the SPEC-09 branch)
- **Type:** deviation
- **Status:** resolved

- **Block placement is re-derived, not imported.** The generator locates the block as rows/cols `[L//2 - side//2, L//2 - side//2 + side)` from `params["settlement_side"]`, the same arithmetic `initial_grids` uses. It does not import `SETTLEMENT_SIDE` or infer the block from `occupied` (SPEC-11 interface contract, DEC-007). A test checks the generator's first ring against the block `initial_grids` actually places for sides 8, 16, 32 and 48. A missing `settlement_side` key raises; there is no default, because a buffer around nothing is the failure the spec says to assert against.
- **Ring 0 is never treated**, whatever `occupied` says there. In a real run the block is `SETTLEMENT` and unoccupied; if a caller passes a field with occupied cells inside the block they are skipped.
- **Unachievable budgets raise `ValueError`** naming the shortfall: if fewer occupied cells lie outside the block than `n_treat`, the rings run off every edge without reaching the budget. `generate` already bounds `n_treat` by the total occupied count, so this can only happen when cells inside the block count toward that total, i.e. an inconsistent field.
- **The outer ring alone is filled at random**; inner rings stay complete. The realised count is exact, so the shared tolerance never bites. One `rng.choice` per call.
- **SPEC-09's I7 and I8 tests were amended on the SPEC-09 branch** (commit "test(spec09): I7 and I8 written to be extended by settlement conditions"), not from this branch: I7 now sets `settlement=True` for `buffer` (§4.4 rejects the config otherwise) and I8 carves the default block out of its random field and passes `phi`/`settlement_side` as the call site does. SPEC-11's frontmatter says to raise a DEC rather than edit that file; the file was edited on the spec that owns it, and SPEC-10 and SPEC-11 were rebased on top. SPEC-09's `test_unimplemented_condition_with_budget_raises_not_implemented` (an empty parametrisation once every condition exists) became an assertion that `IMPLEMENTED == CONDITIONS`, and its "reserved params are accepted" case uses a 64-cell grid so a 32-cell block leaves room for rings. Both are in `tests/test_geometries.py`, which SPEC-11 may touch.

**Context impact.** none

**Commit.** pending

### DEC-027 — `n_treat == 0` early return lives in `generate()`, not in each generator

- **Date:** 2026-09-27
- **Raised by:** Aaron (review of SPEC-09, SPEC-10 and SPEC-11)
- **Spec:** SPEC-09 (also applies to SPEC-10 and SPEC-11)
- **Type:** deviation
- **Status:** resolved

**Situation.** SPEC-09's Behaviour section says the `n_treat == 0` early return "must be the first statement of every generator". As implemented, the return is a single check inside `generate()` (after condition validation, DEC-023), before dispatch to any generator. No generator contains its own check. DEC-023 records the validation ordering but not this placement.

**Decision.** Keep it as implemented. The contract SPEC-09 and §7 I6 care about is that `n_treat == 0` returns all-False *without touching `rng`*, for every condition, identically. Through the public API (`generate`, and so `run_fire`) that holds: no generator is ever entered at zero budget, and I6 passes with byte-identical results across all six conditions. A single choke point also means a future generator cannot forget the check, which is the failure I6 exists to catch.

**Consequence.** The guarantee holds only through `generate()`. The per-condition functions (`_random`, `_patches`, `_strips`, `_buffer`) are private and are not safe to call directly at `n_treat == 0`. Nothing outside `src/geometries.py` and its tests should call them. A generator added by a later spec is covered automatically if it is registered in `_GENERATORS`.

**Context impact.** none. §4.2 signatures and §7 I6 are unchanged; this records how the invariant is met.

**Commit.** pending

### DEC-028 — Clustering-scale ordering verified at L=256; not guaranteed at L=128, b=0.05

- **Date:** 2026-09-27
- **Raised by:** Aaron (review of SPEC-10)
- **Spec:** SPEC-10
- **Type:** ambiguity
- **Status:** resolved

**Situation.** SPEC-10's acceptance criteria require mean connected-component size to increase across `random` → `patches(4)` → `patches(8)` → `patches(16)` (§11). The original test checked this at one point only (`L=128`, `p=0.55`, `b=0.15`, 3 seeds), so it could not say where the claim holds. Review found the ordering broke at `L=128`, `b=0.05`, `p ≤ 0.46`, where `patches(16)` came out at or below `patches(8)` (e.g. `p=0.41`: 6.3 for `k=8`, 5.9 for `k=16`).

**Decision.** The ordering claim stands, at the scale the experiments use. A sweep of `p ∈ {0.30, 0.36, 0.41, 0.46, 0.55, 0.70}` × `b ∈ {0.05 … 0.30}` at `L=128` (10 seeds) showed the ordering holds everywhere except `b=0.05` at `p ≤ 0.46`. Re-run at `L=256` (8 seeds), every point checked is ordered, including `b=0.05` at `p ∈ {0.36, 0.41, 0.46}`. The `L=128` failure is a finite-size effect: at `b=0.05` a `16×16` block is a large share of a small budget, so few blocks are placed and the trim removes much of the last one. It is not a defect in `patches`.

`test_component_size_increases_with_clustering_scale` is now parametrised over `p ∈ {0.36, 0.41, 0.46, 0.55, 0.70}` × `b ∈ {0.05, 0.15, 0.30}` at `L=256` (4 seeds), covering the `p_rel ∈ {−0.05, 0, +0.05}` range of Experiment 1 (`p_c ≈ 0.41`) plus `p=0.70`. A second test, `test_strips_raise_when_no_spacing_brackets_the_budget`, covers the bracket-search `RuntimeError` in `_strips`, which had no test. Both are in `tests/test_geometries.py`, in SPEC-10's may-touch list. No code change.

**Flag.** Pilots or quick checks run at `L=128` with `b=0.05` should not be read against the §11 ordering claim. Reported results use `L=256`.

**Context impact.** none

**Commit.** pending

### DEC-029 — SPEC-05 has no channel for the `p_rel` column

- **Date:** 2026-09-27
- **Raised by:** Aaron on SPEC-05
- **Spec:** SPEC-05 (affects SPEC-06, SPEC-12, SPEC-13, SPEC-14, SPEC-16)
- **Type:** ambiguity
- **Status:** superseded by DEC-030

**Situation.** §5 requires a `p_rel` column (float64 | null): the offset from the governing `p_c` where a config was specified that way, null where `p` was absolute. SPEC-05 assembles each row from `Config` + `RunResult` and defines `run_configs(cfgs: list[Config], out_path, resume=True)`. Neither input carries `p_rel`: `Config` (§4.1) has no such field, `RunResult` is "§5 minus the config echo" and has none, and SPEC-06's `resolve_p` returns only the absolute `p`. SPEC-13 says "the resolved absolute value goes in `p`, the offset in `p_rel`", and SPEC-12, 14 and 16 all say "no new interface, uses `run_configs`", so no downstream spec supplies the value either. As written, the harness can only emit `p_rel` as all-null. Every threshold-relative experiment (Exp 1, 3, 2b's inputs, the §10.2 O1 pilot) would then write rows whose `p_rel` is wrong, and parquets are append-only (§9), so it cannot be patched afterwards.

**Decision.** none yet — needs a call from Aaron and/or Armaan. Options:

1. **Optional keyword argument on `run_configs`** (recommended): `p_rel: Sequence[float | None] | None = None`, parallel to `cfgs`, default all-null. Backward compatible with every spec written against the current signature; `p_rel` stays out of `run_id` (it is a pure function of `p` and the governing `p_c`, i.e. a label). Changes SPEC-05's own interface only, not §4 or §5. Then SPEC-06, 12, 13, 14 and 16 each need their "no new interface" line amended to say they pass it, and SPEC-05's Interface contract is amended.
2. **Add `p_rel` to `Config`.** Changes §4.1, so `project-context.md` and `src/model.py` (outside SPEC-05's may-touch list) change in the same PR; a separate spec or a widened may-touch list is needed.
3. **Carry it in `geometry_params`.** Rejected: it pollutes a column and the generators' input with metadata that is not geometry.
4. **Always null, derive at analysis time from `p` and `pc_estimates.parquet`.** Contradicts §5 as the row contract.

**Also confirm (not blocking, will be implemented as stated unless told otherwise).**

- *Chunking.* "Chunk by config, not by replicate" is read as: a task is a run of consecutive `Config`s in input order (replicates of one parameter point are adjacent, so they land together in the file), sized `min(20, ceil(n / (4 * workers)))`, dispatched with ordered `imap`. Rows are flushed to the parquet atomically (temp file, then `os.replace`) after each completed chunk group, so a partial run always holds whole chunks and resumes by `run_id`. Strict one-task-per-parameter-point would leave most of 16 cores idle for Exp 2b (4 points at R = 10,000), breaking §6.3's ~35 minutes.
- *`code_version`.* Plain `git rev-parse --short HEAD`, obtained once in the parent before any compute and validated as hex; the runner raises if it cannot. It does not append `-dirty` for an uncommitted tree, because that would stop it being "a real short SHA" for SPEC-18's audit. Committing results from a dirty tree is therefore a human check.
- *`run.py`.* Nothing in SPEC-05 is dispatched by `--exp`; the experiment bodies belong to SPEC-07 and 12 to 16, so `run.py` is left untouched.

**Rationale.** Option 1 is the smallest change that makes §5 satisfiable and leaves both contracts (§4, §5) intact.

**Context impact.** none (option 1). Option 2 would change §4.1.

**Commit.** pending

### DEC-030 — SPEC-05: `p_rel` channel, chunking, and what was measured

- **Date:** 2026-09-27
- **Raised by:** Aaron on SPEC-05
- **Spec:** SPEC-05 (affects SPEC-06, SPEC-12, SPEC-13, SPEC-14, SPEC-16)
- **Type:** ambiguity
- **Status:** resolved

**Situation.** DEC-029: the harness had no channel for the §5 `p_rel` column.

**Decision.** Option 1 of DEC-029, as chosen by Aaron. `run_configs(cfgs, out_path, resume=True, *, p_rel=None)`; `p_rel` is a sequence parallel to `cfgs` (same length, else `ValueError`), default all-null, written to the `p_rel` column and **not** part of `run_id`. It stays paired with its config across resume. SPEC-05's Interface contract is amended in the spec file. No §4 signature and no §5 column changes.

**Follow-ups (not done here, because a spec may not edit another spec).** SPEC-06, 12, 13, 14 and 16 say "no new interface, uses `run_configs`". Each of the callers that resolves `p_rel` must now pass it: SPEC-12 (pilot), SPEC-13 (Exp 1), SPEC-14 (Exp 2), SPEC-16 (Exp 3; Exp 4 passes nothing, `p_rel` null by design). Their spec text should say so.

**Other choices made in implementation, as flagged in DEC-029.**

- *Chunking.* A task is a run of consecutive configs in input order, `min(20, ceil(n / (4 * workers)))` long, dispatched with ordered `imap`, so the file order equals the input order and replicates of one parameter point land together. Rows are checkpointed with a temp-file-then-`os.replace` write every 30 s and on any exit (including an exception or Ctrl-C), so an interrupted run always leaves a complete parquet made of whole chunks. Resume matches on `run_id`, so it is correct at any granularity.
- *Append-only.* Resuming rewrites the file atomically with the existing rows carried over unchanged (tested to be identical, `wall_ms` included). `resume=False` on an existing file raises `FileExistsError` instead of overwriting. Duplicate configs in one call raise `ValueError`.
- *`code_version`.* `git rev-parse --short HEAD`, taken once before any compute, validated as hex; the runner raises and writes nothing if it fails. No `-dirty` suffix, so committing results made from an uncommitted tree remains a human check (SPEC-18).
- *`run_id`.* First 16 hex chars of SHA-256 over canonical JSON of every `Config` field. Float fields are coerced to float and int fields to int, so `p=1` and `p=1.0`, numpy scalars and `-0.0` hash the same. `max_steps=None` and `max_steps=8*L` are different runs by design.
- *I7 over the results frame (DEC-023).* DEC-023 said to add it as a second assertion in `test_invariants.py::test_i7_budget_parity`. That file is not in SPEC-05's may-touch list, so the frame check is `tests/test_experiments.py::test_frame_i7_budget_parity`, which also checks I9 over the frame. Deviation from DEC-023's placement only.
- *`run.py`.* Untouched: nothing in SPEC-05 is dispatched by `--exp`.

**Acceptance criterion not met on this hardware: "16 workers, 200 configs, at least 8x faster than serial".**
Measured on the development machine (8 physical cores, 16 logical, Windows spawn), 200 `PERCOLATION` edge-ignition configs at `L=256`:

| | serial | 16 workers | speed-up |
|---|---|---|---|
| harness | 23.8 s | 4.05 s | 5.9x |
| bare `Pool.map`, no harness code | 24.0 s | 4.00 s | 6.0x |
| harness, 800 configs | ~96 s | 12.8 s | 7.5x |

The harness is indistinguishable from a raw `Pool.map`, and the speed-up rises with job size as the ~1 s process-spawn cost amortises, so the limit is 8 physical cores plus start-up, not the harness. `tests/test_experiments.py::test_16_workers_at_least_8x_faster_than_serial` states the criterion verbatim but is opt-in (`SPEC05_SPEEDUP=1`) and fails here at 5.9x. It should be run on a machine with 16 physical cores, or the criterion restated. A default test (`test_parallel_is_faster_and_identical_to_serial`) checks parallel is at least 2x faster and produces identical rows. This matters little for the compute budget: Experiment 0b/2 are overnight runs whose cost is dominated by the `L=512` runs, where start-up is negligible.

**Context impact.** none

**Commit.** pending

### DEC-031 — SPEC-05 speed-up criterion reworded

- **Date:** 2026-09-27
- **Raised by:** Aaron (on SPEC-05)
- **Spec:** SPEC-05
- **Type:** deviation
- **Status:** resolved

**Situation.** SPEC-05 required "16 workers, 200 configs, at least 8x faster than serial". DEC-030 measured 5.9x on an 8-physical-core / 16-thread machine, with the harness matching a bare `Pool.map` (4.01 s vs 4.00 s) and the speed-up rising with job size (7.5x at 800 configs). The criterion is bounded by physical cores and Windows process-spawn cost, not by the harness, so it cannot pass on 8-core hardware and says nothing about correctness.

**Decision.** Reworded by Aaron: on at least 4 cores, a parallel run of 200 configs is at least 2x faster than serial and returns identical rows in the same order. This is what `test_parallel_is_faster_and_identical_to_serial` checks. The opt-in `test_16_workers_at_least_8x_faster_than_serial` and its `SPEC05_SPEEDUP` switch are removed; the measurements stay in DEC-030 as the record. This supersedes the part of DEC-030 that describes that opt-in test and the unmet criterion.

**Rationale.** The property that matters is that parallelism works and does not change results; row identity is checked directly. Overnight run time is a scheduling concern, not a correctness one.

**Context impact.** none

**Commit.** pending

### DEC-032 — SPEC-06: who builds the `pc_estimates` rows, and the estimator's method
- **Date:** 2026-10-02
- **Raised by:** agent (on SPEC-06)
- **Spec:** SPEC-06 (affects SPEC-07, SPEC-14, SPEC-19)
- **Type:** ambiguity
- **Status:** resolved — within the spec's silence, no contract touched; reviewer to confirm

**Situation.** SPEC-06 fixes `estimate_pc(df, condition, regime) -> (p_c, stderr)` and `write_pc_estimates(rows, path)`, and says each measured key gets three per-`L` `var_peak` rows plus one `fss_crossing` row. It does not say what produces the `var_peak` rows or the `rows` argument: `estimate_pc` returns only the crossing, and `write_pc_estimates` takes rows that already exist. SPEC-07, SPEC-14 and SPEC-19 say "feed the frame to `estimate_pc` and append the rows", so a caller has no way to get the per-`L` rows. The spec also names the crossing and variance-peak methods without saying how either is computed.

**Decision.**

- A new public function `pc_rows(df, condition, regime) -> list[dict]` returns the four rows (three `var_peak` with `L` set, one `fss_crossing` with `L` null) in the §4.6 columns, ready for `write_pc_estimates`. Its crossing row equals `estimate_pc`'s return exactly. No signature in §4 changes and no column is added. `write_pc_estimates` accepts a list of dicts or a DataFrame.
- *Crossing.* Per `L`, binomial-logit maximum likelihood of the indicator (`spanned` under edge ignition, `reached_edge` under point ignition, whichever is non-null) against `p`. The estimate is the mean over all pairs of sizes of the `p` where two fitted logits are equal. A pair with a non-increasing fit, parallel curves, or a crossing outside the `p` range both sizes were swept over makes the estimate raise. It is never extrapolated.
- *Variance peak.* Per `L`, the vertex of a quadratic fitted to the cells with `Var(burned_fraction)` at least half the maximum. A peak at an end of the sweep raises.
- *Standard errors.* Bootstrap over the runs in each `(L, p)` cell, 400 replicates, seeded from a module constant so a frame always gives the same answer. At least 90% of replicates must give an estimate.
- *Frame checks beyond the spec.* `estimate_pc` raises if the `(regime, condition)` rows hold more than one `b`, `kappa`, `geometry_params`, `beta`, `f_treat`, `phi`, `tau`, `diagonal_factor`, `ignition` or `settlement`. A frame that mixes them mixes thresholds, and `patches` levels in particular would otherwise be averaged (DEC-012). Fewer than two lattice sizes raises, and exactly two warns that the stderr is unreliable, as the spec's risks note asks.
- `resolve_p` compares `b` and `kappa` exactly, raises `FileNotFoundError` for a missing file and `LookupError` for zero or more than one match, and raises `ValueError` if `p_c + p_rel` is not a probability.

**Follow-up (not done here, because a spec may not edit another spec).** SPEC-07, SPEC-14 and SPEC-19 should say "call `pc_rows(df, condition, regime)` and pass the result to `write_pc_estimates`".

**Rationale.** The row identity of DEC-004 is only usable if something produces those rows. Logistic crossing is smooth under noise, where an interpolated crossing of two noisy empirical curves can have several sign changes. The bootstrap gives a stderr that is checked against the observed scatter in `tests/test_analysis.py`.

**Context impact.** none

**Commit.** pending

### DEC-033 — SPEC-07, SPEC-14 and SPEC-19 aligned to `pc_rows`
- **Date:** 2026-10-02
- **Raised by:** Aaron (decision); applied by agent
- **Spec:** SPEC-07, SPEC-14, SPEC-19 (follow-up to DEC-032)
- **Type:** spec alignment
- **Status:** resolved

**Situation.** DEC-032 added `pc_rows(df, condition, regime)` to SPEC-06, because nothing in the specified interface produces the three per-`L` `var_peak` rows that DEC-004 requires. SPEC-07, SPEC-14 and SPEC-19 said "feed the frame to `estimate_pc`" and "uses `estimate_pc` / `write_pc_estimates` as they stand". Followed literally, that leaves an implementer unable to meet those specs' own acceptance criteria and forces a `blocked` under `workflow-rules.md` §6. DEC-032 listed this as a follow-up it could not apply, since a spec may not edit another spec.

**Decision.** Aaron authorised the edits. The scope and interface text of each spec now routes through `pc_rows`:

- **SPEC-07** — In scope and Interface contract. The frame goes to `pc_rows`, and its rows to `write_pc_estimates`.
- **SPEC-14** — In scope and Interface contract. `pc_rows(df, condition, "STUDY")` per condition, one condition level per call.
- **SPEC-19** — Context to read, In scope and Interface contract. One `kappa` per call.

Acceptance criteria, row identity (DEC-004) and the I1 binding (DEC-014) are unchanged. The edits are wording only.

**Rationale.** Keeps the specs consistent with the implemented SPEC-06 interface before any of them is picked up.

**Context impact.** none. No §4 signature or §5 column changes. This completes the follow-up in DEC-032.

**Commit.** pending

### DEC-034 — SPEC-07: choices the spec left open
- **Date:** 2026-10-02
- **Raised by:** Aaron (on SPEC-07)
- **Spec:** SPEC-07
- **Type:** deviation
- **Status:** resolved — no contract touched; reviewer to confirm

**Situation.** SPEC-07 is silent on how the Experiment 0 runs are seeded, how a staged run (L=128 and 256 first, per its Notes) is run, where the I1 assertion sits relative to the append to `pc_estimates.parquet`, and how the `code_version` rule applies to results produced before the code is committed.

**Decision.**

- *Seeds.* The spec does not say how runs are seeded. `seed = (i_L * 61 + i_p) * 500 + replicate`, where `i_L` and `i_p` index the full grid. Every run gets its own stream, and `run_id` does not depend on which subset of `sizes` or `replicates` was requested, so a staged or pilot run resumes into the full one.
- *Extra arguments.* `run_exp0` takes optional `sizes`, `out_path`, `pc_path` and `replicates`, all defaulting to the spec grid, so `run.py --exp 0` is unchanged. A subset of `sizes` or fewer `replicates` runs the configs only and records no `p_c`: a threshold from part of the grid must not be written as the Experiment 0 estimate. This is what the spec's "run L=128 and 256 first" note needs.
- *I1 before write.* I1 is asserted before anything is appended to `pc_estimates.parquet`, so a failing baseline leaves no estimate in an append-only file. If the key is already present, a rerun appends nothing and re-checks the stored crossing against I1.
- *`run.py`.* Already routed `--exp 0` to `run_exp0`; not touched.
- *Grid tests.* Row count, regime settings and nullness are enforced at run time by `_check_exp0_frame` and `Config.__post_init__`. No separate unit tests were added, because `tests/test_experiments.py` is not on the spec's may-touch list.
- *`code_version`.* The results carry `f25c4a6`, the SPEC-06 head, a real SHA. They were produced from a working tree with uncommitted SPEC-07 changes (the grid builder), so the SHA names the parent of the code that made them. The model, step function and estimator are identical at that SHA. For an exact match, commit the code and rerun after deleting `results/exp0.parquet` and `results/pc_estimates.parquet` (about 20 minutes).

**Measured.** 91,500 rows, none truncated, longest run 1692 steps against a limit of 8L at L=512. Mean `wall_ms` is 25 / 100 / 883 ms at L = 128 / 256 / 512, so the full grid is 8.5 core-hours of summed in-worker run time (about 32 minutes of wall time on 16 threads), not the 75 core-hours the spec estimated from §6.3. `fss_crossing` p_c = 0.4064 ± 0.0005 against 0.407; `var_peak` is 0.4105 / 0.4088 / 0.4075 at L = 128 / 256 / 512, converging on the crossing from above as finite-size theory predicts.

**Rationale.** Each item is a choice inside the spec's silence; none changes a contract, the grid, or the I1 binding.

**Context impact.** none

**Commit.** pending

### DEC-035 — SPEC-19: choices the spec left open
- **Date:** 2026-10-02
- **Raised by:** agent on SPEC-19
- **Spec:** SPEC-19
- **Type:** deviation
- **Status:** resolved — no contract touched; reviewer to confirm

**Situation.** SPEC-19 is silent on how the Experiment 0b runs are seeded, what the pre-pass does when the transition is not bracketed, what happens when a crossing leaves its range, how a staged run (L=128, 256 first, per its Notes) is run, and how the `code_version` rule applies to results produced before the code is committed.

**Decision.**

- *Seeds.* Pre-pass: `(i_kappa * 61 + i_p) * 100 + replicate`. Sweep: `1_000_000 + (((i_kappa * 21 + i_p) * 3 + i_L) * 500 + replicate`. Indices are positions in the full grid, so a staged or reduced run resumes into the full one with the same `run_id`s (as DEC-034 for Experiment 0). The offset keeps the sweep's random streams distinct from the pre-pass's.
- *Centre rule.* "Smallest `p` with `P(span) >= 0.5`" is read as `>=`, so exactly 0.5 counts. `exp0b_centres` raises, pointing at a DEC, if a kappa never reaches 0.5 (the spec's own rule for `kappa=4`), and also if it has already reached 0.5 at the lowest pre-pass `p=0.30`, because the transition is then not bracketed and a sweep centred on it would be a guess. Neither fired.
- *Range check.* In `run_exp0b`, every kappa's crossing is checked to lie strictly inside its declared range (centre ± 0.05) before anything is appended to `pc_estimates.parquet`. All four arms are checked first and written in one `write_pc_estimates` call, so a failing arm leaves no partial record in the append-only file. Re-centring uses an optional `centres=` argument. If the keys are already recorded, nothing is appended (as `run_exp0`).
- *Extra arguments.* `run_exp0b` takes optional `sizes`, `prepass_path`, `out_path`, `pc_path`, `replicates` and `centres`, all defaulting to the spec grid, so `run.py --exp 0b` is unchanged. A subset of `sizes` or fewer `replicates` runs the configs only and records no threshold. The pre-pass is always the full R=100.
- *Tests.* Beyond the required rotation-symmetry test, `tests/test_exp0b.py` covers the grids, seeds, centre derivation and the staged-run path, using synthetic frames, so it runs in seconds.
- *`code_version`.* The results carry `5398134`, the SPEC-07 head, a real SHA. They were produced from a working tree with uncommitted SPEC-19 changes, so the SHA names the parent of the code that made them (same situation as DEC-034). The model, step function and estimator are identical at that SHA. For an exact match, commit the code and rerun after deleting `results/exp0b_prepass.parquet`, `results/exp0b.parquet` and the 16 `STUDY` rows of `results/pc_estimates.parquet`.

**Measured.** Pre-pass sweep centres: kappa 0 / 1 / 2 / 4 = 0.480 / 0.450 / 0.480 / 0.500. `fss_crossing` p_c ± stderr: 0.4769 ± 0.0004 / 0.4641 ± 0.0006 / 0.5004 ± 0.0009 / 0.5410 ± 0.0010; all strictly inside range. `var_peak` at L=512: 0.4785 / 0.4663 / 0.5010 / 0.5424. 126,000 sweep rows and 24,400 pre-pass rows, none truncated. Mean `wall_ms` is 22 / 79 / 710 at L = 128 / 256 / 512, about 15 core-hours of in-worker run time in all, not the ~103 core-hours §6.3 estimates.

**Rationale.** Each item is a choice inside the spec's silence; none changes a contract, the grid, or the sweep definition.

**Context impact.** none

**Commit.** pending

### DEC-036 — SPEC-08: choices the spec left open
- **Date:** 2026-10-04
- **Raised by:** Aaron (on SPEC-08)
- **Spec:** SPEC-08
- **Type:** deviation
- **Status:** resolved — no contract touched; reviewer to confirm

**Situation.** SPEC-08 fixes the registry interface and what the validation figure must show. It is silent on the output format, how the style is applied, where the captions live, how the literature value reaches the figure, and the layout. One process point too: `depends_on: [SPEC-07]`, which is `in review`, not `done`.

**Decision.**

- *Dependency.* Implemented with SPEC-07 `in review`, at the project lead's instruction, as SPEC-06 was with SPEC-05 open. SPEC-07's code and `results/exp0.parquet` / `pc_estimates.parquet` are in this branch's history (stacked on SPEC-19). If SPEC-07's results are regenerated, the figure rebuilds from them with no change.
- *Builders return a bare `Figure`.* They use `matplotlib.figure.Figure`, not `pyplot`, so no figure is registered in global pyplot state, nothing needs closing, and a notebook shows exactly one copy. `matplotlib.use` is never called, so the notebook's inline backend is untouched. Checked by passing the returned figure through IPython's inline formatter: it yields `image/png`, and `pyplot.get_fignums()` is empty afterwards.
- *Style and registry.* `@figure(name, caption=...)` registers the builder and wraps it in `rc_context(STYLE)`, so the style never leaks into the caller's `rcParams`. It rejects a duplicate name, and a builder that returns anything other than a `Figure` raises `TypeError`. The palette is the first three validated categorical slots (one fixed colour per lattice size, plus a marker per size so identity is not colour-alone).
- *Captions.* Stored next to the function and exposed as `CAPTIONS[name]` and `FIGURES[name].caption`. A caption carries no measured number (those are in the legend, computed from the data), so it cannot go stale when a result is regenerated.
- *Output.* `build()` writes `<outdir>/<name>.png` at 200 dpi with the `Software` metadata tag removed, so the bytes depend only on data and code. Two builds compare byte-identical (tested). The `--all` flag mentioned in `.gitignore` is supported alongside `--figure`.
- *Reading results.* The crossing is the single `PERCOLATION` / `none` / `b=0` / `kappa=0` / `fss_crossing` / null-`L` row of `pc_estimates.parquet` (DEC-004), read with pandas directly rather than through `src.analysis`, so `make_figures.py` imports nothing from `src/`. It raises `FileNotFoundError` for a missing file, `LookupError` for zero or several matching rows, and `ValueError` for a missing lattice size, non-`PERCOLATION` rows, null `spanned` or truncated runs. `RESULTS_DIR` is a module constant resolved from `__file__`, so the script works from any directory; tests repoint it.
- *`P_C_LITERATURE` is repeated as a literal* in `make_figures.py` (0.407) rather than imported from `src.model`. Importing it needs a `sys.path` edit for `python figures/make_figures.py`, and a `src` import is what the "reads `results/` only" rule is meant to keep out. `tests/test_figures.py` asserts it equals `src.model.P_C_LITERATURE`.
- *Layout.* Two panels: (a) the full sweep `p ∈ [0.30, 0.60]`, (b) a zoom on `[0.38, 0.44]`. The crossing (0.4064) and the literature value (0.407) are 0.0006 apart, which is invisible on the full axis. The zoom shows both, with the crossing shaded to its standard error. Wilson 95% bands are shown on each curve. The suptitle and caption both state that the `PERCOLATION` threshold is not comparable with any `STUDY` threshold (D5); no `STUDY` value appears anywhere in the figure, and a test checks that.

**Note.** `project-context.md` §6.1 says `P_C_LITERATURE` "is used in exactly one place: an assertion in Experiment 0's validation". §10.1 D5 and SPEC-08 require the validation figure to mark it, so the figure is a second, display-only use. Read as: it is never a grid value or a substitute for a measured `p_c`, which holds. If §6.1's wording is meant literally, it wants a clause for the figure. Not edited here.

**Not verified.** The style was checked in an IPython inline formatter, not in a live Jupyter notebook, because no notebook exists until SPEC-20.

**Context impact.** none

**Commit.** pending

### DEC-037 — SPEC-12: settlement pilot outcome, `SETTLEMENT_SIDE` freeze, and choices the spec left open
- **Date:** 2026-10-04
- **Raised by:** Aaron (on SPEC-12)
- **Spec:** SPEC-12
- **Type:** contract change
- **Status:** resolved - reviewer to confirm the `SETTLEMENT_SIDE = 16` judgement below

**Situation.** SPEC-12 runs the §10.2 O1 pilot and writes the outcome into the specification. It is silent on how many of the "~800" pilot runs are controls, how the two `kappa` arms combine under rule 1 and rule 2, what to freeze when the rule selects no side, and the shape of the coarse Experiment 1 grid. One process point: `depends_on` lists SPEC-05, SPEC-06 and SPEC-19, none of which is `done`. Implemented at the project lead's instruction, stacked on the open branches; `results/pc_estimates.parquet` already holds the Experiment 0b rows the pilot resolves against.

**Outcome.** Branch 3 of the §10.2 O1 rule.

| side | `kappa=0`, `p=0.5269` P(reached) | drift | `kappa=2`, `p=0.5504` P(reached) | drift |
|---|---|---|---|---|
| 8 | 0.96 | −0.15% | 0.10 | −0.10% |
| 16 | 0.92 | −0.39% | 0.18 | −0.51% |
| 32 | 0.94 | −1.54% (reject) | 0.18 | −1.63% (reject) |
| 48 | 0.94 | −3.54% (reject) | 0.14 | −3.54% (reject) |

No side lies in [0.3, 0.8] at either `kappa`, so the result does not depend on whether rule 1 is read as "both" or "either". Rule 2 independently rejects 32 and 48 (their drift is `side²/L²` by construction). 800 runs, none truncated. `settlement_reached_step` among reached runs: median 104 / 92 / 91 / 134 steps (sides 16 / 32 / 48 / 8) at `kappa=0`, 46–48 of 50 reached; at `kappa=2` only 5–9 of 50 reach, so it is heavily censored there.

**Decision.**

- *Pilot composition.* 800 = 400 settlement runs (4 sides × 2 `kappa` × R=50) + 400 controls (`settlement=False`, no `settlement_side` key, 200 per `kappa`, independent seeds). Rule 2 needs "the no-settlement case at the same p", which is a separate run set, and the spec's verification snippet groups by `geometry_params`, so the controls appear as the `{}` group. Controls at one `kappa` share `p`, so one set serves all four sides. `phi=0`; the Experiment 0b threshold at `phi=-π/2` is the same by the §6.1 rotation symmetry.
- *Reading of the rule, fixed in code before the pilot ran.* Both rules are read at both `kappa` (a side qualifies only if in band and within 1% at each), because Experiment 1 runs at both. Drift is the relative difference of mean `n_occupied` from the controls at the same `kappa`. This did not affect the outcome (above).
- *Branch 3 and the value.* The metric for SQ4 becomes `settlement_reached_step`; `settlement_reached` is still recorded, no §5 change. **`SETTLEMENT_SIDE` stays 16.** The rule gives no value in branch 3. 16 is the pre-existing default that every merged spec and test was built on, it passes rule 2, and the pilot shows `P(settlement_reached)` is flat in side, so nothing supports moving. Side 8 also passes rule 2 and is the other defensible choice; this is the judgement for the reviewer. Changing it means editing the constant and rerunning `python run.py --exp 1-coarse` (under a minute) on a fresh results file.
- *Censoring (for SPEC-13 and SPEC-17).* The step is `null` for runs that never reach the settlement. Those are right-censored, so a mean over reached runs alone is biased toward fast fires, and at `kappa=2` it rests on very few runs. The analysis should report the reach probability and the time-to-reach together, or treat it as a time-to-event outcome. The roadmap's SQ4 wording ("minimises P(settlement reached)") is not edited here (not on the may-touch list).
- *Coarse Experiment 1.* All 12 condition levels kept (`none` at `b=0` only, 11 treated levels), `b ∈ {0.10, 0.15, 0.20, 0.30}` plus `b=0`, R=20 (of 200), `p_rel ∈ {−0.05, 0, +0.05}` plus absolute `p=0.70`, `kappa ∈ {0, 2}`, `phi=0`, `settlement=True` with `settlement_side=16` written explicitly (DEC-015). 7,200 rows, none truncated, I7 holds over the frame. `b=0.15` is included because Experiments 2 and 3 use it.
- *Heatmap.* `A` is read as mean `burned_fraction`. Eight panels (`kappa` × density), each with its own colour scale since `A` spans orders of magnitude between densities; the `b=0` column is the untreated run repeated per row. Registered as `exp1-coarse`; the builder reads `exp1_coarse.parquet` only. `import json` was added to `make_figures.py` for it.
- *Seeds.* Pilot `2,000,000 + position`, coarse `3,000,000 + position × 20 + replicate`, clear of Experiments 0 and 0b and of each other.
- *`run.py`.* `pilot` and `1-coarse` added between `0b` and `1`, so `--exp all` runs them in dependency order.
- *Tests.* None added: `tests/` is not on the spec's may-touch list (as DEC-034). The decision rule, grids and frame checks run at run time (`_check_pilot_frame`, `_check_exp1c_frame`); the existing suite passes unchanged.
- *`code_version`.* Both frames carry `e19a989`, the SPEC-20 head, a real SHA. They were produced from a working tree with uncommitted SPEC-12 changes, so it names the parent of the code that made them (as DEC-034, DEC-035). The model and step function are identical at that SHA.

**Rationale.** The decision rule was fixed before the pilot and was applied as written; branch 3 is the one the spec says to take when the outcome is inconvenient. The remaining items are choices inside the spec's silence.

**Context impact.** `project-context.md` §3.6 (`SETTLEMENT_SIDE` frozen at 16, marker removed) and §10.2 O1 (resolution recorded, SQ4 metric changed to `settlement_reached_step`). Only O4 remains open in §10.

**Commit.** pending

### DEC-039 — SPEC-13: ownership, the Experiment 2 selection rule recorded before the run, and the illustrative scars

- **Date:** 2026-10-04
- **Raised by:** Armaan (SPEC-13)
- **Spec:** SPEC-13 (and SPEC-14)
- **Type:** ambiguity
- **Status:** resolved — reviewer to confirm

**Ownership.** SPEC-13 moves from Aaron to Armaan, reviewer Aaron, agreed between us on 2026-10-04 in exchange for SPEC-06 and SPEC-08, which Aaron implemented for the Checkpoint 2 notebook.

**Experiment 2 selection rule, recorded here before `results/exp1.parquet` exists** (SPEC-13 acceptance; §6.2; DEC-012), unchanged:

> "Best" means the lowest mean `burned_fraction` in Experiment 1 at `b = 0.15`, `p_rel = +0.05`, `kappa = 0`. It is chosen separately among the three `patches` levels (`k ∈ {4, 8, 16}`) and among the three `strips_perp` levels (`w ∈ {4, 8, 16}`). `random` is always included. Experiment 2 measures exactly one level per family.

This commit precedes the commit that adds `results/exp1.parquet`, so the rule is fixed in history before the data it is applied to.

**Choices the spec left open.**

- *Seeds.* Seed = `4,000,000 + position·200 + replicate`, position in (kappa, p, condition-level, b) order, so a staged run at fewer replicates resumes into the full run with the same `run_id`s. Clear of the other experiments' seed ranges.
- *Operating points.* `p_rel ∈ {−0.05, 0, +0.05}` resolve against Experiment 0b at the matching kappa (0.4769 and 0.5004 for kappa 0 and 2); `p = 0.70` carries `p_rel = null`. The frame check recomputes every resolved `p` and fails if any differs, which catches the §2 O4 failure mode (a PERCOLATION or wrong-kappa threshold) that the spec names as the most likely silent error.
- *Illustrative scars (DEC-009).* Eight configs, replicate 0 of these Experiment 1 points, all at `p_rel = +0.05`: kappa 0 with `none` and `strips_perp(w=8)` at b = 0.15; kappa 2 with `none`, then `random`, `patches(k=8)`, `strips_perp(w=8)`, `strips_para(w=8)` and `buffer` at b = 0.15. They are picked out of `exp1_grid` itself, so every scar has a matching row in `exp1.parquet` with the same `run_id`. The npz keys are `<run_id>__scar`, `<run_id>__ignition_step`, `<run_id>__config` (canonical JSON) and `run_ids`. SPEC-17 may want a different set; changing `SCAR_LEVELS` and rerunning `run.py --exp scars` (seconds) is all it takes.
- *Run entry.* `run.py --exp scars` is placed right after `1`, so `--exp all` captures scars after the sweep.
- *Tests.* `tests/test_exp1.py` is new. SPEC-13's may-touch list omits tests; the spec's acceptance criteria need them.
- *Compute.* Measured from the coarse run at 83 ms per run, the full 107,200-run grid is about 2.5 core-hours, roughly 11× below §6.3's 28-core-hour estimate. That is an undershoot, not the overshoot the spec warns about; the bounding box is doing its job.

**Context impact.** none

**Commit.** pending
