# CITS4403 — Bushfire Spread CA with Fuel Management

A stochastic cellular automaton of fire spread over a lattice of fuel cells, with a directional wind kernel. A fixed budget of fuel treatment (prescribed burning) is applied before ignition, in one of several spatial arrangements. The project asks two things:

1. Does the *spatial arrangement* of a fixed treatment budget shift the system's critical fuel density, or does it only reduce burn size away from it?
2. Is the arrangement that minimises landscape-scale burned area the same one that minimises how quickly a settlement is reached?

The full specification (model rules, results schema, experiment grids, invariants) is `context/project-context.md`.

## Contribution

The base model is site percolation on a square lattice with a Moore neighbourhood, which is a known system. We use it as a **validation baseline only**: Experiment 0 recovers the known site-percolation threshold (0.407) to check the implementation.

What we add on top of that baseline:

- a stochastic fire-spread rule with a von Mises wind kernel and a diagonal distance factor;
- a fuel-treatment budget placed in six geometries (`random`, `patches`, `strips_perp`, `strips_para`, `buffer`, and the untreated reference), with the clustering scale swept across `random` → `patches` → `strips`;
- a measured critical fuel density per condition, rather than a literature value;
- burn-size distributions at each condition's own critical point, and a settlement metric (time to reach).

The validation threshold governs no substantive result, and the study thresholds are measured separately for each condition (`project-context.md` §2, O4).

## Setup

Requires Python 3.x (developed and verified on 3.12). The model uses Python and NumPy only; matplotlib, pandas and pyarrow handle results and figures, pytest runs the checks, and jupyter runs the notebooks.

```bash
python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
```

There is no external data to download. Every number comes from simulation, and the outputs are stored in `results/`.

## Reproduce everything

```bash
python run.py --exp all
```

This runs every experiment in dependency order. `results/` is committed, so on a fresh clone the runner **resumes**: it skips every configuration already present (matched on `run_id`), checks that recorded thresholds and fits still match what the data gives, and never rewrites a committed parquet. To regenerate an experiment from scratch, delete its file from `results/` first. The full grid is an overnight run on a multi-core machine (`project-context.md` §6.3).

Then check it:

```bash
pytest -q                              # invariants I1-I11 and unit tests
python figures/make_figures.py --all   # every figure, from results/ only, into figures/out/
```

## Usage

Run one experiment:

```bash
python run.py --exp 0      # percolation validation
python run.py --exp 0b     # untreated study thresholds (needed before 1)
python run.py --exp 1      # geometry x budget
python run.py --exp 2      # threshold shift per condition
python run.py --exp 2b     # burn-size tails at each condition's threshold
python run.py --exp 3      # wind interaction
python run.py --exp 4      # sensitivity
```

Auxiliary entries: `pilot` (settlement size pilot), `1-coarse`, `scars` (illustrative burn scars) and `i11` (lattice frame-invariance check). `all` runs them all in order.

Run a single fire from Python:

```python
from src.model import Config, run_fire

result = run_fire(Config(L=128, p=0.55, kappa=0.0, seed=1), capture_scar=True)
print(result.burned_fraction, result.steps)
```

`run_fire` is deterministic: the same `Config` always gives the same result.

Build one figure: `python figures/make_figures.py --figure threshold-shift`. The names are listed by `python figures/make_figures.py --help`.

## Reading order

Read the notebooks in numeric order. Each is committed with its outputs stored, so they can be read without running anything. Each is a presentation layer over `figures/make_figures.py`, not a second source of figures.

1. `notebooks/01-model-and-validation.ipynb` — the model, a live demonstration, the invariant suite, the Experiment 0 validation
2. `notebooks/02-treatment-geometries.ipynb` — the treatment arrangements, clustering scale, efficiency, the settlement trade-off
3. `notebooks/03-thresholds-and-tails.ipynb` — threshold shift, burn-size distributions, wind, sensitivity, limitations

See `notebooks/README.md` for per-notebook prerequisites.

## Repository layout

```
run.py            single entry point for every experiment
requirements.txt  dependencies
src/              all main code
  model.py          Config, run_fire, wind kernel, lattice initialisation
  geometries.py     the treatment geometry generators
  metrics.py        pure summary functions over a finished run
  experiments.py    experiment grids, parallel runner, parquet writers
  analysis.py       threshold estimation, finite-size scaling, tail fitting
figures/          make_figures.py: every figure, reading only from results/
notebooks/        three notebooks, committed with outputs
tests/            invariants I1-I11 plus unit tests
results/          simulation output, one row per run; tracked, append-only
context/          specification, workflow rules, per-task specs, decisions log
```

How this maps to the rubrics's suggested layout:

| Suggested | Here | Note |
|---|---|---|
| `src/` | `src/` | All model and experiment code. |
| `utils/` | `src/metrics.py`, `src/analysis.py`, `figures/make_figures.py` | Helper functions live beside the code that uses them rather than in a separate folder. |
| `data/` | `results/` | The project has no input dataset. `results/` holds the simulation output, tracked so a clone has the exact numbers behind every figure. |
| `notebooks/` | `notebooks/` | As above. |

## Design notes

- **Reproducible by construction.** Every run draws from its own seeded generator, with no global random state, and every result row records the git SHA of the code that produced it.
- **Results are append-only.** A committed parquet is never edited; reruns resume or write a new file.
- **Two regimes that must not be mixed.** `PERCOLATION` (validation only) and `STUDY` (all substantive experiments) use different rule parameters, and the code refuses inconsistent combinations.
- **Truncation is never filtered.** Every reported run finishes; the analysis layer asserts it.
