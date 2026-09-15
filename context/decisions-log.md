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
