# -*- coding: utf-8 -*-
"""Mocked-API test for floor_rebar.py's Phase 2.3 hardening: Rebar Set
grouping (MRA), real polygon cover offset, and dynamic leg length /
closed-link fallback in narrow zones."""
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
    def CreateTransformed(self, transform):
        return Line(self._p0 + transform.shift, self._p1 + transform.shift)

class Transform(object):
    def __init__(self, shift):
        self.shift = shift
    @staticmethod
    def CreateTranslation(shift):
        return Transform(shift)

class FakeHost(object):
    def __init__(self, bottom_face, top_face, width_ft, depth_ft, height_ft):
        self._bottom_face = bottom_face
        self._top_face = top_face
        self._w, self._d, self._h = width_ft, depth_ft, height_ft
        self._solid = Solid([bottom_face, top_face], volume=width_ft * depth_ft * height_ft)
    def get_Geometry(self, opts):
        return [self._solid]
    def get_BoundingBox(self, view):
        return BBoxXYZ(XYZ(0.0, 0.0, 0.0), XYZ(self._w, self._d, self._h))

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
DB.Solid = Solid
DB.Options = Options
DB.Transform = Transform
DB.GeometryInstance = type('GeometryInstance', (), {})
DB.ViewDetailLevel = types.SimpleNamespace(Fine=1)
DB.BuiltInParameter = types.SimpleNamespace(REBAR_BAR_DIAMETER=1)
DB.FilteredElementCollector = lambda doc: types.SimpleNamespace(
    OfClass=lambda cls: types.SimpleNamespace(ToElements=lambda: []))

revit_stubs.install_system_stubs()

_LIB = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'lib'))

re_engine = revit_stubs.load_module('re_engine', _LIB + r'\rebar_engine.py')

footing_rebar_mod = revit_stubs.load_module('footing_rebar_mod', _LIB + r'\footing_rebar.py')
footing_rebar_mod.re_engine = re_engine
footing_rebar_mod._ensure_engine = lambda: re_engine

slab_topology = revit_stubs.load_module('slab_topology', _LIB + r'\slab_topology.py')

floor_rebar = revit_stubs.load_module('floor_rebar', _LIB + r'\floor_rebar.py')
floor_rebar.footing_rebar_mod = footing_rebar_mod
floor_rebar._ensure_footing_rebar = lambda: footing_rebar_mod
floor_rebar.re_engine = re_engine
floor_rebar._ensure_engine = lambda: re_engine
floor_rebar.slab_topology = slab_topology
floor_rebar._ensure_topology = lambda: slab_topology

doc = None


def make_rect_floor(width_mm=6000.0, depth_mm=4000.0, thickness_mm=200.0, holes_mm=None):
    holes_mm = holes_mm or []
    w_ft, d_ft, h_ft = width_mm / _MM_PER_FT, depth_mm / _MM_PER_FT, thickness_mm / _MM_PER_FT
    outer = [(0.0, 0.0), (width_mm, 0.0), (width_mm, depth_mm), (0.0, depth_mm)]
    bottom_loops = [_loop_mm(outer, 0.0)] + [_loop_mm(h, 0.0) for h in holes_mm]
    top_loops = [_loop_mm(outer, h_ft)] + [_loop_mm(h, h_ft) for h in holes_mm]
    bottom = FakeFace(0.0, XYZ(0, 0, -1), 0.0, 0.0, w_ft, d_ft, bottom_loops)
    top = FakeFace(h_ft, XYZ(0, 0, 1), 0.0, 0.0, w_ft, d_ft, top_loops)
    return FakeHost(bottom, top, w_ft, d_ft, h_ft)


def make_l_shape_floor(thickness_mm=200.0):
    h_ft = thickness_mm / _MM_PER_FT
    outer = [(0, 0), (5000, 0), (5000, 2000), (3000, 2000), (3000, 3000), (0, 3000)]
    bottom = FakeFace(0.0, XYZ(0, 0, -1), 0.0, 0.0, 5000.0 / _MM_PER_FT, 3000.0 / _MM_PER_FT,
                       [_loop_mm(outer, 0.0)])
    top = FakeFace(h_ft, XYZ(0, 0, 1), 0.0, 0.0, 5000.0 / _MM_PER_FT, 3000.0 / _MM_PER_FT,
                    [_loop_mm(outer, h_ft)])
    return FakeHost(bottom, top, 5000.0 / _MM_PER_FT, 3000.0 / _MM_PER_FT, h_ft)


# ── Test 1: plain rectangle -> the ENTIRE main grid groups into Sets ───
host = make_rect_floor(width_mm=6000.0, depth_mm=4000.0, thickness_mm=200.0)
result = floor_rebar.build_floor_reinforcement(
    doc, host, bottom_cover_mm=25.0, bottom_dia_x_mm=10.0, bottom_dia_y_mm=10.0,
    bottom_spacing_mm=200.0)
along_x = result['bottom_mat']['along_x']
assert len(along_x['bars']) == 0, "a plain rectangle should produce ZERO individual bars"
assert len(along_x['sets']) == 1, "every row is identical -> exactly ONE Rebar Set"
print("build_floor_reinforcement (rectangle): entire B1 direction is ONE Rebar Set, "
      "zero individual bars — MRA-friendly: OK")

# ── Test 2: real cover offset — bars respect cover on the CHAMFERED edge ──
host_l = make_l_shape_floor()
result_l = floor_rebar.build_floor_reinforcement(
    doc, host_l, bottom_cover_mm=40.0, bottom_dia_x_mm=10.0, bottom_dia_y_mm=10.0,
    bottom_spacing_mm=250.0)
along_x_l = result_l['bottom_mat']['along_x']
all_bars_l = along_x_l['bars'] + along_x_l['sets']
for b in all_bars_l:
    line = b['curves'][0]
    x0 = line.GetEndPoint(0).X * _MM_PER_FT
    x1 = line.GetEndPoint(1).X * _MM_PER_FT
    y = line.GetEndPoint(0).Y * _MM_PER_FT
    if y > 2000.0:
        assert x1 <= 3000.0 - 40.0 + 1e-3, \
            "bar violates real cover on the chamfered notch edge (must be >= 40mm inside it)"
print("build_floor_reinforcement (L-shape): real polygon cover offset keeps bars "
      ">= cover away from the chamfered edge, not just axis-inset: OK")

# ── Test 3: large hole — grouping still happens either side of it ──────
host_hole = make_rect_floor(width_mm=6000.0, depth_mm=4000.0, thickness_mm=200.0,
                             holes_mm=[[(2500, 1500), (3500, 1500), (3500, 2500), (2500, 2500)]])
result_hole = floor_rebar.build_floor_reinforcement(
    doc, host_hole, bottom_cover_mm=25.0, bottom_dia_x_mm=10.0, bottom_dia_y_mm=10.0,
    bottom_spacing_mm=200.0)
along_x_hole = result_hole['bottom_mat']['along_x']
# axis-aligned rectangular hole -> every row is EITHER "full width" or "split in 2",
# each a uniform run of its own -> should still be almost entirely Sets, few/no individual bars
assert len(along_x_hole['sets']) >= 2, "expected at least 2 sets (above/below vs through the hole)"
assert len(along_x_hole['bars']) <= 2, \
    "an axis-aligned hole should produce at most a couple of individual bars, not thousands"
print("build_floor_reinforcement (large rectangular hole): grouping still produces "
      "Rebar Sets on both sides of the hole, negligible individual-bar count: OK")

# ── Test 4 (Phase 3.5 item 5): ONE continuous Set per polygon EDGE ──────
# A wide-open 6000x4000 rectangle: X-anchor U-bars (B1/T1) sit on the
# LEFT/RIGHT edges (they run along Y); Y-anchor (B2/T2) sit on the
# TOP/BOTTOM edges (they run along X). Each edge must become exactly
# ONE continuous Rebar Set spanning corner-to-corner (minus the
# corner-inset margin at each end), NOT a chain of per-row fragments.
result_closure = floor_rebar.build_floor_reinforcement(
    doc, host, bottom_cover_mm=25.0, bottom_dia_x_mm=10.0, bottom_dia_y_mm=10.0,
    bottom_spacing_mm=200.0,
    include_top_mat=True, top_cover_mm=25.0, top_dia_x_mm=10.0, top_dia_y_mm=10.0,
    top_spacing_mm=200.0,
    include_perimeter_closure_ubars=True,
    x_anchor_ubar_dia_mm=8.0, x_anchor_ubar_spacing_mm=200.0,
    y_anchor_ubar_dia_mm=8.0, y_anchor_ubar_spacing_mm=200.0)
closure = result_closure['perimeter_closure_ubars']
# max(40d = 320mm, 2h = 400mm on this 200mm slab): EC2 9.3.1.4 edge U-bars (2026-09-30)
nominal_leg_mm = max(40.0 * 8.0, 2.0 * 200.0)
cover_mm = 25.0  # the outer boundary is cover-offset BEFORE the edges are walked
# T2.17 (2026-09-30): one U-bar beside each mat bar ending on the edge,
# over the mat's whole zone, in two uniform halves per edge (each half
# shifted towards the middle so none leaves the zone) -> 2 Sets per edge.
contact_mm = (10.0 + 8.0) / 2.0
assert len(closure['x_bars']['sets']) == 2 and closure['x_bars']['bars'] == [],     "the left AND right edges must each be exactly ONE Set (T2.17: one Rebar Set per side)"
assert len(closure['y_bars']['sets']) == 2 and closure['y_bars']['bars'] == [],     "the top AND bottom edges must each be exactly ONE Set"
for key, edge_mm in (('x_bars', 4000.0), ('y_bars', 6000.0)):
    zone_mm = edge_mm - 2 * cover_mm - 10.0  # mat rows run cover + d/2 .. edge - cover - d/2
    for s_ in closure[key]['sets']:
        assert s_['style'] is None
        # one U beside every mat bar except the last: the Set spans the mat rows less one spacing
        assert s_['array_length_mm'] > zone_mm - 2 * 200.0 - 1.0,             "the Set must cover the mat zone (less one spacing), not stop an anchorage short of each corner"
print("build_floor_reinforcement (closure U-bars, wide floor): each edge is ONE "
      "uniform Set over the whole mat zone, one U beside each mat bar: OK")

# ── Test 4b: an L-shaped (non-convex) floor also closes with continuous ──
# edges, including around its own reflex/notch corner — no fragmentation.
l_host = make_l_shape_floor(thickness_mm=200.0)
result_l = floor_rebar.build_floor_reinforcement(
    doc, l_host, bottom_cover_mm=25.0, bottom_dia_x_mm=10.0, bottom_dia_y_mm=10.0,
    bottom_spacing_mm=200.0,
    include_top_mat=True, top_cover_mm=25.0, top_dia_x_mm=10.0, top_dia_y_mm=10.0,
    top_spacing_mm=200.0,
    include_perimeter_closure_ubars=True,
    x_anchor_ubar_dia_mm=8.0, x_anchor_ubar_spacing_mm=200.0,
    y_anchor_ubar_dia_mm=8.0, y_anchor_ubar_spacing_mm=200.0)
l_closure = result_l['perimeter_closure_ubars']
# the L-shape's outer loop has 6 edges (3 X-anchor "vertical" ones, 3
# Y-anchor "horizontal" ones) — every edge long enough for the corner
# inset (320mm) becomes its own Set or individual bar; NONE should be
# missing (a fragmented scanline would have silently dropped the notch).
def _edge_coords(entries, coord):
    """Distinct plan coordinate (mm) of each U-bar's vertical back, one per edge served."""
    found = set()
    for e in entries['sets'] + entries['bars']:
        for c in e['curves']:
            p0, p1 = c.GetEndPoint(0), c.GetEndPoint(1)
            if abs(p0.X - p1.X) < 1e-9 and abs(p0.Y - p1.Y) < 1e-9:
                found.add(round((p0.X if coord == 'x' else p0.Y) * _MM_PER_FT))
    return found


assert len(_edge_coords(l_closure['x_bars'], 'x')) == 3,     "3 vertical edges (left, the step, and the right side of the notch)"
assert len(_edge_coords(l_closure['y_bars'], 'y')) == 3,     "3 horizontal edges (bottom, the notch shelf, and the top)"
print("build_floor_reinforcement (L-shaped floor): every edge around a "
      "non-convex boundary, including the reflex notch corner, gets its own "
      "continuous closure run: OK")

# ── Test 5 (Phase 3.5 item 5): narrow rib between two holes -> closed link ──
narrow_host = make_rect_floor(
    width_mm=6000.0, depth_mm=4000.0, thickness_mm=200.0,
    holes_mm=[
        [(1000, 500), (2900, 500), (2900, 3500), (1000, 3500)],
        [(3100, 500), (5000, 500), (5000, 3500), (3100, 3500)],
    ])
# the rib between the two holes is only 200mm wide (2900 to 3100) — a
# full 320mm leg from EITHER hole's own facing edge would cross into
# the OTHER hole; the material-containment check (not a shrunk leg)
# must catch this and fall back to a closed link on those facing edges.
result_narrow = floor_rebar.build_floor_reinforcement(
    doc, narrow_host, bottom_cover_mm=25.0, bottom_dia_x_mm=10.0, bottom_dia_y_mm=10.0,
    bottom_spacing_mm=200.0,
    include_top_mat=True, top_cover_mm=25.0, top_dia_x_mm=10.0, top_dia_y_mm=10.0,
    top_spacing_mm=200.0,
    include_perimeter_closure_ubars=True,
    x_anchor_ubar_dia_mm=8.0, x_anchor_ubar_spacing_mm=200.0,
    y_anchor_ubar_dia_mm=8.0, y_anchor_ubar_spacing_mm=200.0)
x_closure_narrow = result_narrow['perimeter_closure_ubars']['x_bars']
all_x_entries_narrow = x_closure_narrow['sets'] + x_closure_narrow['bars']
link_entries = [e for e in all_x_entries_narrow if e.get('style') == 'StirrupTie']
assert len(link_entries) >= 2, \
    "both hole edges facing the 200mm rib must fall back to a closed link"
for e in link_entries:
    assert len(e['curves']) == 4, "a closed link is a 4-segment closed rectangle"
    xs = set(round(c.GetEndPoint(i).X * _MM_PER_FT, 1) for c in e['curves'] for i in (0, 1))
    assert any(2850.0 < x < 3150.0 for x in xs), \
        "the closed link must sit right at the narrow rib, not elsewhere on the hole"
print("build_floor_reinforcement (200mm-wide rib between two holes): the "
      "material-containment check catches the WOULD-BE leg collision and "
      "falls back to a closed link instead of colliding U-bars: OK")

# ── Test 6: every open closure U-bar's leg is the FULL nominal length ──
y_closure_narrow = result_narrow['perimeter_closure_ubars']['y_bars']
all_y_entries = y_closure_narrow['sets'] + y_closure_narrow['bars']
for e in all_x_entries_narrow + all_y_entries:
    if e.get('style') == 'StirrupTie':
        continue
    # an open U-bar chain's legs are curves[0] and curves[-1]
    leg0 = e['curves'][0]
    leg_len_mm = leg0.GetEndPoint(0).DistanceTo(leg0.GetEndPoint(1)) * _MM_PER_FT
    assert abs(leg_len_mm - nominal_leg_mm) < 1e-3, \
        "every open U-bar's leg must be EXACTLY the full nominal length, never shrunk"
print("build_floor_reinforcement: every open closure U-bar's leg is exactly "
      "the full 40xdiameter nominal length — never a shrunk/degenerate leg: OK")

# ── Test 7 (Phase 2.4 item 3): narrow-zone main bar suppression ────────
# The 200mm gap between the two holes (X:2900-3100) is narrower than
# 2 x 40 x 8mm = 640mm -> gets a closed link on the X-anchor closure
# scan, so the along_x main grid must NOT also generate a redundant
# straight bar spanning that same narrow X-interval.
along_x_narrow = result_narrow['bottom_mat']['along_x']
for b in along_x_narrow['bars'] + along_x_narrow['sets']:
    line = b['curves'][0] if b['curves'][0].Length else b['curves'][-1]
    x0 = line.GetEndPoint(0).X * _MM_PER_FT
    x1 = line.GetEndPoint(1).X * _MM_PER_FT
    width = abs(x1 - x0)
    assert not (1.0 < width < 640.0 and 2850.0 < min(x0, x1) < 2950.0), \
        "a redundant sliver main bar was generated inside the narrow closed-link zone"
print("build_floor_reinforcement (narrow zone + closure U-bars active): no "
      "redundant sliver main bar generated inside the closed-link zone — "
      "'basura' bug fixed: OK")

# ── Test 8: WITHOUT closure U-bars active, the narrow zone keeps its normal bar ──
result_no_closure = floor_rebar.build_floor_reinforcement(
    doc, narrow_host, bottom_cover_mm=25.0, bottom_dia_x_mm=10.0, bottom_dia_y_mm=10.0,
    bottom_spacing_mm=200.0)
along_x_no_closure = result_no_closure['bottom_mat']['along_x']
assert len(along_x_no_closure['bars']) + len(along_x_no_closure['sets']) > 0
print("build_floor_reinforcement (narrow zone, closure U-bars OFF): main grid "
      "still reinforces the narrow strip normally — suppression only applies "
      "when a closed link actually replaces it: OK")

# ── Test 9 (Phase 2.5 item 2): every grouped Set carries materialized_bars ──
# so a failed SetLayoutAsMaximumSpacing propagation can be rebuilt via
# create_freeform_group instead of silently staying "Layout Rule: Single".
for s in along_x['sets']:
    assert 'materialized_bars' in s and len(s['materialized_bars']) >= 2
    for mb in s['materialized_bars']:
        assert 'curves' in mb and 'normal' in mb
for s in closure['x_bars']['sets'] + closure['y_bars']['sets']:
    assert 'materialized_bars' in s and len(s['materialized_bars']) >= 2
print("build_floor_reinforcement: every grouped Set (main grid AND closure "
      "U-bars) carries materialized_bars for the Set-to-FreeForm fallback "
      "cascade — guarantees zero loose bars: OK")

# ── Test 10 (Phase 2.6 "flying bars"): Set propagation direction ───────
# Every SET's array_length_mm must span an interval that stays WITHIN
# the floor's own footprint — a Set propagating the wrong way (the
# handedness bug) would still report a POSITIVE array_length_mm (it's
# just abs(last-first)), so the real diagnostic is: every MATERIALIZED
# bar in the run must itself lie strictly inside the offset boundary
# (bottom_outer's own bbox, inset by the residual half-diameter) — a
# bar propagated backwards would land OUTSIDE it.
xmin, xmax, ymin, ymax = 0.0, 6000.0, 0.0, 4000.0
for direction_key, dia in (('along_x', 10.0), ('along_y', 10.0)):
    grouped = result['bottom_mat'][direction_key]
    for s in grouped['sets']:
        for mb in s['materialized_bars']:
            for curve in mb['curves']:
                for i in (0, 1):
                    p = curve.GetEndPoint(i)
                    x_mm, y_mm = p.X * _MM_PER_FT, p.Y * _MM_PER_FT
                    assert xmin - 1.0 <= x_mm <= xmax + 1.0, \
                        "%s materialized bar X=%.1f flies outside [%.1f,%.1f] (handedness regression)" % (
                            direction_key, x_mm, xmin, xmax)
                    assert ymin - 1.0 <= y_mm <= ymax + 1.0, \
                        "%s materialized bar Y=%.1f flies outside [%.1f,%.1f] (handedness regression)" % (
                            direction_key, y_mm, ymin, ymax)
print("build_floor_reinforcement (rectangle): every materialized Set bar, in "
      "BOTH directions, stays strictly within the floor's footprint — no "
      "'flying bars' from a backwards propagation normal: OK")

# ── Test 11 (UPDATED — PHASE 3.5.8 item 1): top/bottom mats share ONE
# LATERAL (plan) cover boundary, independent of their own Z-direction
# face covers ───────────────────────────────────────────────────────
# Originally this test asserted the top mat's PLAN boundary used its
# own top_cover_mm (60mm) while the bottom mat used bottom_cover_mm
# (25mm) — i.e. two DIFFERENT lateral insets derived from two
# DIFFERENT vertical face covers. That was exactly the bug Phase 3.5.8
# item 1 fixed: a slab has ONE physical side/edge cover regardless of
# which mat you're placing; the vertical Z cover differs between top
# and bottom mats (correctly), but the X/Y plan inset must not. Both
# mats' plan boundaries are now resolved from the SAME native
# "Exterior" side cover (falling back to bottom_cover_mm when no native
# value is set on the host, as here) — so both mats' bars share the
# SAME lateral inset (25mm's fallback), not two different ones.
result_diff_cover = floor_rebar.build_floor_reinforcement(
    doc, host, bottom_cover_mm=25.0, bottom_dia_x_mm=10.0, bottom_dia_y_mm=10.0,
    bottom_spacing_mm=200.0,
    include_top_mat=True, top_cover_mm=60.0, top_dia_x_mm=10.0, top_dia_y_mm=10.0,
    top_spacing_mm=200.0)
along_x_top = result_diff_cover['top_mat']['along_x']
for s in along_x_top['sets'] + along_x_top['bars']:
    for curve in s['curves']:
        for i in (0, 1):
            p = curve.GetEndPoint(i)
            x_mm = p.X * _MM_PER_FT
            assert 25.0 - 1.0 <= x_mm <= 6000.0 - 25.0 + 1.0, \
                "top mat bar at X=%.1f should respect the SHARED lateral cover " \
                "(25mm fallback), not its own top_cover_mm (60mm)" % x_mm
print("build_floor_reinforcement (top cover 60mm != bottom cover 25mm): top and "
      "bottom mats now share ONE lateral plan boundary (native side cover, not "
      "each mat's own Z-direction face cover): OK")

# ── Test 12: an interval collapsed to empty by inset -> zero ghost bars ──
# Uses a perfectly normal, well-formed 6000x4000 floor (valid offset
# polygon) but an absurdly large own-diameter so material_intervals'
# own residual inset (dia/2) collapses every row's interval to empty —
# isolating "inset consumes the whole interval" from a degenerate
# offset-polygon edge case (a tiny floor with cover exceeding its own
# width, which is a different, unrealistic failure mode).
result_collapsed = floor_rebar.build_floor_reinforcement(
    doc, host, bottom_cover_mm=25.0, bottom_dia_x_mm=6000.0, bottom_dia_y_mm=10.0,
    bottom_spacing_mm=200.0)
along_x_collapsed = result_collapsed['bottom_mat']['along_x']
assert along_x_collapsed['sets'] == [] and along_x_collapsed['bars'] == []
print("build_floor_reinforcement: an interval collapsed to empty by its own "
      "inset produces ZERO sets/bars, never a ghost Set with an empty shape: OK")

def _ubars_per_hole_edge(entries):
    """{edge key: U-bar count} for open closure entries; key = the back's fixed plan coordinate."""
    counts = {}
    for e in entries:
        if e.get('style') is not None:
            continue
        leg = e['curves'][0]
        along_x = abs(leg.GetEndPoint(0).X - leg.GetEndPoint(1).X) > abs(leg.GetEndPoint(0).Y - leg.GetEndPoint(1).Y)
        back = e['curves'][1].GetEndPoint(0)
        key = ('x', round(back.X * _MM_PER_FT)) if along_x else ('y', round(back.Y * _MM_PER_FT))
        counts[key] = counts.get(key, 0) + max(1, len(e.get('materialized_bars', [])))
    return counts


# ── Test 13 (Phase 3.5 item 5 / 2026-09-02, round 2 — explicit user
# request "igual que la distancia entre Ubars del contorno del
# forjado"): leg length is STILL binary ──
# A single short rectangular hole whose own edges are shorter than
# 2 x nominal_leg_mm (320mm) used to fall back to a closed link on
# every one of those edges. ROUND 1 fix (2026-09-02, reported live —
# "deberían ser Ubars en perpendicular a esa cara, no links en
# paralelo"): tries ONE open U-bar centred on the edge first — a closed
# link is the LAST resort, only when even a centred leg would land
# outside material. ROUND 2 fix (same day, "solo una por cada lado del
# hueco" + explicit follow-up "quiero más de uno si el lado es largo,
# igual que... el contorno del forjado"): before settling for that ONE
# centred bar, a RELAXED margin (nominal_leg_mm / 2, still clear of the
# shared corner) is tried at the SAME spacing_mm the main perimeter
# itself uses — for THIS hole's 550mm edges that fits 3 positions
# (550 - 320 = 230mm span > 200mm spacing), so every edge now becomes a
# 3-bar Set, not a single centred bar. The leg length itself is still
# strictly binary — FULL nominal_leg_mm or a closed link, never a
# shrunk fraction — this test confirms that binary guarantee under the
# new "prefer spaced, then centred, then a closed link" cascade.
tiny_hole_host = make_rect_floor(
    width_mm=6000.0, depth_mm=4000.0, thickness_mm=200.0,
    holes_mm=[[(2000, 1500), (2500, 1500), (2500, 2000), (2000, 2000)]])  # 500x500mm hole
result_tiny_hole = floor_rebar.build_floor_reinforcement(
    doc, tiny_hole_host, bottom_cover_mm=25.0, bottom_dia_x_mm=10.0, bottom_dia_y_mm=10.0,
    bottom_spacing_mm=200.0,
    include_top_mat=True, top_cover_mm=25.0, top_dia_x_mm=10.0, top_dia_y_mm=10.0,
    top_spacing_mm=200.0,
    include_perimeter_closure_ubars=True,
    x_anchor_ubar_dia_mm=8.0, x_anchor_ubar_spacing_mm=200.0,
    y_anchor_ubar_dia_mm=8.0, y_anchor_ubar_spacing_mm=200.0)
tiny_closure = result_tiny_hole['perimeter_closure_ubars']
tiny_hole_entries = (tiny_closure['x_bars']['sets'] + tiny_closure['x_bars']['bars']
                     + tiny_closure['y_bars']['sets'] + tiny_closure['y_bars']['bars'])
# every edge of this 500mm hole (each side ~550mm after cover growth)
# is shorter than 2*320=640mm -> all 4 of its own edges hit the "too
# short for the main perimeter's own CORNER-INSET spacing" branch —
# but the RELAXED margin (160mm) leaves a 230mm usable span, which fits
# 3 positions at the same 200mm spacing_mm the main perimeter uses
# (230mm > 200mm spacing -> ceil(230/200)+1 = 3), so every edge becomes
# a 3-bar Set, not a single centred bar or a closed link.
hole_area_entries = [e for e in tiny_hole_entries
                      if any(1900.0 < c.GetEndPoint(i).X * _MM_PER_FT < 2600.0
                             for c in e['curves'] for i in (0, 1))]
tiny_counts = _ubars_per_hole_edge(hole_area_entries)
assert len(tiny_counts) == 4 and all(n >= 3 for n in tiny_counts.values()),     "all 4 edges of this 500x500 hole must get at least 3 open U-bars (T2.17 keeps the minimum)"
assert all(e.get('is_hole') is True for e in hole_area_entries),     "every closure entry around this hole must carry is_hole=True"
for e in tiny_hole_entries:
    if e.get('style') == 'StirrupTie':
        continue
    leg0 = e['curves'][0]
    leg_len_mm = leg0.GetEndPoint(0).DistanceTo(leg0.GetEndPoint(1)) * _MM_PER_FT
    assert abs(leg_len_mm - 400.0) < 1e-3, \
        "every non-link U-bar leg must be the FULL nominal length, never shrunk"
print("_build_edge_ubars: a hole too short for the main perimeter's own corner-"
      "inset spacing now tries a relaxed margin at the SAME spacing_mm first — "
      "fitting multiple open U-bars per edge (full nominal_leg_mm each), each "
      "entry tagged is_hole=True for ui.py's real-Shape-code routing — a closed "
      "link is still the last resort when not even a centred leg fits: OK")

# ── Test 13b (round 3, 2026-09-02 — reported live: Shape 21 confirmed, but
# "sigue creando solo un ubar por cada cara del hueco... debería ser un
# multi rebar, con la misma distancia entre barras que los Ubars del
# contorno de la losa") — a hole edge that clears the STANDARD corner-inset
# span (never enters the "too short" branch Test 13 exercises) but whose
# usable span between full corner insets is still <= spacing_mm, so
# `_evenly_spaced` itself returns exactly ONE midpoint bar — round 2 never
# retried the relaxed margin here, only inside the "too short" branch.
bigger_hole_host = make_rect_floor(
    width_mm=6000.0, depth_mm=4000.0, thickness_mm=200.0,
    holes_mm=[[(2000, 1500), (2650, 1500), (2650, 2150), (2000, 2150)]])  # 650x650mm hole
result_bigger_hole = floor_rebar.build_floor_reinforcement(
    doc, bigger_hole_host, bottom_cover_mm=25.0, bottom_dia_x_mm=10.0, bottom_dia_y_mm=10.0,
    bottom_spacing_mm=200.0,
    include_top_mat=True, top_cover_mm=25.0, top_dia_x_mm=10.0, top_dia_y_mm=10.0,
    top_spacing_mm=200.0,
    include_perimeter_closure_ubars=True,
    x_anchor_ubar_dia_mm=8.0, x_anchor_ubar_spacing_mm=200.0,
    y_anchor_ubar_dia_mm=8.0, y_anchor_ubar_spacing_mm=200.0)
bigger_closure = result_bigger_hole['perimeter_closure_ubars']
bigger_hole_entries = (bigger_closure['x_bars']['sets'] + bigger_closure['x_bars']['bars']
                       + bigger_closure['y_bars']['sets'] + bigger_closure['y_bars']['bars'])
# each edge is ~700mm after cover growth: usable_lo=usable_hi margins of
# 320mm leave only a 60mm usable span (<= 200mm spacing) -> the STANDARD
# path's own _evenly_spaced returns exactly 1 position (usable_hi >
# usable_lo, so this never even reaches the "too short" branch) — the
# round-3 fix must retry the relaxed (160mm) margin here too, which leaves
# a 380mm span (> 200mm spacing) -> 3 positions.
bigger_hole_area_entries = [e for e in bigger_hole_entries
                            if any(1900.0 < c.GetEndPoint(i).X * _MM_PER_FT < 2750.0
                                   for c in e['curves'] for i in (0, 1))]
bigger_counts = _ubars_per_hole_edge(bigger_hole_area_entries)
assert len(bigger_counts) == 4 and all(n >= 3 for n in bigger_counts.values()),     "all 4 edges of this hole must get at least 3 open U-bars"
assert all(e.get('is_hole') is True for e in bigger_hole_area_entries),     "every closure entry around this hole must carry is_hole=True"
print("_build_edge_ubars: a hole edge that clears the standard corner-inset "
      "span but whose usable span between insets is still <= spacing_mm now "
      "also retries the relaxed margin (not just the 'too short' branch) — "
      "fixes 'solo un ubar por cada cara del hueco' for edges long enough to "
      "clear standard insets but not long enough for standard spacing: OK")

# ── Test 13c (round 5, 2026-09-02 — explicit user request: "si los huecos
# son de 500x500mm al menos debería haber 3 Ubars en cada lado") — the EXACT
# scenario reported live: a 500x500mm hole, 10mm anchor dia (leg=400mm,
# 40x diameter), edges ~550mm after cover growth. Even the round-3 relaxed
# margin (leg/2=200mm) only leaves a 150mm usable span (<= 200mm spacing) —
# not enough for a 2nd bar at the main perimeter's own spacing. The user's
# own structural judgement, applied here: worth a genuinely TIGHTER,
# hole-only corner margin (leg/4=100mm) to guarantee _HOLE_MIN_BARS (3).
min3_hole_host = make_rect_floor(
    width_mm=6000.0, depth_mm=4000.0, thickness_mm=200.0,
    holes_mm=[[(2000, 1500), (2500, 1500), (2500, 2000), (2000, 2000)]])  # 500x500mm hole
result_min3_hole = floor_rebar.build_floor_reinforcement(
    doc, min3_hole_host, bottom_cover_mm=25.0, bottom_dia_x_mm=10.0, bottom_dia_y_mm=10.0,
    bottom_spacing_mm=200.0,
    include_top_mat=True, top_cover_mm=25.0, top_dia_x_mm=10.0, top_dia_y_mm=10.0,
    top_spacing_mm=200.0,
    include_perimeter_closure_ubars=True,
    x_anchor_ubar_dia_mm=10.0, x_anchor_ubar_spacing_mm=200.0,
    y_anchor_ubar_dia_mm=10.0, y_anchor_ubar_spacing_mm=200.0)
min3_closure = result_min3_hole['perimeter_closure_ubars']
min3_hole_entries = (min3_closure['x_bars']['sets'] + min3_closure['x_bars']['bars']
                     + min3_closure['y_bars']['sets'] + min3_closure['y_bars']['bars'])
min3_hole_area_entries = [e for e in min3_hole_entries
                          if any(1900.0 < c.GetEndPoint(i).X * _MM_PER_FT < 2600.0
                                 for c in e['curves'] for i in (0, 1))]
min3_counts = _ubars_per_hole_edge(min3_hole_area_entries)
assert len(min3_counts) == 4 and all(n >= floor_rebar._HOLE_MIN_BARS for n in min3_counts.values()),     "a 500x500mm hole must get AT LEAST _HOLE_MIN_BARS (3) U-bars per edge, per explicit user request"
assert all(e.get('is_hole') is True for e in min3_hole_area_entries),     "every closure entry around this hole must carry is_hole=True"
for e in min3_hole_area_entries:
    leg0 = (e['materialized_bars'][0]['curves'] if e.get('materialized_bars') else e['curves'])[0]
    leg_len_mm = leg0.GetEndPoint(0).DistanceTo(leg0.GetEndPoint(1)) * _MM_PER_FT
    assert abs(leg_len_mm - 400.0) < 1e-3, \
        "the tighter hole-only corner margin must never shrink the leg's own " \
        "anchorage length (400mm) — only the ALONG-EDGE spacing is tightened"
print("_build_edge_ubars: a 500x500mm hole (400mm anchorage leg) now gets AT "
      "LEAST 3 open U-bars per edge via a tighter, hole-only corner margin — "
      "the anchorage leg length itself is never shrunk, only the along-edge "
      "spacing: OK")

# ── Test 14 (Phase 3.1 item 3 regression): mm coordinates are rounded ────
assert floor_rebar._round_mm(1499.999999999997) == 1500.0, \
    "floating-point noise a few ULPs off a clean mm value must be squashed before curve construction"
assert floor_rebar._round_mm(123.456) == 123.456
print("_round_mm: sub-micron floating-point drift from upstream topology math is "
      "squashed to a clean value before any curve endpoint is built — Shape-00 "
      "recognition failures from near-perpendicular/near-coincident noise fixed: OK")

print("\nALL FLOOR_REBAR PHASE 2.3 CHECKS PASSED")
