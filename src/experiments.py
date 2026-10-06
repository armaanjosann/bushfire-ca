"""Experiment harness and entry points (project-context.md §4.5, §5).

This module owns the results schema (§5): `run_configs` turns a list of
Configs into one parquet row per run, in parallel, resumable. Experiment grids
are built by the specs named on the `run_exp*` stubs below; none of them may
change a column.
"""

import dataclasses
import hashlib
import json
import math
import multiprocessing
import os
import re
import subprocess
import time
from collections.abc import Sequence
from pathlib import Path

import numpy as np
import pandas as pd

from src.analysis import (PC_PATH, TAIL_FITS_PATH, assert_not_truncated, fit_tail, g2_gate,
                          pc_rows, resolve_p, write_pc_estimates, write_tail_fits)
from src.model import P_C_LITERATURE, SETTLEMENT_SIDE, Config, RunResult, run_fire

# Run-time tuning. Constants, read at call time and never mutated by this
# module (§8: no global mutable state).
WORKERS = os.cpu_count() or 1
MAX_CHUNK = 20          # most configs one worker task holds
CHUNKS_PER_WORKER = 4   # aim for this many tasks per worker so cores stay busy
FLUSH_SECONDS = 30.0    # minimum gap between checkpoint writes

BUDGET_BASIS = "occupied"  # §2 O2, §5

# §5 column order and dtypes. Pandas nullable dtypes (Int32, boolean) where the
# schema says `| null`; never -1 or False sentinels. `p_rel` and the other
# nullable floats are float64, and NaN is written to parquet as a true null.
SCHEMA: dict[str, str] = {
    "run_id": "str",
    "code_version": "str",
    "seed": "int64",
    "regime": "str",
    "L": "int32",
    "p": "float64",
    "p_rel": "float64",
    "condition": "str",
    "geometry_params": "str",
    "b": "float64",
    "budget_basis": "str",
    "f_treat": "float64",
    "beta": "float64",
    "kappa": "float64",
    "phi": "float64",
    "tau": "float64",
    "diagonal_factor": "bool",
    "ignition": "str",
    "ignition_y": "Int32",
    "ignition_x": "Int32",
    "settlement": "bool",
    "n_cells": "int32",
    "n_occupied": "int32",
    "n_treated": "int32",
    "burned_cells": "int32",
    "still_burning_cells": "int32",
    "burned_fraction": "float64",
    "burned_fraction_of_fuel": "float64",
    "spanned": "boolean",
    "reached_edge": "boolean",
    "settlement_reached": "boolean",
    "settlement_reached_step": "Int32",
    "steps": "int32",
    "truncated": "bool",
    "wall_ms": "float64",
}

_FLOAT_FIELDS = frozenset({"p", "f_treat", "beta", "kappa", "phi", "b"})
_INT_FIELDS = frozenset({"L", "tau", "seed", "max_steps"})


# --- identity ---------------------------------------------------------------


def _canon(value):
    """Reduce a config value to plain JSON types, stable across machines."""
    if isinstance(value, np.generic):
        value = value.item()
    if isinstance(value, dict):
        return {str(k): _canon(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_canon(v) for v in value]
    if isinstance(value, float):
        return value + 0.0  # -0.0 -> 0.0
    return value


def _canonical_config(cfg: Config) -> dict:
    out = {}
    for f in dataclasses.fields(cfg):
        v = _canon(getattr(cfg, f.name))
        if v is not None:
            if f.name in _FLOAT_FIELDS:
                v = float(v) + 0.0
            elif f.name in _INT_FIELDS:
                v = int(v)
        out[f.name] = v
    return out


def _dumps(obj) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"))


def config_run_id(cfg: Config) -> str:
    """Deterministic hash of every Config field, `geometry_params` included.

    Canonical JSON (sorted keys, numpy scalars unwrapped, 1 and 1.0 alike for
    float fields) fed to SHA-256, so it is the same in every process and on
    every machine. Python's `hash()` is salted per process and is not used.
    """
    return hashlib.sha256(_dumps(_canonical_config(cfg)).encode()).hexdigest()[:16]


def code_version() -> str:
    """Git short SHA of the checkout this code runs from.

    Raises rather than falling back to a placeholder: a made-up version
    committed alongside real results is invisible until submission
    (workflow-rules.md §9).
    """
    repo = Path(__file__).resolve().parent.parent
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=repo, capture_output=True, text=True, check=True, timeout=30,
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError) as exc:
        raise RuntimeError(f"cannot obtain a git short SHA for code_version: {exc}") from exc
    if not re.fullmatch(r"[0-9a-f]{7,40}", out):
        raise RuntimeError(f"git returned {out!r}, not a short SHA; refusing to write results")
    return out


# --- rows -------------------------------------------------------------------


def _assemble_row(cfg: Config, res: RunResult, wall_ms: float, version: str,
                  p_rel: float | None) -> dict:
    """One §5 row: config echo + RunResult outcome fields, copied and not recomputed (DEC-006)."""
    return {
        "run_id": config_run_id(cfg),
        "code_version": version,
        "seed": cfg.seed,
        "regime": cfg.regime,
        "L": cfg.L,
        "p": cfg.p,
        "p_rel": p_rel,
        "condition": cfg.condition,
        "geometry_params": _dumps(_canon(cfg.geometry_params)),
        "b": cfg.b,
        "budget_basis": BUDGET_BASIS,
        "f_treat": cfg.f_treat,
        "beta": cfg.beta,
        "kappa": cfg.kappa,
        "phi": cfg.phi,
        "tau": cfg.tau,
        "diagonal_factor": cfg.diagonal_factor,
        "ignition": cfg.ignition,
        "ignition_y": res.ignition_y,
        "ignition_x": res.ignition_x,
        "settlement": cfg.settlement,
        "n_cells": res.n_cells,
        "n_occupied": res.n_occupied,
        "n_treated": res.n_treated,  # realised, not round(b * n_occupied)
        "burned_cells": res.burned_cells,
        "still_burning_cells": res.still_burning_cells,
        "burned_fraction": res.burned_fraction,
        "burned_fraction_of_fuel": res.burned_fraction_of_fuel,
        "spanned": res.spanned,
        "reached_edge": res.reached_edge,
        "settlement_reached": res.settlement_reached,
        "settlement_reached_step": res.settlement_reached_step,
        "steps": res.steps,
        "truncated": res.truncated,
        "wall_ms": wall_ms,
    }


def _to_frame(rows: list[dict]) -> pd.DataFrame:
    df = pd.DataFrame(rows, columns=list(SCHEMA))
    return _coerce(df)


def _coerce(df: pd.DataFrame) -> pd.DataFrame:
    return df.astype(SCHEMA)


def _run_chunk(task: tuple) -> list[dict]:
    """Worker body. Each run builds its own generator from cfg.seed inside run_fire."""
    pairs, version = task
    rows = []
    for cfg, p_rel in pairs:
        t0 = time.perf_counter()
        res = run_fire(cfg)
        wall_ms = (time.perf_counter() - t0) * 1000.0
        rows.append(_assemble_row(cfg, res, wall_ms, version, p_rel))
    return rows


# --- runner -----------------------------------------------------------------


def _read_existing(out_path: Path) -> pd.DataFrame:
    df = pd.read_parquet(out_path)
    missing = [c for c in SCHEMA if c not in df.columns]
    if missing:
        raise ValueError(f"{out_path} does not match the §5 schema; missing columns {missing}")
    return _coerce(df[list(SCHEMA)])


def _write_atomic(df: pd.DataFrame, out_path: Path) -> None:
    """Write via a temp file and rename, so an interrupt never leaves a torn parquet."""
    tmp = out_path.with_name(out_path.name + ".tmp")
    df.to_parquet(tmp, index=False)
    os.replace(tmp, out_path)


def run_configs(cfgs: list[Config], out_path: str, resume: bool = True, *,
                p_rel: Sequence[float | None] | None = None) -> pd.DataFrame:
    """Run every config and write one §5 row per run to `out_path` (parquet).

    Returns the whole contents of `out_path` afterwards, previously written
    rows first, then new rows in input order.

    With `resume=True`, configs whose `run_id` is already in the file are
    skipped and the new rows are added to the existing ones; the rows already
    there are carried over unchanged. `resume=False` refuses to touch an
    existing file (results are append-only, workflow-rules.md §9).

    `p_rel` is parallel to `cfgs` (DEC-029, DEC-030): the offset from the
    governing p_c for configs whose `p` was resolved that way, else None.
    `Config` has no such field, and it is not part of `run_id`.

    Work is split into chunks of consecutive configs, so the replicates of a
    parameter point land together. Completed chunks are checkpointed to
    `out_path` every `FLUSH_SECONDS`, so an interrupted run resumes from the
    last checkpoint.
    """
    cfgs = list(cfgs)
    if p_rel is None:
        p_rels = [None] * len(cfgs)
    else:
        p_rels = [None if v is None or (isinstance(v, float) and math.isnan(v)) else float(v)
                  for v in p_rel]
        if len(p_rels) != len(cfgs):
            raise ValueError(f"p_rel has {len(p_rels)} entries for {len(cfgs)} configs")

    ids = [config_run_id(c) for c in cfgs]
    if len(set(ids)) != len(ids):
        raise ValueError("cfgs contains duplicate configs (same run_id); each run needs a distinct seed")

    version = code_version()  # before any compute, and before any write
    out = Path(out_path)

    if out.exists():
        if not resume:
            raise FileExistsError(f"{out} exists; results are append-only, use resume=True or a new path")
        existing = _read_existing(out)
    else:
        existing = _to_frame([])

    done = set(existing["run_id"])
    todo = [(c, p) for c, p, i in zip(cfgs, p_rels, ids) if i not in done]
    if not todo:
        return existing

    workers = max(1, min(WORKERS, len(todo)))
    size = max(1, min(MAX_CHUNK, math.ceil(len(todo) / (CHUNKS_PER_WORKER * workers))))
    tasks = [(todo[i:i + size], version) for i in range(0, len(todo), size)]

    out.parent.mkdir(parents=True, exist_ok=True)
    frame = existing
    pending: list[dict] = []

    def flush():
        nonlocal frame, pending
        if not pending:
            return
        new = _to_frame(pending)
        frame = new if frame.empty else pd.concat([frame, new], ignore_index=True)
        pending = []
        _write_atomic(frame, out)

    last_flush = time.monotonic()
    try:
        if workers == 1:
            results = map(_run_chunk, tasks)
            pool = None
        else:
            pool = multiprocessing.Pool(workers)
            results = pool.imap(_run_chunk, tasks)  # ordered: file order == input order
        try:
            for rows in results:
                pending.extend(rows)
                if time.monotonic() - last_flush >= FLUSH_SECONDS:
                    flush()
                    last_flush = time.monotonic()
        finally:
            if pool is not None:
                pool.terminate()
                pool.join()
    finally:
        flush()  # keep every completed chunk, even on error or Ctrl-C
    return frame


# --- experiment entry points (bodies land in later specs) --------------------


# --- Experiment 0: percolation validation (SPEC-07) ---------------------------

EXP0_PATH = "results/exp0.parquet"
EXP0_L = (128, 256, 512)
EXP0_R = 500
EXP0_P = tuple(round(0.30 + 0.005 * i, 3) for i in range(61))  # 0.300 .. 0.600, §6.2
I1_TOLERANCE = 0.01  # §7 I1, DEC-014


def exp0_grid(sizes: Sequence[int] = EXP0_L, replicates: int = EXP0_R) -> list[Config]:
    """The §6.2 Experiment 0 configs: PERCOLATION, edge ignition, no treatment.

    Every setting §4.4 pins for PERCOLATION is passed explicitly, so the grid
    is rejected at construction if any of them ever stopped being what the
    exact site-percolation reduction needs (§1).

    Each run's seed is its position in the *full* grid (lattice size, then `p`,
    then replicate), so runs are independent of one another and a run has the
    same `run_id` whether it came from a subset of `sizes` or a smaller
    `replicates`. That is what lets a staged run (L=128, 256 first) resume into
    the full one.
    """
    if not 1 <= replicates <= EXP0_R:
        raise ValueError(f"replicates must be in 1..{EXP0_R}, got {replicates}")
    unknown = [L for L in sizes if L not in EXP0_L]
    if unknown:
        raise ValueError(f"sizes {unknown} are not in the Experiment 0 grid {EXP0_L}")
    cfgs = []
    for L in sorted(sizes):
        i_L = EXP0_L.index(L)
        for i_p, p in enumerate(EXP0_P):
            for r in range(replicates):
                cfgs.append(Config(
                    L=L, regime="PERCOLATION", p=p,
                    beta=1.0, kappa=0.0, diagonal_factor=False, tau=1,
                    condition="none", b=0.0, ignition="edge", settlement=False,
                    seed=(i_L * len(EXP0_P) + i_p) * EXP0_R + r,
                ))
    return cfgs


def _check_exp0_frame(df: pd.DataFrame, n_expected: int) -> None:
    """The Experiment 0 acceptance checks that hold row by row."""
    problems = []
    if len(df) != n_expected:
        problems.append(f"{len(df)} rows, expected {n_expected}")
    if df["truncated"].any():
        problems.append("truncated rows present (raise max_steps, do not filter, §3.7)")
    fixed = {"regime": "PERCOLATION", "beta": 1.0, "kappa": 0.0, "diagonal_factor": False,
             "b": 0.0, "tau": 1.0, "ignition": "edge", "condition": "none", "settlement": False}
    for col, want in fixed.items():
        if not (df[col] == want).all():
            problems.append(f"{col} is not {want!r} on every row")
    if df["reached_edge"].notna().any():
        problems.append("reached_edge is non-null (must be null under edge ignition, §3.5)")
    if df["spanned"].isna().any():
        problems.append("spanned is null on some rows")
    if problems:
        raise AssertionError("Experiment 0 frame failed: " + "; ".join(problems))


def _assert_i1(p_c: float) -> None:
    """§7 I1, and the only use of P_C_LITERATURE in the experiments (§6.1)."""
    if abs(p_c - P_C_LITERATURE) > I1_TOLERANCE:
        raise AssertionError(
            f"I1 failed: measured PERCOLATION p_c = {p_c:.4f}, literature {P_C_LITERATURE}, "
            f"tolerance {I1_TOLERANCE}. Stop and debug the model; do not proceed on a "
            "broken baseline (SPEC-07)."
        )


def run_exp0(sizes: Sequence[int] = EXP0_L, out_path: str = EXP0_PATH,
             pc_path: str = PC_PATH, replicates: int = EXP0_R) -> pd.DataFrame:
    """Experiment 0: run the grid, estimate p_c, assert I1.

    With the full `sizes` and `replicates` this writes `out_path`, then appends
    the four `pc_estimates` rows of DEC-004 (three per-`L` `var_peak` and one
    `fss_crossing`) through `pc_rows` / `write_pc_estimates`. A subset of
    `sizes` or fewer `replicates` is a staged or pilot run: it only runs the
    configs, because a threshold from part of the grid must not be recorded as
    the Experiment 0 estimate.

    I1 is asserted before anything is written to `pc_estimates.parquet`, so a
    failing baseline leaves no estimate on record. If the key is already there
    (a rerun after success) nothing is appended and the stored value is
    re-checked against I1.
    """
    cfgs = exp0_grid(sizes, replicates)
    df = run_configs(cfgs, out_path)
    _check_exp0_frame(df, len(cfgs))

    if tuple(sorted(sizes)) != EXP0_L or replicates != EXP0_R:
        print(f"Experiment 0 staged run: {len(df)} rows in {out_path}; "
              "no p_c recorded (not the full grid).")
        return df

    if Path(pc_path).exists():
        pc = pd.read_parquet(pc_path)
        mine = pc[(pc["regime"] == "PERCOLATION") & (pc["condition"] == "none")
                  & (pc["b"] == 0.0) & (pc["kappa"] == 0.0)]
        if not mine.empty:
            stored = mine.loc[mine["method"] == "fss_crossing", "p_c"]
            if len(stored) != 1:
                raise ValueError(f"{pc_path} holds a partial Experiment 0 key; resolve by hand")
            _assert_i1(float(stored.iloc[0]))
            print(f"Experiment 0 already recorded in {pc_path}: "
                  f"fss_crossing p_c = {float(stored.iloc[0]):.4f}")
            return df

    rows = pc_rows(df, "none", "PERCOLATION")
    crossing = next(r for r in rows if r["method"] == "fss_crossing")
    _assert_i1(crossing["p_c"])
    write_pc_estimates(rows, pc_path)

    peak = next(r for r in rows if r["method"] == "var_peak" and r["L"] == max(EXP0_L))
    print(f"Experiment 0: fss_crossing p_c = {crossing['p_c']:.4f} ± {crossing['p_c_stderr']:.4f} "
          f"(literature {P_C_LITERATURE}); L={peak['L']} var_peak = {peak['p_c']:.4f} "
          "(cross-check, not asserted)")
    return df


# --- Experiment 0b: untreated STUDY baseline thresholds (SPEC-19) -------------

EXP0B_PREPASS_PATH = "results/exp0b_prepass.parquet"
EXP0B_PATH = "results/exp0b.parquet"
EXP0B_KAPPAS = (0.0, 1.0, 2.0, 4.0)
EXP0B_PHI = -math.pi / 2  # §6.1 edge-ignition wind convention: wind blows row 0 -> row L-1
EXP0B_L = (128, 256, 512)
EXP0B_R = 500
EXP0B_HALF_WIDTH = 0.05
EXP0B_P_STEP = 0.005
EXP0B_N_P = 21  # centre +/- 0.05 at step 0.005
EXP0B_PREPASS_L = 128
EXP0B_PREPASS_R = 100
EXP0B_PREPASS_P = tuple(round(0.30 + 0.01 * i, 2) for i in range(61))  # 0.30 .. 0.90
EXP0B_SEED_BASE = 1_000_000  # keeps the sweep's streams clear of the pre-pass's


def _exp0b_config(L: int, p: float, kappa: float, seed: int) -> Config:
    """One untreated STUDY edge-ignition config. `beta`, `f_treat`, `tau` and
    `diagonal_factor` are passed explicitly so a change to a STUDY default
    cannot silently change what this experiment measures."""
    return Config(
        L=L, regime="STUDY", p=p, f_treat=0.2,
        beta=0.8, kappa=kappa, phi=EXP0B_PHI, tau=1, diagonal_factor=True,
        condition="none", b=0.0, ignition="edge", settlement=False, seed=seed,
    )


def exp0b_prepass_grid(replicates: int = EXP0B_PREPASS_R) -> list[Config]:
    """The pre-pass: L=128, p in [0.30, 0.90] step 0.01, every kappa.

    Seed is the run's position in the full pre-pass (kappa, then `p`, then
    replicate).
    """
    if not 1 <= replicates <= EXP0B_PREPASS_R:
        raise ValueError(f"replicates must be in 1..{EXP0B_PREPASS_R}, got {replicates}")
    n_p = len(EXP0B_PREPASS_P)
    return [
        _exp0b_config(EXP0B_PREPASS_L, p, kappa, (i_k * n_p + i_p) * EXP0B_PREPASS_R + r)
        for i_k, kappa in enumerate(EXP0B_KAPPAS)
        for i_p, p in enumerate(EXP0B_PREPASS_P)
        for r in range(replicates)
    ]


def exp0b_centres(prepass: pd.DataFrame) -> dict[float, float]:
    """Each kappa's sweep centre from the pre-pass frame (SPEC-19 scope).

    The centre is the smallest pre-pass `p` at which P(span) >= 0.5, rounded
    to the nearest 0.005. Deterministic in `prepass`. Raises if a kappa never
    reaches 0.5, or already has by the first `p`: the transition is then not
    bracketed by the pre-pass and a sweep centred on it would be a guess.
    """
    assert_not_truncated(prepass)
    centres = {}
    for kappa in EXP0B_KAPPAS:
        sub = prepass[(prepass["kappa"] == kappa) & (prepass["regime"] == "STUDY")
                      & (prepass["condition"] == "none") & (prepass["L"] == EXP0B_PREPASS_L)]
        if sub.empty:
            raise ValueError(f"pre-pass frame has no rows for kappa={kappa}")
        if sub["spanned"].isna().any():
            raise ValueError(f"pre-pass kappa={kappa} has null `spanned`")
        frac = sub.assign(hit=sub["spanned"].astype(bool)).groupby(
            sub["p"].round(6))["hit"].mean().sort_index()
        above = frac[frac >= 0.5]
        if above.empty:
            raise ValueError(
                f"kappa={kappa}: no pre-pass p has P(span) >= 0.5 (max {frac.max():.3f} at "
                f"p={frac.idxmax():.2f}). Stop and raise a DEC; do not widen past p=1 (SPEC-19)."
            )
        first = float(above.index[0])
        if first <= float(frac.index[0]) + 1e-9:
            raise ValueError(
                f"kappa={kappa}: P(span) >= 0.5 already at the lowest pre-pass p={first:.2f}; "
                "the transition is not bracketed. Stop and raise a DEC (SPEC-19)."
            )
        centres[kappa] = round(round(first / EXP0B_P_STEP) * EXP0B_P_STEP, 3)
    return centres


def exp0b_p_values(centre: float) -> tuple[float, ...]:
    """The 21 sweep points: centre +/- 0.05 at step 0.005."""
    return tuple(round(centre + EXP0B_P_STEP * (i - EXP0B_N_P // 2), 3) for i in range(EXP0B_N_P))


def exp0b_grid(centres: dict[float, float], sizes: Sequence[int] = EXP0B_L,
               replicates: int = EXP0B_R) -> list[Config]:
    """The §6.2 Experiment 0b main sweep, one 21-point arm per kappa.

    As in `exp0_grid`, a run's seed is its position in the *full* grid (kappa,
    `p`, lattice size, replicate), so a staged run (L=128, 256 first) resumes
    into the full one with the same `run_id`s.
    """
    if not 1 <= replicates <= EXP0B_R:
        raise ValueError(f"replicates must be in 1..{EXP0B_R}, got {replicates}")
    unknown = [L for L in sizes if L not in EXP0B_L]
    if unknown:
        raise ValueError(f"sizes {unknown} are not in the Experiment 0b grid {EXP0B_L}")
    missing = [k for k in EXP0B_KAPPAS if k not in centres]
    if missing:
        raise ValueError(f"no sweep centre for kappa {missing}")
    cfgs = []
    for i_k, kappa in enumerate(EXP0B_KAPPAS):
        for i_p, p in enumerate(exp0b_p_values(centres[kappa])):
            for L in sorted(sizes):
                i_L = EXP0B_L.index(L)
                base = EXP0B_SEED_BASE + (((i_k * EXP0B_N_P + i_p) * len(EXP0B_L)) + i_L) * EXP0B_R
                cfgs.extend(_exp0b_config(L, p, kappa, base + r) for r in range(replicates))
    return cfgs


def _check_exp0b_frame(df: pd.DataFrame, n_expected: int, what: str) -> None:
    """The Experiment 0b acceptance checks that hold row by row (pre-pass and sweep)."""
    problems = []
    if len(df) != n_expected:
        problems.append(f"{len(df)} rows, expected {n_expected}")
    if df["truncated"].any():
        problems.append("truncated rows present (raise max_steps, do not filter, §3.7)")
    if not df["run_id"].is_unique:
        problems.append("run_id is not unique")
    fixed = {"regime": "STUDY", "condition": "none", "b": 0.0, "beta": 0.8, "f_treat": 0.2,
             "tau": 1.0, "diagonal_factor": True, "ignition": "edge", "settlement": False,
             "phi": EXP0B_PHI}
    for col, want in fixed.items():
        if not (df[col] == want).all():
            problems.append(f"{col} is not {want!r} on every row")
    if df["reached_edge"].notna().any():
        problems.append("reached_edge is non-null (must be null under edge ignition, §3.5)")
    if df["spanned"].isna().any():
        problems.append("spanned is null on some rows")
    if problems:
        raise AssertionError(f"Experiment 0b {what} frame failed: " + "; ".join(problems))


def run_exp0b(sizes: Sequence[int] = EXP0B_L, prepass_path: str = EXP0B_PREPASS_PATH,
              out_path: str = EXP0B_PATH, pc_path: str = PC_PATH,
              replicates: int = EXP0B_R, centres: dict[float, float] | None = None
              ) -> pd.DataFrame:
    """Experiment 0b: pre-pass, sweep, and the untreated STUDY thresholds.

    Writes `prepass_path`, derives each kappa's sweep centre from it
    (`exp0b_centres`), runs the sweep into `out_path`, then appends four
    `pc_estimates` rows per kappa (three per-`L` `var_peak`, one `fss_crossing`)
    through `pc_rows` / `write_pc_estimates` (DEC-004, DEC-032).

    A subset of `sizes` or fewer `replicates` is a staged run: it only runs the
    configs and records no threshold, because a threshold from part of the grid
    must not be recorded as the Experiment 0b estimate (as `run_exp0`).
    `centres` replaces the pre-pass-derived centres, for re-centring an arm
    whose crossing fell outside its range (SPEC-19 Behaviour).

    Every crossing is checked to lie strictly inside its kappa's declared
    range, and all four are checked before any is written, so a failing arm
    leaves no estimate in the append-only file. If the keys are already
    recorded, nothing is appended.
    """
    prepass = run_configs(exp0b_prepass_grid(), prepass_path)
    _check_exp0b_frame(prepass, len(EXP0B_KAPPAS) * len(EXP0B_PREPASS_P) * EXP0B_PREPASS_R,
                       "pre-pass")
    centres = exp0b_centres(prepass) if centres is None else dict(centres)
    print("Experiment 0b sweep centres: "
          + ", ".join(f"kappa={k:g}: {centres[k]:.3f}" for k in EXP0B_KAPPAS))

    cfgs = exp0b_grid(centres, sizes, replicates)
    df = run_configs(cfgs, out_path)
    _check_exp0b_frame(df, len(cfgs), "sweep")

    if tuple(sorted(sizes)) != EXP0B_L or replicates != EXP0B_R:
        print(f"Experiment 0b staged run: {len(df)} rows in {out_path}; "
              "no p_c recorded (not the full grid).")
        return df

    if Path(pc_path).exists():
        pc = pd.read_parquet(pc_path)
        mine = pc[(pc["regime"] == "STUDY") & (pc["condition"] == "none")
                  & (pc["b"] == 0.0) & pc["kappa"].isin(EXP0B_KAPPAS)]
        if not mine.empty:
            have = set(mine.loc[mine["method"] == "fss_crossing", "kappa"])
            if have != set(EXP0B_KAPPAS) or len(mine) != 4 * len(EXP0B_KAPPAS):
                raise ValueError(f"{pc_path} holds a partial Experiment 0b record; resolve by hand")
            print(f"Experiment 0b already recorded in {pc_path}; nothing appended.")
            return df

    rows, report = [], []
    for kappa in EXP0B_KAPPAS:
        arm_rows = pc_rows(df[df["kappa"] == kappa], "none", "STUDY")
        crossing = next(r for r in arm_rows if r["method"] == "fss_crossing")
        lo = round(centres[kappa] - EXP0B_HALF_WIDTH, 3)
        hi = round(centres[kappa] + EXP0B_HALF_WIDTH, 3)
        if not lo < crossing["p_c"] < hi:
            raise AssertionError(
                f"kappa={kappa:g}: crossing p_c = {crossing['p_c']:.4f} is not strictly inside "
                f"its sweep range ({lo}, {hi}). Re-centre on it with `centres=` and rerun that "
                "arm; do not extrapolate (SPEC-19)."
            )
        rows.extend(arm_rows)
        report.append(f"kappa={kappa:g}: centre {centres[kappa]:.3f}, "
                      f"p_c = {crossing['p_c']:.4f} ± {crossing['p_c_stderr']:.4f}")
    write_pc_estimates(rows, pc_path)
    print("Experiment 0b: " + "; ".join(report))
    return df


# --- Settlement-size pilot (SPEC-12, project-context.md §10.2 O1) -------------

PILOT_PATH = "results/pilot_settlement.parquet"
PILOT_L = 256
PILOT_SIDES = (8, 16, 32, 48)
PILOT_KAPPAS = (0.0, 2.0)
PILOT_P_REL = 0.05
PILOT_R = 50
PILOT_CONTROL_R = len(PILOT_SIDES) * PILOT_R  # no-settlement runs per kappa
PILOT_SEED_BASE = 2_000_000  # clear of Experiments 0 and 0b (below 1.13M)

# The §10.2 O1 decision rule. Constants, fixed before the pilot was run (DEC-037).
P_REACH_BAND = (0.3, 0.8)  # rule 1: baseline P(settlement_reached)
N_OCC_TOLERANCE = 0.01     # rule 2: relative n_occupied drift versus no settlement


def pilot_grid(pc_path: str = PC_PATH, replicates: int = PILOT_R
               ) -> tuple[list[Config], list[float | None]]:
    """The §10.2 O1 pilot: `(configs, p_rel)`, parallel, ready for `run_configs`.

    Settlement runs: side x kappa x `replicates`, `b=0`, `condition="none"`,
    `p = p_c(kappa) + 0.05` resolved against Experiment 0b. Control runs: the
    "no-settlement case at the same p" that rule 2 compares `n_occupied` with,
    `PILOT_CONTROL_R` per kappa, with `settlement=False` and no
    `settlement_side` key (§3.6). With the default `replicates` that is
    400 + 400 = 800 runs. Seeds are positions in the full grid, so a run's
    `run_id` does not depend on `replicates`.
    """
    if not 1 <= replicates <= PILOT_R:
        raise ValueError(f"replicates must be in 1..{PILOT_R}, got {replicates}")
    n_sides, n_kappas = len(PILOT_SIDES), len(PILOT_KAPPAS)
    cfgs, p_rels = [], []

    def make(kappa, p, seed, settlement, params):
        return Config(
            L=PILOT_L, regime="STUDY", p=p, f_treat=0.2,
            beta=0.8, kappa=kappa, phi=0.0, tau=1, diagonal_factor=True,
            condition="none", b=0.0, geometry_params=params,
            ignition="random_cell", settlement=settlement, seed=seed,
        )

    for i_k, kappa in enumerate(PILOT_KAPPAS):
        p = resolve_p(PILOT_P_REL, regime="STUDY", condition="none", b=0.0, kappa=kappa, path=pc_path)
        for i_s, side in enumerate(PILOT_SIDES):
            for r in range(replicates):
                seed = PILOT_SEED_BASE + (i_s * n_kappas + i_k) * PILOT_R + r
                cfgs.append(make(kappa, p, seed, True, {"settlement_side": side}))
                p_rels.append(PILOT_P_REL)
        base = PILOT_SEED_BASE + n_sides * n_kappas * PILOT_R + i_k * PILOT_CONTROL_R
        for c in range(n_sides * replicates):
            cfgs.append(make(kappa, p, base + c, False, {}))
            p_rels.append(PILOT_P_REL)
    return cfgs, p_rels


def _check_pilot_frame(df: pd.DataFrame, n_expected: int) -> None:
    problems = []
    if len(df) != n_expected:
        problems.append(f"{len(df)} rows, expected {n_expected}")
    if df["truncated"].any():
        problems.append("truncated rows present (raise max_steps, do not filter, §3.7)")
    if not df["run_id"].is_unique:
        problems.append("run_id is not unique")
    fixed = {"regime": "STUDY", "condition": "none", "b": 0.0, "L": PILOT_L, "beta": 0.8,
             "f_treat": 0.2, "tau": 1.0, "diagonal_factor": True, "ignition": "random_cell"}
    for col, want in fixed.items():
        if not (df[col] == want).all():
            problems.append(f"{col} is not {want!r} on every row")
    s = df[df["settlement"]]
    if s["settlement_reached"].isna().any():
        problems.append("settlement_reached is null on a settlement run")
    if df.loc[~df["settlement"], "settlement_reached"].notna().any():
        problems.append("settlement_reached is non-null on a no-settlement run")
    if df["reached_edge"].isna().any() or df["spanned"].notna().any():
        problems.append("reached_edge/spanned nullness is wrong for random_cell ignition (§3.5)")
    if problems:
        raise AssertionError("Settlement pilot frame failed: " + "; ".join(problems))


def pilot_decision(df: pd.DataFrame) -> dict:
    """Apply the §10.2 O1 decision rule to the pilot frame.

    Returns `{"table": DataFrame, "chosen": int | None}`. `table` has one row
    per (side, kappa): baseline `p_reach` over the settlement runs, its Wilson
    95% interval, mean `n_occupied`, and `drift`, the relative difference from
    the no-settlement runs at the same kappa (hence the same p).

    Rule 1 takes the smallest side whose `p_reach` is in `P_REACH_BAND`; rule 2
    rejects a side whose `|drift|` exceeds `N_OCC_TOLERANCE`. Both are read at
    *both* kappa: Experiment 1 runs at both, so a side that only works at one
    would discriminate geometries at one wind strength and saturate at the
    other (DEC-037). `chosen` is None when no side passes, which is branch 3 of
    the rule, not a licence to relax branches 1 and 2.
    """
    assert_not_truncated(df)
    rows = []
    for kappa in PILOT_KAPPAS:
        k = df[df["kappa"] == kappa]
        control = k[~k["settlement"]]["n_occupied"].mean()
        for side in PILOT_SIDES:
            sub = k[k["settlement"] & (k["geometry_params"] == _dumps({"settlement_side": side}))]
            if sub.empty:
                raise ValueError(f"pilot frame has no rows for side={side}, kappa={kappa:g}")
            n = len(sub)
            hits = int(sub["settlement_reached"].astype(bool).sum())
            phat = hits / n
            z = 1.96
            centre = (phat + z * z / (2 * n)) / (1 + z * z / n)
            half = z * math.sqrt(phat * (1 - phat) / n + z * z / (4 * n * n)) / (1 + z * z / n)
            rows.append({
                "side": side, "kappa": kappa, "n": n, "p_reach": phat,
                "ci_lo": centre - half, "ci_hi": centre + half,
                "n_occupied": sub["n_occupied"].mean(),
                "control_n_occupied": control,
                "drift": sub["n_occupied"].mean() / control - 1.0,
            })
    table = pd.DataFrame(rows)
    lo, hi = P_REACH_BAND
    table["in_band"] = table["p_reach"].between(lo, hi)
    table["drift_ok"] = table["drift"].abs() <= N_OCC_TOLERANCE
    ok = table.groupby("side")[["in_band", "drift_ok"]].all().all(axis=1)
    passing = [s for s in PILOT_SIDES if ok[s]]
    return {"table": table, "chosen": min(passing) if passing else None}


def run_pilot(out_path: str = PILOT_PATH, pc_path: str = PC_PATH,
              replicates: int = PILOT_R) -> pd.DataFrame:
    """Run the settlement pilot and report the §10.2 O1 decision.

    Writes `out_path`, then prints baseline `P(settlement_reached)` and the
    `n_occupied` drift per side and kappa, and which side the rule selects. It
    edits nothing: `SETTLEMENT_SIDE` and `project-context.md` §3.6 / §10.2 are
    changed by hand from this output, in the same PR (SPEC-12).
    """
    cfgs, p_rels = pilot_grid(pc_path, replicates)
    df = run_configs(cfgs, out_path, p_rel=p_rels)
    _check_pilot_frame(df, len(cfgs))

    res = pilot_decision(df)
    t = res["table"]
    print("Settlement pilot (L=256, b=0, condition=none, p_rel=+0.05, R="
          f"{replicates}); band {P_REACH_BAND}, drift tolerance {N_OCC_TOLERANCE:.0%}")
    for kappa in PILOT_KAPPAS:
        sub = t[t["kappa"] == kappa]
        p = float(df[(df["kappa"] == kappa) & df["settlement"]]["p"].iloc[0])
        print(f"  kappa={kappa:g}  p={p:.4f}  control n_occupied={sub['control_n_occupied'].iloc[0]:.1f}")
        for _, r in sub.iterrows():
            print(f"    side={int(r['side']):>2}  P(reached)={r['p_reach']:.3f} "
                  f"[{r['ci_lo']:.3f}, {r['ci_hi']:.3f}] {'in band' if r['in_band'] else 'OUT'}  "
                  f"drift={r['drift']:+.4%} {'ok' if r['drift_ok'] else 'REJECT'}")
    if res["chosen"] is None:
        print("No side satisfies both rules: branch 3, switch the SQ4 metric to "
              "settlement_reached_step (§10.2 O1).")
    else:
        print(f"Rule selects SETTLEMENT_SIDE = {res['chosen']}")
    return df


# --- Coarse Experiment 1 (SPEC-12, project-context.md §6.2) -------------------

EXP1C_PATH = "results/exp1_coarse.parquet"
EXP1C_L = 256
EXP1C_KAPPAS = (0.0, 2.0)
EXP1C_P_REL = (-0.05, 0.0, 0.05)
EXP1C_P_ABS = 0.70
EXP1C_B = (0.10, 0.15, 0.20, 0.30)  # plus b=0, run as `none` only (§6.2)
EXP1C_R = 20  # of Experiment 1's R=200
EXP1C_SEED_BASE = 3_000_000
EXP1C_LEVELS = (
    [("random", {})]
    + [("patches", {"k": k}) for k in (4, 8, 16)]
    + [("strips_perp", {"w": w}) for w in (4, 8, 16)]
    + [("strips_para", {"w": w}) for w in (4, 8, 16)]
    + [("buffer", {})]
)  # the 11 treated condition-levels; `none` is the twelfth, at b=0 only


def exp1_coarse_grid(pc_path: str = PC_PATH, side: int = SETTLEMENT_SIDE,
                     replicates: int = EXP1C_R) -> tuple[list[Config], list[float | None]]:
    """The coarse Experiment 1 grid: `(configs, p_rel)`, parallel, for `run_configs`.

    Reduces replicates (R=20) and the `b` grid, and keeps every condition-level
    (SPEC-12). Every config has `settlement=True` and writes `settlement_side`
    explicitly (§3.6, DEC-015), set to the frozen `SETTLEMENT_SIDE`. `p` is
    `p_c(kappa) + p_rel` resolved against Experiment 0b, plus the absolute
    `p=0.70` with `p_rel` null. `none` appears at `b=0` only; the other 11
    levels at every `b` above 0.

    Seed is the run's position in this grid (kappa, p, condition-level, b,
    replicate).
    """
    if not 1 <= replicates <= EXP1C_R:
        raise ValueError(f"replicates must be in 1..{EXP1C_R}, got {replicates}")
    points = [("none", {}, 0.0)] + [(c, prm, b) for c, prm in EXP1C_LEVELS for b in EXP1C_B]
    cfgs, p_rels = [], []
    pos = 0
    for kappa in EXP1C_KAPPAS:
        ps = [(resolve_p(rel, regime="STUDY", condition="none", b=0.0, kappa=kappa, path=pc_path), rel)
              for rel in EXP1C_P_REL] + [(EXP1C_P_ABS, None)]
        for p, rel in ps:
            for condition, prm, b in points:
                for r in range(replicates):
                    cfgs.append(Config(
                        L=EXP1C_L, regime="STUDY", p=p, f_treat=0.2,
                        beta=0.8, kappa=kappa, phi=0.0, tau=1, diagonal_factor=True,
                        condition=condition, b=b,
                        geometry_params={**prm, "settlement_side": side},
                        ignition="random_cell", settlement=True,
                        seed=EXP1C_SEED_BASE + pos * EXP1C_R + r,
                    ))
                    p_rels.append(rel)
                pos += 1
    return cfgs, p_rels


def _check_exp1c_frame(df: pd.DataFrame, n_expected: int) -> None:
    problems = []
    if len(df) != n_expected:
        problems.append(f"{len(df)} rows, expected {n_expected}")
    if df["truncated"].any():
        problems.append("truncated rows present (raise max_steps, do not filter, §3.7)")
    if not df["run_id"].is_unique:
        problems.append("run_id is not unique")
    fixed = {"regime": "STUDY", "L": EXP1C_L, "beta": 0.8, "f_treat": 0.2, "tau": 1.0,
             "diagonal_factor": True, "ignition": "random_cell", "settlement": True}
    for col, want in fixed.items():
        if not (df[col] == want).all():
            problems.append(f"{col} is not {want!r} on every row")
    if df["settlement_reached"].isna().any():
        problems.append("settlement_reached is null on a settlement run")
    if df["reached_edge"].isna().any() or df["spanned"].notna().any():
        problems.append("reached_edge/spanned nullness is wrong for random_cell ignition (§3.5)")
    if not ((df["condition"] == "none") == (df["b"] == 0.0)).all():
        problems.append("`none` must appear at b=0 and only there (§6.2)")
    if problems:
        raise AssertionError("Coarse Experiment 1 frame failed: " + "; ".join(problems))


def run_exp1_coarse(out_path: str = EXP1C_PATH, pc_path: str = PC_PATH,
                    side: int = SETTLEMENT_SIDE, replicates: int = EXP1C_R) -> pd.DataFrame:
    """Coarse Experiment 1: the reduced grid, to locate the interesting region.

    Runs after `run_pilot` has fixed `SETTLEMENT_SIDE`. A look at the data, not a
    result: SPEC-13 runs the full grid.
    """
    cfgs, p_rels = exp1_coarse_grid(pc_path, side, replicates)
    df = run_configs(cfgs, out_path, p_rel=p_rels)
    _check_exp1c_frame(df, len(cfgs))
    print(f"Coarse Experiment 1: {len(df)} rows in {out_path} (settlement_side={side}, "
          f"R={replicates}).")
    return df


# --- Experiment 1: geometry x budget (SPEC-13, §6.2) --------------------------

EXP1_PATH = "results/exp1.parquet"
EXP1_L = 256
EXP1_KAPPAS = (0.0, 2.0)
EXP1_P_REL = (-0.05, 0.0, 0.05)
EXP1_P_ABS = 0.70
EXP1_B = (0.05, 0.10, 0.15, 0.20, 0.25, 0.30)  # plus b=0, run as `none` only (§6.2)
EXP1_R = 200
EXP1_SEED_BASE = 4_000_000  # clear of 0 (<1M), 0b (1-1.13M), pilot (2M), 1-coarse (3M)
EXP1_LEVELS = EXP1C_LEVELS  # the 11 treated condition-levels; `none` is the twelfth


def exp1_points(pc_path: str = PC_PATH) -> list[tuple[float, float, float | None]]:
    """The eight (kappa, p, p_rel) operating points, `p` resolved at build time.

    `p_rel` resolves against the untreated STUDY threshold at the *matching*
    kappa (Experiment 0b, §6.1); `resolve_p` raises if that row is missing and
    nothing here catches it. The absolute p = 0.70 carries `p_rel = None`.
    """
    points = []
    for kappa in EXP1_KAPPAS:
        for rel in EXP1_P_REL:
            points.append((kappa, resolve_p(rel, regime="STUDY", condition="none", b=0.0,
                                            kappa=kappa, path=pc_path), rel))
        points.append((kappa, EXP1_P_ABS, None))
    return points


def exp1_grid(pc_path: str = PC_PATH, side: int = SETTLEMENT_SIDE,
              replicates: int = EXP1_R) -> tuple[list[Config], list[float | None]]:
    """The §6.2 Experiment 1 grid: `(configs, p_rel)`, parallel, for `run_configs`.

    2 kappa x 4 densities x (`none` at b=0 + 11 treated levels x 6 budgets)
    = 536 points, x R = 200 = 107,200 runs. `none` exists only at b=0 (§4.4).
    Every config writes `settlement_side` explicitly (§3.6, DEC-015).

    Seed is the run's position in the full grid (kappa, p, condition-level, b,
    replicate), so a staged run with fewer replicates resumes into the full one
    with the same `run_id`s.
    """
    if not 1 <= replicates <= EXP1_R:
        raise ValueError(f"replicates must be in 1..{EXP1_R}, got {replicates}")
    levels = [("none", {}, 0.0)] + [(c, prm, b) for c, prm in EXP1_LEVELS for b in EXP1_B]
    cfgs, p_rels = [], []
    pos = 0
    for kappa, p, rel in exp1_points(pc_path):
        for condition, prm, b in levels:
            for r in range(replicates):
                cfgs.append(_exp1_config(kappa, p, condition, prm, b, side,
                                         EXP1_SEED_BASE + pos * EXP1_R + r))
                p_rels.append(rel)
            pos += 1
    return cfgs, p_rels


def _exp1_config(kappa, p, condition, prm, b, side, seed) -> Config:
    """One Experiment 1 config; STUDY constants passed explicitly so a change to a
    default cannot silently change what this experiment measures."""
    return Config(
        L=EXP1_L, regime="STUDY", p=p, f_treat=0.2,
        beta=0.8, kappa=kappa, phi=0.0, tau=1, diagonal_factor=True,
        condition=condition, b=b, geometry_params={**prm, "settlement_side": side},
        ignition="random_cell", settlement=True, seed=seed,
    )


def _check_exp1_frame(df: pd.DataFrame, n_expected: int, pc_path: str = PC_PATH) -> None:
    """Every SPEC-13 acceptance check that holds row by row."""
    from src.geometries import budget_tolerance

    problems = []
    if len(df) != n_expected:
        problems.append(f"{len(df)} rows, expected {n_expected}")
    if df["truncated"].any():
        problems.append("truncated rows present (raise max_steps, do not filter, §3.7, I10)")
    if not df["run_id"].is_unique:
        problems.append("run_id is not unique")
    fixed = {"regime": "STUDY", "L": EXP1_L, "beta": 0.8, "f_treat": 0.2, "tau": 1.0,
             "phi": 0.0, "diagonal_factor": True, "ignition": "random_cell", "settlement": True}
    for col, want in fixed.items():
        if not (df[col] == want).all():
            problems.append(f"{col} is not {want!r} on every row")
    if df["spanned"].notna().any():
        problems.append("spanned is non-null (must be null under random_cell ignition, §3.5)")
    if df["reached_edge"].isna().any() or df["settlement_reached"].isna().any():
        problems.append("reached_edge or settlement_reached is null on some rows")
    if not ((df["condition"] == "none") == (df["b"] == 0.0)).all():
        problems.append("`none` must appear at b=0 and only there (§6.2)")
    treated = df[df["condition"] != "none"]
    per_level = treated.groupby(["condition", "geometry_params"])["b"].apply(lambda s: set(s.round(6)))
    if not all(bs == set(EXP1_B) for bs in per_level):
        problems.append("some condition-level is missing a budget")

    # p matches the resolved threshold + offset, at the matching kappa (§6.1, §2 O4)
    rel = df["p_rel"]
    if not df.loc[rel.isna(), "p"].eq(EXP1_P_ABS).all():
        problems.append("rows with null p_rel must have p = 0.70")
    for (kappa, off), sub in df[rel.notna()].groupby(["kappa", "p_rel"]):
        want = resolve_p(float(off), regime="STUDY", condition="none", b=0.0,
                         kappa=float(kappa), path=pc_path)
        if not np.allclose(sub["p"], want, rtol=0, atol=1e-12):
            problems.append(f"p != resolved threshold + offset at kappa={kappa}, p_rel={off}")

    # I7 over the frame: realised n_treated within the shared tolerance of round(b * n_occupied)
    nominal = (treated["b"] * treated["n_occupied"]).round().astype(int)
    slack = nominal.map(budget_tolerance)
    if ((treated["n_treated"] - nominal).abs() > slack).any():
        problems.append("n_treated outside the budget tolerance on some rows (I7)")
    if (df.loc[df["condition"] == "none", "n_treated"] != 0).any():
        problems.append("`none` rows with n_treated != 0")

    if problems:
        raise AssertionError("Experiment 1 frame failed: " + "; ".join(problems))


def run_exp1(out_path: str = EXP1_PATH, pc_path: str = PC_PATH, side: int = SETTLEMENT_SIDE,
             replicates: int = EXP1_R) -> pd.DataFrame:
    """Experiment 1: the full geometry x budget grid (SPEC-13).

    Resumable: rerunning skips every `run_id` already in `out_path`. Only the
    rows this call asked for are checked, so a staged run (fewer replicates)
    passes against its own size.
    """
    cfgs, p_rels = exp1_grid(pc_path, side, replicates)
    t0 = time.time()
    df = run_configs(cfgs, out_path, p_rel=p_rels)
    df = df[df["run_id"].isin({config_run_id(c) for c in cfgs})]
    _check_exp1_frame(df, len(cfgs), pc_path)
    print(f"Experiment 1: {len(df)} rows in {out_path} (R={replicates}, settlement_side={side}); "
          f"{df['wall_ms'].sum() / 3.6e6:.2f} core-hours, {time.time() - t0:.0f} s wall.")
    return df


# --- Illustrative scars (SPEC-13, DEC-009, DEC-013) ---------------------------

SCARS_PATH = "results/scars_illustrative.npz"
SCARS_P_REL = 0.05
SCAR_LEVELS = (  # (kappa, condition, params, b): replicate 0 of each Experiment 1 point
    (0.0, "none", {}, 0.0),
    (0.0, "strips_perp", {"w": 8}, 0.15),
    (2.0, "none", {}, 0.0),
    (2.0, "random", {}, 0.15),
    (2.0, "patches", {"k": 8}, 0.15),
    (2.0, "strips_perp", {"w": 8}, 0.15),
    (2.0, "strips_para", {"w": 8}, 0.15),
    (2.0, "buffer", {}, 0.15),
)


def scar_configs(pc_path: str = PC_PATH, side: int = SETTLEMENT_SIDE) -> list[Config]:
    """The named illustrative configs: replicate 0 of eight Experiment 1 points at
    p_c + 0.05 (DEC-039). Picked out of `exp1_grid`, so each scar is the scar of
    a row that exists in exp1.parquet, with the same `run_id`."""
    cfgs, p_rels = exp1_grid(pc_path, side, 1)
    by_key = {}
    for cfg, rel in zip(cfgs, p_rels):
        key = (cfg.kappa, rel, cfg.condition, _dumps({k: v for k, v in cfg.geometry_params.items()
                                                      if k != "settlement_side"}), cfg.b)
        by_key[key] = cfg
    out = []
    for kappa, condition, prm, b in SCAR_LEVELS:
        key = (kappa, SCARS_P_REL, condition, _dumps(prm), b)
        if key not in by_key:
            raise LookupError(f"illustrative scar {key} is not a point of the Experiment 1 grid")
        out.append(by_key[key])
    return out


def run_scars(out_path: str = SCARS_PATH, pc_path: str = PC_PATH,
              side: int = SETTLEMENT_SIDE) -> list[str]:
    """Capture the illustrative scars to one npz (the only scar file, workflow-rules §9).

    For each named config: `<run_id>__scar` (int8 final state), `<run_id>__ignition_step`
    (int32, step each cell first burned, -1 if never) and `<run_id>__config` (canonical
    JSON). `run_ids` lists them in order. `run_configs` has no scar option; this is the
    only path that stores grids (§4.1).
    """
    arrays = {}
    run_ids = []
    for cfg in scar_configs(pc_path, side):
        rid = config_run_id(cfg)
        res = run_fire(cfg, capture_scar=True)
        arrays[f"{rid}__scar"] = res.scar.astype(np.int8)
        arrays[f"{rid}__ignition_step"] = res.ignition_step.astype(np.int32)
        arrays[f"{rid}__config"] = np.array(_dumps(_canonical_config(cfg)))
        run_ids.append(rid)
    arrays["run_ids"] = np.array(run_ids)
    path = Path(out_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.stem + ".tmp.npz")
    np.savez_compressed(tmp, **arrays)
    os.replace(tmp, path)
    print(f"Illustrative scars: {len(run_ids)} configs -> {path} ({path.stat().st_size / 1e6:.2f} MB)")
    return run_ids


# --- Experiment 2: threshold shift (SPEC-14, §6.2, DEC-012) ------------------

EXP2_PATH = "results/exp2.parquet"
EXP2_PREPASS_PATH = "results/exp2_prepass.parquet"
EXP2_B = 0.15
EXP2_KAPPA = 0.0
EXP2_PHI = -math.pi / 2          # §6.1: wind (none here) and strips_perp bands across the spanning direction
EXP2_L = (128, 256, 512)
EXP2_R = 500
EXP2_HALF_WIDTH = 0.05           # declared sweep: centre +/- 0.05 ...
EXP2_P_STEP = 0.005              # ... at step 0.005 ...
EXP2_N_P = 21                    # ... = 21 points per condition (SPEC-14 acceptance)
EXP2_PREPASS_L = 128
EXP2_PREPASS_R = 100
EXP2_PREPASS_P = tuple(round(0.40 + 0.01 * i, 2) for i in range(61))  # 0.40 .. 1.00
EXP2_SEED_BASE = 5_000_000       # pre-pass from here, sweep from +1,000,000; clear of Exp 1 (4.0-4.11M)
EXP2_SWEEP_SEED_OFFSET = 1_000_000
EXP2_FAMILIES = ("patches", "strips_perp")
EXP2_SELECT_P_REL = 0.05         # the §6.2 selection cell: b=0.15, p_rel=+0.05, kappa=0


def exp2_selection(exp1_path: str = EXP1_PATH) -> dict[str, dict]:
    """Apply the §6.2 selection rule (DEC-012, recorded in DEC-039 before Exp 1 ran).

    Among each family's three levels, the lowest mean `burned_fraction` in
    Experiment 1 at b=0.15, p_rel=+0.05, kappa=0. Returns
    {family: {"params": {...}, "means": {label: mean}}} so the numbers behind
    the choice can be quoted.
    """
    path = Path(exp1_path)
    if not path.exists():
        raise FileNotFoundError(f"{path} does not exist; run Experiment 1 (SPEC-13) first")
    df = pd.read_parquet(path, columns=["condition", "geometry_params", "b", "kappa", "p_rel",
                                        "burned_fraction"])
    cell = df[(df["b"] == EXP2_B) & (df["kappa"] == EXP2_KAPPA)
              & np.isclose(df["p_rel"].fillna(np.inf), EXP2_SELECT_P_REL)]
    out = {}
    for family in EXP2_FAMILIES:
        sub = cell[cell["condition"] == family]
        means = sub.groupby("geometry_params")["burned_fraction"].mean()
        if len(means) != 3:
            raise LookupError(f"Experiment 1 has {len(means)} {family} levels in the selection cell, expected 3")
        best = means.idxmin()
        prm = {k: v for k, v in json.loads(best).items() if k != "settlement_side"}
        labels = {_dumps({k: v for k, v in json.loads(g).items() if k != "settlement_side"}): float(m)
                  for g, m in means.items()}
        out[family] = {"params": prm, "means": labels}
    return out


def exp2_levels(exp1_path: str = EXP1_PATH) -> list[tuple[str, dict]]:
    """The three measured conditions: random, patches(k*), strips_perp(w*). No `none` arm:
    the untreated reference is Experiment 0b's kappa=0 row (SPEC-14 scope)."""
    sel = exp2_selection(exp1_path)
    return [("random", {})] + [(f, sel[f]["params"]) for f in EXP2_FAMILIES]


def _exp2_config(L: int, p: float, condition: str, prm: dict, seed: int) -> Config:
    return Config(
        L=L, regime="STUDY", p=p, f_treat=0.2,
        beta=0.8, kappa=EXP2_KAPPA, phi=EXP2_PHI, tau=1, diagonal_factor=True,
        condition=condition, b=EXP2_B, geometry_params=dict(prm),
        ignition="edge", settlement=False, seed=seed,
    )


def exp2_prepass_grid(levels: list[tuple[str, dict]], replicates: int = EXP2_PREPASS_R) -> list[Config]:
    """L=128, p in [0.40, 1.00] step 0.01, per condition: locates each centre (DEC-040).
    The range runs to p=1 because a strip layout's threshold can sit far above the
    untreated one, which is the effect this experiment exists to measure."""
    if not 1 <= replicates <= EXP2_PREPASS_R:
        raise ValueError(f"replicates must be in 1..{EXP2_PREPASS_R}, got {replicates}")
    n_p = len(EXP2_PREPASS_P)
    return [
        _exp2_config(EXP2_PREPASS_L, p, cond, prm, EXP2_SEED_BASE + (i_c * n_p + i_p) * EXP2_PREPASS_R + r)
        for i_c, (cond, prm) in enumerate(levels)
        for i_p, p in enumerate(EXP2_PREPASS_P)
        for r in range(replicates)
    ]


def exp2_centres(prepass: pd.DataFrame, levels: list[tuple[str, dict]]) -> dict[str, float]:
    """Each condition's sweep centre: the smallest pre-pass p with P(span) >= 0.5, to the
    nearest 0.005, the Experiment 0b rule (SPEC-19). Raises if not bracketed, or if the
    sweep would run past p = 1."""
    assert_not_truncated(prepass)
    centres = {}
    for cond, _ in levels:
        sub = prepass[prepass["condition"] == cond]
        if sub.empty or sub["spanned"].isna().any():
            raise ValueError(f"pre-pass has no usable rows for {cond!r}")
        frac = sub.assign(hit=sub["spanned"].astype(bool)).groupby(sub["p"].round(6))["hit"].mean().sort_index()
        above = frac[frac >= 0.5]
        if above.empty:
            raise ValueError(f"{cond}: P(span) never reaches 0.5 by p=1 (max {frac.max():.2f}). Raise a DEC.")
        first = float(above.index[0])
        if first <= float(frac.index[0]) + 1e-9:
            raise ValueError(f"{cond}: P(span) >= 0.5 already at p={first:.2f}; not bracketed. Raise a DEC.")
        centre = round(round(first / EXP2_P_STEP) * EXP2_P_STEP, 3)
        if centre + EXP2_HALF_WIDTH > 1.0 + 1e-9:
            raise ValueError(f"{cond}: centre {centre} puts the sweep past p=1. Raise a DEC.")
        centres[cond] = centre
    return centres


def exp2_p_values(centre: float) -> tuple[float, ...]:
    """The 21 declared sweep points: centre +/- 0.05 at step 0.005."""
    return tuple(round(centre + EXP2_P_STEP * (i - EXP2_N_P // 2), 3) for i in range(EXP2_N_P))


def exp2_grid(levels: list[tuple[str, dict]], centres: dict[str, float],
              sizes: Sequence[int] = EXP2_L, replicates: int = EXP2_R) -> list[Config]:
    """The §6.2 Experiment 2 sweep. Seed is the run's position in the full grid
    (condition, p, L, replicate), so a staged run resumes into the full one."""
    if not 1 <= replicates <= EXP2_R:
        raise ValueError(f"replicates must be in 1..{EXP2_R}, got {replicates}")
    unknown = [L for L in sizes if L not in EXP2_L]
    if unknown:
        raise ValueError(f"sizes {unknown} are not in the Experiment 2 grid {EXP2_L}")
    base0 = EXP2_SEED_BASE + EXP2_SWEEP_SEED_OFFSET
    cfgs = []
    for i_c, (cond, prm) in enumerate(levels):
        for i_p, p in enumerate(exp2_p_values(centres[cond])):
            for L in sorted(sizes):
                i_L = EXP2_L.index(L)
                base = base0 + (((i_c * EXP2_N_P + i_p) * len(EXP2_L)) + i_L) * EXP2_R
                cfgs.extend(_exp2_config(L, p, cond, prm, base + r) for r in range(replicates))
    return cfgs


def _check_exp2_frame(df: pd.DataFrame, n_expected: int, what: str) -> None:
    problems = []
    if len(df) != n_expected:
        problems.append(f"{len(df)} rows, expected {n_expected}")
    if df["truncated"].any():
        problems.append("truncated rows present (raise max_steps, do not filter, §3.7, I10)")
    if not df["run_id"].is_unique:
        problems.append("run_id is not unique")
    fixed = {"regime": "STUDY", "b": EXP2_B, "kappa": EXP2_KAPPA, "phi": EXP2_PHI, "beta": 0.8,
             "f_treat": 0.2, "tau": 1.0, "diagonal_factor": True, "ignition": "edge",
             "settlement": False}
    for col, want in fixed.items():
        if not (df[col] == want).all():
            problems.append(f"{col} is not {want!r} on every row")
    if (df["condition"] == "none").any():
        problems.append("a `none` row is present (the reference is Experiment 0b)")
    if df["reached_edge"].notna().any() or df["spanned"].isna().any():
        problems.append("reached_edge must be null and spanned non-null under edge ignition (§3.5)")
    if problems:
        raise AssertionError(f"Experiment 2 {what} frame failed: " + "; ".join(problems))


EXP2_SCALE_PATH = "results/exp2_scale.parquet"
EXP2_SCALE_COLUMNS = ["regime", "condition", "b", "kappa", "L", "p50", "p50_stderr", "n_per_point"]


def p50_rows(df: pd.DataFrame, condition: str) -> list[dict]:
    """Per-lattice-size 50% spanning points for one condition (DEC-041).

    The fuel density at which P(span) first reaches 1/2 on each L, by linear
    interpolation between the two sweep points that bracket it, after enforcing
    monotonicity in p (P(span) is monotone in p; the deviations are sampling
    noise at R=500). The standard error is propagated from the binomial error on
    the two bracketing points divided by the local slope.

    This is a descriptive per-L statistic, not an estimate of an infinite-lattice
    threshold. It exists because a condition whose P(span) curves do not cross
    across L has no single threshold to record, and the way it moves with L is
    itself the result (`strips_perp`, DEC-041).
    """
    rows = []
    for L, cell in df.groupby("L"):
        g = cell.groupby("p")["spanned"].agg(["mean", "size"]).sort_index()
        ps, frac, n = g.index.to_numpy(float), g["mean"].to_numpy(float), g["size"].to_numpy(float)
        mono = np.maximum.accumulate(frac)
        i = int(np.argmax(mono >= 0.5))
        if mono[i] < 0.5 or i == 0:
            raise ValueError(
                f"{condition} at L={L}: P(span) does not cross 1/2 inside the sweep "
                f"(range {mono[0]:.3f}..{mono[-1]:.3f}); cannot report a 50% point"
            )
        lo_p, hi_p, lo_f, hi_f = ps[i - 1], ps[i], mono[i - 1], mono[i]
        slope = (hi_f - lo_f) / (hi_p - lo_p)
        p50 = lo_p + (0.5 - lo_f) / slope
        se_f = math.sqrt(sum(f * (1 - f) / m for f, m in ((lo_f, n[i - 1]), (hi_f, n[i]))))
        rows.append({
            "regime": "STUDY", "condition": condition, "b": float(cell["b"].iloc[0]),
            "kappa": float(cell["kappa"].iloc[0]), "L": int(L),
            "p50": float(p50), "p50_stderr": float(se_f / slope),
            "n_per_point": int(n.min()),
        })
    return rows


def write_p50(rows, path: str = EXP2_SCALE_PATH) -> None:
    """Append per-L 50% points to `path`, append-only on (condition, b, kappa, L)."""
    if not rows:
        return
    new = pd.DataFrame(list(rows))[EXP2_SCALE_COLUMNS]
    out_path = Path(path)
    old = pd.read_parquet(out_path) if out_path.exists() else None
    key = lambda d: set(map(tuple, d[["regime", "condition", "b", "kappa", "L"]].to_numpy().tolist()))
    if old is not None:
        clash = key(old) & key(new)
        if clash:
            raise ValueError(f"duplicate per-L rows for {sorted(clash)} in {path}; nothing written")
        new = pd.concat([old, new], ignore_index=True)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = out_path.with_name(out_path.name + ".tmp")
    new.to_parquet(tmp, index=False)
    os.replace(tmp, out_path)


def run_exp2(exp1_path: str = EXP1_PATH, prepass_path: str = EXP2_PREPASS_PATH,
             out_path: str = EXP2_PATH, pc_path: str = PC_PATH, sizes: Sequence[int] = EXP2_L,
             replicates: int = EXP2_R, centres: dict[str, float] | None = None,
             scale_path: str = EXP2_SCALE_PATH) -> pd.DataFrame:
    """Experiment 2: selection, pre-pass, sweep, and per-condition STUDY thresholds.

    Writes the pre-pass, centres each condition on it (DEC-040), runs the sweep,
    then appends one `fss_crossing` and three `var_peak` rows per condition through
    `pc_rows` / `write_pc_estimates`. A staged run (fewer sizes or replicates)
    records no threshold. Every crossing must lie strictly inside its own range,
    and all three are checked before any is written. `centres` overrides the
    pre-pass, for re-centring a condition whose crossing fell outside its range.

    A condition whose P(span) curves have no L-independent crossing has no single
    threshold to record. Its `fss_crossing` row is omitted - so `resolve_p` refuses
    it rather than returning a number that does not exist - and its per-L 50%
    points go to `scale_path` instead (DEC-041).
    """
    levels = exp2_levels(exp1_path)
    print("Experiment 2 conditions: " + ", ".join(f"{c}{_dumps(p) if p else ''}" for c, p in levels))

    prepass = run_configs(exp2_prepass_grid(levels), prepass_path)
    _check_exp2_frame(prepass, len(levels) * len(EXP2_PREPASS_P) * EXP2_PREPASS_R, "pre-pass")
    centres = exp2_centres(prepass, levels) if centres is None else dict(centres)
    print("Experiment 2 sweep centres: " + ", ".join(f"{c}: {centres[c]:.3f}" for c, _ in levels))

    cfgs = exp2_grid(levels, centres, sizes, replicates)
    full = run_configs(cfgs, out_path)
    df = full[full["run_id"].isin({config_run_id(c) for c in cfgs})]
    _check_exp2_frame(df, len(cfgs), "sweep")

    if tuple(sorted(sizes)) != EXP2_L or replicates != EXP2_R:
        print(f"Experiment 2 staged run: {len(df)} rows; no p_c recorded (not the full grid).")
        return df

    rows, report, scale_rows = [], [], []
    for cond, _ in levels:
        sub = df[df["condition"] == cond]
        lo = round(centres[cond] - EXP2_HALF_WIDTH, 3)
        hi = round(centres[cond] + EXP2_HALF_WIDTH, 3)
        try:
            cond_rows = pc_rows(sub, cond, "STUDY")
        except ValueError as exc:
            # No L-independent crossing: the condition's threshold depends on the
            # lattice size, so there is no single p_c to record (DEC-041, option A).
            # Its per-L 50% points are written to `scale_path` instead, and no
            # `fss_crossing` row is written, so `resolve_p` correctly refuses it.
            if "no valid crossing" not in str(exc):
                raise
            scale_rows.extend(p50_rows(full[full["condition"] == cond], cond))
            report.append(f"{cond}: NO scale-free threshold; per-L 50% points "
                          "recorded instead (DEC-041)")
            continue
        crossing = next(r for r in cond_rows if r["method"] == "fss_crossing")
        if not lo < crossing["p_c"] < hi:
            raise AssertionError(
                f"{cond}: crossing p_c = {crossing['p_c']:.4f} is not strictly inside its sweep range "
                f"({lo}, {hi}). Re-centre with `centres=` and rerun that condition; do not extrapolate."
            )
        rows.extend(cond_rows)
        scale_rows.extend(p50_rows(full[full["condition"] == cond], cond))
        report.append(f"{cond}: centre {centres[cond]:.3f}, p_c = {crossing['p_c']:.4f} ± {crossing['p_c_stderr']:.4f}")

    if not rows:
        raise AssertionError("Experiment 2 recorded no threshold for any condition; nothing written")
    write_pc_estimates(rows, pc_path)
    write_p50(scale_rows, scale_path)
    print("Experiment 2: " + "; ".join(report))
    return df


# --- Experiment 2b: tail statistics (SPEC-15, §6.2, §10.2 O4) ----------------

EXP2_PATH = "results/exp2.parquet"        # written by Experiment 2 (SPEC-14)
EXP2B_PATH = "results/exp2b.parquet"
EXP2B_L = 256
EXP2B_B = 0.15
EXP2B_KAPPA = 0.0
EXP2B_PHI = -math.pi / 2                  # the orientation the thresholds were measured in (§6.1)
EXP2B_R = 10_000
EXP2B_R_RAISED = 50_000                   # the §10.2 O4 G2 escalation
EXP2B_SEED_BASE = 9_000_000               # clear of 0 (<1M), 0b (1-1.13M), pilot (2M), 1-coarse (3M)
EXP2B_FAMILIES = ("patches", "strips_perp")  # the levels Experiment 2 selected (DEC-012)


def exp2b_levels(exp2_path: str = EXP2_PATH) -> list[tuple[str, dict, float]]:
    """The four Experiment 2b conditions as (condition, geometry_params, b).

    `none` at b=0 and `random` at b=0.15 are fixed. The `patches` and
    `strips_perp` levels are read from Experiment 2's own rows, never
    re-selected here (SPEC-15 Behaviour): each family must appear at exactly one
    level at b=0.15 in `exp2_path`.
    """
    path = Path(exp2_path)
    if not path.exists():
        raise FileNotFoundError(
            f"{path} does not exist. Experiment 2b runs each treated condition at the threshold "
            "Experiment 2 measured and at the level it selected, so run Experiment 2 (SPEC-14) first."
        )
    exp2 = pd.read_parquet(path, columns=["condition", "b", "geometry_params"])
    levels = [("none", {}, 0.0), ("random", {}, EXP2B_B)]
    for family in EXP2B_FAMILIES:
        found = exp2.loc[(exp2["condition"] == family) & (exp2["b"] == EXP2B_B),
                         "geometry_params"].unique()
        if len(found) != 1:
            raise LookupError(
                f"{path} must hold exactly one {family!r} level at b={EXP2B_B}, found "
                f"{sorted(found) or 'none'} (DEC-012)"
            )
        prm = json.loads(found[0])
        prm.pop("settlement_side", None)   # Experiment 2 has no settlement; defensive only
        levels.append((family, prm, EXP2B_B))
    return levels


def exp2b_available_levels(exp2_path: str = EXP2_PATH, pc_path: str = PC_PATH
                           ) -> tuple[list[tuple[str, dict, float]], list[tuple[str, str]]]:
    """Split `exp2b_levels` into the conditions that have a measured threshold and
    those that do not, with the reason (DEC-042).

    Experiment 2b runs each condition at its own `fss_crossing` value. A condition
    whose P(span) curves have no L-independent crossing has no such row, so
    `resolve_p` raises and the condition cannot be run at "its threshold" — there
    is no single value to run it at (`strips_perp`, DEC-041). It is reported here
    rather than skipped quietly, and it is never substituted with another
    condition's threshold or with a per-L value.
    """
    runnable, dropped = [], []
    for condition, prm, b in exp2b_levels(exp2_path):
        try:
            resolve_p(0.0, regime="STUDY", condition=condition, b=b, kappa=EXP2B_KAPPA, path=pc_path)
        except (LookupError, FileNotFoundError) as exc:
            dropped.append((condition, type(exc).__name__))
            continue
        runnable.append((condition, prm, b))
    return runnable, dropped


def exp2b_grid(exp2_path: str = EXP2_PATH, pc_path: str = PC_PATH, replicates: int = EXP2B_R,
               conditions: Sequence[str] | None = None, size: int = EXP2B_L
               ) -> tuple[list[Config], list[float]]:
    """The Experiment 2b grid: `(configs, p_rel)`, parallel, for `run_configs`.

    Each condition runs at its own measured threshold, `resolve_p(0.0, ...)` on
    its `fss_crossing` row: Experiment 0b's `(STUDY, none, 0, 0)` for `none`,
    Experiment 2's `(STUDY, condition, 0.15, 0)` for the treated three. `p_rel`
    is 0.0 for every run: at the condition's own threshold, which §6.2 names
    as 2b's reference in place of the governing one (DEC-038).

    Seeds are laid out so condition i, replicate r has seed
    EXP2B_SEED_BASE + i * EXP2B_R_RAISED + r. A G2 escalation to 50,000
    replicates therefore *extends* the 10,000-run set with the same run_ids and
    resumes into the same file. `conditions` restricts the grid (the G2
    escalation narrows it); `size` exists for tests.
    """
    if not 1 <= replicates <= EXP2B_R_RAISED:
        raise ValueError(f"replicates must be in 1..{EXP2B_R_RAISED}, got {replicates}")
    levels, _ = exp2b_available_levels(exp2_path, pc_path)
    if not levels:
        raise LookupError("no Experiment 2b condition has a measured threshold; run Experiment 2 first")
    names = [c for c, _, _ in levels]
    if conditions is not None:
        unknown = [c for c in conditions if c not in names]
        if unknown:
            raise ValueError(f"unknown Experiment 2b conditions {unknown}; valid: {names}")
    all_names = [c for c, _, _ in exp2b_levels(exp2_path)]
    cfgs, p_rels = [], []
    for condition, prm, b in levels:
        i = all_names.index(condition)      # position in the full list, not the runnable one
        if conditions is not None and condition not in conditions:
            continue
        p = resolve_p(0.0, regime="STUDY", condition=condition, b=b, kappa=EXP2B_KAPPA, path=pc_path)
        for r in range(replicates):
            cfgs.append(Config(
                L=size, regime="STUDY", p=p, f_treat=0.2,
                beta=0.8, kappa=EXP2B_KAPPA, phi=EXP2B_PHI, tau=1, diagonal_factor=True,
                condition=condition, b=b, geometry_params=dict(prm),
                ignition="random_cell", settlement=False,
                seed=EXP2B_SEED_BASE + i * EXP2B_R_RAISED + r,
            ))
            p_rels.append(0.0)
    return cfgs, p_rels


def _check_exp2b_frame(df: pd.DataFrame, n_expected: int) -> None:
    problems = []
    if len(df) != n_expected:
        problems.append(f"{len(df)} rows, expected {n_expected}")
    if df["truncated"].any():
        problems.append("truncated rows present (raise max_steps, do not filter, §3.7, I10)")
    if not df["run_id"].is_unique:
        problems.append("run_id is not unique")
    fixed = {"regime": "STUDY", "beta": 0.8, "f_treat": 0.2, "tau": 1.0, "kappa": EXP2B_KAPPA,
             "phi": EXP2B_PHI, "diagonal_factor": True, "ignition": "random_cell",
             "settlement": False}
    for col, want in fixed.items():
        if not (df[col] == want).all():
            problems.append(f"{col} is not {want!r} on every row")
    if df["spanned"].notna().any() or df["reached_edge"].isna().any():
        problems.append("spanned/reached_edge nullness is wrong for random_cell ignition (§3.5)")
    if problems:
        raise AssertionError("Experiment 2b frame failed: " + "; ".join(problems))


def exp2b_fits(df: pd.DataFrame, replicates: int) -> list[dict]:
    """One tail fit per condition-level in `df` (rows of TAIL_COLUMNS).

    Burn size is `burned_cells`; the support is bounded by the lattice,
    `x_max = L*L` (DEC-038).
    """
    assert_not_truncated(df)
    rows = []
    for (condition, prm), sub in df.groupby(["condition", "geometry_params"], sort=False):
        L = int(sub["L"].iloc[0])
        fit = fit_tail(sub["burned_cells"].to_numpy(), x_max=L * L)
        rows.append({"experiment": "2b", "condition": condition, "geometry_params": prm,
                     "b": float(sub["b"].iloc[0]), "replicates": int(replicates),
                     "p": float(sub["p"].iloc[0]), "kappa": float(sub["kappa"].iloc[0]),
                     "L": L, **fit})
    return rows


def run_exp2b(exp2_path: str = EXP2_PATH, pc_path: str = PC_PATH, out_path: str = EXP2B_PATH,
              fits_path: str = TAIL_FITS_PATH, replicates: int = EXP2B_R,
              conditions: Sequence[str] | None = None, size: int = EXP2B_L) -> pd.DataFrame:
    """Experiment 2b: run the tail grid, fit each condition, report gate G2.

    Fits are recorded only for a full-size run at R = 10,000 (all four
    conditions) or R = 50,000 (the G2 escalation, any subset); any other
    replicate count or lattice size is a staged run that records nothing, as
    in `run_exp0`. Gate G2 is printed, not acted on: raising R is a team
    decision recorded in §10.2 O4 (SPEC-15 Behaviour). Returns the fits.
    """
    runnable, dropped = exp2b_available_levels(exp2_path, pc_path)
    for condition, why in dropped:
        print(f"Experiment 2b: {condition!r} has no measured threshold ({why}), so it is not run. "
              "Its tail is not fitted and no substitute p is used (DEC-041, DEC-042).")
    cfgs, p_rels = exp2b_grid(exp2_path, pc_path, replicates, conditions, size)
    df = run_configs(cfgs, out_path, p_rel=p_rels)
    df = df[df["run_id"].isin({config_run_id(c) for c in cfgs})]   # this request's rows only
    _check_exp2b_frame(df, len(cfgs))

    fits = pd.DataFrame(exp2b_fits(df, replicates))
    full = size == EXP2B_L and (
        (replicates == EXP2B_R and conditions is None) or replicates == EXP2B_R_RAISED)
    if full and conditions is None and len(runnable) < len(exp2b_levels(exp2_path)):
        print(f"Experiment 2b full run over the {len(runnable)} conditions with a threshold.")
    if full:
        write_tail_fits(fits, fits_path)
    else:
        print(f"Experiment 2b staged run (R={replicates}, L={size}): no fits recorded.")

    show = ["condition", "geometry_params", "p", "x_min", "n_tail", "alpha", "alpha_stderr",
            "cutoff", "cutoff_lo", "cutoff_hi", "decades_above_xmin",
            "ks_distance", "ks_critical", "fit_rejected"]
    print(fits[show].round(4).to_string(index=False))
    bad = fits[fits["fit_rejected"] > 0]
    if not bad.empty:
        print(f"\nGOODNESS OF FIT: the power-law-with-cutoff model is REJECTED for "
              f"{', '.join(bad['condition'])} (KS distance above its 5% critical value). "
              "The fitted exponent and cutoff describe the data poorly and must not be "
              "reported as if they did; see DEC-043.")
    gate = g2_gate(fits)
    print("Gate G2 (>= 2 decades of tail above x_min, §10.2 O4):")
    print(gate.to_string(index=False))
    if not gate["passes"].all():
        print("G2 fails for some conditions. Decide whether to rerun at R=50,000 "
              "(run_exp2b(replicates=50_000, conditions=[...])) and record it in §10.2 O4.")
    return fits


# --- Experiment 3: wind interaction (SPEC-16, §6.2) ---------------------------

EXP3_PATH = "results/exp3.parquet"
EXP3_L = 256
EXP3_KAPPAS = (0.0, 1.0, 2.0, 4.0)
EXP3_B = 0.15
EXP3_P_REL = 0.05
EXP3_R = 200
EXP3_PHI = 0.0
EXP3_SEED_BASE = 6_000_000      # clear of Exp 1 (4.0-4.11M) and Exp 2 (5.0-6.0M is 2's; see note)


def exp3_levels(exp1_path: str = EXP1_PATH) -> list[tuple[str, dict, float]]:
    """The seven treated conditions of §6.2 Experiment 3, plus `none` at b=0.

    Seven is the roadmap's condition list (§4.4) minus the untreated reference:
    `random`, `patches` at all three scales, `strips_perp`, `strips_para` and
    `buffer`. The strip widths are the level Experiment 2 selected, so the
    orientation contrast is measured at the width the rest of the project uses
    (DEC-044). `none` at b=0 is carried as the untreated reference at every
    kappa, which the §11 efficiency metric divides against.
    """
    w = exp2_selection(exp1_path)["strips_perp"]["params"]
    levels = [("random", {}, EXP3_B)]
    levels += [("patches", {"k": k}, EXP3_B) for k in (4, 8, 16)]
    levels += [("strips_perp", dict(w), EXP3_B), ("strips_para", dict(w), EXP3_B)]
    levels += [("buffer", {}, EXP3_B)]
    assert len(levels) == 7, len(levels)
    return [("none", {}, 0.0)] + levels


def exp3_grid(exp1_path: str = EXP1_PATH, pc_path: str = PC_PATH,
              side: int = SETTLEMENT_SIDE, replicates: int = EXP3_R
              ) -> tuple[list[Config], list[float]]:
    """The §6.2 Experiment 3 grid: `(configs, p_rel)`, parallel, for `run_configs`.

    4 kappa x 8 arms x R = 200 = 6,400 runs. `p` resolves to that kappa's own
    untreated threshold + 0.05 — four different thresholds, not one, which the
    spec names as the most likely error here (§6.1, §2 O4).
    """
    if not 1 <= replicates <= EXP3_R:
        raise ValueError(f"replicates must be in 1..{EXP3_R}, got {replicates}")
    levels = exp3_levels(exp1_path)
    cfgs, p_rels, pos = [], [], 0
    for kappa in EXP3_KAPPAS:
        p = resolve_p(EXP3_P_REL, regime="STUDY", condition="none", b=0.0, kappa=kappa, path=pc_path)
        for condition, prm, b in levels:
            for r in range(replicates):
                cfgs.append(Config(
                    L=EXP3_L, regime="STUDY", p=p, f_treat=0.2,
                    beta=0.8, kappa=kappa, phi=EXP3_PHI, tau=1, diagonal_factor=True,
                    condition=condition, b=b, geometry_params={**prm, "settlement_side": side},
                    ignition="random_cell", settlement=True,
                    seed=EXP3_SEED_BASE + pos * EXP3_R + r,
                ))
                p_rels.append(EXP3_P_REL)
            pos += 1
    return cfgs, p_rels


def _check_exp3_frame(df: pd.DataFrame, n_expected: int, pc_path: str = PC_PATH) -> None:
    problems = []
    if len(df) != n_expected:
        problems.append(f"{len(df)} rows, expected {n_expected}")
    if df["truncated"].any():
        problems.append("truncated rows present (§3.7, I10)")
    if not df["run_id"].is_unique:
        problems.append("run_id is not unique")
    fixed = {"regime": "STUDY", "L": EXP3_L, "beta": 0.8, "f_treat": 0.2, "tau": 1.0,
             "phi": EXP3_PHI, "diagonal_factor": True, "ignition": "random_cell", "settlement": True}
    for col, want in fixed.items():
        if not (df[col] == want).all():
            problems.append(f"{col} is not {want!r} on every row")
    if df["settlement_reached"].isna().any():
        problems.append("settlement_reached is null on some rows")
    if set(df["kappa"]) != set(EXP3_KAPPAS):
        problems.append(f"kappa values are {sorted(set(df['kappa']))}, expected {list(EXP3_KAPPAS)}")
    # each kappa's p is that kappa's own threshold + 0.05, never another kappa's
    for kappa, sub in df.groupby("kappa"):
        want = resolve_p(EXP3_P_REL, regime="STUDY", condition="none", b=0.0,
                         kappa=float(kappa), path=pc_path)
        if not np.allclose(sub["p"], want, rtol=0, atol=1e-12):
            problems.append(f"p at kappa={kappa} is not that kappa's threshold + {EXP3_P_REL}")
    treated = df[df["condition"] != "none"]
    if not (treated["b"] == EXP3_B).all():
        problems.append(f"a treated row is not at b={EXP3_B}")
    # seven treated *levels*: patches appears three times under one condition name
    levels_per_kappa = treated.groupby("kappa").apply(
        lambda g: g.groupby(["condition", "geometry_params"]).ngroups, include_groups=False)
    if levels_per_kappa.min() != 7:
        problems.append(f"a kappa arm has {levels_per_kappa.min()} treated levels, expected 7")
    if problems:
        raise AssertionError("Experiment 3 frame failed: " + "; ".join(problems))


def run_exp3(exp1_path: str = EXP1_PATH, out_path: str = EXP3_PATH, pc_path: str = PC_PATH,
             side: int = SETTLEMENT_SIDE, replicates: int = EXP3_R) -> pd.DataFrame:
    """Experiment 3: is the ranking of treatment arrangements wind-dependent (SQ1)."""
    cfgs, p_rels = exp3_grid(exp1_path, pc_path, side, replicates)
    df = run_configs(cfgs, out_path, p_rel=p_rels)
    df = df[df["run_id"].isin({config_run_id(c) for c in cfgs})]
    _check_exp3_frame(df, len(cfgs), pc_path)
    print(f"Experiment 3: {len(df)} rows in {out_path} "
          f"({len(EXP3_KAPPAS)} kappa x {len(exp3_levels(exp1_path))} arms, R={replicates}).")
    return df


# --- Experiment 4: sensitivity (SPEC-16, §6.2, DEC-011) -----------------------

EXP4_PATH = "results/exp4.parquet"
EXP4_L = 256
EXP4_KAPPA = 2.0
EXP4_P_REL = 0.05               # resolved once, then held fixed; rows carry p_rel null
EXP4_F_TREAT = (0.0, 0.2, 0.4)
EXP4_BETA = (0.7, 0.8, 0.9)
EXP4_B = 0.15
EXP4_R = 200
EXP4_SEED_BASE = 7_000_000


def exp4_levels(exp1_path: str = EXP1_PATH) -> list[tuple[str, dict, float]]:
    """The reduced condition set: the untreated reference and one level of each
    geometry family that the primary analysis uses (DEC-044). Deliberately
    smaller than Experiment 3 — this is a sensitivity check, not a second main
    experiment (SPEC-16 Behaviour)."""
    sel = exp2_selection(exp1_path)
    return [("none", {}, 0.0), ("random", {}, EXP4_B),
            ("patches", dict(sel["patches"]["params"]), EXP4_B),
            ("strips_perp", dict(sel["strips_perp"]["params"]), EXP4_B),
            ("buffer", {}, EXP4_B)]


def exp4_grid(exp1_path: str = EXP1_PATH, pc_path: str = PC_PATH,
              side: int = SETTLEMENT_SIDE, replicates: int = EXP4_R
              ) -> tuple[list[Config], list[None]]:
    """The §6.2 Experiment 4 grid: 3 f_treat x 3 beta x 5 conditions x R = 9,000 runs.

    One **absolute** `p`, the kappa=2 Experiment 0b threshold + 0.05, resolved
    once and held fixed across every cell, with `p_rel` null on every row
    (§6.2, DEC-011): the check asks how outcomes move when beta changes on the
    *same* landscape, so it must not re-centre per beta.
    """
    if not 1 <= replicates <= EXP4_R:
        raise ValueError(f"replicates must be in 1..{EXP4_R}, got {replicates}")
    p = resolve_p(EXP4_P_REL, regime="STUDY", condition="none", b=0.0,
                  kappa=EXP4_KAPPA, path=pc_path)
    levels = exp4_levels(exp1_path)
    cfgs, pos = [], 0
    for f_treat in EXP4_F_TREAT:
        for beta in EXP4_BETA:
            for condition, prm, b in levels:
                for r in range(replicates):
                    cfgs.append(Config(
                        L=EXP4_L, regime="STUDY", p=p, f_treat=f_treat,
                        beta=beta, kappa=EXP4_KAPPA, phi=0.0, tau=1, diagonal_factor=True,
                        condition=condition, b=b,
                        geometry_params={**prm, "settlement_side": side},
                        ignition="random_cell", settlement=True,
                        seed=EXP4_SEED_BASE + pos * EXP4_R + r,
                    ))
                pos += 1
    return cfgs, [None] * len(cfgs)


def _check_exp4_frame(df: pd.DataFrame, n_expected: int, pc_path: str = PC_PATH) -> None:
    problems = []
    if len(df) != n_expected:
        problems.append(f"{len(df)} rows, expected {n_expected}")
    if df["truncated"].any():
        problems.append("truncated rows present (§3.7, I10)")
    if not df["run_id"].is_unique:
        problems.append("run_id is not unique")
    if not (df["kappa"] == EXP4_KAPPA).all():
        problems.append(f"kappa is not {EXP4_KAPPA} on every row")
    if df["p_rel"].notna().any():
        problems.append("p_rel must be null on every row (DEC-011)")
    want = resolve_p(EXP4_P_REL, regime="STUDY", condition="none", b=0.0,
                     kappa=EXP4_KAPPA, path=pc_path)
    if not np.allclose(df["p"], want, rtol=0, atol=1e-12):
        problems.append(f"p is not the single absolute value {want:.4f} on every row")
    if set(df["f_treat"].round(6)) != set(EXP4_F_TREAT):
        problems.append(f"f_treat values are {sorted(set(df['f_treat']))}")
    if set(df["beta"].round(6)) != set(EXP4_BETA):
        problems.append(f"beta values are {sorted(set(df['beta']))}")
    cells = df.groupby(["f_treat", "beta"])["condition"].nunique()
    if len(cells) != len(EXP4_F_TREAT) * len(EXP4_BETA) or cells.min() < 5:
        problems.append("the f_treat x beta cross is not complete over the condition set")
    if df["settlement_reached"].isna().any():
        problems.append("settlement_reached is null on some rows")
    if problems:
        raise AssertionError("Experiment 4 frame failed: " + "; ".join(problems))


def run_exp4(exp1_path: str = EXP1_PATH, out_path: str = EXP4_PATH, pc_path: str = PC_PATH,
             side: int = SETTLEMENT_SIDE, replicates: int = EXP4_R) -> pd.DataFrame:
    """Experiment 4: do the conclusions survive the fixed parameter choices."""
    cfgs, p_rels = exp4_grid(exp1_path, pc_path, side, replicates)
    df = run_configs(cfgs, out_path, p_rel=p_rels)
    df = df[df["run_id"].isin({config_run_id(c) for c in cfgs})]
    _check_exp4_frame(df, len(cfgs), pc_path)
    print(f"Experiment 4: {len(df)} rows in {out_path} "
          f"(f_treat x beta x {len(exp4_levels(exp1_path))} conditions, R={replicates}).")
    return df


# --- I11: lattice frame invariance (SPEC-16, §7 I11, §10.1 D3) ----------------

I11_PATH = "results/i11_frame.parquet"
I11_PHIS = (0.0, math.pi / 4)
I11_KAPPA = 2.0
I11_B = 0.15
I11_P_REL = 0.05
I11_L = 256
I11_R = 200
I11_SEED_BASE = 8_000_000


def i11_grid(exp1_path: str = EXP1_PATH, pc_path: str = PC_PATH,
             replicates: int = I11_R) -> tuple[list[Config], list[float]]:
    """`strips_perp` and `strips_para` at phi = 0 and phi = pi/4, R = 200 each.

    The geometry rotates with the wind because the strip generators build bands
    relative to `phi` (DEC-008), so no separate rotated condition is needed: the
    same two condition names at a different `phi` *are* the rotated geometry.
    """
    if not 1 <= replicates <= I11_R:
        raise ValueError(f"replicates must be in 1..{I11_R}, got {replicates}")
    w = exp2_selection(exp1_path)["strips_perp"]["params"]
    p = resolve_p(I11_P_REL, regime="STUDY", condition="none", b=0.0,
                  kappa=I11_KAPPA, path=pc_path)
    cfgs, pos = [], 0
    for phi in I11_PHIS:
        for condition in ("strips_perp", "strips_para"):
            for r in range(replicates):
                cfgs.append(Config(
                    L=I11_L, regime="STUDY", p=p, f_treat=0.2,
                    beta=0.8, kappa=I11_KAPPA, phi=phi, tau=1, diagonal_factor=True,
                    condition=condition, b=I11_B, geometry_params=dict(w),
                    ignition="random_cell", settlement=False,
                    seed=I11_SEED_BASE + pos * I11_R + r,
                ))
            pos += 1
    return cfgs, [I11_P_REL] * len(cfgs)


def i11_gaps(df: pd.DataFrame) -> pd.DataFrame:
    """The `strips_perp` − `strips_para` gap in mean burned fraction at each phi,
    with a standard error, and whether the two 95% intervals overlap.

    Reports the magnitude either way (SPEC-16 Behaviour): a pass is one line in
    Methods, a fail is a measured lattice artefact for Limitations.
    """
    rows = []
    for phi, sub in df.groupby("phi"):
        stats = sub.groupby("condition")["burned_fraction"].agg(["mean", "sem", "size"])
        gap = float(stats.loc["strips_perp", "mean"] - stats.loc["strips_para", "mean"])
        se = float(math.hypot(stats.loc["strips_perp", "sem"], stats.loc["strips_para", "sem"]))
        rows.append({"phi": float(phi), "gap": gap, "gap_stderr": se,
                     "ci_lo": gap - 1.96 * se, "ci_hi": gap + 1.96 * se,
                     "n_per_condition": int(stats["size"].min())})
    out = pd.DataFrame(rows).sort_values("phi").reset_index(drop=True)
    a, b = out.iloc[0], out.iloc[1]
    out.attrs["overlap"] = bool(a["ci_lo"] <= b["ci_hi"] and b["ci_lo"] <= a["ci_hi"])
    out.attrs["difference"] = float(a["gap"] - b["gap"])
    out.attrs["difference_stderr"] = float(math.hypot(a["gap_stderr"], b["gap_stderr"]))
    return out


def run_i11(exp1_path: str = EXP1_PATH, out_path: str = I11_PATH, pc_path: str = PC_PATH,
            replicates: int = I11_R) -> pd.DataFrame:
    cfgs, p_rels = i11_grid(exp1_path, pc_path, replicates)
    df = run_configs(cfgs, out_path, p_rel=p_rels)
    df = df[df["run_id"].isin({config_run_id(c) for c in cfgs})]
    assert_not_truncated(df)
    gaps = i11_gaps(df)
    print(f"I11 frame invariance ({len(df)} rows in {out_path}):")
    print(gaps.round(5).to_string(index=False))
    print(f"  difference between the two gaps: {gaps.attrs['difference']:+.5f} "
          f"+/- {gaps.attrs['difference_stderr']:.5f}; "
          f"95% intervals {'overlap -> frame invariance holds' if gaps.attrs['overlap'] else 'do NOT overlap -> measured lattice artefact'}")
    return df
