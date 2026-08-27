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

DB = types.ModuleType('Autodesk.Revit.DB')
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

class _FakeCollector(object):
    def OfCategory(self, cat):
        return self
    def WhereElementIsNotElementType(self):
        return list(_ALL_COLUMNS)

DB.FilteredElementCollector = lambda doc: _FakeCollector()

DBS = types.ModuleType('Autodesk.Revit.DB.Structure')
DBS.RebarStyle = types.SimpleNamespace(Standard=1, StirrupTie=2)
DBS.RebarHookOrientation = types.SimpleNamespace(Left=1, Right=2)
DB.Structure = DBS

autodesk = types.ModuleType('Autodesk')
revit_mod = types.ModuleType('Autodesk.Revit')
autodesk.Revit = revit_mod
revit_mod.DB = DB
sys.modules['Autodesk'] = autodesk
sys.modules['Autodesk.Revit'] = revit_mod
sys.modules['Autodesk.Revit.DB'] = DB
sys.modules['Autodesk.Revit.DB.Structure'] = DBS
sys.modules['System.Collections.Generic'] = types.SimpleNamespace(List=lambda t: (lambda items: list(items)))

spec_re = importlib.util.spec_from_file_location('re_engine_358', _LIB + r'\rebar_engine.py')
re_engine = importlib.util.module_from_spec(spec_re)
sys.modules['re_engine_358'] = re_engine
spec_re.loader.exec_module(re_engine)

spec_col = importlib.util.spec_from_file_location('column_rebar_358', _LIB + r'\column_rebar.py')
column_rebar = importlib.util.module_from_spec(spec_col)
sys.modules['column_rebar_358'] = column_rebar
spec_col.loader.exec_module(column_rebar)
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

# n_u = n_v = 3 -> exactly ONE interior position per axis (the "8 bars
# total, one extra per long edge" example the user gave) -> must
# collapse into one closed interior stirrup loop PER ZONE, not
# individual crossing crossties.
result = column_rebar.build_crosstie_sets(axis, u_dir, v_dir, 150.0, 100.0, 3, 3, zones, layout='all')
assert result['crosstie_bars'] == [], "the diamond (1 interior per axis) case must not emit individual crossties"
assert len(result['interior_stirrup_sets']) == len(zones), (
    "expected one interior stirrup Set per zone ({}), got {}".format(
        len(zones), len(result['interior_stirrup_sets'])))
for iss in result['interior_stirrup_sets']:
    assert len(iss['curves']) == 4, "interior loop must be a closed 4-segment shape"
    assert iss['style'] == 'StirrupTie'
    # closed: each curve's end must meet the next curve's start
    for i in range(4):
        c0, c1 = iss['curves'][i], iss['curves'][(i + 1) % 4]
        p_end, p_next_start = c0.GetEndPoint(1), c1.GetEndPoint(0)
        assert p_end.DistanceTo(p_next_start) < 1e-9, "interior loop is not actually closed"
print("build_crosstie_sets: the 'diamond' case (1 interior bar per axis) collapses "
      "into ONE closed 4-segment interior stirrup loop per zone (StirrupTie, "
      "Set-propagated) instead of individual crossing crossties: OK")

# n_u = 5 (2 interior positions on u), n_v = 2 (0 on v) -> must NOT
# collapse (an axis has more than 1 interior position) -- unchanged
# individual-crosstie behaviour, already covered by test_phase353/356
# but re-asserted here against the NEW dict return shape.
result2 = column_rebar.build_crosstie_sets(axis, u_dir, v_dir, 150.0, 100.0, 5, 2, zones, layout='all')
assert result2['interior_stirrup_sets'] == [], "2+ interior positions on one axis must NOT collapse"
assert len(result2['crosstie_bars']) > 0
print("build_crosstie_sets: an axis with 2+ interior positions keeps individual "
      "crossties unchanged (does not collapse): OK")

print("\nALL PHASE 3.5.8 TARGETED CHECKS PASSED")
