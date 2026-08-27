# -*- coding: utf-8 -*-
"""
NOSA.RebarAutomate — Section Preview Engine (Phase 2, redrawn Phase 2.4)
============================================================================

Meant to be loaded in isolation the same way every other module in this
plugin is:

    from nosa_utils.bootstrap import load_module
    rebar_preview = load_module(
        'rebar_preview', os.path.join(os.path.dirname(__file__), 'rebar_preview.py'))

A lightweight, pure-Python drawing-DATA engine for the WPF Canvas
preview in each category tab. Given the current UI parameters for a
section (cover, bar diameters, spacing), computes 2D LOCAL-coordinate
positions — dots for longitudinal bars, line endpoints for stirrups/
ties/U-bar outlines — within a rectangle (or circle, for round columns,
a later phase) representing the concrete section.

DELIBERATELY DECOUPLED FROM REVIT AND FROM WPF: this module returns
plain Python dicts/tuples only — no System.Windows.Shapes objects, no
live Revit geometry, no Transaction, no Document. ui.py is responsible
for taking this module's output and drawing it onto an actual WPF
Canvas (Ellipse for bar dots, Line/Rectangle for stirrup/tie/section
outlines) — keeping this engine fast, UI-toolkit-agnostic, and cheap to
recompute on every keystroke in a diameter/spacing field without
touching the Revit document at all. This NEVER places real
reinforcement, it only previews a proposed solution.

PHASE 2 SCOPE: two-way mat cross-sections (footings/floors) only —
B1/B2 (bottom mat) and, if requested, T1/T2 (top mat) bar layers, using
the EXACT SAME Z-layering formulas as footing_rebar.build_mat_bar_set /
floor_rebar.build_floor_reinforcement (Phase 5.6's B1/B2/T1/T2
convention), reimplemented here in plain arithmetic rather than by
calling into those modules — this module stays fully independent of
rebar_engine.py/footing_rebar.py/floor_rebar.py (and of the Revit API
they depend on) by design, so it works even outside a Revit session
(e.g. under a plain Python test runner, as this project's established
mocked-API test discipline already relies on for every other module).
Column/beam section previews (circular sections, stirrup outlines) are
a later phase's addition — see compute_section_preview's own docstring
for the exact Phase 2 return shape.

PHASE 2.4 — DOTS vs LINES (correct cross-section drawing convention)
------------------------------------------------------------------
Phase 2's preview drew EVERY layer (B1/B2/T1/T2) identically as a row
of dots — geometrically wrong for a real cross-section: B1/T1 (the
"X-Bars" direction) run PERPENDICULAR to this cross-section's own cut
plane, so they correctly show as dots (you're looking at their cut
end); B2/T2 (the orthogonal "Y-Bars" direction) run IN-PLANE with the
section, so in a real detail drawing they show as a CONTINUOUS LINE
spanning the section's width, resting on/hanging from the X-Bars'
dots — the actual "weave" a real cross-section conveys. This module
now returns X-Bars (B1/T1) as `bars` (dots, unchanged) and Y-Bars
(B2/T2) as a new `lines` list (continuous horizontal segments at their
own Z). A `side_cover_mm` margin (defaults to bottom_cover_mm — this
module has no dedicated "side cover" UI concept of its own, so it
reuses the main cover value as a disclosed, illustrative proxy) insets
BOTH the dots and the lines from the section's own left/right edges,
so the drawn rectangle's outer face and the reinforcement's own extent
are visibly different — the side-cover margin the live-test brief
asked to see. Perimeter closure U-bars now hug that SAME cover-inset
position (matching the real backend, where a closure bar anchors at
the cover line, not the raw concrete face), not the raw outer edge.
"""
import math


def compute_section_preview(width_mm, thickness_mm,
                             bottom_cover_mm, bottom_dia_x_mm, bottom_dia_y_mm,
                             include_top_mat=False, top_cover_mm=None,
                             top_dia_x_mm=None, top_dia_y_mm=None,
                             dots_per_layer=6,
                             include_perimeter_ubars=False,
                             x_anchor_dia_mm=None, y_anchor_dia_mm=None,
                             side_cover_mm=None):
    """
    Cross-section preview data for a two-way mat (footing or floor): a
    rectangle (width x thickness) with a row of dots per reinforcement
    layer present — B1/B2 always, T1/T2 if include_top_mat — positioned
    at the SAME Z each layer would actually sit at, per the B1/B2/T1/T2
    Z-layering convention (see footing_rebar.build_mat_bar_set's Phase
    5.6 docstring for the authoritative formulas, reused here as plain
    arithmetic):

        B1 (Layer 1, bottom mat): y = bottom_cover_mm
        B2 (Layer 2, bottom mat): y = bottom_cover_mm + bottom_dia_x_mm
        T1 (Layer 1, top mat):    y = thickness_mm - top_cover_mm - top_dia_x_mm
        T2 (Layer 2, top mat):    y = thickness_mm - top_cover_mm
                                      - top_dia_x_mm - top_dia_y_mm

    `dots_per_layer` is PURELY illustrative (this function has no
    concept of a real spacing-derived bar count or a real section
    width — those come from the actual host geometry, which this module
    deliberately never touches) — it just gives the preview a
    recognisable "row of bars" look; it is NOT the actual number of
    bars a real run would create.

    Args:
        width_mm          (float): representative section width, mm —
                          purely for drawing proportions, not tied to
                          any real host.
        thickness_mm       (float): representative section thickness
                          (mat depth), mm.
        bottom_cover_mm, bottom_dia_x_mm, bottom_dia_y_mm (float): bottom
                          mat parameters — dia_x_mm is B1's diameter,
                          dia_y_mm is B2's.
        include_top_mat    (bool): whether to also show T1/T2.
        top_cover_mm, top_dia_x_mm, top_dia_y_mm (float or None):
                          required if include_top_mat is True.
        dots_per_layer      (int): how many illustrative dots to draw
                          per layer, minimum 1.
        include_perimeter_ubars (bool): PHASE 2.1 — whether to also
                          compute the two Perimeter Closure U-Bar
                          profiles (one hugging the section's left edge,
                          one hugging its right edge) — see
                          'perimeter_ubars' below. REQUIRES
                          include_top_mat=True (a closure U-bar's back
                          spans a bottom-layer Y to the CORRESPONDING
                          top-layer Y; there is no top layer to reach
                          without one).
        x_anchor_dia_mm, y_anchor_dia_mm (float or None): required if
                          include_perimeter_ubars is True — the closure
                          U-bar's own diameter for the pair anchoring
                          B1/T1 (x_anchor_dia_mm) and the pair anchoring
                          B2/T2 (y_anchor_dia_mm), purely for the
                          preview's own line-weight/label, matching
                          footing_rebar.build_perimeter_closure_ubar_sets'
                          x_anchor_dia_mm/y_anchor_dia_mm parameters.
        side_cover_mm      (float or None): PHASE 2.4 — lateral cover
                          margin insetting both `bars` and `lines` from
                          the section's own left/right edges. Defaults
                          to bottom_cover_mm (see module docstring).

    Returns:
        {
          'section': {'width_mm': float, 'height_mm': float, 'shape': 'rect'},
          'bars':     [{'x_mm': float, 'y_mm': float, 'diameter_mm': float,
                        'layer': 'B1'|'T1'}, ...],   # X-Bars — perpendicular
                        to the section, drawn as dots.
          'lines':    [{'x0_mm': float, 'x1_mm': float, 'y_mm': float,
                        'diameter_mm': float, 'layer': 'B2'|'T2'}, ...],
                        # Y-Bars — in-plane with the section, drawn as a
                        continuous line resting on/hanging from the
                        X-Bars' dots at the correct Z.
          'stirrups': [],   # always empty in Phase 2 — mats have no ties
          'perimeter_ubars': [
              {'edge': 'left'|'right', 'anchor': 'x'|'y',
               'points': [(x_mm, y_mm), ...] (4 points, an open
                          polyline — leg, back, leg, matching
                          build_perimeter_closure_ubar_sets' own
                          [leg, back, leg] curve chain, reprojected onto
                          this 2D section),
               'diameter_mm': float,
               'style': 'primary' | 'weave'},   # 'primary' = the X-anchor
                          (B1/T1) pair, drawn solid; 'weave' = the
                          Y-anchor (B2/T2) pair, drawn with the
                          gradient/transparency treatment ui.py applies
                          to visualise the two directions crossing at
                          the corner without clashing — always empty if
                          include_perimeter_ubars is False.
          ],
        }

    Raises:
        ValueError: if width_mm/thickness_mm aren't positive, if
        include_top_mat is True but any of its required arguments is
        None, if include_perimeter_ubars is True but include_top_mat is
        False, or if include_perimeter_ubars is True but x_anchor_dia_mm
        / y_anchor_dia_mm is None.
    """
    if width_mm <= 0 or thickness_mm <= 0:
        raise ValueError(u'width_mm and thickness_mm must both be positive.')
    if include_top_mat and None in (top_cover_mm, top_dia_x_mm, top_dia_y_mm):
        raise ValueError(u'include_top_mat requires top_cover_mm, top_dia_x_mm '
                          u'and top_dia_y_mm to all be given.')
    if include_perimeter_ubars:
        if not include_top_mat:
            raise ValueError(u'include_perimeter_ubars requires include_top_mat — '
                              u'the closure U-bars anchor between the bottom and '
                              u'top mats.')
        if x_anchor_dia_mm is None or y_anchor_dia_mm is None:
            raise ValueError(u'include_perimeter_ubars requires x_anchor_dia_mm '
                              u'and y_anchor_dia_mm to both be given.')

    n = max(1, int(dots_per_layer))
    half_w = width_mm / 2.0
    margin_mm = bottom_cover_mm if side_cover_mm is None else side_cover_mm
    inner_half_w = max(0.0, half_w - margin_mm)

    def _row(y_mm, diameter_mm, layer):
        # X-Bars (B1/T1) — perpendicular to the section, drawn as dots,
        # inset from the raw edge by the side-cover margin.
        if n == 1:
            xs = [0.0]
        else:
            step = (2.0 * inner_half_w) / float(n - 1)
            xs = [-inner_half_w + i * step for i in range(n)]
        return [{'x_mm': x, 'y_mm': y_mm, 'diameter_mm': diameter_mm, 'layer': layer} for x in xs]

    def _line(y_mm, diameter_mm, layer):
        # Y-Bars (B2/T2) — in-plane with the section, drawn as ONE
        # continuous segment spanning the same cover-inset width.
        return {'x0_mm': -inner_half_w, 'x1_mm': inner_half_w,
                'y_mm': y_mm, 'diameter_mm': diameter_mm, 'layer': layer}

    b1_y = bottom_cover_mm
    b2_y = bottom_cover_mm + bottom_dia_x_mm
    t1_y = t2_y = None

    bars = _row(b1_y, bottom_dia_x_mm, 'B1')
    lines = [_line(b2_y, bottom_dia_y_mm, 'B2')]

    if include_top_mat:
        t1_y = thickness_mm - top_cover_mm - top_dia_x_mm
        t2_y = thickness_mm - top_cover_mm - top_dia_x_mm - top_dia_y_mm
        bars.extend(_row(t1_y, top_dia_x_mm, 'T1'))
        lines.append(_line(t2_y, top_dia_y_mm, 'T2'))

    perimeter_ubars = []
    if include_perimeter_ubars:
        leg_reach_mm = width_mm * 0.12  # illustrative only — see docstring

        def _ubar_polyline(edge, y_bottom, y_top):
            # Hugs the SAME cover-inset position the dots/lines use
            # (matching the real backend, where a closure bar anchors
            # at the cover line, not the raw concrete face) — the
            # earlier "floating U-bars" bug was this using a 0..width_mm
            # range while every dot uses a centred one; now both use
            # the identical -inner_half_w..+inner_half_w range.
            if edge == 'left':
                x_edge, x_leg = -inner_half_w, -inner_half_w + leg_reach_mm
            else:
                x_edge, x_leg = inner_half_w, inner_half_w - leg_reach_mm
            return [(x_leg, y_bottom), (x_edge, y_bottom), (x_edge, y_top), (x_leg, y_top)]

        for edge in ('left', 'right'):
            perimeter_ubars.append({
                'edge': edge, 'anchor': 'x',
                'points': _ubar_polyline(edge, b1_y, t1_y),
                'diameter_mm': x_anchor_dia_mm, 'style': 'primary',
            })
            perimeter_ubars.append({
                'edge': edge, 'anchor': 'y',
                'points': _ubar_polyline(edge, b2_y, t2_y),
                'diameter_mm': y_anchor_dia_mm, 'style': 'weave',
            })

    return {
        'section': {'width_mm': width_mm, 'height_mm': thickness_mm, 'shape': 'rect'},
        'bars': bars,
        'lines': lines,
        'stirrups': [],
        'perimeter_ubars': perimeter_ubars,
    }


# ══════════════════════════════════════════════════════════════════════════
# PHASE 3 — Column cross-section (plan view)
# ══════════════════════════════════════════════════════════════════════════

def _distribute_bar_count_preview(total_count, half_w_mm, half_d_mm):
    """
    Pure-Python mirror of column_rebar.distribute_bar_count — this
    module stays fully independent of column_rebar.py/the Revit API by
    design (see module docstring), so the same small formula is
    reimplemented here rather than imported, matching the precedent
    already set for the B1/B2/T1/T2 Z-layering formulas above.
    """
    total_count = max(4, int(total_count))
    pair_sum = total_count / 2.0 + 2.0
    edge_total = half_w_mm + half_d_mm
    if edge_total <= 0:
        n_u = n_v = max(2, int(round(pair_sum / 2.0)))
    else:
        n_u = max(2, int(round(pair_sum * half_w_mm / edge_total)))
        n_v = max(2, int(round(pair_sum - n_u)))
    return n_u, n_v


def _perimeter_positions_preview(half_w_mm, half_d_mm, n_u, n_v):
    """Pure-Python mirror of column_rebar._perimeter_positions — see
    that function's own docstring for the corner-deduplication logic
    this reproduces exactly."""
    def _edge(lo, hi, n):
        if n == 1:
            return [(lo + hi) / 2.0]
        step = (hi - lo) / float(n - 1)
        return [lo + i * step for i in range(n)]

    us = _edge(-half_w_mm, half_w_mm, n_u)
    vs = _edge(-half_d_mm, half_d_mm, n_v)
    positions, seen = [], set()

    def _add(u, v):
        key = (round(u, 6), round(v, 6))
        if key not in seen:
            seen.add(key)
            positions.append((u, v))

    for u in us:
        _add(u, half_d_mm)
        _add(u, -half_d_mm)
    for v in vs:
        _add(half_w_mm, v)
        _add(-half_w_mm, v)
    return positions


def _crosstie_lines_preview(half_w_mm, half_d_mm, n_u, n_v, layout='all'):
    """
    Pure-Python mirror of column_rebar.build_crosstie_sets's pairing
    logic (plan-view projection: no Z/normal needed here) — see that
    function's own docstring for the corner-exclusion and
    layout='alternate' semantics this reproduces exactly, so the
    preview draws the SAME intermediate-bar <-> direct-mirror pairs
    the backend actually creates.

    Returns:
        list[(x1_mm, y1_mm, x2_mm, y2_mm)]
    """
    def _edge(lo, hi, n):
        if n == 1:
            return [(lo + hi) / 2.0]
        step = (hi - lo) / float(n - 1)
        return [lo + i * step for i in range(n)]

    us = _edge(-half_w_mm, half_w_mm, n_u)
    vs = _edge(-half_d_mm, half_d_mm, n_v)
    us_interior = us[1:-1] if n_u > 2 else []
    vs_interior = vs[1:-1] if n_v > 2 else []

    if layout == 'alternate':
        us_interior = us_interior[0::2]
        vs_interior = vs_interior[0::2]

    lines = [(u, half_d_mm, u, -half_d_mm) for u in us_interior]
    lines += [(half_w_mm, v, -half_w_mm, v) for v in vs_interior]
    return lines


def compute_column_section_preview(width_mm, depth_mm, cover_mm, bar_diameter_mm,
                                    bar_count, stirrup_diameter_mm,
                                    shape='rect', diameter_mm=None,
                                    include_crossties=False, crosstie_layout='all'):
    """
    Column cross-section preview (plan view, looking down the column).

    PHASE 3.4 item 4 — real host geometry, not always a fixed
    illustrative rectangle: if shape == 'circle' (see
    column_rebar.detect_column_geometry), draws a circular outline of
    the REAL diameter_mm, a concentric circular stirrup ring inset by
    cover_mm + stirrup_diameter_mm/2, and bar_count dots distributed
    EVENLY BY ANGLE around the circle (a common, simple round-column
    convention — this project's generation pipeline does not itself
    support circular columns yet, see column_rebar's own module SCOPE;
    this is a preview-only improvement so the UI doesn't show a
    misleading rectangle for a round host). Otherwise (the default,
    'rect'), draws the rectangle at its REAL width_mm x depth_mm
    aspect ratio (previously always a fixed illustrative 400x300mm
    regardless of the real selected column) — same bar-perimeter logic
    as before, unchanged for the rectangular case's numbers.

    Args:
        width_mm, depth_mm    (float): section dimensions, mm — real,
                               if a column is selected and shape=='rect'
                               (see detect_column_geometry), otherwise
                               illustrative. Ignored if shape=='circle'.
        cover_mm               (float): nominal cover, mm.
        bar_diameter_mm         (float): vertical bar diameter, mm.
        bar_count               (int): total desired vertical bar count
                               — see distribute_bar_count.
        stirrup_diameter_mm     (float): stirrup bar diameter, mm.
        shape                   ('rect' or 'circle'): which outline to
                               draw.
        diameter_mm             (float or None): REQUIRED if
                               shape=='circle' — the real column
                               diameter, mm.
        include_crossties       (bool): PHASE 3.5.1 item 4 — if True
                               (and shape=='rect'; column_rebar has no
                               circular-column generation support at
                               all, so this is always empty for
                               'circle'), also compute the interior
                               crosstie lines — see
                               _crosstie_lines_preview.
        crosstie_layout          ('all' or 'alternate'): only used if
                               include_crossties — see
                               column_rebar.build_crosstie_sets.

    Returns:
        {
          'section': {'width_mm': float, 'height_mm': float,
                      'shape': 'rect'|'circle',
                      'diameter_mm': float},  # only present for 'circle'
          'stirrup': {'half_w_mm': float, 'half_d_mm': float,
                      'radius_mm': float},    # only present for 'circle'
          'bars':    [{'x_mm': float, 'y_mm': float, 'diameter_mm': float}, ...],
          'crossties': [{'x1_mm': float, 'y1_mm': float,
                         'x2_mm': float, 'y2_mm': float}, ...],
                       # empty unless include_crossties and shape=='rect'
                       # with genuinely interior bars.
        }

    Raises:
        ValueError: if width_mm/depth_mm (shape=='rect') or
        diameter_mm (shape=='circle') aren't positive.
    """
    if shape == 'circle':
        if diameter_mm is None or diameter_mm <= 0:
            raise ValueError(u'diameter_mm must be positive for a circular column.')
        radius = diameter_mm / 2.0
        stirrup_radius = max(0.0, radius - (cover_mm + stirrup_diameter_mm / 2.0))
        bar_radius = max(0.0, radius - (cover_mm + stirrup_diameter_mm + bar_diameter_mm / 2.0))
        n = max(3, int(bar_count))
        bars = []
        for i in range(n):
            theta = 2.0 * math.pi * i / n
            bars.append({'x_mm': bar_radius * math.cos(theta), 'y_mm': bar_radius * math.sin(theta),
                         'diameter_mm': bar_diameter_mm})
        return {
            'section': {'width_mm': diameter_mm, 'height_mm': diameter_mm,
                        'shape': 'circle', 'diameter_mm': diameter_mm},
            'stirrup': {'half_w_mm': stirrup_radius, 'half_d_mm': stirrup_radius,
                        'radius_mm': stirrup_radius},
            'bars': bars,
            'crossties': [],
        }

    if width_mm <= 0 or depth_mm <= 0:
        raise ValueError(u'width_mm and depth_mm must both be positive.')

    half_w = width_mm / 2.0
    half_d = depth_mm / 2.0

    stirrup_inset = cover_mm + stirrup_diameter_mm / 2.0
    stirrup_half_w = max(0.0, half_w - stirrup_inset)
    stirrup_half_d = max(0.0, half_d - stirrup_inset)

    bar_inset = cover_mm + stirrup_diameter_mm + bar_diameter_mm / 2.0
    bar_half_w = max(0.0, half_w - bar_inset)
    bar_half_d = max(0.0, half_d - bar_inset)

    n_u, n_v = _distribute_bar_count_preview(bar_count, bar_half_w, bar_half_d)
    positions = _perimeter_positions_preview(bar_half_w, bar_half_d, n_u, n_v)

    crossties = []
    if include_crossties:
        crossties = [
            {'x1_mm': x1, 'y1_mm': y1, 'x2_mm': x2, 'y2_mm': y2}
            for (x1, y1, x2, y2) in _crosstie_lines_preview(
                bar_half_w, bar_half_d, n_u, n_v, crosstie_layout)
        ]

    return {
        'section': {'width_mm': width_mm, 'height_mm': depth_mm, 'shape': 'rect'},
        'stirrup': {'half_w_mm': stirrup_half_w, 'half_d_mm': stirrup_half_d},
        'bars': [{'x_mm': u, 'y_mm': v, 'diameter_mm': bar_diameter_mm} for (u, v) in positions],
        'crossties': crossties,
    }


def _evenly_spaced_preview(lo, hi, spacing):
    """Pure-Python mirror of column_rebar._evenly_spaced / footing_rebar.
    _evenly_spaced — same contract, duplicated here for the same
    independence reason as every other small formula in this module."""
    span = hi - lo
    if span <= 0:
        return []
    if span <= spacing:
        return [(lo + hi) / 2.0]
    n = int(math.ceil(span / spacing)) + 1
    actual_spacing = span / float(n - 1)
    return [lo + i * actual_spacing for i in range(n)]


def compute_column_elevation_preview(width_mm, height_mm, cover_mm, bar_diameter_mm,
                                      bar_count, stirrup_diameter_mm,
                                      dense_spacing_mm, normal_spacing_mm,
                                      densify_at_nodes, include_starter_bars,
                                      starter_bar_length_mm=None,
                                      floor_splits_mm=None,
                                      use_cranked_laps=False,
                                      crank_offset_mm=None, crank_slope=6.0,
                                      floor_bands_mm=None,
                                      include_crossties=False):
    """
    PHASE 3.1 (multi-story + cranked laps — PHASE 3.2) — column
    ELEVATION preview (front view, looking at one face): vertical bars
    as line SEGMENTS and horizontal link/tie lines at illustrative Z
    positions mirroring the SAME joint-zone densification logic
    column_rebar.generate_column_stirrup_zones applies (reimplemented
    here in plain arithmetic, per this module's established
    independence-from-column_rebar.py convention — see module
    docstring). Only the DISTINCT X (width-direction) bar positions are
    drawn — bars sharing an X but differing in depth would overlap in a
    genuine front elevation anyway, exactly like a real elevation
    drawing only shows the visible face's bars.

    PHASE 3.2 — mirrors column_rebar.build_story_segment_chains: if
    floor_splits_mm is given, each bar position is broken into one
    segment per storey (0 -> first split -> ... -> height_mm) instead
    of one full-height segment, with a starter at every INTERMEDIATE
    split (always) and at the column's own top (only if
    include_starter_bars) — straight, or a diagonal crank-then-straight
    kink if use_cranked_laps, exactly mirroring
    column_rebar.build_cranked_starter's geometry so the preview stays
    honest about what the real generator will build. 'bars' entries
    changed shape accordingly (see Returns) — this is a deliberate,
    disclosed break from the single-segment-per-bar shape the
    no-splits/no-crank case used to return alone; that case's NUMBERS
    are unchanged, only the key names generalised to a segment
    (x0/y0/x1/y1) instead of a single fixed x with y0/y1.

    Args:
        width_mm, height_mm     (float): representative section width
                                and column height, mm — illustrative
                                only.
        cover_mm                 (float): nominal cover, mm.
        bar_diameter_mm           (float): vertical bar diameter, mm.
        bar_count                 (int): total desired vertical bar
                                count — see distribute_bar_count.
        stirrup_diameter_mm       (float): stirrup/link diameter, mm.
        dense_spacing_mm          (float): link spacing at the joint
                                zones (or everywhere, if
                                densify_at_nodes is False and this is
                                unused).
        normal_spacing_mm         (float): link spacing in the middle
                                span (or everywhere, if
                                densify_at_nodes is False).
        densify_at_nodes          (bool): whether to show 3 zones
                                (denser at both ends) or one uniform
                                zone.
        include_starter_bars      (bool): whether the column's OWN top
                                also gets a starter — every
                                INTERMEDIATE floor split always gets
                                one regardless (see
                                column_rebar.build_story_segment_chains).
        starter_bar_length_mm     (float or None): lap length used at
                                EVERY starter (intermediate splits AND,
                                if include_starter_bars, the top) — mm,
                                defaults to 40x bar_diameter_mm (the
                                same rough multiplier
                                column_rebar.default_lap_length_mm
                                itself defaults to) if not given.
        floor_splits_mm           (list[float] or None): illustrative
                                floor-top elevations, mm from the
                                column base, strictly between 0 and
                                height_mm — see
                                column_rebar.find_floor_split_elevations_ft
                                (converted to mm by the caller). None or
                                empty means an ordinary single-story
                                column — the pre-3.2 behaviour exactly.
        use_cranked_laps          (bool): if True, every starter kinks
                                inward first — see
                                column_rebar.build_cranked_starter.
        crank_offset_mm           (float or None): inward crank shift,
                                mm — defaults to 2 x bar_diameter_mm,
                                matching
                                column_rebar.build_column_reinforcement's
                                own disclosed default.
        crank_slope               (float): the "1:N" slope's N. Default
                                6 (the requested "1:6").
        floor_bands_mm            (list[(float, float)] or None):
                                PHASE 3.4 item 2 — (bottom_mm, top_mm)
                                pairs, mm from the column base, one per
                                intersecting floor — any illustrative
                                link Z that falls INSIDE one of these
                                bands is dropped, so the preview stops
                                showing links running through a floor's
                                own thickness, matching the real
                                generator's _subtract_floor_bands. None
                                means no exclusion (pre-3.4 behaviour).
        include_crossties         (bool): PHASE 3.4 item 5 — if True
                                AND there is at least one genuinely
                                interior bar X position, draws a short
                                horizontal crosstie line "crossing the
                                core" at every (post floor-band
                                exclusion) link Z position.

    Returns:
        {
          'section': {'width_mm': float, 'height_mm': float, 'shape': 'rect'},
          'bars':  [{'x0_mm': float, 'y0_mm': float, 'x1_mm': float,
                     'y1_mm': float, 'diameter_mm': float}, ...],  # one
                    or more segments per bar position — vertical unless
                    a crank kink is drawn there; y1_mm can exceed
                    height_mm at a starter.
          'links': [{'y_mm': float, 'half_w_mm': float}, ...],  # one
                    horizontal line per illustrative link position,
                    excluding any inside a floor_bands_mm band.
          'crossties': [{'y_mm': float, 'half_w_mm': float}, ...],  #
                    empty unless include_crossties and there's a
                    genuinely interior bar position to tie.
          'floor_splits_mm': list[float],  # echoes the input, sorted
                    and clamped to (0, height_mm) — for drawing the
                    floor-level reference lines.
          'starter_extension_mm': float,  # the COLUMN'S OWN TOP
                    starter length — 0.0 if not include_starter_bars,
                    even when intermediate splits still show one.
        }

    Raises:
        ValueError: if width_mm/height_mm aren't positive.
    """
    if width_mm <= 0 or height_mm <= 0:
        raise ValueError(u'width_mm and height_mm must both be positive.')

    half_w = width_mm / 2.0
    stirrup_inset = cover_mm + stirrup_diameter_mm / 2.0
    stirrup_half_w = max(0.0, half_w - stirrup_inset)

    bar_inset = cover_mm + stirrup_diameter_mm + bar_diameter_mm / 2.0
    bar_half_w = max(0.0, half_w - bar_inset)
    # A representative depth just for the perimeter-count split (see
    # docstring — only the resulting DISTINCT X positions matter here).
    bar_half_d = bar_half_w * 0.75
    n_u, n_v = _distribute_bar_count_preview(bar_count, bar_half_w, bar_half_d)
    positions = _perimeter_positions_preview(bar_half_w, bar_half_d, n_u, n_v)
    bar_x_positions = sorted(set(round(u, 3) for u, _ in positions))

    lap_mm = (starter_bar_length_mm if starter_bar_length_mm is not None
              else bar_diameter_mm * 40.0)
    starter_mm = lap_mm if include_starter_bars else 0.0

    splits_mm = sorted(z for z in (floor_splits_mm or [])
                        if 0.0 < z < height_mm)
    resolved_crank_offset_mm = (crank_offset_mm if crank_offset_mm is not None
                                 else 2.0 * bar_diameter_mm)

    bars = []
    for x in bar_x_positions:
        bars.extend(_build_elevation_bar_segments(
            x, height_mm, splits_mm, lap_mm, include_starter_bars,
            use_cranked_laps, resolved_crank_offset_mm, crank_slope, bar_diameter_mm))

    # Link Z positions — mirrors column_rebar.generate_column_stirrup_zones'
    # own bottom/middle/top zone logic; default_joint_zone_length_mm's
    # own formula (max(larger cross-section dim, clear height/6, 450mm))
    # is approximated here using width_mm directly rather than the
    # stirrup's own cover-inset half-extents — a difference of a few mm
    # that doesn't matter for an illustrative elevation.
    joint_zone_mm = max(width_mm, height_mm / 6.0, 450.0)
    start_offset_mm = end_offset_mm = 50.0
    lo, hi = start_offset_mm, height_mm - end_offset_mm
    usable = hi - lo
    link_z_positions = []
    if usable > 0:
        if not densify_at_nodes or 2.0 * joint_zone_mm >= usable:
            spacing = (dense_spacing_mm if (densify_at_nodes and 2.0 * joint_zone_mm >= usable)
                       else normal_spacing_mm)
            link_z_positions = _evenly_spaced_preview(lo, hi, spacing)
        else:
            bottom_zone = _evenly_spaced_preview(lo, lo + joint_zone_mm, dense_spacing_mm)
            top_zone = _evenly_spaced_preview(hi - joint_zone_mm, hi, dense_spacing_mm)
            middle_zone = _evenly_spaced_preview(
                lo + joint_zone_mm, hi - joint_zone_mm, normal_spacing_mm)
            link_z_positions = sorted(set(bottom_zone + middle_zone + top_zone))

    bands = floor_bands_mm or []
    link_z_positions = [z for z in link_z_positions
                         if not any(b_lo < z < b_hi for (b_lo, b_hi) in bands)]

    links = [{'y_mm': z, 'half_w_mm': stirrup_half_w} for z in link_z_positions]

    crossties = []
    has_interior_bar = len(bar_x_positions) > 2  # more than just the 2 extreme corners
    if include_crossties and has_interior_bar:
        crosstie_half_w = stirrup_half_w * 0.5
        crossties = [{'y_mm': z, 'half_w_mm': crosstie_half_w} for z in link_z_positions]

    return {
        'section': {'width_mm': width_mm, 'height_mm': height_mm, 'shape': 'rect'},
        'bars': bars,
        'links': links,
        'crossties': crossties,
        'floor_splits_mm': splits_mm,
        'starter_extension_mm': starter_mm,
    }


def _build_elevation_bar_segments(x_mm, height_mm, splits_mm, lap_mm, include_starter_bars,
                                   use_cranked_laps, crank_offset_mm, crank_slope, bar_diameter_mm):
    """
    ONE bar position's segments for compute_column_elevation_preview,
    mirroring column_rebar.build_story_segment_chains: one segment per
    storey (0 -> first split -> ... -> height_mm), a starter at every
    INTERMEDIATE split (always, using lap_mm) and at the column's own
    top (only if include_starter_bars) — straight, or a diagonal
    crank-then-straight kink if use_cranked_laps, mirroring
    column_rebar.build_cranked_starter's own geometry (crank shifts the
    bar INWARD toward the section centre by crank_offset_mm while
    rising crank_slope times that, then continues straight up for
    lap_mm).
    """
    points_z = [0.0] + list(splits_mm) + [height_mm]
    segments = []
    cur_x = x_mm
    n_segments = len(points_z) - 1
    inward_sign = -1.0 if x_mm >= 0.0 else 1.0
    for i in range(n_segments):
        z0, z1 = points_z[i], points_z[i + 1]
        is_last = (i == n_segments - 1)
        segments.append({'x0_mm': cur_x, 'y0_mm': z0, 'x1_mm': cur_x, 'y1_mm': z1,
                          'diameter_mm': bar_diameter_mm})
        needs_starter = (not is_last) or include_starter_bars
        if not needs_starter:
            continue
        if use_cranked_laps:
            rise_mm = crank_slope * crank_offset_mm
            crank_x = cur_x + inward_sign * crank_offset_mm
            crank_z = z1 + rise_mm
            segments.append({'x0_mm': cur_x, 'y0_mm': z1, 'x1_mm': crank_x, 'y1_mm': crank_z,
                              'diameter_mm': bar_diameter_mm})
            segments.append({'x0_mm': crank_x, 'y0_mm': crank_z, 'x1_mm': crank_x,
                              'y1_mm': crank_z + lap_mm, 'diameter_mm': bar_diameter_mm})
            cur_x = crank_x
        else:
            segments.append({'x0_mm': cur_x, 'y0_mm': z1, 'x1_mm': cur_x, 'y1_mm': z1 + lap_mm,
                              'diameter_mm': bar_diameter_mm})
    return segments
