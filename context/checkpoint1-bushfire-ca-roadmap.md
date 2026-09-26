# CITS4403 Project — Bushfire Spread CA with Fuel Management

## Action plan & roadmap for Checkpoint 1

**Group:** Aaron Tan + partner · **Unit:** CITS4403 Computational Modelling (25% of grade)
**Submission:** report + code + demonstration, 11:59pm Fri 9 Oct 2026
**Checkpoint 1:** lab, Mon 14 Sep — project idea, research question, modelling approach, direction

---

## 1. Concept

We simulate a bushfire spreading across a grid of land (stochastic 2D CA), where each square either has fuel or doesn't, and fire spreads from square to square, with wind pushing it more strongly in one direction. When there's no wind and every square is treated the same way, this setup is mathematically identical to a well-studied problem called percolation, so we already know what the "correct" answer should look like — that gives us a solid way to check our model is working before we add anything new.

Then we add the real twist: **prescribed burning**, where a set percentage of the land has had its fuel deliberately reduced beforehand. The obvious question — "does this help?" — isn't interesting, because of course it does. What we're actually asking is two things. First, if you're only allowed to treat a fixed percentage of the land, does where you put that treatment (scattered randomly, in patches, in strips, in rings around a town) change the fundamental point at which fires start becoming uncontrollable, or does it just make fires somewhat smaller without changing that tipping point? Second, is the layout that minimises total burned area across the whole landscape actually the same layout that best protects a specific town — or do those two goals pull in different directions? Neither answer is obvious in advance, and that's where the interesting part of the project lives.

---



## 2. Research questions

**Primary RQ**

> For a fixed fuel-treatment budget *b* (the fraction of the landscape treated), how does the **spatial arrangement** of treatment affect expected burned area — and does arrangement shift the critical fuel density *pc* (a change in the system's critical point), or only reduce burn size at a fixed distance from *pc* (a change in amplitude)?

This is the sharp version. It is answerable, it is quantitative, and it maps directly onto the unit's core content (emergence, phase transitions, criticality, heavy-tailed distributions).

**Sub-questions**


|     | Question                                                                                                                             | Why it earns marks                                                                                                                                                                               |
| --- | ------------------------------------------------------------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| SQ1 | Is the ranking of treatment arrangements **wind-dependent**?                                                                         | Turns a one-factor study into an interaction study; the answer is genuinely unknown to us up front.                                                                                              |
| SQ2 | How does effectiveness **scale with budget** — linear, diminishing returns, or a threshold at which the landscape stops percolating? | Directly a criticality question. A threshold in *b* is the headline result if it exists.                                                                                                         |
| SQ3 | Does treatment **truncate the burn-size distribution's tail** or change its exponent?                                                | Log-log burn-size distributions are exactly the unit's power-law material. Truncation vs. exponent change is a real distinction.                                                                 |
| SQ4 | Does the arrangement that minimises **mean burned area** also minimise **P(settlement reached)**?                                    | We expect *no* — and a demonstrated trade-off between landscape-scale and asset-scale protection is a far more interesting result than a ranking. This is our insurance against a boring answer. |


**Framing for the facilitator:** the phenomenon of interest is a percolation-type phase transition in a spatially structured medium, and the intervention is a constrained spatial-allocation problem on top of it. The bushfire dressing makes it concrete and locally relevant (WA prescribed burning is live policy), but the result is a statement about critical phenomena, not a fire-behaviour prediction. Be explicit about that framing — it pre-empts "your model isn't realistic enough", which is the obvious criticism of any fire CA.

---



## 3. Modelling approach and why a CA

A CA is the right framework here because fire spread is **local, spatial, and synchronous**: a cell's next state depends only on its own fuel and its neighbours' burning state. There is no need for agents with memory, goals or mobility, so an agent-based model (ABM) would add machinery without adding explanatory power; and a graph model would throw away the spatial embedding that the entire research question is about (treatment *geometry*). The CA also gives us the property we most want: a system whose macroscopic behaviour (a landscape-scale fire) is not derivable from the local rule and must be simulated — which is the unit's central claim about complex systems.

**Baseline being replicated:** site percolation on a square lattice. With deterministic spread and uniform fuel, the burned region is exactly the connected cluster containing the ignition, so burned area vs. fuel density must show a sharp transition at the known site-percolation threshold. That gives us a *quantitative* validation target from the literature rather than a hand-wave.

> Note: percolation and the forest-fire model are not covered in the CITS4403 lecture notes — they sit in Downey's *Think Complexity* alongside the material that is. Worth asking the facilitator to confirm this counts as an acceptable known baseline (see §10). We think it strengthens the project: it is adjacent enough to be legible, novel enough to be an independent investigation.

---



## 4. Model specification



### 4.1 Lattice and states

- Grid: *L* × *L* square lattice, **Moore (8-)neighbourhood**.
- Boundaries: **absorbing / non-periodic**. A landscape has edges; periodic boundaries would wrap a fire back on itself, which is physically wrong and would distort the spanning statistics. Cost: finite-size effects, which we handle explicitly with finite-size scaling (§5, Exp 0).
- Cell state `S ∈ {EMPTY, FUEL, BURNING, BURNT}` plus a continuous **fuel load** `f ∈ [0,1]` per cell.
- Initialisation: each cell is occupied by fuel independently with probability *p* (the **fuel density**); occupied cells get `f = 1` unless treated, treated cells get `f = f_treat`.
- Update: **synchronous**, discrete time. One fire event runs to extinction (no BURNING cells remain).



### 4.2 Transition rule

A burning cell *i* independently attempts to ignite each neighbour *j*:

```
P(i → j) = clip( β · w(θ_ij) · f_j , 0, 1 )
```

with the neighbour igniting if any of its burning neighbours succeeds:

```
P(j ignites) = 1 − Π_{i ∈ burning neighbours of j} (1 − P(i → j))
```

- **β** — base spread coefficient (flammability). Absorbs moisture, temperature and everything else that scales ignition probability uniformly.
- **w(θ)** — wind kernel, von Mises form: `w(θ) = exp(κ · cos(θ − φ)) / Z`, normalised so the mean over the 8 directions is 1. `κ = 0` gives isotropic spread; larger `κ` gives a stronger downwind bias. `φ` is the wind direction.
- **f_j** — the target cell's fuel load. This is the channel treatment acts through.
- Burning cells become BURNT after **τ** steps (τ = 1 recovers pure percolation; τ > 1 gives a fire front with depth).
- BURNT is absorbing within an event.

**Deliberate simplification — do not add a separate moisture parameter.** Moisture would multiply the same ignition probability that β does, making the two unidentifiable. Fold it into β and say so in the report. Likewise, `f_treat` and β interact; we fix `f_treat` and sweep β only in a sensitivity check. Keeping the free-parameter count at **two** (*p* and *b*) plus one moderator (*κ*) is the single most important scoping decision in this project.

### 4.3 Parameters


| Symbol    | Meaning                      | Default                     | Justification / role                                                                                                      |
| --------- | ---------------------------- | --------------------------- | ------------------------------------------------------------------------------------------------------------------------- |
| `L`       | lattice size                 | 256                         | Large enough for clean statistics, cheap enough for big sweeps. 128 / 256 / 512 used for finite-size scaling.             |
| `p`       | fuel density                 | swept 0.30–0.70             | **Primary control.** The percolation order parameter.                                                                     |
| `b`       | treatment budget             | swept 0.00–0.30             | **Primary intervention.** Above ~30% is not policy-plausible.                                                             |
| `f_treat` | fuel load of a treated cell  | 0.2                         | Treated fuel is reduced, not eliminated — a burnt-over block still carries some load. Sensitivity: 0.0, 0.2, 0.4.         |
| `β`       | base spread coefficient      | 1.0 baseline, 0.8 main      | β = 1 gives the exact percolation limit for validation; β < 1 for the substantive runs so spread is genuinely stochastic. |
| `κ`       | wind strength                | 0 and 2 (main), 0–4 (Exp 3) | 0 = still day, 2 ≈ strong directional bias, 4 = extreme.                                                                  |
| `φ`       | wind direction               | 0 (east)                    | Fixed; geometry is rotated relative to it instead.                                                                        |
| `τ`       | burn duration                | 1                           | τ = 1 unless we add front depth as an extension.                                                                          |
| —         | ignition                     | single random FUEL cell     | Multiple ignitions is a named extension, not baseline.                                                                    |
| `R`       | replicates per configuration | 200                         | Enough for tight CIs on mean burned area; 500 for the pc estimates.                                                       |
| —         | seed                         | recorded per run            | Every figure regenerable exactly.                                                                                         |




### 4.4 Treatment geometries

Rather than three arbitrary shapes, we treat arrangement as **one continuous control: the spatial clustering scale of the treatment**, plus one targeted condition. This turns a bar chart into a curve, which is a much stronger piece of analysis.


| Condition          | Definition                                              | Role                                                                           |
| ------------------ | ------------------------------------------------------- | ------------------------------------------------------------------------------ |
| **None** (`b = 0`) | untreated landscape                                     | reference                                                                      |
| **Random**         | `b·L²` cells chosen uniformly                           | clustering scale = 1; the null model                                           |
| **Patches**        | random `k × k` blocks, `k ∈ {4, 8, 16}`                 | interpolates random → strips                                                   |
| **Strips ⊥ wind**  | parallel bands, width `w`, spaced so total area = `b`   | classic firebreak orientation                                                  |
| **Strips ∥ wind**  | same bands rotated 90°                                  | isolates orientation from geometry — same shape, same budget, different result |
| **Buffer rings**   | annulus around a settlement patch, thickness set by `b` | targeted asset protection; the SQ4 condition                                   |


All conditions consume **exactly the same budget** `b`. That is what makes the comparison fair and the question non-trivial.

### 4.5 Response variables

- `A` — burned fraction of the lattice (mean, and full distribution)
- `P(span)` — probability the fire reaches the opposite edge (the percolation order parameter)
- `P(settlement reached)`
- Burn-size distribution `P(A ≥ a)` on log-log axes; tail exponent + cutoff
- `p_c` per condition, estimated from the crossing of `P(span)` across `L ∈ {128, 256, 512}` (finite-size scaling) and cross-checked against the peak of `Var(A)`
- **Efficiency** `ΔA / b` — burned area avoided per unit area treated. This is the policy-relevant metric and the one where the ranking is least obvious.

---



## 5. Experiment design


| #     | Experiment                         | Grid                                                                                                                        | Purpose                                                                                                                                 |
| ----- | ---------------------------------- | --------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------- |
| **0** | **Validation / baseline**          | β=1, κ=0, f≡1, τ=1; `p` ∈ [0.30, 0.60] step 0.005; `L` ∈ {128, 256, 512}; R=500                                             | Recover the known site-percolation threshold. Finite-size scaling. **This is the replication component — do it first, do it properly.** |
| **1** | **Main effect: geometry × budget** | 7 conditions × `b` ∈ {0, .05, .10, .15, .20, .25, .30} × `p` ∈ {p_c−0.05, p_c, p_c+0.05, 0.70} × `κ` ∈ {0, 2}; L=256, R=200 | Answers the primary RQ and SQ1, SQ2, SQ4. ≈ 78k runs.                                                                                   |
| **2** | **Threshold shift**                | best 3 conditions at `b`=0.15; fine `p` sweep; `L` ∈ {128, 256, 512}; R=500                                                 | Does treatment move `p_c` or only rescale `A`? The crux of the primary RQ.                                                              |
| **3** | **Wind interaction**               | `κ` ∈ {0, 1, 2, 4} × 7 conditions at `b`=0.15, `p`=p_c+0.05; L=256, R=200                                                   | SQ1 in full.                                                                                                                            |
| **4** | **Sensitivity (short)**            | `f_treat` ∈ {0, .2, .4}, `β` ∈ {.7, .8, .9}, one condition set                                                              | Shows the conclusions are not artefacts of fixed parameter choices. Half a day, high marks-per-hour.                                    |


**Compute — already measured.** We prototyped the core rule in NumPy and timed it: ~44 ms/run at L=128, ~760 ms at L=256, ~8 s at L=512 on a single throttled cloud core. Experiment 1 is therefore ≈ 16 core-hours worst case — **under two hours on the 9800X3D across 16 cores**, and considerably less with an optimised kernel. Kaya is not required for the planned grid; keep it in reserve only if we go to L=1024 or add multi-season fuel regrowth.

**Prototype result (already confirmed):** with β=1, κ=0, f≡1, L=128, the spanning probability goes 0.00 → 0.25 → 0.90 → 1.00 across p = 0.36 → 0.40 → 0.42 → 0.44, i.e. a sharp transition at **p ≈ 0.41**, matching the literature value for Moore-neighbourhood site percolation (≈ 0.407). The baseline works and the validation target is real. Confirm the literature value against a proper reference (Christensen & Moloney, or Newman & Ziff 2000) before quoting it in the report.

---



## 6. Verification plan

Cheap, and it is exactly what "translate modelling assumptions into a computational implementation" is marked on.

1. **Percolation limit** — β=1, f≡1, τ=1 must reproduce the known `p_c`. ✅ already passing on the prototype.
2. **Deterministic front** — p=1, β=1, κ=0: the fire front must be a square expanding at exactly 1 cell/step in Chebyshev distance.
3. **Isotropy** — κ=0: burn scars must be statistically isotropic (check the second moment of scar shape over many replicates).
4. **Wind sanity** — κ>0: mean scar centroid must displace downwind, monotonically in κ.
5. **Null treatment** — `b = 0` must give *identical* distributions across all six geometry code paths.
6. **Conservation** — burnt + unburnt fuel = initial fuel, every run.

---



## 7. Implementation plan

**Stack:** Python + NumPy (vectorised, no per-cell loops), matplotlib, pandas/parquet for results, `multiprocessing` for the sweep. No frameworks.

**Core kernel:** each step, build 8 shifted copies of the burning mask, multiply by the per-direction wind weight and the fuel grid, combine into a per-cell no-ignition probability, then a single Bernoulli draw over the whole grid. Optimisations if needed: `uint8` states, restrict updates to the bounding box of the active front, and precompute the shifted-index slices.

**Repo layout**

```
src/
  model.py        # the CA: state, wind kernel, step(), run_fire()
  geometries.py   # treatment masks: random, patches, strips, buffer
  metrics.py      # burned area, spanning, settlement reached, distributions
  experiments.py  # config grids, parallel runner, writes results/*.parquet
  analysis.py     # p_c estimation, FSS, tail fitting
figures/
  make_figures.py # every report figure, from results/ only
run.py            # single entry point: python run.py --exp 0|1|2|3|4|all
results/          # parquet, one row per run, seed recorded
report/
```

**Non-negotiable:** every figure in the report is regenerable from the submitted code with one command, and no figure is produced by a notebook cell that no longer exists. This is one of the two things that reliably separates strong reports from average ones in this kind of unit.

---



## 8. Timeline


| When                       | Milestone                                                                                                                                                                    | Done when                                                                              |
| -------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------- |
| **Now → Mon 14 Sep**       | **Checkpoint 1.** Repo skeleton up, this plan agreed, baseline CA running with an animation to show.                                                                         | We can screen-share a spreading fire in the lab.                                       |
| **Mon 15 – Sun 21 Sep**    | **Sprint 1 — baseline + validation.** Full model core, verification checks 1–6, Experiment 0 run.                                                                            | `p_c` recovered with finite-size scaling; validation figure exists.                    |
| **Mon 22 – Sun 28 Sep**    | **Sprint 2 — intervention.** All six geometry generators, wind kernel, coarse Exp 1 pass to locate the interesting region. **Parameter set frozen at the end of this week.** | Coarse heatmap of `A(geometry, b)` exists; parameters locked and justified in writing. |
| **Mon 29 Sep – Sun 5 Oct** | **Sprint 3 — full experiments.** Exps 1–4 at full replicates. All figures produced. Methods + Results sections drafted straight from the code.                               | Every planned figure is in `figures/`, generated by `run.py`.                          |
| **Mon 6 – Thu 8 Oct**      | **Sprint 4 — write-up.** Interpretation, limitations, extensions. Code cleanup and a clean-clone reproduction test. Demo rehearsed twice.                                    | **Submit Thu 8 Oct**, a day early.                                                     |
| **Fri 9 Oct**              | Buffer. Do not plan to use it.                                                                                                                                               | —                                                                                      |


**Standing cadence:** 30-minute sync every Monday and Thursday evening. Anything not working by the Thursday sync gets descoped rather than debugged into the following week.

---



## 9. Division of labour

Split by component, not by week, so neither of us is blocked waiting.


| Aaron                                              | Partner                                                                                      |
| -------------------------------------------------- | -------------------------------------------------------------------------------------------- |
| Model core (`model.py`), wind kernel               | Treatment geometry generators (`geometries.py`)                                              |
| Experiment runner + parallelism (`experiments.py`) | Metrics + statistical analysis (`metrics.py`, `analysis.py`) — `p_c` fitting, FSS, tail fits |
| Verification checks 1, 2, 6                        | Verification checks 3, 4, 5                                                                  |
| Repo hygiene, reproducibility entry point          | Figure production and styling (`make_figures.py`)                                            |
| Report: Model, Implementation, Experiments         | Report: Introduction, Results, Limitations                                                   |
| Demo: live model walkthrough                       | Demo: results walkthrough                                                                    |


Both: the research-question framing, Discussion, and a full read-through of the other's sections before submission.

---



## 10. Questions for the facilitator at Checkpoint 1

1. Percolation and the forest-fire model aren't in the lecture notes. Is **recovering the known site-percolation threshold** an acceptable "replicate a known baseline" step, or do you want the baseline to come from covered material?
2. We've reframed three named geometries into **one continuous clustering-scale control plus a targeted condition**. Does that read as a stronger design, or is the simpler three-way comparison what's expected?
3. How much realism is expected? We're deliberately staying on an abstract lattice rather than importing real fuel-load rasters. Is that a scope risk or a scope saving?
4. Expected **report length and figure count**?
5. Is the **multi-season fuel-regrowth** variant (treatment effectiveness decaying over years) worth doing, or scope creep?
6. When and in what format is the **demonstration** assessed?

---



## 11. Risks and mitigations


| Risk                                                            | Likelihood | Mitigation                                                                                                                                                          |
| --------------------------------------------------------------- | ---------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Parameter hell — too many knobs, whole fortnight lost to tuning | Medium     | Two free parameters (`p`, `b`) + one moderator (`κ`). Moisture folded into β. Everything else fixed and justified in writing by end of Sprint 2.                    |
| Boring result ("buffers win, obviously")                        | Medium     | SQ4 (landscape vs. settlement trade-off), the efficiency metric `ΔA/b`, and the wind interaction. At least one of the three will produce a non-obvious ranking.     |
| Sweep too big to finish                                         | Low        | Already measured (§5): under two hours on the desktop. Kaya in reserve.                                                                                             |
| Analysis harder than the model                                  | High       | It is — that's why the geometry generators and the analysis stack are started in Sprint 1/2, not Sprint 3.                                                          |
| Partner and I diverge on the code                               | Medium     | One repo, small PRs, the two weekly syncs, and a frozen interface between `model.py` and `geometries.py` (a geometry is just a function `(L, b, rng) → fuel_mask`). |


---



## 12. Limitations to name in the report

Committing to these now means the section writes itself — and naming *what each assumption probably distorts, in which direction* is what separates a good limitations section from generic hedging.

- **No topography.** Fire runs uphill dramatically faster. Our isotropic-plus-wind kernel therefore understates spread variance in real terrain.
- **No spotting.** Embers jumping ahead of the front routinely defeat firebreaks. Because we exclude spotting, our model almost certainly **overstates the effectiveness of buffer and strip geometries** — a directional bias we can state precisely.
- **Wind is constant in space and time.** Real catastrophic fires are usually driven by a wind *change*. Our model cannot produce that failure mode.
- **No suppression.** No firefighting response, so burned areas are upper bounds.
- **Uniform treatment cost per cell.** Real prescribed burning costs vary with access and with the edge-to-area ratio of the treated shape — long thin strips are expensive per hectare in a way our fixed budget doesn't capture.
- **Single ignition, single season.** No fuel regrowth, so treatment never ages; real treatment effectiveness decays over roughly five years.
- **Sub-cell homogeneity.** One fuel value per cell erases the fine-grained fuel structure that matters at the ignition scale.

---



## 13. How this maps to the assessment criteria


| Criterion (from the project spec)            | Where it's satisfied                                                                                                  |
| -------------------------------------------- | --------------------------------------------------------------------------------------------------------------------- |
| Formulate a focused research question        | §2 — primary RQ + four sub-questions                                                                                  |
| Select and justify a modelling framework     | §3 — why CA and not ABM or graph                                                                                      |
| Translate assumptions into an implementation | §4, §6, §7 — spec, verification, reproducible code                                                                    |
| Design systematic experiments                | §5 — five experiments, factorial, replicated                                                                          |
| Qualitative *and* quantitative evidence      | Burn-scar images and space-time views (qualitative); `p_c`, burn-size distributions, efficiency curves (quantitative) |
| Interpret critically, identify limitations   | §12 — specific, directional                                                                                           |
| Communicate and collaborate                  | §8, §9 — cadence, split, single reproducible entry point                                                              |


---



## 14. Do this before Monday

- [ ] Both read this document; disagree in writing before the lab, not in it.
- [ ] Create the repo, push `src/model.py` with the core rule and a 30-second animation of a spreading fire.
- [ ] Re-run the p-sweep at L=128 yourselves and confirm the transition near p ≈ 0.41.
- [ ] Agree the division of labour in §9 and adjust it to your partner's actual availability.
- [ ] Bring §2 and the six questions in §10 to the lab — those are the two pages that matter in the conversation.