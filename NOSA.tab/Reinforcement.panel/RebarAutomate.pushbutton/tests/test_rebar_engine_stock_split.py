# -*- coding: utf-8 -*-
"""
Mocked-API tests for rebar_engine.split_rebar_by_stock_length — this
function had ZERO test coverage before this file, which is exactly how
a real, live bug survived undetected across every typology that uses it
(beams, walls, footings, floors all call it via their own stock-length-
split logic): a 12m bar split at an 8m stock length produced two FULL
8m segments (a 4m overlap) instead of the intended normative lap length
(confirmed live against a real wall in the user's own project).

Pure math, no live Revit session — same minimal XYZ/Line stub pattern
already used by test_column_rebar_phase3.py.
"""
from __future__ import absolute_import, print_function, unicode_literals
import math
import os
import sys

_EXT_LIB = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', 'lib'))
if _EXT_LIB not in sys.path:
    sys.path.insert(0, _EXT_LIB)
from tests_support import revit_stubs  # noqa: E402

_MM_PER_FT = 304.8


class XYZ(object):
    def __init__(self, x=0.0, y=0.0, z=0.0):
        self.X, self.Y, self.Z = x, y, z
    def __add__(self, o):
        return XYZ(self.X + o.X, self.Y + o.Y, self.Z + o.Z)
    def __sub__(self, o):
        return XYZ(self.X - o.X, self.Y - o.Y, self.Z - o.Z)
    def Multiply(self, s):
        return XYZ(self.X * s, self.Y * s, self.Z * s)
    def DotProduct(self, o):
        return self.X * o.X + self.Y * o.Y + self.Z * o.Z
    def CrossProduct(self, o):
        return XYZ(self.Y * o.Z - self.Z * o.Y,
                    self.Z * o.X - self.X * o.Z,
                    self.X * o.Y - self.Y * o.X)
    def GetLength(self):
        return math.sqrt(self.X ** 2 + self.Y ** 2 + self.Z ** 2)
    def Normalize(self):
        L = self.GetLength()
        if L == 0:
            return XYZ(0, 0, 0)
        return XYZ(self.X / L, self.Y / L, self.Z / L)
    def DistanceTo(self, o):
        return (self - o).GetLength()


class Line(object):
    def __init__(self, p0, p1):
        self._p0, self._p1 = p0, p1
    @staticmethod
    def CreateBound(p0, p1):
        return Line(p0, p1)
    def GetEndPoint(self, i):
        return self._p0 if i == 0 else self._p1
    def Evaluate(self, t, normalized=True):
        return self._p0 + (self._p1 - self._p0).Multiply(t)
    @property
    def Direction(self):
        return (self._p1 - self._p0).Normalize()
    @property
    def Length(self):
        return self._p0.DistanceTo(self._p1)


if 'Autodesk' not in sys.modules:
    XYZ.BasisX = XYZ(1.0, 0.0, 0.0)
    XYZ.BasisZ = XYZ(0.0, 0.0, 1.0)
    revit_stubs.install_revit_stubs(db_attrs=dict(XYZ=XYZ, Line=Line), structure_attrs={})

revit_stubs.install_system_stubs(full_tree=True, only_if_missing=True)

_lib = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'lib'))
if _lib not in sys.path:
    sys.path.insert(0, _lib)

import rebar_engine  # noqa: E402


def _make_bar(length_mm):
    return Line.CreateBound(XYZ(0.0, 0.0, 0.0), XYZ(0.0, 0.0, length_mm / _MM_PER_FT))


def test_bar_within_stock_length_is_not_split():
    bar = _make_bar(7000.0)
    segs = rebar_engine.split_rebar_by_stock_length(bar, 8000.0, 480.0)
    assert len(segs) == 1
    assert abs(segs[0].length_mm - 7000.0) < 0.5
    assert segs[0].has_start_lap is False and segs[0].has_end_lap is False


def test_12m_bar_at_8m_stock_overlaps_by_exactly_the_lap_length():
    """BUG FIX regression guard — confirmed live: this used to produce
    two FULL 8m segments (a 4m overlap) instead of ~480mm."""
    bar = _make_bar(12000.0)
    segs = rebar_engine.split_rebar_by_stock_length(bar, 8000.0, 480.0)
    assert len(segs) == 2
    for s in segs:
        assert s.length_mm <= 8000.0 + 0.5
    overlap_mm = (segs[0].curve.GetEndPoint(1).Z - segs[1].curve.GetEndPoint(0).Z) * _MM_PER_FT
    assert abs(overlap_mm - 480.0) < 1.0, u'overlap was {:.1f}mm, expected ~480mm'.format(overlap_mm)


def test_every_segment_is_within_stock_length_for_a_long_multi_split_bar():
    bar = _make_bar(30000.0)
    segs = rebar_engine.split_rebar_by_stock_length(bar, 8000.0, 480.0)
    assert len(segs) >= 4
    for s in segs:
        assert s.length_mm <= 8000.0 + 0.5


def test_greedy_distribution_all_segments_are_max_stock_except_the_last():
    """GREEDY FIX regression guard — per explicit user request, every
    segment except the last should be exactly stock_length_mm (not the
    previous equal-length distribution, which gave e.g. two 6240mm
    segments for this exact input)."""
    bar = _make_bar(12000.0)
    segs = rebar_engine.split_rebar_by_stock_length(bar, 8000.0, 480.0)
    assert len(segs) == 2
    assert abs(segs[0].length_mm - 8000.0) < 0.5, \
        u'first segment was {:.1f}mm, expected exactly 8000mm (max stock)'.format(segs[0].length_mm)
    assert abs(segs[1].length_mm - 4480.0) < 0.5, \
        u'last segment was {:.1f}mm, expected the 4480mm remainder'.format(segs[1].length_mm)


def test_greedy_distribution_multi_segment_bar_only_the_last_is_short():
    bar = _make_bar(30000.0)
    segs = rebar_engine.split_rebar_by_stock_length(bar, 8000.0, 480.0)
    for s in segs[:-1]:
        assert abs(s.length_mm - 8000.0) < 0.5, \
            u'non-last segment was {:.1f}mm, expected exactly 8000mm'.format(s.length_mm)
    assert segs[-1].length_mm < 8000.0 - 0.5, u'last segment should be the short remainder'
    # every consecutive pair still overlaps by exactly the intended lap
    for a, b in zip(segs, segs[1:]):
        overlap_mm = (a.curve.GetEndPoint(1).Z - b.curve.GetEndPoint(0).Z) * _MM_PER_FT
        assert abs(overlap_mm - 480.0) < 1.0, u'overlap was {:.1f}mm, expected ~480mm'.format(overlap_mm)


def test_segments_cover_the_full_bar_length_end_to_end():
    bar = _make_bar(20000.0)
    segs = rebar_engine.split_rebar_by_stock_length(bar, 8000.0, 480.0)
    assert abs(segs[0].curve.GetEndPoint(0).Z) < 1e-6
    assert abs(segs[-1].curve.GetEndPoint(1).Z - 20000.0 / _MM_PER_FT) < 1e-6


def test_lap_length_must_be_smaller_than_stock_length():
    bar = _make_bar(20000.0)
    try:
        rebar_engine.split_rebar_by_stock_length(bar, 8000.0, 8000.0)
        assert False, 'expected ValueError for lap_length_mm >= stock_length_mm'
    except ValueError:  # nosa-lint: disable=NOSA006 - test cleanup, failure is irrelevant
        pass



def test_staggered_first_piece_moves_every_lap_along():
    """T4.8: a shorter first piece shifts the laps; later pieces stay full stock, laps exact."""
    bar = _make_bar(30000.0)
    plain = rebar_engine.split_rebar_by_stock_length(bar, 12000.0, 750.0)
    staggered = rebar_engine.split_rebar_by_stock_length(bar, 12000.0, 750.0, first_length_mm=11025.0)
    assert abs(staggered[0].length_mm - 11025.0) < 0.5
    for s in staggered[1:-1]:
        assert abs(s.length_mm - 12000.0) < 0.5
    for a, b in zip(staggered, staggered[1:]):
        overlap_mm = (a.curve.GetEndPoint(1).Z - b.curve.GetEndPoint(0).Z) * _MM_PER_FT
        assert abs(overlap_mm - 750.0) < 1.0
    assert abs(staggered[-1].curve.GetEndPoint(1).Z - 30000.0 / _MM_PER_FT) < 1e-6
    shift_mm = (plain[0].curve.GetEndPoint(1).Z - staggered[0].curve.GetEndPoint(1).Z) * _MM_PER_FT
    assert abs(shift_mm - 975.0) < 1.0


def test_staggered_first_piece_ignored_when_the_bar_fits_in_it():
    bar = _make_bar(9000.0)
    segs = rebar_engine.split_rebar_by_stock_length(bar, 12000.0, 750.0, first_length_mm=11025.0)
    assert len(segs) == 1



def test_hook_type_by_angle_only_returns_hooks_of_the_bar_style():
    """A Standard bar with a Stirrup/Tie hook fails in Revit ("internal error", crossties 2026-10-02)."""
    class _Hook(object):
        def __init__(self, name, angle_deg, style):
            self.Name, self.HookAngle, self.Style = name, math.radians(angle_deg), style
    hooks = [_Hook('Stirrup/Tie - 135', 135, 'tie'), _Hook('Standard - 90', 90, 'std'),
             _Hook('Standard - 135', 135, 'std'), _Hook('Stirrup/Tie - 90', 90, 'tie')]

    class _Collector(object):
        def __init__(self, doc):
            pass
        def OfClass(self, cls):
            return self
        def ToElements(self):
            return hooks
    saved = (rebar_engine.DB.__dict__.get('FilteredElementCollector'),
             rebar_engine.DBS.__dict__.get('RebarHookType'), rebar_engine.DBS.__dict__.get('RebarStyle'))
    rebar_engine.DB.FilteredElementCollector = _Collector
    rebar_engine.DBS.RebarHookType = object
    rebar_engine.DBS.RebarStyle = revit_stubs.namespace(Standard='std', StirrupTie='tie')
    try:
        assert rebar_engine.get_hook_type_by_angle(None, 135.0).Name == 'Standard - 135'
        assert rebar_engine.get_hook_type_by_angle(None, 135.0, style='tie').Name == 'Stirrup/Tie - 135'
        assert rebar_engine.get_hook_type_by_angle(None, 90.0, style='tie').Name == 'Stirrup/Tie - 90'
        hooks.pop(2)
        assert rebar_engine.get_hook_type_by_angle(None, 135.0) is None   # never a mismatched style
    finally:
        for owner, name, value in ((rebar_engine.DB, 'FilteredElementCollector', saved[0]),
                                   (rebar_engine.DBS, 'RebarHookType', saved[1]),
                                   (rebar_engine.DBS, 'RebarStyle', saved[2])):
            if value is None:
                delattr(owner, name)
            else:
                setattr(owner, name, value)

if __name__ == '__main__':
    tests = [v for k, v in sorted(globals().items()) if k.startswith('test_')]
    failures = 0
    for t in tests:
        try:
            t()
            print(u'{}: OK'.format(t.__name__))
        except Exception as e:
            failures += 1
            print(u'{}: FAILED -- {}'.format(t.__name__, e))
    print(u'\n{}/{} tests passed'.format(len(tests) - failures, len(tests)))
    sys.exit(1 if failures else 0)
