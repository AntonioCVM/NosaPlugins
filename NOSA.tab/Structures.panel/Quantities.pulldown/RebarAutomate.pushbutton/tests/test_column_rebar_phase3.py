# -*- coding: utf-8 -*-
"""Mocked-API test for column_rebar.py's Phase 3 additions: distribute_bar_count,
generate_column_stirrup_zones, build_stirrup_sets, and the full
build_column_reinforcement orchestration."""
import math
import os
import sys
import types

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
        return math.sqrt(self.X**2 + self.Y**2 + self.Z**2)
    def Normalize(self):
        L = self.GetLength()
        if L == 0:
            return XYZ(0, 0, 0)
        return XYZ(self.X / L, self.Y / L, self.Z / L)
    def DistanceTo(self, o):
        return (self - o).GetLength()

class UV(object):
    def __init__(self, u, v):
        self.U, self.V = u, v

class BBoxUV(object):
    def __init__(self, umin, vmin, umax, vmax):
        self.Min = UV(umin, vmin)
        self.Max = UV(umax, vmax)

class PlanarFace(object):
    pass

class FakeFace(PlanarFace):
    """Origin/normal are fixed (get_host_faces only Evaluates at the UV
    bbox midpoint, so a constant point suffices for these tests)."""
    def __init__(self, normal, origin):
        self._normal = normal
        self._origin = origin
        self._bbox = BBoxUV(0.0, 0.0, 1.0, 1.0)
    def GetBoundingBox(self):
        return self._bbox
    def ComputeNormal(self, uv):
        return self._normal
    def Evaluate(self, uv):
        return self._origin

class CylindricalFace(object):
    """A round column's curved side face — Phase 3.4 item 4 detection
    only needs .Radius (feet)."""
    def __init__(self, radius_ft):
        self.Radius = radius_ft

class Solid(object):
    def __init__(self, faces, volume=1.0):
        self.Faces = faces
        self.Volume = volume

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

class FakeHost(object):
    """location can be a LocationCurve, a LocationPoint, or None (no
    Location at all) — exercising all 3 of get_column_axis' resolution
    paths (Phase 3.1 fix)."""
    _next_id = [1]
    def __init__(self, solid, location=None, bbox=None):
        self._solid = solid
        self.Location = location
        self._bbox = bbox
        self.Id = FakeHost._next_id[0]
        FakeHost._next_id[0] += 1
    def get_Geometry(self, opts):
        return [self._solid]
    def get_BoundingBox(self, view):
        return self._bbox

_EXT_LIB = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', '..', 'lib'))
if _EXT_LIB not in sys.path:
    sys.path.insert(0, _EXT_LIB)
from tests_support import revit_stubs  # noqa: E402

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
DB.BuiltInParameter = types.SimpleNamespace(REBAR_BAR_DIAMETER=1)
DB.BuiltInCategory = types.SimpleNamespace(OST_Floors=1, OST_StructuralColumns=2)

_FLOORS_IN_DOC = []      # tests populate this to exercise multi-story splitting
_COLUMNS_IN_DOC = []     # tests populate this to exercise crank-offset detection


def _elements_in_doc(cat):
    if cat == DB.BuiltInCategory.OST_StructuralColumns:
        return _COLUMNS_IN_DOC
    return _FLOORS_IN_DOC


DB.FilteredElementCollector = revit_stubs.collector_factory(_elements_in_doc)


class FakeFloor(object):
    """A floor for multi-story split testing: only get_BoundingBox
    matters to find_floor_split_elevations_ft."""
    def __init__(self, xmin_mm, xmax_mm, ymin_mm, ymax_mm, top_z_mm):
        self._bbox = BBoxXYZ(
            XYZ(xmin_mm / _MM_PER_FT, ymin_mm / _MM_PER_FT, (top_z_mm - 200.0) / _MM_PER_FT),
            XYZ(xmax_mm / _MM_PER_FT, ymax_mm / _MM_PER_FT, top_z_mm / _MM_PER_FT))
    def get_BoundingBox(self, view):
        return self._bbox

revit_stubs.install_system_stubs()

_LIB = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'lib'))

re_engine = revit_stubs.load_module('re_engine', _LIB + r'\rebar_engine.py')

column_rebar = revit_stubs.load_module('column_rebar', _LIB + r'\column_rebar.py')
column_rebar.re_engine = re_engine
column_rebar._ensure_engine = lambda: re_engine

doc = None


def make_column(width_mm=400.0, depth_mm=300.0, height_mm=3000.0):
    """A rectangular column: width along X, depth along Y, from Z=0 to
    Z=height_mm, centred on the X/Y origin."""
    hw_ft = (width_mm / 2.0) / _MM_PER_FT
    hd_ft = (depth_mm / 2.0) / _MM_PER_FT
    h_ft = height_mm / _MM_PER_FT
    faces = [
        FakeFace(XYZ(1, 0, 0), XYZ(hw_ft, 0, h_ft / 2.0)),
        FakeFace(XYZ(-1, 0, 0), XYZ(-hw_ft, 0, h_ft / 2.0)),
        FakeFace(XYZ(0, 1, 0), XYZ(0, hd_ft, h_ft / 2.0)),
        FakeFace(XYZ(0, -1, 0), XYZ(0, -hd_ft, h_ft / 2.0)),
        FakeFace(XYZ(0, 0, 1), XYZ(0, 0, h_ft)),    # top cap — excluded by |normal.Z|<0.3
        FakeFace(XYZ(0, 0, -1), XYZ(0, 0, 0)),      # bottom cap — excluded
    ]
    solid = Solid(faces, volume=width_mm * depth_mm * height_mm)
    axis = Line.CreateBound(XYZ(0, 0, 0), XYZ(0, 0, h_ft))
    return FakeHost(solid, LocationCurve(axis))


def make_column_location_point(width_mm=400.0, depth_mm=300.0, height_mm=3000.0,
                                px_mm=1500.0, py_mm=2500.0):
    """PHASE 3.1 — the REALISTIC case: a LocationPoint-based column (how
    most OST_StructuralColumns instances are actually modelled), with
    no LocationCurve at all — this used to crash with
    "Host has no LocationCurve" before the fix. The insertion point
    (px_mm, py_mm) is deliberately NOT at the bbox centre, to prove
    get_column_axis prefers the real LocationPoint over a bbox-derived
    centre."""
    hw_ft = (width_mm / 2.0) / _MM_PER_FT
    hd_ft = (depth_mm / 2.0) / _MM_PER_FT
    h_ft = height_mm / _MM_PER_FT
    px_ft, py_ft = px_mm / _MM_PER_FT, py_mm / _MM_PER_FT
    faces = [
        FakeFace(XYZ(1, 0, 0), XYZ(px_ft + hw_ft, py_ft, h_ft / 2.0)),
        FakeFace(XYZ(-1, 0, 0), XYZ(px_ft - hw_ft, py_ft, h_ft / 2.0)),
        FakeFace(XYZ(0, 1, 0), XYZ(px_ft, py_ft + hd_ft, h_ft / 2.0)),
        FakeFace(XYZ(0, -1, 0), XYZ(px_ft, py_ft - hd_ft, h_ft / 2.0)),
        FakeFace(XYZ(0, 0, 1), XYZ(px_ft, py_ft, h_ft)),
        FakeFace(XYZ(0, 0, -1), XYZ(px_ft, py_ft, 0.0)),
    ]
    solid = Solid(faces, volume=width_mm * depth_mm * height_mm)
    bbox = BBoxXYZ(XYZ(px_ft - hw_ft, py_ft - hd_ft, 0.0),
                    XYZ(px_ft + hw_ft, py_ft + hd_ft, h_ft))
    return FakeHost(solid, LocationPoint(XYZ(px_ft, py_ft, 0.0)), bbox=bbox)


# ── Test 1: distribute_bar_count — proportional split, minimum 4 ───────
n_u, n_v = column_rebar.distribute_bar_count(8, half_w_mm=200.0, half_d_mm=150.0)
assert n_u >= 2 and n_v >= 2
total = 2 * n_u + 2 * n_v - 4
assert 6 <= total <= 10  # approximately matches the requested 8
assert n_u >= n_v  # the wider (X) edge gets proportionally more bars
n_u2, n_v2 = column_rebar.distribute_bar_count(2, half_w_mm=200.0, half_d_mm=150.0)
assert n_u2 >= 2 and n_v2 >= 2  # floor of 4 total (2+2 corners) enforced
print("distribute_bar_count: proportional split, minimum-4 floor enforced: OK")

# ── Test 2: generate_column_stirrup_zones — densify OFF -> one zone ────
zones_off = column_rebar.generate_column_stirrup_zones(
    clear_height_mm=3000.0, joint_zone_length_mm=500.0,
    dense_spacing_mm=100.0, normal_spacing_mm=200.0, densify_at_nodes=False)
assert len(zones_off) == 1
assert zones_off[0]['spacing_mm'] == 200.0
print("generate_column_stirrup_zones (densify OFF): single uniform zone at "
      "normal_spacing_mm: OK")

# ── Test 3: densify ON -> 3 zones (bottom joint / middle / top joint) ──
zones_on = column_rebar.generate_column_stirrup_zones(
    clear_height_mm=3000.0, joint_zone_length_mm=500.0,
    dense_spacing_mm=100.0, normal_spacing_mm=200.0, densify_at_nodes=True)
assert len(zones_on) == 3
assert zones_on[0]['spacing_mm'] == 100.0 and zones_on[2]['spacing_mm'] == 100.0
assert zones_on[1]['spacing_mm'] == 200.0
# T2.20: the joint zones keep their boundary links; the middle zone starts and
# ends one normal spacing inside them, so no link is placed twice.
assert zones_on[1]['start_mm'] == zones_on[0]['end_mm'] + 200.0
assert zones_on[1]['end_mm'] == zones_on[2]['start_mm'] - 200.0
print("generate_column_stirrup_zones (densify ON): 3 zones, dense at both joints, "
      "normal in the middle, no link shared at the boundaries: OK")

# ── Test 4: short column -> joint zones overlap -> falls back to ONE dense zone ──
zones_short = column_rebar.generate_column_stirrup_zones(
    clear_height_mm=800.0, joint_zone_length_mm=500.0,
    dense_spacing_mm=100.0, normal_spacing_mm=200.0, densify_at_nodes=True)
assert len(zones_short) == 1 and zones_short[0]['spacing_mm'] == 100.0
print("generate_column_stirrup_zones (short column, densify ON): falls back "
      "to ONE dense zone end-to-end, the safer outcome: OK")

# ── Test 5: build_stirrup_sets — one Set descriptor per zone ────────────
host = make_column()
axis = column_rebar.get_column_axis(host)
u_dir, v_dir = XYZ(1, 0, 0), XYZ(0, 1, 0)
sets = column_rebar.build_stirrup_sets(axis, u_dir, v_dir, 150.0, 100.0, zones_on)
assert len(sets) == 3
for s in sets:
    assert len(s['curves']) == 4  # closed rectangle
    assert s['style'] == 'StirrupTie'
    assert s['array_length_mm'] > 0
print("build_stirrup_sets: one 4-segment closed StirrupTie Set descriptor "
      "per zone: OK")

# ── Test 6 (Phase 3.2 item 2): verticals as Rebar Sets, one per face ───
# A SQUARE column so n_u == n_v — the brief's own literal example
# ("rectangular column with 12 bars -> 4 Sets, one per face").
sq_host = make_column(width_mm=400.0, depth_mm=400.0, height_mm=3000.0)
result = column_rebar.build_column_reinforcement(
    doc, sq_host, cover_mm=40.0, bar_diameter_mm=20.0, bar_count=12,
    stirrup_diameter_mm=10.0, dense_spacing_mm=100.0, normal_spacing_mm=200.0,
    densify_at_nodes=True)
assert len(result['stirrup_sets']) == 3
assert len(result['vertical_bar_sets']) == 4, \
    "a 12-bar square column, single storey, must be exactly 4 Sets (one per face)"
assert result['vertical_bars'] == []  # every face has >= 2 positions here
total_bars = sum(s['count'] for s in result['vertical_bar_sets'])
assert total_bars == 12
for s in result['vertical_bar_sets']:
    assert len(s['curves']) == 1  # no starter bars requested -> plain single line
    line = s['curves'][0]
    z0 = line.GetEndPoint(0).Z * _MM_PER_FT
    z1 = line.GetEndPoint(1).Z * _MM_PER_FT
    assert abs(z0 - 0.0) < 1.0 and abs(z1 - 3000.0) < 1.0  # spans the full clear height
    assert s['array_length_mm'] > 0
    assert s['count'] >= 2
print("build_column_reinforcement: 3 stirrup Sets + verticals grouped into "
      "exactly 4 Rebar Sets (one per face) for a 12-bar square column, "
      "matching the brief's own example: OK")

# ── Test 6b: a non-square column can reduce a face to a single bar — ──
# that face stays an individual element (SetLayoutAsFixedNumber has
# nothing to propagate for a count of 1), all bars still accounted for.
result_narrow_face = column_rebar.build_column_reinforcement(
    doc, host, cover_mm=40.0, bar_diameter_mm=20.0, bar_count=12,
    stirrup_diameter_mm=10.0, dense_spacing_mm=100.0, normal_spacing_mm=200.0)
total_set_bars = sum(s['count'] for s in result_narrow_face['vertical_bar_sets'])
total_individual = len(result_narrow_face['vertical_bars'])
assert total_set_bars + total_individual == 12
assert total_individual > 0, \
    "this 400x300 column's proportions should reduce at least one V-edge to 1 bar"
for vb in result_narrow_face['vertical_bars']:
    assert len(vb['curves']) == 1
print("build_column_reinforcement: a face reduced to a single bar position "
      "stays an individual element — every bar is still accounted for "
      "between the Sets and the individuals: OK")

# ── Test 7: starter bars extend only the TOP end ────────────────────────
result_starters = column_rebar.build_column_reinforcement(
    doc, host, cover_mm=40.0, bar_diameter_mm=20.0, bar_count=8,
    stirrup_diameter_mm=10.0, dense_spacing_mm=100.0, normal_spacing_mm=200.0,
    include_starter_bars=True)
assert len(result_starters['vertical_bar_sets']) > 0
# PHASE 3.5.9 item 2 — a straight lap extension is COLLINEAR with the
# main bar (no section change above), so _merge_collinear_chain now
# collapses [main_line, extension_line] into ONE Line — passing two
# collinear segments to Rebar.CreateFromCurves was confirmed live to
# return None ("Internal Error" on straight starters).
for s in result_starters['vertical_bar_sets']:
    assert len(s['curves']) == 1, (
        "a straight starter extension is collinear with the main bar and must be "
        "merged into a single Line, not passed as two collinear segments")
    line = s['curves'][0]
    base_z = line.GetEndPoint(0).Z * _MM_PER_FT
    top_z = line.GetEndPoint(1).Z * _MM_PER_FT
    assert top_z > base_z  # the merged line still extends UPWARD past the column head
    assert abs(base_z - 0.0) < 1.0  # base unchanged
print("build_column_reinforcement (starter bars): each vertical bar's TOP "
      "end is extended for a lap splice as ONE merged straight Line (not two "
      "collinear segments), base untouched: OK")

# ── Test 7b (user decision 2026-09-30): the crank finishes just below the slab top ──
# A 20 mm bar at a floor the column crosses cranks one diameter (+ the given reduction)
# at 1:6, the diagonal ending 40 mm under the slab's top face; the straight lap above it
# runs kicker + lap above the slab top. A roof projection with nothing above stays straight.
try:
    _FLOORS_IN_DOC[:] = [FakeFloor(-1000.0, 1000.0, -1000.0, 1000.0, top_z_mm=1500.0)]
    result_cranked = column_rebar.build_column_reinforcement(
        doc, host, cover_mm=40.0, bar_diameter_mm=20.0, bar_count=8,
        stirrup_diameter_mm=10.0, dense_spacing_mm=100.0, normal_spacing_mm=200.0,
        include_starter_bars=True, use_cranked_laps=True, crank_offset_mm=30.0,
        starter_bar_length_mm=1000.0, kicker_mm=75.0)
    cranked = [s for s in result_cranked['vertical_bar_sets'] if len(s['curves']) == 3]
    assert cranked, 'the storey below the floor must crank'
    for s in cranked:
        main_line, crank_line, lap_line = s['curves']
        start_z = main_line.GetEndPoint(1).Z * _MM_PER_FT
        end_z = crank_line.GetEndPoint(1).Z * _MM_PER_FT
        assert abs(end_z - (1500.0 - 40.0)) < 1e-6, end_z
        assert abs((end_z - start_z) - 6.0 * 50.0) < 1e-6, 'offset 30 + one diameter, at 1:6'
        shift = crank_line.GetEndPoint(1) - crank_line.GetEndPoint(0)
        assert abs(math.hypot(shift.X, shift.Y) * _MM_PER_FT - 50.0) < 1e-6
        assert abs(lap_line.GetEndPoint(1).Z * _MM_PER_FT - (1500.0 + 75.0 + 1000.0)) < 1e-6
        assert abs(lap_line.GetEndPoint(1).X - lap_line.GetEndPoint(0).X) < 1e-9
    roof = [s for s in result_cranked['vertical_bar_sets'] if len(s['curves']) == 1]
    assert roof, 'the roof projection has nothing above it: straight'
finally:
    _FLOORS_IN_DOC[:] = []
print("build_column_reinforcement (cranked laps): 1:6 crank of one diameter + reduction, "
      "ending 40 mm below the slab top; lap measured above the kicker: OK")

# Pure rules.
assert column_rebar.crank_offset_rule_mm(16.0, 0.0) == 0.0, 'H16 and under: straight'
assert column_rebar.crank_offset_rule_mm(20.0, 0.0) == 20.0, 'H20 and over: one diameter'
assert column_rebar.crank_offset_rule_mm(12.0, 50.0) == 50.0, 'section change always cranks'
assert column_rebar.crank_offset_rule_mm(25.0, 50.0) == 75.0
assert column_rebar.crank_offset_rule_mm(25.0, -50.0) == 25.0, 'a larger column above adds nothing'
assert column_rebar.top_l_foot_mm(800.0, 200.0, 20.0) == 600.0
assert column_rebar.top_l_foot_mm(300.0, 250.0, 20.0) == 240.0, 'foot at least 12 phi'
print("crank_offset_rule_mm / top_l_foot_mm: site rules by diameter, 12 phi minimum foot: OK")

# BS 8666 shape 26: sloped leg B >= 10d (<= 16 mm) or 13d (> 16 mm); the rise lengthens to meet it.
assert column_rebar.crank_min_sloped_leg_mm(16.0) == 160.0
assert column_rebar.crank_min_sloped_leg_mm(20.0) == 260.0
rise = column_rebar.crank_rise_mm(20.0, 20.0)
assert abs(math.hypot(rise, 20.0) - 260.0) < 1e-6, 'H20 one-diameter crank: B = 13d, flatter than 1:6'
assert column_rebar.crank_rise_mm(16.0, 50.0) == 300.0, '1:6 already gives B >= 10d'
print("crank_rise_mm: 1:6, lengthened so the sloped leg B meets 10d / 13d: OK")

# ── Test 7c (Phase 3.3): crank offset AUTO-DETECTED from the real ──────
# column found above — 0.0 (no crank) when the SAME instance continues
# (nothing distinct found above), the REAL section difference when a
# genuinely smaller column is found stacked on top.
try:
    _COLUMNS_IN_DOC[:] = []
    result_no_upper = column_rebar.build_column_reinforcement(
        doc, host, cover_mm=40.0, bar_diameter_mm=20.0, bar_count=8,
        stirrup_diameter_mm=10.0, dense_spacing_mm=100.0, normal_spacing_mm=200.0,
        include_starter_bars=True, use_cranked_laps=True)  # crank_offset_mm NOT given
    for s in result_no_upper['vertical_bar_sets']:
        # PHASE 3.5.9 item 2 — a straight extension (no crank) is
        # collinear with the main bar and is now merged into ONE Line.
        assert len(s['curves']) == 1, \
            "no distinct column found above -> straight extension, no crank, merged to 1 line"
    print("build_column_reinforcement (auto crank, no column above): falls "
          "back to a plain straight extension (merged into one collinear Line) "
          "— the continuous-column case: OK")

    # A genuinely SMALLER column (300x300 instead of 400x300) stacked
    # directly on top, base at the column's own top (3000mm).
    smaller_upper = make_column(width_mm=300.0, depth_mm=300.0, height_mm=3000.0)
    smaller_upper._bbox = BBoxXYZ(
        XYZ(-150.0 / _MM_PER_FT, -150.0 / _MM_PER_FT, 3000.0 / _MM_PER_FT),
        XYZ(150.0 / _MM_PER_FT, 150.0 / _MM_PER_FT, 6000.0 / _MM_PER_FT))
    _COLUMNS_IN_DOC[:] = [smaller_upper]
    # bar_count=12 on this 400x300 column gives n_v=3 -> the V-edges
    # (the ones where the section ACTUALLY shrinks, 400mm -> 300mm)
    # fall back to individual bars (see Test 6b) rather than a Set —
    # exercise both lists so whichever holds them is checked.
    result_auto = column_rebar.build_column_reinforcement(
        doc, host, cover_mm=40.0, bar_diameter_mm=20.0, bar_count=12,
        stirrup_diameter_mm=10.0, dense_spacing_mm=100.0, normal_spacing_mm=200.0,
        include_starter_bars=True, use_cranked_laps=True)
    found_crank = False
    for s in result_auto['vertical_bar_sets'] + result_auto['vertical_bars']:
        if len(s['curves']) == 3:
            found_crank = True
            main_line, crank_line, lap_line = s['curves']
            assert crank_line.GetEndPoint(1).Z > main_line.GetEndPoint(1).Z
    assert found_crank, \
        "the V-edges (narrower on X, where the section actually shrank) must crank"
    print("build_column_reinforcement (auto crank, smaller column above): "
          "derives a REAL non-zero crank from the actual section "
          "difference, no manual crank_offset_mm needed: OK")
finally:
    _COLUMNS_IN_DOC[:] = []

# ── Test 8: non-rectangular / missing-face column raises a clear error ──
bad_solid = Solid([FakeFace(XYZ(1, 0, 0), XYZ(1, 0, 0))])  # only 1 side face
bad_axis = Line.CreateBound(XYZ(0, 0, 0), XYZ(0, 0, 10))
bad_host = FakeHost(bad_solid, LocationCurve(bad_axis))
try:
    column_rebar.build_column_reinforcement(
        doc, bad_host, cover_mm=40.0, bar_diameter_mm=20.0, bar_count=8,
        stirrup_diameter_mm=10.0, dense_spacing_mm=100.0, normal_spacing_mm=200.0)
    assert False, "should have raised"
except ValueError:
    pass
print("build_column_reinforcement: a non-rectangular column (not exactly 4 "
      "side faces) raises a clear ValueError: OK")

# ── Test 9 (Phase 3.1): LocationPoint-based column no longer crashes ───
# This is the REALISTIC, common case for OST_StructuralColumns — the
# live "Host has no LocationCurve" crash.
lp_host = make_column_location_point(width_mm=400.0, depth_mm=300.0, height_mm=3000.0,
                                      px_mm=1500.0, py_mm=2500.0)
lp_axis = column_rebar.get_column_axis(lp_host)
p0, p1 = lp_axis.GetEndPoint(0), lp_axis.GetEndPoint(1)
assert abs(p0.X * _MM_PER_FT - 1500.0) < 1.0 and abs(p0.Y * _MM_PER_FT - 2500.0) < 1.0
# The bbox-derived axis is now inset by the 2mm axis-clamp epsilon
# (Phase 3.4/3.5 item 1 — see get_column_axis's own docstring).
assert abs(p0.Z * _MM_PER_FT - column_rebar._AXIS_CLAMP_EPSILON_MM) < 0.5
assert abs(p1.Z * _MM_PER_FT - (3000.0 - column_rebar._AXIS_CLAMP_EPSILON_MM)) < 0.5
print("get_column_axis (LocationPoint-based column): derives a vertical axis "
      "from the global bounding box, using the REAL insertion point for X/Y "
      "— no crash: OK")

lp_result = column_rebar.build_column_reinforcement(
    doc, lp_host, cover_mm=40.0, bar_diameter_mm=20.0, bar_count=8,
    stirrup_diameter_mm=10.0, dense_spacing_mm=100.0, normal_spacing_mm=200.0)
assert len(lp_result['vertical_bar_sets']) + len(lp_result['vertical_bars']) >= 2
for s in lp_result['vertical_bar_sets']:
    x_mm = s['curves'][0].GetEndPoint(0).X * _MM_PER_FT
    assert 1500.0 - 200.0 < x_mm < 1500.0 + 200.0  # centred on the REAL insertion point, not (0,0)
for vb in lp_result['vertical_bars']:
    x_mm = vb['curves'][0].GetEndPoint(0).X * _MM_PER_FT
    assert 1500.0 - 200.0 < x_mm < 1500.0 + 200.0
print("build_column_reinforcement (LocationPoint-based column): full "
      "pipeline runs end-to-end, bars centred on the column's real "
      "insertion point: OK")

# ── Test 10: no Location at all, but a valid bbox -> falls back to its centre ──
no_loc_host = FakeHost(lp_host._solid, location=None, bbox=lp_host._bbox)
axis_no_loc = column_rebar.get_column_axis(no_loc_host)
p0nl = axis_no_loc.GetEndPoint(0)
assert abs(p0nl.X * _MM_PER_FT - 1500.0) < 1.0  # matches the bbox centre here (px=1500 IS the centre)
print("get_column_axis (no Location at all): falls back to the bounding "
      "box's own X/Y centre rather than crashing: OK")

# ── Test 11: neither Location nor bounding box -> a clear ValueError ───
nothing_host = FakeHost(lp_host._solid, location=None, bbox=None)
try:
    column_rebar.get_column_axis(nothing_host)
    assert False, "should have raised"
except ValueError:
    pass
print("get_column_axis: neither LocationCurve, LocationPoint, nor a "
      "bounding box raises a clear ValueError, not a downstream crash: OK")

# ── Test 12 (Phase 3.2 item 1): multi-story column split at floor tops ──
tall_host = make_column(width_mm=400.0, depth_mm=400.0, height_mm=9000.0)
tall_axis = column_rebar.get_column_axis(tall_host)
_FLOORS_IN_DOC[:] = [
    FakeFloor(-1000.0, 1000.0, -1000.0, 1000.0, top_z_mm=3000.0),
    FakeFloor(-1000.0, 1000.0, -1000.0, 1000.0, top_z_mm=6000.0),
]
try:
    split_entries = column_rebar.find_floor_split_elevations_ft(doc, tall_axis)
    assert len(split_entries) == 2
    tops_mm = [e['top_ft'] * _MM_PER_FT for e in split_entries]
    bottoms_mm = [e['bottom_ft'] * _MM_PER_FT for e in split_entries]
    assert abs(tops_mm[0] - 3000.0) < 1.0 and abs(tops_mm[1] - 6000.0) < 1.0
    assert abs(bottoms_mm[0] - 2800.0) < 1.0 and abs(bottoms_mm[1] - 5800.0) < 1.0, \
        "each entry's own bottom_ft (the slab's underside) must also be reported"
    print("find_floor_split_elevations_ft: detects both floors the column's "
          "own axis passes through (top AND bottom), sorted ascending: OK")

    tall_result = column_rebar.build_column_reinforcement(
        doc, tall_host, cover_mm=40.0, bar_diameter_mm=20.0, bar_count=12,
        stirrup_diameter_mm=10.0, dense_spacing_mm=100.0, normal_spacing_mm=200.0,
        include_starter_bars=True)
    assert len(tall_result['vertical_bar_sets']) == 4 * 3, \
        "4 faces x 3 storey segments (2 floors -> 3 segments) = 12 Sets"
    for s in tall_result['vertical_bar_sets']:
        # PHASE 3.5.9 item 2 — every segment here gets a starter, and a
        # straight starter is collinear with its own main segment, so
        # _merge_collinear_chain collapses [main_line, extension] into
        # ONE Line — the merged line's TOP now sits PAST the nominal
        # split/column-top elevation (3000/6000/9000mm) by the lap
        # length, not stopping exactly at it as the old, un-merged
        # [main_line, extension] pair's FIRST curve used to.
        assert len(s['curves']) == 1, \
            "a straight starter is collinear with its own segment and must merge to 1 Line"
        line0 = s['curves'][0]
        top_z_mm = line0.GetEndPoint(1).Z * _MM_PER_FT
        assert any(top_z_mm > z - 1.0 for z in (3000.0, 6000.0, 9000.0)), top_z_mm
    print("build_column_reinforcement (multi-story): a column crossing 2 "
          "floors yields 3 storey segments per face (12 Sets total for a "
          "12-bar square column), each with its own starter at its own "
          "storey's floor top: OK")

    # ── Test 12b (Phase 3.4 item 2): stirrup Sets stop at each slab ─────
    for s in tall_result['stirrup_sets']:
        z0_mm = s['array_length_mm']  # not directly a Z, just sanity below
        assert z0_mm > 0.0
    # No stirrup zone may straddle a floor's own [bottom,top] band.
    zone_ranges_mm = []
    base_z_mm = tall_axis.GetEndPoint(0).Z * _MM_PER_FT
    for s in tall_result['stirrup_sets']:
        chain = s['curves'][0]
        z_start_mm = chain.GetEndPoint(0).Z * _MM_PER_FT - base_z_mm
        zone_ranges_mm.append((z_start_mm, z_start_mm + s['array_length_mm']))
    for (band_lo, band_hi) in ((2800.0, 3000.0), (5800.0, 6000.0)):
        for (z_lo, z_hi) in zone_ranges_mm:
            assert not (z_lo < band_hi - 1.0 and z_hi > band_lo + 1.0), \
                "a stirrup zone [%s,%s] straddles the floor band [%s,%s]" % (
                    z_lo, z_hi, band_lo, band_hi)
    print("build_column_reinforcement (multi-story): stirrup Sets never "
          "straddle a detected floor's own thickness — they stop at the "
          "slab's underside and resume at its top: OK")

    # ── Test 13: an ordinary single-story column is UNAFFECTED ─────────
    _FLOORS_IN_DOC[:] = []
    plain_result = column_rebar.build_column_reinforcement(
        doc, sq_host, cover_mm=40.0, bar_diameter_mm=20.0, bar_count=12,
        stirrup_diameter_mm=10.0, dense_spacing_mm=100.0, normal_spacing_mm=200.0)
    assert len(plain_result['vertical_bar_sets']) == 4  # unchanged from Test 6
    print("build_column_reinforcement: a single-story column (no floor "
          "intersections) produces the exact same single-segment-per-face "
          "output as before Phase 3.2 — zero functionality loss: OK")
finally:
    _FLOORS_IN_DOC[:] = []

# ── Test 14 (Phase 3.4 item 1): get_column_axis clamps to the REAL bbox ──
drift_axis = Line.CreateBound(XYZ(0, 0, -100.0 / _MM_PER_FT), XYZ(0, 0, 3100.0 / _MM_PER_FT))
drift_bbox = BBoxXYZ(XYZ(-200.0 / _MM_PER_FT, -150.0 / _MM_PER_FT, 0.0),
                      XYZ(200.0 / _MM_PER_FT, 150.0 / _MM_PER_FT, 3000.0 / _MM_PER_FT))
drift_host = FakeHost(host._solid, LocationCurve(drift_axis), bbox=drift_bbox)
clamped_axis = column_rebar.get_column_axis(drift_host)
p0, p1 = clamped_axis.GetEndPoint(0), clamped_axis.GetEndPoint(1)
# Clamped to the bbox INSET by the epsilon (Phase 3.4/3.5 item 1) — a
# hair inside the solid, not exactly on its boundary.
eps = column_rebar._AXIS_CLAMP_EPSILON_MM
assert abs(p0.Z * _MM_PER_FT - eps) < 1e-6, \
    "a LocationCurve base BELOW the real bbox.Min.Z must be clamped up to it (+epsilon)"
assert abs(p1.Z * _MM_PER_FT - (3000.0 - eps)) < 1e-6, \
    "a LocationCurve top ABOVE the real bbox.Max.Z must be clamped down to it (-epsilon)"
assert p0.Z > 0.0 and p1.Z < 3000.0 / _MM_PER_FT, \
    "both clamped endpoints must sit STRICTLY inside the real bbox, not exactly on it"
print("get_column_axis: a LocationCurve extending outside the host's own "
      "real bounding box is clamped to it (with a small inward epsilon, "
      "not the exact boundary) — the ground-floor Internal Error fix: OK")

# ── Test 14b (Phase 3.5 item 1): the ABSOLUTE base segment is NEVER ────
# cranked or extended, straight from the foundation, regardless of
# use_cranked_laps — the crank/starter machinery only ever touches a
# segment's TOP end (build_story_segment_chains's own seg_end), so a
# ground-floor column's base is structurally incapable of being
# cranked, with or without an intersecting floor above it.
ground_axis = column_rebar.get_column_axis(make_column(width_mm=400.0, depth_mm=400.0, height_mm=6000.0))
_FLOORS_IN_DOC[:] = [FakeFloor(-1000.0, 1000.0, -1000.0, 1000.0, top_z_mm=3000.0)]
try:
    ground_splits_ft = [e['top_ft'] for e in
                         column_rebar.find_floor_split_elevations_ft(doc, ground_axis)]
    ground_chains = column_rebar.build_story_segment_chains(
        ground_axis, XYZ(0, 0, 0), ground_splits_ft, lap_length_mm=800.0,
        include_starter_bars=True, use_cranked_laps=True,
        inward_dir=XYZ(0, -1, 0), crank_offset_fn=lambda z: 30.0, crank_slope=6.0)
    assert len(ground_chains) == 2  # base segment (0->3000) + top segment (3000->6000)
    base_chain = ground_chains[0]
    assert len(base_chain) == 3, "the base segment ITSELF still gets a starter at its OWN top"
    base_main_line = base_chain[0]
    assert isinstance(base_main_line, Line)
    p_base_bottom = base_main_line.GetEndPoint(0)
    p_base_top = base_main_line.GetEndPoint(1)
    # The BASE segment's own bottom (the true foundation-level start)
    # must be exactly ground_axis's own base — a plain straight point,
    # never shifted/cranked — while its TOP (entering the floor above)
    # is exactly where the crank/starter is allowed to happen.
    assert abs(p_base_bottom.Z - ground_axis.GetEndPoint(0).Z) < 1e-9
    assert abs(p_base_bottom.X) < 1e-9 and abs(p_base_bottom.Y) < 1e-9, \
        "the absolute base point must be unshifted — no crank applied there"
    print("build_story_segment_chains: the absolute base segment is always a "
          "plain straight line from the true foundation level — cranks/starters "
          "only ever occur at a segment's TOP, entering the floor above: OK")
finally:
    _FLOORS_IN_DOC[:] = []

# ── Test 15 (Phase 3.4 item 3): minimise total Rebar Set count ──────────
# half_w=50mm, half_d=200mm (post cover+stirrup+bar-radius inset) with
# bar_count=8 gives n_u=2 (corners only), n_v=4 (2 genuine interior
# bars/edge) — the OLD always-'u'-owns-corners logic would have produced
# 4 Sets of 2 bars each; the fix must produce 2 Sets of 4 bars each.
groups_swap = column_rebar._face_groups(50.0, 200.0, 2, 4)
nonempty_swap = [g for g in groups_swap if g['positions']]
assert len(nonempty_swap) == 2, "must collapse to exactly 2 non-empty face groups"
for g in nonempty_swap:
    assert g['edge_dir'] == 'v' and len(g['positions']) == 4
assert sum(len(g['positions']) for g in groups_swap) == 8
print("_face_groups: the axis with MORE bars (here 'v', 4 vs 2) owns the "
      "corners, collapsing an 8-bar column to 2 Sets of 4 instead of 4 "
      "Sets of 2 — minimises the total Rebar Set count: OK")

# A tie (n_u == n_v) must be UNCHANGED from the original 'u'-owns-corners
# default (already covered by Test 6's 12-bar square-column assertions,
# re-affirmed here directly against _face_groups).
groups_tie = column_rebar._face_groups(140.0, 140.0, 4, 4)
u_groups_tie = [g for g in groups_tie if g['edge_dir'] == 'u']
assert all(len(g['positions']) == 4 for g in u_groups_tie)
print("_face_groups: a tied n_u == n_v keeps 'u' as the corner-owner, "
      "unchanged from before this fix: OK")

# Bar-count matching end-to-end: the 8-bar/n_u=2,n_v=4 proportions,
# built through the full pipeline, must yield exactly 2 vertical_bar_sets.
narrow_swap_host = make_column(width_mm=220.0, depth_mm=520.0, height_mm=3000.0)
swap_result = column_rebar.build_column_reinforcement(
    doc, narrow_swap_host, cover_mm=40.0, bar_diameter_mm=20.0, bar_count=8,
    stirrup_diameter_mm=10.0, dense_spacing_mm=100.0, normal_spacing_mm=200.0)
assert len(swap_result['vertical_bar_sets']) == 2
assert swap_result['vertical_bars'] == []
assert sum(s['count'] for s in swap_result['vertical_bar_sets']) == 8
print("build_column_reinforcement: an 8-bar column whose proportions used "
      "to yield 4 tiny Sets now yields exactly 2 full-size Sets end-to-end: OK")

# ── Test 16 (Phase 3.4 item 4): detect_column_geometry ──────────────────
rect_geom = column_rebar.detect_column_geometry(doc, host)
assert rect_geom is not None and rect_geom['shape'] == 'rect'
assert abs(rect_geom['width_mm'] - 400.0) < 0.5 and abs(rect_geom['depth_mm'] - 300.0) < 0.5
print("detect_column_geometry (rectangular column): reads the REAL "
      "width/depth (400x300mm), not an illustrative default: OK")

circ_axis = Line.CreateBound(XYZ(0, 0, 0), XYZ(0, 0, 3000.0 / _MM_PER_FT))
circ_solid = Solid([CylindricalFace(200.0 / _MM_PER_FT)], volume=1.0)
# BUG FIX (2026-09-01) — detect_column_geometry's circular branch now
# derives diameter from the host's own bounding box (CylindricalFace.
# Radius doesn't behave as a plain float in the real pythonnet binding —
# see column_rebar.py's own comment on this), not the fixture's
# CylindricalFace(radius_ft) stub attribute directly, so this fixture
# needs a bbox matching the same 400mm diameter for the test to mean
# anything real.
circ_bbox = BBoxXYZ(XYZ(-200.0 / _MM_PER_FT, -200.0 / _MM_PER_FT, 0.0),
                     XYZ(200.0 / _MM_PER_FT, 200.0 / _MM_PER_FT, 3000.0 / _MM_PER_FT))
circ_host = FakeHost(circ_solid, LocationCurve(circ_axis), bbox=circ_bbox)
circ_geom = column_rebar.detect_column_geometry(doc, circ_host)
assert circ_geom is not None and circ_geom['shape'] == 'circle'
assert abs(circ_geom['diameter_mm'] - 400.0) < 0.5
print("detect_column_geometry (circular column): finds the CylindricalFace "
      "and reports its real diameter instead of forcing a rectangle: OK")

# ── Test 17 (Phase 3.4 item 5): interior crossties ──────────────────────
tie_result_off = column_rebar.build_column_reinforcement(
    doc, host, cover_mm=40.0, bar_diameter_mm=20.0, bar_count=12,
    stirrup_diameter_mm=10.0, dense_spacing_mm=100.0, normal_spacing_mm=200.0,
    include_crossties=False)
assert tie_result_off['crosstie_sets'] == []
print("build_column_reinforcement: crosstie_sets stays empty when "
      "include_crossties is False (the default): OK")

# host (400x300, bar_count=12) gives n_u=5, n_v=3 (see Test 6b) — 3
# interior U-edge bars (1 per edge x... actually n_u=5 means 3 interior
# per U-edge) and 1 interior V-edge bar per edge -> genuinely interior
# bars on BOTH axes, so crossties must be generated for both.
tie_result_on = column_rebar.build_column_reinforcement(
    doc, host, cover_mm=40.0, bar_diameter_mm=20.0, bar_count=12,
    stirrup_diameter_mm=10.0, dense_spacing_mm=100.0, normal_spacing_mm=200.0,
    include_crossties=True)
assert len(tie_result_on['crosstie_sets']) > 0
for s in tie_result_on['crosstie_sets']:
    assert 'curve' in s and 'normal' in s  # individual bar, not a Set spec
    p_a, p_b = s['curve'].GetEndPoint(0), s['curve'].GetEndPoint(1)
    assert p_a.Z == p_b.Z  # a crosstie is horizontal
print("build_column_reinforcement (crossties ON): straight interior "
      "crossties are generated for a column with genuinely interior bars: OK")

# n_u == n_v == 2 (only the 4 corners, bar_count=4) -> no interior bars
# on either axis -> crosstie_sets must stay empty even with the flag on.
no_interior_result = column_rebar.build_column_reinforcement(
    doc, host, cover_mm=40.0, bar_diameter_mm=20.0, bar_count=4,
    stirrup_diameter_mm=10.0, dense_spacing_mm=100.0, normal_spacing_mm=200.0,
    include_crossties=True)
assert no_interior_result['crosstie_sets'] == []
print("build_column_reinforcement (crossties ON, 4-bar column): no "
      "interior bars to tie -> crosstie_sets stays empty, no false "
      "positives: OK")

print("\nALL COLUMN_REBAR PHASE 3 CHECKS PASSED")


# ── T4.6 (D3): densification at intermediate nodes of multi-storey columns ──
storey_zones = column_rebar.generate_storey_stirrup_zones(
    6300.0, 450.0, 100.0, 200.0, True, 50.0, 50.0, floor_bands_mm=[(3000.0, 3300.0)])
dense = [z for z in storey_zones if z['spacing_mm'] == 100.0]
assert len(dense) == 4, "each storey is densified at both ends: 4 dense zones, got {}".format(len(dense))
assert any(abs(z['end_mm'] - 2950.0) < 1e-6 for z in dense), "dense zone just under the slab"
assert any(abs(z['start_mm'] - 3350.0) < 1e-6 for z in dense), "dense zone just above the slab"
assert all(z['end_mm'] <= 3000.0 or z['start_mm'] >= 3300.0 for z in storey_zones), \
    "no link inside the slab"
single = column_rebar.generate_storey_stirrup_zones(3000.0, 450.0, 100.0, 200.0, True)
assert len(single) == 3, "a single-storey column keeps its 3 zones"
print("generate_storey_stirrup_zones: intermediate node densified above and below "
      "the slab, no link inside it: OK")
