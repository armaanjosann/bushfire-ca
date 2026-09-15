"""Invariants I1-I11 (project-context.md §7).

Each is a permanently-failing placeholder until the spec named in its reason
implements it, so an unowned invariant shows up as a failing test rather than
an absence (SPEC-01).
"""

import pytest


@pytest.mark.xfail(reason="I1 percolation limit lands in SPEC-07", strict=False)
def test_i1():
    raise NotImplementedError


@pytest.mark.xfail(reason="I2 determinism lands in SPEC-03", strict=False)
def test_i2():
    raise NotImplementedError


@pytest.mark.xfail(reason="I3 deterministic front shape lands in SPEC-03", strict=False)
def test_i3():
    raise NotImplementedError


@pytest.mark.xfail(reason="I4 isotropy lands in SPEC-04", strict=False)
def test_i4():
    raise NotImplementedError


@pytest.mark.xfail(reason="I5 wind monotonicity lands in SPEC-04", strict=False)
def test_i5():
    raise NotImplementedError


@pytest.mark.xfail(reason="I6 null treatment lands in SPEC-09", strict=False)
def test_i6():
    raise NotImplementedError


@pytest.mark.xfail(reason="I7 budget parity lands in SPEC-09", strict=False)
def test_i7():
    raise NotImplementedError


@pytest.mark.xfail(reason="I8 treatment placement lands in SPEC-09", strict=False)
def test_i8():
    raise NotImplementedError


@pytest.mark.xfail(reason="I9 conservation lands in SPEC-03", strict=False)
def test_i9():
    raise NotImplementedError


@pytest.mark.xfail(reason="I10 no truncation lands in SPEC-06", strict=False)
def test_i10():
    raise NotImplementedError


@pytest.mark.xfail(reason="I11 lattice frame invariance lands in SPEC-16", strict=False)
def test_i11():
    raise NotImplementedError
