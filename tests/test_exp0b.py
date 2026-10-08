"""SPEC-19: Experiment 0b — untreated STUDY baseline thresholds."""

import math

import numpy as np
import pandas as pd
import pytest

from src import experiments
from src.model import NEIGHBOURS, wind_weights


# --- the symmetry §6.1 relies on --------------------------------------------


@pytest.mark.parametrize("kappa", [1.0, 2.0, 4.0])
def test_phi_minus_half_pi_is_the_phi_0_kernel_rotated_90_clockwise(kappa):
    """A 90-degree clockwise rotation takes east (0, +1) to south (+1, 0), i.e.
    (dy, dx) -> (dx, -dy). Wind from row 0 towards row L-1 is east wind rotated
    that way, so its weights are the phi=0 weights moved along that map."""
    w0 = wind_weights(kappa, 0.0, True)
    w_south = wind_weights(kappa, -math.pi / 2, True)

    perm = [NEIGHBOURS.index((dx, -dy)) for dy, dx in NEIGHBOURS]
    assert sorted(perm) == list(range(8))
    assert perm != list(range(8)), "rotation must move directions, or the test proves nothing"

    expected = np.empty(8)
    expected[perm] = w0
    np.testing.assert_allclose(w_south, expected, rtol=1e-12, atol=1e-15)
    assert not np.allclose(w_south, w0), "phi must matter at kappa > 0"


# --- grids --------------------------------------------------------------------

CENTRES = {0.0: 0.55, 1.0: 0.60, 2.0: 0.65, 4.0: 0.75}


def test_prepass_grid_settings_and_size():
    cfgs = experiments.exp0b_prepass_grid()
    assert len(cfgs) == 4 * 61 * 100
    assert {c.L for c in cfgs} == {128}
    assert {c.kappa for c in cfgs} == {0.0, 1.0, 2.0, 4.0}
    assert min(c.p for c in cfgs) == 0.30 and max(c.p for c in cfgs) == 0.90
    assert len({c.seed for c in cfgs}) == len(cfgs)
    assert len({experiments.config_run_id(c) for c in cfgs}) == len(cfgs)


def test_sweep_grid_settings_and_size():
    cfgs = experiments.exp0b_grid(CENTRES)
    assert len(cfgs) == 4 * 21 * 3 * 500 == 126_000
    assert len({experiments.config_run_id(c) for c in cfgs}) == len(cfgs)
    for c in cfgs[::997]:
        assert (c.regime, c.condition, c.b, c.beta, c.f_treat, c.tau) == \
            ("STUDY", "none", 0.0, 0.8, 0.2, 1)
        assert c.diagonal_factor is True and c.ignition == "edge" and c.settlement is False
        assert c.phi == -math.pi / 2


def test_sweep_p_values_are_centre_plus_minus_0_05_at_step_0_005():
    ps = experiments.exp0b_p_values(0.655)
    assert len(ps) == 21
    assert ps[0] == 0.605 and ps[10] == 0.655 and ps[-1] == 0.705
    np.testing.assert_allclose(np.diff(ps), 0.005)


def test_sweep_seeds_do_not_depend_on_the_requested_subset():
    full = experiments.exp0b_grid(CENTRES)
    staged = experiments.exp0b_grid(CENTRES, sizes=(128, 256), replicates=7)
    ids = {experiments.config_run_id(c) for c in full}
    assert len(staged) == 4 * 21 * 2 * 7
    assert all(experiments.config_run_id(c) in ids for c in staged)


def test_sweep_seeds_clear_of_the_prepass():
    pre = {c.seed for c in experiments.exp0b_prepass_grid()}
    assert not pre & {c.seed for c in experiments.exp0b_grid(CENTRES, sizes=(128,), replicates=5)}


def test_grid_rejects_unknown_size_and_missing_centre():
    with pytest.raises(ValueError):
        experiments.exp0b_grid(CENTRES, sizes=(64,))
    with pytest.raises(ValueError):
        experiments.exp0b_grid({0.0: 0.5})


# --- centre derivation --------------------------------------------------------


def _prepass_frame(transitions: dict, n=10):
    """Synthetic pre-pass: P(span) is 0 below the kappa's transition p and 1 from it on
    (None => never reaches 0.5)."""
    rows = []
    for kappa in experiments.EXP0B_KAPPAS:
        t = transitions[kappa]
        for p in experiments.EXP0B_PREPASS_P:
            hit = t is not None and p >= t - 1e-9
            for r in range(n):
                rows.append({"regime": "STUDY", "condition": "none", "L": 128, "kappa": kappa,
                             "p": p, "spanned": hit, "truncated": False})
    df = pd.DataFrame(rows)
    df["spanned"] = df["spanned"].astype("boolean")
    return df


def test_centre_is_smallest_p_with_half_spanning_rounded_to_0_005():
    df = _prepass_frame({0.0: 0.57, 1.0: 0.60, 2.0: 0.66, 4.0: 0.75})
    assert experiments.exp0b_centres(df) == {0.0: 0.57, 1.0: 0.6, 2.0: 0.66, 4.0: 0.75}


def test_exactly_half_counts_and_one_run_short_does_not():
    df = _prepass_frame({0.0: 0.60, 1.0: 0.60, 2.0: 0.66, 4.0: 0.75})
    at = df.index[(df["kappa"] == 0.0) & (df["p"] == 0.50)]
    df.loc[at, "spanned"] = [True] * 5 + [False] * 5      # P(span) = 0.5 exactly
    assert experiments.exp0b_centres(df)[0.0] == 0.5
    df.loc[at, "spanned"] = [True] * 4 + [False] * 6      # P(span) = 0.4
    assert experiments.exp0b_centres(df)[0.0] == 0.6


def test_centre_is_deterministic():
    df = _prepass_frame({0.0: 0.57, 1.0: 0.60, 2.0: 0.66, 4.0: 0.75})
    assert experiments.exp0b_centres(df) == experiments.exp0b_centres(df.sample(frac=1, random_state=1))


def test_centre_raises_when_no_p_reaches_half():
    df = _prepass_frame({0.0: 0.57, 1.0: 0.60, 2.0: 0.66, 4.0: None})
    with pytest.raises(ValueError, match="DEC"):
        experiments.exp0b_centres(df)


def test_centre_raises_when_transition_is_not_bracketed():
    df = _prepass_frame({0.0: 0.30, 1.0: 0.60, 2.0: 0.66, 4.0: 0.75})
    with pytest.raises(ValueError, match="bracketed"):
        experiments.exp0b_centres(df)


def test_centre_refuses_a_truncated_frame():
    df = _prepass_frame({0.0: 0.57, 1.0: 0.60, 2.0: 0.66, 4.0: 0.75})
    df.loc[0, "truncated"] = True
    with pytest.raises(AssertionError):
        experiments.exp0b_centres(df)


# --- run_exp0b on a staged run ------------------------------------------------


def test_staged_run_records_no_threshold(tmp_path, monkeypatch):
    """A subset of sizes runs the configs and writes nothing to pc_estimates."""
    ran = []

    def fake_run_configs(cfgs, path, **kw):
        ran.append(len(cfgs))
        return pd.DataFrame({"run_id": [experiments.config_run_id(c) for c in cfgs]})

    monkeypatch.setattr(experiments, "run_configs", fake_run_configs)
    monkeypatch.setattr(experiments, "_check_exp0b_frame", lambda *a, **k: None)
    pc_path = tmp_path / "pc.parquet"
    experiments.run_exp0b(sizes=(128,), replicates=2, centres=CENTRES,
                          prepass_path=str(tmp_path / "pre.parquet"),
                          out_path=str(tmp_path / "x.parquet"), pc_path=str(pc_path))
    assert ran == [4 * 61 * 100, 4 * 21 * 1 * 2]
    assert not pc_path.exists()
