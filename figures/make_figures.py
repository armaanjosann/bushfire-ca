"""Every report figure, reading only from results/ (project-context.md §9).

Must never call the simulator. A builder reads parquet from `results/` and
returns a matplotlib `Figure`; it does not simulate, re-estimate a threshold or
write to disk. Only `build()` writes, so notebooks can display
`FIGURES[name]()` inline (DEC-016) and the clean-clone gate can write the same
figures to `figures/out/`, which is gitignored (DEC-017).

    python figures/make_figures.py --figure validation
    python figures/make_figures.py --all [--outdir figures/out]

Adding a figure (SPEC-17): write a function returning a `Figure` and decorate it
with `@figure("name", caption="...")`. The decorator registers it in `FIGURES`
and applies the shared style, and the caption sits next to the code that draws
the figure so the report and the code cannot drift.
"""

from __future__ import annotations

import argparse
import functools
import os
from pathlib import Path
from typing import Callable

import matplotlib as mpl
import numpy as np
import pandas as pd
from matplotlib.figure import Figure

RESULTS_DIR = Path(__file__).resolve().parents[1] / "results"
EXP0_PATH = "exp0.parquet"
PC_PATH = "pc_estimates.parquet"

# The published site-percolation threshold, square lattice, 8-neighbour
# connectivity. A validation target to be marked on the figure and nothing else:
# it is never an input to an estimate (project-context.md §6.1). Kept here as a
# literal so this module imports nothing from src/; tests/test_figures.py checks
# it equals src.model.P_C_LITERATURE.
P_C_LITERATURE = 0.407

VALIDATION_SIZES = (128, 256, 512)

# --- shared style -----------------------------------------------------------
# Categorical slots 1-3 of the reference palette, which validate for every pair
# (scatter-style use); one colour per lattice size, fixed, never cycled.
SERIES_COLOURS = {128: "#2a78d6", 256: "#eb6834", 512: "#1baf7a"}
SERIES_MARKERS = {128: "o", 256: "s", 512: "^"}
INK = "#0b0b0b"
INK_SECONDARY = "#52514e"
INK_MUTED = "#8a8985"
SURFACE = "#fcfcfb"
GRID = "#e4e3df"

STYLE = {
    "figure.facecolor": SURFACE,
    "axes.facecolor": SURFACE,
    "savefig.facecolor": SURFACE,
    "axes.edgecolor": INK_MUTED,
    "axes.labelcolor": INK_SECONDARY,
    "axes.titlecolor": INK,
    "axes.titlesize": 11,
    "axes.titleweight": "regular",
    "axes.titlelocation": "left",
    "axes.labelsize": 10,
    "axes.spines.top": False,
    "axes.spines.right": False,
    "axes.grid": True,
    "grid.color": GRID,
    "grid.linewidth": 0.8,
    "axes.axisbelow": True,
    "xtick.color": INK_SECONDARY,
    "ytick.color": INK_SECONDARY,
    "xtick.labelsize": 9,
    "ytick.labelsize": 9,
    "text.color": INK,
    "lines.linewidth": 1.6,
    "lines.markersize": 4.5,
    "legend.frameon": False,
    "legend.fontsize": 9,
    "font.size": 10,
    "figure.dpi": 100,
}
SAVE_DPI = 200

# --- registry ---------------------------------------------------------------
FIGURES: dict[str, Callable[[], Figure]] = {}
CAPTIONS: dict[str, str] = {}


def figure(name: str, *, caption: str):
    """Register a builder under `name` with its caption, in the shared style."""
    if name in FIGURES:
        raise ValueError(f"figure {name!r} is already registered")

    def register(fn: Callable[[], Figure]) -> Callable[[], Figure]:
        @functools.wraps(fn)
        def builder() -> Figure:
            with mpl.rc_context(STYLE):
                fig = fn()
            if not isinstance(fig, Figure):
                raise TypeError(f"builder {name!r} must return a Figure, got {type(fig).__name__}")
            return fig

        builder.caption = caption
        FIGURES[name] = builder
        CAPTIONS[name] = caption
        return builder

    return register


def build(name: str, outdir: str = "figures/out") -> str:
    """Build one registered figure, write it to `outdir`, return the file path."""
    if name not in FIGURES:
        raise KeyError(f"unknown figure {name!r}; registered: {', '.join(FIGURES)}")
    fig = FIGURES[name]()
    os.makedirs(outdir, exist_ok=True)
    path = os.path.join(outdir, f"{name}.png")
    # No Software tag: the file is then a pure function of the data and the code.
    fig.savefig(path, dpi=SAVE_DPI, metadata={"Software": None})
    return path


def build_all(outdir: str = "figures/out") -> list[str]:
    """Build every registered figure; return the file paths in registry order."""
    return [build(name, outdir) for name in FIGURES]


# --- reading results --------------------------------------------------------
def _read(filename: str, hint: str, columns: list[str]) -> pd.DataFrame:
    path = RESULTS_DIR / filename
    if not path.exists():
        raise FileNotFoundError(f"{path} is missing; {hint}. Figures are built from results/ only.")
    df = pd.read_parquet(path, columns=columns)
    if df.empty:
        raise ValueError(f"{path} has no rows")
    return df


def _wilson(k: np.ndarray, n: np.ndarray, z: float = 1.96) -> tuple[np.ndarray, np.ndarray]:
    """Wilson score interval for a binomial proportion."""
    phat = k / n
    denom = 1.0 + z**2 / n
    centre = (phat + z**2 / (2 * n)) / denom
    half = z * np.sqrt(phat * (1 - phat) / n + z**2 / (4 * n**2)) / denom
    return centre - half, centre + half


def _percolation_curves() -> dict[int, pd.DataFrame]:
    """P(span) against p per lattice size, from Experiment 0 only."""
    df = _read(EXP0_PATH, "run `python run.py --exp 0`",
               ["regime", "ignition", "L", "p", "spanned", "truncated"])
    if not (df["regime"] == "PERCOLATION").all() or not (df["ignition"] == "edge").all():
        raise ValueError(f"{EXP0_PATH} holds non-PERCOLATION or non-edge rows; "
                         "the validation figure plots Experiment 0 only")
    if df["spanned"].isna().any():
        raise ValueError(f"{EXP0_PATH} has null `spanned` values")
    if df["truncated"].any():
        raise ValueError(f"{EXP0_PATH} has truncated runs (I10)")
    missing = sorted(set(VALIDATION_SIZES) - set(df["L"].astype(int)))
    if missing:
        raise ValueError(f"{EXP0_PATH} has no rows for L = {missing}; the figure needs all of "
                         f"{list(VALIDATION_SIZES)}")
    curves = {}
    for size in VALIDATION_SIZES:
        sub = df[df["L"] == size].assign(spanned=lambda d: d["spanned"].astype(float))
        g = sub.groupby("p")["spanned"].agg(["sum", "count"]).sort_index()
        lo, hi = _wilson(g["sum"].to_numpy(float), g["count"].to_numpy(float))
        curves[size] = pd.DataFrame({"p": g.index.to_numpy(float), "P": (g["sum"] / g["count"]).to_numpy(),
                                     "lo": lo, "hi": hi})
    return curves


def _percolation_crossing() -> tuple[float, float]:
    """The PERCOLATION `fss_crossing` row of pc_estimates.parquet: (p_c, stderr)."""
    df = _read(PC_PATH, "run `python run.py --exp 0`",
               ["regime", "condition", "b", "kappa", "L", "p_c", "p_c_stderr", "method"])
    rows = df[(df["regime"] == "PERCOLATION") & (df["condition"] == "none") & (df["b"] == 0.0)
              & (df["kappa"] == 0.0) & (df["method"] == "fss_crossing") & df["L"].isna()]
    if len(rows) != 1:
        raise LookupError(f"{PC_PATH} has {len(rows)} PERCOLATION fss_crossing rows, expected exactly 1")
    return float(rows["p_c"].iloc[0]), float(rows["p_c_stderr"].iloc[0])


# --- figures ----------------------------------------------------------------
@figure(
    "validation",
    caption=(
        "Validation of the PERCOLATION regime (Experiment 0). Probability P(span) that a fire "
        "ignited along the top edge reaches the bottom edge, against site occupancy p, for "
        "L = 128, 256 and 512 (Moore neighbourhood; shaded bands are 95% Wilson intervals). "
        "(a) The full sweep. (b) The transition: the curves steepen with L and cross at the "
        "finite-size-scaling crossing (solid line, shaded to its standard error). The dashed "
        "line is the literature value P_C_LITERATURE = 0.407 for the 8-neighbour square "
        "lattice; it is a validation target only and enters no estimate. This threshold "
        "belongs to the PERCOLATION regime and is not comparable with any STUDY threshold."
    ),
)
def validation() -> Figure:
    curves = _percolation_curves()
    p_c, p_c_se = _percolation_crossing()

    fig = Figure(figsize=(12.5, 4.6), layout="constrained")
    ax_full, ax_zoom = fig.subplots(1, 2)
    zoom = (0.38, 0.44)

    for ax, in_zoom in ((ax_full, False), (ax_zoom, True)):
        for size, c in curves.items():
            colour = SERIES_COLOURS[size]
            ax.fill_between(c["p"], c["lo"], c["hi"], color=colour, alpha=0.15, linewidth=0)
            ax.plot(c["p"], c["P"], color=colour, marker=SERIES_MARKERS[size],
                    markersize=4.5 if in_zoom else 3, label=f"L = {size}")
        ax.axvspan(p_c - p_c_se, p_c + p_c_se, color=INK, alpha=0.18, linewidth=0)
        ax.axvline(p_c, color=INK, linewidth=1.2, label=f"FSS crossing  p = {p_c:.4f} ± {p_c_se:.4f}")
        ax.axvline(P_C_LITERATURE, color=INK_SECONDARY, linewidth=1.2, linestyle=(0, (4, 3)),
                   label=f"Literature  p = {P_C_LITERATURE} (validation target)")
        ax.set_xlabel("Site occupancy p")
        ax.set_ylabel("P(span)")
        ax.set_ylim(-0.02, 1.02)

    ax_full.set_xlim(0.30, 0.60)
    ax_full.set_title("(a) Full sweep")
    ax_zoom.set_xlim(*zoom)
    ax_zoom.set_title("(b) Near the transition")

    handles, labels = ax_zoom.get_legend_handles_labels()
    fig.legend(handles, labels, loc="outside lower center", ncol=5, columnspacing=1.6, handlelength=2.2)
    fig.suptitle("Experiment 0: site-percolation validation  (PERCOLATION regime; "
                 "not comparable with any STUDY threshold)", fontsize=11, color=INK_SECONDARY)
    return fig


# --- CLI --------------------------------------------------------------------
def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Build report figures from results/")
    which = parser.add_mutually_exclusive_group(required=True)
    which.add_argument("--figure", choices=sorted(FIGURES), help="build one figure")
    which.add_argument("--all", action="store_true", help="build every figure")
    parser.add_argument("--outdir", default="figures/out", help="output directory (gitignored)")
    args = parser.parse_args(argv)

    paths = build_all(args.outdir) if args.all else [build(args.figure, args.outdir)]
    for path in paths:
        print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
