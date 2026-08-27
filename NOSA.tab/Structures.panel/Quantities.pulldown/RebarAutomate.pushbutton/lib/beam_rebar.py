# -*- coding: utf-8 -*-
"""
NOSA.RebarAutomate — Beam Rebar (Phase 2)
============================================================================

Category module for structural framing (beams). Loads rebar_engine.py
in isolation via imp.load_source (unique alias 're_engine'), matching
this extension's established sys.modules isolation convention.

Pure geometry/math — NO UI, no direct Rebar.CreateFromCurves calls of
its own. Every public function returns DB.Curve objects (or lists of
them) that a caller hands to rebar_engine.RebarWrapper for actual
element creation; this module never opens a Transaction itself, except
indirectly through rebar_engine.split_rebar_by_stock_length's caller
contract — split_rebar_by_stock_length itself does not open a
Transaction either (it is pure geometry, see its own docstring).

SCOPE
-----
Targets a STRAIGHT beam (a single Line location curve) with a
rectangular cross-section exposing exactly 4 usable planar faces: one
top, one bottom, two sides running parallel to the beam axis. A curved
beam, or one whose profile does not resolve to that face pattern (e.g.
a haunched/tapered beam, or a non-rectangular section), raises a clear
ValueError rather than silently producing wrong geometry — see
_beam_faces()'s docstring.
"""
import math
import os

from Autodesk.Revit import DB

_HERE = os.path.dirname(os.path.abspath(__file__))
re_engine = None


def _ensure_engine():
    global re_engine
    if re_engine is None:
        import imp
        re_engine = imp.load_source('re_engine', os.path.join(_HERE, 'rebar_engine.py'))
    return re_engine


_MM_PER_FT = 304.8


# ══════════════════════════════════════════════════════════════════════════
# Location curve & face classification
# ══════════════════════════════════════════════════════════════════════════

def get_beam_axis(host):
    """
    The beam's straight centreline, as a DB.Line.

    Args:
        host (DB.Element): the beam (structural framing) instance.

    Returns:
        DB.Line

    Raises:
        ValueError: if the host's Location isn't a LocationCurve, or
        its curve isn't a straight Line — this module's SCOPE is
        explicitly straight beams only (see module docstring).
    """
    loc = getattr(host, 'Location', None)
    curve = getattr(loc, 'Curve', None) if loc is not None else None
    if curve is None:
        raise ValueError(u'Host has no LocationCurve — not a line-based '
                          u'structural framing element?')
    if not isinstance(curve, DB.Line):
        raise ValueError(u'Beam centreline is not a straight Line — curved '
                          u'beams are not supported by this module yet.')
    return curve


def _beam_faces(cover_mgr, axis_dir):
    """
    Classify a beam host's planar faces into (top, bottom, side_a,
    side_b).

    top/bottom: normal's Z component above +0.7 / below -0.7 (same
    threshold as footing_rebar.get_footing_bottom_face — consistent
    across category modules).

    side_a/side_b: the two remaining faces whose normal is close to
    PERPENDICULAR to the beam axis (dot product with axis_dir near
    zero) — this specifically EXCLUDES the beam's own end-cut faces,
    whose normal runs roughly PARALLEL to the axis instead, so an end
    face is correctly never mistaken for a long side.

    Args:
        cover_mgr (rebar_engine.CoverGeometryManager)
        axis_dir  (DB.XYZ): unit vector, the beam's axis direction.

    Returns:
        (top, bottom, side_a, side_b) — each a HostFaceInfo.

    Raises:
        ValueError: if top, bottom, or exactly two side faces weren't
        found — see module docstring's SCOPE note.
    """
    top = bottom = None
    sides = []
    for f in cover_mgr.faces:
        z = f.normal.Z
        if z > 0.7:
            if top is None or f.normal.Z > top.normal.Z:
                top = f
            continue
        if z < -0.7:
            if bottom is None or f.normal.Z < bottom.normal.Z:
                bottom = f
            continue
        if abs(f.normal.DotProduct(axis_dir)) < 0.3:
            sides.append(f)

    if top is None or bottom is None:
        raise ValueError(u'Could not find both a top and a bottom face on '
                          u'this beam — is its profile a simple rectangle?')
    if len(sides) != 2:
        raise ValueError(
            u'Expected exactly 2 long side faces, found {} — non-rectangular '
            u'or tapered beam profiles are not supported by this module '
            u'yet.'.format(len(sides)))
    return top, bottom, sides[0], sides[1]


# ══════════════════════════════════════════════════════════════════════════
# Longitudinal bars
# ══════════════════════════════════════════════════════════════════════════

def _cross_section_point(p_ref, width_dir, height_dir, transverse_pt, vertical_pt):
    """
    Combine a transverse-position reference point (correct along
    width_dir, e.g. from a side face's cover offset) and a
    vertical-position reference point (correct along height_dir, e.g.
    from the top/bottom face's cover offset) into ONE cross-section
    point relative to p_ref — the width coordinate is taken from
    transverse_pt's own offset from p_ref, the height coordinate from
    vertical_pt's, each projected onto its relevant axis only (so
    neither point's position along the beam's AXIS direction — which is
    irrelevant here and may differ between the two — leaks into the
    result).

    Args:
        p_ref         (DB.XYZ): reference origin (e.g. the beam axis's
                      start point).
        width_dir     (DB.XYZ): unit vector, beam's local width axis.
        height_dir    (DB.XYZ): unit vector, beam's local height axis.
        transverse_pt (DB.XYZ): any point at the desired WIDTH position
                      (its height/axis position is ignored).
        vertical_pt   (DB.XYZ): any point at the desired HEIGHT position
                      (its width/axis position is ignored).

    Returns:
        DB.XYZ
    """
    w = (transverse_pt - p_ref).DotProduct(width_dir)
    h = (vertical_pt - p_ref).DotProduct(height_dir)
    return p_ref + width_dir.Multiply(w) + height_dir.Multiply(h)


def compute_longitudinal_bar_lines(axis_curve, face_info, side_a, side_b,
                                    cover_mm, n_bars, bar_diameter_mm=0.0):
    """
    Generate `n_bars` parallel longitudinal bar Lines along the beam's
    axis, offset inward from `face_info` (the beam's top or bottom
    face) by cover_mm, and evenly distributed across the beam's width
    between side_a and side_b (each inset by cover_mm +
    bar_diameter_mm/2 from its own face) — same even-distribution
    philosophy as footing_rebar._evenly_spaced / rebar_engine's
    stock-length splitting, so bars are spread across the full usable
    width rather than packed to one side.

    n_bars <= 1 places a single bar centred on the width.

    Args:
        axis_curve      (DB.Line): the beam's centreline, from
                         get_beam_axis().
        face_info        (rebar_engine.HostFaceInfo): top or bottom face.
        side_a, side_b   (rebar_engine.HostFaceInfo): the beam's two
                         long side faces.
        cover_mm         (float): nominal cover, mm.
        n_bars           (int): number of bars to place across the width.
        bar_diameter_mm  (float): used for the side inset.

    Returns:
        list[DB.Line], length n_bars (or empty if n_bars <= 0).
    """
    if n_bars <= 0:
        return []

    engine = _ensure_engine()
    p_start = axis_curve.GetEndPoint(0)
    p_end = axis_curve.GetEndPoint(1)
    axis_dir = axis_curve.Direction

    height_dir = face_info.normal.Normalize()
    width_dir = axis_dir.CrossProduct(height_dir).Normalize()

    vertical_pt = engine.compute_cover_point(face_info, cover_mm)
    side_inset_mm = cover_mm + bar_diameter_mm / 2.0
    edge_a = engine.compute_cover_point(side_a, side_inset_mm)
    edge_b = engine.compute_cover_point(side_b, side_inset_mm)

    if n_bars == 1:
        fractions = [0.5]
    else:
        fractions = [i / float(n_bars - 1) for i in range(n_bars)]

    bars = []
    for t in fractions:
        transverse_pt = edge_a + (edge_b - edge_a).Multiply(t)
        cs_start = _cross_section_point(p_start, width_dir, height_dir, transverse_pt, vertical_pt)
        cs_end = _cross_section_point(p_end, width_dir, height_dir, transverse_pt, vertical_pt)
        bars.append(DB.Line.CreateBound(cs_start, cs_end))
    return bars


def split_long_bars(bar_lines, stock_length_mm, lap_length_mm, lap_offset_mm=25.0):
    """
    Run every bar Line through
    rebar_engine.split_rebar_by_stock_length() and return one curve
    chain per input bar — a single-Line chain for bars already within
    stock_length_mm, or several segments (with lap-splice transverse
    offsets applied) for longer ones. This is the required hand-off to
    the Phase 1 engine for over-length longitudinal bars.

    Args:
        bar_lines        (list[DB.Line]): from
                          compute_longitudinal_bar_lines().
        stock_length_mm  (float): max commercial bar length.
        lap_length_mm    (float): normative lap length (caller-supplied
                          — see rebar_engine.split_rebar_by_stock_length's
                          docstring; this module does not calculate it).
        lap_offset_mm    (float): transverse lap separation, mm.

    Returns:
        list[list[DB.Curve]] — one chain per input bar, in the same
        order.
    """
    engine = _ensure_engine()
    chains = []
    for line in bar_lines:
        segments = engine.split_rebar_by_stock_length(
            line, stock_length_mm, lap_length_mm, lap_offset_mm)
        chains.append([seg.curve for seg in segments])
    return chains


# ══════════════════════════════════════════════════════════════════════════
# Stirrups
# ══════════════════════════════════════════════════════════════════════════

def _evenly_spaced(lo, hi, spacing):
    """Same contract as footing_rebar._evenly_spaced — duplicated here
    (not imported) so this module stays self-contained; see that
    module's copy for the full derivation/edge-case notes."""
    span = hi - lo
    if span <= 0:
        return []
    if span <= spacing:
        return [(lo + hi) / 2.0]
    n = int(math.ceil(span / spacing)) + 1
    actual_spacing = span / float(n - 1)
    return [lo + i * actual_spacing for i in range(n)]


def generate_stirrup_positions(axis_curve, spacing_mm, start_offset_mm=50.0, end_offset_mm=50.0):
    """
    Evenly-spaced stirrup positions (distance in mm along axis_curve
    from its start) between start_offset_mm and
    (beam length - end_offset_mm).

    Args:
        axis_curve       (DB.Line): the beam's centreline.
        spacing_mm       (float): max stirrup spacing, mm.
        start_offset_mm, end_offset_mm (float): clearance from each end
                         before the first / after the last stirrup
                         (e.g. to clear a supporting column).

    Returns:
        list[float] distances in mm, empty if the beam is too short for
        even one stirrup after the two end offsets.
    """
    length_mm = axis_curve.Length * _MM_PER_FT
    lo = start_offset_mm
    hi = length_mm - end_offset_mm
    return _evenly_spaced(lo, hi, spacing_mm)


def build_stirrup_rectangle(axis_curve, dist_mm, width_dir, height_dir,
                             half_width_mm, half_height_mm):
    """
    A closed 4-segment rectangular stirrup curve chain, centred on the
    beam axis at dist_mm from its start, in the plane perpendicular to
    the axis (spanned by width_dir/height_dir), sized by the given
    (already cover-inset) half-width / half-height.

    Args:
        axis_curve       (DB.Line): the beam's centreline.
        dist_mm          (float): distance along the axis from its start.
        width_dir, height_dir (DB.XYZ): the beam's local cross-section
                         axes (same ones used for longitudinal bars —
                         see compute_longitudinal_bar_lines).
        half_width_mm, half_height_mm (float): stirrup leg half-extents,
                         mm — typically the cover-inset distance from
                         the beam centreline to each side/top-bottom
                         face.

    Returns:
        list[DB.Line] — 4 segments forming a closed rectangle.
    """
    p_start = axis_curve.GetEndPoint(0)
    center = p_start + axis_curve.Direction.Multiply(dist_mm / _MM_PER_FT)
    w = width_dir.Multiply(half_width_mm / _MM_PER_FT)
    h = height_dir.Multiply(half_height_mm / _MM_PER_FT)
    p1 = center - w - h
    p2 = center + w - h
    p3 = center + w + h
    p4 = center - w + h
    return [DB.Line.CreateBound(p1, p2), DB.Line.CreateBound(p2, p3),
            DB.Line.CreateBound(p3, p4), DB.Line.CreateBound(p4, p1)]


# ══════════════════════════════════════════════════════════════════════════
# Orchestration
# ══════════════════════════════════════════════════════════════════════════

def build_beam_rebar_curves(doc, host, cover_mm, bar_diameter_mm,
                             n_top_bars, n_bottom_bars,
                             stirrup_spacing_mm, stirrup_bar_diameter_mm=8.0,
                             stirrup_start_offset_mm=50.0, stirrup_end_offset_mm=50.0,
                             stock_length_mm=12000.0, lap_length_mm=None,
                             lap_offset_mm=25.0):
    """
    High-level pipeline for one beam host:
      1. Read the beam's straight centreline (get_beam_axis).
      2. Build a CoverGeometryManager and classify top/bottom/side_a/
         side_b faces (_beam_faces).
      3. Build top and bottom longitudinal bar Lines
         (compute_longitudinal_bar_lines), splitting any that exceed
         stock_length_mm via rebar_engine.split_rebar_by_stock_length
         (split_long_bars).
      4. Build stirrup rectangles at every generate_stirrup_positions()
         position, sized from the cover-inset cross-section.

    Args:
        doc                     (DB.Document)
        host                    (DB.Element): the beam.
        cover_mm                (float): nominal cover, mm — applied to
                                top, bottom, and both sides alike.
        bar_diameter_mm         (float): longitudinal bar diameter, mm.
        n_top_bars, n_bottom_bars (int): bars across the width, top and
                                bottom.
        stirrup_spacing_mm      (float): max stirrup spacing, mm.
        stirrup_bar_diameter_mm (float): stirrup leg bar diameter, mm —
                                used only to inset the stirrup rectangle
                                one more radius inside the longitudinal-
                                bar cover line (stirrups sit just inside
                                the main bars, not on top of them).
        stirrup_start_offset_mm, stirrup_end_offset_mm (float): see
                                generate_stirrup_positions.
        stock_length_mm         (float): max commercial bar length —
                                see rebar_engine.split_rebar_by_stock_length.
        lap_length_mm           (float or None): REQUIRED if any
                                longitudinal bar ends up longer than
                                stock_length_mm — see Raises below.
        lap_offset_mm            (float): transverse lap separation, mm.

    Returns:
        {
          'top_bars':    list[list[DB.Curve]],
          'bottom_bars': list[list[DB.Curve]],
          'stirrups':    list[list[DB.Curve]],  # each a closed 4-segment chain
        }

    Raises:
        ValueError: from get_beam_axis / _beam_faces (see their
        docstrings), or if a longitudinal bar exceeds stock_length_mm
        while lap_length_mm was not supplied.
    """
    engine = _ensure_engine()
    axis = get_beam_axis(host)
    cover_mgr = engine.CoverGeometryManager(doc, host)
    top, bottom, side_a, side_b = _beam_faces(cover_mgr, axis.Direction)

    top_lines = compute_longitudinal_bar_lines(
        axis, top, side_a, side_b, cover_mm, n_top_bars, bar_diameter_mm)
    bottom_lines = compute_longitudinal_bar_lines(
        axis, bottom, side_a, side_b, cover_mm, n_bottom_bars, bar_diameter_mm)

    needs_split = any(l.Length * _MM_PER_FT > stock_length_mm
                       for l in (top_lines + bottom_lines))
    if needs_split and lap_length_mm is None:
        raise ValueError(
            u'At least one longitudinal bar exceeds stock_length_mm '
            u'({} mm) but lap_length_mm was not supplied — required to '
            u'split it.'.format(stock_length_mm))

    if lap_length_mm is not None:
        top_chains = split_long_bars(top_lines, stock_length_mm, lap_length_mm, lap_offset_mm)
        bottom_chains = split_long_bars(bottom_lines, stock_length_mm, lap_length_mm, lap_offset_mm)
    else:
        top_chains = [[l] for l in top_lines]
        bottom_chains = [[l] for l in bottom_lines]

    # Stirrup cross-section: cover-inset from top/bottom/sides, then one
    # more half-diameter in from the LONGITUDINAL bar's own diameter so
    # the stirrup leg sits just inside the main bars, not overlapping them.
    height_dir = top.normal.Normalize()
    width_dir = axis.Direction.CrossProduct(height_dir).Normalize()
    p_start = axis.GetEndPoint(0)

    inset_mm = cover_mm + bar_diameter_mm
    top_pt = engine.compute_cover_point(top, inset_mm)
    bottom_pt = engine.compute_cover_point(bottom, inset_mm)
    side_a_pt = engine.compute_cover_point(side_a, inset_mm)
    side_b_pt = engine.compute_cover_point(side_b, inset_mm)

    half_height_mm = abs((top_pt - p_start).DotProduct(height_dir)
                          - (bottom_pt - p_start).DotProduct(height_dir)) / 2.0 * _MM_PER_FT
    half_width_mm = abs((side_a_pt - p_start).DotProduct(width_dir)
                         - (side_b_pt - p_start).DotProduct(width_dir)) / 2.0 * _MM_PER_FT

    stirrup_positions = generate_stirrup_positions(
        axis, stirrup_spacing_mm, stirrup_start_offset_mm, stirrup_end_offset_mm)
    stirrups = [
        build_stirrup_rectangle(axis, d, width_dir, height_dir, half_width_mm, half_height_mm)
        for d in stirrup_positions
    ]

    return {'top_bars': top_chains, 'bottom_bars': bottom_chains, 'stirrups': stirrups}
