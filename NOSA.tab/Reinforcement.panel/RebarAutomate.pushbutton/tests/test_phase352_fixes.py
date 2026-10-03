# -*- coding: utf-8 -*-
"""Targeted checks for the 4 Phase 3.5.2 live-Revit fixes: per-edge
try/except isolation in floor_rebar, Base/Top Level+Offset column axis
(bypassing Join Geometry), the crank sign correction, and the
face-count geometric fallback for faceted circular columns. Mock setup
mirrors test_column_rebar_phase3.py's proven pattern (importlib, not
the removed `imp` module column_rebar._ensure_engine would otherwise
try to use)."""
import math
import sys
import os
import types

_MM_PER_FT = 304.8
_LIB = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'lib'))
_EXT_LIB = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', 'lib'))
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

class PlanarFace(object):
    pass

class FakeFace(PlanarFace):
    def __init__(self, normal, origin):
        self._normal, self._origin = normal, origin
        self._bbox = BBoxUV(0.0, 0.0, 1.0, 1.0)
    def GetBoundingBox(self):
        return self._bbox
    def ComputeNormal(self, uv):
        return self._normal
    def Evaluate(self, uv):
        return self._origin

class CylindricalFace(object):
    def __init__(self, radius_ft):
        self.Radius = radius_ft

class Solid(object):
    def __init__(self, faces, volume=1.0, edges=None):
        self.Faces = faces
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

class BBoxXYZ(object):
    def __init__(self, mn, mx):
        self.Min, self.Max = mn, mx

class LocationCurve(object):
    def __init__(self, curve):
        self.Curve = curve

class LocationPoint(object):
    def __init__(self, point):
        self.Point = point

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

class FakeHost(object):
    _next_id = [1]
    def __init__(self, solid, location=None, bbox=None, doc=None, params=None):
        self._solid = solid
        self.Location = location
        self._bbox = bbox
        self.Document = doc
        self._params = params or {}
        self.Id = FakeHost._next_id[0]
        FakeHost._next_id[0] += 1
    def get_Geometry(self, opts):
        return [self._solid]
    def get_BoundingBox(self, view):
        return self._bbox
    def get_Parameter(self, bip):
        return self._params.get(bip)


DB, DBS = revit_stubs.install_revit_stubs(structure_attrs=revit_stubs.rebar_structure_attrs())
DB.XYZ = XYZ
DB.XYZ.BasisZ = XYZ(0, 0, 1)
DB.UV = UV
DB.Line = Line
DB.PlanarFace = PlanarFace
DB.CylindricalFace = CylindricalFace
DB.Solid = Solid
DB.Options = Options
DB.GeometryInstance = type('GeometryInstance', (), {})
DB.ViewDetailLevel = types.SimpleNamespace(Fine=1)
DB.BuiltInParameter = types.SimpleNamespace(
    REBAR_BAR_DIAMETER=1,
    FAMILY_BASE_LEVEL_PARAM='BASE_LEVEL',
    FAMILY_BASE_LEVEL_OFFSET_PARAM='BASE_OFFSET',
    FAMILY_TOP_LEVEL_PARAM='TOP_LEVEL',
    FAMILY_TOP_LEVEL_OFFSET_PARAM='TOP_OFFSET',
)
DB.BuiltInCategory = types.SimpleNamespace(OST_Floors=1, OST_StructuralColumns=2)

DB.FilteredElementCollector = revit_stubs.collector_factory()

revit_stubs.install_system_stubs()

re_engine = revit_stubs.load_module('re_engine_352', _LIB + r'\rebar_engine.py')

column_rebar = revit_stubs.load_module('column_rebar_352', _LIB + r'\column_rebar.py')
column_rebar.re_engine = re_engine
column_rebar._ensure_engine = lambda: re_engine


_load = revit_stubs.load_module

floor_rebar = _load("floor_rebar_352", os.path.join(_LIB, "floor_rebar.py"))


# ── Fix 2: Base/Top Level+Offset Z source, bypassing Join Geometry ──────
base_level = FakeLevel(0.0)         # ground floor, elevation 0
top_level = FakeLevel(10.0)         # 10ft above
doc = FakeDoc({'L_BASE': base_level, 'L_TOP': top_level})
params = {
    'BASE_LEVEL': FakeParam(elem_id='L_BASE'),
    'BASE_OFFSET': FakeParam(value_ft=0.0),
    'TOP_LEVEL': FakeParam(elem_id='L_TOP'),
    'TOP_OFFSET': FakeParam(value_ft=-0.5),   # top offset -0.5ft below Top Level
}
# A solid whose OWN reported geometry is skewed (simulating Join
# Geometry with the foundation cutting into the reported extent) —
# if the fix works, the level-param path is used FIRST and this skewed
# solid is never even consulted.
skewed_solid = Solid([], edges=[])
host = FakeHost(skewed_solid, location=LocationPoint(XYZ(0.0, 0.0, 0.0)),
                bbox=BBoxXYZ(XYZ(-1.0, -1.0, 2.0), XYZ(1.0, 1.0, 3.0)),  # also skewed/wrong
                doc=doc, params=params)
axis = column_rebar.get_column_axis(host)
p0, p1 = axis.GetEndPoint(0), axis.GetEndPoint(1)
lo_z, hi_z = min(p0.Z, p1.Z), max(p0.Z, p1.Z)
eps_ft = column_rebar._AXIS_CLAMP_EPSILON_FT
assert abs(lo_z - (0.0 + eps_ft)) < 1e-9, lo_z
assert abs(hi_z - (9.5 - eps_ft)) < 1e-9, hi_z
print("get_column_axis: Base/Top Level+Offset parameters are used FIRST for Z, "
      "bypassing a Join-Geometry-skewed Solid/BoundingBox entirely: OK")

host_no_params = FakeHost(skewed_solid, location=LocationPoint(XYZ(0.0, 0.0, 0.0)),
                           bbox=BBoxXYZ(XYZ(-1.0, -1.0, 2.0), XYZ(1.0, 1.0, 3.0)),
                           doc=doc, params={})
axis2 = column_rebar.get_column_axis(host_no_params)
p0b, p1b = axis2.GetEndPoint(0), axis2.GetEndPoint(1)
lo_z2, hi_z2 = min(p0b.Z, p1b.Z), max(p0b.Z, p1b.Z)
assert abs(lo_z2 - (2.0 + eps_ft)) < 1e-9
assert abs(hi_z2 - (3.0 - eps_ft)) < 1e-9
print("get_column_axis: missing Base/Top Level params falls back to BoundingBox "
      "unchanged from pre-3.5.2 behaviour: OK")

assert column_rebar._AXIS_CLAMP_EPSILON_MM == 5.0
print("get_column_axis: epsilon raised to 5mm: OK")


# ── Fix 3: crank direction (not just magnitude) ─────────────────────────
seg_end = XYZ(100.0 / _MM_PER_FT, 0.0, 3.0)
inward_dir = XYZ(-1.0, 0.0, 0.0)   # "inward" points toward -X here
axis_dir = XYZ(0.0, 0.0, 1.0)
crank_offset_mm = 30.0             # POSITIVE -> per contract, must shift INWARD (-X)
lines = column_rebar.build_cranked_starter(seg_end, inward_dir, axis_dir,
                                            lap_length_mm=500.0,
                                            crank_offset_mm=crank_offset_mm, crank_slope=6.0)
crank_top = lines[0].GetEndPoint(1)
assert crank_top.X < seg_end.X, (
    "positive crank_offset_mm must shift the point along +inward_dir (here -X), "
    "got X={} (was {})".format(crank_top.X, seg_end.X))
print("build_cranked_starter: a POSITIVE crank_offset_mm now shifts INWARD "
      "(matches its own documented contract) instead of outward: OK")


# ── Fix 4: face-count geometric fallback for a faceted circular column ──
faceted_faces = [FakeFace(XYZ(math.cos(a), math.sin(a), 0.0), XYZ(0, 0, 1.5))
                 for a in [i * 2 * math.pi / 8 for i in range(8)]]  # 8-sided
faceted_solid = Solid(faceted_faces, edges=[])
faceted_host = FakeHost(
    faceted_solid, location=LocationPoint(XYZ(0.0, 0.0, 0.0)),
    bbox=BBoxXYZ(XYZ(-500.0 / _MM_PER_FT, -500.0 / _MM_PER_FT, 0.0),
                 XYZ(500.0 / _MM_PER_FT, 500.0 / _MM_PER_FT, 3.0)),
    doc=doc, params={})
geom = column_rebar.detect_column_geometry(doc, faceted_host)
assert geom is not None and geom['shape'] == 'circle', geom
assert abs(geom['diameter_mm'] - 1000.0) < 1.0, geom
print("detect_column_geometry: an 8-sided FACETED column (no CylindricalFace) "
      "is detected as circular via face-count + bbox, no parameter name needed: OK")

rect_faces = [
    FakeFace(XYZ(1, 0, 0), XYZ(200.0 / _MM_PER_FT, 0, 1.5)),
    FakeFace(XYZ(-1, 0, 0), XYZ(-200.0 / _MM_PER_FT, 0, 1.5)),
    FakeFace(XYZ(0, 1, 0), XYZ(0, 150.0 / _MM_PER_FT, 1.5)),
    FakeFace(XYZ(0, -1, 0), XYZ(0, -150.0 / _MM_PER_FT, 1.5)),
]
rect_solid = Solid(rect_faces, edges=[])
rect_host = FakeHost(rect_solid, location=LocationPoint(XYZ(0.0, 0.0, 0.0)),
                      bbox=BBoxXYZ(XYZ(-1.0, -1.0, 0.0), XYZ(1.0, 1.0, 3.0)),
                      doc=doc, params={})
geom_rect = column_rebar.detect_column_geometry(doc, rect_host)
assert geom_rect is not None and geom_rect['shape'] == 'rect', geom_rect
print("detect_column_geometry: a genuine 4-sided rectangular column is unaffected "
      "by the new >4-sides fallback: OK")


# ── Fix 1: per-edge try/except isolation in floor_rebar ─────────────────
_orig_line_create_bound = Line.CreateBound
_fail_on = {'armed': False}

_POISON_X_FT = 999.0 / _MM_PER_FT

def _flaky_create_bound(p0, p1):
    if _fail_on['armed'] and abs(p0.X - _POISON_X_FT) < 1e-9:
        raise Exception('Internal Error (simulated degenerate curve)')
    return _orig_line_create_bound(p0, p1)

class _FakeTopo(object):
    """Two edges: one 'poisoned' (triggers the simulated Revit
    exception via its Z-anchor X coordinate), one healthy — proves a
    single bad edge is skipped (logged) while the healthy edge still
    produces reinforcement."""
    def polygon_edges_mm(self, loop):
        return [
            ((999.0, 0.0), (999.0, 1000.0), (0.0, 1.0), (1.0, 0.0), 1000.0),
            ((0.0, 0.0), (1000.0, 0.0), (1.0, 0.0), (0.0, 1.0), 1000.0),
        ]
    def point_in_material_mm(self, x, y, outer, holes):
        return True

class _FakeFootingMod(object):
    DB = DB
    @staticmethod
    def _evenly_spaced(lo, hi, spacing):
        return [lo, hi] if hi > lo else [lo]
    @staticmethod
    def add_end_hooks(back, leg, direction, at_start=True, at_end=True):
        return [back]

DB.Line.CreateBound = staticmethod(_flaky_create_bound)
_fail_on['armed'] = True
result = floor_rebar._build_edge_ubars(
    _FakeTopo(), _FakeFootingMod(), DB, [(0, 0), (1000, 0), (1000, 1000), (0, 1000)], [],
    x_leg_mm=200.0, x_spacing_mm=200.0, b1_z_ft=0.0, t1_z_ft=1.0,
    y_leg_mm=200.0, y_spacing_mm=200.0, b2_z_ft=0.0, t2_z_ft=1.0)
_fail_on['armed'] = False
DB.Line.CreateBound = _orig_line_create_bound

total_bars_and_sets = (len(result['x_bars']['bars']) + len(result['x_bars']['sets'])
                        + len(result['y_bars']['bars']) + len(result['y_bars']['sets']))
assert total_bars_and_sets == 1, (
    "expected exactly 1 surviving edge's worth of reinforcement (the poisoned "
    "edge skipped, not aborting the other edge) -> {}".format(result))
print("_build_edge_ubars: a single edge whose curve construction raises is caught, "
      "logged, and skipped via continue -- the OTHER edge's reinforcement survives "
      "instead of the whole floor being lost: OK")

print("\nALL PHASE 3.5.2 TARGETED CHECKS PASSED")
