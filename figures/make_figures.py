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
import json
import os
from pathlib import Path
from typing import Callable

import matplotlib as mpl
import numpy as np
import pandas as pd
from matplotlib.colors import ListedColormap
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


# --- coarse Experiment 1 heatmap (SPEC-12) ----------------------------------
EXP1_COARSE_PATH = "exp1_coarse.parquet"
# Row order: random, then the clustering-scale continuum (§4.2), then the targeted buffer.
COARSE_LEVELS = (
    [("random", None)]
    + [("patches", k) for k in (4, 8, 16)]
    + [("strips_perp", w) for w in (4, 8, 16)]
    + [("strips_para", w) for w in (4, 8, 16)]
    + [("buffer", None)]
)
COARSE_PANELS = [(kappa, rel) for kappa in (0.0, 2.0) for rel in (-0.05, 0.0, 0.05, None)]
COARSE_CMAP = mpl.colors.LinearSegmentedColormap.from_list("burn", [SURFACE, "#2a78d6", "#0a2a52"])


def _coarse_level(condition: str, geometry_params: str):
    """(condition, k or w) from a row; `settlement_side` is not part of the level."""
    prm = json.loads(geometry_params)
    return condition, prm.get("k", prm.get("w"))


def _coarse_label(level) -> str:
    condition, scale = level
    return condition if scale is None else f"{condition} {'k' if condition == 'patches' else 'w'}={scale}"


def _coarse_frame() -> pd.DataFrame:
    df = _read(EXP1_COARSE_PATH, "run `python run.py --exp 1-coarse`",
               ["regime", "settlement", "condition", "geometry_params", "b", "kappa", "p", "p_rel",
                "burned_fraction", "truncated"])
    if not (df["regime"] == "STUDY").all() or not df["settlement"].all():
        raise ValueError(f"{EXP1_COARSE_PATH} holds non-STUDY or no-settlement rows")
    if df["truncated"].any():
        raise ValueError(f"{EXP1_COARSE_PATH} has truncated runs (I10)")
    df = df.assign(level=[_coarse_label(_coarse_level(c, g))
                          for c, g in zip(df["condition"], df["geometry_params"])])
    untreated = df[(df["condition"] == "none") & (df["b"] == 0.0)]
    if untreated.empty:
        raise ValueError(f"{EXP1_COARSE_PATH} has no untreated (`none`, b=0) rows")
    return df


@figure(
    "exp1-coarse",
    caption=(
        "Coarse Experiment 1: a first look at where treatment geometry and budget matter, not a "
        "result. Mean burned fraction A of the lattice (burned cells / lattice cells) for each "
        "treatment geometry (rows) and budget b (columns), for a fire from one random fuel cell "
        "on a lattice with a settlement. Panels are wind strength kappa (rows of panels) by fuel "
        "density: 0.05 below, at and 0.05 above the untreated threshold p_c of that kappa "
        "(Experiment 0b), and the absolute p = 0.70. The b = 0 column is the untreated run, "
        "repeated for every geometry. Each panel has its own colour scale, because A differs by "
        "orders of magnitude between densities. Replicates are reduced, so cell-to-cell "
        "differences are indicative only; the full grid is Experiment 1."
    ),
)
def exp1_coarse() -> Figure:
    df = _coarse_frame()
    budgets = sorted(df["b"].unique())
    levels = [_coarse_label(lv) for lv in COARSE_LEVELS]

    fig = Figure(figsize=(17.5, 10.5), layout="constrained")
    axes = fig.subplots(2, 4)
    for ax, (kappa, rel) in zip(axes.ravel(), COARSE_PANELS):
        sel = df["kappa"] == kappa
        sel &= df["p_rel"].isna() if rel is None else np.isclose(df["p_rel"].fillna(np.inf), rel)
        sub = df[sel]
        if sub.empty:
            raise ValueError(f"{EXP1_COARSE_PATH} has no rows for kappa={kappa}, p_rel={rel}")
        mean = sub.groupby(["level", "b"])["burned_fraction"].mean()
        base = float(sub[sub["condition"] == "none"]["burned_fraction"].mean())
        grid = np.array([[base if b == 0.0 else mean.get((lv, b), np.nan) for b in budgets]
                         for lv in levels])
        if np.isnan(grid).any():
            raise ValueError(f"{EXP1_COARSE_PATH} is missing cells for kappa={kappa}, p_rel={rel}")

        im = ax.imshow(grid, cmap=COARSE_CMAP, vmin=0.0, vmax=float(grid.max()) or 1.0, aspect="auto")
        for i in range(grid.shape[0]):
            for j in range(grid.shape[1]):
                v = grid[i, j]
                ax.text(j, i, f"{v:.3f}" if v < 0.1 else f"{v:.2f}", ha="center", va="center",
                        fontsize=7.5, color="white" if v > 0.55 * grid.max() else INK)
        ax.set_xticks(range(len(budgets)), [f"{b:g}" for b in budgets])
        ax.set_yticks(range(len(levels)), levels)
        ax.tick_params(length=0)
        ax.grid(False)
        for side in ax.spines.values():
            side.set_visible(False)
        ax.set_xlabel("budget b")
        where = "p = 0.70" if rel is None else f"p_c {rel:+.2f}"
        ax.set_title(f"kappa = {kappa:g}, {where}  (p = {sub['p'].iloc[0]:.3f})")
        cb = fig.colorbar(im, ax=ax, shrink=0.85, pad=0.02)
        cb.ax.tick_params(labelsize=7)
        cb.outline.set_visible(False)

    n = df.groupby(["kappa", "p", "level", "b"]).size()
    reps = f"{n.min()}" if n.min() == n.max() else f"{n.min()}-{n.max()}"
    fig.suptitle(f"Coarse Experiment 1: mean burned fraction A(geometry, b)  "
                 f"(STUDY, L = 256, {reps} replicates per cell)", fontsize=11, color=INK_SECONDARY)
    return fig


# --- CLI --------------------------------------------------------------------
# ===========================================================================
# Results figures (SPEC-17)
# ===========================================================================

EXP1_PATH = "exp1.parquet"
EXP2B_PATH = "exp2b.parquet"
EXP2_SCALE_PATH = "exp2_scale.parquet"
EXP3_PATH = "exp3.parquet"
EXP4_PATH = "exp4.parquet"
TAIL_FITS_PATH = "tail_fits.parquet"
SCARS_PATH = "scars_illustrative.npz"

HEADLINE_B = 0.15          # the budget the report leads with
HEADLINE_P_REL = 0.05      # 0.05 above the untreated threshold

# One colour per condition family, fixed everywhere, so a reader learns them once.
FAMILY_COLOURS = {
    "none": INK_MUTED, "random": "#2a78d6", "patches": "#eb6834",
    "strips_perp": "#1baf7a", "strips_para": "#a06cd5", "buffer": "#d64550",
}
FAMILY_MARKERS = {"none": "x", "random": "o", "patches": "s",
                  "strips_perp": "^", "strips_para": "v", "buffer": "D"}
# Clustering scale (§11): random is 1, patches is k, strips is w. `buffer` is the
# targeted condition and sits off the axis, so it is never plotted on it.
OFF_AXIS = ("none", "buffer")


def _scale_of(condition: str, geometry_params: str) -> float | None:
    prm = json.loads(geometry_params)
    if condition == "random":
        return 1.0
    if condition in OFF_AXIS:
        return None
    value = prm.get("k", prm.get("w"))
    return None if value is None else float(value)


def _label_of(condition: str, geometry_params: str) -> str:
    scale = _scale_of(condition, geometry_params)
    if condition in OFF_AXIS or scale is None or condition == "random":
        return condition
    key = "k" if condition == "patches" else "w"
    return f"{condition} {key}={int(scale)}"


_SCALES = (1.0, 4.0, 8.0, 16.0)


def _colour(condition: str, scale: float | None = None) -> tuple:
    """The family colour, lightened for a smaller clustering scale so the three
    levels of one family are told apart without a second colour axis."""
    base = mpl.colors.to_rgb(FAMILY_COLOURS.get(condition, INK_MUTED))
    if scale is None or condition in OFF_AXIS or condition == "random":
        return (*base, 1.0)
    i = _SCALES.index(float(scale)) if float(scale) in _SCALES else 1
    mix = 0.55 - 0.18 * i                       # smaller scale -> paler
    return (*tuple(c + (1.0 - c) * max(mix, 0.0) for c in base), 1.0)


def _with_levels(df: pd.DataFrame) -> pd.DataFrame:
    """Add `level` (display label) and `scale` (clustering scale) columns."""
    return df.assign(
        level=[_label_of(c, g) for c, g in zip(df["condition"], df["geometry_params"])],
        scale=[_scale_of(c, g) for c, g in zip(df["condition"], df["geometry_params"])],
    )


def _exp1(columns: list[str]) -> pd.DataFrame:
    df = _read(EXP1_PATH, "run `python run.py --exp 1`", columns)
    if df["truncated"].any():
        raise ValueError(f"{EXP1_PATH} has truncated runs (I10)")
    return _with_levels(df)


def _headline_slice(df: pd.DataFrame, kappa: float) -> pd.DataFrame:
    """The operating point the report leads with: p_c + 0.05 at one wind strength."""
    sel = (df["kappa"] == kappa) & np.isclose(df["p_rel"].fillna(np.inf), HEADLINE_P_REL)
    out = df[sel]
    if out.empty:
        raise ValueError(f"{EXP1_PATH} has no rows at kappa={kappa}, p_rel={HEADLINE_P_REL}")
    return out


def _realised_budget(df: pd.DataFrame) -> float:
    """Mean realised treated fraction of the fuel, which is what `b` means in
    results (§11): n_treated / n_occupied, never the nominal budget."""
    return float((df["n_treated"] / df["n_occupied"]).mean())


# --- 1. the clustering-scale curve ------------------------------------------


@figure(
    "clustering-scale",
    caption=(
        "Mean burned fraction A against the clustering scale of the treatment, the "
        "continuous axis of the primary analysis (project-context.md §11): scale 1 is "
        "`random`, scale k is `patches(k)`, scale w is `strips(w)`. Fires start at one "
        "random fuel cell on a 256x256 lattice with a settlement; each point is 200 "
        "replicates. Panels are fuel density: 0.05 above the untreated threshold (left) "
        "and the absolute p = 0.70 well above it (right), both with no wind. Line style "
        "separates the three families that share the axis; `buffer` is the targeted "
        "condition and sits off this axis, so it is not shown. Bands are +/- 1 standard "
        "error of the mean. Budgets are the realised treated fraction of the fuel."
    ),
)
def clustering_scale() -> Figure:
    df = _exp1(["condition", "geometry_params", "b", "kappa", "p_rel", "p",
                "burned_fraction", "n_treated", "n_occupied", "truncated"])
    df = df[(df["kappa"] == 0.0) & df["scale"].notna()]
    budgets = [0.05, 0.15, 0.30]
    panels = [("p_rel", HEADLINE_P_REL, "0.05 above the untreated threshold"),
              ("p_abs", 0.70, "p = 0.70, well above it")]
    styles = {"patches": "-", "strips_perp": "--", "strips_para": ":"}

    fig = Figure(figsize=(12.5, 5.2), layout="constrained")
    axes = fig.subplots(1, 2, sharey=True)
    for ax, (kind, value, title) in zip(axes, panels):
        sel = (np.isclose(df["p_rel"].fillna(np.inf), value) if kind == "p_rel"
               else df["p_rel"].isna() & np.isclose(df["p"], value))
        sub = df[sel]
        if sub.empty:
            raise ValueError(f"{EXP1_PATH} has no rows for {kind}={value}")
        for i, b in enumerate(budgets):
            at_b = sub[np.isclose(sub["b"], b)]
            shade = 0.35 + 0.65 * i / max(len(budgets) - 1, 1)
            realised = _realised_budget(at_b)
            rnd = at_b[at_b["condition"] == "random"]
            for family, style in styles.items():
                fam = at_b[at_b["condition"] == family]
                if fam.empty:
                    continue
                g = fam.groupby("scale")["burned_fraction"].agg(["mean", "sem"]).sort_index()
                # `random` is scale 1 of the same axis, so every family line starts
                # from it: that is what makes this a continuum and not three charts
                x = np.concatenate([[1.0], g.index.to_numpy()])
                mean = np.concatenate([[rnd["burned_fraction"].mean()], g["mean"].to_numpy()])
                sem = np.concatenate([[rnd["burned_fraction"].sem()], g["sem"].to_numpy()])
                colour = mpl.colors.to_rgba(FAMILY_COLOURS[family], shade)
                ax.plot(x, mean, style, color=colour, marker=FAMILY_MARKERS[family],
                        label=f"{family}, b = {realised:.2f}")
                ax.fill_between(x, mean - sem, mean + sem, color=colour, alpha=0.18, linewidth=0)
            if not rnd.empty:
                ax.plot([1.0], [rnd["burned_fraction"].mean()], "o",
                        color=mpl.colors.to_rgba(FAMILY_COLOURS["random"], shade), markersize=7)
        ax.set_xscale("log", base=2)
        ax.set_xticks([1, 4, 8, 16], ["1\n(random)", "4", "8", "16"])
        ax.set_xlabel("clustering scale of the treatment")
        ax.set_title(title)
    axes[0].set_ylabel("mean burned fraction A")
    axes[0].set_yscale("log")
    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="outside right upper", fontsize=8,
               title="family and budget", title_fontsize=9)
    fig.suptitle("Treatment clustering scale against burned area (STUDY, L = 256, no wind, R = 200)",
                 fontsize=11, color=INK_SECONDARY)
    return fig


# --- 2. efficiency -----------------------------------------------------------


@figure(
    "efficiency",
    caption=(
        "Treatment efficiency by condition and budget: burned area avoided per unit area "
        "treated, (A[untreated] - A[condition]) / (n_treated / n_cells), using the "
        "**realised** treated count on every row, never the nominal budget "
        "(project-context.md §11). Fuel density 0.05 above the untreated threshold, no "
        "wind, L = 256, 200 replicates per cell. Higher is better. Error bars are +/- 1 "
        "standard error, propagated from the treated and untreated means. Efficiency "
        "falls with budget for every condition, which is diminishing returns (SQ2)."
    ),
)
def efficiency() -> Figure:
    df = _headline_slice(
        _exp1(["condition", "geometry_params", "b", "kappa", "p_rel", "burned_fraction",
               "n_treated", "n_cells", "n_occupied", "truncated"]), 0.0)
    untreated = df[df["condition"] == "none"]["burned_fraction"]
    if untreated.empty:
        raise ValueError(f"{EXP1_PATH} has no untreated rows at the headline operating point")
    base, base_sem = float(untreated.mean()), float(untreated.sem())

    budgets = sorted(b for b in df["b"].unique() if b > 0)
    order = {"random": 0, "patches": 1, "strips_perp": 2, "strips_para": 3, "buffer": 4}
    keyed = df[df["condition"] != "none"].drop_duplicates("level")
    levels = [lv for _, lv in sorted(
        zip(zip(keyed["condition"].map(order).fillna(9), keyed["scale"].fillna(0)), keyed["level"]))]

    fig = Figure(figsize=(12.5, 5.4), layout="constrained")
    ax = fig.subplots()
    width = 0.8 / len(budgets)
    for i, b in enumerate(budgets):
        means, errs = [], []
        for lv in levels:
            cell = df[(df["level"] == lv) & np.isclose(df["b"], b)]
            if cell.empty:
                means.append(np.nan); errs.append(np.nan); continue
            treated_area = float((cell["n_treated"] / cell["n_cells"]).mean())
            means.append((base - cell["burned_fraction"].mean()) / treated_area)
            errs.append(float(np.hypot(base_sem, cell["burned_fraction"].sem())) / treated_area)
        x = np.arange(len(levels)) + (i - (len(budgets) - 1) / 2) * width
        ax.bar(x, means, width, yerr=errs, capsize=2, label=f"b = {b:g}",
               color=mpl.cm.viridis(0.15 + 0.7 * i / max(len(budgets) - 1, 1)),
               edgecolor="none", error_kw={"elinewidth": 0.9, "ecolor": INK_MUTED})
    ax.set_xticks(np.arange(len(levels)), levels, rotation=30, ha="right")
    ax.set_ylabel("burned area avoided per unit area treated")
    ax.axhline(0, color=INK_MUTED, linewidth=0.9)
    ax.legend(ncol=len(budgets), fontsize=9)
    ax.set_title("Efficiency of each treatment arrangement (STUDY, L = 256, no wind, "
                 "p = p_c + 0.05, R = 200)")
    return fig


# --- 3. threshold shift ------------------------------------------------------


@figure(
    "threshold-shift",
    caption=(
        "Measured critical fuel density p_c of each treated landscape at b = 0.15, against "
        "the untreated STUDY baseline (Experiment 0b, kappa = 0). Bars are +/- 1 bootstrap "
        "standard error on the finite-size-scaling crossing across L in {128, 256, 512}, "
        "R = 500. `random` and `patches(4)` have a crossing, so a single threshold; "
        "`strips_perp(4)` has none, because its curves do not cross: its 50% spanning point "
        "falls steadily with lattice size, so the three per-L points are shown instead and "
        "no single value is quoted (DEC-041). Every threshold here is a STUDY value; the "
        "PERCOLATION validation threshold is a different quantity and never appears "
        "alongside these (project-context.md §10.1 D5)."
    ),
)
def threshold_shift() -> Figure:
    pc = _read(PC_PATH, "run `python run.py --exp 0b` and `--exp 2`",
               ["regime", "condition", "b", "kappa", "L", "p_c", "p_c_stderr", "method"])
    study = pc[(pc["regime"] == "STUDY") & (pc["method"] == "fss_crossing") & pc["L"].isna()
               & (pc["kappa"] == 0.0)]
    base = study[(study["condition"] == "none") & (study["b"] == 0.0)]
    if len(base) != 1:
        raise LookupError(f"{PC_PATH} has {len(base)} untreated STUDY kappa=0 crossings, expected 1")
    baseline, baseline_se = float(base["p_c"].iloc[0]), float(base["p_c_stderr"].iloc[0])

    treated = study[np.isclose(study["b"], HEADLINE_B)].sort_values("p_c")
    scale = _read(EXP2_SCALE_PATH, "run `python run.py --exp 2`",
                  ["regime", "condition", "b", "kappa", "L", "p50", "p50_stderr"])
    scale = scale[np.isclose(scale["b"], HEADLINE_B) & (scale["kappa"] == 0.0)]
    no_crossing = sorted(set(scale["condition"]) - set(treated["condition"]))

    rows = [("untreated (b = 0)", baseline, baseline_se)]
    rows += [(c, float(r["p_c"]), float(r["p_c_stderr"])) for c, r in
             zip(treated["condition"], treated.to_dict("records"))]
    fig = Figure(figsize=(11.5, 5.6), layout="constrained")
    ax = fig.subplots()
    y = np.arange(len(rows) + len(no_crossing))
    for i, (label, value, err) in enumerate(rows):
        colour = FAMILY_COLOURS.get(label.split()[0], INK_MUTED)
        ax.errorbar(value, i, xerr=max(err, 1e-9) * 1.96, fmt="o", color=colour, capsize=4,
                    markersize=7, zorder=3)
        ax.annotate(f"{value:.4f}", (value, i), textcoords="offset points", xytext=(0, 11),
                    ha="center", fontsize=9, color=INK_SECONDARY)
    labels = [r[0] for r in rows]
    for j, condition in enumerate(no_crossing):
        i = len(rows) + j
        sub = scale[scale["condition"] == condition].sort_values("L")
        colour = FAMILY_COLOURS.get(condition, INK_MUTED)
        ax.plot(sub["p50"], np.full(len(sub), i), "-", color=colour, alpha=0.5, zorder=2)
        for _, r in sub.iterrows():
            ax.plot(r["p50"], i, "o", color=colour, markersize=6, zorder=3)
            ax.annotate(f"L={int(r['L'])}", (r["p50"], i), textcoords="offset points",
                        xytext=(0, 11), ha="center", fontsize=8, color=INK_SECONDARY)
        labels.append(f"{condition}\n(no scale-free value)")
    ax.axvline(baseline, color=INK_MUTED, linestyle="--", linewidth=1.1, zorder=1)
    ax.annotate("untreated baseline", (baseline, len(labels) - 0.45), fontsize=8,
                color=INK_MUTED, ha="right", xytext=(-6, 0), textcoords="offset points")
    ax.set_yticks(y, labels)
    ax.set_ylim(-0.6, len(labels) - 0.3)
    ax.invert_yaxis()
    ax.set_xlabel("critical fuel density p_c")
    ax.set_title("Does treatment move the critical point? (STUDY, b = 0.15, no wind, edge "
                 "ignition, R = 500)")
    return fig


# --- 4. burn-size distributions ---------------------------------------------


@figure(
    "burn-size-distributions",
    caption=(
        "Burn-size distributions at each condition's own critical point (Experiment 2b, "
        "STUDY, L = 256, one random ignition, no settlement, R = 10,000). Survival function "
        "P(X >= s) on log-log axes; a straight line would be a power law. Dashed curves are "
        "the fitted power law with exponential cutoff. **The fit is rejected for every "
        "condition**: each KS distance is about eight times its 5% critical value, because "
        "at a critical point on a finite lattice the distribution is a shallow power law "
        "followed by a pile-up of fires that span the lattice, which no monotonically "
        "decaying model represents. No exponent or cutoff from this figure may be quoted as "
        "a measured value (DEC-043). What the figure does show is that the distributions "
        "differ between conditions."
    ),
)
def burn_size_distributions() -> Figure:
    df = _read(EXP2B_PATH, "run `python run.py --exp 2b`",
               ["condition", "geometry_params", "burned_cells", "p", "L", "truncated"])
    if df["truncated"].any():
        raise ValueError(f"{EXP2B_PATH} has truncated runs (I10)")
    fits = _read(TAIL_FITS_PATH, "run `python run.py --exp 2b`",
                 ["condition", "geometry_params", "x_min", "x_max", "alpha", "cutoff",
                  "ks_distance", "ks_critical", "fit_rejected", "n_tail"])
    df = _with_levels(df)
    fig = Figure(figsize=(11.5, 6.0), layout="constrained")
    ax = fig.subplots()
    for level, sub in df.groupby("level"):
        condition = sub["condition"].iloc[0]
        s = np.sort(sub["burned_cells"].to_numpy())
        s = s[s > 0]
        vals, counts = np.unique(s, return_counts=True)
        surv = 1.0 - (np.cumsum(counts) - counts) / s.size
        colour = FAMILY_COLOURS.get(condition, INK_MUTED)
        ax.step(vals, surv, where="post", color=colour, linewidth=1.6,
                label=f"{level}  (p = {sub['p'].iloc[0]:.4f})")
        row = fits[fits["condition"] == condition]
        if len(row) == 1:
            r = row.iloc[0]
            grid = np.arange(int(r["x_min"]), int(r["x_max"]) + 1, dtype=float)
            w = grid ** (-float(r["alpha"])) * np.exp(-grid / float(r["cutoff"]))
            model = 1.0 - np.cumsum(w / w.sum())
            keep = grid <= vals.max()
            ax.plot(grid[keep], model[keep] * float(np.interp(r["x_min"], vals, surv)),
                    "--", color=colour, linewidth=1.1, alpha=0.85)
    ax.set_xscale("log"); ax.set_yscale("log")
    ax.set_ylim(1e-3, 1.4)      # below 1e-3 is fewer than 10 of 10,000 runs: noise
    ax.set_xlabel("burn size s (cells)")
    ax.set_ylabel("P(burn size >= s)")
    rejected = fits[fits["fit_rejected"] > 0]["condition"].tolist()
    ax.set_title("Burn-size distributions, each condition at its own critical point")
    ax.legend(fontsize=9, loc="lower left")
    if rejected:
        ax.annotate(
            "Dashed curves are the fitted power law with cutoff.\n"
            f"The fit is REJECTED for {', '.join(rejected)}:\n"
            "the curve is flat then falls off a cliff, which is a\n"
            "finite-size pile-up, not a power-law tail (DEC-043).",
            xy=(0.98, 0.97), xycoords="axes fraction", ha="right", va="top", fontsize=9,
            color=INK_SECONDARY,
            bbox={"boxstyle": "round,pad=0.5", "facecolor": "white", "edgecolor": GRID})
    return fig


# --- 5. the SQ4 trade-off ----------------------------------------------------


@figure(
    "sq4-tradeoff",
    caption=(
        "The asset-against-landscape trade-off (SQ4). Each point is one treatment "
        "arrangement at the realised budget shown, placed by the mean fraction of the "
        "landscape burned (x) and the fraction of fires that reached the settlement ring "
        "(y). Fuel density 0.05 above the untreated threshold, L = 256, 200 replicates; "
        "panels are no wind and strong wind. Bars are +/- 1 standard error. The bottom-left "
        "corner is best on both measures. `buffer` sits bottom-right: it protects the "
        "settlement completely while leaving much more of the landscape burnt than the "
        "strip arrangements, so the arrangement that best protects the asset is not the one "
        "that best protects the landscape."
    ),
)
def sq4_tradeoff() -> Figure:
    df = _exp1(["condition", "geometry_params", "b", "kappa", "p_rel", "burned_fraction",
                "settlement_reached", "n_treated", "n_occupied", "truncated"])
    if df["settlement_reached"].isna().any():
        raise ValueError(f"{EXP1_PATH} has null settlement_reached; SQ4 needs it on every row")
    fig = Figure(figsize=(12.5, 5.6), layout="constrained")
    axes = fig.subplots(1, 2, sharey=True)
    for ax, kappa in zip(axes, (0.0, 2.0)):
        sub = _headline_slice(df, kappa)
        sub = sub[(np.isclose(sub["b"], HEADLINE_B)) | (sub["condition"] == "none")]
        for level, cell in sub.groupby("level"):
            condition = cell["condition"].iloc[0]
            x, y = cell["burned_fraction"].mean(), cell["settlement_reached"].astype(float).mean()
            xe, ye = cell["burned_fraction"].sem(), cell["settlement_reached"].astype(float).sem()
            ax.errorbar(x, y, xerr=xe, yerr=ye, fmt=FAMILY_MARKERS.get(condition, "o"),
                        color=_colour(condition, cell["scale"].iloc[0]), markersize=8,
                        capsize=3, label=level)
        realised = _realised_budget(sub[sub["condition"] != "none"])
        ax.set_xlabel("mean fraction of the landscape burned")
        ax.set_title(f"{'no wind' if kappa == 0 else f'wind, kappa = {kappa:g}'}  "
                     f"(treated b = {realised:.2f})")
    axes[0].set_ylabel("fraction of fires that reached the settlement")
    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="outside right upper", fontsize=8, title="arrangement",
               title_fontsize=9)
    fig.suptitle("Protecting the landscape against protecting the settlement (SQ4)",
                 fontsize=11, color=INK_SECONDARY)
    return fig


# --- 6. wind interaction -----------------------------------------------------


@figure(
    "wind-interaction",
    caption=(
        "Experiment 3: is the ranking of treatment arrangements wind-dependent (SQ1)? Mean "
        "burned fraction (left) and the fraction of fires reaching the settlement (right) "
        "against wind strength kappa, each arrangement at b = 0.15 and at the untreated "
        "threshold of that same kappa plus 0.05, so every point sits at a comparable "
        "distance from its own critical point. L = 256, 200 replicates per point, bands are "
        "+/- 1 standard error. Strips across the wind are best at every wind strength, and "
        "the gap to strips along the wind widens as wind strengthens; the middle of the "
        "ranking does reorder."
    ),
)
def wind_interaction() -> Figure:
    df = _read(EXP3_PATH, "run `python run.py --exp 3`",
               ["condition", "geometry_params", "kappa", "b", "burned_fraction",
                "settlement_reached", "truncated"])
    if df["truncated"].any():
        raise ValueError(f"{EXP3_PATH} has truncated runs (I10)")
    df = _with_levels(df)
    fig = Figure(figsize=(12.5, 5.4), layout="constrained")
    axes = fig.subplots(1, 2)
    panels = [("burned_fraction", "mean burned fraction A", axes[0]),
              ("settlement_reached", "fraction of fires reaching the settlement", axes[1])]
    for column, ylabel, ax in panels:
        for level, sub in df.groupby("level"):
            condition = sub["condition"].iloc[0]
            g = sub.assign(v=sub[column].astype(float)).groupby("kappa")["v"].agg(["mean", "sem"])
            g = g.sort_index()
            colour = _colour(condition, sub["scale"].iloc[0])
            style = "--" if condition == "strips_para" else ("-." if condition == "none" else "-")
            ax.plot(g.index, g["mean"], style, color=colour,
                    marker=FAMILY_MARKERS.get(condition, "o"), label=level)
            ax.fill_between(g.index, g["mean"] - g["sem"], g["mean"] + g["sem"],
                            color=colour, alpha=0.15, linewidth=0)
        ax.set_xlabel("wind strength kappa")
        ax.set_ylabel(ylabel)
        ax.set_xticks(sorted(df["kappa"].unique()))
    axes[0].set_yscale("log")
    axes[1].legend(fontsize=8, ncol=2)
    fig.suptitle("Wind interaction: does the ranking of arrangements depend on wind? "
                 "(STUDY, L = 256, b = 0.15, p = p_c(kappa) + 0.05, R = 200)",
                 fontsize=11, color=INK_SECONDARY)
    return fig


# --- 7. sensitivity ----------------------------------------------------------


@figure(
    "sensitivity",
    caption=(
        "Experiment 4: do the conclusions survive the parameter choices? Mean burned "
        "fraction against the base spread probability beta, one panel per treated-fuel load "
        "f_treat, with the reduced condition set. All 9,000 runs sit at a single absolute "
        "fuel density p = 0.5504, the kappa = 2 untreated threshold plus 0.05, held fixed "
        "across every cell so the landscape does not move with beta (DEC-011). L = 256, "
        "200 replicates per point, bands are +/- 1 standard error. The ranking of "
        "arrangements is unchanged across beta, so it is not an artefact of fixing beta at "
        "0.8; f_treat matters more, and at f_treat = 0.4 the arrangements converge, because "
        "treated fuel that still burns readily stops acting as a break."
    ),
)
def sensitivity() -> Figure:
    df = _read(EXP4_PATH, "run `python run.py --exp 4`",
               ["condition", "geometry_params", "beta", "f_treat", "burned_fraction", "truncated"])
    if df["truncated"].any():
        raise ValueError(f"{EXP4_PATH} has truncated runs (I10)")
    df = _with_levels(df)
    loads = sorted(df["f_treat"].unique())
    fig = Figure(figsize=(13.0, 4.8), layout="constrained")
    axes = fig.subplots(1, len(loads), sharey=True)
    for ax, load in zip(np.atleast_1d(axes), loads):
        sub = df[np.isclose(df["f_treat"], load)]
        for level, cell in sub.groupby("level"):
            condition = cell["condition"].iloc[0]
            g = cell.groupby("beta")["burned_fraction"].agg(["mean", "sem"]).sort_index()
            colour = _colour(condition, cell["scale"].iloc[0])
            ax.plot(g.index, g["mean"], "-." if condition == "none" else "-", color=colour,
                    marker=FAMILY_MARKERS.get(condition, "o"), label=level)
            ax.fill_between(g.index, g["mean"] - g["sem"], g["mean"] + g["sem"],
                            color=colour, alpha=0.15, linewidth=0)
        ax.set_xlabel("base spread probability beta")
        ax.set_xticks(sorted(sub["beta"].unique()))
        ax.set_title(f"treated fuel load f_treat = {load:g}")
    np.atleast_1d(axes)[0].set_ylabel("mean burned fraction A")
    np.atleast_1d(axes)[0].set_yscale("log")
    np.atleast_1d(axes)[-1].legend(fontsize=8)
    fig.suptitle("Sensitivity: the ranking of arrangements against beta and treated fuel load "
                 "(STUDY, L = 256, kappa = 2, one fixed p = 0.5504, R = 200)",
                 fontsize=11, color=INK_SECONDARY)
    return fig


# --- 8 and 9. illustrative scars and the space-time view ---------------------


def _scars() -> tuple[list[str], dict]:
    path = RESULTS_DIR / SCARS_PATH
    if not path.exists():
        raise FileNotFoundError(
            f"{path} is missing; run `python run.py --exp scars`. Figures are built from "
            "results/ only and never call the simulator.")
    with np.load(path, allow_pickle=False) as z:
        run_ids = [str(r) for r in z["run_ids"]]
        data = {}
        for rid in run_ids:
            for key in ("scar", "ignition_step", "config"):
                name = f"{rid}__{key}"
                if name not in z:
                    raise ValueError(f"{path} is missing {name}; rerun `python run.py --exp scars`")
            data[rid] = {"scar": z[f"{rid}__scar"], "ignition_step": z[f"{rid}__ignition_step"],
                         "config": json.loads(str(z[f"{rid}__config"]))}
    return run_ids, data


def _scar_title(cfg: dict) -> str:
    prm = {k: v for k, v in cfg.get("geometry_params", {}).items() if k != "settlement_side"}
    name = cfg["condition"] + (f" {list(prm)[0]}={list(prm.values())[0]}" if prm else "")
    wind = "no wind" if cfg["kappa"] == 0 else f"kappa = {cfg['kappa']:g}"
    return f"{name}, b = {cfg['b']:g}\n{wind}"


# Cell states, as src/model.py defines them. Kept as literals so this module
# imports nothing from src/; tests/test_figures.py checks they agree.
EMPTY, FUEL, BURNING, BURNT, SETTLEMENT = 0, 1, 2, 3, 4
SCAR_COLOURS = ListedColormap(["#efe9dc", "#6a9a45", "#ff4d1a", "#2b1d14", "#2f6fd1"])


@figure(
    "scars",
    caption=(
        "Illustrative burn scars: one fire under each treatment arrangement, drawn from "
        "Experiment 1 itself (replicate 0 of the named configurations, L = 256, fuel density "
        "0.05 above the untreated threshold). Dark is burnt, green is fuel the fire never "
        "reached, pale is bare ground, blue is the settlement. Treated fuel is not shaded "
        "separately: a treatment changes a cell's fuel load, not its state. These are single "
        "runs shown for shape, not evidence of a mean; every quantitative claim comes from "
        "the replicated experiments."
    ),
)
def scars() -> Figure:
    run_ids, data = _scars()
    cols = 4
    rows = int(np.ceil(len(run_ids) / cols))
    fig = Figure(figsize=(3.2 * cols, 3.5 * rows), layout="constrained")
    axes = np.atleast_1d(fig.subplots(rows, cols)).ravel()
    for ax, rid in zip(axes, run_ids):
        d = data[rid]
        ax.imshow(d["scar"], cmap=SCAR_COLOURS, vmin=0, vmax=4, interpolation="nearest")
        ax.set_title(_scar_title(d["config"]), fontsize=9)
        ax.set_xticks([]); ax.set_yticks([]); ax.grid(False)
    for ax in axes[len(run_ids):]:
        ax.set_visible(False)
    fig.suptitle("One fire under each arrangement (illustrative, single runs)",
                 fontsize=11, color=INK_SECONDARY)
    return fig


@figure(
    "scars-space-time",
    caption=(
        "The same illustrative fires as the scar figure, coloured by the step at which each "
        "cell caught fire, so the picture is a map of travel time from the ignition point "
        "(marked white). Pale grey is fuel that never burned. Colour spreading outward in "
        "even bands is a fire advancing freely; crowded bands are a front held up by a "
        "treated strip or a gap in the fuel. Under wind the bands stretch downwind, which is "
        "the directional kernel acting on the front rather than on the overall spread rate."
    ),
)
def scars_space_time() -> Figure:
    run_ids, data = _scars()
    cols = 4
    rows = int(np.ceil(len(run_ids) / cols))
    vmax = max(int(d["ignition_step"].max()) for d in data.values())
    fig = Figure(figsize=(3.2 * cols, 3.6 * rows), layout="constrained")
    axes = np.atleast_1d(fig.subplots(rows, cols)).ravel()
    image = None
    for ax, rid in zip(axes, run_ids):
        d = data[rid]
        backdrop = np.zeros(d["scar"].shape + (3,))
        backdrop[d["scar"] == EMPTY] = mpl.colors.to_rgb("#efe9dc")
        backdrop[d["scar"] != EMPTY] = mpl.colors.to_rgb("#c9c6bb")
        backdrop[d["scar"] == SETTLEMENT] = mpl.colors.to_rgb("#2f6fd1")
        ax.imshow(backdrop, interpolation="nearest")
        image = ax.imshow(np.ma.masked_less(d["ignition_step"], 0), cmap="inferno_r",
                          vmin=0, vmax=vmax, interpolation="nearest")
        ys, xs = np.nonzero(d["ignition_step"] == 0)
        if ys.size:
            ax.plot(xs.mean(), ys.mean(), "o", ms=6, mfc="white", mec="black", mew=1.1)
        ax.set_title(_scar_title(d["config"]), fontsize=9)
        ax.set_xticks([]); ax.set_yticks([]); ax.grid(False)
    for ax in axes[len(run_ids):]:
        ax.set_visible(False)
    fig.colorbar(image, ax=axes.tolist(), shrink=0.6, label="step at which the cell caught fire")
    fig.suptitle("How each fire travelled (illustrative, single runs)",
                 fontsize=11, color=INK_SECONDARY)
    return fig


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
