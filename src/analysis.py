"""p_c estimation, finite-size scaling, tail fitting (project-context.md §4.6).

SPEC-06 (this file, so far): `estimate_pc`, `pc_rows`, `write_pc_estimates`,
`resolve_p`, `assert_not_truncated`. Tail fitting lands in SPEC-15.

`p_c` is a measured value, never a constant (§6.1). Nothing in this module
supplies a threshold; the only way one gets here is as a row of
`results/pc_estimates.parquet`, and a missing row raises.

Method, in one place:

* **Crossing (`method="fss_crossing"`).** For each lattice size `L`, the
  spanning (edge ignition) or reached-edge (point ignition) indicator is fitted
  as a logistic function of `p` by binomial maximum likelihood. Two lattice
  sizes' fitted curves cross where their logits are equal; the estimate is the
  mean of that crossing over every pair of sizes. Near the threshold the
  curves of different `L` cross at one point and steepen with `L`, which is
  what the finite-size scaling argument rests on.
* **Variance peak (`method="var_peak"`).** For each `L`, the location of the
  maximum of `Var(burned_fraction)` over `p`, taken as the vertex of a
  quadratic through the top of the curve. A single size's peak is offset from
  the infinite-lattice threshold by a finite-size shift (DEC-014), so it is a
  cross-check and not the governing value.
* **Standard errors** are non-parametric bootstrap standard deviations over
  the runs inside each `(L, p)` cell, from a generator seeded by a module
  constant, so the same frame always gives the same answer.
"""

from __future__ import annotations

import math
import os
import warnings
from dataclasses import dataclass
from itertools import combinations
from pathlib import Path

import numpy as np
import pandas as pd

PC_PATH = "results/pc_estimates.parquet"

METHOD_CROSSING = "fss_crossing"
METHOD_VAR_PEAK = "var_peak"
_METHODS = (METHOD_CROSSING, METHOD_VAR_PEAK)
_REGIMES = ("STUDY", "PERCOLATION")

# §4.6 columns, in order, with their dtypes. `L` is nullable: the crossing row
# belongs to every size at once, so it has none (DEC-004).
PC_COLUMNS = ["regime", "condition", "b", "kappa", "L", "p_c", "p_c_stderr", "method"]
_PC_DTYPES = {
    "regime": "str",
    "condition": "str",
    "b": "float64",
    "kappa": "float64",
    "L": "Int32",
    "p_c": "float64",
    "p_c_stderr": "float64",
    "method": "str",
}

# Constants, read at call time and never mutated (§8: no global mutable state).
_N_BOOT = 400                 # bootstrap replicates per standard error
_BOOT_SEED = 4403             # every bootstrap builds its own generator from this
_MIN_BOOT_VALID = 0.9         # fraction of replicates that must give an estimate
_PEAK_WINDOW = 0.5            # quadratic uses cells with Var >= this * peak Var
_MIN_P_POINTS = 3             # distinct p per L needed to fit a curve

# Everything below must be single-valued within one (regime, condition) frame,
# otherwise the frame mixes systems that have different thresholds. `b` and
# `kappa` are the pc_estimates key; the rest are other rule/geometry settings.
_SINGLE_VALUED = (
    "b", "kappa", "geometry_params", "beta", "f_treat", "phi", "tau",
    "diagonal_factor", "ignition", "settlement",
)


# --- the I10 assertion ------------------------------------------------------


def assert_not_truncated(df: pd.DataFrame) -> None:
    """Raise AssertionError if any row of `df` is truncated (§3.7, §7 I10).

    The fix for a truncated run is to raise `max_steps` and rerun, never to
    filter the row out, so this does not offer a way to drop rows. A missing
    value in `truncated` is treated as a failure: it cannot be shown to be False.
    """
    if "truncated" not in df.columns:
        raise AssertionError("frame has no `truncated` column; I10 cannot be checked")
    flag = df["truncated"]
    bad = int(flag.isna().sum() + (flag.dropna().astype(bool)).sum())
    if bad:
        raise AssertionError(
            f"I10: {bad} of {len(df)} rows are truncated (or have no truncated flag). "
            "Raise max_steps and rerun; do not filter these rows out (§3.7)."
        )


# --- reading a frame into cells ---------------------------------------------


@dataclass(frozen=True)
class _Cells:
    """Per-L sweep data: one entry per distinct p, ascending."""

    L: int
    p: np.ndarray            # (m,) float64
    n: np.ndarray            # (m,) runs per cell
    k: np.ndarray            # (m,) successes (indicator true)
    burned: list             # m arrays of burned_fraction


@dataclass(frozen=True)
class _Sweep:
    regime: str
    condition: str
    b: float
    kappa: float
    indicator: str
    cells: dict              # L -> _Cells, ascending L


def _prepare(df: pd.DataFrame, condition: str, regime: str) -> _Sweep:
    """Check a frame and reduce it to per-(L, p) cells for one key."""
    if not isinstance(df, pd.DataFrame):
        raise TypeError(f"df must be a DataFrame, got {type(df).__name__}")
    # I10 first, over the whole frame, before anything else is looked at.
    assert_not_truncated(df)

    needed = ["regime", "condition", "L", "p", "b", "kappa", "burned_fraction",
              "spanned", "reached_edge"]
    missing = [c for c in needed if c not in df.columns]
    if missing:
        raise ValueError(f"frame is missing §5 columns {missing}")

    sub = df[(df["regime"] == regime) & (df["condition"] == condition)]
    if sub.empty:
        raise ValueError(f"no rows with regime={regime!r}, condition={condition!r}")

    for col in _SINGLE_VALUED:
        if col in sub.columns and sub[col].nunique(dropna=False) != 1:
            raise ValueError(
                f"rows for regime={regime!r}, condition={condition!r} hold more than one "
                f"{col!r} ({sorted(map(str, sub[col].unique()))}); estimate one "
                "(regime, condition, b, kappa) at a time"
            )

    # §3.5: `spanned` is set only under edge ignition and `reached_edge` only
    # under point ignition, the other being null.
    has_span = sub["spanned"].notna().all()
    has_edge = sub["reached_edge"].notna().all()
    if has_span == has_edge:
        raise ValueError(
            "exactly one of `spanned` / `reached_edge` must be non-null on every row "
            "(edge vs point ignition, §3.5)"
        )
    indicator = "spanned" if has_span else "reached_edge"

    work = pd.DataFrame({
        "L": sub["L"].astype(int).to_numpy(),
        "p": sub["p"].astype(float).round(12).to_numpy(),
        "hit": sub[indicator].astype(bool).to_numpy(),
        "burned": sub["burned_fraction"].astype(float).to_numpy(),
    })
    cells = {}
    for L, g in work.groupby("L", sort=True):
        ps, ns, ks, bs = [], [], [], []
        for p, c in g.groupby("p", sort=True):
            ps.append(p)
            ns.append(len(c))
            ks.append(int(c["hit"].sum()))
            bs.append(c["burned"].to_numpy())
        if len(ps) < _MIN_P_POINTS:
            raise ValueError(
                f"L={L} has {len(ps)} distinct p values; need at least {_MIN_P_POINTS}"
            )
        cells[int(L)] = _Cells(int(L), np.array(ps), np.array(ns, float),
                               np.array(ks, float), bs)

    return _Sweep(regime, condition, float(sub["b"].iloc[0]) + 0.0,
                  float(sub["kappa"].iloc[0]) + 0.0, indicator, cells)


# --- crossing ---------------------------------------------------------------


def _fit_logistic(z: np.ndarray, k: np.ndarray, n: np.ndarray) -> np.ndarray:
    """Binomial-logit maximum likelihood, `logit P = a + c*z`, batched.

    `k` is (B, m) successes out of `n` (m,) trials at `z` (m,). Returns (B, 2)
    as [a, c], NaN for a batch member that did not converge. Half a success
    and half a failure are added to every cell (Firth-style), which keeps the
    estimate finite when a cell is all-hit or all-miss.
    """
    k = k + 0.5
    n = n + 1.0
    X = np.stack([np.ones_like(z), z], axis=1)                 # (m, 2)
    beta = np.zeros((k.shape[0], 2))
    step = np.full(k.shape[0], np.inf)
    for _ in range(100):
        eta = np.clip(beta @ X.T, -30.0, 30.0)                 # (B, m)
        mu = 1.0 / (1.0 + np.exp(-eta))
        w = n * mu * (1.0 - mu)
        score = (k - n * mu) @ X                               # (B, 2)
        hess = np.einsum("bm,mi,mj->bij", w, X, X)
        delta = np.linalg.solve(hess, score[..., None])[..., 0]
        delta = np.clip(delta, -4.0, 4.0)
        beta = beta + delta
        step = np.abs(delta).max(axis=1)
        if step.max() < 1e-10:
            break
    beta[step > 1e-6] = np.nan
    return beta


def _crossing_estimates(sweep: _Sweep, k_by_L: dict, x0: float, s: float) -> np.ndarray:
    """Mean pairwise crossing of the fitted curves, for each batch member.

    `k_by_L[L]` is (B, m_L). Entries are NaN where any pair has no valid
    crossing: a non-increasing fit, parallel curves, or a crossing outside the
    p range both sizes were swept over (never extrapolated).
    """
    fits = {}
    for L, c in sweep.cells.items():
        fits[L] = _fit_logistic((c.p - x0) / s, k_by_L[L], c.n)

    pair_z = []
    for La, Lb in combinations(sorted(sweep.cells), 2):
        (aa, ca), (ab, cb) = fits[La].T, fits[Lb].T
        pa, pb = sweep.cells[La].p, sweep.cells[Lb].p
        lo = (max(pa.min(), pb.min()) - x0) / s
        hi = (min(pa.max(), pb.max()) - x0) / s
        with np.errstate(divide="ignore", invalid="ignore"):
            z = (ab - aa) / (ca - cb)
        ok = (ca > 0) & (cb > 0) & (np.abs(ca - cb) > 1e-9) & (z >= lo) & (z <= hi)
        pair_z.append(np.where(ok, z, np.nan))
    return x0 + s * np.mean(pair_z, axis=0)


def _crossing(sweep: _Sweep, rng: np.random.Generator) -> tuple[float, float]:
    Ls = sorted(sweep.cells)
    if len(Ls) < 2:
        raise ValueError(
            f"the crossing needs at least two lattice sizes; frame has L={Ls}"
        )
    if len(Ls) == 2:
        warnings.warn(
            f"only two lattice sizes ({Ls}); the crossing is a single intersection and its "
            "standard error is unreliable. Three or more are needed for it to be meaningful.",
            UserWarning, stacklevel=3,
        )

    all_p = np.concatenate([c.p for c in sweep.cells.values()])
    x0 = float(all_p.mean())
    s = float((all_p.max() - all_p.min()) / 2.0)
    if s <= 0:
        raise ValueError("every p is identical; nothing to cross")

    point = _crossing_estimates(
        sweep, {L: sweep.cells[L].k[None, :] for L in Ls}, x0, s
    )[0]
    if not np.isfinite(point):
        raise ValueError(
            f"no valid crossing of the P({sweep.indicator}) curves across L={Ls} inside the "
            "swept p range (curves not increasing with p, parallel, or crossing outside the "
            "sweep). Widen or recentre the sweep; no value is extrapolated."
        )

    boot_k = {
        L: rng.binomial(c.n.astype(int), c.k / c.n, size=(_N_BOOT, c.p.size)).astype(float)
        for L, c in sweep.cells.items()
    }
    boot = _crossing_estimates(sweep, boot_k, x0, s)
    boot = boot[np.isfinite(boot)]
    if boot.size < _MIN_BOOT_VALID * _N_BOOT:
        raise ValueError(
            f"the crossing is not stable under resampling ({boot.size}/{_N_BOOT} replicates "
            "gave one); the sweep does not pin the threshold down"
        )
    return float(point), float(boot.std(ddof=1))


# --- variance peak ----------------------------------------------------------


def _peak_location(x: np.ndarray, v: np.ndarray) -> float:
    """Vertex of a quadratic through the top of `v(x)`; NaN if the peak is an end point.

    The quadratic uses the contiguous run of cells around the maximum whose
    value is at least `_PEAK_WINDOW` of it (at least the maximum and its
    neighbours), which is less jumpy than an argmax on a noisy curve.
    """
    i = int(np.argmax(v))
    if i == 0 or i == len(v) - 1:
        return float("nan")
    lo = hi = i
    thr = _PEAK_WINDOW * v[i]
    while lo > 0 and v[lo - 1] >= thr:
        lo -= 1
    while hi < len(v) - 1 and v[hi + 1] >= thr:
        hi += 1
    lo, hi = min(lo, i - 1), max(hi, i + 1)
    xs = x[lo:hi + 1] - x[i]
    a, b, _ = np.polyfit(xs, v[lo:hi + 1], 2)
    if a >= 0:
        return float(x[i])
    vertex = -b / (2.0 * a)
    return float(x[i] + min(max(vertex, xs[0]), xs[-1]))


def _var_peak(cells: _Cells, rng: np.random.Generator) -> tuple[float, float]:
    if np.any(cells.n < 2):
        raise ValueError(f"L={cells.L}: a cell has fewer than two runs; variance undefined")
    v = np.array([b.var(ddof=1) for b in cells.burned])
    peak = _peak_location(cells.p, v)
    if not np.isfinite(peak):
        raise ValueError(
            f"L={cells.L}: Var(burned_fraction) peaks at an end of the sweep "
            f"(p={cells.p[int(np.argmax(v))]}); the sweep does not bracket the peak"
        )
    boot_v = np.empty((_N_BOOT, cells.p.size))
    for j, b in enumerate(cells.burned):
        idx = rng.integers(0, b.size, size=(_N_BOOT, b.size))
        boot_v[:, j] = b[idx].var(axis=1, ddof=1)
    boot = np.array([_peak_location(cells.p, row) for row in boot_v])
    boot = boot[np.isfinite(boot)]
    if boot.size < _MIN_BOOT_VALID * _N_BOOT:
        raise ValueError(
            f"L={cells.L}: the variance peak is not stable under resampling "
            f"({boot.size}/{_N_BOOT} replicates)"
        )
    return peak, float(boot.std(ddof=1))


# --- public estimation API --------------------------------------------------


def estimate_pc(df, condition: str, regime: str) -> tuple[float, float]:
    """`(p_c, stderr)` from the crossing of P(span) or P(reached_edge) across `L`.

    `df` is a §5 results frame. Rows of `(regime, condition)` are used and must
    all share one `b`, `kappa` and geometry, i.e. one `pc_estimates` key.
    `truncated == False` is asserted over the whole frame first (I10).

    This is the governing `fss_crossing` value. The variance-peak cross-check
    is produced by `pc_rows`.
    """
    sweep = _prepare(df, condition, regime)
    return _crossing(sweep, np.random.default_rng(_BOOT_SEED))


def pc_rows(df, condition: str, regime: str) -> list[dict]:
    """The `pc_estimates` rows for one measured key: one `var_peak` row per `L`
    and exactly one `fss_crossing` row with `L` null (DEC-004).

    The crossing row carries the same `(p_c, stderr)` as `estimate_pc`. Hand the
    result to `write_pc_estimates`.
    """
    sweep = _prepare(df, condition, regime)
    p_c, se = _crossing(sweep, np.random.default_rng(_BOOT_SEED))
    key = {"regime": regime, "condition": condition, "b": sweep.b, "kappa": sweep.kappa}

    rows = []
    for L, cells in sweep.cells.items():
        peak, peak_se = _var_peak(cells, np.random.default_rng([_BOOT_SEED, L]))
        rows.append({**key, "L": L, "p_c": peak, "p_c_stderr": peak_se,
                     "method": METHOD_VAR_PEAK})
    rows.append({**key, "L": None, "p_c": p_c, "p_c_stderr": se, "method": METHOD_CROSSING})
    return rows


# --- pc_estimates.parquet ---------------------------------------------------


def _coerce_pc(df: pd.DataFrame, where: str) -> pd.DataFrame:
    if set(df.columns) != set(PC_COLUMNS):
        raise ValueError(
            f"{where} must have exactly the columns {PC_COLUMNS}; got {list(df.columns)}"
        )
    return df[PC_COLUMNS].astype(_PC_DTYPES).reset_index(drop=True)


def _validate_pc(df: pd.DataFrame) -> None:
    if df.empty:
        raise ValueError("no rows to write")
    bad = ~df["regime"].isin(_REGIMES)
    if bad.any():
        raise ValueError(f"regime must be one of {_REGIMES}; got {sorted(df['regime'][bad])}")
    bad = ~df["method"].isin(_METHODS)
    if bad.any():
        raise ValueError(f"method must be one of {_METHODS}; got {sorted(df['method'][bad])}")
    crossing = df["method"] == METHOD_CROSSING
    if (crossing & df["L"].notna()).any():
        raise ValueError(f"a {METHOD_CROSSING!r} row must have L null (DEC-004)")
    if (~crossing & df["L"].isna()).any():
        raise ValueError(f"a {METHOD_VAR_PEAK!r} row must have L set (DEC-004)")
    for col in ("b", "kappa", "p_c", "p_c_stderr"):
        if not np.isfinite(df[col].to_numpy(float)).all():
            raise ValueError(f"column {col!r} has a non-finite value")
    if not ((df["p_c"] > 0) & (df["p_c"] < 1)).all():
        raise ValueError("p_c must lie strictly between 0 and 1")
    if (df["p_c_stderr"] < 0).any():
        raise ValueError("p_c_stderr must be non-negative")


def _keys(df: pd.DataFrame) -> list[tuple]:
    L = df["L"].astype(object).where(df["L"].notna(), None)
    return list(zip(df["regime"], df["condition"], df["b"] + 0.0, df["kappa"] + 0.0,
                    df["method"], L))


def _read_pc(path: Path) -> pd.DataFrame:
    return _coerce_pc(pd.read_parquet(path), str(path))


def write_pc_estimates(rows, path: str = PC_PATH) -> None:
    """Append `rows` (dicts, or a DataFrame) with the §4.6 columns to `path`.

    Rows already in the file are carried over unchanged and the file is replaced
    atomically, so an existing committed parquet is never edited in place
    (workflow-rules.md §9). `(regime, condition, b, kappa, method, L)` must be
    unique across the existing rows and the new ones; a duplicate raises and
    nothing is written.
    """
    new = rows.copy() if isinstance(rows, pd.DataFrame) else pd.DataFrame(list(rows))
    new = _coerce_pc(new, "rows")
    _validate_pc(new)

    path = Path(path)
    old = _read_pc(path) if path.exists() else None

    seen = set(_keys(old)) if old is not None else set()
    for key in _keys(new):
        if key in seen:
            raise ValueError(
                f"duplicate pc_estimates row for (regime, condition, b, kappa, method, L) = "
                f"{key}; nothing written"
            )
        seen.add(key)

    out = new if old is None else pd.concat([old, new], ignore_index=True)
    out = out.astype(_PC_DTYPES)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    out.to_parquet(tmp, index=False)
    os.replace(tmp, path)


def resolve_p(p_rel: float, *, regime: str, condition: str, b: float, kappa: float,
              path: str = PC_PATH) -> float:
    """Absolute p for an offset from the governing threshold.

    Selects the single `method == "fss_crossing"` row (L null) matching
    `(regime, condition, b, kappa)`, with `b` and `kappa` compared exactly, and
    returns `p_c + p_rel`. Raises if the file is missing (FileNotFoundError),
    if no row matches or more than one does (LookupError), or if the result is
    not a probability (ValueError). Never falls back to a default or to a
    different regime or condition (§6.1, §2 O4).
    """
    if not math.isfinite(p_rel):
        raise ValueError(f"p_rel must be finite, got {p_rel!r}")
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(
            f"{path} does not exist, so p_rel cannot be resolved. Run the experiment that "
            "measures this threshold first; there is no fallback value (§6.1)."
        )
    df = _read_pc(path)

    crossing = df[(df["method"] == METHOD_CROSSING) & df["L"].isna()]
    hit = crossing[
        (crossing["regime"] == regime)
        & (crossing["condition"] == condition)
        & (crossing["b"] == float(b))
        & (crossing["kappa"] == float(kappa))
    ]
    wanted = f"(regime={regime!r}, condition={condition!r}, b={b!r}, kappa={kappa!r})"
    if len(hit) == 0:
        have = crossing[(crossing["regime"] == regime) & (crossing["condition"] == condition)]
        listing = sorted(zip(have["b"], have["kappa"]))
        raise LookupError(
            f"no {METHOD_CROSSING!r} row in {path} for {wanted}. "
            f"Measured (b, kappa) for this regime and condition: {listing or 'none'}."
        )
    if len(hit) > 1:
        raise LookupError(
            f"{len(hit)} {METHOD_CROSSING!r} rows in {path} match {wanted}; the key must be unique"
        )

    p = float(hit["p_c"].iloc[0]) + float(p_rel)
    if not 0.0 <= p <= 1.0:
        raise ValueError(f"p_c + p_rel = {p} is not a probability, for {wanted}")
    return p
