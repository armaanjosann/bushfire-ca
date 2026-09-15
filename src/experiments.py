"""Experiment entry points, dispatched by run.py (project-context.md §4.5).

Config grids, the multiprocessing runner and the parquet writers land in
SPEC-05. Each experiment's own body lands in the spec named below.
"""


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
