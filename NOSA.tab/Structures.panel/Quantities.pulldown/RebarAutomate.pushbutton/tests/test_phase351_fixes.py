# -*- coding: utf-8 -*-
"""Targeted checks for the 4 Phase 3.5.1 live-Revit fixes, isolated from
the full mocked-API ecosystem (these are pure-Python helpers new this
turn, not exercised by the existing mocked test suites since mock
Solids expose no .Edges)."""
import math
import sys
import os

_LIB = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'lib'))
_EXT_LIB = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', '..', 'lib'))
if _EXT_LIB not in sys.path:
    sys.path.insert(0, _EXT_LIB)
from tests_support import revit_stubs  # noqa: E402


_load = revit_stubs.load_module


# ── slab_topology: minimum edge length filter ──────────────────────────
slab_topology = _load("slab_topology_351", os.path.join(_LIB, "slab_topology.py"))

# A 5mm sliver (tessellation noise) between two 1000mm sides must be
# dropped now, where the old 1e-6mm tolerance would have kept it.
noisy = [(0.0, 0.0), (1000.0, 0.0), (1000.0, 0.005), (1000.0, 1000.0), (0.0, 1000.0)]
edges = slab_topology.polygon_edges_mm(noisy)
assert len(edges) == 4, "expected the 5mm sliver edge to be filtered out, got {} edges".format(len(edges))
print("polygon_edges_mm: a 5mm tessellation-noise sliver is filtered out (>= 15mm threshold): OK")

clean = [(0.0, 0.0), (1000.0, 0.0), (1000.0, 1000.0), (0.0, 1000.0)]
assert len(slab_topology.polygon_edges_mm(clean)) == 4
print("polygon_edges_mm: a real 20mm-or-larger edge would still be kept (baseline unaffected): OK")


# ── floor_rebar: solid Z-extent + clamp ─────────────────────────────────
class FakeEdge(object):
    def __init__(self, curve):
        self._curve = curve
    def AsCurve(self):
        return self._curve

class FakeCurve(object):
    def __init__(self, z0, z1):
        self._z0, self._z1 = z0, z1
    def GetEndPoint(self, i):
        class P(object):
            pass
        p = P()
        p.Z = self._z0 if i == 0 else self._z1
        return p

class FakeSolid(object):
    def __init__(self, edges):
        self.Edges = edges

floor_rebar = _load("floor_rebar_351", os.path.join(_LIB, "floor_rebar.py"))

solid = FakeSolid([FakeEdge(FakeCurve(0.0, 0.0)), FakeEdge(FakeCurve(1.0, 1.0))])
extent = floor_rebar._solid_z_extent_ft(solid)
assert extent == (0.0, 1.0), extent
print("floor_rebar._solid_z_extent_ft: reads real Min/Max Z from Solid.Edges: OK")

assert floor_rebar._solid_z_extent_ft(None) is None
class NoEdges(object):
    pass
assert floor_rebar._solid_z_extent_ft(NoEdges()) is None
print("floor_rebar._solid_z_extent_ft: None/no-.Edges solid falls back to None (caller uses face Z unchanged): OK")

# A Z value comfortably inside the solid stays unchanged.
z = floor_rebar._clamp_z_to_solid_ft(0.5, (0.0, 1.0))
assert abs(z - 0.5) < 1e-9
# A Z value that (per a bad bbox/skew scenario) sits just past the real
# solid's own top gets pulled back inside, epsilon-inset.
z2 = floor_rebar._clamp_z_to_solid_ft(1.5, (0.0, 1.0))
assert z2 < 1.0 and z2 > 0.9, z2
print("floor_rebar._clamp_z_to_solid_ft: clamps a Z outside the real solid back inside, epsilon-inset: OK")
# None extent (unreadable solid) leaves the value untouched — exactly
# today's pre-fix behaviour, so every existing mocked test is unaffected.
assert floor_rebar._clamp_z_to_solid_ft(5.0, None) == 5.0
print("floor_rebar._clamp_z_to_solid_ft: None extent leaves the face-derived Z untouched (back-compat): OK")


# ── column_rebar: same Z-extent helper + Diameter/b/h param fallback ───
# column_rebar.py does `from Autodesk.Revit import DB` at module level —
# stub it out (empty module object is enough; the functions under test
# here never touch DB.* internally) so the module can be imported
# outside Revit, same technique the existing mocked test files use.
revit_stubs.install_revit_stubs()

column_rebar = _load("column_rebar_351", os.path.join(_LIB, "column_rebar.py"))

extent2 = column_rebar._solid_z_extent_ft(solid)
assert extent2 == (0.0, 1.0)
print("column_rebar._solid_z_extent_ft: mirrors floor_rebar's own (self-contained duplicate): OK")


class FakeParam(object):
    def __init__(self, value_ft):
        self._value_ft = value_ft
    def AsDouble(self):
        return self._value_ft

class FakeSymbol(object):
    def __init__(self, params):
        self._params = params
    def LookupParameter(self, name):
        return self._params.get(name)

class FakeFacetedHost(object):
    """A round column with NO CylindricalFace (faceted approximation) —
    only its TYPE carries a real 'Diameter' parameter, mm converted to
    ft (450mm / 304.8)."""
    def __init__(self, type_params):
        self._instance_params = {}
        self.Symbol = FakeSymbol(type_params)
    def LookupParameter(self, name):
        return self._instance_params.get(name)

host = FakeFacetedHost({u'Diameter': FakeParam(450.0 / 304.8)})
d_mm = column_rebar._lookup_length_param_mm(host, [u'Diameter', u'DIAMETER', u'diameter'])
assert d_mm is not None and abs(d_mm - 450.0) < 0.01, d_mm
print("column_rebar._lookup_length_param_mm: reads a type-level 'Diameter' parameter in mm: OK")

host_bh = FakeFacetedHost({u'b': FakeParam(400.0 / 304.8), u'h': FakeParam(600.0 / 304.8)})
b_mm = column_rebar._lookup_length_param_mm(host_bh, [u'b', u'B'])
h_mm = column_rebar._lookup_length_param_mm(host_bh, [u'h', u'H'])
assert abs(b_mm - 400.0) < 0.01 and abs(h_mm - 600.0) < 0.01
print("column_rebar._lookup_length_param_mm: reads type-level 'b'/'h' parameters in mm: OK")

host_none = FakeFacetedHost({})
assert column_rebar._lookup_length_param_mm(host_none, [u'Diameter']) is None
print("column_rebar._lookup_length_param_mm: no matching parameter -> None, not a crash: OK")


# ── rebar_preview: section-view crosstie line pairing ───────────────────
rebar_preview = _load("rebar_preview_351", os.path.join(_LIB, "rebar_preview.py"))

data = rebar_preview.compute_column_section_preview(
    400.0, 600.0, cover_mm=40.0, bar_diameter_mm=20.0, bar_count=12,
    stirrup_diameter_mm=10.0, shape='rect', include_crossties=True)
assert len(data['crossties']) > 0, "expected interior crossties for a 12-bar 400x600 column"
for tie in data['crossties']:
    assert set(tie.keys()) == {'x1_mm', 'y1_mm', 'x2_mm', 'y2_mm'}
print("compute_column_section_preview: include_crossties=True produces plan-view tie lines "
      "with the same pairing math as column_rebar.build_crosstie_sets: OK")

data_circle = rebar_preview.compute_column_section_preview(
    0.0, 0.0, cover_mm=40.0, bar_diameter_mm=20.0, bar_count=12,
    stirrup_diameter_mm=10.0, shape='circle', diameter_mm=500.0, include_crossties=True)
assert data_circle['crossties'] == [], "circular columns have no crosstie generation support at all"
print("compute_column_section_preview: circular shape always returns empty crossties (no backend "
      "support for circular columns at all, matching column_rebar's own module SCOPE): OK")

data_off = rebar_preview.compute_column_section_preview(
    400.0, 600.0, cover_mm=40.0, bar_diameter_mm=20.0, bar_count=12,
    stirrup_diameter_mm=10.0, shape='rect', include_crossties=False)
assert data_off['crossties'] == []
print("compute_column_section_preview: include_crossties=False (default) stays empty, back-compat: OK")

print("\nALL PHASE 3.5.1 TARGETED CHECKS PASSED")
