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

_LIB = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'lib'))
_EXT_LIB = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', 'lib'))
if _EXT_LIB not in sys.path:
    sys.path.insert(0, _EXT_LIB)
from tests_support import revit_stubs  # noqa: E402


_load = revit_stubs.load_module


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
# BUG FIX (2026-09-02, round 2, live report — "los Ubars salen al revés")
# — a real 90° hook curls INTO the surrounding concrete (toward the
# section's own mid-depth), never OUT past the nearest free face it's
# already sitting at cover distance from.
assert all(h['y1_mm'] > h['y0_mm'] for h in bottom_stubs), \
    "bottom (B2) hooks must bend UP, INTO the section (toward mid-depth)"
assert all(h['y1_mm'] < h['y0_mm'] for h in top_stubs), \
    "top (T2) hooks must bend DOWN, INTO the section (toward mid-depth)"
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

# ── compute_wall_elevation_preview: starter bars (round 2, live report
# "los starter bars no se ven") ──────────────────────────────────────
wall_no_starters = rebar_preview.compute_wall_elevation_preview(
    6000.0, 3000.0, 25.0, 12.0, 200.0, 200.0)
assert wall_no_starters['starter_extension_mm'] == 0.0
assert all(b['y0_mm'] >= 0.0 for b in wall_no_starters['bars']), \
    "no starters requested -> every vertical bar segment stays within [0, height_mm]"

wall_starters = rebar_preview.compute_wall_elevation_preview(
    6000.0, 3000.0, 25.0, 12.0, 200.0, 200.0,
    include_starters=True, starter_length_mm=600.0)
assert wall_starters['starter_extension_mm'] == 600.0
_vert_inset_mm = 25.0 + 12.0 / 2.0  # cover + vert_dia/2 — matches the function's own 'inset'
_expected_y0 = _vert_inset_mm - 600.0
assert all(abs(b['y0_mm'] - _expected_y0) < 1e-6 for b in wall_starters['bars']), \
    "every vertical bar's own y0_mm must extend exactly starter_length_mm below " \
    "its own normal starting point (cover + half diameter above y=0), not below y=0 itself"

wall_starters_auto = rebar_preview.compute_wall_elevation_preview(
    6000.0, 3000.0, 25.0, 12.0, 200.0, 200.0, include_starters=True)
assert wall_starters_auto['starter_extension_mm'] == max(40.0 * 12.0, 500.0), \
    "starter_length_mm omitted -> the SAME 40x-diameter/500mm-minimum default " \
    "build_wall_reinforcement itself uses"
print("compute_wall_elevation_preview: starter bars (straight extension below "
      "the wall's own base, matching build_wall_reinforcement's own "
      "include_starter_bars) are now visible in the preview, with the correct "
      "default length when omitted: OK")


# ── compute_wall_section_preview (round 2, 2026-09-02 — live report
# "la sección no se ve correctamente, necesitaríamos una sección bien
# hecha") — REWRITTEN into a real vertical cut through the wall's
# thickness: vertical bars as continuous LINES (one per face), horizontal
# bars as DOTS spaced at horiz_spacing_mm, both centred at y=0 (matching
# _draw_simple_section_preview's own centred convention, shared with
# compute_beam_section_preview). ──────────────────────────────────────
wall_section = rebar_preview.compute_wall_section_preview(
    250.0, 900.0, 25.0, 12.0, 10.0, 200.0,
    both_faces=True, include_ties=True, tie_spacing_mm=400.0, include_ubars=True)
assert len(wall_section['bar_lines']) == 2, \
    "one continuous vertical bar LINE per face (both_faces=True)"
for bl in wall_section['bar_lines']:
    assert bl['diameter_mm'] == 12.0
    assert bl['y0_mm'] < 0.0 < bl['y1_mm'], \
        "vertical bar lines must be centred at y=0, spanning both above and below it"
assert len(wall_section['bars']) >= 4, \
    "multiple horizontal-bar dot rows (2 faces x >=2 rows at 900mm height / 200mm spacing)"
assert all(b['diameter_mm'] == 10.0 for b in wall_section['bars'])
assert len(wall_section['ties']) >= 1
assert len(wall_section['ubars']) == 1

# both_faces=False -> exactly 1 bar_line, and ties/ubars silently empty
# even if requested (they only make sense with 2 faces to connect).
wall_section_1face = rebar_preview.compute_wall_section_preview(
    250.0, 900.0, 25.0, 12.0, 10.0, 200.0,
    both_faces=False, include_ties=True, tie_spacing_mm=400.0, include_ubars=True)
assert len(wall_section_1face['bar_lines']) == 1
assert wall_section_1face['ties'] == [] and wall_section_1face['ubars'] == []

try:
    rebar_preview.compute_wall_section_preview(
        250.0, 900.0, 25.0, 12.0, 10.0, 200.0, include_ties=True)
    raise AssertionError("include_ties without tie_spacing_mm must raise ValueError")
except ValueError:
    pass

print("compute_wall_section_preview: now a real vertical cut through the "
      "wall's thickness — continuous vertical bar lines + spaced "
      "horizontal-bar dots + tie/U-bar detail, centred to match "
      "_draw_simple_section_preview's shared convention: OK")

print()
print("ALL REBAR_PREVIEW PHASE 2.6 CHECKS PASSED")
