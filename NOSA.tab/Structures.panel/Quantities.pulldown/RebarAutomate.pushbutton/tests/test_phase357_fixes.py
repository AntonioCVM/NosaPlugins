# -*- coding: utf-8 -*-
"""Targeted checks for the 4 Phase 3.5.7 live-Revit fixes: circular
column reinforcement (radial bars + Arc.Create ties), the Z-max revert
(already covered by test_phase353_fixes.py's updated assertion, not
repeated here), full topology port for footing main-grid + perimeter
closure U-bars (holes respected), and the cardinal-axis snap for
U-bar legs on diagonal edges."""
import math
import os
import sys
import types
import importlib.util

_MM_PER_FT = 304.8
_LIB = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'lib'))


# ══════════════════════════════════════════════════════════════════════════
# Shared mock scaffold (same pattern as test_floor_rebar_phase23.py)
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
    def CrossProduct(self, o):
        return XYZ(self.Y * o.Z - self.Z * o.Y,
                    self.Z * o.X - self.X * o.Z,
                    self.X * o.Y - self.Y * o.X)
    def GetLength(self):
        return math.sqrt(self.X**2 + self.Y**2 + self.Z**2)
    def Normalize(self):
        L = self.GetLength()
        return XYZ(0, 0, 0) if L == 0 else XYZ(self.X / L, self.Y / L, self.Z / L)
    def DistanceTo(self, o):
        return (self - o).GetLength()

class UV(object):
    def __init__(self, u, v):
        self.U, self.V = u, v

class BBoxUV(object):
    def __init__(self, umin, vmin, umax, vmax):
        self.Min, self.Max = UV(umin, vmin), UV(umax, vmax)

class BBoxXYZ(object):
    def __init__(self, mn, mx):
        self.Min, self.Max = mn, mx

class PlanarFace(object):
    pass

class MockLine(object):
    def __init__(self, p0, p1):
        self._p0, self._p1 = p0, p1
    def Tessellate(self):
        return [self._p0, self._p1]

def _loop_mm(points_mm, z_ft):
    pts_ft = [XYZ(x / _MM_PER_FT, y / _MM_PER_FT, z_ft) for x, y in points_mm]
    n = len(pts_ft)
    return [MockLine(pts_ft[i], pts_ft[(i + 1) % n]) for i in range(n)]

class FakeFace(PlanarFace):
    def __init__(self, z_ft, normal, umin, vmin, umax, vmax, curve_loops):
        self._z = z_ft
        self._normal = normal
        self._bbox = BBoxUV(umin, vmin, umax, vmax)
        self._curve_loops = curve_loops
    def GetBoundingBox(self):
        return self._bbox
    def ComputeNormal(self, uv):
        return self._normal
    def Evaluate(self, uv):
        return XYZ(uv.U, uv.V, self._z)
    def GetEdgesAsCurveLoops(self):
        return self._curve_loops

class Solid(object):
    def __init__(self, faces=None, volume=1.0, edges=None):
        self.Faces = faces or []
        self.Volume = volume
        self.Edges = edges if edges is not None else []

class Options(object):
    def __init__(self):
        self.ComputeReferences = False
        self.DetailLevel = None

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

class Arc(object):
    """Records its own construction args for inspection, matching the
    real DB.Arc.Create(center, radius, startAngle, endAngle, xAxis,
    yAxis) overload used by _build_circular_column_reinforcement."""
    def __init__(self, center, radius_ft, start_angle, end_angle, x_axis, y_axis):
        self.center = center
        self.radius_ft = radius_ft
        self.start_angle = start_angle
        self.end_angle = end_angle
    @staticmethod
    def Create(center, radius_ft, start_angle, end_angle, x_axis, y_axis):
        return Arc(center, radius_ft, start_angle, end_angle, x_axis, y_axis)
    def GetEndPoint(self, i):
        angle = self.start_angle if i == 0 else self.end_angle
        return XYZ(self.center.X + self.radius_ft * math.cos(angle),
                   self.center.Y + self.radius_ft * math.sin(angle),
                   self.center.Z)

class LocationPoint(object):
    def __init__(self, point, rotation=None):
        self.Point = point
        self.Rotation = rotation

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
    def __init__(self, elements_by_id=None):
        self._elements = elements_by_id or {}
    def GetElement(self, elem_id):
        return self._elements.get(elem_id)

class FakeHost(object):
    """Footing/floor host — bottom/top faces + a solid wrapping them."""
    _next_id = [1]
    def __init__(self, bottom_face, top_face, width_ft, depth_ft, height_ft):
        self._bottom_face = bottom_face
        self._top_face = top_face
        self._w, self._d, self._h = width_ft, depth_ft, height_ft
        self._solid = Solid([bottom_face, top_face], volume=width_ft * depth_ft * height_ft)
        self.Id = FakeHost._next_id[0]
        FakeHost._next_id[0] += 1
    def get_Geometry(self, opts):
        return [self._solid]
    def get_BoundingBox(self, view):
        return BBoxXYZ(XYZ(0.0, 0.0, 0.0), XYZ(self._w, self._d, self._h))
    def get_Parameter(self, bip):
        return None
    def LookupParameter(self, name):
        return None

class FakeColumnHost(object):
    """Column host — location + type/instance params, no real solid
    needed since circular generation never touches Solid.Faces."""
    _next_id = [1]
    def __init__(self, location=None, bbox=None, params=None):
        self.Location = location
        self._bbox = bbox
        self._params = params or {}
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


DB = types.ModuleType('Autodesk.Revit.DB')
DB.XYZ = XYZ
DB.XYZ.BasisZ = XYZ(0, 0, 1)
DB.XYZ.BasisX = XYZ(1, 0, 0)
DB.UV = UV
DB.Line = Line
DB.Arc = Arc
DB.PlanarFace = PlanarFace
DB.CylindricalFace = type('CylindricalFace', (), {})
DB.Solid = Solid
DB.Options = Options
DB.GeometryInstance = type('GeometryInstance', (), {})
DB.ViewDetailLevel = types.SimpleNamespace(Fine=1)

class _FakeElementId(object):
    def __init__(self, value):
        self._value = value
    def __eq__(self, other):
        return isinstance(other, _FakeElementId) and other._value == self._value
    def __ne__(self, other):
        return not self.__eq__(other)
    def __hash__(self):
        return hash(self._value)
DB.ElementId = types.SimpleNamespace(InvalidElementId=_FakeElementId(-1))

DB.BuiltInParameter = types.SimpleNamespace(
    REBAR_BAR_DIAMETER=1,
    FAMILY_BASE_LEVEL_PARAM='BASE_LEVEL',
    FAMILY_BASE_LEVEL_OFFSET_PARAM='BASE_OFFSET',
    FAMILY_TOP_LEVEL_PARAM='TOP_LEVEL',
    FAMILY_TOP_LEVEL_OFFSET_PARAM='TOP_OFFSET',
    CLEAR_COVER_TOP='CLEAR_COVER_TOP',
    CLEAR_COVER_BOTTOM='CLEAR_COVER_BOTTOM',
    CLEAR_COVER_OTHER='CLEAR_COVER_OTHER',
)
DB.BuiltInCategory = types.SimpleNamespace(OST_Floors=1, OST_StructuralColumns=2)

class _FakeCollector(object):
    def OfClass(self, cls):
        return self
    def OfCategory(self, cat):
        return self
    def WhereElementIsNotElementType(self):
        return []
    def ToElements(self):
        return []
DB.FilteredElementCollector = lambda doc: _FakeCollector()

DBS = types.ModuleType('Autodesk.Revit.DB.Structure')
class _NoRebarHostData(object):
    @staticmethod
    def GetRebarHostData(host):
        raise RuntimeError('not mocked')
DBS.RebarHostData = _NoRebarHostData
DBS.RebarBarType = object
DBS.RebarShape = object
DBS.RebarStyle = types.SimpleNamespace(Standard=1, StirrupTie=2)
DBS.RebarHookOrientation = types.SimpleNamespace(Left=1, Right=2)
DBS.RebarHookType = object
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


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


re_engine = _load('re_engine_357', _LIB + r'\rebar_engine.py')

footing_rebar = _load('footing_rebar_357', _LIB + r'\footing_rebar.py')
footing_rebar.re_engine = re_engine
footing_rebar._ensure_engine = lambda: re_engine

slab_topology = _load('slab_topology_357', _LIB + r'\slab_topology.py')

floor_rebar = _load('floor_rebar_357', _LIB + r'\floor_rebar.py')
floor_rebar.footing_rebar_mod = footing_rebar
floor_rebar._ensure_footing_rebar = lambda: footing_rebar
floor_rebar.re_engine = re_engine
floor_rebar._ensure_engine = lambda: re_engine
floor_rebar.slab_topology = slab_topology
floor_rebar._ensure_topology = lambda: slab_topology

footing_rebar.slab_topology = slab_topology
footing_rebar._ensure_topology = lambda: slab_topology
footing_rebar.floor_rebar_mod = floor_rebar
footing_rebar._ensure_floor_rebar = lambda: floor_rebar

column_rebar = _load('column_rebar_357', _LIB + r'\column_rebar.py')
column_rebar.re_engine = re_engine
column_rebar._ensure_engine = lambda: re_engine

doc = None


def make_pile_cap_with_hole(width_mm=3000.0, depth_mm=2000.0, thickness_mm=800.0,
                             hole_mm=None):
    hole_mm = hole_mm or [(1200.0, 800.0), (1800.0, 800.0), (1800.0, 1200.0), (1200.0, 1200.0)]
    w_ft, d_ft, h_ft = width_mm / _MM_PER_FT, depth_mm / _MM_PER_FT, thickness_mm / _MM_PER_FT
    outer = [(0.0, 0.0), (width_mm, 0.0), (width_mm, depth_mm), (0.0, depth_mm)]
    bottom_loops = [_loop_mm(outer, 0.0), _loop_mm(hole_mm, 0.0)]
    top_loops = [_loop_mm(outer, h_ft), _loop_mm(hole_mm, h_ft)]
    bottom = FakeFace(0.0, XYZ(0, 0, -1), 0.0, 0.0, w_ft, d_ft, bottom_loops)
    top = FakeFace(h_ft, XYZ(0, 0, 1), 0.0, 0.0, w_ft, d_ft, top_loops)
    return FakeHost(bottom, top, w_ft, d_ft, h_ft)


# ══════════════════════════════════════════════════════════════════════════
# Fix 1 — circular column reinforcement
# ══════════════════════════════════════════════════════════════════════════

circ_host = FakeColumnHost(
    location=LocationPoint(XYZ(0, 0, 0)),
    bbox=BBoxXYZ(XYZ(-1.0, -1.0, 0.0), XYZ(1.0, 1.0, 3000.0 / _MM_PER_FT)),
    params={'BASE_LEVEL': FakeParam(elem_id='dummy'), 'Diameter': FakeParam(value_ft=500.0 / _MM_PER_FT)})
doc357 = FakeDoc({})  # get_column_axis falls to bbox since level params resolve to None-doc
result = column_rebar.build_column_reinforcement(
    doc357, circ_host, cover_mm=40.0, bar_diameter_mm=16.0, bar_count=8,
    stirrup_diameter_mm=8.0, dense_spacing_mm=100.0, normal_spacing_mm=200.0)
assert result['crosstie_sets'] == [], "circular columns must never generate crossties"
assert result['vertical_bar_sets'] == [], "circular verticals are individual bars, not Sets"
assert len(result['vertical_bars']) == 8, len(result['vertical_bars'])
bar_radius_mm = 500.0 / 2.0 - (40.0 + 8.0 + 16.0 / 2.0)
for i, vb in enumerate(result['vertical_bars']):
    theta = 2.0 * math.pi * i / 8
    line = vb['curves'][0]
    p = line.GetEndPoint(0)
    expected_x_ft = bar_radius_mm * math.cos(theta) / _MM_PER_FT
    expected_y_ft = bar_radius_mm * math.sin(theta) / _MM_PER_FT
    assert abs(p.X - expected_x_ft) < 1e-6, (i, p.X, expected_x_ft)
    assert abs(p.Y - expected_y_ft) < 1e-6, (i, p.Y, expected_y_ft)
print("build_column_reinforcement (circular): 8 bars distributed radially by pure "
      "trigonometry, no crossties, no Rebar Sets for verticals: OK")

assert len(result['stirrup_sets']) > 0
# PHASE 3.5.9 item 4 — Revit rejected the original 2-Arc closed loop
# (Rebar.CreateFromCurves returned None, live-confirmed); ties are now
# a 24-chord closed polygon of straight Line segments approximating
# the circle, the same closed-polyline shape already proven for
# rectangular StirrupTie sets.
expected_n = column_rebar._CIRCULAR_TIE_CHORD_COUNT
bar_inset_mm = 40.0 + 8.0 + 16.0 / 2.0
stirrup_inset_mm = 40.0 + 8.0 / 2.0
stirrup_radius_ft = (500.0 / 2.0 - stirrup_inset_mm) / _MM_PER_FT
for s in result['stirrup_sets']:
    assert len(s['curves']) == expected_n, (len(s['curves']), expected_n)
    for c in s['curves']:
        assert isinstance(c, Line), "circular tie chords must be straight Line segments, not Arcs"
    # closed: each curve's end meets the next curve's start
    for i in range(expected_n):
        c0, c1 = s['curves'][i], s['curves'][(i + 1) % expected_n]
        assert c0.GetEndPoint(1).DistanceTo(c1.GetEndPoint(0)) < 1e-9, "tie polygon is not closed"
    # every vertex sits at the stirrup's own radius from the tie's own center (axis)
    for c in s['curves']:
        p = c.GetEndPoint(0)
        r_ft = math.sqrt(p.X ** 2 + p.Y ** 2)
        assert abs(r_ft - stirrup_radius_ft) < 1e-6, (r_ft, stirrup_radius_ft)
print("build_column_reinforcement (circular): ties are a closed {}-chord polygon "
      "of straight Lines (Revit rejected the 2-Arc loop), each vertex on the "
      "tie's own radius, Set-propagated per zone: OK".format(expected_n))


# ══════════════════════════════════════════════════════════════════════════
# Fix 3 (footing side) — full topology port respects a real hole
# ══════════════════════════════════════════════════════════════════════════

cap_host = make_pile_cap_with_hole()
mat = footing_rebar.build_mat_bars_topology(
    doc, cap_host, is_top=False, cover_mm=50.0, dia_x_mm=16.0, dia_y_mm=16.0,
    spacing_x_mm=200.0, spacing_y_mm=200.0)
assert 'along_x' in mat and 'along_y' in mat
assert set(mat['along_x'].keys()) == {'sets', 'bars'}
total_x_items = len(mat['along_x']['sets']) + len(mat['along_x']['bars'])
assert total_x_items > 0, "expected at least some along_x reinforcement around the hole"
print("build_mat_bars_topology: returns the same {'sets','bars'} shape floors use "
      "(consumable by ui.py's _create_grouped_bars) and produces real geometry "
      "around a pile-cap hole: OK")

# Every materialized bar curve must be clipped BEFORE it would cross the
# hole -- i.e. no single continuous 'along_y' bar (runs in Y, one row
# per X) spans the full 0..2000mm depth at an X row that falls inside
# the hole's own X-band (1200-1800mm).
hole_x_lo_ft, hole_x_hi_ft = 1200.0 / _MM_PER_FT, 1800.0 / _MM_PER_FT
found_a_row_through_hole_band = False
for s in mat['along_y']['sets'] + mat['along_y']['bars']:
    for curve in s['curves']:
        p0, p1 = curve.GetEndPoint(0), curve.GetEndPoint(1)
        if hole_x_lo_ft - 0.01 < p0.X < hole_x_hi_ft + 0.01:
            found_a_row_through_hole_band = True
            span_ft = abs(p1.Y - p0.Y)
            span_mm = span_ft * _MM_PER_FT
            assert span_mm < 2000.0 - 1.0, (
                "a bar in the hole's own X-band spans the full depth "
                "({}mm) -- the hole was NOT clipped".format(span_mm))
assert found_a_row_through_hole_band, "test setup sanity: expected at least one row in the hole's band"
print("build_mat_bars_topology: bars whose row falls within the hole's own band are "
      "clipped SHORTER than the full footing depth -- the hole is respected, not "
      "run straight through: OK")

closure = footing_rebar.build_perimeter_closure_ubars_topology(
    doc, cap_host, bottom_cover_mm=50.0, bottom_dia_x_mm=16.0, bottom_dia_y_mm=16.0,
    top_cover_mm=50.0, top_dia_x_mm=16.0, top_dia_y_mm=16.0,
    x_anchor_dia_mm=12.0, x_anchor_spacing_mm=200.0,
    y_anchor_dia_mm=12.0, y_anchor_spacing_mm=200.0)
assert set(('x_bars', 'y_bars', 'debug_failed_edges')) <= set(closure.keys())
total_closure_items = (len(closure['x_bars']['sets']) + len(closure['x_bars']['bars'])
                        + len(closure['y_bars']['sets']) + len(closure['y_bars']['bars']))
assert total_closure_items >= 8, (
    "expected closure U-bars around BOTH the outer boundary (4 edges) AND the "
    "hole (4 more edges), got {} total items".format(total_closure_items))
print("build_perimeter_closure_ubars_topology: generates closure U-bars around the "
      "OUTER boundary AND the interior hole (>= 8 edges total), not just the 4 "
      "outer sides: OK")


# ══════════════════════════════════════════════════════════════════════════
# Fix 3 (U-bar side) — cardinal-axis snap for diagonal edges
# ══════════════════════════════════════════════════════════════════════════

outer_square = [(0.0, 0.0), (2000.0, 0.0), (2000.0, 2000.0), (0.0, 2000.0)]
# A perfectly diagonal edge (45 degrees) near the middle of the square,
# far from any other boundary -- inward_normal should be diagonal
# too, but the SNAPPED leg direction must land on a cardinal axis.
p0_diag, p1_diag = (900.0, 1000.0), (1100.0, 1000.0)
diag_normal = (0.0, 1.0)  # already-inward for this horizontal test edge
snapped = floor_rebar._snap_normal_to_cardinal_mm(
    p0_diag, p1_diag, diag_normal, slab_topology, outer_square, [])
assert snapped == (0.0, 1.0), snapped
print("_snap_normal_to_cardinal_mm: an already-cardinal normal passes through "
      "unchanged (no spurious re-direction for the ordinary axis-aligned case): OK")

# A genuinely diagonal inward_normal (approx 45 degrees) must snap to
# whichever cardinal it's closer to, and the snap must be re-confirmed
# inside material (both candidates ARE inside this simple square, so
# the snap must succeed, not silently fall back).
diag_normal_45 = (0.6, 0.8)  # closer to +Y than +X
snapped2 = floor_rebar._snap_normal_to_cardinal_mm(
    (900.0, 900.0), (1100.0, 1100.0), diag_normal_45, slab_topology, outer_square, [])
assert snapped2 == (0.0, 1.0), snapped2
print("_snap_normal_to_cardinal_mm: a diagonal (45-degree-ish) normal snaps to its "
      "closest cardinal axis (+Y here), aligning the leg with the main mat: OK")

print("\nALL PHASE 3.5.7 TARGETED CHECKS PASSED")
