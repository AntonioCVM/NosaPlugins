# -*- coding: utf-8 -*-
"""Targeted checks for the Phase 2.6 (2026-09-02) preview fixes, reported
live: 90° hooks invisible in the Footings/Slabs preview, beam section bar
dots visually overlapping the stirrup outline, a missing beam elevation
view, and the wall preview mislabelled + not centred + missing its own
cross-section. rebar_preview.py is deliberately Revit-free (see its own
module docstring), so this runs under a plain Python interpreter, no
mocked-API scaffolding needed — same convention as test_phase351_fixes.py."""
import sys
import os
import importlib.util

_LIB = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'lib'))


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


rebar_preview = _load("rebar_preview_26", os.path.join(_LIB, "rebar_preview.py"))

# ── compute_section_preview: 90° hooks now produce visible geometry ─────
data_no_hooks = rebar_preview.compute_section_preview(
    1000.0, 400.0, 25.0, 12.0, 12.0,
    include_top_mat=True, top_cover_mm=25.0, top_dia_x_mm=10.0, top_dia_y_mm=10.0)
assert data_no_hooks['hooks'] == [], \
    "bottom_hooks/top_hooks default False -> no hook geometry at all"

data_hooks = rebar_preview.compute_section_preview(
    1000.0, 400.0, 25.0, 12.0, 12.0,
    include_top_mat=True, top_cover_mm=25.0, top_dia_x_mm=10.0, top_dia_y_mm=10.0,
    bottom_hooks=True, top_hooks=True)
assert len(data_hooks['hooks']) == 4, \
    "2 stubs (one per end) for EACH of B2 and T2 = 4 total, got {}".format(len(data_hooks['hooks']))
bottom_stubs = [h for h in data_hooks['hooks'] if h['layer'] == 'B2']
top_stubs = [h for h in data_hooks['hooks'] if h['layer'] == 'T2']
assert len(bottom_stubs) == 2 and len(top_stubs) == 2
assert all(h['y1_mm'] < h['y0_mm'] for h in bottom_stubs), \
    "bottom (B2) hooks must bend DOWN, toward the nearest free face"
assert all(h['y1_mm'] > h['y0_mm'] for h in top_stubs), \
    "top (T2) hooks must bend UP, toward the nearest free face"
print("compute_section_preview: bottom_hooks/top_hooks now produce real, "
      "direction-correct hook geometry instead of having no effect at all: OK")

# only bottom_hooks — top has no top mat here, so top_hooks would be
# meaningless; only 2 stubs expected (bottom mat only).
data_bottom_only = rebar_preview.compute_section_preview(
    1000.0, 400.0, 25.0, 12.0, 12.0, bottom_hooks=True)
assert len(data_bottom_only['hooks']) == 2
print("compute_section_preview: bottom_hooks alone (no top mat) -> 2 stubs, no crash: OK")


# ── compute_beam_section_preview: bars must nest INSIDE the stirrup ─────
# BUG FIX verification — before the fix, bar_ih == stirrup ih (SAME
# inset), so a bar dot centred there would poke half its own radius
# outside the stirrup rectangle. Now bar_ih must be strictly SMALLER
# than the stirrup's own half_h_mm by at least the bar's own radius.
beam_data = rebar_preview.compute_beam_section_preview(
    300.0, 500.0, 40.0, 20.0, 3, 3, 8.0)
stirrup = beam_data['stirrup']
top_bar_y = max(b['y_mm'] for b in beam_data['bars'])
bar_radius_mm = 20.0 / 2.0
assert top_bar_y <= stirrup['half_h_mm'] - bar_radius_mm + 1e-6, \
    "a bar dot's own OUTER edge must land at or inside the stirrup's inner " \
    "face, never straddling/overlapping the stirrup outline (top_bar_y={}, " \
    "stirrup half_h={}, bar radius={})".format(top_bar_y, stirrup['half_h_mm'], bar_radius_mm)
# Corner bars (x = +/- bar_iw) must likewise stay clear of the stirrup's
# own side edges.
corner_bar_x = max(b['x_mm'] for b in beam_data['bars'])
assert corner_bar_x <= stirrup['half_w_mm'] - bar_radius_mm + 1e-6, \
    "a corner bar dot must not straddle the stirrup's own side edge either"
print("compute_beam_section_preview: bar dots now nest strictly INSIDE the "
      "stirrup outline (own two-inset convention, matching columns/footings) "
      "instead of straddling it — fixes 'las barras... parece que chocan': OK")


# ── compute_beam_elevation_preview (new, Phase 2.6) ──────────────────────
elev = rebar_preview.compute_beam_elevation_preview(
    6000.0, 500.0, 40.0, 20.0, 20.0, 8.0, 200.0, end_offset_mm=50.0)
assert elev['section']['width_mm'] == 6000.0
top_line = next(b for b in elev['bars'] if b['layer'] == 'top')
bottom_line = next(b for b in elev['bars'] if b['layer'] == 'bottom')
assert top_line['x0_mm'] == 0.0 and top_line['x1_mm'] == 6000.0
assert top_line['y0_mm'] > bottom_line['y0_mm'], "top bar line must sit above the bottom bar line"
assert len(elev['stirrups']) >= 2, "a 6m beam at 200mm spacing must show multiple stirrup ticks"
assert all(50.0 <= s['x_mm'] <= 5950.0 for s in elev['stirrups']), \
    "every stirrup tick must fall within the end_offset-inset span"

# Densify-ends case — expect a mix of tight and normal spacing (more
# stirrups than the plain uniform case at the SAME base spacing).
elev_dense = rebar_preview.compute_beam_elevation_preview(
    6000.0, 500.0, 40.0, 20.0, 20.0, 8.0, 200.0, end_offset_mm=50.0,
    densify_ends=True, dense_spacing_mm=100.0, confine_length_mm=1000.0)
assert len(elev_dense['stirrups']) > len(elev['stirrups']), \
    "densify_ends with a tighter dense_spacing_mm must produce MORE stirrup " \
    "positions than the uniform-spacing case"
print("compute_beam_elevation_preview: full-length top/bottom bar lines + "
      "evenly-spaced (optionally end-densified) stirrup ticks, matching "
      "beam_rebar's own even-distribution/end-densification convention: OK")


# ── compute_wall_elevation_preview: horiz_dia_mm now actually used ──────
wall_default = rebar_preview.compute_wall_elevation_preview(
    6000.0, 3000.0, 25.0, 12.0, 200.0, 200.0)
default_horiz_dia = wall_default['horizontals'][0]['diameter_mm']
assert abs(default_horiz_dia - 12.0 * 0.85) < 1e-6, \
    "omitting horiz_dia_mm must keep the old fallback (vert_dia_mm * 0.85) for compatibility"

wall_real = rebar_preview.compute_wall_elevation_preview(
    6000.0, 3000.0, 25.0, 12.0, 200.0, 200.0, horiz_dia_mm=16.0)
real_horiz_dia = wall_real['horizontals'][0]['diameter_mm']
assert real_horiz_dia == 16.0, \
    "passing horiz_dia_mm must use the REAL value, not the derived fallback " \
    "(fixes TxtWallHorizDia having no effect on the preview at all)"
print("compute_wall_elevation_preview: horiz_dia_mm (e.g. TxtWallHorizDia) "
      "now genuinely affects the drawn horizontal mesh thickness instead of "
      "being silently ignored: OK")


# ── compute_wall_section_preview: sanity check it's a valid, usable call
# (this function already existed but was never wired into the UI at all
# until this round — confirming its own contract still holds). ──────────
wall_section = rebar_preview.compute_wall_section_preview(
    250.0, 25.0, 12.0, both_faces=True, include_ties=True, include_ubars=True)
assert len(wall_section['bars']) == 4  # 2 faces x (1 main + 1 edge dot each)
assert len(wall_section['ties']) == 1
assert len(wall_section['ubars']) == 1
print("compute_wall_section_preview: still returns a valid dots+tie+ubar "
      "cross-section through the wall's own thickness, now actually wired "
      "into the Walls tab's own (new) Section Preview canvas: OK")

print()
print("ALL REBAR_PREVIEW PHASE 2.6 CHECKS PASSED")
