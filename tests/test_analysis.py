"""SPEC-06: p_c estimation, finite-size scaling, the p_rel resolver, I10.

Everything is checked against synthetic sweeps whose threshold is known, so a
quietly biased estimator shows up here and not as a plausible-looking number in
a result.
"""

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from src.analysis import (
    PC_COLUMNS,
    assert_not_truncated,
    estimate_pc,
    pc_rows,
    resolve_p,
    write_pc_estimates,
)

P0 = 0.45
LS = (128, 256, 512)


def make_sweep(p0=P0, Ls=LS, *, n=500, width0=0.02, regime="STUDY", condition="none",
               b=0.0, kappa=0.0, geometry="{}", half_range=0.05, step=0.005,
               rng=None, indicator="spanned"):
    """A §5-shaped frame with logistic P(indicator) centred at `p0`.

    The curve steepens with L, like a real finite-size sweep (width ~ L^-3/4),
    but every size is centred on `p0`, so the crossing is exactly `p0`. The
    burned fraction is bimodal (big when the indicator fires, small when it
    does not), so Var(burned_fraction) peaks where P = 1/2, i.e. also at `p0`.
    With `rng=None` the outcome counts are the expectation rounded, i.e. no
    sampling noise, which isolates bias from noise.
    """
    ps = np.round(np.arange(p0 - half_range, p0 + half_range + 1e-9, step), 6)
    jitter = np.linspace(-1.0, 1.0, n)
    rows = []
    for L in Ls:
        w = width0 * (128 / L) ** 0.75
        for p in ps:
            prob = 1.0 / (1.0 + np.exp(-(p - p0) / w))
            k = int(round(prob * n)) if rng is None else int(rng.binomial(n, prob))
            hit = np.arange(n) < k
            burned = np.where(hit, 0.6, 0.05) + 0.01 * jitter
            rows.append(pd.DataFrame({
                "regime": regime, "condition": condition, "L": L, "p": p,
                "b": b, "kappa": kappa, "geometry_params": geometry,
                "spanned": pd.array(hit if indicator == "spanned" else [None] * n,
                                    dtype="boolean"),
                "reached_edge": pd.array(hit if indicator == "reached_edge" else [None] * n,
                                         dtype="boolean"),
                "burned_fraction": burned,
                "truncated": False,
            }))
    return pd.concat(rows, ignore_index=True)


def key_row(regime, condition, b, kappa, p_c, *, L=None, method="fss_crossing", se=0.002):
    return {"regime": regime, "condition": condition, "b": b, "kappa": kappa, "L": L,
            "p_c": p_c, "p_c_stderr": se, "method": method}


# --- estimate_pc ------------------------------------------------------------


def test_recovers_known_threshold_within_stderr():
    p_c, se = estimate_pc(make_sweep(), "none", "STUDY")
    assert 0.0 < se < 0.01
    assert abs(p_c - P0) <= se


@pytest.mark.parametrize("p0", [0.35, 0.40, 0.55])
def test_threshold_recovered_at_other_centres(p0):
    p_c, se = estimate_pc(make_sweep(p0=p0), "none", "STUDY")
    assert abs(p_c - p0) <= se


def test_point_ignition_indicator_is_used():
    p_c, se = estimate_pc(make_sweep(indicator="reached_edge"), "none", "STUDY")
    assert abs(p_c - P0) <= se


def test_stderr_is_calibrated_on_sampled_sweeps():
    """Sampled counts, not rounded expectations: the returned stderr must be a
    fair measure of the real scatter, not just non-zero."""
    errs, ses = [], []
    for seed in range(24):
        p_c, se = estimate_pc(make_sweep(rng=np.random.default_rng(seed)), "none", "STUDY")
        errs.append(p_c - P0)
        ses.append(se)
    errs, ses = np.array(errs), np.array(ses)
    assert np.all(np.abs(errs) < 4 * ses)                 # nothing wildly off
    assert np.mean(np.abs(errs) <= 2 * ses) >= 0.85       # ~95% expected
    assert abs(errs.mean()) < 2 * errs.std(ddof=1) / np.sqrt(len(errs))   # unbiased
    # the claimed error is the observed scatter to within a factor of 2
    assert 0.5 < ses.mean() / errs.std(ddof=1) < 2.0


def test_estimate_is_deterministic():
    df = make_sweep(rng=np.random.default_rng(0))
    assert estimate_pc(df, "none", "STUDY") == estimate_pc(df, "none", "STUDY")


def test_selects_the_requested_regime_and_condition():
    a = make_sweep(p0=0.45, regime="STUDY", condition="none")
    b = make_sweep(p0=0.40, regime="PERCOLATION", condition="none")
    c = make_sweep(p0=0.48, regime="STUDY", condition="random", b=0.15)
    df = pd.concat([a, b, c], ignore_index=True)
    assert abs(estimate_pc(df, "none", "STUDY")[0] - 0.45) < 0.003
    assert abs(estimate_pc(df, "none", "PERCOLATION")[0] - 0.40) < 0.003
    assert abs(estimate_pc(df, "random", "STUDY")[0] - 0.48) < 0.003


@pytest.mark.parametrize("col, other", [("b", 0.30), ("kappa", 2.0), ("geometry_params", '{"k":4}')])
def test_mixed_keys_in_one_frame_raise(col, other):
    a = make_sweep(condition="random", b=0.15)
    c = make_sweep(condition="random", b=0.15)
    c[col] = other
    with pytest.raises(ValueError, match=col):
        estimate_pc(pd.concat([a, c], ignore_index=True), "random", "STUDY")


def test_crossing_outside_the_sweep_raises_and_does_not_extrapolate():
    # the true crossing is at 0.45 but only p >= 0.47 is swept
    df = make_sweep()
    df = df[df["p"] >= 0.47]
    with pytest.raises(ValueError):
        estimate_pc(df, "none", "STUDY")


def test_one_lattice_size_raises_and_two_warn():
    with pytest.raises(ValueError, match="two lattice sizes"):
        estimate_pc(make_sweep(Ls=(128,)), "none", "STUDY")
    with pytest.warns(UserWarning, match="two lattice sizes"):
        p_c, _ = estimate_pc(make_sweep(Ls=(128, 256)), "none", "STUDY")
    assert abs(p_c - P0) < 0.005


def test_no_rows_for_the_key_raises():
    with pytest.raises(ValueError, match="no rows"):
        estimate_pc(make_sweep(), "random", "STUDY")


def test_frame_must_pick_one_ignition_indicator():
    df = make_sweep()
    df["reached_edge"] = pd.array([True] * len(df), dtype="boolean")
    with pytest.raises(ValueError, match="spanned"):
        estimate_pc(df, "none", "STUDY")


# --- I10 --------------------------------------------------------------------


def test_truncated_row_raises():
    df = make_sweep()
    df.loc[0, "truncated"] = True
    with pytest.raises(AssertionError, match="I10"):
        estimate_pc(df, "none", "STUDY")
    with pytest.raises(AssertionError, match="I10"):
        pc_rows(df, "none", "STUDY")


def test_truncated_row_in_another_condition_still_raises():
    """The assertion is over the whole frame; it is not a filter."""
    df = pd.concat([make_sweep(), make_sweep(condition="random", b=0.15)], ignore_index=True)
    df.loc[df["condition"] == "random", "truncated"] = True
    with pytest.raises(AssertionError, match="I10"):
        estimate_pc(df, "none", "STUDY")


def test_missing_truncated_flag_raises():
    df = make_sweep()
    with pytest.raises(AssertionError):
        assert_not_truncated(df.drop(columns="truncated"))
    df["truncated"] = pd.array([None] * len(df), dtype="boolean")
    with pytest.raises(AssertionError):
        assert_not_truncated(df)


# --- pc_rows and the variance-peak cross-check ------------------------------


def test_var_peak_agrees_with_crossing_on_synthetic_data():
    df = make_sweep()
    p_c, se = estimate_pc(df, "none", "STUDY")
    for r in pc_rows(df, "none", "STUDY"):
        if r["method"] == "var_peak":
            assert abs(r["p_c"] - p_c) < 0.004
            assert abs(r["p_c"] - P0) < 0.004


def test_var_peak_agrees_on_sampled_data():
    df = make_sweep(rng=np.random.default_rng(5))
    for r in pc_rows(df, "none", "STUDY"):
        assert abs(r["p_c"] - P0) <= 3 * r["p_c_stderr"] + 0.002


def test_pc_rows_identity_matches_dec_004():
    rows = pc_rows(make_sweep(), "none", "STUDY")
    per_L = [r for r in rows if r["method"] == "var_peak"]
    crossing = [r for r in rows if r["method"] == "fss_crossing"]
    assert sorted(r["L"] for r in per_L) == list(LS)
    assert len(crossing) == 1 and crossing[0]["L"] is None
    assert (crossing[0]["p_c"], crossing[0]["p_c_stderr"]) == estimate_pc(
        make_sweep(), "none", "STUDY"
    )
    for r in rows:
        assert (r["regime"], r["condition"], r["b"], r["kappa"]) == ("STUDY", "none", 0.0, 0.0)


# --- write_pc_estimates -----------------------------------------------------


def test_write_one_key_over_three_L(tmp_path):
    path = tmp_path / "pc.parquet"
    write_pc_estimates(pc_rows(make_sweep(), "none", "STUDY"), str(path))
    df = pd.read_parquet(path)

    assert list(df.columns) == PC_COLUMNS
    assert str(df["L"].dtype) == "Int32"
    var_peak = df[df["method"] == "var_peak"]
    crossing = df[df["method"] == "fss_crossing"]
    assert len(var_peak) == 3 and var_peak["L"].notna().all()
    assert sorted(var_peak["L"]) == list(LS)
    assert len(crossing) == 1 and crossing["L"].isna().all()


def test_write_raises_on_duplicate_and_leaves_file_untouched(tmp_path):
    path = tmp_path / "pc.parquet"
    rows = pc_rows(make_sweep(), "none", "STUDY")
    write_pc_estimates(rows, str(path))
    before = path.read_bytes()

    with pytest.raises(ValueError, match="duplicate"):
        write_pc_estimates(rows, str(path))
    with pytest.raises(ValueError, match="duplicate"):
        write_pc_estimates([rows[0]], str(path))                     # one per-L row
    with pytest.raises(ValueError, match="duplicate"):
        write_pc_estimates([rows[-1]], str(path))                    # the crossing row
    assert path.read_bytes() == before


def test_write_raises_on_duplicate_within_one_call(tmp_path):
    r = key_row("STUDY", "none", 0.0, 0.0, 0.45)
    with pytest.raises(ValueError, match="duplicate"):
        write_pc_estimates([r, dict(r)], str(tmp_path / "pc.parquet"))
    assert not (tmp_path / "pc.parquet").exists()


def test_write_appends_other_keys_and_keeps_existing_rows(tmp_path):
    path = tmp_path / "pc.parquet"
    write_pc_estimates(pc_rows(make_sweep(), "none", "STUDY"), str(path))
    first = pd.read_parquet(path)
    write_pc_estimates(
        pc_rows(make_sweep(p0=0.5, kappa=2.0), "none", "STUDY"), str(path)
    )
    both = pd.read_parquet(path)
    assert len(both) == 8
    pd.testing.assert_frame_equal(both.iloc[:4].reset_index(drop=True), first)
    # same method and L but a different b or kappa is a different key, not a duplicate
    write_pc_estimates([key_row("STUDY", "none", 0.0, 4.0, 0.52)], str(path))
    assert len(pd.read_parquet(path)) == 9


@pytest.mark.parametrize("bad", [
    {"method": "mystery"},
    {"regime": "OTHER"},
    {"L": 128},                                          # crossing row with L set
    {"p_c": float("nan")},
    {"p_c": 1.2},
    {"p_c_stderr": -0.1},
])
def test_write_rejects_malformed_rows(tmp_path, bad):
    row = {**key_row("STUDY", "none", 0.0, 0.0, 0.45), **bad}
    with pytest.raises(ValueError):
        write_pc_estimates([row], str(tmp_path / "pc.parquet"))


def test_write_rejects_var_peak_row_without_L(tmp_path):
    row = key_row("STUDY", "none", 0.0, 0.0, 0.45, method="var_peak")
    with pytest.raises(ValueError, match="L set"):
        write_pc_estimates([row], str(tmp_path / "pc.parquet"))


def test_write_rejects_wrong_columns(tmp_path):
    row = key_row("STUDY", "none", 0.0, 0.0, 0.45)
    row["extra"] = 1
    with pytest.raises(ValueError, match="columns"):
        write_pc_estimates([row], str(tmp_path / "pc.parquet"))


def test_write_creates_missing_directory(tmp_path):
    path = tmp_path / "nested" / "results" / "pc.parquet"
    write_pc_estimates([key_row("STUDY", "none", 0.0, 0.0, 0.45)], str(path))
    assert path.exists()


# --- resolve_p --------------------------------------------------------------


def seeded(tmp_path, *rows, name="pc.parquet"):
    path = tmp_path / name
    write_pc_estimates(list(rows), str(path))
    return str(path)


def test_resolve_p_adds_the_offset(tmp_path):
    path = seeded(tmp_path, key_row("STUDY", "none", 0.0, 2.0, 0.55))
    kw = dict(regime="STUDY", condition="none", b=0.0, kappa=2.0, path=path)
    assert resolve_p(0.0, **kw) == pytest.approx(0.55)
    assert resolve_p(0.05, **kw) == pytest.approx(0.60)
    assert resolve_p(-0.05, **kw) == pytest.approx(0.50)


def test_resolve_p_raises_when_file_is_missing(tmp_path):
    with pytest.raises(FileNotFoundError, match="no fallback"):
        resolve_p(0.0, regime="STUDY", condition="none", b=0.0, kappa=0.0,
                  path=str(tmp_path / "absent.parquet"))


def test_resolve_p_raises_when_row_is_missing(tmp_path):
    path = seeded(tmp_path, key_row("STUDY", "none", 0.0, 0.0, 0.55))
    for kw in (
        dict(regime="STUDY", condition="none", b=0.0, kappa=2.0),       # other kappa
        dict(regime="STUDY", condition="random", b=0.0, kappa=0.0),     # other condition
        dict(regime="STUDY", condition="none", b=0.15, kappa=0.0),      # other b
    ):
        with pytest.raises(LookupError, match="no 'fss_crossing' row"):
            resolve_p(0.0, path=path, **kw)


def test_resolve_p_never_returns_a_percolation_row_for_study(tmp_path):
    path = seeded(tmp_path, key_row("PERCOLATION", "none", 0.0, 0.0, 0.41))
    with pytest.raises(LookupError):
        resolve_p(0.0, regime="STUDY", condition="none", b=0.0, kappa=0.0, path=path)

    both = seeded(tmp_path,
                  key_row("PERCOLATION", "none", 0.0, 0.0, 0.41),
                  key_row("STUDY", "none", 0.0, 0.0, 0.58), name="both.parquet")
    assert resolve_p(0.0, regime="STUDY", condition="none", b=0.0, kappa=0.0,
                     path=both) == pytest.approx(0.58)
    assert resolve_p(0.0, regime="PERCOLATION", condition="none", b=0.0, kappa=0.0,
                     path=both) == pytest.approx(0.41)


def test_resolve_p_uses_the_crossing_row_not_a_per_L_row(tmp_path):
    path = seeded(
        tmp_path,
        key_row("STUDY", "none", 0.0, 0.0, 0.50, L=128, method="var_peak"),
        key_row("STUDY", "none", 0.0, 0.0, 0.51, L=256, method="var_peak"),
        key_row("STUDY", "none", 0.0, 0.0, 0.52, L=512, method="var_peak"),
        key_row("STUDY", "none", 0.0, 0.0, 0.47),
    )
    assert resolve_p(0.0, regime="STUDY", condition="none", b=0.0, kappa=0.0,
                     path=path) == pytest.approx(0.47)


def test_resolve_p_with_only_per_L_rows_raises(tmp_path):
    path = seeded(tmp_path, key_row("STUDY", "none", 0.0, 0.0, 0.50, L=128, method="var_peak"))
    with pytest.raises(LookupError):
        resolve_p(0.0, regime="STUDY", condition="none", b=0.0, kappa=0.0, path=path)


def test_resolve_p_raises_on_two_crossing_rows(tmp_path):
    # write_pc_estimates refuses this, so build the file directly
    rows = [key_row("STUDY", "none", 0.0, 0.0, 0.50), key_row("STUDY", "none", 0.0, 0.0, 0.52)]
    path = tmp_path / "pc.parquet"
    pd.DataFrame(rows).astype({"L": "Int32"}).to_parquet(path, index=False)
    with pytest.raises(LookupError, match="unique"):
        resolve_p(0.0, regime="STUDY", condition="none", b=0.0, kappa=0.0, path=str(path))


def test_resolve_p_rejects_an_impossible_p(tmp_path):
    path = seeded(tmp_path, key_row("STUDY", "none", 0.0, 0.0, 0.97))
    with pytest.raises(ValueError, match="not a probability"):
        resolve_p(0.05, regime="STUDY", condition="none", b=0.0, kappa=0.0, path=path)


def test_resolve_p_round_trips_a_measured_threshold(tmp_path):
    """The whole chain: sweep -> estimate -> rows -> parquet -> resolved p."""
    path = tmp_path / "pc.parquet"
    write_pc_estimates(pc_rows(make_sweep(p0=0.52, kappa=2.0), "none", "STUDY"), str(path))
    p_c, _ = estimate_pc(make_sweep(p0=0.52, kappa=2.0), "none", "STUDY")
    assert resolve_p(0.05, regime="STUDY", condition="none", b=0.0, kappa=2.0,
                     path=str(path)) == pytest.approx(p_c + 0.05)


# --- the literature value must not leak into analysis ----------------------


def test_literature_constant_is_absent_from_analysis_py():
    src = (Path(__file__).resolve().parent.parent / "src" / "analysis.py").read_text()
    assert "0.407" not in src and "P_C_LITERATURE" not in src


# ===========================================================================
# SPEC-15: burn-size tail fitting
# ===========================================================================
#
# Every check runs against synthetic samples drawn from the exact discrete model
# with known parameters, so a fit that is quietly wrong shows up here rather
# than as a plausible exponent in a result (SPEC-15 Notes).

from src.analysis import (  # noqa: E402
    G2_MIN_DECADES,
    TAIL_COLUMNS,
    TAIL_FIT_FIELDS,
    fit_tail,
    g2_gate,
    write_tail_fits,
)

TAIL_X_MAX = 256 * 256   # the Experiment 2b lattice


def tail_sample(rng, n, alpha, x_min, *, cutoff=None, x_max=TAIL_X_MAX, body=0):
    """n draws from p(x) ∝ x^-alpha · exp(-x/cutoff) on {x_min..x_max}, plus
    `body` draws uniform on {1..x_min-1} that are *not* power law, so x_min has
    something real to find."""
    x = np.arange(x_min, x_max + 1, dtype=float)
    w = x ** -alpha * (np.exp(-x / cutoff) if cutoff else 1.0)
    out = rng.choice(x, size=n, p=w / w.sum()).astype(np.int64)
    if body:
        out = np.concatenate([out, rng.integers(1, x_min, size=body)])
    return rng.permutation(out)


def test_tail_fit_returns_every_contract_field():
    f = fit_tail(tail_sample(np.random.default_rng(0), 2000, 2.0, 5), x_max=TAIL_X_MAX)
    for key in ("x_min", "alpha", "alpha_stderr", "cutoff", "n_tail", "decades_above_xmin",
                "ks_distance"):
        assert key in f
    assert list(f) == TAIL_FIT_FIELDS
    assert all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in f.values())


@pytest.mark.parametrize("alpha", [1.6, 2.2, 2.8])
def test_tail_recovers_known_exponent_at_known_xmin(alpha):
    f = fit_tail(tail_sample(np.random.default_rng(1), 5000, alpha, 10), x_max=TAIL_X_MAX, x_min=10)
    assert abs(f["alpha"] - alpha) <= 2 * f["alpha_stderr"]
    assert abs(f["alpha_pl"] - alpha) <= 2 * f["alpha_pl_stderr"]
    assert f["alpha_stderr"] < 0.05


def test_tail_alpha_stderr_is_calibrated():
    """Acceptance: alpha recovered "to within the returned stderr". For an
    honest stderr that holds in about 68% of samples, so it is checked as
    coverage over 40 independent samples, not on one hand-picked seed."""
    inside = []
    for seed in range(40):
        f = fit_tail(tail_sample(np.random.default_rng(100 + seed), 3000, 2.2, 10),
                     x_max=TAIL_X_MAX, x_min=10)
        inside.append(abs(f["alpha"] - 2.2) <= f["alpha_stderr"])
    assert 0.5 <= np.mean(inside) <= 0.9


def test_tail_reports_no_cutoff_on_untruncated_data():
    # A 1-sigma interval excludes the truth (here: "no cutoff") by chance in
    # about one sample in six, so this is a rate, not an every-sample check.
    detections = reaches_none = 0
    for seed in range(40):
        f = fit_tail(tail_sample(np.random.default_rng(200 + seed), 3000, 2.2, 10),
                     x_max=TAIL_X_MAX, x_min=10)
        reaches_none += f["cutoff_hi"] == np.inf
        detections += f["cutoff_p_value"] < 0.05
    assert reaches_none >= 30
    assert detections <= 8   # nominal 5% of 40 = 2; generous for the boundary test


def test_tail_recovers_known_cutoff():
    f = fit_tail(tail_sample(np.random.default_rng(3), 8000, 1.5, 5, cutoff=2000),
                 x_max=TAIL_X_MAX, x_min=5)
    assert f["cutoff_p_value"] < 1e-6
    assert f["cutoff_lo"] <= 2000 * 1.15 and f["cutoff_hi"] >= 2000 / 1.15
    assert abs(f["alpha"] - 1.5) <= 3 * f["alpha_stderr"]
    # the pure power law, forced to absorb the cutoff, is biased steep
    assert f["alpha_pl"] > f["alpha"] + 3 * f["alpha_stderr"]


def test_tail_cutoff_interval_is_calibrated():
    inside = []
    for seed in range(40):
        f = fit_tail(tail_sample(np.random.default_rng(300 + seed), 4000, 1.5, 5, cutoff=2000),
                     x_max=TAIL_X_MAX, x_min=5)
        inside.append(f["cutoff_lo"] <= 2000 <= f["cutoff_hi"])
    assert 0.5 <= np.mean(inside) <= 0.9


def test_tail_distinguishes_truncation_from_exponent_change():
    """The SQ3 question itself: same alpha with a shorter cutoff must read as
    truncation, a different alpha with no cutoff as an exponent change."""
    rng = np.random.default_rng(4)
    base = fit_tail(tail_sample(rng, 8000, 1.7, 3, cutoff=20000), x_max=TAIL_X_MAX, x_min=3)
    trunc = fit_tail(tail_sample(rng, 8000, 1.7, 3, cutoff=1000), x_max=TAIL_X_MAX, x_min=3)
    steep = fit_tail(tail_sample(rng, 8000, 2.3, 3), x_max=TAIL_X_MAX, x_min=3)
    assert abs(trunc["alpha"] - base["alpha"]) < 3 * np.hypot(trunc["alpha_stderr"], base["alpha_stderr"])
    assert trunc["cutoff_hi"] < base["cutoff_lo"]
    assert steep["alpha"] - base["alpha"] > 10 * np.hypot(steep["alpha_stderr"], base["alpha_stderr"])


def test_tail_xmin_selected_by_ks_finds_the_tail():
    """The body below 30 is uniform, not power law. KS selection should land at
    or above the true start (it errs high, which only costs tail points, never
    low into the body), and alpha should come out right either way."""
    picked = []
    for seed in range(10):
        f = fit_tail(tail_sample(np.random.default_rng(900 + seed), 4000, 2.0, 30, body=6000),
                     x_max=TAIL_X_MAX)
        picked.append(f["x_min"])
        assert f["x_min"] >= 25                      # never deep in the body
        assert abs(f["alpha"] - 2.0) <= 3 * f["alpha_stderr"]
        assert f["n"] == 10000
    assert 28 <= np.median(picked) <= 45


def test_tail_decades_above_xmin():
    f = fit_tail(tail_sample(np.random.default_rng(6), 3000, 1.6, 10), x_max=TAIL_X_MAX, x_min=10)
    assert f["decades_above_xmin"] == pytest.approx(np.log10(f["max_size"] / 10))


def test_tail_fit_is_deterministic():
    s = tail_sample(np.random.default_rng(7), 3000, 2.0, 5, body=500)
    assert fit_tail(s, x_max=TAIL_X_MAX) == fit_tail(s.copy(), x_max=TAIL_X_MAX)


def test_tail_drops_zero_sizes_and_rejects_bad_input():
    s = tail_sample(np.random.default_rng(8), 2000, 2.0, 5)
    with_zeros = np.concatenate([s, np.zeros(300, dtype=int)])
    assert fit_tail(with_zeros, x_max=TAIL_X_MAX, x_min=5)["n"] == 2000
    with pytest.raises(ValueError):
        fit_tail(np.arange(1, 20), x_max=TAIL_X_MAX)               # too few
    with pytest.raises(ValueError):
        fit_tail(s + 0.5, x_max=TAIL_X_MAX)                          # not counts
    with pytest.raises(ValueError):
        fit_tail(s, x_max=int(s.max()) - 1)                          # support too small
    with pytest.raises(ValueError):
        fit_tail(s, x_max=TAIL_X_MAX, x_min=int(s.max()))            # tail too short


def test_tail_analysis_imports_no_forbidden_package():
    src = Path("src/analysis.py").read_text()
    for bad in ("scipy", "powerlaw", "numba", "torch"):
        assert f"import {bad}" not in src and f"from {bad}" not in src


# --- the gate and the writer -------------------------------------------------


def _fit_row(condition, decades_seed=0, replicates=10_000, **over):
    f = fit_tail(tail_sample(np.random.default_rng(decades_seed), 1000, 2.0, 5), x_max=TAIL_X_MAX)
    row = {"experiment": "2b", "condition": condition, "geometry_params": "{}", "b": 0.15,
           "replicates": replicates, "p": 0.5, "kappa": 0.0, "L": 256, **f}
    row.update(over)
    return row


def test_g2_gate_flags_short_tails():
    rows = pd.DataFrame([_fit_row("none", decades_above_xmin=3.1),
                         _fit_row("random", decades_above_xmin=G2_MIN_DECADES - 0.2)])
    gate = g2_gate(rows)
    assert gate.set_index("condition")["passes"].to_dict() == {"none": True, "random": False}


def test_write_tail_fits_is_append_only(tmp_path):
    path = tmp_path / "tail_fits.parquet"
    write_tail_fits([_fit_row("none", b=0.0)], path)
    write_tail_fits([_fit_row("random")], path)
    df = pd.read_parquet(path)
    assert list(df.columns) == TAIL_COLUMNS and len(df) == 2
    with pytest.raises(ValueError, match="duplicate"):
        write_tail_fits([_fit_row("random")], path)
    assert len(pd.read_parquet(path)) == 2                         # nothing written
    write_tail_fits([_fit_row("random", replicates=50_000)], path)  # G2 rerun is a new key
    assert len(pd.read_parquet(path)) == 3


def test_write_tail_fits_requires_every_column(tmp_path):
    row = _fit_row("none")
    del row["alpha"]
    with pytest.raises(ValueError, match="missing"):
        write_tail_fits([row], tmp_path / "t.parquet")
