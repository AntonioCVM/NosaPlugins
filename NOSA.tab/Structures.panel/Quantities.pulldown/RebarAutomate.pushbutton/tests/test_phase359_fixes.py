# -*- coding: utf-8 -*-
"""Targeted checks for the Phase 3.5.9 math fixes found from Phase
3.5.8's telemetry: the 'bare b -> circular' false positive (square
columns running through the circular code path), the collinear-chain
merge (straight lap extensions rejected by CreateFromCurves), and the
circular tie's 2-Arc -> 24-chord polygon replacement. The n_u/n_v >= 2
defensive clamp (item 3) has no observable behavior change (already
guaranteed by distribute_bar_count) and is covered by inspection, not
a new assertion here."""
import math
import os
import sys
import types

_MM_PER_FT = 304.8
_LIB = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'lib'))
_EXT_LIB = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', '..', 'lib'))
if _EXT_LIB not in sys.path:
    sys.path.insert(0, _EXT_LIB)
from tests_support import revit_stubs  # noqa: E402


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
    def GetLength(self):
        return math.sqrt(self.X**2 + self.Y**2 + self.Z**2)
    def Normalize(self):
        L = self.GetLength()
        return XYZ(0, 0, 0) if L == 0 else XYZ(self.X / L, self.Y / L, self.Z / L)
    def DistanceTo(self, o):
        return (self - o).GetLength()

class BBoxXYZ(object):
    def __init__(self, mn, mx):
        self.Min, self.Max = mn, mx

class LocationPoint(object):
    def __init__(self, point, rotation=0.0):
        self.Point = point
        self.Rotation = rotation

class FakeParam(object):
    def __init__(self, elem_id=None, value_ft=None):
        self._elem_id, self._value_ft = elem_id, value_ft
    def AsElementId(self):
        return self._elem_id
    def AsDouble(self):
        return self._value_ft

class FakeDoc(object):
    def __init__(self, elements_by_id):
        self._elements = elements_by_id
    def GetElement(self, elem_id):
        return self._elements.get(elem_id)

class FakeColumnHost(object):
    _next_id = [1]
    def __init__(self, location=None, bbox=None, params=None):
        self.Location = location
        self._bbox = bbox
        self._params = params or {}
        self.Category = None
        self.Id = FakeColumnHost._next_id[0]
        FakeColumnHost._next_id[0] += 1
    def get_Geometry(self, opts):
        return []
    def get_BoundingBox(self, view):
        return self._bbox
    def get_Parameter(self, bip):
        return self._params.get(bip)
    def LookupParameter(self, name):
        return self._params.get(name)

class Line(object):
    def __init__(self, p0, p1):
        self._p0, self._p1 = p0, p1
    @staticmethod
    def CreateBound(p0, p1):
        return Line(p0, p1)
    def GetEndPoint(self, i):
        return self._p0 if i == 0 else self._p1
    @property
    def Direction(self):
        return (self._p1 - self._p0).Normalize()
    @property
    def Length(self):
        return self._p0.DistanceTo(self._p1)

DB, DBS = revit_stubs.install_revit_stubs(structure_attrs=dict(
    RebarStyle=revit_stubs.namespace(Standard=1, StirrupTie=2),
    RebarHookOrientation=revit_stubs.namespace(Left=1, Right=2)))
DB.XYZ = XYZ
DB.XYZ.BasisZ = XYZ(0, 0, 1)
DB.Line = Line
DB.BuiltInParameter = types.SimpleNamespace(
    FAMILY_BASE_LEVEL_PARAM='BASE_LEVEL',
    FAMILY_BASE_LEVEL_OFFSET_PARAM='BASE_OFFSET',
    FAMILY_TOP_LEVEL_PARAM='TOP_LEVEL',
    FAMILY_TOP_LEVEL_OFFSET_PARAM='TOP_OFFSET',
)
DB.BuiltInCategory = types.SimpleNamespace(OST_Floors=1, OST_StructuralColumns=2)

DB.FilteredElementCollector = revit_stubs.collector_factory()

revit_stubs.install_system_stubs()

re_engine = revit_stubs.load_module('re_engine_359', _LIB + r'\rebar_engine.py')

column_rebar = revit_stubs.load_module('column_rebar_359', _LIB + r'\column_rebar.py')
column_rebar.re_engine = re_engine
column_rebar._ensure_engine = lambda: re_engine


# ══════════════════════════════════════════════════════════════════════════
# Fix 1 — bare 'b' with no 'h' must be SQUARE, never circular
# ══════════════════════════════════════════════════════════════════════════

doc = FakeDoc({})  # BASE_LEVEL resolves to None -> get_column_axis falls to bbox
square_host = FakeColumnHost(
    location=LocationPoint(XYZ(0, 0, 0), rotation=0.0),
    bbox=BBoxXYZ(XYZ(-0.5, -0.5, 0.0), XYZ(0.5, 0.5, 3000.0 / _MM_PER_FT)),
    params={'BASE_LEVEL': FakeParam(elem_id='dummy'), 'b': FakeParam(value_ft=400.0 / _MM_PER_FT)})

axis = column_rebar.get_column_axis(square_host)
engine = re_engine
cover_mgr = engine.CoverGeometryManager(doc, square_host)
source = column_rebar._resolve_column_geometry_source(square_host, axis, cover_mgr)
assert source['kind'] == 'analytical', "a bare 'b' column must resolve analytically, not fall to face-detection"
assert source['b_mm'] == 400.0
assert source['h_mm'] == 400.0, "h_mm must default to b_mm (square), not be treated as a diameter"
print("_resolve_column_geometry_source: a bare 'b' with no 'h' resolves as a SQUARE "
      "section (h_mm = b_mm), analytically: OK")

result = column_rebar.build_column_reinforcement(
    doc, square_host, cover_mm=40.0, bar_diameter_mm=16.0, bar_count=4,
    stirrup_diameter_mm=8.0, dense_spacing_mm=100.0, normal_spacing_mm=200.0)

# Must NOT have gone through the circular path: circular ties are a
# 24-chord polygon and crossties are always empty by contract; a
# rectangular 4-bar column's stirrup is a plain 4-segment loop.
assert len(result['stirrup_sets']) > 0
for s in result['stirrup_sets']:
    assert len(s['curves']) == 4, (
        "a bare-'b' square column must produce RECTANGULAR 4-segment ties, "
        "not the circular path's 24-chord polygon — got {} curves".format(len(s['curves'])))

# The 4 vertical bars must land at the exact 4 CORNERS of the cover-inset
# square, not at 0/90/180/270-degree radial positions (which, for a
# square, are the FACE MIDPOINTS — the exact symptom this fix resolves).
# For n_u=n_v=2 (tied), the 'u' edges own BOTH corners each (2
# positions per edge -> one Rebar Set per edge), and the 'v' edges have
# ZERO interior positions left (skipped entirely) — so this is 2 Sets
# of 2 (top 'u' edge + bottom 'u' edge), covering all 4 corners between
# them, not 4 individual Sets.
bar_inset_mm = 40.0 + 8.0 + 16.0 / 2.0
half_mm = 400.0 / 2.0 - bar_inset_mm
assert result['vertical_bars'] == [], "n_u=n_v=2 leaves no single-position faces at all"
assert len(result['vertical_bar_sets']) == 2, (
    "4 bars on a square column (n_u=n_v=2, tied -> 'u' owns both corner-pair "
    "edges, 'v' has none left) must yield exactly 2 Sets of 2 — got {}".format(
        len(result['vertical_bar_sets'])))
corners_seen = set()
for vs in result['vertical_bar_sets']:
    assert vs['count'] == 2
    assert abs(vs['array_length_mm'] - 2.0 * half_mm) < 1e-6, (
        "each edge's Set must span corner-to-corner, the full {}mm width".format(2.0 * half_mm))
    p0 = vs['curves'][0].GetEndPoint(0)
    x_mm, y_mm = round(p0.X * _MM_PER_FT, 3), round(p0.Y * _MM_PER_FT, 3)
    # a genuine CORNER has BOTH coordinates at the half-extent magnitude —
    # a face-MIDPOINT (the old circular-misdetection symptom) would have
    # only ONE coordinate at that magnitude, the other at 0.
    assert abs(abs(x_mm) - half_mm) < 1e-6 and abs(abs(y_mm) - half_mm) < 1e-6, (
        "bar at ({:.2f},{:.2f})mm is not a corner (half_mm={:.2f}) — landed on a "
        "face MIDPOINT instead, the exact 'circular radial placement on a square "
        "section' symptom".format(x_mm, y_mm, half_mm))
    corners_seen.add((x_mm, y_mm))
assert len(corners_seen) == 2, "the 2 Sets' own start corners must be distinct"
print("build_column_reinforcement: a bare-'b' 4-bar square column places all 4 "
      "bars at the exact CORNERS (via the rectangular path, 2 Sets of 2), not at "
      "face midpoints (the old circular-misdetection symptom): OK")


# ══════════════════════════════════════════════════════════════════════════
# Fix 2 — collinear chain merge (also exercised end-to-end above via
# include_starter_bars=False's plain vertical bars; here a direct,
# isolated check of the helper itself)
# ══════════════════════════════════════════════════════════════════════════

p0, p1, p2 = XYZ(0, 0, 0), XYZ(0, 0, 10), XYZ(0, 0, 16)
chain = [Line.CreateBound(p0, p1), Line.CreateBound(p1, p2)]
merged = column_rebar._merge_collinear_chain(chain)
assert len(merged) == 1, "two collinear segments sharing an endpoint must merge into ONE Line"
assert merged[0].GetEndPoint(0).Z == 0 and merged[0].GetEndPoint(1).Z == 16

# A genuinely KINKED chain (crank diagonal, different direction) must NOT merge.
p3 = XYZ(2, 0, 20)
kinked = [Line.CreateBound(p0, p1), Line.CreateBound(p1, p3)]
merged_kinked = column_rebar._merge_collinear_chain(kinked)
assert len(merged_kinked) == 2, "a genuine direction change (crank) must NOT be merged away"
print("_merge_collinear_chain: collapses collinear neighbours into one Line, "
      "leaves a genuine kink (different direction) untouched: OK")


# ══════════════════════════════════════════════════════════════════════════
# Fix 4 — circular tie chord count constant sanity (full geometry already
# re-verified in test_phase357_fixes.py against the live build path)
# ══════════════════════════════════════════════════════════════════════════

assert column_rebar._CIRCULAR_TIE_CHORD_COUNT >= 12, "too few chords would visibly deviate from a circle"
print("_CIRCULAR_TIE_CHORD_COUNT: sane chord count for the circular-tie polygon "
      "fallback: OK")

print("\nALL PHASE 3.5.9 TARGETED CHECKS PASSED")
