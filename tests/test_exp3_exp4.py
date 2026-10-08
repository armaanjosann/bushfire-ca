"""SPEC-16: Experiment 3 (wind interaction), Experiment 4 (sensitivity), and the
I11 frame-invariance grid."""

import math

import numpy as np
import pandas as pd
import pytest

from src import experiments
from src.analysis import resolve_p
from src.experiments import (
    EXP3_B,
    EXP3_KAPPAS,
    EXP3_P_REL,
    EXP3_R,
    EXP4_B,
    EXP4_BETA,
    EXP4_F_TREAT,
    EXP4_KAPPA,
    EXP4_R,
    I11_KAPPA,
    I11_PHIS,
    I11_R,
    config_run_id,
    exp3_grid,
    exp3_levels,
    exp4_grid,
    exp4_levels,
    i11_gaps,
    i11_grid,
)
from src.model import SETTLEMENT_SIDE


# --- Experiment 3 ------------------------------------------------------------


def test_exp3_has_seven_treated_conditions_plus_the_untreated_reference():
    levels = exp3_levels()
    treated = [lv for lv in levels if lv[0] != "none"]
    assert len(treated) == 7 and len(levels) == 8
    assert {c for c, _, _ in treated} == {"random", "patches", "strips_perp", "strips_para", "buffer"}
    assert sorted(prm["k"] for c, prm, _ in treated if c == "patches") == [4, 8, 16]
    assert all(b == EXP3_B for _, _, b in treated)
    assert levels[0] == ("none", {}, 0.0)


def test_exp3_grid_shape_and_settings():
    cfgs, p_rels = exp3_grid(replicates=3)
    assert len(cfgs) == len(EXP3_KAPPAS) * 8 * 3 == len(p_rels)
    assert set(p_rels) == {EXP3_P_REL}
    assert len({config_run_id(c) for c in cfgs}) == len(cfgs)
    for c in cfgs:
        assert (c.L, c.regime, c.ignition, c.settlement, c.phi) == (256, "STUDY", "random_cell", True, 0.0)
        assert c.geometry_params["settlement_side"] == SETTLEMENT_SIDE
    assert {c.kappa for c in cfgs} == set(EXP3_KAPPAS)


def test_exp3_resolves_each_kappa_against_its_own_threshold():
    """The spec names this as the single most likely error in SPEC-16."""
    cfgs, _ = exp3_grid(replicates=2)
    by_kappa = {}
    for c in cfgs:
        by_kappa.setdefault(c.kappa, set()).add(c.p)
    assert len({next(iter(v)) for v in by_kappa.values()}) == len(EXP3_KAPPAS), "thresholds must differ by kappa"
    for kappa, ps in by_kappa.items():
        assert len(ps) == 1
        want = resolve_p(EXP3_P_REL, regime="STUDY", condition="none", b=0.0, kappa=kappa)
        assert next(iter(ps)) == pytest.approx(want, abs=1e-12)


def test_exp3_frame_check_catches_a_kappa_mismatched_threshold(tmp_path):
    cfgs, p_rels = exp3_grid(replicates=1)
    keep = [i for i, c in enumerate(cfgs) if c.condition in ("none", "random")]
    df = experiments.run_configs([cfgs[i] for i in keep], str(tmp_path / "e3.parquet"),
                                 p_rel=[p_rels[i] for i in keep])
    bad = df.copy()
    bad.loc[bad["kappa"] == 4.0, "p"] = bad.loc[bad["kappa"] == 0.0, "p"].iloc[0]
    with pytest.raises(AssertionError, match="threshold"):
        experiments._check_exp3_frame(bad, len(bad))


def test_exp3_replicate_bounds():
    with pytest.raises(ValueError):
        exp3_grid(replicates=0)
    with pytest.raises(ValueError):
        exp3_grid(replicates=EXP3_R + 1)


# --- Experiment 4 ------------------------------------------------------------


def test_exp4_condition_set_is_reduced():
    levels = exp4_levels()
    assert len(levels) == 5 < len(exp3_levels())
    assert [c for c, _, _ in levels] == ["none", "random", "patches", "strips_perp", "buffer"]


def test_exp4_grid_is_the_full_cross_at_one_absolute_p():
    cfgs, p_rels = exp4_grid(replicates=2)
    assert len(cfgs) == len(EXP4_F_TREAT) * len(EXP4_BETA) * 5 * 2
    assert set(p_rels) == {None}, "Experiment 4 rows carry no p_rel (DEC-011)"
    assert len({c.p for c in cfgs}) == 1, "one absolute p, held fixed across every cell"
    want = resolve_p(0.05, regime="STUDY", condition="none", b=0.0, kappa=EXP4_KAPPA)
    assert cfgs[0].p == pytest.approx(want, abs=1e-12)
    assert {c.kappa for c in cfgs} == {EXP4_KAPPA}
    assert {round(c.f_treat, 6) for c in cfgs} == set(EXP4_F_TREAT)
    assert {round(c.beta, 6) for c in cfgs} == set(EXP4_BETA)
    assert len({config_run_id(c) for c in cfgs}) == len(cfgs)


def test_exp4_does_not_recentre_per_beta():
    """A sensitivity check holds the landscape fixed while beta varies, so every
    beta must sit at the same p (§6.2 note, DEC-011)."""
    cfgs, _ = exp4_grid(replicates=1)
    by_beta = {}
    for c in cfgs:
        by_beta.setdefault(c.beta, set()).add(c.p)
    assert all(len(v) == 1 for v in by_beta.values())
    assert len({next(iter(v)) for v in by_beta.values()}) == 1


# --- I11 ---------------------------------------------------------------------


def test_i11_grid_is_both_orientations_at_both_wind_angles():
    cfgs, p_rels = i11_grid(replicates=4)
    assert len(cfgs) == len(I11_PHIS) * 2 * 4
    assert {c.phi for c in cfgs} == set(I11_PHIS)
    assert {c.condition for c in cfgs} == {"strips_perp", "strips_para"}
    assert {c.kappa for c in cfgs} == {I11_KAPPA}
    assert all(not c.settlement for c in cfgs)
    assert len({config_run_id(c) for c in cfgs}) == len(cfgs)


def test_i11_geometry_rotates_with_the_wind():
    """At phi = pi/4 the bands must be diagonal, so the two conditions differ
    there as they do on the axes. If they did not, that would be a SPEC-10
    defect, not something to patch in SPEC-16."""
    from src.geometries import generate

    occupied = np.random.default_rng(0).random((128, 128)) < 0.6
    n = round(0.15 * occupied.sum())
    for phi in I11_PHIS:
        perp = generate("strips_perp", np.random.default_rng(1), occupied, n, w=4, phi=phi)
        para = generate("strips_para", np.random.default_rng(1), occupied, n, w=4, phi=phi)
        assert not np.array_equal(perp, para)


def test_i11_gaps_reports_magnitude_and_overlap():
    def frame(gap0, gap1, n=200, sd=0.05):
        rng, rows = np.random.default_rng(3), []
        for phi, gap in zip(I11_PHIS, (gap0, gap1)):
            for cond, mean in (("strips_perp", 0.10 + gap), ("strips_para", 0.10)):
                rows += [{"phi": phi, "condition": cond, "truncated": False,
                          "burned_fraction": v} for v in rng.normal(mean, sd, n)]
        return pd.DataFrame(rows)

    same = i11_gaps(frame(0.03, 0.03))
    assert list(same["phi"]) == sorted(I11_PHIS)
    assert same.attrs["overlap"] is True
    assert abs(same.attrs["difference"]) < 3 * same.attrs["difference_stderr"]

    differ = i11_gaps(frame(0.03, -0.05))
    assert differ.attrs["overlap"] is False
    assert differ.attrs["difference"] == pytest.approx(0.08, abs=0.02)
    for col in ("gap", "gap_stderr", "ci_lo", "ci_hi", "n_per_condition"):
        assert col in differ.columns
