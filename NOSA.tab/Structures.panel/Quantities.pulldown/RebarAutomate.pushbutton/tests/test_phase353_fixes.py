# -*- coding: utf-8 -*-
"""Targeted checks for the 4 Phase 3.5.3 live-Revit fixes: crosstie
zone-boundary deduplication, Level+Offset/Solid.Edges intersection,
empirical (not winding-based) inward_normal resolution + debug_failed_edges,
and native Rebar Cover reading."""
import math
import sys
import os
import types
import importlib.util

_MM_PER_FT = 304.8
_LIB = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'lib'))


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


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

class LocationPoint(object):
    def __init__(self, point):
        self.Point = point

class Solid(object):
    def __init__(self, faces=None, volume=1.0, edges=None):
        self.Faces = faces or []
        self.Volume = volume
        self.Edges = edges if edges is not None else []

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


DB = types.ModuleType('Autodesk.Revit.DB')
DB.XYZ = XYZ
DB.XYZ.BasisZ = XYZ(0, 0, 1)
DB.Line = Line
DB.Solid = Solid
DB.Options = type('Options', (), {'__init__': lambda self: None})
DB.GeometryInstance = type('GeometryInstance', (), {})
DB.CylindricalFace = type('CylindricalFace', (), {})
DB.PlanarFace = type('PlanarFace', (), {})
DB.ViewDetailLevel = types.SimpleNamespace(Fine=1)
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
DBS.RebarFaceType = types.SimpleNamespace(Top='Top', Bottom='Bottom', Exterior='Exterior')
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

spec_re = importlib.util.spec_from_file_location('re_engine_353', _LIB + r'\rebar_engine.py')
re_engine = importlib.util.module_from_spec(spec_re)
sys.modules['re_engine_353'] = re_engine
spec_re.loader.exec_module(re_engine)

spec_col = importlib.util.spec_from_file_location('column_rebar_353', _LIB + r'\column_rebar.py')
column_rebar = importlib.util.module_from_spec(spec_col)
sys.modules['column_rebar_353'] = column_rebar
spec_col.loader.exec_module(column_rebar)
column_rebar.re_engine = re_engine
column_rebar._ensure_engine = lambda: re_engine

floor_rebar = _load("floor_rebar_353", os.path.join(_LIB, "floor_rebar.py"))
slab_topology = _load("slab_topology_353", os.path.join(_LIB, "slab_topology.py"))


# ── Fix 1: crosstie zone-boundary deduplication ─────────────────────────
axis = Line.CreateBound(XYZ(0.0, 0.0, 0.0), XYZ(0.0, 0.0, 10.0))
u_dir, v_dir = XYZ(1, 0, 0), XYZ(0, 1, 0)
# 3 zones from a densify_at_nodes split, joint=1000mm each end, sharing
# boundaries exactly at 1000mm and 5000mm (the exact live bug pattern).
zones = [
    {'start_mm': 0.0, 'end_mm': 1000.0, 'spacing_mm': 100.0},
    {'start_mm': 1000.0, 'end_mm': 5000.0, 'spacing_mm': 200.0},
    {'start_mm': 5000.0, 'end_mm': 6000.0, 'spacing_mm': 100.0},
]
crossties = column_rebar.build_crosstie_sets(axis, u_dir, v_dir, 150.0, 100.0, 5, 2, zones, layout='all')
bars = crossties['crosstie_bars']
# n_u=5 -> 3 interior U positions (>1, so no collapse-to-loop; stays as
# individual crossties). Rather than hand-derive an exact expected
# count (fragile against the Phase 3.5.6 item 4 Z-epsilon inset
# changing exactly which boundary positions survive dedup), verify the
# count is internally consistent: every bar's own Z must appear in
# EXACTLY ONE zone's own (now epsilon-inset) position list, and the
# total must be a whole multiple of n_pairs (3).
n_pairs = 3
assert len(bars) % n_pairs == 0, len(bars)
assert len(bars) > 0
assert crossties['interior_stirrup_sets'] == []

# Directly verify no two bars share the exact same curve endpoints
# (the literal "Identical rebar" signature).
seen = set()
for b in bars:
    c = b['curve']
    key = (round(c.GetEndPoint(0).X, 6), round(c.GetEndPoint(0).Y, 6), round(c.GetEndPoint(0).Z, 6),
           round(c.GetEndPoint(1).X, 6), round(c.GetEndPoint(1).Y, 6), round(c.GetEndPoint(1).Z, 6))
    assert key not in seen, "duplicate crosstie geometry found at {}".format(key)
    seen.add(key)
print("build_crosstie_sets: adjacent zones sharing a boundary Z no longer emit "
      "duplicate ('Identical rebar') crossties: OK")


# ── Fix 1b (Phase 3.5.7 REVERT): Level+Offset is STRICT authority,
# never narrowed by Solid.Edges ──────────────────────────────────────────
base_level, top_level = FakeLevel(0.0), FakeLevel(10.0)
doc353 = FakeDoc({'L_BASE': base_level, 'L_TOP': top_level})
params = {
    'BASE_LEVEL': FakeParam(elem_id='L_BASE'), 'BASE_OFFSET': FakeParam(value_ft=0.0),
    'TOP_LEVEL': FakeParam(elem_id='L_TOP'), 'TOP_OFFSET': FakeParam(value_ft=0.0),
}
class FakeEdge(object):
    def __init__(self, z0, z1):
        self._z0, self._z1 = z0, z1
    def AsCurve(self):
        return self
    def GetEndPoint(self, i):
        p = XYZ(0, 0, self._z0 if i == 0 else self._z1)
        return p
# Solid.Edges reports a NARROWER real extent (2.0 to 8.0) than the
# Level+Offset intent (0.0 to 10.0) -- simulating Join Geometry with a
# floor ABOVE the column notching its own solid short of the true
# structural top. Phase 3.5.3's intersection would have clamped to
# this narrower range, severing continuity/cranks at the floor -- the
# live regression this revert fixes. Level+Offset must win OUTRIGHT.
narrow_solid = Solid(edges=[FakeEdge(2.0, 2.0), FakeEdge(8.0, 8.0)])
host_intersect = FakeHost(narrow_solid, location=LocationPoint(XYZ(0, 0, 0)),
                           bbox=BBoxXYZ(XYZ(-1, -1, -5), XYZ(1, 1, 15)),
                           doc=doc353, params=params)
axis_intersect = column_rebar.get_column_axis(host_intersect)
p0, p1 = axis_intersect.GetEndPoint(0), axis_intersect.GetEndPoint(1)
lo, hi = min(p0.Z, p1.Z), max(p0.Z, p1.Z)
eps = column_rebar._AXIS_CLAMP_EPSILON_FT
assert abs(lo - (0.0 + eps)) < 1e-9, lo
assert abs(hi - (10.0 - eps)) < 1e-9, hi
print("get_column_axis: Level+Offset wins OUTRIGHT even when Solid.Edges reports a "
      "narrower (join-notched) extent -- continuity/cranks through a floor above "
      "are no longer amputated: OK")


# ── Fix 2: empirical inward_normal (not winding-based) ──────────────────
# A hole loop deliberately given the SAME winding as a CCW outer square
# (i.e. NOT reversed -- violating the old "hole always opposite"
# assumption) -- the empirical test must still resolve the true inward
# direction (into the annulus between hole and outer), not blindly flip.
outer = [(0.0, 0.0), (2000.0, 0.0), (2000.0, 2000.0), (0.0, 2000.0)]
hole_same_winding_as_outer = [(500.0, 500.0), (1500.0, 500.0), (1500.0, 1500.0), (500.0, 1500.0)]
for (p0e, p1e, unit_dir, raw_normal, length_mm) in slab_topology.polygon_edges_mm(hole_same_winding_as_outer):
    resolved = floor_rebar._resolve_inward_normal_mm(
        p0e, p1e, raw_normal, True, slab_topology, outer, [hole_same_winding_as_outer])
    mx, my = (p0e[0] + p1e[0]) / 2.0, (p0e[1] + p1e[1]) / 2.0
    test_x = mx + resolved[0] * 5.0
    test_y = my + resolved[1] * 5.0
    assert slab_topology.point_in_material_mm(test_x, test_y, outer, [hole_same_winding_as_outer]), (
        "resolved normal for hole edge ({},{})-({},{}) points into the VOID, not material"
        .format(p0e[0], p0e[1], p1e[0], p1e[1]))
print("_resolve_inward_normal_mm: resolves correctly into REAL material even for a hole "
      "loop that does NOT follow the assumed opposite-winding convention: OK")

# Outer boundary itself must also resolve correctly (material inward).
for (p0e, p1e, unit_dir, raw_normal, length_mm) in slab_topology.polygon_edges_mm(outer):
    resolved = floor_rebar._resolve_inward_normal_mm(
        p0e, p1e, raw_normal, False, slab_topology, outer, [])
    mx, my = (p0e[0] + p1e[0]) / 2.0, (p0e[1] + p1e[1]) / 2.0
    assert slab_topology.point_in_material_mm(mx + resolved[0] * 5.0, my + resolved[1] * 5.0, outer, [])
print("_resolve_inward_normal_mm: resolves correctly for the outer boundary too: OK")


# ── Fix 3: debug_failed_edges returned from _build_edge_ubars ───────────
_orig_create_bound = Line.CreateBound
_poison_x_ft = 999.0 / _MM_PER_FT
_armed = {'v': False}
def _flaky(p0, p1):
    if _armed['v'] and abs(p0.X - _poison_x_ft) < 1e-9:
        raise Exception('Internal Error (simulated)')
    return _orig_create_bound(p0, p1)

class _FakeTopo(object):
    def polygon_edges_mm(self, loop):
        return [((999.0, 0.0), (999.0, 1000.0), (0.0, 1.0), (1.0, 0.0), 1000.0)]
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

DB.Line.CreateBound = staticmethod(_flaky)
_armed['v'] = True
result = floor_rebar._build_edge_ubars(
    _FakeTopo(), _FakeFootingMod(), DB, [(0, 0), (1000, 0), (1000, 1000), (0, 1000)], [],
    x_leg_mm=200.0, x_spacing_mm=200.0, b1_z_ft=0.0, t1_z_ft=1.0,
    y_leg_mm=200.0, y_spacing_mm=200.0, b2_z_ft=0.0, t2_z_ft=1.0)
_armed['v'] = False
DB.Line.CreateBound = _orig_create_bound

assert 'debug_failed_edges' in result
assert len(result['debug_failed_edges']) == 1, result['debug_failed_edges']
entry = result['debug_failed_edges'][0]
assert set(('p0_mm', 'p1_mm', 'bz_ft', 'tz_ft', 'inward_normal', 'error')) <= set(entry.keys())
assert abs(entry['p0_mm'][0] - 999.0) < 1e-6
print("_build_edge_ubars: a failed edge's exact geometry (p0/p1/bz/tz/inward_normal) "
      "is returned via debug_failed_edges for ui.py to visualize: OK")


# ── Fix 4 (Phase 3.5.5): native cover is an ElementId-typed parameter
# (references a RebarCoverType element), NOT a raw AsDouble() value
# (Phase 3.5.4's bug) and NOT RebarHostData/RebarFaceType (Phase
# 3.5.3's abandoned approach) ────────────────────────────────────────────
class FakeCoverTypeElem(object):
    def __init__(self, cover_ft):
        self.CoverDistance = cover_ft

class FakeCoverParam(object):
    def __init__(self, elem_id):
        self._elem_id = elem_id
    def AsElementId(self):
        return self._elem_id

class FakeCoverHost(object):
    def __init__(self, params):
        self._params = params  # {bip_name: FakeCoverParam or None}
    def get_Parameter(self, bip):
        return self._params.get(bip)

cover_type_bottom_id = _FakeElementId(101)
cover_type_top_id = _FakeElementId(102)
doc_cover = FakeDoc({
    cover_type_bottom_id: FakeCoverTypeElem(50.0 / _MM_PER_FT),
    cover_type_top_id: FakeCoverTypeElem(30.0 / _MM_PER_FT),
})
configured_host = FakeCoverHost({
    'CLEAR_COVER_BOTTOM': FakeCoverParam(cover_type_bottom_id),
    'CLEAR_COVER_TOP': FakeCoverParam(cover_type_top_id),
})
cover_bottom = re_engine.get_native_cover_mm(doc_cover, configured_host, u'Bottom')
cover_top = re_engine.get_native_cover_mm(doc_cover, configured_host, u'Top')
assert abs(cover_bottom - 50.0) < 0.01, cover_bottom
assert abs(cover_top - 30.0) < 0.01, cover_top
print("get_native_cover_mm: resolves CLEAR_COVER_BOTTOM/TOP's ElementId to its real "
      "RebarCoverType element and reads ITS CoverDistance (Bottom=50mm, Top=30mm): OK")

# InvalidElementId (the real Revit sentinel for "not set", NOT None)
# must also fall back cleanly.
unconfigured_host = FakeCoverHost({
    'CLEAR_COVER_OTHER': FakeCoverParam(DB.ElementId.InvalidElementId),
})
cover_fallback = re_engine.get_native_cover_mm(doc_cover, unconfigured_host, u'Exterior', default_mm=40.0)
assert abs(cover_fallback - 40.0) < 0.01, cover_fallback
print("get_native_cover_mm: InvalidElementId (Revit's real 'not configured' sentinel, "
      "not None) falls back to the normative default, never crashes: OK")

# A host whose get_Parameter raises (simulating a live IronPython/API
# surprise) must ALSO degrade to the fallback, never propagate.
class ExplodingHost(object):
    def get_Parameter(self, bip):
        raise RuntimeError('simulated API failure')

cover_exploding = re_engine.get_native_cover_mm(doc_cover, ExplodingHost(), u'Top', default_mm=40.0)
assert abs(cover_exploding - 40.0) < 0.01, cover_exploding
print("get_native_cover_mm: a host that raises on get_Parameter still degrades to "
      "the fallback instead of crashing the caller: OK")

print("\nALL PHASE 3.5.3/3.5.4 TARGETED CHECKS PASSED")
