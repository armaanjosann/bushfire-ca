"""SPEC-08: the figure registry and the validation figure.

The registry contract matters most: notebooks display `FIGURES[name]()` directly
(DEC-016), so every builder must return a `Figure` and must not write to disk.
"""

import re
import shutil
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from matplotlib.figure import Figure

from figures import make_figures as mf

REPO = Path(__file__).resolve().parents[1]
SOURCE = (REPO / "figures" / "make_figures.py").read_text(encoding="utf-8")


@pytest.fixture
def results_dir(tmp_path, monkeypatch):
    """An empty stand-in for results/, so missing-file behaviour can be tested."""
    monkeypatch.setattr(mf, "RESULTS_DIR", tmp_path)
    return tmp_path


# --- registry ---------------------------------------------------------------
def test_registry_is_nonempty_and_every_builder_returns_a_figure():
    assert mf.FIGURES, "no figures registered"
    for name, builder in mf.FIGURES.items():
        assert callable(builder), name
        fig = builder()
        assert isinstance(fig, Figure), f"{name} returned {type(fig).__name__}"


def test_validation_is_registered():
    assert "validation" in mf.FIGURES


def test_builders_do_not_write_to_disk(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    for builder in mf.FIGURES.values():
        builder()
    assert list(tmp_path.iterdir()) == []


def test_every_figure_has_a_caption_next_to_it():
    assert set(mf.CAPTIONS) == set(mf.FIGURES)
    for name, builder in mf.FIGURES.items():
        assert builder.caption and builder.caption == mf.CAPTIONS[name]


def test_register_rejects_duplicate_and_non_figure(monkeypatch):
    monkeypatch.setattr(mf, "FIGURES", dict(mf.FIGURES))
    monkeypatch.setattr(mf, "CAPTIONS", dict(mf.CAPTIONS))
    with pytest.raises(ValueError):
        mf.figure("validation", caption="x")(lambda: None)

    mf.figure("not_a_figure", caption="x")(lambda: None)
    with pytest.raises(TypeError):
        mf.FIGURES["not_a_figure"]()


# --- build / CLI ------------------------------------------------------------
def test_build_writes_a_file_and_returns_its_path(tmp_path):
    path = mf.build("validation", str(tmp_path / "out"))
    assert Path(path).is_file() and Path(path).stat().st_size > 0


def test_build_all_covers_the_registry(tmp_path):
    paths = mf.build_all(str(tmp_path))
    assert [Path(p).stem for p in paths] == list(mf.FIGURES)


def test_build_unknown_name_raises(tmp_path):
    with pytest.raises(KeyError, match="nope"):
        mf.build("nope", str(tmp_path))


def test_rebuilding_gives_byte_identical_files(tmp_path):
    a = mf.build("validation", str(tmp_path / "a"))
    b = mf.build("validation", str(tmp_path / "b"))
    assert Path(a).read_bytes() == Path(b).read_bytes()


def test_cli_builds_one_figure(tmp_path, capsys):
    assert mf.main(["--figure", "validation", "--outdir", str(tmp_path)]) == 0
    assert (tmp_path / "validation.png").is_file()
    assert "validation.png" in capsys.readouterr().out


# --- reads results only, never simulates ------------------------------------
def test_source_never_simulates_or_imports_the_model():
    assert "run_fire" not in SOURCE
    assert "capture_scar" not in SOURCE
    assert not re.search(r"^\s*(from|import)\s+src", SOURCE, flags=re.MULTILINE)


def test_literature_constant_matches_the_model():
    from src.model import P_C_LITERATURE

    assert mf.P_C_LITERATURE == P_C_LITERATURE


@pytest.mark.parametrize("missing", ["exp0.parquet", "pc_estimates.parquet"])
def test_missing_results_raise_a_clear_error(results_dir, missing):
    for name in ("exp0.parquet", "pc_estimates.parquet"):
        if name != missing:
            shutil.copy(REPO / "results" / name, results_dir / name)
    with pytest.raises(FileNotFoundError, match=missing):
        mf.FIGURES["validation"]()


def test_no_results_at_all_raises(results_dir):
    with pytest.raises(FileNotFoundError):
        mf.FIGURES["validation"]()


def test_missing_lattice_size_raises(results_dir):
    df = pd.read_parquet(REPO / "results" / "exp0.parquet")
    df[df["L"] != 512].to_parquet(results_dir / "exp0.parquet")
    shutil.copy(REPO / "results" / "pc_estimates.parquet", results_dir / "pc_estimates.parquet")
    with pytest.raises(ValueError, match="512"):
        mf.FIGURES["validation"]()


def test_study_rows_in_exp0_are_refused(results_dir):
    df = pd.read_parquet(REPO / "results" / "exp0.parquet")
    df = df.assign(regime="STUDY")
    df.to_parquet(results_dir / "exp0.parquet")
    shutil.copy(REPO / "results" / "pc_estimates.parquet", results_dir / "pc_estimates.parquet")
    with pytest.raises(ValueError, match="PERCOLATION"):
        mf.FIGURES["validation"]()


def test_missing_crossing_row_raises(results_dir):
    shutil.copy(REPO / "results" / "exp0.parquet", results_dir / "exp0.parquet")
    pc = pd.read_parquet(REPO / "results" / "pc_estimates.parquet")
    pc[pc["method"] != "fss_crossing"].to_parquet(results_dir / "pc_estimates.parquet")
    with pytest.raises(LookupError):
        mf.FIGURES["validation"]()


# --- the validation figure --------------------------------------------------
def _vlines(ax):
    """x positions of full-height vertical lines on an axis."""
    xs = []
    for line in ax.get_lines():
        x = list(line.get_xdata())
        if len(x) == 2 and x[0] == x[1]:
            xs.append(float(x[0]))
    return xs


def test_validation_shows_three_curves_the_crossing_and_the_literature_marker():
    fig = mf.FIGURES["validation"]()
    pc = pd.read_parquet(REPO / "results" / "pc_estimates.parquet")
    crossing = pc[(pc["regime"] == "PERCOLATION") & (pc["method"] == "fss_crossing")]["p_c"].iloc[0]

    for ax in fig.axes:
        labels = [line.get_label() for line in ax.get_lines()]
        for size in mf.VALIDATION_SIZES:
            assert f"L = {size}" in labels
        assert sorted(_vlines(ax)) == pytest.approx(sorted([crossing, mf.P_C_LITERATURE]))
    legend = " ".join(t.get_text() for t in fig.legends[0].get_texts())
    assert "FSS crossing" in legend and "Literature" in legend and "validation target" in legend


def test_validation_curves_are_the_experiment_0_proportions():
    df = pd.read_parquet(REPO / "results" / "exp0.parquet")
    fig = mf.FIGURES["validation"]()
    ax = fig.axes[0]
    for size in mf.VALIDATION_SIZES:
        line = next(l for l in ax.get_lines() if l.get_label() == f"L = {size}")
        sub = df[df["L"] == size]
        expected = sub.groupby("p")["spanned"].apply(lambda s: s.astype(float).mean()).sort_index()
        assert list(line.get_xdata()) == pytest.approx(list(expected.index))
        assert list(line.get_ydata()) == pytest.approx(list(expected.values))


def test_validation_never_shows_a_study_threshold():
    """§10.1 D5, §2 O4: the PERCOLATION threshold never sits beside a STUDY one."""
    pc = pd.read_parquet(REPO / "results" / "pc_estimates.parquet")
    study = pc[pc["regime"] == "STUDY"]["p_c"].tolist()
    fig = mf.FIGURES["validation"]()
    drawn = [x for ax in fig.axes for x in _vlines(ax)]
    for s in study:
        assert all(abs(x - s) > 1e-3 for x in drawn)
    text = " ".join(t.get_text() for ax in fig.axes for t in ax.texts) + fig._suptitle.get_text()
    assert "not comparable" in text


def test_validation_caption_states_the_constraints():
    caption = mf.CAPTIONS["validation"]
    assert "validation target only" in caption
    assert "not comparable with any STUDY threshold" in caption


# ===========================================================================
# SPEC-17: the results figures
# ===========================================================================

RESULTS_FIGURES = (
    "clustering-scale", "efficiency", "threshold-shift", "burn-size-distributions",
    "sq4-tradeoff", "wind-interaction", "sensitivity", "scars", "scars-space-time",
)


def test_every_results_figure_is_registered_with_a_caption():
    """The report cites these by name; a missing one must fail here, not be
    noticed when the report is written."""
    for name in RESULTS_FIGURES:
        assert name in mf.FIGURES, f"{name} is not registered"
        assert callable(mf.FIGURES[name])
        assert len(mf.CAPTIONS[name]) > 120, f"{name} has no real caption"


@pytest.mark.parametrize("name", RESULTS_FIGURES)
def test_results_figure_builds_and_returns_a_figure(name):
    fig = mf.FIGURES[name]()
    assert isinstance(fig, Figure)
    assert fig.axes, f"{name} produced no axes"


@pytest.mark.parametrize("name", RESULTS_FIGURES)
def test_results_figure_raises_clearly_when_its_input_is_missing(name, results_dir):
    """A builder must say which command to run, not plot an empty axis."""
    with pytest.raises((FileNotFoundError, LookupError, ValueError)) as excinfo:
        mf.FIGURES[name]()
    assert "run `python run.py" in str(excinfo.value)


def test_figures_never_simulate():
    assert not re.search(r"\brun_fire\b|\bcapture_scar\b", SOURCE), \
        "figures/make_figures.py must never call the simulator (§9)"
    assert not re.search(r"^\s*(from|import)\s+src\b", SOURCE, re.M), \
        "figures/make_figures.py must not import from src/"


def test_scar_state_codes_match_the_model():
    """The scar figures colour by cell state using literals, so that this module
    imports nothing from src/. Those literals must agree with the model."""
    from src import model

    for name in ("EMPTY", "FUEL", "BURNING", "BURNT", "SETTLEMENT"):
        assert getattr(mf, name) == getattr(model, name), name


def test_no_results_figure_places_a_percolation_threshold_beside_a_study_one():
    """§10.1 D5: the validation threshold is a different quantity and must never
    sit in the same panel as a treated STUDY threshold."""
    pc = pd.read_parquet(mf.RESULTS_DIR / mf.PC_PATH)
    perc = float(pc[(pc["regime"] == "PERCOLATION") & (pc["method"] == "fss_crossing")]["p_c"].iloc[0])
    for name in RESULTS_FIGURES:
        fig = mf.FIGURES[name]()
        for ax in fig.axes:
            for line in ax.lines:
                xs = line.get_xdata()
                if len(xs):
                    assert not any(abs(float(x) - perc) < 1e-6 for x in np.atleast_1d(xs)), \
                        f"{name} draws the PERCOLATION threshold"


def test_threshold_shift_shows_the_scale_dependent_condition_without_a_single_value():
    """DEC-041: a condition with no scale-free threshold is shown as its per-L
    points and labelled as such, never as one number."""
    fig = mf.FIGURES["threshold-shift"]()
    labels = [t.get_text() for t in fig.axes[0].get_yticklabels()]
    assert any("no scale-free value" in lb for lb in labels)
    assert any("untreated" in lb for lb in labels)


def test_efficiency_divides_by_the_realised_treated_area():
    """§11: the efficiency metric divides by realised n_treated, never nominal b."""
    body = SOURCE.split("def efficiency()")[1].split("# ---")[0]
    assert "n_treated" in body and "n_cells" in body
    assert not re.search(r'/\s*cell\["b"\]|/\s*b\b', body), "efficiency must not divide by nominal b"


def test_sq4_figure_plots_both_response_variables():
    fig = mf.FIGURES["sq4-tradeoff"]()
    ax = fig.axes[0]
    assert "burned" in ax.get_xlabel()
    assert "settlement" in ax.get_ylabel()
    assert len(ax.collections) + len(ax.lines) > 5, "every condition should appear"


def test_burn_size_figure_reports_the_fit_verdict():
    """DEC-043: a rejected fit must be visible on the figure, not just in the data."""
    fits = pd.read_parquet(mf.RESULTS_DIR / mf.TAIL_FITS_PATH)
    fig = mf.FIGURES["burn-size-distributions"]()
    text = " ".join(t.get_text() for ax in fig.axes for t in ax.texts)
    if (fits["fit_rejected"] > 0).any():
        assert "REJECTED" in text


def test_scar_figures_need_the_npz_and_its_ignition_steps(results_dir, tmp_path):
    np.savez_compressed(results_dir / mf.SCARS_PATH, run_ids=np.array(["abc"]),
                        **{"abc__scar": np.zeros((4, 4), dtype=np.int8)})
    for name in ("scars", "scars-space-time"):
        with pytest.raises(ValueError, match="ignition_step"):
            mf.FIGURES[name]()


def test_building_twice_gives_byte_identical_files(tmp_path):
    first, second = tmp_path / "a", tmp_path / "b"
    for name in RESULTS_FIGURES:
        a, b = mf.build(name, str(first)), mf.build(name, str(second))
        assert Path(a).read_bytes() == Path(b).read_bytes(), f"{name} is not reproducible"


def test_build_all_covers_every_registered_figure(tmp_path):
    paths = mf.build_all(str(tmp_path))
    assert len(paths) == len(mf.FIGURES)
    assert all(Path(p).exists() and Path(p).stat().st_size > 5_000 for p in paths)
