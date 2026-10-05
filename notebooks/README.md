# notebooks/

The presentation layer over the project (`context/project-context.md` §9, DEC-016). A notebook adds prose, equations and interpretation on top of the figure registry in `figures/make_figures.py`; it is not a second source of figures, and the numbers it quotes come from `results/` or from a cell that computes them visibly.

## Running order

Read and run them in numeric order.

| # | Notebook | Prerequisite commands (from the repository root) |
|---|---|---|
| 01 | `01-model-and-validation.ipynb` — the model, a live demonstration, the invariant suite, the Experiment 0 validation | `python run.py --exp 0` |
| 02 | `02-treatment-geometries.ipynb` — what the arrangements look like, the clustering-scale axis, efficiency, the settlement trade-off, illustrative scars | `python run.py --exp 1` and `--exp scars` |
| 03 | `03-thresholds-and-tails.ipynb` — threshold shift, burn-size distributions, wind interaction, sensitivity, frame invariance, limitations | `python run.py --exp 0b`, `--exp 2`, `--exp 2b`, `--exp 3`, `--exp i11`, `--exp 4` |

`python run.py --exp all` produces everything the three notebooks read.

## Setup

```bash
pip install -r requirements.txt     # includes jupyter and ipykernel
python run.py --exp 0               # prerequisite for notebook 01
jupyter lab                         # or open the notebook in VS Code
```

Then open a notebook and choose *Restart & Run All*. The notebooks locate the repository root themselves, so they run wherever Jupyter was launched from.

## Conventions

- **Every notebook is committed with its outputs stored** (DEC-017), executed top to bottom with execution counts running 1, 2, 3, … and no out-of-order cells, so a reader sees the analysis without running anything. This is an exception to the rule against committing generated figures, scoped to `notebooks/*.ipynb`; `figures/out/` stays gitignored.
- **Each notebook begins with `%matplotlib inline`.** The builders construct a `Figure` directly rather than through `pyplot`, so without it a figure cell renders as `<Figure ...>` instead of the image, and the committed notebook would store no picture.
- **Figures come from the registry**: `from figures.make_figures import FIGURES`, then `FIGURES["name"]()`. A builder returns a figure and writes nothing to disk. A figure that is not registered is added to the registry (SPEC-08, SPEC-17), not drawn by hand in a notebook.
- **`run_fire` appears in notebook 01 only, in exactly one cell** (DEC-018): a seeded live demonstration at `L <= 128`, labelled as a demonstration and feeding no reported quantity. Notebooks 02 and 03 never call it.
- **Regenerate before committing.** After a change, re-execute in place so the stored outputs match the code:

  ```bash
  jupyter nbconvert --to notebook --execute --inplace notebooks/01-model-and-validation.ipynb
  ```

  Keep notebooks small. Committed outputs make for noisy diffs, so prefer registry figures to bespoke ones, and keep each notebook well under a megabyte.
- `.ipynb_checkpoints/` is gitignored; do not commit it.
