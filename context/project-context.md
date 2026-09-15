# CONTEXT.md — Bushfire Spread CA with Fuel Management

**Agent-facing specification.** This is the source of truth for implementation: contracts, schemas, resolved ambiguities and invariants. It contains no schedule, no task allocation and no human to-dos — if you are an agent, there is nothing in this document to "do" except implement what it specifies.

Companion document: `checkpoint1-bushfire-ca-roadmap.md` holds the motivation, research questions, report framing and project management. Read it for *why*; read this for *what* and *how*. Where the two disagree on a mechanical detail, **this document wins** — §2 lists the points where it deliberately overrides the roadmap.

Specs in `context/specs/` implement this document. Where a spec disagrees with it, this document wins and the spec is the defect. `context/workflow-rules.md` governs how work proceeds — agents read that first.

Unit: CITS4403 Computational Modelling, UWA. Deliverables are a report, the code, and a demonstration.

---

## 1. What the system is

A stochastic 2-D cellular automaton of fire spread over a lattice of fuel cells, with a directional wind kernel. A **fuel treatment** (prescribed burning) is applied to a fixed budget of cells before ignition, according to one of several spatial arrangements. A single fire event is run to extinction and summarised.

The scientific question is whether the *spatial arrangement* of a fixed treatment budget shifts the system's critical fuel density, or only reduces burn size away from it — and whether the arrangement that minimises landscape-scale burned area is the same one that minimises the probability a settlement is reached.

Two configurations of the same model are used throughout, and **they must not be conflated**:

| Regime | Purpose | Settings |
|---|---|---|
| `PERCOLATION` | Validation / replication of a known baseline | `beta=1.0`, `kappa=0.0`, `diagonal_factor=False`, `f_treat` unused (`b=0`), `tau=1`, `ignition="edge"` |
| `STUDY` | All substantive experiments | `beta=0.8`, `kappa ∈ {0,2,...}`, `diagonal_factor=True`, `f_treat=0.2`, `tau=1`, `ignition="random_cell"` |

Under `PERCOLATION` the model reduces **exactly** to site percolation on a Moore-neighbourhood square lattice: every occupied neighbour ignites with probability 1, so the burned region is precisely the connected cluster containing the ignition. This is why that regime exists and why its settings are not negotiable — changing any of `beta`, `kappa` or `diagonal_factor` breaks the reduction and destroys the validation.

Literature target for that reduction: `P_C_LITERATURE = 0.407` (site percolation threshold, square lattice, 8-neighbour connectivity). A prototype run at `L=128` reproduced a transition at `p ≈ 0.41`. **This constant is a validation target and a sanity bound only. It must never be used as a grid value or as a substitute for a measured `p_c`** — see §6.1.

---

## 2. Deliberate overrides of the roadmap document

These are decisions the roadmap left open or specified differently. Implement the version here.

| # | Roadmap said | This document specifies | Why |
|---|---|---|---|
| O1 | geometry is `(L, b, rng) -> fuel_mask` | geometry is `(rng, occupied, n_treat, **params) -> mask` | Generators must see occupancy to hit an exact budget in *occupied* cells (§4.2). |
| O2 | `b` = "fraction of the landscape treated" | `b` = fraction of **occupied (fuel) cells** treated | You cannot prescribe-burn bare ground. Treating empty cells would make `b` non-comparable across fuel densities `p`, which would confound the two primary controls. |
| O3 | diagonal distance factor "optionally folded in" | `diagonal_factor: bool`, **True** in `STUDY`, **forced False** in `PERCOLATION` | Needed for round fire fronts in the study regime; breaks the exact percolation reduction, so it must be off for validation. |
| O4 | single `p_c` | `p_c` is measured **per condition per regime**; `PERCOLATION`'s `p_c` does not govern `STUDY` runs | Different rule parameters, different threshold. Conflating them is the most likely silent error in this project. |
| O5 | ignition = "single random FUEL cell" | two modes: `"edge"` (Exp 0 only) and `"random_cell"` (everything else) | Spanning probability is only meaningful with edge ignition; burned-area statistics are only meaningful with point ignition. |
| O6 | verification check 2: "front must be a square" | square only when `diagonal_factor=False`; round-ish when True | Direct consequence of O3. |

---

## 3. Model specification

### 3.1 Lattice and state

- Square lattice, `L × L`, **Moore (8-) neighbourhood**.
- Boundaries are **absorbing and non-periodic**. Fire that reaches an edge simply leaves the domain; no wraparound. Finite-size effects are handled by finite-size scaling, not by periodic boundaries.
- Cell state, `int8`:

```
EMPTY = 0    # no fuel, never burns, never propagates
FUEL  = 1    # unburnt fuel, load f > 0
BURNING = 2  # currently alight
BURNT = 3    # absorbing within one fire event
SETTLEMENT = 4  # non-fuel, never burns, never propagates; used for the settlement metric
```

- **Fuel load** `f: float64[L, L]`, held separately from state:
  - `EMPTY` and `SETTLEMENT` cells: `f = 0.0`
  - occupied, untreated: `f = 1.0`
  - occupied, treated: `f = f_treat` (default `0.2`)

### 3.2 Initialisation

1. Place the settlement (§3.6) if the run uses one.
2. Each non-settlement cell is occupied independently with probability `p`. Occupied → `FUEL`, otherwise `EMPTY`.
3. Apply the treatment mask from the geometry generator (§4): masked occupied cells get `f = f_treat`. Treatment does **not** change a cell's state, only its fuel load.
4. Ignite according to `ignition` mode (§3.5).

Order matters: occupancy is drawn **before** treatment, because the generator needs to see the realised occupancy to hit an exact budget.

### 3.3 Transition rule

Discrete time, **synchronous** update. One step:

1. Let `B` be the set of cells currently `BURNING`.
2. For each of the 8 neighbour offsets `d`, a burning cell attempts to ignite its neighbour in that direction with probability

   ```
   P_d(j) = clip( beta * w_d * f[j], 0.0, 1.0 )
   ```

3. A cell `j` in state `FUEL` ignites with probability

   ```
   P(j ignites) = 1 - Π_{d : j's neighbour in direction -d is burning} (1 - P_d(j))
   ```

   Implement as a running product of `(1 - P_d)` over the 8 shifted burning masks, then one Bernoulli draw over the whole grid.
4. Increment `burn_clock` for every cell in `B`. Cells with `burn_clock >= tau` become `BURNT`.
5. Cells that ignited this step become `BURNING`.

**Semantics that must be preserved:**

- Ignition probabilities are computed from the burning set *at the start of the step*. A cell ignited this step does not spread until the next step.
- A cell that becomes `BURNT` this step **did** get to attempt ignition this step (step 2 runs before step 4).
- `EMPTY`, `BURNT` and `SETTLEMENT` cells never ignite. Only `FUEL` cells can.
- The run terminates when no `BURNING` cells remain, or when `step == max_steps` (§3.7).

### 3.4 Wind kernel

Neighbour offsets, in fixed order (this ordering is a contract — weights are indexed by it):

```python
NEIGHBOURS = [(-1,-1), (-1,0), (-1,1), (0,-1), (0,1), (1,-1), (1,0), (1,1)]  # (dy, dx)
```

Weights, von Mises form. For offset `(dy, dx)`, with `theta = atan2(-dy, dx)` (negated so `+y` down in array coordinates maps to north-up in physical coordinates):

```
raw_d = exp(kappa * cos(theta - phi)) * (DIAGONAL_FACTOR if diagonal else 1.0)
w_d   = raw_d / mean(raw)          # normalised so mean over the 8 directions == 1
```

- `DIAGONAL_FACTOR = 1/sqrt(2) ≈ 0.7071`, applied to the four diagonal offsets when `diagonal_factor=True`. Rationale: spread rate falls with distance; without it, Moore-neighbourhood spread is √2 faster along diagonals and fronts are square rather than round.
- `kappa = 0` ⟹ all `w_d` equal (and equal to 1 when `diagonal_factor=False`).
- `phi` is the wind direction in radians; `phi = 0` is east (`+x`).
- The mean-1 normalisation means `kappa` changes anisotropy without changing mean spread rate. **Do not normalise to sum 1** — that would couple wind strength to overall flammability and confound `kappa` with `beta`.

### 3.5 Ignition modes

| Mode | Definition | Used by | Reported metric |
|---|---|---|---|
| `"edge"` | every `FUEL` cell in row 0 is set `BURNING` at `t=0` | threshold sweeps only: Exp 0, 0b, 2 | `spanned` — did any cell in row `L-1` burn |
| `"random_cell"` | one `FUEL` cell chosen uniformly at random (settlement-adjacent cells are eligible; `EMPTY` cells are not) | all other experiments | `reached_edge` — did any cell in any of the four edge rows/columns burn |

`spanned` is meaningless under `"random_cell"` and must be written as `null`, not `False`. Likewise `reached_edge` under `"edge"` is trivially true and must be `null`. Record `ignition_y`, `ignition_x` for `"random_cell"` (`null` for `"edge"`).

If no `FUEL` cell exists, return a zero-burn run rather than raising.

### 3.6 Settlement

Used only when `settlement=True` (Experiment 1 and 3; omit elsewhere to save time).

- A single filled square block of side `SETTLEMENT_SIDE`, centred at `(L//2, L//2)`, cells set to state `SETTLEMENT`. **`SETTLEMENT_SIDE` is provisionally 16 at `L=256`; the binding value is fixed by the pilot in §10.2 O1 before Experiment 1 runs at full replicates.**
- Settlement cells have `f = 0`, never burn, never propagate. They act as a hole in the fuel bed.
- The side may be set per run through `geometry_params["settlement_side"]` (int), defaulting to `SETTLEMENT_SIDE` when absent. Placement, the settlement ring and the `buffer` generator all read the resolved value; this is how the §10.2 O1 pilot varies side without global state. Grid builders for `settlement=True` runs always set the key explicitly, so a run's `run_id` never depends on whether the default was written out; runs without a settlement omit it (DEC-007, DEC-015).
- **`settlement_reached` is True iff any cell in the 1-cell-wide ring immediately surrounding the settlement block enters state `BURNING` at any time during the run.** Record the step at which it first happens (`settlement_reached_step`, else `null`).
- Ignition under `"random_cell"` may occur anywhere in the fuel bed, including inside a buffer ring. Do not exclude regions — excluding them biases the comparison in favour of buffer geometries.

### 3.7 Truncation

- `max_steps = 8 * L` by default.
- If the loop exits on `max_steps` with cells still `BURNING`, set `truncated = True`.
- **`burned_cells` counts `BURNT` cells only.** Cells still `BURNING` at truncation are counted separately as `still_burning_cells`. Do not silently fold them into the burned total — that was a bug in the throwaway prototype.
- `truncated` must be `False` for every run in every reported figure. The analysis layer asserts this; if it ever fires, raise `max_steps` rather than filtering the rows out.

---

## 4. Module contracts

### 4.1 `src/model.py`

```python
@dataclass(frozen=True)
class Config:
    # lattice
    L: int = 256
    # regime
    regime: str = "STUDY"              # "STUDY" | "PERCOLATION"
    # fuel
    p: float = 0.45                    # occupancy probability
    f_treat: float = 0.2
    # rule
    beta: float = 0.8
    kappa: float = 0.0
    phi: float = 0.0
    tau: int = 1
    diagonal_factor: bool = True
    # treatment
    condition: str = "none"            # see §4.2
    b: float = 0.0                     # fraction of OCCUPIED cells treated
    geometry_params: dict = field(default_factory=dict)
    # setup
    ignition: str = "random_cell"      # "random_cell" | "edge"
    settlement: bool = False
    max_steps: int | None = None       # default 8 * L
    # reproducibility
    seed: int = 0

    def __post_init__(self):
        ...  # validate regime consistency; see §4.4

@dataclass
class RunResult:
    ...        # exactly the fields in the schema of §5, minus the config echo
    scar: np.ndarray | None = None           # final state grid, only when capture_scar=True
    ignition_step: np.ndarray | None = None  # int32[L, L]: step each cell first became BURNING
                                             # (0 for ignition cells), -1 if never; only when capture_scar=True

def run_fire(cfg: Config, capture_scar: bool = False) -> RunResult: ...
def wind_weights(kappa: float, phi: float, diagonal_factor: bool) -> np.ndarray: ...  # shape (8,)
def initial_grids(cfg: Config, rng) -> tuple[np.ndarray, np.ndarray]: ...             # (state, f)
```

`run_fire` is pure with respect to `(cfg)`: same config, same result, always. It creates its own `np.random.default_rng(cfg.seed)` internally and must not accept an external generator — that is what makes the determinism test in §7 possible.

`scar` and `ignition_step` are returned only when explicitly requested. `ignition_step` exists for the space-time view of the illustrative scars (DEC-013). It is never written to a parquet, so the §5 rule against `-1` sentinels does not apply to it. **Never store scars for a full sweep** — 78k grids at `256²` is far too much. Capture them for a hand-picked handful of illustrative configurations only.

### 4.2 `src/geometries.py`

Every generator has this signature:

```python
Generator = Callable[..., np.ndarray]   # -> bool[L, L], True where treated

def generate(condition: str, rng, occupied: np.ndarray, n_treat: int, **params) -> np.ndarray
```

- `occupied` is `bool[L, L]`, True where the cell holds fuel (settlement and empty cells are False).
- `n_treat = round(b * occupied.sum())` — computed by the caller, passed in.
- The returned mask must satisfy `(mask & occupied).sum() == n_treat` where exactly achievable, and otherwise fall within `max(1, ceil(0.01 * n_treat))` of it. The **actual** count is recorded as `n_treated` and is what the efficiency metric divides by — never the nominal `b`.
- A generator must never mark a non-occupied cell as treated; assert `mask & ~occupied == 0` before returning.
- `n_treat == 0` must return an all-False mask for every condition, identically.

| `condition` | Params | Construction |
|---|---|---|
| `"none"` | — | all-False. Requires `n_treat == 0`. |
| `"random"` | — | choose `n_treat` occupied cells uniformly without replacement. Exact. Clustering scale 1. |
| `"patches"` | `k` ∈ {4, 8, 16} | place `k × k` blocks at uniformly random top-left positions (may overlap) until covered occupied cells ≥ `n_treat`; then randomly un-treat the excess. Records actual count. |
| `"strips_perp"` | `w` ∈ {4, 8, 16} (default 4) | bands of width `w` running perpendicular to `phi`, evenly spaced; bisect on spacing until the occupied-cell count hits `n_treat`. Band phase offset drawn uniformly per replicate. `w` is a swept clustering-scale level, not a fixed default — see §10.1 D2. |
| `"strips_para"` | `w` ∈ {4, 8, 16} (default 4) | identical construction, rotated 90°. Same shape, same budget — isolates orientation. Swept over the same `w` set as `strips_perp`. |
| `"buffer"` | — | grow concentric rings outward from the settlement block, one cell of thickness at a time, until covered occupied cells ≥ `n_treat`; fill the final partial ring at random. Requires `settlement=True`. |

**Clustering scale.** `random` (scale 1) → `patches` (scale `k`) → `strips` (scale `L` in one dimension) form the continuum that the primary analysis is built on. `buffer` is the targeted condition and sits off that axis. Keep `k` and `w` on the same footing so a single "treatment clustering scale" axis can be plotted.

### 4.3 `src/metrics.py`

Pure functions over a finished run: burned fraction (of lattice and of initial fuel), edge reached, spanning, settlement reached and first-reach step, step count, still-burning count. No I/O, no plotting.

### 4.4 Validation of config consistency

`Config.__post_init__` must raise on:

- `regime == "PERCOLATION"` with any of: `beta != 1.0`, `kappa != 0.0`, `diagonal_factor is True`, `tau != 1`, `b != 0`, `ignition != "edge"`.
- `condition == "buffer"` with `settlement is False`.
- `condition == "none"` with `b != 0`.
- `b < 0 or b > 1`, `p < 0 or p > 1`, `tau < 1`, `L < 32`.

Fail loudly at construction. A silently mis-specified regime produces plausible-looking numbers that are wrong, which is the worst failure mode available here.

### 4.5 `src/experiments.py`

- Builds config grids per experiment (§6).
- Runs them with `multiprocessing.Pool`; chunk by config, not by replicate.
- Writes one parquet file per experiment to `results/exp{N}.parquet`, one row per run, schema per §5.
- Must be resumable: if the output file exists, skip configs already present (match on `run_id`).

### 4.6 `src/analysis.py`

- `estimate_pc(df, condition, regime) -> (p_c, stderr)` — from the crossing of `P(span)` or `P(reached_edge)` across `L`, cross-checked against the peak of `Var(burned_fraction)`.
- Writes `results/pc_estimates.parquet` with columns `regime, condition, b, kappa, L, p_c, p_c_stderr, method`. For each measured `(regime, condition, b, kappa)` there is one per-`L` row per lattice size (`method="var_peak"`) and exactly one `method="fss_crossing"` row with `L` null (nullable `Int32`). The crossing row is the governing threshold (DEC-004).
- Tail fitting for burn-size distributions.
- Asserts `truncated == False` across every input frame.

### 4.7 `run.py`

Single entry point. `python run.py --exp {0,0b,1,2,2b,3,4,all}`, plus the auxiliary entries the specs add (`pilot`, `1-coarse`, `scars`). `all` runs every entry needed for the report in dependency order, so `0b` runs before `1`. Every figure in the report must be reproducible from a clean clone with this command and nothing else.

---

## 5. Results schema

One row per run. This is the most load-bearing contract in the project — every figure and every statistic is derived from this table, so it is specified exhaustively.

| Column | Type | Notes |
|---|---|---|
| `run_id` | str | Deterministic hash of the full config. Primary key; used for resume. |
| `code_version` | str | Git short SHA at run time. |
| `seed` | int64 | |
| `regime` | str | `STUDY` \| `PERCOLATION` |
| `L` | int32 | |
| `p` | float64 | |
| `p_rel` | float64 \| null | Offset from the governing `p_c` where the config was specified that way (§6.1); `null` if `p` was absolute. |
| `condition` | str | |
| `geometry_params` | str | JSON-encoded dict. |
| `b` | float64 | Nominal budget. |
| `budget_basis` | str | `"occupied"`. Recorded explicitly so the alternative is distinguishable if ever run. |
| `f_treat` | float64 | |
| `beta`, `kappa`, `phi`, `tau` | float64 | |
| `diagonal_factor` | bool | |
| `ignition` | str | |
| `ignition_y`, `ignition_x` | int32 \| null | `null` for `"edge"`. |
| `settlement` | bool | |
| `n_cells` | int32 | `L*L` |
| `n_occupied` | int32 | Realised, not expected. |
| `n_treated` | int32 | **Realised.** Use this, not `b`, in efficiency metrics. |
| `burned_cells` | int32 | `BURNT` only. |
| `still_burning_cells` | int32 | Non-zero only if `truncated`. |
| `burned_fraction` | float64 | `burned_cells / n_cells` |
| `burned_fraction_of_fuel` | float64 | `burned_cells / n_occupied` |
| `spanned` | bool \| null | `null` unless `ignition == "edge"`. |
| `reached_edge` | bool \| null | `null` unless `ignition == "random_cell"`. |
| `settlement_reached` | bool \| null | `null` unless `settlement`. |
| `settlement_reached_step` | int32 \| null | |
| `steps` | int32 | |
| `truncated` | bool | Must be False in all reported rows. |
| `wall_ms` | float64 | For compute budgeting. |

Nullable integer columns use pandas nullable dtypes (`Int32`), not `-1` sentinels.

---

## 6. Experiments

### 6.1 `p_c` is a measured value, never a constant

This is the single most important rule in the document.

- Experiment 0 measures `p_c` under `PERCOLATION` and writes it to `results/pc_estimates.parquet`.
- Experiment 0b measures the untreated (`condition="none"`, `b=0`) `STUDY` threshold at every `kappa` that a threshold-relative grid uses, `kappa ∈ {0, 1, 2, 4}`. It runs **before** the §10.2 O1 pilot and Experiment 1, because both resolve `p_rel` against it (DEC-011).
- Experiment 2 measures `p_c` **per treated condition** under `STUDY`. Its untreated reference is Experiment 0b's `kappa=0` row, not a rerun.
- Experiments whose grids are specified relative to a threshold (`p_c - 0.05`, `p_c`, `p_c + 0.05`) resolve that offset **at config-build time** by reading the relevant row from `pc_estimates.parquet`. The resolved absolute `p` goes in the `p` column and the offset in `p_rel`.
- If `pc_estimates.parquet` is missing or lacks the needed row, **raise**. Do not fall back to `P_C_LITERATURE`.
- `P_C_LITERATURE = 0.407` is used in exactly one place: an assertion in Experiment 0's validation that the measured value is within a tolerance of it.

The governing `p_c` for a `STUDY` experiment is the untreated (`condition="none"`, `b=0`) `STUDY` threshold at the matching `kappa` (the `fss_crossing` row that Experiment 0b writes), unless the experiment explicitly says otherwise. All `STUDY` thresholds are measured at `beta=0.8`, `f_treat=0.2`. An experiment that varies `beta` does not resolve `p_rel` (see Experiment 4).

**Edge-ignition wind convention.** `STUDY` threshold sweeps (Experiments 0b and 2) use `phi = -π/2`, so the wind blows from row 0 towards row `L-1` and the ignited edge (§3.5) is the upwind edge. A 90° rotation of the lattice is an exact symmetry of the rule: the Moore neighbourhood, the diagonal factor and the von Mises kernel all rotate with it. So for untreated fuel, the threshold measured at `phi = -π/2` is exactly the threshold at `phi = 0`, and `pc_estimates.parquet` needs no `phi` column. Experiment 2b keeps `phi = -π/2` from Experiment 2, so its treated geometries are the same ones whose threshold was measured.

### 6.2 Grid

| # | Name | Grid | Ignition | Settlement |
|---|---|---|---|---|
| 0 | Validation | `PERCOLATION`; `p` ∈ [0.30, 0.60] step 0.005; `L` ∈ {128, 256, 512}; R=500 | `edge` | no |
| 0b | Study baseline threshold | `STUDY`; `condition="none"`, `b`=0; `kappa` ∈ {0, 1, 2, 4}; `phi`=−π/2; fine `p` sweep per `kappa`, declared in the builder: ±0.05 at step 0.005 around a centre located by an `L`=128 pre-pass; `L` ∈ {128, 256, 512}; R=500 | `edge` | no |
| 1 | Geometry × budget | `STUDY`; 12 condition-levels (see note below) × `b` ∈ {0, .05, .10, .15, .20, .25, .30} × `p_rel` ∈ {−0.05, 0, +0.05} plus absolute `p=0.70` × `kappa` ∈ {0, 2}; `L`=256; R=200 | `random_cell` | yes |
| 2 | Threshold shift | `STUDY`; `kappa`=0, `phi`=−π/2; at `b`=0.15: `random`, the best `patches` level and the best `strips_perp` level from Exp 1 (selection rule below); fine `p` sweep, declared in the builder; `L` ∈ {128, 256, 512}; R=500. Untreated reference is Exp 0b at `kappa=0`, not rerun | `edge` | no |
| 2b | Tail statistics | `STUDY`; `kappa`=0, `phi`=−π/2; `none` at `b`=0 with `p` = Exp 0b `kappa=0` `p_c`; `random`, best `patches` level, best `strips_perp` level at `b`=0.15, each with `p` = its own Exp 2 `p_c`; `L`=256; R=10,000 | `random_cell` | no |
| 3 | Wind interaction | `STUDY`; `kappa` ∈ {0,1,2,4} × 7 conditions at `b`=0.15, `p_rel`=+0.05; `L`=256; R=200 | `random_cell` | yes |
| 4 | Sensitivity | `STUDY`; `f_treat` ∈ {0, .2, .4} × `beta` ∈ {.7, .8, .9}, reduced condition set; `kappa`=2; **absolute** `p` = Exp 0b `p_c` at `kappa=2` + 0.05, resolved once and held fixed across every `beta` (`p_rel` null) | `random_cell` | yes |

**Experiment 2 selection rule, fixed before Experiment 1 runs.** "Best" means the lowest mean `burned_fraction` in Experiment 1 at `b=0.15`, `p_rel=+0.05`, `kappa=0`. It is chosen separately among the three `patches` levels and among the three `strips_perp` levels. Experiment 2 therefore measures at most one level per condition family, which keeps the `(regime, condition, b, kappa)` key of `pc_estimates.parquet` unique (DEC-012).

**Experiment 4 holds `p` fixed across `beta` on purpose.** A sensitivity check asks how outcomes move when `beta` changes on the same landscape, so it does not re-centre on a threshold specific to each `beta` (DEC-011).

Note Experiments 0b and 2 use **edge** ignition: estimating a percolation threshold requires a spanning measure, which point ignition cannot provide. This differs from Experiment 1 by design.

The 12 condition-levels are: `none`, `random`, `patches(k=4)`, `patches(k=8)`, `patches(k=16)`, `strips_perp(w=4)`, `strips_perp(w=8)`, `strips_perp(w=16)`, `strips_para(w=4)`, `strips_para(w=8)`, `strips_para(w=16)`, and `buffer` where a settlement exists. (`none` only appears at `b=0`, so the effective count varies by budget.) Sweeping `w` alongside `patches`' `k` is what makes the clustering-scale axis (§11) continuous across both geometry families rather than three points plus two isolated ones — see §10.1 D2.

### 6.3 Compute

Measured on a single throttled cloud core with an unoptimised kernel: ~44 ms/run at `L=128`, ~760 ms at `L=256`, ~8 s at `L=512`. Experiment 1 at 12 condition-levels is therefore ~28 core-hours worst case — still under two hours across 16 cores, and considerably less once the optimisations in §8 land. Experiment 2b adds ~8 core-hours (~35 minutes across 16 cores). Experiment 0b costs ~26 core-hours per `kappa` arm for a 21-point sweep, dominated by `L=512`. Four arms come to ~103 core-hours, ~6.5 hours across 16 cores, and the `L=128` pre-pass is negligible. Experiment 2 at three treated conditions is ~77 core-hours. Both are overnight runs, and runs near the threshold may be slower than these averages. No HPC is required for the grid as specified.

---

## 7. Invariants and tests

Implement these as an actual test suite, not as prose. Several are also report figures.

| # | Invariant | Test |
|---|---|---|
| I1 | **Percolation limit.** `PERCOLATION` regime reproduces the known threshold. | The `fss_crossing` `p_c` (crossing across `L ∈ {128, 256, 512}`) within 0.01 of `P_C_LITERATURE`. The `L=512` `var_peak` value is reported alongside as a cross-check, not asserted (DEC-014). |
| I2 | **Determinism.** Same config ⟹ identical result. | Run any config twice; every schema field equal. |
| I3 | **Deterministic front shape.** `p=1, beta=1, kappa=0, diagonal_factor=False`: front is square, expanding 1 cell/step in Chebyshev distance. With `diagonal_factor=True` the front is not square — assert Chebyshev growth only in the False case. |
| I4 | **Isotropy.** `kappa=0`: burn scars statistically isotropic. | Second moment of scar shape, x vs y, equal within CI over ≥200 replicates. |
| I5 | **Wind monotonicity.** Mean scar centroid displaces downwind, monotonically in `kappa`. | Centroid projection on `phi` strictly increasing over `kappa ∈ {0,1,2,4}`. |
| I6 | **Null treatment.** `b=0` gives identical distributions across every condition code path. | Same seed, every condition, `b=0` ⟹ byte-identical results. This catches accidental rng consumption inside generators. |
| I7 | **Budget parity.** `n_treated` within tolerance of `round(b * n_occupied)` for every condition. | Assert in the generator and again over the results frame. |
| I8 | **Treatment placement.** No treated cell is unoccupied. | `mask & ~occupied` is empty. |
| I9 | **Conservation.** `burned_cells + still_burning_cells ≤ n_occupied`; no cell leaves `BURNT`. | Per-run assertion. |
| I10 | **No truncation.** `truncated` is False across every reported frame. | Assertion in `analysis.py`. |
| I11 | **Lattice frame invariance.** The `strips_perp` − `strips_para` gap does not depend on whether the wind is axis-aligned. | At `b=0.15`, `p_rel=+0.05`, `kappa=2`, `L=256`, R=200: compare the gap at `phi=0` (axis-aligned strips) with `phi=π/4` (geometry rotated to match). Overlapping CIs ⟹ a Methods line; non-overlapping ⟹ a measured lattice artefact for Limitations. See §10.1 D3. |

I6 deserves emphasis: the natural way to write a geometry generator draws from `rng` even when `n_treat == 0`, which desynchronises the stream and makes the `b=0` baselines differ between conditions for no physical reason. Generators must return early on `n_treat == 0` **before touching `rng`**.

---

## 8. Implementation constraints

- **Python + NumPy only** for the model. No numba, no Cython, no torch. Matplotlib for figures, pandas/pyarrow for results.
- **Fully vectorised.** No per-cell Python loops anywhere in the step function. The step is: build 8 shifted burning masks, accumulate `(1 - P_d)` as a running product, one Bernoulli draw over the grid.
- **Bounding-box optimisation.** Restrict the per-step computation to the bounding box of the active front, padded by 1. Most of a run has a small front in a large grid; this is where the bulk of the speedup is.
- `state` and `burn_clock` are `uint8`/`int8`. `f` is `float64`.
- Precompute the shifted-slice index pairs once per grid size rather than recomputing them each step.
- No global mutable state. No module-level `np.random` calls — every draw comes from the run's own generator.
- Results are append-only; never mutate a written parquet file. `results/` is **tracked in git** — see `context/workflow-rules.md` §9 for what may and may not be committed.

---

## 9. Repository layout

```
CLAUDE.md              # agent entry point; points at context/
run.py                 # single entry point: python run.py --exp 0|0b|1|2|2b|3|4|all
context/
  workflow-rules.md    # how work is done here — binding on agents
  project-context.md   # this file — the specification
  progress-tracker.md  # status of every spec
  decisions-log.md     # ambiguities, deviations, contract changes
  spec-template.md     # blank template for a new spec
  specs/               # one file per spec, SPEC-NN-short-name.md
  checkpoint1-bushfire-ca-roadmap.md   # motivation, RQs, report framing
src/
  model.py        # Config, RunResult, run_fire, wind_weights, initial_grids
  geometries.py   # generate() and the per-condition generators
  metrics.py      # pure summary functions
  experiments.py  # config grids, parallel runner, parquet writers
  analysis.py     # p_c estimation, FSS, tail fitting, assertions
figures/
  make_figures.py # every report figure, reading only from results/
tests/
  test_invariants.py   # I1-I11
results/          # parquet, one row per run — tracked in git, append-only
report/
```

`figures/make_figures.py` reads from `results/` and nothing else. It must never call `run_fire`.

---

## 10. Decisions and remaining open items

Five points were left undecided in the first draft of this document. Three are resolved below on design grounds and are now binding; two remain genuinely open and are settled by evidence at a stated gate. **Nothing here may still be open after the Sprint 2 parameter freeze (Sun 28 Sep)** — a methodological choice carried into Sprint 3 becomes a choice made after seeing the results, which is not defensible in the report.

Numbering is preserved from the original list so the resolutions are traceable: D2, D3, D5 were open questions 2, 3 and 5; O1 and O4 were 1 and 4.

### 10.1 Resolved — binding

**D2 — Strip width `w` is swept, not fixed. `w ∈ {4, 8, 16}`.**

The primary analysis is built on a clustering-scale axis (§11): `random` at scale 1, `patches` at scale `k`, `strips` at scale `w`. With `w` fixed at 4, that axis has three points from `patches` and one from `strips`, and the geometry comparison degenerates into "patches at three scales versus two arbitrary strips". Sweeping `w` over the same set as `k` puts both families on one axis and makes the orientation contrast (`perp` vs `para`) available at every scale rather than at one arbitrary width.

The cost objection does not survive arithmetic. Strips are 2 of the condition families, so this takes Experiment 1 from 8 to 12 condition-levels — 1.5×, not 3× — i.e. ~28 core-hours, still under two hours across 16 cores. Implemented in §4.2 and §6.2.

**D3 — `phi` is not swept. The underlying concern becomes verification check I11.**

Fixing `phi = 0` and rotating the geometry is *almost* equivalent to rotating the wind, but not exactly: the lattice has 4-fold symmetry and the strips are axis-aligned, so an axis-aligned wind can in principle couple to the lattice in a way a diagonal wind does not. That is a soundness question about the implementation, not a research question, and it does not deserve an experimental dimension.

It is answered once, cheaply, by I11 (§7): compare the `strips_perp` − `strips_para` gap at `phi = 0` against `phi = π/4` with the geometry rotated to match, at a single operating point, R=200. Overlapping CIs ⟹ one line in Methods stating the frame-invariance check passed. Non-overlapping ⟹ a *measured* lattice artefact with a magnitude attached, which goes in Limitations. Both outcomes are reportable; neither costs an axis.

**D5 — The `PERCOLATION` `p_c` stays in the report, as validation only.**

It appears in exactly two places: one figure (`P(span)` vs `p` across `L ∈ {128, 256, 512}`, with the finite-size-scaling crossing and `P_C_LITERATURE` marked) and two sentences in Methods. That figure *is* the unit's "replicate a known baseline" deliverable, so dropping it forfeits an assessment criterion outright.

The constraint runs the other way instead: because O4 in §2 means this threshold governs no substantive result, it must never appear in a table alongside a `STUDY` threshold, and the report states once, explicitly, that the two are different by construction and not comparable.

> **Contingent on the facilitator.** Roadmap §10 Q1 asks whether recovering the site-percolation threshold counts as an acceptable known baseline at all. If the answer is "the baseline must come from covered material", D5 is void and the validation strategy is re-planned from scratch. Ask that question first at Checkpoint 1.

### 10.2 Open — settled by evidence at a stated gate

**O1 — `SETTLEMENT_SIDE`. Gate: pilot in Sprint 2, before Experiment 1 runs at full replicates.**

`SETTLEMENT_SIDE = 16` at `L = 256` is 0.4% of the lattice by area and is unvalidated in both directions. Too small and `settlement_reached` saturates near 0 or 1 and cannot discriminate between geometries, which kills SQ4; too large and the settlement is a hole big enough to distort the fuel bed and shift the effective occupancy.

*Pilot* — ~800 runs, well under half an hour: side ∈ {8, 16, 32, 48} × `kappa` ∈ {0, 2}, at `b = 0`, `condition = "none"`, `p_rel = +0.05` (resolved against Experiment 0b at the matching `kappa`), `L = 256`, R = 50.

*Decision rule, fixed before the pilot runs:*

1. Take the **smallest** side whose baseline `P(settlement_reached)` falls in **[0.3, 0.8]**.
2. Reject any side for which `n_occupied` differs by more than 1% from the no-settlement case at the same `p`.
3. If no side satisfies both, the discriminating variable is wrong rather than the size: switch the SQ4 metric to `settlement_reached_step` (time-to-reach, which does not saturate) and record that change here.

The chosen value is then written into §3.6 as a constant with this justification attached. The pilot is a Methods paragraph, not a result.

**O4 — Burn-size distribution replicate count. Gate: after Experiment 2 yields measured per-condition `p_c`.**

This one genuinely cannot be decided now. Sizing a tail fit requires knowing whether the distribution is heavy-tailed at all, roughly where `x_min` sits, and how far the finite-size cutoff intrudes at `L = 256` — none of which exist before Experiment 2. What *is* decided now is the protocol, so that the choice is not made under deadline pressure while looking at the answer:

> **Experiment 2b.** `STUDY`, `L = 256`, `random_cell` ignition, no settlement, `kappa = 0`, `phi = −π/2`, `b = 0.15` for treated conditions. `p` set to the measured per-condition `p_c` from Experiment 2 (Experiment 0b for `none`) — a threshold is a property of the rule and the lattice, not of the ignition mode, so an edge-ignition estimate is the correct `p` for point-ignition tail runs. Conditions: `none` at `b = 0`, then `random`, the best `patches` level and the best `strips_perp` level from Experiment 1. These are exactly the three treated conditions Experiment 2 measures (§6.2 selection rule, DEC-012). R = 10,000. Fit by maximum likelihood with `x_min` chosen by KS distance (Clauset–Shalizi–Newman), and **report the exponent together with the fitted cutoff** — SQ3 asks whether treatment truncates the tail or changes its exponent, and a fit with no cutoff term cannot distinguish the two.

Cost is ~8 core-hours, about 35 minutes across 16 cores, so Experiment 2b is scheduled in Sprint 3 unconditionally rather than treated as optional. Experiment 1 stays at R = 200: that is correctly sized for confidence intervals on the *mean*, and inflating it would not serve a tail fit anyway.

What remains open at the gate is only the replicate count. If the fits show `x_min` sitting so high that fewer than ~2 decades of tail survive above it, raise R to 50,000 for the two headline conditions and narrow the condition set accordingly. Record the outcome here.

## 11. Glossary

| Term | Meaning here |
|---|---|
| **Budget** `b` | Fraction of *occupied* cells whose fuel load is reduced to `f_treat`. |
| **Condition** | A treatment geometry (`random`, `patches`, `strips_perp`, …) — the categorical factor. |
| **Regime** | `PERCOLATION` or `STUDY` — which rule parameterisation is in force. |
| **Clustering scale** | The linear size of a contiguous treated region: 1 for `random`, `k` for `patches`, `w` for `strips`. The continuous axis of the primary analysis. |
| **Efficiency** | `(burned_fraction[b=0] - burned_fraction[b]) / (n_treated / n_cells)` — burned area avoided per unit area treated. |
| **Spanning** | Fire started at one edge reaches the opposite edge. Edge ignition only. |
| **Scar** | The final state grid of one fire event. |
