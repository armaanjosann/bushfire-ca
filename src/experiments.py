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

from src.model import Config, RunResult, run_fire

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


def run_exp0():
    raise NotImplementedError("Experiment 0 (percolation validation) lands in SPEC-07")


def run_exp1():
    raise NotImplementedError("Experiment 1 (geometry x budget) lands in SPEC-13")


def run_exp2():
    raise NotImplementedError("Experiment 2 (threshold shift) lands in SPEC-14")


def run_exp2b():
    raise NotImplementedError("Experiment 2b (tail statistics) lands in SPEC-15")


def run_exp3():
    raise NotImplementedError("Experiment 3 (wind interaction) lands in SPEC-16")


def run_exp4():
    raise NotImplementedError("Experiment 4 (sensitivity) lands in SPEC-16")
