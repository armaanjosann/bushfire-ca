"""SPEC-08: the figure registry and the validation figure.

The registry contract matters most: notebooks display `FIGURES[name]()` directly
(DEC-016), so every builder must return a `Figure` and must not write to disk.
"""

import re
import shutil
from pathlib import Path

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
