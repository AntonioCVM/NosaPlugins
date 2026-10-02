# -*- coding: utf-8 -*-
"""Targeted checks for the 4 Phase 3.5.8 DIRECT fixes (crosstie
normative collapse, find_column_above Level+Offset priority, and the
small-hole area threshold). The U-bar native side-cover fix (item 1)
and the 3 telemetry-only items (5/6/7, print statements with no
behavior change) are not covered here — reviewed by inspection and
compile-check instead, since exercising build_floor_reinforcement's
full pipeline just to observe a cover value swap is disproportionate,
and the telemetry items have no return-value change to assert on."""
import math
import os
import sys
import types
import importlib.util

_MM_PER_FT = 304.8
_LIB = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'lib'))
_EXT_LIB = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', '..', 'lib'))
if _EXT_LIB not in sys.path:
    sys.path.insert(0, _EXT_LIB)
from tests_support import revit_stubs  # noqa: E402


# ══════════════════════════════════════════════════════════════════════════
# Fix 4 — small-hole area threshold (pure geometry, no DB mocking needed)
# ══════════════════════════════════════════════════════════════════════════

spec_topo = importlib.util.spec_from_file_location('slab_topology_358', _LIB + r'\slab_topology.py')
slab_topology = importlib.util.module_from_spec(spec_topo)
spec_topo.loader.exec_module(slab_topology)

def _square_mm(cx, cy, side_mm):
    h = side_mm / 2.0
    return [(cx - h, cy - h), (cx + h, cy - h), (cx + h, cy + h), (cx - h, cy + h)]

outer_loop = _square_mm(0, 0, 5000.0)
hole_300 = _square_mm(1000, 1000, 300.0)   # the user's own stated minimum "large" hole
hole_150 = _square_mm(3000, 3000, 150.0)   # smaller, but bigger than a true small sleeve
hole_50 = _square_mm(-2000, -2000, 50.0)   # a genuine small sleeve/penetration

outer, large_holes, n_small = slab_topology.classify_loops([outer_loop, hole_300, hole_150, hole_50])
assert hole_300 in large_holes, "a 300x300mm hole (the user's own minimum) must be 'large'"
assert hole_150 in large_holes, ("a 150x150mm hole (22500mm^2) must be 'large' under the "
                                  "lowered 10000mm^2 threshold (it was 'small' under the old "
                                  "40000mm^2 default)")
assert hole_50 not in large_holes, "a genuine 50x50mm sleeve must still be dropped as 'small'"
assert n_small == 1
print("classify_loops: lowered small_hole_area_mm2 threshold (10000mm^2) correctly "
      "promotes a 150x150mm hole to 'large' while still dropping a true 50x50mm "
      "sleeve, and the user's own 300x300mm minimum is comfortably 'large': OK")


# ══════════════════════════════════════════════════════════════════════════
# Shared mock scaffold for column_rebar (same pattern as test_phase352/356)
# ══════════════════════════════════════════════════════════════════════════

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

class Line(object):
    def __init__(self, p0, p1):
        self._p0, self._p1 = p0, p1
    @staticmethod
    def CreateBound(p0, p1):
        if p0.DistanceTo(p1) < 1e-9:
            raise ValueError('zero-length line')
        return Line(p0, p1)
    def GetEndPoint(self, i):
        return self._p0 if i == 0 else self._p1
    @property
    def Direction(self):
        return (self._p1 - self._p0).Normalize()
    @property
    def Length(self):
        return self._p0.DistanceTo(self._p1)

class BBoxXYZ(object):
    def __init__(self, mn, mx):
        self.Min, self.Max = mn, mx

class FakeParam(object):
    def __init__(self, elem_id=None, value_ft=None):
        self._elem_id, self._value_ft = elem_id, value_ft
    def AsElementId(self):
        return self._elem_id
    def AsDouble(self):
        return self._value_ft

class FakeLevel(object):
    def __init__(self, elevation_ft):
        self.Elevation = elevation_ft

class FakeDoc(object):
    def __init__(self, elements_by_id):
        self._elements = elements_by_id
    def GetElement(self, elem_id):
        return self._elements.get(elem_id)

class FakeColumnHost(object):
    def __init__(self, doc=None, bbox=None, params=None, elem_id=None):
        self.Document = doc
        self._bbox = bbox
        self._params = params or {}
        self.Id = elem_id
        self.Category = None
    def get_BoundingBox(self, view):
        return self._bbox
    def get_Parameter(self, bip):
        return self._params.get(bip)

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

_ALL_COLUMNS = []

DB.FilteredElementCollector = revit_stubs.collector_factory(_ALL_COLUMNS)

revit_stubs.install_system_stubs()

re_engine = revit_stubs.load_module('re_engine_358', _LIB + r'\rebar_engine.py')

column_rebar = revit_stubs.load_module('column_rebar_358', _LIB + r'\column_rebar.py')
column_rebar.re_engine = re_engine
column_rebar._ensure_engine = lambda: re_engine


# ══════════════════════════════════════════════════════════════════════════
# Fix 3 — find_column_above prefers Level+Offset over a Join-notched bbox
# ══════════════════════════════════════════════════════════════════════════

doc = FakeDoc({})
base_level = FakeLevel(10.0)   # 10ft elevation
top_level = FakeLevel(20.0)
doc._elements['BASE_LVL_ID'] = base_level
doc._elements['TOP_LVL_ID'] = top_level

# The upper column's TRUE base is Level(10ft) + 0 offset = 10.0ft, but
# its SOLID has been notched by Join Geometry with the floor below, so
# its own bbox.Min.Z incorrectly reads 10.3ft (100mm short) -- well
# outside the old 0.05ft (~15mm) tolerance against elevation_ft=10.0.
upper_bbox = BBoxXYZ(XYZ(-1.0, -1.0, 10.3), XYZ(1.0, 1.0, 20.0))
upper_params = {
    'BASE_LEVEL': FakeParam(elem_id='BASE_LVL_ID'),
    'BASE_OFFSET': FakeParam(value_ft=0.0),
    'TOP_LEVEL': FakeParam(elem_id='TOP_LVL_ID'),
    'TOP_OFFSET': FakeParam(value_ft=0.0),
}
upper_host = FakeColumnHost(doc=doc, bbox=upper_bbox, params=upper_params, elem_id=99)

lower_host = FakeColumnHost(doc=doc, bbox=None, params={}, elem_id=1)

_ALL_COLUMNS[:] = [lower_host, upper_host]

found = column_rebar.find_column_above(doc, lower_host, elevation_ft=10.0, x0=0.0, y0=0.0)
assert found is upper_host, (
    "find_column_above must match the upper column via its AUTHORED Level+Offset "
    "base (10.0ft), not its Join-notched bbox.Min.Z (10.3ft) which sits outside "
    "the 0.05ft tolerance -- a real column above was missed, silencing the crank")
print("find_column_above: matches the upper column via Level+Offset even when its "
      "own Solid is notched short by Join Geometry (bbox.Min.Z alone would have "
      "missed it): OK")

# Sanity: with NO distinct column above (only the host itself in range),
# still returns None -- unchanged "continuous instance" behaviour.
_ALL_COLUMNS[:] = [lower_host]
assert column_rebar.find_column_above(doc, lower_host, elevation_ft=10.0, x0=0.0, y0=0.0) is None
print("find_column_above: still returns None for a genuinely continuous single "
      "instance (no distinct column above), unchanged: OK")


# ══════════════════════════════════════════════════════════════════════════
# Fix 2 — crosstie normative collapse to one interior stirrup loop
# ══════════════════════════════════════════════════════════════════════════

axis = Line.CreateBound(XYZ(0.0, 0.0, 0.0), XYZ(0.0, 0.0, 10.0))
u_dir, v_dir = XYZ(1, 0, 0), XYZ(0, 1, 0)
zones = [
    {'start_mm': 0.0, 'end_mm': 3000.0, 'spacing_mm': 200.0},
    {'start_mm': 3000.0, 'end_mm': 6000.0, 'spacing_mm': 200.0},
]

# n_u = n_v = 3 -> ONE interior bar per side (8 bars): two crossed crossties per zone, one per
# axis (2026-10-02: a diamond cannot wrap the mid-side bars inside Revit's cover line, so Revit
# squeezed and shifted it into the bars).
result = column_rebar.build_crosstie_sets(axis, u_dir, v_dir, 150.0, 100.0, 3, 3, zones, layout='all')
assert result['crosstie_bars'] == []
sets = result['interior_stirrup_sets']
assert len(sets) == 2 * len(zones), len(sets)
for iss in sets:
    assert iss['layer'] == 'crosstie' and iss['style'] == 'StirrupTie' and len(iss['curves']) == 1
print("build_crosstie_sets: one interior bar per side -> two crossed 135/135 crossties per zone "
      "(StirrupTie Sets), no diamond: OK")

# n_u = 5 (2 interior positions on u), n_v = 2 (0 on v) -> must NOT
# collapse (an axis has more than 1 interior position) -- unchanged
# individual-crosstie behaviour, already covered by test_phase353/356
# but re-asserted here against the NEW dict return shape.
result2 = column_rebar.build_crosstie_sets(axis, u_dir, v_dir, 150.0, 100.0, 5, 2, zones, layout='all')
assert result2['crosstie_bars'] == []
assert sorted(s['layer'] for s in result2['interior_stirrup_sets']) == [
    'crosstie', 'crosstie', 'interior_stirrup', 'interior_stirrup']
print("build_crosstie_sets: 3 interior bars on one axis -> one interior link (outer pair) "
      "+ one crosstie (middle bar) per zone: OK")

# Every tie passes OUTSIDE the bars it restrains, seated like a corner bar in a main link
# (user review 2026-10-02: ties were drawn through / inside the bars, then 3-5 mm into them).
import math as _m

SEATED = 15.0 + (20.0 - (20.0 - 10.0) / _m.sqrt(2.0) - 10.0)


def _seg_dist(p, a, b):
    ax, ay = b[0] - a[0], b[1] - a[1]
    t = max(0.0, min(1.0, ((p[0] - a[0]) * ax + (p[1] - a[1]) * ay) / float(ax * ax + ay * ay)))
    return _m.hypot(p[0] - a[0] - t * ax, p[1] - a[1] - t * ay)


for n_u, n_v in ((5, 2), (5, 3), (5, 5), (4, 6), (3, 3)):
    hw = hd = 250.0
    us = [-hw + i * 2 * hw / (n_u - 1) for i in range(n_u)]
    vs = [-hd + i * 2 * hd / (n_v - 1) for i in range(n_v)]
    interior = [(u, s * hd) for u in us[1:-1] for s in (1, -1)] + \
               [(s * hw, v) for v in vs[1:-1] for s in (1, -1)]
    shapes = column_rebar.interior_tie_layout(hw, hd, n_u, n_v, 'all', 20.0, 10.0)
    for bar in interior:
        best = {}
        for sh in shapes:
            pts = sh['points']
            segs = len(pts) if sh['closed'] else len(pts) - 1
            for i in range(segs):
                d = _seg_dist(bar, pts[i], pts[(i + 1) % len(pts)])
                best[sh['kind']] = min(best.get(sh['kind'], 1e9), d)
        # every tie leg is (20 + 10) / 2 + the bend-seat extra (2.93 mm: H20 in an H10 link on a
        # 40 mm mandrel, rebar_engine.link_corner_extra_inset_mm) from the bar it holds
        assert abs(min(best.values()) - SEATED) < 0.05, (n_u, n_v, bar, best)
print("interior_tie_layout: every interior bar is held from outside, seated like a main-link corner "
      "bar ({:.2f} mm to the tie centreline), for 5x2, 5x3, 5x5, 4x6 and 3x3: OK".format(SEATED))

# A crosstie runs D/2 past each bar so its 135 deg hooks wrap the bars it ties.
ct = [s for s in column_rebar.interior_tie_layout(250.0, 250.0, 3, 4, 'all', 20.0, 10.0, 40.0)
      if s['kind'] == 'crosstie'][0]
(u0, v0), (u1, v1) = ct['points']
assert abs(u0 + SEATED) < 1e-6 and abs(v0 - 270.0) < 1e-6 and abs(v1 + 270.0) < 1e-6, ct
print("interior_tie_layout: crosstie seated beside the bar and run D/2 past it: OK")

print("\nALL PHASE 3.5.8 TARGETED CHECKS PASSED")
