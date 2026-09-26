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
