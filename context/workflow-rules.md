# workflow-rules.md

**Binding on every agent and every human working in this repository.** If you are an agent: read this file first, in full, before touching anything else.

---

## 1. Precedence

When two sources disagree, the higher one wins:

1. **`context/project-context.md`** — the specification. Source of truth for contracts, schemas, invariants and parameters.
2. **The spec** you were asked to implement (`context/specs/SPEC-NN-*.md`).
3. **`context/checkpoint1-bushfire-ca-roadmap.md`** — motivation, research questions, report framing. Never overrides a mechanical detail.
4. **Your own judgement.** Last, always.

A spec that contradicts `project-context.md` is a defect in the spec, not a licence to deviate. Stop — see §6.

## 2. Reading order

1. this file
2. `context/project-context.md` — all of it, once. §4, §5, §7 and §8 are contracts, not description.
3. the spec named in your instruction
4. only the files listed in that spec's **Context to read** and **Files — may touch**

Do not read the whole repository. Do not re-derive context you were handed. Do not open `results/` or `figures/` unless the spec says to.

## 3. The loop

1. Read (§2).
2. Check `depends_on` in the spec's frontmatter. If any listed spec is not `done` in `progress-tracker.md`, stop (§6).
3. Check the stop conditions (§6). If one applies, stop **before** writing code.
4. Set `status: in progress` in the spec frontmatter **and** in `progress-tracker.md`. Create the branch (§8).
5. Implement exactly what the spec says, only in the files it permits (§7).
6. Write or extend the tests the spec names under **Invariants**. Run them. They must pass.
7. Log every deviation, however small, in `decisions-log.md` (§5).
8. Set `status: in review`, push, open a PR (§8).
9. Report what you did, what you deliberately did not do, and every DEC entry you raised.

**An agent may never set a spec to `done`.** That is a human action, after review and merge.

## 4. Status vocabulary

| Status | Means | Set by |
|---|---|---|
| `not started` | Spec written, no work begun | Spec author |
| `in progress` | Branch exists, implementation under way | Implementer |
| `in review` | PR open, every invariant the spec names passes locally, self-reviewed | Implementer |
| `done` | Reviewed by the **other** team member and merged to `main` | Reviewer only |
| `blocked` | Stopped under §6. Requires an open DEC entry, or an unfinished `depends_on` | Implementer |

Status lives in two places and both are updated in the same commit: the spec's frontmatter and its row in `progress-tracker.md`. If they ever disagree, **the spec frontmatter is correct** and the tracker is stale.

## 5. The decisions log

Write an entry in `decisions-log.md` whenever:

- the spec is ambiguous, silent on something you need, or under-specified
- the spec conflicts with `project-context.md`
- you cannot implement the spec as written
- a contract in `project-context.md` needs to change
- you hit an open item in `project-context.md` §10
- you deviate from the spec in any way, however small

**The contract rule.** If a decision changes anything specified in `project-context.md` — a signature, a schema column, a default, an invariant, a parameter, a grid — you must edit `project-context.md` **in the same pull request**, and the DEC entry records which sections changed plus the commit SHA. The log explains *why*; `project-context.md` states *what*. A decision that lives only in the log leaves the specification silently wrong, and the next agent reads the stale version.

Entries are **append-only**. Never edit a past entry. Supersede it with a new one and mark the old one `superseded by DEC-NNN`.

When a spec reaches `in review`, list its DEC IDs in the spec's `decisions:` frontmatter field and in the tracker's Decisions column, so a finished piece of work points at every deviation behind it.

## 6. Stop conditions

Stop, write no code, set `status: blocked`, open a DEC entry with `Status: open`, and report back — if any of these hold:

- the spec is ambiguous, or conflicts with `project-context.md`
- the work would need a **new dependency**
- the work would need a change to the **results schema** (§5) or a **module signature** (§4)
- the work would need an **open item in §10** resolved
- a `depends_on` spec is not `done`
- an invariant fails and the fix lies outside your spec's permitted files

Guessing is worse than stopping. This model produces plausible-looking numbers whatever you feed it, so a silent wrong assumption does not announce itself — it shows up as a result you cannot defend in the report.

## 7. Scope guards

Do not:

- touch a file outside the spec's **may touch** list
- refactor, rename, reformat or otherwise improve anything the spec did not ask for
- **add a dependency.** The model is Python + NumPy only — no numba, no Cython, no torch, nothing in the step function beyond NumPy. `matplotlib`, `pandas`/`pyarrow`, `pytest` and — for the presentation layer only — `jupyter`/`ipykernel` (DEC-016) are the only others in the project.
- change the results schema (§5), the module signatures (§4), or the invariants (§7)
- edit another spec, or change any status other than your own spec's
- resolve an open item in `project-context.md` §10
- use module-level `np.random` or any global mutable state
- mutate or overwrite a parquet file already committed (§9)
- commit generated figures unless the spec explicitly asks for them. **Exception:** `notebooks/*.ipynb` are committed *with* their outputs stored (DEC-017). `figures/out/` stays gitignored.

## 8. Git

- one spec, one branch, one PR. Branch name: `spec/SPEC-07-pc-estimation`.
- never commit directly to `main`
- PR title starts with the spec ID; the PR body links the GitHub issue and lists every DEC entry raised
- the reviewer is **the other team member**, following the component split in the roadmap §9. Neither of us approves our own work, and neither of us approves an agent's work we commissioned without reading the diff ourselves.
- agent commits carry a co-author trailer, so authorship in the submitted repository is honest

## 9. Results and data

`results/` is **tracked in git**. The parquet is part of the record, not a build artefact.

- **Append-only.** Never mutate or overwrite a committed parquet. A rerun either appends through the resume path (`project-context.md` §4.5) or writes a new file.
- Every row carries `code_version`. Before committing results, confirm it is the real short SHA of the code that produced them, not a placeholder.
- Commit only runs that back a reported figure or a validation claim. Delete exploratory and scratch runs first.
- Expected total is roughly 10–20 MB across all experiments. If a single file exceeds 50 MB, stop and raise it — that means something is being written per-replicate that should not be.
- Never bulk-commit `scar` arrays (§4.1). Illustrative scars only, and only where a spec asks for them.
- `figures/make_figures.py` reads from `results/` and nothing else, and must never call `run_fire`. Notebooks consume its `FIGURES` registry; `notebooks/01` alone may call `run_fire`, in one seeded cell at `L <= 128`, labelled as a demonstration and feeding no reported quantity (DEC-018).

## 10. For the two of us — not for agents

- The tracker is reviewed at each Monday and Thursday sync. Anything `in progress` across two consecutive syncs is **descoped, not debugged** into the following week (roadmap §8).
- Anything `blocked` is the first item at the next sync. A blocked spec is waiting on a decision from us, and it is our job to unblock it, not the agent's to guess.
- Before submission, verify from a **clean clone**: `python run.py --exp all` and `pytest`, then confirm every figure in the report came out of that run.
