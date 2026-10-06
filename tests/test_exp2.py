"""SPEC-14: Experiment 2 — selection, pre-pass centring, the declared sweep."""

import json

import numpy as np
import pandas as pd
import pytest

from src import experiments
from src.experiments import (
    EXP2_HALF_WIDTH,
    EXP2_L,
    EXP2_N_P,
    EXP2_P_STEP,
    EXP2_PREPASS_P,
    EXP2_PREPASS_R,
    EXP2_R,
    config_run_id,
    exp2_centres,
    exp2_grid,
    exp2_levels,
    exp2_p_values,
    exp2_prepass_grid,
    exp2_selection,
)

LEVELS = [("random", {}), ("patches", {"k": 4}), ("strips_perp", {"w": 4})]


def _fake_exp1(path, means):
    rows = []
    for (fam, key, val), m in means.items():
        g = json.dumps({key: val, "settlement_side": 16}, separators=(",", ":"), sort_keys=True)
        for bf in (m - 0.01, m + 0.01):
            rows.append({"condition": fam, "geometry_params": g, "b": 0.15, "kappa": 0.0,
                         "p_rel": 0.05, "burned_fraction": bf})
    # decoys outside the selection cell, which must be ignored
    rows.append({"condition": "patches", "geometry_params": '{"k":16,"settlement_side":16}', "b": 0.30,
                 "kappa": 0.0, "p_rel": 0.05, "burned_fraction": 0.0})
    rows.append({"condition": "patches", "geometry_params": '{"k":16,"settlement_side":16}', "b": 0.15,
                 "kappa": 2.0, "p_rel": 0.05, "burned_fraction": 0.0})
    pd.DataFrame(rows).to_parquet(path, index=False)


def test_selection_rule_on_real_experiment_1():
    sel = exp2_selection()
    assert sel["patches"]["params"] == {"k": 4} and sel["strips_perp"]["params"] == {"w": 4}
    assert min(sel["patches"]["means"].values()) == sel["patches"]["means"]['{"k":4}']


def test_selection_rule_uses_only_the_declared_cell(tmp_path):
    path = tmp_path / "exp1.parquet"
    _fake_exp1(path, {("patches", "k", 4): 0.3, ("patches", "k", 8): 0.1, ("patches", "k", 16): 0.2,
                      ("strips_perp", "w", 4): 0.2, ("strips_perp", "w", 8): 0.3, ("strips_perp", "w", 16): 0.05})
    sel = exp2_selection(str(path))
    assert sel["patches"]["params"] == {"k": 8} and sel["strips_perp"]["params"] == {"w": 16}
    assert exp2_levels(str(path)) == [("random", {}), ("patches", {"k": 8}), ("strips_perp", {"w": 16})]


def test_selection_needs_experiment_1(tmp_path):
    with pytest.raises(FileNotFoundError):
        exp2_selection(str(tmp_path / "missing.parquet"))


def test_declared_sweep_is_explicit_and_symmetric():
    assert (EXP2_HALF_WIDTH, EXP2_P_STEP, EXP2_N_P) == (0.05, 0.005, 21)
    ps = exp2_p_values(0.6)
    assert len(ps) == 21 and ps[0] == 0.55 and ps[-1] == 0.65 and ps[10] == 0.6
    assert np.allclose(np.diff(ps), 0.005)


def test_prepass_grid_shape():
    cfgs = exp2_prepass_grid(LEVELS)
    assert len(cfgs) == 3 * len(EXP2_PREPASS_P) * EXP2_PREPASS_R
    assert {c.L for c in cfgs} == {128} and min(c.p for c in cfgs) == 0.40 and max(c.p for c in cfgs) == 1.0
    for c in cfgs[:: 997]:
        assert (c.ignition, c.settlement, c.b, c.kappa, c.phi) == ("edge", False, 0.15, 0.0, -np.pi / 2)


def _prepass_frame(curves):
    rows = []
    for cond, (p_half, _) in curves.items():
        for p in EXP2_PREPASS_P:
            k = 100 if p >= p_half else 0
            rows += [{"condition": cond, "p": p, "spanned": i < k, "truncated": False} for i in range(100)]
    return pd.DataFrame(rows)


def test_centres_from_prepass():
    df = _prepass_frame({"random": (0.53, None), "strips_perp": (0.76, None)})
    c = exp2_centres(df, [("random", {}), ("strips_perp", {"w": 4})])
    assert c == {"random": 0.53, "strips_perp": 0.76}


def test_centres_refuse_unbracketed_and_past_p_one():
    with pytest.raises(ValueError, match="never reaches"):
        exp2_centres(_prepass_frame({"strips_perp": (2.0, None)}), [("strips_perp", {})])
    with pytest.raises(ValueError, match="not bracketed"):
        exp2_centres(_prepass_frame({"random": (0.0, None)}), [("random", {})])
    with pytest.raises(ValueError, match="past p=1"):
        exp2_centres(_prepass_frame({"random": (0.99, None)}), [("random", {})])


def test_grid_shape_seeds_and_staged_resume():
    centres = {"random": 0.53, "patches": 0.52, "strips_perp": 0.76}
    full = exp2_grid(LEVELS, centres, replicates=3)
    assert len(full) == 3 * 21 * 3 * 3
    assert len({config_run_id(c) for c in full}) == len(full)
    staged = exp2_grid(LEVELS, centres, sizes=(128,), replicates=2)
    assert {config_run_id(c) for c in staged} <= {config_run_id(c) for c in full}
    assert all(c.condition != "none" for c in full)
    for cond, centre in centres.items():
        ps = sorted({c.p for c in full if c.condition == cond})
        assert ps[0] == pytest.approx(centre - 0.05) and ps[-1] == pytest.approx(centre + 0.05)


def test_grid_rejects_bad_requests():
    centres = {"random": 0.53, "patches": 0.52, "strips_perp": 0.76}
    with pytest.raises(ValueError):
        exp2_grid(LEVELS, centres, replicates=EXP2_R + 1)
    with pytest.raises(ValueError):
        exp2_grid(LEVELS, centres, sizes=(64,))


def test_staged_run_end_to_end_records_nothing(tmp_path, monkeypatch):
    monkeypatch.setattr(experiments, "EXP2_PREPASS_P", (0.40, 0.50, 0.60, 0.70, 0.80, 0.90))
    pc = tmp_path / "pc.parquet"
    df = experiments.run_exp2(prepass_path=str(tmp_path / "pre.parquet"), out_path=str(tmp_path / "e2.parquet"),
                              pc_path=str(pc), sizes=(128,), replicates=2)
    assert len(df) == 3 * 21 * 2 and not pc.exists()
    assert df["spanned"].notna().all() and df["reached_edge"].isna().all()


# --- per-L 50% points, for a condition with no scale-free threshold (DEC-041) ---


from src.experiments import EXP2_SCALE_COLUMNS, p50_rows, write_p50  # noqa: E402


def _sweep_frame(p50_by_L, *, condition="strips_perp", n=500, width=0.02):
    """A sweep whose P(span) is a logistic centred at `p50_by_L[L]` for each L."""
    rows = []
    for L, centre in p50_by_L.items():
        for p in np.round(np.arange(centre - 0.05, centre + 0.0501, 0.005), 4):
            k = int(round(n / (1 + np.exp(-(p - centre) / width))))
            rows += [{"condition": condition, "b": 0.15, "kappa": 0.0, "L": L, "p": p,
                      "spanned": i < k, "truncated": False} for i in range(n)]
    return pd.DataFrame(rows)


def test_p50_rows_recovers_each_lattice_sizes_midpoint():
    want = {128: 0.75, 256: 0.71, 512: 0.67}
    rows = p50_rows(_sweep_frame(want), "strips_perp")
    assert {r["L"] for r in rows} == set(want)
    for r in rows:
        assert abs(r["p50"] - want[r["L"]]) < 0.002
        assert 0 < r["p50_stderr"] < 0.01
        assert (r["regime"], r["condition"], r["b"], r["kappa"]) == ("STUDY", "strips_perp", 0.15, 0.0)
        assert r["n_per_point"] == 500


def test_p50_rows_refuses_a_sweep_that_never_reaches_half():
    df = _sweep_frame({128: 0.95})          # centred far above its own window
    df = df[df["p"] < 0.92]
    with pytest.raises(ValueError, match="does not cross 1/2"):
        p50_rows(df, "strips_perp")


def test_p50_rows_is_robust_to_sampling_noise():
    # a curve with a small non-monotone dip must still give a sensible midpoint
    df = _sweep_frame({256: 0.60})
    dip = (df["p"] == 0.595) & (df.groupby("p").cumcount() < 60)
    df.loc[dip, "spanned"] = ~df.loc[dip, "spanned"]
    assert abs(p50_rows(df, "strips_perp")[0]["p50"] - 0.60) < 0.005


def test_write_p50_is_append_only(tmp_path):
    path = tmp_path / "scale.parquet"
    write_p50(p50_rows(_sweep_frame({128: 0.75, 256: 0.71}), "strips_perp"), path)
    assert list(pd.read_parquet(path).columns) == EXP2_SCALE_COLUMNS
    write_p50(p50_rows(_sweep_frame({128: 0.53}, condition="random"), "random"), path)
    assert len(pd.read_parquet(path)) == 3
    with pytest.raises(ValueError, match="duplicate"):
        write_p50(p50_rows(_sweep_frame({128: 0.53}, condition="random"), "random"), path)
    assert len(pd.read_parquet(path)) == 3        # nothing written on the clash
    write_p50([], path)                            # no rows is a no-op


def test_run_exp2_records_what_crosses_and_refuses_what_does_not():
    """The committed Experiment 2 result (DEC-041, option A): random and patches
    have a threshold, strips_perp has only per-L points, and `resolve_p` refuses
    the condition that has none rather than inventing a value."""
    from src.analysis import resolve_p

    pc = pd.read_parquet("results/pc_estimates.parquet")
    study = pc[(pc.regime == "STUDY") & (pc.b == 0.15) & (pc.method == "fss_crossing")]
    assert set(study.condition) == {"random", "patches"}
    assert resolve_p(0.0, regime="STUDY", condition="random", b=0.15, kappa=0.0) > 0.5
    with pytest.raises(LookupError):
        resolve_p(0.0, regime="STUDY", condition="strips_perp", b=0.15, kappa=0.0)

    scale = pd.read_parquet("results/exp2_scale.parquet")
    strips = scale[scale.condition == "strips_perp"].sort_values("L")
    assert list(strips.L) == [128, 256, 512]
    assert strips.p50.is_monotonic_decreasing          # the finding: it falls with L
    assert strips.p50.min() > 0.6                      # and stays far above untreated 0.477
