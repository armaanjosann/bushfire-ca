"""Real tests for Config validation (project-context.md §4.4) and wind_weights
(§3.4). SPEC-01."""

import numpy as np
import pytest

from src.model import Config, NEIGHBOURS, wind_weights


def _percolation_kwargs(**overrides):
    kwargs = dict(
        regime="PERCOLATION",
        beta=1.0,
        kappa=0.0,
        diagonal_factor=False,
        tau=1,
        b=0.0,
        ignition="edge",
    )
    kwargs.update(overrides)
    return kwargs


# --- valid construction --------------------------------------------------


def test_default_config_is_valid():
    Config()


def test_valid_percolation_config():
    Config(**_percolation_kwargs())


# --- §4.4 regime consistency ----------------------------------------------


def test_percolation_rejects_beta_not_one():
    with pytest.raises(ValueError, match="beta"):
        Config(**_percolation_kwargs(beta=0.8))


def test_percolation_rejects_kappa_not_zero():
    with pytest.raises(ValueError, match="kappa"):
        Config(**_percolation_kwargs(kappa=2.0))


def test_percolation_rejects_diagonal_factor_true():
    with pytest.raises(ValueError, match="diagonal_factor"):
        Config(**_percolation_kwargs(diagonal_factor=True))


def test_percolation_rejects_tau_not_one():
    with pytest.raises(ValueError, match="tau"):
        Config(**_percolation_kwargs(tau=2))


def test_percolation_rejects_b_not_zero():
    with pytest.raises(ValueError, match="b"):
        Config(**_percolation_kwargs(b=0.1, condition="random"))


def test_percolation_rejects_ignition_not_edge():
    with pytest.raises(ValueError, match="ignition"):
        Config(**_percolation_kwargs(ignition="random_cell"))


# --- §4.4 condition consistency --------------------------------------------


def test_buffer_condition_requires_settlement():
    with pytest.raises(ValueError, match="settlement"):
        Config(condition="buffer", settlement=False, b=0.1)


def test_buffer_condition_with_settlement_is_valid():
    Config(condition="buffer", settlement=True, b=0.1)


def test_none_condition_rejects_nonzero_budget():
    with pytest.raises(ValueError, match="b"):
        Config(condition="none", b=0.1)


# --- §4.4 range checks ------------------------------------------------------


def test_b_below_zero_rejected():
    with pytest.raises(ValueError, match="b"):
        Config(condition="random", b=-0.1)


def test_b_above_one_rejected():
    with pytest.raises(ValueError, match="b"):
        Config(condition="random", b=1.1)


def test_p_below_zero_rejected():
    with pytest.raises(ValueError, match="p"):
        Config(p=-0.1)


def test_p_above_one_rejected():
    with pytest.raises(ValueError, match="p"):
        Config(p=1.1)


def test_tau_below_one_rejected():
    with pytest.raises(ValueError, match="tau"):
        Config(tau=0)


def test_l_below_32_rejected():
    with pytest.raises(ValueError, match="L"):
        Config(L=16)


# --- wind_weights (§3.4) ---------------------------------------------------


def test_wind_weights_flat_kernel_is_ones():
    w = wind_weights(0.0, 0.0, False)
    assert np.allclose(w, np.ones(8))


@pytest.mark.parametrize("kappa", [0.0, 1.0, 2.0, 4.0])
@pytest.mark.parametrize("phi", [0.0, np.pi / 4, np.pi / 2])
@pytest.mark.parametrize("diagonal_factor", [True, False])
def test_wind_weights_mean_is_one(kappa, phi, diagonal_factor):
    w = wind_weights(kappa, phi, diagonal_factor)
    assert w.shape == (8,)
    assert abs(w.mean() - 1.0) < 1e-12


def test_wind_weights_diagonal_factor_shrinks_diagonals():
    w = wind_weights(0.0, 0.0, True)
    is_diagonal = np.array([(dy != 0 and dx != 0) for dy, dx in NEIGHBOURS])
    diag = w[is_diagonal]
    axial = w[~is_diagonal]
    assert np.allclose(diag, diag[0])
    assert np.all(diag < axial)
