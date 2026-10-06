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


# ===========================================================================
# Burn-size tail fitting (SPEC-15, §10.2 O4)
# ===========================================================================
#
# Model. A fire's size x (burned cells) is a positive integer that cannot
# exceed the lattice, so the tail is fitted as a *discrete* distribution on the
# finite support {x_min, ..., x_max}:
#
#     power law (PL):            p(x) ∝ x^(-alpha)
#     with cutoff (TPL):         p(x) ∝ x^(-alpha) · exp(-x / cutoff)
#
# Because the support is finite, the normalising constant is an ordinary finite
# sum and the maximum-likelihood fit is exact in numpy, with no zeta function
# and nothing outside numpy (DEC-038). Both models are exponential families in the
# sufficient statistics (ln x, x), so the log-likelihood is concave and Newton's
# method converges from any start.
#
# Procedure (Clauset, Shalizi & Newman 2009, with the cutoff model in the
# selection step, DEC-038):
#   1. for each candidate x_min, fit TPL by maximum likelihood (cutoff >= 0
#      enforced through lambda = 1/cutoff >= 0);
#   2. keep the x_min whose fitted model is closest to the data in KS distance;
#   3. at that x_min, report alpha and the cutoff together, plus the pure-PL fit
#      and a likelihood-ratio test of "cutoff" against "no cutoff".

TAIL_FITS_PATH = "results/tail_fits.parquet"
TAIL_MIN_N = 50              # fewest tail points a candidate x_min may leave
TAIL_MAX_CANDIDATES = 200    # x_min candidates tried (log-spaced if more exist)
G2_MIN_DECADES = 2.0         # §10.2 O4 gate: decades of tail above x_min
_NEWTON_TOL = 1e-10
_NEWTON_MAX_ITER = 100

TAIL_FIT_FIELDS = [
    "x_min", "x_max", "n", "n_tail", "max_size", "decades_above_xmin",
    "alpha", "alpha_stderr", "cutoff", "cutoff_lo", "cutoff_hi",
    "cutoff_rate", "cutoff_rate_stderr",
    "alpha_pl", "alpha_pl_stderr", "cutoff_llr", "cutoff_p_value",
    "ks_distance", "ks_critical", "fit_rejected",
]
TAIL_KEY = ["experiment", "condition", "geometry_params", "b", "replicates"]
TAIL_COLUMNS = TAIL_KEY + ["p", "kappa", "L"] + TAIL_FIT_FIELDS


@dataclass(frozen=True)
class _Support:
    """The finite support {x_min .. x_max} and its sufficient statistics."""
    x: np.ndarray       # float64 values
    logx: np.ndarray


def _support(x_min: int, x_max: int) -> _Support:
    x = np.arange(x_min, x_max + 1, dtype=np.float64)
    return _Support(x, np.log(x))


def _moments(sup: _Support, alpha: float, lam: float) -> tuple[float, np.ndarray, np.ndarray, np.ndarray]:
    """log Z, mean of (ln x, x), covariance of (ln x, x), and the pmf, under
    p(x) ∝ exp(-alpha ln x - lam x) on the support. Shifted by the max exponent
    so nothing overflows."""
    e = -alpha * sup.logx - lam * sup.x
    m = float(e.max())
    w = np.exp(e - m)
    z = float(w.sum())
    pmf = w / z
    stats = np.stack([sup.logx, sup.x])                 # (2, K)
    mean = stats @ pmf
    centred = stats - mean[:, None]
    cov = (centred * pmf) @ centred.T
    return m + math.log(z), mean, cov, pmf


def _loglik(sup, alpha, lam, n, s_log, s_x) -> float:
    log_z = _moments(sup, alpha, lam)[0]
    return -alpha * s_log - lam * s_x - n * log_z


def _fit_pl(sup: _Support, n: int, s_log: float) -> tuple[float, float, float]:
    """Pure power law: (alpha, stderr, log-likelihood). 1-D Newton, concave."""
    x_min = sup.x[0]
    # continuous-approximation start (CSN eq. 3.7); exact fit refines it
    alpha = 1.0 + n / max(s_log - n * math.log(x_min - 0.5), 1e-12)
    ll = _loglik(sup, alpha, 0.0, n, s_log, 0.0)
    for _ in range(_NEWTON_MAX_ITER):
        _, mean, cov, _ = _moments(sup, alpha, 0.0)
        grad = n * mean[0] - s_log
        hess = -n * cov[0, 0]
        step = -grad / hess
        t = 1.0
        while True:                                     # backtracking: never go downhill
            new = alpha + t * step
            new_ll = _loglik(sup, new, 0.0, n, s_log, 0.0)
            if new_ll >= ll - 1e-12 or t < 1e-8:
                break
            t *= 0.5
        alpha, ll = new, new_ll
        if abs(t * step) < _NEWTON_TOL * max(1.0, abs(alpha)):
            break
    var = _moments(sup, alpha, 0.0)[2][0, 0]
    return alpha, 1.0 / math.sqrt(n * var), ll


def _fit_tpl(sup: _Support, n: int, s_log: float, s_x: float,
             alpha0: float, ll0: float) -> tuple[float, float, np.ndarray, float]:
    """Power law with cutoff: (alpha, lam, covariance of (alpha, lam), log-lik).

    Projected Newton on the concave log-likelihood with lam >= 0. If the
    optimum is on the boundary lam = 0 the model is the pure power law, and the
    covariance returned is the 1-D one with lam's variance set to inf.
    """
    theta = np.array([alpha0, 0.0])
    ll = ll0
    for _ in range(_NEWTON_MAX_ITER):
        _, mean, cov, _ = _moments(sup, theta[0], theta[1])
        grad = np.array([n * mean[0] - s_log, n * mean[1] - s_x])
        if theta[1] == 0.0 and grad[1] <= 0.0:
            # at the boundary and the likelihood wants lam < 0: only alpha moves
            step = np.array([grad[0] / (n * cov[0, 0]), 0.0])
        else:
            try:
                step = np.linalg.solve(n * cov, grad)   # -H^{-1} g, with H = -n cov
            except np.linalg.LinAlgError:
                step = grad / np.maximum(n * np.diag(cov), 1e-300)
        t = 1.0
        while True:
            new = theta + t * step
            new[1] = max(new[1], 0.0)                   # project onto lam >= 0
            new_ll = _loglik(sup, new[0], new[1], n, s_log, s_x)
            if new_ll >= ll - 1e-12 or t < 1e-8:
                break
            t *= 0.5
        moved = new - theta
        theta, ll = new, new_ll
        if abs(moved[0]) < _NEWTON_TOL * max(1.0, abs(theta[0])) and abs(moved[1]) <= _NEWTON_TOL * max(theta[1], 1e-12):
            break

    _, _, cov, _ = _moments(sup, theta[0], theta[1])
    if theta[1] == 0.0:
        out = np.array([[1.0 / (n * cov[0, 0]), 0.0], [0.0, math.inf]])
    else:
        out = np.linalg.inv(n * cov)
    return float(theta[0]), float(theta[1]), out, ll


def _ks(tail_sorted: np.ndarray, pmf: np.ndarray, x_min: int) -> float:
    """KS distance between the tail's empirical CDF and the model CDF, at the
    distinct observed values (both CDFs are step functions on the integers)."""
    cdf = np.cumsum(pmf)
    vals, counts = np.unique(tail_sorted, return_counts=True)
    emp = np.cumsum(counts) / tail_sorted.size
    model = cdf[(vals - x_min).astype(np.int64)]
    return float(np.max(np.abs(emp - model)))


def _candidates(sizes_sorted: np.ndarray) -> np.ndarray:
    """Distinct values a tail may start at, thinned to at most
    TAIL_MAX_CANDIDATES, log-spaced, keeping the smallest.

    A candidate must leave at least TAIL_MIN_N points at or above it **and** at
    least `G2_MIN_DECADES` of range below the largest observed size. The range
    floor is what stops the selection degenerating (DEC-043): the KS distance of
    a fitted model falls with the number of points it is fitted to, so without
    it the search always drifts to a sliver at the very top of the distribution,
    where any shape fits well and the fitted "tail" describes a finite-size peak
    rather than a tail. The floor is the same two decades §10.2 O4's gate asks
    for, so a fit that is reported at all spans a range worth reporting.
    """
    vals = np.unique(sizes_sorted)
    n_at_or_above = sizes_sorted.size - np.searchsorted(sizes_sorted, vals, side="left")
    enough_points = n_at_or_above >= TAIL_MIN_N
    enough_range = vals <= sizes_sorted[-1] / 10.0 ** G2_MIN_DECADES
    vals = vals[enough_points & enough_range]
    if vals.size == 0:                      # a distribution too narrow for any tail
        vals = np.unique(sizes_sorted)[:1]
    if vals.size > TAIL_MAX_CANDIDATES:
        idx = np.unique(np.round(np.geomspace(1, vals.size, TAIL_MAX_CANDIDATES)).astype(int) - 1)
        vals = vals[idx]
    return vals


def _fit_at(sizes_sorted: np.ndarray, x_min: int, x_max: int) -> dict:
    tail = sizes_sorted[np.searchsorted(sizes_sorted, x_min, side="left"):]
    n = int(tail.size)
    sup = _support(x_min, x_max)
    s_log = float(np.log(tail).sum())
    s_x = float(tail.sum())
    alpha_pl, alpha_pl_se, ll_pl = _fit_pl(sup, n, s_log)
    alpha, lam, cov, ll = _fit_tpl(sup, n, s_log, s_x, alpha_pl, ll_pl)
    pmf = _moments(sup, alpha, lam)[3]
    _ks_value = _ks(tail, pmf, x_min)
    llr = max(2.0 * (ll - ll_pl), 0.0)
    # The cutoff is reported as 1/lam with a 1-sigma interval from inverting
    # lam ± se(lam). se(lam) is well calibrated; a delta-method se on 1/lam is
    # not, because 1/lam is strongly skewed whenever lam is poorly determined
    # (DEC-038). The upper end is inf when lam - se <= 0: the data cannot rule
    # out "no cutoff" at 1 sigma.
    lam_se = math.sqrt(cov[1, 1])
    cutoff = 1.0 / lam if lam > 0.0 else math.inf
    cutoff_lo = 1.0 / (lam + lam_se) if math.isfinite(lam_se) else 0.0
    cutoff_hi = 1.0 / (lam - lam_se) if lam - lam_se > 0.0 else math.inf
    return {
        "x_min": int(x_min), "x_max": int(x_max), "n_tail": n,
        "max_size": int(tail[-1]),
        "decades_above_xmin": float(math.log10(tail[-1] / x_min)),
        "alpha": float(alpha), "alpha_stderr": float(math.sqrt(cov[0, 0])),
        "cutoff": float(cutoff), "cutoff_lo": float(cutoff_lo), "cutoff_hi": float(cutoff_hi),
        "cutoff_rate": float(lam), "cutoff_rate_stderr": float(lam_se),
        "alpha_pl": float(alpha_pl), "alpha_pl_stderr": float(alpha_pl_se),
        "ks_critical": 1.36 / math.sqrt(n),     # KS 5% critical value at this n
        "fit_rejected": float(_ks_value > 1.36 / math.sqrt(n)),
        "cutoff_llr": float(llr),
        # lam = 0 is on the boundary of the parameter space, so the null
        # distribution of the LR statistic is ½χ²₀ + ½χ²₁ (Self & Liang 1987)
        "cutoff_p_value": 0.5 * math.erfc(math.sqrt(llr / 2.0)) if llr > 0 else 1.0,
        "ks_distance": _ks_value,
    }


def fit_tail(sizes: np.ndarray, *, x_max: int | None = None, x_min: int | None = None) -> dict:
    """Fit the upper tail of a burn-size sample (SPEC-15 interface contract).

    `sizes` are burned-cell counts, one per run. Non-positive sizes (a run with
    no fuel at all) are dropped. `x_max` is the largest size the system can
    produce — the lattice, `L*L`, for a burn size — and bounds the support of
    both models (DEC-038). If omitted it defaults to 100 × the largest observed
    size, a stand-in for "unbounded" whose effect on the fit is negligible for
    alpha > 1. `x_min` fixes the start of the tail; by default it is chosen by
    KS distance over the candidates.

    Returns a dict with the TAIL_FIT_FIELDS: `alpha` and `cutoff` are the
    reported fit (power law with exponential cutoff; `cutoff = inf` when the
    data give no evidence of one), `cutoff_lo`/`cutoff_hi` its 1-sigma
    interval, `cutoff_rate` = 1/cutoff with its stderr, `alpha_pl` the pure
    power law at the same
    `x_min`, `cutoff_p_value` the likelihood-ratio test of cutoff against none,
    and `decades_above_xmin = log10(max_size / x_min)` for the §10.2 O4 gate.
    """
    s = np.asarray(sizes)
    if s.ndim != 1:
        raise ValueError(f"sizes must be 1-D, got shape {s.shape}")
    if not np.issubdtype(s.dtype, np.number) or not np.all(np.isfinite(s)):
        raise ValueError("sizes must be finite numbers")
    if np.any(s != np.round(s)):
        raise ValueError("sizes must be integer counts (burned cells)")
    s = np.sort(s[s > 0].astype(np.int64))
    if s.size < TAIL_MIN_N:
        raise ValueError(f"need at least {TAIL_MIN_N} positive sizes to fit a tail, got {s.size}")
    if x_max is None:
        x_max = int(100 * s[-1])
    if x_max < s[-1]:
        raise ValueError(f"x_max={x_max} is below the largest observed size {int(s[-1])}")

    if x_min is not None:
        if x_min < 1 or (s >= x_min).sum() < TAIL_MIN_N:
            raise ValueError(f"x_min={x_min} leaves fewer than {TAIL_MIN_N} tail points")
        best = _fit_at(s, int(x_min), int(x_max))
    else:
        best = None
        for cand in _candidates(s):
            fit = _fit_at(s, int(cand), int(x_max))
            if best is None or fit["ks_distance"] < best["ks_distance"]:
                best = fit
    best["n"] = int(s.size)
    return {k: best[k] for k in TAIL_FIT_FIELDS}


def g2_gate(fits: pd.DataFrame) -> pd.DataFrame:
    """§10.2 O4 gate G2: which conditions keep at least G2_MIN_DECADES of tail
    above x_min. Returns condition, decades_above_xmin and a `passes` column.
    Raising R to 50,000 is a decision for the team, recorded in §10.2 O4; this
    only reports the evidence."""
    out = fits[["condition", "geometry_params", "replicates", "x_min", "max_size",
                "decades_above_xmin"]].copy()
    out["passes"] = out["decades_above_xmin"] >= G2_MIN_DECADES
    return out


_TAIL_DTYPES = {
    "experiment": "string", "condition": "string", "geometry_params": "string",
    "b": "float64", "replicates": "int64", "p": "float64", "kappa": "float64", "L": "int64",
    "x_min": "int64", "x_max": "int64", "n": "int64", "n_tail": "int64", "max_size": "int64",
}


def write_tail_fits(rows, path: str = TAIL_FITS_PATH) -> None:
    """Append fit rows (dicts or a DataFrame with TAIL_COLUMNS) to `path`.

    Append-only like `write_pc_estimates` (workflow-rules.md §9): existing rows
    are carried over unchanged, the file is replaced atomically, and a row whose
    (experiment, condition, geometry_params, b, replicates) is already recorded
    raises with nothing written. A rerun at R = 50,000 after the G2 gate is a
    new key, so both fits stay in the record.
    """
    new = rows.copy() if isinstance(rows, pd.DataFrame) else pd.DataFrame(list(rows))
    missing = [c for c in TAIL_COLUMNS if c not in new.columns]
    if missing:
        raise ValueError(f"tail-fit rows are missing columns {missing}")
    new = new[TAIL_COLUMNS]
    for col, dtype in _TAIL_DTYPES.items():
        new[col] = new[col].astype(dtype)
    for col in TAIL_COLUMNS:
        if col not in _TAIL_DTYPES:
            new[col] = new[col].astype("float64")

    path = Path(path)
    old = pd.read_parquet(path) if path.exists() else None
    key = lambda df: list(df[TAIL_KEY].itertuples(index=False, name=None))
    seen = set(key(old)) if old is not None else set()
    for k in key(new):
        if k in seen:
            raise ValueError(f"duplicate tail-fit row for {dict(zip(TAIL_KEY, k))}; nothing written")
        seen.add(k)

    out = new if old is None else pd.concat([old, new], ignore_index=True)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    out.to_parquet(tmp, index=False)
    os.replace(tmp, path)
