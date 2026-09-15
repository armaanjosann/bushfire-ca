---
id:                      # SPEC-NN
title:
status: not started      # not started | in progress | in review | done | blocked
owner:                   # who implements it
reviewer:                # the other team member
phase:                   # e.g. Sprint 1 — baseline + validation
depends_on: []           # spec IDs that must be `done` first
implements: []           # project-context.md sections this realises, e.g. [§4.1, §3.3]
issue:                   # GitHub issue number or URL
branch:                  # spec/SPEC-NN-short-name
pr:                      # PR number or URL
decisions: []            # DEC IDs raised while implementing this spec
---

# SPEC-NN — <title>

## Objective

<!-- One or two sentences. What exists at the end that did not exist before. Not how. -->

## Context to read

<!-- The minimum an implementer needs. Name sections, not whole documents.
     e.g. project-context.md §4.1 (Config, run_fire), §3.3 (transition rule) -->

-

## Scope

**In scope**

<!-- Bullets. Be specific enough that "as specified" is checkable. -->

-

**Out of scope**

<!-- Name the adjacent things an implementer would otherwise drift into,
     and the spec that owns each one. This field prevents most scope creep. -->

-

## Files

**May touch**

<!-- Exact paths. Anything not listed is off-limits. -->

-

**Must not touch**

<!-- Shared or contract-bearing files this spec is likely to be tempted by. -->

-

## Interface contract

<!-- Copy the signatures verbatim from project-context.md §4 where they exist.
     If they exist there, write "as project-context.md §4.x — do not redesign".
     If this spec defines a NEW interface, write it out in full here, because
     it will become the thing other specs are implemented against. -->

```python

```

## Behaviour

<!-- The rules the implementation must follow, in enough detail that two people
     would write the same thing. Point at project-context.md rather than
     restating it — a restatement is a second source of truth that can drift. -->

-

## Acceptance criteria

<!-- Checkable statements, not intentions. Each one either holds or does not. -->

- [ ]
- [ ]

## Invariants

<!-- Which of project-context.md §7 (I1-I11) this spec must make pass, and any
     new test it adds. This is what makes "implement as specified" machine-checkable. -->

- [ ] I

## Verification

<!-- The exact command(s) a reviewer runs to check this. -->

```bash

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

<!-- Known traps, prior art in the repo, anything the implementer will hit.
     Optional — delete the section if empty. -->
