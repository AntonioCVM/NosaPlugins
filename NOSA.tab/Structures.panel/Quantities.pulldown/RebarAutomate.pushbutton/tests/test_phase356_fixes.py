# -*- coding: utf-8 -*-
"""Targeted checks for the 4 Phase 3.5.6 live-Revit fixes: analytical
column cross-section (b/h + Location.Rotation) as PRIMARY with the
face-based path kept as fallback, isolated-solid footing bbox
(excluding nested pile geometry), a console warning for a
self-intersecting hole offset, and the 50mm crosstie Z-epsilon at zone
boundaries."""
import math
import sys
import os
import types

_MM_PER_FT = 304.8
_LIB = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'lib'))
_EXT_LIB = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', '..', 'lib'))
if _EXT_LIB not in sys.path:
    sys.path.insert(0, _EXT_LIB)
from tests_support import revit_stubs  # noqa: E402


_load = revit_stubs.load_module


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

class FakeEdge(object):
    def __init__(self, p0, p1):
        self._p0, self._p1 = p0, p1
    def AsCurve(self):
        return self
    def GetEndPoint(self, i):
        return self._p0 if i == 0 else self._p1

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

class BBoxXYZ(object):
    def __init__(self, mn, mx):
        self.Min, self.Max = mn, mx

class LocationPoint(object):
    def __init__(self, point, rotation=None):
        self.Point = point
        self.Rotation = rotation

class GeometryInstance(object):
    def __init__(self, nested_solids):
        self._nested = nested_solids
    def GetInstanceGeometry(self):
        return self._nested

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
    def LookupParameter(self, name):
        return self._params.get(name)


DB, DBS = revit_stubs.install_revit_stubs(structure_attrs=revit_stubs.rebar_structure_attrs())
DB.XYZ = XYZ
DB.XYZ.BasisZ = XYZ(0, 0, 1)
DB.XYZ.BasisX = XYZ(1, 0, 0)
DB.UV = UV
DB.Line = Line
DB.PlanarFace = PlanarFace
DB.CylindricalFace = CylindricalFace
DB.Solid = Solid
DB.Options = Options
DB.GeometryInstance = GeometryInstance
DB.ViewDetailLevel = types.SimpleNamespace(Fine=1)

DB.ElementId = revit_stubs.element_id_namespace()

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

DB.FilteredElementCollector = revit_stubs.collector_factory()

revit_stubs.install_system_stubs()

re_engine = revit_stubs.load_module('re_engine_356', _LIB + r'\rebar_engine.py')

column_rebar = revit_stubs.load_module('column_rebar_356', _LIB + r'\column_rebar.py')
column_rebar.re_engine = re_engine
column_rebar._ensure_engine = lambda: re_engine

footing_rebar = revit_stubs.load_module('footing_rebar_356', _LIB + r'\footing_rebar.py')
footing_rebar.re_engine = re_engine
footing_rebar._ensure_engine = lambda: re_engine

floor_rebar = _load("floor_rebar_356", os.path.join(_LIB, "floor_rebar.py"))
slab_topology = _load("slab_topology_356", os.path.join(_LIB, "slab_topology.py"))


# ══════════════════════════════════════════════════════════════════════════
# Fix 1 — analytical column section (b/h + Location.Rotation), PRIMARY,
# face-based path kept as fallback
# ══════════════════════════════════════════════════════════════════════════

# A column JOINED to a floor (simulated: its Solid exposes some
# arbitrary/broken face count, NOT exactly 4 — the exact live failure
# mode) but WITH b/h type params and a real Location.Rotation. The
# analytical path must succeed WITHOUT ever needing _column_faces to
# resolve at all.
axis = column_rebar.DB.Line.CreateBound(XYZ(0, 0, 0), XYZ(0, 0, 10.0))
broken_faces = [FakeFace(XYZ(1, 0, 0), XYZ(1, 0, 1))]  # only 1 side face -- a join artefact
broken_solid = Solid(broken_faces)
rotated_host = FakeHost(broken_solid, location=LocationPoint(XYZ(0, 0, 0), rotation=math.pi / 6.0),
                         params={'b': FakeParam(value_ft=400.0 / _MM_PER_FT),
                                 'h': FakeParam(value_ft=600.0 / _MM_PER_FT)})

doc356 = FakeDoc()
cover_mgr_broken = re_engine.CoverGeometryManager(doc356, rotated_host)
source = column_rebar._resolve_column_geometry_source(rotated_host, axis, cover_mgr_broken)
assert source['kind'] == 'analytical', source
expected_u = math.cos(math.pi / 6.0)
assert abs(source['u_dir'].X - expected_u) < 1e-9
half_w, half_d = column_rebar._half_extents_from_source(re_engine, axis, source, 40.0)
assert abs(half_w - (200.0 - 40.0)) < 1e-6, half_w
assert abs(half_d - (300.0 - 40.0)) < 1e-6, half_d
print("_resolve_column_geometry_source: b/h + Location.Rotation resolve the section "
      "analytically even when the Solid's own face count is broken by a join: OK")

# A column with NO b/h params and NO rotation must fall back to the
# face-based path (_column_faces) -- verifies the safety net is intact,
# not deleted.
rect_faces = [
    FakeFace(XYZ(1, 0, 0), XYZ(200.0 / _MM_PER_FT, 0, 1.5)),
    FakeFace(XYZ(-1, 0, 0), XYZ(-200.0 / _MM_PER_FT, 0, 1.5)),
    FakeFace(XYZ(0, 1, 0), XYZ(0, 150.0 / _MM_PER_FT, 1.5)),
    FakeFace(XYZ(0, -1, 0), XYZ(0, -150.0 / _MM_PER_FT, 1.5)),
]
plain_host = FakeHost(Solid(rect_faces), location=LocationPoint(XYZ(0, 0, 0)), params={})
cover_mgr_plain = re_engine.CoverGeometryManager(doc356, plain_host)
source2 = column_rebar._resolve_column_geometry_source(plain_host, axis, cover_mgr_plain)
assert source2['kind'] == 'faces', source2
print("_resolve_column_geometry_source: falls back to the face-based path (unchanged, "
      "not deleted) when b/h/Rotation aren't available: OK")

# detect_column_geometry: analytical b/h beats a broken face count too.
geom = column_rebar.detect_column_geometry(doc356, rotated_host)
assert geom == {'shape': 'rect', 'width_mm': 400.0, 'depth_mm': 600.0}, geom
print("detect_column_geometry: analytical b/h resolves the preview shape directly, "
      "never touching the column's (broken) Solid.Faces at all: OK")


# ══════════════════════════════════════════════════════════════════════════
# Fix 2 — isolated-solid footing bbox (excludes nested pile geometry)
# ══════════════════════════════════════════════════════════════════════════

cap_solid = Solid(edges=[
    FakeEdge(XYZ(-1000.0 / _MM_PER_FT, -1000.0 / _MM_PER_FT, 0.0),
             XYZ(1000.0 / _MM_PER_FT, 1000.0 / _MM_PER_FT, -600.0 / _MM_PER_FT)),
], volume=2.0)
# A pile nested INSIDE the pile-cap family, reaching far below the cap
# (e.g. -8000mm) -- this is the exact "piles nested inside a pile-cap
# family" scenario. Larger volume than the cap on purpose, to also
# exercise get_host_solid(include_nested=False)'s own exclusion.
pile_solid = Solid(edges=[
    FakeEdge(XYZ(0.0, 0.0, 0.0), XYZ(0.0, 0.0, -8000.0 / _MM_PER_FT)),
], volume=50.0)
pile_instance = GeometryInstance([pile_solid])
cap_host = FakeHost(None)
cap_host.get_Geometry = lambda opts: [cap_solid, pile_instance]
cap_host._bbox = BBoxXYZ(XYZ(-1000.0 / _MM_PER_FT, -1000.0 / _MM_PER_FT, -8000.0 / _MM_PER_FT),
                          XYZ(1000.0 / _MM_PER_FT, 1000.0 / _MM_PER_FT, 0.0))  # whole-instance, includes pile

isolated_bbox = re_engine.get_isolated_solid_bbox(cap_host)
assert isolated_bbox is not None
assert abs(isolated_bbox.Min.Z - (-600.0 / _MM_PER_FT)) < 1e-6, isolated_bbox.Min.Z
print("get_isolated_solid_bbox: Min.Z sits at the cap's OWN underside (-600mm), not "
      "the nested pile's tip (-8000mm) -- get_host_solid(include_nested=False) "
      "correctly excludes the GeometryInstance: OK")

whole_bbox = cap_host.get_BoundingBox(None)
assert whole_bbox.Min.Z < isolated_bbox.Min.Z, "sanity: whole-instance bbox really is deeper"
print("get_isolated_solid_bbox: confirmed strictly shallower than "
      "host.get_BoundingBox(None) for this nested-pile scenario (the bug being fixed): OK")

footing_result = footing_rebar._footing_bbox(cap_host)
assert abs(footing_result.Min.Z - (-600.0 / _MM_PER_FT)) < 1e-6
print("footing_rebar._footing_bbox: uses the isolated solid, not the whole-element "
      "bbox, as the drop-in replacement at all 4 call sites: OK")

# No top-level solid at all (pathological) -> fall back to whole bbox.
nested_only_host = FakeHost(None)
nested_only_host.get_Geometry = lambda opts: [pile_instance]
nested_only_host._bbox = BBoxXYZ(XYZ(0, 0, -1.0), XYZ(1.0, 1.0, 0.0))
fallback_result = footing_rebar._footing_bbox(nested_only_host)
assert fallback_result is nested_only_host._bbox
print("footing_rebar._footing_bbox: falls back to host.get_BoundingBox(None) when no "
      "top-level solid exists at all, unchanged from pre-3.5.6 behaviour: OK")


# ══════════════════════════════════════════════════════════════════════════
# Fix 3 — self-intersecting hole offset warning
# ══════════════════════════════════════════════════════════════════════════

class _FakeTopoBowtie(object):
    """Simulates offset_polygon_mm collapsing a narrow-notched hole
    into a near-degenerate result: polygon_edges_mm returns only 2
    valid edges for the (is_hole=True) loop, 4 for the outer."""
    def polygon_edges_mm(self, loop):
        if len(loop) == 3:  # our fake "collapsed hole" marker
            return [((0, 0), (100, 0), (1, 0), (0, 1), 100.0),
                     ((100, 0), (0, 0), (-1, 0), (0, -1), 100.0)]
        return [((0, 0), (1000, 0), (1, 0), (0, 1), 1000.0),
                ((1000, 0), (1000, 1000), (0, 1), (-1, 0), 1000.0),
                ((1000, 1000), (0, 1000), (-1, 0), (0, -1), 1000.0),
                ((0, 1000), (0, 0), (0, -1), (1, 0), 1000.0)]
    def point_in_material_mm(self, x, y, outer, holes):
        return True

class _FakeFootingModBowtie(object):
    DB = DB
    @staticmethod
    def _evenly_spaced(lo, hi, spacing):
        return [lo, hi] if hi > lo else [lo]
    @staticmethod
    def add_end_hooks(back, leg, direction, at_start=True, at_end=True):
        return [back]

collapsed_hole = [(0, 0), (50, 5), (100, 0)]  # 3 points -> triggers the fake's bowtie path
result = floor_rebar._build_edge_ubars(
    _FakeTopoBowtie(), _FakeFootingModBowtie(), DB,
    [(0, 0), (1000, 0), (1000, 1000), (0, 1000)], [collapsed_hole],
    x_leg_mm=200.0, x_spacing_mm=200.0, b1_z_ft=0.0, t1_z_ft=1.0,
    y_leg_mm=200.0, y_spacing_mm=200.0, b2_z_ft=0.0, t2_z_ft=1.0)
assert result is not None  # ran to completion, no exception -- the warning is print-only
print("_build_edge_ubars: a hole loop producing < 3 valid edges after offset prints a "
      "self-intersection warning and continues (verified by not raising / hanging): OK")


# ══════════════════════════════════════════════════════════════════════════
# Fix 4 — 50mm crosstie Z-epsilon at zone boundaries
# ══════════════════════════════════════════════════════════════════════════

axis2 = column_rebar.DB.Line.CreateBound(XYZ(0.0, 0.0, 0.0), XYZ(0.0, 0.0, 10.0))
u_dir2, v_dir2 = XYZ(1, 0, 0), XYZ(0, 1, 0)
zones2 = [
    {'start_mm': 0.0, 'end_mm': 1000.0, 'spacing_mm': 250.0},
    {'start_mm': 1000.0, 'end_mm': 5000.0, 'spacing_mm': 500.0},
    {'start_mm': 5000.0, 'end_mm': 6000.0, 'spacing_mm': 250.0},
]
# 2026-10-02: interior ties are Sets following the link zones, lifted one link diameter
# above the links (never coplanar with them) and ending inside their zone.
sets2 = column_rebar.build_crosstie_sets(axis2, u_dir2, v_dir2, 150.0, 100.0, 5, 2, zones2,
                                         layout='all', link_diameter_mm=10.0)['interior_stirrup_sets']
by_zone = {}
for s in sets2:
    z_mm = s['curves'][0].GetEndPoint(0).Z * _MM_PER_FT
    by_zone.setdefault(round(z_mm, 6), []).append(s)
assert sorted(by_zone) == [round(z['start_mm'] + 10.0, 6) for z in zones2], sorted(by_zone)
for z in zones2:
    for s in by_zone[round(z['start_mm'] + 10.0, 6)]:
        assert abs(s['array_length_mm'] - (z['end_mm'] - z['start_mm'] - 10.0)) < 1e-6
        assert s['spacing_mm'] == z['spacing_mm']
print("build_crosstie_sets: interior Sets start one link diameter above each zone start, "
      "share its spacing and end inside it: OK")

print("\nALL PHASE 3.5.6 TARGETED CHECKS PASSED")
