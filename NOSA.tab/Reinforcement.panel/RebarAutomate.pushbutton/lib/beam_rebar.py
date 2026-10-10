# -*- coding: utf-8 -*-
"""
NOSA.RebarAutomate — Beam Rebar (Phase 2)
============================================================================

Category module for structural framing (beams). Loads rebar_engine.py
in isolation via nosa_utils.bootstrap.load_module (unique alias
're_engine'), matching this extension's established sys.modules
isolation convention.

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
        # PHASE F0 — migrated from imp.load_source to
        # nosa_utils.bootstrap.load_module (tries importlib first,
        # falls back to imp). Relies on ui.py having already added the
        # extension's shared lib/ to sys.path, same as this module
        # already implicitly relied on ui.py running first.
        from nosa_utils.bootstrap import load_module
        re_engine = load_module('re_engine', os.path.join(_HERE, 'rebar_engine.py'))
    return re_engine


_MM_PER_FT = 304.8


def _column_rebar():
    """column_rebar (interior_tie_layout), the copy ui.py loaded if any."""
    import sys
    mod = sys.modules.get('column_rebar')
    if mod is None:
        from nosa_utils.bootstrap import load_module
        mod = load_module('column_rebar', os.path.join(_HERE, 'column_rebar.py'))
    return mod


def build_interior_tie_sets(stirrup_sets, section_origin, axis_dir, width_dir, height_dir,
                            bar_half_width_mm, bar_half_height_mm, n_top, n_bottom,
                            bar_diameter_mm, link_diameter_mm, link_bend_diameter_mm=None,
                            layout='all'):
    """
    Interior links and 135/135 crossties for a beam, laid out like its stirrups (one Set per
    stirrup zone, lifted one link diameter along the axis): the column rule of
    column_rebar.interior_tie_layout across the row with more bars (top and bottom faces).
    Returns [{'curves', 'normal', 'array_length_mm', 'spacing_mm', 'style', 'layer'}, ...].
    """
    n_u = max(n_top or 0, n_bottom or 0)
    if n_u <= 2:
        return []
    shapes = _column_rebar().interior_tie_layout(
        bar_half_width_mm, bar_half_height_mm, n_u, 2, layout,
        bar_diameter_mm, link_diameter_mm, link_bend_diameter_mm)
    sets = []
    for sset in stirrup_sets:
        positions = sset.get('positions') or []
        if not positions:
            continue
        start = positions[0] + link_diameter_mm
        length = max(0.0, positions[-1] - positions[0] - link_diameter_mm)
        base = section_origin + axis_dir.Multiply(start / _MM_PER_FT)
        for shape in shapes:
            pts = _column_rebar().hook_side_points(
                [base + width_dir.Multiply(u / _MM_PER_FT) + height_dir.Multiply(v / _MM_PER_FT)
                 for u, v in shape['points']], shape, width_dir, height_dir, axis_dir)
            count = len(pts) if shape['closed'] else len(pts) - 1
            sets.append({
                'curves': [DB.Line.CreateBound(pts[i], pts[(i + 1) % len(pts)]) for i in range(count)],
                'normal': axis_dir, 'array_length_mm': length,
                'spacing_mm': sset['spacing_mm'], 'style': 'StirrupTie',
                'layer': 'crosstie' if shape['kind'] == 'crosstie' else 'interior_stirrup'})
    return sets


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


def _clamp_axis_to_bbox(axis, host):
    """
    BUG FIX (2026-09-01, ROUND 2 2026-09-02) — reported live: "la
    armadura principal sale fuera de las vigas". ROUND 1 clamped to
    `host.get_BoundingBox(None)`, reasoning the LocationCurve (10340.0mm
    on the real beam, id 1318407) overshoots the beam's actual, mitred/
    joined solid (10325.4mm). Confirmed live to be a NO-OP: re-tested
    after that fix, the exact same 7.3mm-per-end overshoot was still
    there, bit-for-bit identical. Root cause of the NO-OP:
    `host.get_BoundingBox(None)` does NOT shrink to reflect an end join/
    miter for a framing element the way the VISIBLE solid does — a
    documented-in-this-codebase Revit quirk (see
    rebar_engine.get_isolated_solid_bbox's own docstring for the
    analogous pile-cap case: "host.get_BoundingBox(None)... reflects
    the combined extent of the WHOLE family instance", not the real
    trimmed geometry). Switched to that SAME already-proven utility
    (derives a bbox from the host's own top-level Solid.Edges — which
    DOES reflect the join, since CoverGeometryManager/get_host_solid
    read geometry via get_Geometry(), which incorporates joins) instead
    of writing a second, beam-specific fix for the identical class of
    bug; falls back to get_BoundingBox(None) only if that utility finds
    no usable solid, unchanged from ROUND 1 in that fallback case.

    Clamps `axis`'s own endpoints to that bbox's extent along the axis
    direction, projecting all 8 bbox corners onto that direction to
    find its tightest reach (works for any beam orientation, not just
    axis-aligned ones) — a NO-OP whenever the LocationCurve already
    sits inside the solid (the ordinary case), so this only ever
    shortens, never lengthens, an overshoot.

    Returns:
        DB.Line — the clamped axis, or `axis` unchanged if no bbox is
        available or clamping would degenerate to a zero-length line.
    """
    engine = _ensure_engine()
    bbox = None
    try:
        bbox = engine.get_isolated_solid_bbox(host)
    except Exception:
        bbox = None
    if bbox is None:
        try:
            bbox = host.get_BoundingBox(None)
        except Exception:
            bbox = None
    if bbox is None:
        return axis
    direction = axis.Direction
    p0 = axis.GetEndPoint(0)
    p1 = axis.GetEndPoint(1)
    corners = [DB.XYZ(x, y, z)
               for x in (bbox.Min.X, bbox.Max.X)
               for y in (bbox.Min.Y, bbox.Max.Y)
               for z in (bbox.Min.Z, bbox.Max.Z)]
    projections = [(c - p0).DotProduct(direction) for c in corners]
    lo, hi = min(projections), max(projections)
    t1 = (p1 - p0).DotProduct(direction)
    new_t0 = max(0.0, lo)
    new_t1 = min(t1, hi)
    if new_t1 - new_t0 < 1.0 / _MM_PER_FT:
        return axis
    new_p0 = p0 + direction.Multiply(new_t0)
    new_p1 = p0 + direction.Multiply(new_t1)
    return DB.Line.CreateBound(new_p0, new_p1)


def beam_spans_mm(host, axis):
    """
    [(x0, x1)] mm along `axis` (from its start) where the beam's solid exists: more than one
    span when the beam runs through an intermediate column or wall that cuts it.
    """
    import continuous_beam as cb
    length_mm = axis.Length * _MM_PER_FT
    intervals = []
    try:
        solid = _ensure_engine().get_host_solid(host, include_nested=False)
        pieces = DB.SolidUtils.SplitVolumes(solid) if solid is not None else []
        p0, d = axis.GetEndPoint(0), axis.Direction
        for piece in pieces:
            ts = []
            for edge in piece.Edges:
                c = edge.AsCurve()
                for i in (0, 1):
                    ts.append((c.GetEndPoint(i) - p0).DotProduct(d) * _MM_PER_FT)
            if ts:
                intervals.append((min(ts), max(ts)))
    except Exception:
        intervals = []
    return cb.solid_spans(intervals, length_mm) if intervals else [(0.0, length_mm)]


def cb_rules():
    import continuous_beam
    return continuous_beam


def _vibrator_gaps_to_keep(base_lines, bar_dia_mm):
    """Gaps of a top row to leave empty for the poker vibrator (SMDSC MB1): one per 300 mm of width, if 75 mm clear."""
    import continuous_beam as cb
    if len(base_lines) < 2:
        return 0
    pitch = base_lines[1].GetEndPoint(0).DistanceTo(base_lines[0].GetEndPoint(0)) * _MM_PER_FT
    if pitch - 1.1 * bar_dia_mm < cb.VIBRATOR_GAP_MM:
        return 0
    width = (len(base_lines) - 1) * pitch + bar_dia_mm + 2.0 * 45.0     # about the member width
    return min(cb.vibrator_gaps_needed(width), len(base_lines) - 1)


def _slot_points(base_lines, n_bars, dia_mm, bar_dia_mm, to_face, x_mm, axis_dir, vibrator=False):
    """
    [(kind, point at x_mm)] for n extra bars beside a row of main bars (base_lines, axis order):
    between two main bars with their outer faces level, then in a second layer behind the row.
    to_face: unit vector from the bars towards their face (up for top bars, down for bottom).
    vibrator: a top row, which keeps its central gap(s) free for the poker (SMDSC MB1).
    """
    import continuous_beam as cb
    drop = (bar_dia_mm / 2.0 + max(bar_dia_mm, 25.0) + dia_mm / 2.0) / _MM_PER_FT
    lift = (bar_dia_mm - dia_mm) / 2.0 / _MM_PER_FT

    def at(line, x):
        return line.GetEndPoint(0) + axis_dir.Multiply(x / _MM_PER_FT)
    out = []
    keep = _vibrator_gaps_to_keep(base_lines, bar_dia_mm) if vibrator else 0
    for kind, i in cb.support_bar_slots(len(base_lines), n_bars, keep):
        if kind == 'between':
            p = (at(base_lines[i], x_mm) + at(base_lines[i + 1], x_mm)).Multiply(0.5) + to_face.Multiply(lift)
        else:
            p = at(base_lines[i], x_mm) - to_face.Multiply(drop)
        out.append((kind, p))
    return out


def _spacer_groups(chains_by_key, base_lines, bar_dia_mm, to_face, axis_dir, label=u'Beam Spacer Bars'):
    """
    Spacer bars (SMDSC MB1 / Fig. 4.2) under every second layer of chains_by_key ((kind, ...) keys,
    kind 'second'): across the row from outer bar to outer bar, in the gap between the layers, at
    1 m centres. Groups as group_parallel_bar_chains_into_sets, plus 'diameter_mm'.
    """
    import continuous_beam as cb
    second = [c for key, cs in chains_by_key.items() if key[0] == 'second' for c in cs]
    if not second or len(base_lines) < 2:
        return []
    o = base_lines[0].GetEndPoint(0)
    xs = [(pt - o).DotProduct(axis_dir) * _MM_PER_FT
          for chain in second for seg in chain for crv in seg for pt in (crv.GetEndPoint(0), crv.GetEndPoint(1))]
    s = cb.spacer_dia_mm(bar_dia_mm)
    inward = to_face.Negate().Multiply((bar_dia_mm / 2.0 + s / 2.0) / _MM_PER_FT)

    def at(line, x):
        x_line = (line.GetEndPoint(0) - o).DotProduct(axis_dir) * _MM_PER_FT
        return line.GetEndPoint(0) + axis_dir.Multiply((x - x_line) / _MM_PER_FT)
    positions = cb.spacer_positions_mm(min(xs), max(xs))
    chains = [[[DB.Line.CreateBound(at(base_lines[0], x) + inward, at(base_lines[-1], x) + inward)]]
              for x in positions]
    pitch = positions[1] - positions[0] if len(positions) > 1 else 0.0
    groups = group_parallel_bar_chains_into_sets(chains, pitch, axis_dir, label)
    for g in groups:
        g['diameter_mm'] = s
    return groups


def _grouped(chains_by_key, normal, label):
    """Rebar Set groups of parallel extra bars, one per (layer, reach) key."""
    sets = []
    for key, chains in sorted(chains_by_key.items()):
        gaps = [chains[k + 1][0][0].GetEndPoint(0).DistanceTo(chains[k][0][0].GetEndPoint(0)) * _MM_PER_FT
                for k in range(len(chains) - 1)]
        even = gaps and max(gaps) - min(gaps) < 1.0
        name = label + (u' (2nd layer)' if key[0] == 'second' else u'')
        sets.extend(group_parallel_bar_chains_into_sets(chains, gaps[0] if even else 0.0, normal, name))
    return sets


def additional_bar_sets(axis, spans_mm, top_lines, bottom_lines, top_ext_mm, bottom_ext_mm,
                        continuous_ends, up, normal, bar_dia_mm, d_mm, anchorage_mm, clear_mm,
                        n_support, support_dia_mm, n_span, span_dia_mm, support_inset_mm=0.0):
    """
    Extra bars of one beam element (x mm along `axis` from its start; spans_mm = clear spans
    between support faces), SMDSC 6.3.2 simplified rules (L = clear span + d): support bars over
    every intermediate support, at least 60 % to 0.25 L and none shorter than max(0.15 L, 45 bar
    diameters), each side by its own span; at an end support with a column (not a support of a
    continuous line) the same reach, from the column's far face with a leg (top leg of the end
    U-bar), its leg support_inset_mm inside the top bars' legs (T8.49). Span bars stopping 0.15 L from an
    internal support, 0.1 L from an exterior (monolithic) one and 0.08 L from a simple support.
    Returns {'support': [...], 'span': [...]}.
    """
    import continuous_beam as cb
    out = {'support': [], 'span': [], 'spacer': []}
    direction = axis.Direction
    length = axis.Length * _MM_PER_FT

    def eff(span):
        return cb.effective_span_mm(span[1] - span[0], d_mm)
    if n_support and top_lines:
        dia = support_dia_mm or bar_dia_mm
        lbd = (anchorage_mm or 40.0 * bar_dia_mm) * dia / bar_dia_mm
        base = [_extend_line(l, -top_ext_mm[0], -top_ext_mm[1]) if any(top_ext_mm) else l for l in top_lines]
        n_long, _n_short = cb.hogging_groups(n_support)
        chains = {}

        def add(key, p, x0, x1, leg0=0.0, leg1=0.0):
            q0 = p + direction.Multiply(x0 / _MM_PER_FT)
            q1 = p + direction.Multiply(x1 / _MM_PER_FT)
            curves = [DB.Line.CreateBound(q0, q1)]
            if leg0:
                curves.insert(0, DB.Line.CreateBound(q0 - up.Multiply(leg0 / _MM_PER_FT), q0))
            if leg1:
                curves.append(DB.Line.CreateBound(q1, q1 - up.Multiply(leg1 / _MM_PER_FT)))
            chains.setdefault(key, []).append([curves])

        for (la, lb), (ra, rb) in zip(spans_mm[:-1], spans_mm[1:]):
            left, right = cb.hogging_reaches_mm(eff((la, lb)), dia), cb.hogging_reaches_mm(eff((ra, rb)), dia)
            for k, (kind, p) in enumerate(_slot_points(base, n_support, dia, bar_dia_mm, up, 0.0, direction,
                                                       vibrator=True)):
                reach = 1 if k < n_long else 0
                add((kind, reach, 'internal'), p, max(lb - left[reach], 0.0), min(ra + right[reach], length))
        for end in (0, 1):
            ext = top_ext_mm[end]
            if not ext or continuous_ends[end]:
                continue
            ext = max(ext - support_inset_mm, 0.0)
            span = spans_mm[0] if end == 0 else spans_mm[-1]
            reaches = cb.hogging_reaches_mm(eff(span), dia)
            leg = support_leg_mm(lbd, ext, dia, clear_mm)
            for k, (kind, p) in enumerate(_slot_points(base, n_support, dia, bar_dia_mm, up, 0.0, direction,
                                                       vibrator=True)):
                g = 1 if k < n_long else 0
                if end == 0:
                    add((kind, g, 'start'), p, -ext, min(span[0] + reaches[g], length), leg0=leg)
                else:
                    add((kind, g, 'end'), p, max(span[1] - reaches[g], 0.0), length + ext, leg1=leg)
        out['support'] = _grouped(chains, normal, u'Beam Support Bars')
        out['spacer'].extend(_spacer_groups(chains, base, bar_dia_mm, up, direction))
    if n_span and bottom_lines:
        dia = span_dia_mm or bar_dia_mm
        base = [_extend_line(l, -bottom_ext_mm[0], -bottom_ext_mm[1]) if any(bottom_ext_mm) else l
                for l in bottom_lines]
        chains = {}
        last = len(spans_mm) - 1

        def kind_at(end, inner):
            if inner or continuous_ends[end]:
                return 'internal'
            return 'exterior' if top_ext_mm[end] else 'simple'     # a column there: monolithic
        for k, (a, b) in enumerate(spans_mm):
            rng = cb.sagging_range_mm(a, b, kind_at(0, k > 0), kind_at(1, k < last), d_mm)
            if rng is None:
                continue
            for kind, p in _slot_points(base, n_span, dia, bar_dia_mm, up.Negate(), 0.0, direction):
                q0 = p + direction.Multiply(rng[0] / _MM_PER_FT)
                chains.setdefault((kind, k), []).append(
                    [[DB.Line.CreateBound(q0, p + direction.Multiply(rng[1] / _MM_PER_FT))]])
        out['span'] = _grouped(chains, normal, u'Beam Span Bars')
        out['spacer'].extend(_spacer_groups(chains, base, bar_dia_mm, up.Negate(), direction))
    return out


def get_beam_section_mm(doc, host, cover_mm, bar_diameter_mm=20.0):
    """
    Representative beam width / height (mm) from host solid faces.
    Used by the WPF section preview — not for placement geometry.
    """
    engine = _ensure_engine()
    axis = get_beam_axis(host)
    cover_mgr = engine.CoverGeometryManager(doc, host)
    top, bottom, side_a, side_b = _beam_faces(cover_mgr, axis.Direction)
    height_dir = top.normal.Normalize()
    width_dir = axis.Direction.CrossProduct(height_dir).Normalize()
    p_start = axis.GetEndPoint(0)
    inset_mm = cover_mm + bar_diameter_mm
    top_pt = engine.compute_cover_point(top, inset_mm)
    bottom_pt = engine.compute_cover_point(bottom, inset_mm)
    side_a_pt = engine.compute_cover_point(side_a, inset_mm)
    side_b_pt = engine.compute_cover_point(side_b, inset_mm)
    half_h = abs((top_pt - p_start).DotProduct(height_dir)
                 - (bottom_pt - p_start).DotProduct(height_dir)) / 2.0 * _MM_PER_FT
    half_w = abs((side_a_pt - p_start).DotProduct(width_dir)
                 - (side_b_pt - p_start).DotProduct(width_dir)) / 2.0 * _MM_PER_FT
    return max(half_w * 2.0 + 2.0 * inset_mm, 100.0), max(half_h * 2.0 + 2.0 * inset_mm, 150.0)


def _area(face_info):
    return getattr(face_info, 'area', 0.0) or 0.0


def lowered_top(engine, top, drop_mm):
    """The top face moved down drop_mm: the links and top bars measured from it go that much lower (T8.49)."""
    if not drop_mm:
        return top
    n = top.normal.Normalize()
    return engine.HostFaceInfo(top.face, top.normal, top.origin - n.Multiply(drop_mm / _MM_PER_FT))


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
    for f in _ensure_engine().merge_coplanar_faces(cover_mgr.faces):
        z = f.normal.Z
        if z > 0.7:
            if top is None or f.normal.Z > top.normal.Z + 1e-6 or (
                    abs(f.normal.Z - top.normal.Z) <= 1e-6 and _area(f) > _area(top)):
                top = f
            continue
        if z < -0.7:
            if bottom is None or f.normal.Z < bottom.normal.Z - 1e-6 or (
                    abs(f.normal.Z - bottom.normal.Z) <= 1e-6 and _area(f) > _area(bottom)):
                bottom = f
            continue
        if abs(f.normal.DotProduct(axis_dir)) < 0.3:
            sides.append(f)

    if top is None or bottom is None:
        raise ValueError(u'Could not find both a top and a bottom face on '
                          u'this beam — is its profile a simple rectangle?')
    if len(sides) > 2:
        # a stepped or flanged profile: the largest face on each side carries the links
        ref = sides[0].normal
        pos = [f for f in sides if f.normal.DotProduct(ref) > 0.0]
        neg = [f for f in sides if f.normal.DotProduct(ref) <= 0.0]
        if pos and neg:
            sides = [max(pos, key=_area), max(neg, key=_area)]
    if len(sides) != 2:
        raise ValueError(
            u'Expected 2 long side faces, found {} — this beam profile (not a rectangle) '
            u'is not supported yet.'.format(len(sides)))
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


def longitudinal_bar_inset_mm(cover_mm, bar_diameter_mm, stirrup_diameter_mm):
    """Face-to-centreline distance of a beam's longitudinal bars (sides, top and bottom)."""
    return cover_mm + stirrup_diameter_mm + bar_diameter_mm / 2.0 +         _ensure_engine().link_corner_extra_inset_mm(bar_diameter_mm, stirrup_diameter_mm)


def compute_longitudinal_bar_lines(axis_curve, face_info, side_a, side_b,
                                    cover_mm, n_bars, bar_diameter_mm=0.0,
                                    stirrup_diameter_mm=0.0, seed_side_normal=None):
    """
    Generate `n_bars` parallel longitudinal bar Lines along the beam's
    axis, offset inward from `face_info` (the beam's top or bottom
    face) by cover_mm + stirrup_diameter_mm (the stirrup leg sits
    BETWEEN the cover line and the main bar — see BUG FIX note below),
    and evenly distributed across the beam's width between side_a and
    side_b (each inset by cover_mm + stirrup_diameter_mm +
    bar_diameter_mm/2 from its own face) — same even-distribution
    philosophy as footing_rebar._evenly_spaced / rebar_engine's
    stock-length splitting, so bars are spread across the full usable
    width rather than packed to one side.

    BUG FIX (2026-09-01, confirmed live against a real project): this
    function's own inset never accounted for stirrup_diameter_mm at
    all (it defaulted to 0 — old callers get IDENTICAL behaviour to
    before if they still omit it). Meanwhile build_beam_rebar_curves
    computed the STIRRUP rectangle's own half-extents from
    `cover_mm + bar_diameter_mm` (the full LONGITUDINAL bar diameter,
    not the stirrup's own radius) — a LARGER inset than this function's
    `cover_mm + bar_diameter_mm/2` side inset, which put the stirrup
    FURTHER FROM the face than the main bars, i.e. INSIDE the bar cage
    instead of wrapping around it (the live symptom reported: "cercos
    por dentro de las barras"). Correct RC convention is the reverse:
    cover is measured to the OUTERMOST reinforcement (the stirrup), so
    the stirrup sits at cover + its own half-diameter, and the main
    bars sit further in, behind the stirrup's full diameter. Passing
    stirrup_diameter_mm here (now added by build_beam_rebar_curves) and
    reducing the stirrup's own inset (see that function) together fix
    the nesting order for any bar/stirrup diameter combination — not
    just the common case where the stirrup happens to be thinner.

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
        stirrup_diameter_mm (float): the stirrup leg this bar sits
                         behind, mm — 0.0 (the default) reproduces this
                         function's pre-fix behaviour exactly.
        seed_side_normal (DB.XYZ or None): the SAME propagation normal
                         that create_rebar_set will be called with for
                         these bars (see the round-4 BUG FIX note below)
                         — bars[0] is ordered onto the side FACING AWAY
                         from this vector, so that
                         ShapeDrivenAccessor.SetLayoutAsMaximumSpacing(
                         ..., bars_on_normal_side=True) — which extends
                         the OTHER (n_bars-1) copies FROM bars[0] FURTHER
                         in the +normal direction, not "fills between" a
                         start and end bar — lands the whole set back
                         inside the section instead of propagating
                         straight through one side face. None (the
                         default) falls back to this function's own
                         local `width_dir`, which is only a safe choice
                         when the caller does not also share ONE fixed
                         normal across multiple calls with DIFFERENT
                         face_info (width_dir's sign flips with
                         face_info.normal, e.g. between a top and a
                         bottom call) — build_beam_rebar_curves always
                         passes its own single, shared long_bar_normal_vec
                         here for exactly that reason.

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

    # T2.10b (measured live 2026-09-30): the bar centreline sits a full radius
    # behind the stirrup, plus the seat in the stirrup's bend at the corners;
    # the old cover + stirrup put the top row 12 mm too close to the face.
    side_inset_mm = longitudinal_bar_inset_mm(cover_mm, bar_diameter_mm, stirrup_diameter_mm)
    vertical_pt = engine.compute_cover_point(face_info, side_inset_mm)
    edge_a = engine.compute_cover_point(side_a, side_inset_mm)
    edge_b = engine.compute_cover_point(side_b, side_inset_mm)

    # BUG FIX (2026-09-02, round 4) — reported live and confirmed with a
    # live reproduction against a real beam (1318407): `_beam_faces`
    # appends side_a/side_b in whatever order `cover_mgr.faces` happens
    # to enumerate them (arbitrary, not tied to +/-width_dir), but this
    # function always walks t=0..1 from edge_a to edge_b regardless —
    # so `top_lines[0]` (fed as the FIRST/seed bar into
    # group_parallel_bar_chains_into_sets -> create_rebar_set) can land
    # on the +normal side. Revit's own
    # ShapeDrivenAccessor.SetLayoutAsMaximumSpacing(..., bars_on_normal_
    # side=True) propagates the OTHER (n_bars-1) copies STARTING FROM
    # that seed bar and extending FURTHER in the +normal direction — it
    # does not "fill between" two given bars, confirmed live via
    # revit_set_rebar_layout on a manually-created single bar: seeded at
    # the +normal-side edge (X=19407mm on a beam whose 300mm width spans
    # X=[19165,19465]), propagating array_length_mm=184mm pushed the
    # WHOLE set to X=[19391,19589] — entirely outside the section;
    # seeded at the -normal-side edge instead, the SAME propagation
    # landed exactly on X=[19219,19417], correctly spanning the section.
    # Fixed by always starting the walk from whichever of edge_a/edge_b
    # sits on the -normal side, regardless of which one _beam_faces
    # happened to call "side_a" — bars[0] (and therefore the Set's own
    # seed curve) is now guaranteed on the correct side for Revit's own
    # propagation convention. Uses `seed_side_normal` (the SAME shared
    # normal create_rebar_set will actually be called with — see this
    # function's own docstring) rather than the local `width_dir`, which
    # flips sign between a top and a bottom call and would silently fix
    # only one of the two.
    _ordering_normal = seed_side_normal if seed_side_normal is not None else width_dir
    if ((edge_a - p_start).DotProduct(_ordering_normal)
            > (edge_b - p_start).DotProduct(_ordering_normal)):
        edge_a, edge_b = edge_b, edge_a

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


def _as_curves(segment):
    """A bar segment is one Line, or a list of curves once it carries an anchorage leg."""
    return list(segment) if isinstance(segment, (list, tuple)) else [segment]


def support_extensions_mm(doc, axis, end_inset_mm, foundations=False):
    """
    (start, end) mm a beam bar runs on past each end of `axis` to reach the far face of the
    structural column it frames into, less end_inset_mm; 0 where no column is found.
    foundations: a ground beam, whose supports are also the pile caps and pads it runs into; its
    main bars then continue right across them (IStructE SMDSC 6.7).
    """
    from nosa_utils.revit_helpers import is_ground_beam
    categories = [DB.BuiltInCategory.OST_StructuralColumns]
    if foundations:
        categories.append(DB.BuiltInCategory.OST_StructuralFoundation)
    exts = []
    direction = axis.Direction
    for point, outward in ((axis.GetEndPoint(0), direction.Negate()), (axis.GetEndPoint(1), direction)):
        probe = point + outward.Multiply(20.0 / _MM_PER_FT)
        reach = DB.XYZ(30.0 / _MM_PER_FT, 30.0 / _MM_PER_FT, 300.0 / _MM_PER_FT)
        ext = 0.0
        try:
            columns = [e for cat in categories for e in DB.FilteredElementCollector(doc).OfCategory(cat)
                       .WhereElementIsNotElementType().WherePasses(
                           DB.BoundingBoxIntersectsFilter(DB.Outline(probe - reach, probe + reach)))
                       if not is_ground_beam(e)]
            for column in columns:
                bbox = column.get_BoundingBox(None)
                corners = [DB.XYZ(x, y, z) for x in (bbox.Min.X, bbox.Max.X)
                           for y in (bbox.Min.Y, bbox.Max.Y) for z in (bbox.Min.Z, bbox.Max.Z)]
                far_mm = max((c - point).DotProduct(outward) for c in corners) * _MM_PER_FT
                ext = max(ext, far_mm - end_inset_mm)
        except Exception:
            ext = 0.0
        exts.append(ext if ext > 1.0 else 0.0)
    return exts[0], exts[1]


def _extend_line(line, ext0_mm, ext1_mm):
    d = line.Direction
    return DB.Line.CreateBound(line.GetEndPoint(0) - d.Multiply(ext0_mm / _MM_PER_FT),
                               line.GetEndPoint(1) + d.Multiply(ext1_mm / _MM_PER_FT))


def support_leg_mm(anchorage_mm, straight_in_support_mm, bar_diameter_mm, clear_mm):
    """90 degree leg: the anchorage the straight length in the column does not give, >= 12 phi."""
    leg = max(anchorage_mm - straight_in_support_mm, 12.0 * bar_diameter_mm)
    if clear_mm > 0:
        leg = min(leg, clear_mm - bar_diameter_mm)
    return 5.0 * math.ceil(leg / 5.0 - 1e-9) if leg > 0 else 0.0


def _add_support_legs(chains, ext0_mm, ext1_mm, leg_dir, anchorage_mm, bar_diameter_mm, clear_mm):
    """Leg on the first segment's start / last segment's end where the bar runs into a column."""
    out = []
    for chain in chains:
        chain = list(chain)
        if ext0_mm:
            first = chain[0]
            leg = support_leg_mm(anchorage_mm, ext0_mm, bar_diameter_mm, clear_mm) / _MM_PER_FT
            p = first.GetEndPoint(0)
            chain[0] = [DB.Line.CreateBound(p + leg_dir.Multiply(leg), p)] + _as_curves(first)
        if ext1_mm:
            last = _as_curves(chain[-1])
            leg = support_leg_mm(anchorage_mm, ext1_mm, bar_diameter_mm, clear_mm) / _MM_PER_FT
            p = last[-1].GetEndPoint(1)
            chain[-1] = last + [DB.Line.CreateBound(p, p + leg_dir.Multiply(leg))]
        out.append(chain)
    return out


def side_bar_rows_mm(clear_mm, pitch_mm=250.0):
    """(rows, pitch) of side bars between a bottom and a top bar clear_mm apart, at <= pitch_mm."""
    if clear_mm <= pitch_mm + 1e-6:
        return 0, 0.0
    gaps = int(math.ceil(clear_mm / pitch_mm - 1e-9))
    return gaps - 1, clear_mm / gaps


def build_side_bar_sets(axis, section_origin, width_dir, height_dir, half_width_mm, half_height_mm,
                        link_dia_mm, bar_dia_mm, stirrup_sets, beam_height_mm, side_bar_dia_mm=None):
    """
    IStructE SMDSC 6.3 / EC2 7.3.3: a beam 1000 mm deep or more takes H16 side bars inside the links
    at <= 250 mm up each side face, between the bottom and top bars, along the length the links
    cover. side_bar_dia_mm: None = automatic (16 from 1000 mm), 0 = none. One Set per face, propagated
    up from the lowest row. Returns groups for the tab's _create_long_group.
    """
    from nosa_utils import links
    if side_bar_dia_mm is None:
        side_bar_dia_mm = links.SIDE_BAR_DIA_MM if beam_height_mm >= links.SIDE_BARS_DEPTH_MM - 1e-6 else 0.0
    positions = [p for s in stirrup_sets for p in (s.get('positions') or [])]
    if not side_bar_dia_mm or not positions:
        return []
    bar_offset = link_dia_mm / 2.0 + bar_dia_mm / 2.0          # main bars inside the link centreline
    bottom = -half_height_mm + bar_offset
    top = half_height_mm - bar_offset
    rows, pitch = side_bar_rows_mm(top - bottom, links.SIDE_BAR_PITCH_MM)
    if rows < 1:
        return []
    across = half_width_mm - link_dia_mm / 2.0 - side_bar_dia_mm / 2.0
    x0, x1 = min(positions), max(positions)
    direction = axis.Direction.Normalize()
    groups = []
    for sign in (1.0, -1.0):
        rows_curves = []
        for k in range(rows):
            z = bottom + pitch * (k + 1)
            base = (section_origin + width_dir.Multiply(sign * across / _MM_PER_FT)
                    + height_dir.Multiply(z / _MM_PER_FT))
            rows_curves.append([DB.Line.CreateBound(base + direction.Multiply(x0 / _MM_PER_FT),
                                                    base + direction.Multiply(x1 / _MM_PER_FT))])
        groups.append({'curves': rows_curves[0], 'count': rows, 'spacing_mm': pitch + 0.01,
                       'array_length_mm': pitch * (rows - 1), 'normal': height_dir.Normalize(),
                       'label': u'Beam Side Bars', 'all_curves': rows_curves, 'diameter_mm': side_bar_dia_mm})
    return groups


def group_parallel_bar_chains_into_sets(chains, spacing_mm, normal, label):
    """
    Group N parallel, IDENTICALLY-SHAPED longitudinal bar chains (one
    per compute_longitudinal_bar_lines position, each optionally
    lap-split by split_long_bars) into Rebar-Set-ready groups instead
    of N individual elements — same optimisation stirrups already had,
    now extended to top/bottom longitudinal bars.

    Every chain here is a plain parallel translate of every other one
    across the beam's width (split_long_bars runs the SAME
    stock_length_mm/lap_length_mm/lap_offset_mm through
    rebar_engine.split_rebar_by_stock_length for each line
    independently, on lines of identical length — so all chains come
    out with the same segment count and the same relative split
    positions; only their fixed spacing_mm apart differs). This lets
    ONE representative chain, propagated `count` times, stand in for
    the whole set — exactly how build_beam_rebar_curves already groups
    stirrup zones and wall_rebar.py groups its mesh sets.

    Args:
        chains      (list[list[DB.Curve]]): one chain per parallel bar
                    position, from compute_longitudinal_bar_lines (each
                    a 1-curve chain) or split_long_bars (each possibly
                    multi-segment) — all the SAME length.
        spacing_mm  (float): centre-to-centre spacing between adjacent
                    positions, mm (0.0 or chains with < 2 entries mean
                    no propagation — each bar stays individual).
        normal      (DB.XYZ): the plane normal for these bars (this
                    module's width_dir convention).
        label       (unicode): base label for created elements.

    Returns:
        list[dict]: one entry per SEGMENT INDEX, each
        {'curves', 'count', 'spacing_mm', 'array_length_mm', 'normal',
         'label', 'all_curves'} — 'all_curves' lists every parallel
        bar's own curve at that segment index, for a caller's fallback
        path if Rebar Set creation itself fails (mirrors stirrup_sets'
        own 'all_curves' key). Falls back to one entry per (bar,
        segment) — count=1, i.e. genuinely individual elements, never
        silently dropping a bar — if the chains aren't uniformly
        shaped (should not happen given split_long_bars' own
        determinism, but this function never assumes it blindly) or
        there's nothing to group (< 2 bars, or spacing_mm <= 0).
    """
    if not chains:
        return []
    n_bars = len(chains)
    n_segments = len(chains[0])
    uniform = n_segments > 0 and all(len(c) == n_segments for c in chains)

    if n_bars < 2 or spacing_mm <= 0 or not uniform:
        groups = []
        for chain in chains:
            for seg in chain:
                groups.append({
                    'curves': _as_curves(seg), 'all_curves': [_as_curves(seg)], 'count': 1,
                    'spacing_mm': 0.0, 'array_length_mm': 0.0,
                    'normal': normal, 'label': label,
                })
        return groups

    array_length_mm = (n_bars - 1) * spacing_mm
    groups = []
    for seg_idx in range(n_segments):
        seg_label = (u'{} (segment {})'.format(label, seg_idx + 1)
                     if n_segments > 1 else label)
        groups.append({
            'curves': _as_curves(chains[0][seg_idx]),
            'all_curves': [_as_curves(chain[seg_idx]) for chain in chains],
            'count': n_bars,
            'spacing_mm': spacing_mm,
            'array_length_mm': array_length_mm,
            'normal': normal,
            'label': seg_label,
        })
    return groups


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
    from nosa_utils import links
    length_mm = axis_curve.Length * _MM_PER_FT
    lo = start_offset_mm
    hi = length_mm - end_offset_mm
    return links.exact_pitch_positions(lo, hi, spacing_mm)     # round pitches on the drawing


def generate_stirrup_positions_densified(axis_curve, spacing_mm, dense_spacing_mm,
                                          confine_length_mm,
                                          start_offset_mm=50.0, end_offset_mm=50.0):
    """
    Stirrup positions with denser spacing in end confinement zones
    (support regions) and normal spacing in the middle span.

    Returns:
        list[dict]: each {'zone': 'start'|'middle'|'end',
                          'spacing_mm': float,
                          'positions': list[float]}
        Empty list if the beam is too short.
    """
    length_mm = axis_curve.Length * _MM_PER_FT
    lo = start_offset_mm
    hi = length_mm - end_offset_mm
    if hi <= lo:
        return []

    dense = dense_spacing_mm if dense_spacing_mm and dense_spacing_mm > 0 else spacing_mm
    if dense > spacing_mm:
        dense = spacing_mm  # denser = smaller spacing
    confine = max(confine_length_mm or 0.0, 0.0)

    usable = hi - lo
    # Cap each end zone so middle still has room when beam is short
    max_each = usable * 0.4
    confine_each = min(confine, max_each) if confine > 0 else 0.0

    # Round pitches (user 2026-10-10): the end zones at exactly the dense pitch from the support faces, the
    # middle at exactly the span pitch; the remainder under one pitch goes to the two joints between zones.
    from nosa_utils import links
    groups = []
    n_end = int(math.floor(confine_each / dense + 1e-9)) if confine_each > dense * 0.5 else 0
    if n_end >= 1 and hi - lo > 2.0 * n_end * dense + dense:
        start = [lo + k * dense for k in range(n_end + 1)]
        end = [hi - (n_end - k) * dense for k in range(n_end + 1)]
        groups.append({'zone': u'start', 'spacing_mm': dense, 'positions': start})
        middle = links.interior_exact_positions(start[-1], end[0], spacing_mm)
        if middle:
            # start[-1] / end[0] already carry the end zones' last / first stirrup (T2.20)
            groups.append({'zone': u'middle', 'spacing_mm': spacing_mm, 'positions': middle})
        groups.append({'zone': u'end', 'spacing_mm': dense, 'positions': end})
    else:
        groups.append({
            'zone': u'middle',
            'spacing_mm': spacing_mm,
            'positions': links.exact_pitch_positions(lo, hi, spacing_mm),
        })

    # Drop empty groups
    return [g for g in groups if g['positions']]


def build_stirrup_rectangle(axis_curve, dist_mm, width_dir, height_dir,
                             half_width_mm, half_height_mm,
                             section_origin=None):
    """
    A closed 4-segment rectangular stirrup curve chain at dist_mm along
    the beam axis, in the plane perpendicular to the axis.

    section_origin: point on the start section that is the TRUE geometric
    centre of the (cover-inset) stirrup — NOT the LocationCurve start,
    which on most Revit beams sits on the top face. If None, falls back
    to the LocationCurve start (legacy / incorrect for top-centred axes).
    """
    p_start = section_origin if section_origin is not None else axis_curve.GetEndPoint(0)
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
                             lap_offset_mm=25.0,
                             densify_ends=False, dense_spacing_mm=None,
                             confine_length_mm=None, anchorage_mm=None,
                             include_interior_ties=False, tie_layout='all',
                             link_bend_diameter_mm=None, continuous_ends=(False, False),
                             internal_bottom_ext_mm=(0.0, 0.0), bottom_stop_mm=(None, None),
                             bottom_stop_leg=(False, False), include_top=True,
                             n_support_bars=0, support_bar_diameter_mm=None,
                             n_span_bars=0, span_bar_diameter_mm=None, side_bar_diameter_mm=None,
                             top_drop_mm=0.0):
    """
    High-level pipeline for one beam host:
      1. Read the beam's straight centreline (get_beam_axis).
      2. Build a CoverGeometryManager and classify top/bottom/side_a/
         side_b faces (_beam_faces).
      3. Build top and bottom longitudinal bar Lines
         (compute_longitudinal_bar_lines), splitting any that exceed
         stock_length_mm via rebar_engine.split_rebar_by_stock_length
         (split_long_bars).
      4. Build stirrup rectangles — uniform spacing, or densified at
         end confinement zones when densify_ends is True.

    Returns:
        {
          'top_bars':    list[list[DB.Curve]],  # flat list (compat)
          'bottom_bars': list[list[DB.Curve]],  # flat list (compat)
          'top_bar_sets': list[dict],    # grouped for Set creation —
          'bottom_bar_sets': list[dict], # see group_parallel_bar_
                                          # chains_into_sets
          'stirrups':    list[list[DB.Curve]],  # flat list (compat)
          'stirrup_sets': list[dict],  # grouped by zone for Set creation
          'beam_height_mm': float,
          'confine_length_mm': float,
          'spans_mm': [(x0, x1)],        # more than one when the beam runs over
                                          # intermediate columns (beam_spans_mm)
          'support_bar_sets': list[dict], # extra top bars over those supports
        }
    A beam over intermediate supports gets its links span by span (none inside the column),
    its top-bar laps in the central third of a span and, with n_support_bars, the support bars
    of a continuous line (continuous_beam's rules).
    """
    from nosa_utils import standards
    stock_length_mm = standards.bar_stock_length_mm(bar_diameter_mm, stock_length_mm)   # SMDSC 4.2.4
    engine = _ensure_engine()
    axis = get_beam_axis(host)
    # BUG FIX (2026-09-01) — see _clamp_axis_to_bbox's own docstring:
    # the raw LocationCurve can run past the beam's actual (mitred)
    # solid at each end; every downstream use of `axis` (longitudinal
    # bars AND stirrup zones) needs the clamped version, so this
    # happens once, immediately, before anything else derives from it.
    axis = _clamp_axis_to_bbox(axis, host)
    warnings = []
    cover_mgr = engine.CoverGeometryManager(doc, host)
    top, bottom, side_a, side_b = _beam_faces(cover_mgr, axis.Direction)
    top = lowered_top(engine, top, top_drop_mm)       # T8.49: under a slab's top mat / a main beam's top bars
    spans_mm = beam_spans_mm(host, axis)

    # Computed here (not after, as before the round-4 fix) so BOTH the
    # top and the bottom compute_longitudinal_bar_lines calls below can
    # share this ONE fixed normal as their seed_side_normal — see that
    # function's own docstring/BUG FIX note for why using each call's
    # own local width_dir (which flips sign between a top and a bottom
    # face_info) would only fix one of the two.
    long_bar_normal_vec = axis.Direction.CrossProduct(top.normal.Normalize()).Normalize()

    top_lines = compute_longitudinal_bar_lines(
        axis, top, side_a, side_b, cover_mm, n_top_bars, bar_diameter_mm,
        stirrup_diameter_mm=stirrup_bar_diameter_mm,
        seed_side_normal=long_bar_normal_vec)
    bottom_lines = compute_longitudinal_bar_lines(
        axis, bottom, side_a, side_b, cover_mm, n_bottom_bars, bar_diameter_mm,
        stirrup_diameter_mm=stirrup_bar_diameter_mm,
        seed_side_normal=long_bar_normal_vec)

    # Anchorage into the supporting columns (user decision 2026-10-01): through the
    # column to its far face, then a 90 degree leg back into the beam.
    end_inset_mm = cover_mm + stirrup_bar_diameter_mm
    from nosa_utils.revit_helpers import is_ground_beam
    ext0_mm, ext1_mm = support_extensions_mm(doc, axis, end_inset_mm, foundations=is_ground_beam(host))
    # T7.2 — a span of a continuous beam: at an intermediate support the bottom bars only run
    # straight into it (no leg) and the top bars are the line's own continuous hanger bars.
    b_ext0 = internal_bottom_ext_mm[0] if continuous_ends[0] else ext0_mm
    b_ext1 = internal_bottom_ext_mm[1] if continuous_ends[1] else ext1_mm
    # SMDSC MB1 flexible detailing: at an end column the bottom bars stop short, lapping the end U-bars
    b_leg0, b_leg1 = (0.0 if continuous_ends[0] else ext0_mm), (0.0 if continuous_ends[1] else ext1_mm)
    # a half joint (SMDSC 6.9): the bottom bars stop at the notch and turn up behind the hanger links
    # T8.49, SMDSC MB1: the legs in one column nest, the top bars outermost, the support bars inside them, the
    # bottom bars inside both (they coincided, found by the rebar QA)
    from nosa_utils import joints
    insets = joints.nested_leg_insets_mm(bar_diameter_mm, bar_diameter_mm,
                                         (support_bar_diameter_mm or bar_diameter_mm) if n_support_bars else None)
    for end, ext in ((0, ext0_mm), (1, ext1_mm)):
        if ext and not continuous_ends[end] and bottom_stop_mm[end] is None:
            nested = max(ext - insets['bottom'], 0.0)
            if end == 0:
                b_ext0 = b_leg0 = nested
            else:
                b_ext1 = b_leg1 = nested
    if bottom_stop_mm[0] is not None:
        b_ext0, b_leg0 = bottom_stop_mm[0], (1.0 if bottom_stop_leg[0] else 0.0)
    if bottom_stop_mm[1] is not None:
        b_ext1, b_leg1 = bottom_stop_mm[1], (1.0 if bottom_stop_leg[1] else 0.0)
    if ext0_mm or ext1_mm:
        top_lines = [_extend_line(l, ext0_mm, ext1_mm) for l in top_lines]
    if b_ext0 or b_ext1:
        bottom_lines = [_extend_line(l, b_ext0, b_ext1) for l in bottom_lines]
    height_dir_legs = top.normal.Normalize()
    if top_lines and bottom_lines:
        clear_mm = abs((top_lines[0].GetEndPoint(0) - bottom_lines[0].GetEndPoint(0))
                       .DotProduct(height_dir_legs)) * _MM_PER_FT
    else:
        clear_mm = 0.0

    needs_split = any(l.Length * _MM_PER_FT > stock_length_mm
                       for l in (top_lines + bottom_lines))
    if needs_split and lap_length_mm is None:
        raise ValueError(
            u'At least one longitudinal bar exceeds stock_length_mm '
            u'({} mm) but lap_length_mm was not supplied — required to '
            u'split it.'.format(stock_length_mm))

    if lap_length_mm is not None and len(spans_mm) > 1 and any(
            l.Length * _MM_PER_FT > stock_length_mm for l in top_lines):
        # laps of the top bars where hogging is nil: central third of a span
        import continuous_beam as cb
        top_chains = []
        x_start, x_end = -ext0_mm, axis.Length * _MM_PER_FT + ext1_mm
        segments, lap_notes = cb.lap_cuts(x_start, x_end, [{'x0': a, 'x1': b} for a, b in spans_mm],
                                          stock_length_mm, lap_length_mm)
        warnings.extend(lap_notes)
        down = height_dir_legs.Negate().Multiply(bar_diameter_mm / _MM_PER_FT)
        for line in top_lines:
            p0 = line.GetEndPoint(0) + axis.Direction.Multiply(ext0_mm / _MM_PER_FT)
            chain = []
            for j, (a, b) in enumerate(segments):
                pa, pb = p0 + axis.Direction.Multiply(a / _MM_PER_FT), p0 + axis.Direction.Multiply(b / _MM_PER_FT)
                if j % 2:
                    pa, pb = pa + down, pb + down
                chain.append(DB.Line.CreateBound(pa, pb))
            top_chains.append(chain)
        bottom_chains = split_long_bars(bottom_lines, stock_length_mm, lap_length_mm, lap_offset_mm)
    elif lap_length_mm is not None:
        top_chains = split_long_bars(top_lines, stock_length_mm, lap_length_mm, lap_offset_mm)
        bottom_chains = split_long_bars(bottom_lines, stock_length_mm, lap_length_mm, lap_offset_mm)
    else:
        top_chains = [[l] for l in top_lines]
        bottom_chains = [[l] for l in bottom_lines]

    anchor_mm = anchorage_mm if anchorage_mm else 40.0 * bar_diameter_mm
    if (ext0_mm or ext1_mm) and clear_mm and clear_mm - bar_diameter_mm < 12.0 * bar_diameter_mm:
        warnings.append(u'Anchorage legs into the columns are only {:.0f} mm (under 12 bar '
                        u'diameters): the beam section is just {:.0f} mm between its top and '
                        u'bottom bars. If a floor is cutting the beam, switch the join order '
                        u'(Modify > Join > Switch Join Order) and regenerate.'.format(
                            max(clear_mm - bar_diameter_mm, 0.0), clear_mm))
    top_chains = _add_support_legs(top_chains, ext0_mm, ext1_mm, height_dir_legs.Negate(),
                                   anchor_mm, bar_diameter_mm, clear_mm)
    # the inner (bottom) legs rise only to under the top bars' bends they stand inside (T8.49)
    bottom_clear = clear_mm
    if clear_mm and insets['bottom'] and (ext0_mm or ext1_mm):
        room = joints.nested_leg_room_mm(clear_mm, insets['bottom'], bar_diameter_mm, bar_diameter_mm)
        bottom_clear = room + bar_diameter_mm          # support_leg_mm takes the bar size off again
    bottom_chains = _add_support_legs(bottom_chains, b_leg0, b_leg1, height_dir_legs,
                                      anchor_mm, bar_diameter_mm, bottom_clear)
    if not include_top:
        top_chains = []

    # Optimisation: n parallel, identically-shaped longitudinal bars
    # (top_lines/bottom_lines are plain parallel translates of each
    # other across the width) become ONE Rebar Set instead of n
    # individual elements wherever possible — see
    # group_parallel_bar_chains_into_sets' own docstring. Spacing is
    # read straight off the real bar geometry (works whether n_bars
    # ended up evenly or unevenly distributed). long_bar_normal_vec was
    # already computed above (shared with the seed_side_normal passed
    # into compute_longitudinal_bar_lines).
    top_spacing_mm = (top_lines[1].GetEndPoint(0).DistanceTo(top_lines[0].GetEndPoint(0))
                       * _MM_PER_FT) if len(top_lines) > 1 else 0.0
    bottom_spacing_mm = (bottom_lines[1].GetEndPoint(0).DistanceTo(bottom_lines[0].GetEndPoint(0))
                          * _MM_PER_FT) if len(bottom_lines) > 1 else 0.0
    top_bar_sets = group_parallel_bar_chains_into_sets(
        top_chains, top_spacing_mm, long_bar_normal_vec, u'Beam Top Bars') if top_chains else []
    bottom_bar_sets = group_parallel_bar_chains_into_sets(
        bottom_chains, bottom_spacing_mm, long_bar_normal_vec, u'Beam Bottom Bars')

    # BUG FIX (2026-09-01, confirmed live): the stirrup rectangle used
    # to be inset by cover + FULL longitudinal bar diameter — LARGER
    # than the main bars' own inset (cover + bar_dia/2, now cover +
    # stirrup_dia + bar_dia/2 — see compute_longitudinal_bar_lines'
    # own fix above), which put the stirrup INSIDE the bar cage instead
    # of wrapping around it ("cercos por dentro de las barras"). Cover
    # is measured to the OUTERMOST reinforcement — the stirrup itself —
    # so its own rectangle sits at cover + ITS OWN half-diameter, always
    # closer to the face than the main bars behind it, for any bar/
    # stirrup diameter combination (not just the common case where the
    # stirrup happens to be thinner than the main bars).
    height_dir = top.normal.Normalize()
    width_dir = axis.Direction.CrossProduct(height_dir).Normalize()
    p_start = axis.GetEndPoint(0)

    inset_mm = cover_mm + stirrup_bar_diameter_mm / 2.0
    top_pt = engine.compute_cover_point(top, inset_mm)
    bottom_pt = engine.compute_cover_point(bottom, inset_mm)
    side_a_pt = engine.compute_cover_point(side_a, inset_mm)
    side_b_pt = engine.compute_cover_point(side_b, inset_mm)

    h_top_ft = (top_pt - p_start).DotProduct(height_dir)
    h_bot_ft = (bottom_pt - p_start).DotProduct(height_dir)
    half_height_mm = abs(h_top_ft - h_bot_ft) / 2.0 * _MM_PER_FT
    half_width_mm = abs((side_a_pt - p_start).DotProduct(width_dir)
                         - (side_b_pt - p_start).DotProduct(width_dir)) / 2.0 * _MM_PER_FT

    # LocationCurve is often on the TOP of the beam — offset to the
    # geometric mid-height of the cover-inset stirrup section.
    mid_h_ft = (h_top_ft + h_bot_ft) / 2.0
    section_origin = p_start + height_dir.Multiply(mid_h_ft)

    beam_height_mm = half_height_mm * 2.0 + 2.0 * inset_mm
    # Default confine length = 2 * effective depth (approx beam height)
    if confine_length_mm is None or confine_length_mm <= 0:
        confine_length_mm = 2.0 * beam_height_mm

    zone_groups = []
    for k, (a, b) in enumerate(spans_mm):
        # one span at a time: no links inside an intermediate column
        span_axis = axis if len(spans_mm) == 1 else DB.Line.CreateBound(
            p_start + axis.Direction.Multiply(a / _MM_PER_FT), p_start + axis.Direction.Multiply(b / _MM_PER_FT))
        if densify_ends:
            dens = dense_spacing_mm if dense_spacing_mm else max(stirrup_spacing_mm * 0.5, 75.0)
            groups = generate_stirrup_positions_densified(
                span_axis, stirrup_spacing_mm, dens, confine_length_mm,
                stirrup_start_offset_mm, stirrup_end_offset_mm)
        else:
            positions = generate_stirrup_positions(
                span_axis, stirrup_spacing_mm, stirrup_start_offset_mm, stirrup_end_offset_mm)
            groups = [{
                'zone': u'middle',
                'spacing_mm': stirrup_spacing_mm,
                'positions': positions,
            }] if positions else []
        for g in groups:
            g['positions'] = [a + x for x in g['positions']]
            if len(spans_mm) > 1:
                g['zone'] = u'span {} {}'.format(k + 1, g['zone'])
        zone_groups.extend(groups)

    stirrups = []
    stirrup_sets = []
    for zg in zone_groups:
        zone_curves = [
            build_stirrup_rectangle(axis, d, width_dir, height_dir,
                                    half_width_mm, half_height_mm,
                                    section_origin=section_origin)
            for d in zg['positions']
        ]
        stirrups.extend(zone_curves)
        if not zone_curves:
            continue
        n = len(zone_curves)
        # The Set spans the zone's real positions, at its real (evenly
        # distributed) step: the nominal spacing overshot into the next zone.
        positions = zg['positions']
        array_mm = positions[-1] - positions[0] if n > 1 else 0.0
        spacing = (array_mm / (n - 1) + 0.01) if n > 1 else zg['spacing_mm']
        stirrup_sets.append({
            'zone': zg['zone'],
            'curves': zone_curves[0],
            'all_curves': zone_curves,
            'spacing_mm': spacing,
            'array_length_mm': array_mm,
            'count': n,
            'normal': axis.Direction.Normalize(),
            'positions': positions,
        })

    # Additional bars (user decision 2026-10-05): hogging bars over the supports, sagging bars in
    # the spans — EC2 + UK NA, Concrete Centre / IStructE simplified curtailment (continuous_beam).
    d_mm = beam_height_mm - longitudinal_bar_inset_mm(cover_mm, bar_diameter_mm, stirrup_bar_diameter_mm)
    extra = additional_bar_sets(
        axis, spans_mm, top_lines, bottom_lines, (ext0_mm, ext1_mm), (b_ext0, b_ext1),
        continuous_ends, height_dir_legs, long_bar_normal_vec, bar_diameter_mm, d_mm, anchor_mm,
        clear_mm, n_support_bars, support_bar_diameter_mm, n_span_bars, span_bar_diameter_mm,
        support_inset_mm=insets['support'])
    support_bar_sets, span_bar_sets = extra['support'], extra['span']
    if (n_support_bars or n_span_bars) and not any(continuous_ends):
        warnings.extend(cb_rules().simplified_rules_warnings([b - a for a, b in spans_mm]))

    bar_inset = longitudinal_bar_inset_mm(cover_mm, bar_diameter_mm, stirrup_bar_diameter_mm)
    interior_tie_sets = []
    if include_interior_ties:
        interior_tie_sets = build_interior_tie_sets(
            stirrup_sets, section_origin, axis.Direction.Normalize(), width_dir, height_dir,
            half_width_mm + inset_mm - bar_inset, half_height_mm + inset_mm - bar_inset,
            n_top_bars, n_bottom_bars, bar_diameter_mm, stirrup_bar_diameter_mm,
            link_bend_diameter_mm, tie_layout)
        if n_top_bars and n_bottom_bars and n_top_bars != n_bottom_bars and interior_tie_sets:
            warnings.append(u'interior links/crossties follow the row with more bars ({} vs {}); '
                            u'the other row is not held at every leg.'.format(
                                max(n_top_bars, n_bottom_bars), min(n_top_bars, n_bottom_bars)))

    side_bar_sets = build_side_bar_sets(
        axis, section_origin, width_dir, height_dir, half_width_mm, half_height_mm,
        stirrup_bar_diameter_mm, bar_diameter_mm, stirrup_sets, beam_height_mm, side_bar_diameter_mm)

    return {
        'side_bar_sets': side_bar_sets,
        'top_bars': top_chains,
        'bottom_bars': bottom_chains,
        'top_bar_sets': top_bar_sets,
        'bottom_bar_sets': bottom_bar_sets,
        'stirrups': stirrups,
        'stirrup_sets': stirrup_sets,
        'beam_height_mm': beam_height_mm,
        'beam_width_mm': half_width_mm * 2.0 + 2.0 * inset_mm,
        'confine_length_mm': confine_length_mm if densify_ends else 0.0,
        'long_bar_normal': width_dir,
        'bar_inset_mm': bar_inset,
        'top_drop_mm': top_drop_mm,
        'interior_tie_sets': interior_tie_sets,
        'spans_mm': spans_mm,
        'support_bar_sets': support_bar_sets,
        'span_bar_sets': span_bar_sets,
        'spacer_sets': extra.get('spacer', []),
        'warnings': warnings,
    }


# ══════════════════════════════════════════════════════════════════════════
# Continuous beams (T7.2)
# ══════════════════════════════════════════════════════════════════════════

def _oriented_axis(host, direction):
    """The clamped beam axis, running along `direction`."""
    axis = _clamp_axis_to_bbox(get_beam_axis(host), host)
    if axis.Direction.DotProduct(direction) < 0:
        axis = DB.Line.CreateBound(axis.GetEndPoint(1), axis.GetEndPoint(0))
    return axis


def group_beam_lines(hosts, max_gap_mm=1500.0, tol_mm=10.0):
    """
    Split selected beams into lines of spans: parallel, on one straight line (within tol_mm)
    and end to end across a gap no wider than max_gap_mm. Returns [[host, ...], ...] — a line of
    one beam is a plain single-span beam.
    """
    axes = {}
    for host in hosts:
        try:
            axes[host.Id] = _clamp_axis_to_bbox(get_beam_axis(host), host)
        except Exception:
            axes[host.Id] = None
    tol = tol_mm / _MM_PER_FT
    parent = dict((h.Id, h.Id) for h in hosts)

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for a in hosts:
        for b in hosts:
            if a.Id == b.Id or axes[a.Id] is None or axes[b.Id] is None:
                continue
            la, lb = axes[a.Id], axes[b.Id]
            d = la.Direction
            if abs(d.DotProduct(lb.Direction)) < 0.9995:
                continue
            off = lb.GetEndPoint(0) - la.GetEndPoint(0)
            if (off - d.Multiply(off.DotProduct(d))).GetLength() > tol:
                continue
            ta = sorted([0.0, la.Length])
            tb = sorted([(lb.GetEndPoint(i) - la.GetEndPoint(0)).DotProduct(d) for i in (0, 1)])
            gap = max(tb[0] - ta[1], ta[0] - tb[1]) * _MM_PER_FT
            if gap <= max_gap_mm:
                parent[find(a.Id)] = find(b.Id)
    lines = {}
    for host in hosts:
        lines.setdefault(find(host.Id), []).append(host)
    return list(lines.values())


def get_beam_arc(host):
    """The beam's centreline when it is an arc on plan (T8.58), else None."""
    curve = getattr(getattr(host, 'Location', None), 'Curve', None)
    if isinstance(curve, DB.Arc) and abs(curve.Normal.Normalize().Z) > 0.999:
        return curve
    return None


def _column_reach_mm(doc, point, outward, end_inset_mm):
    """mm a bar runs on from point along outward to the far face of the column there, less end_inset_mm; 0 if none."""
    probe = point + outward.Multiply(20.0 / _MM_PER_FT)
    reach = DB.XYZ(30.0 / _MM_PER_FT, 30.0 / _MM_PER_FT, 300.0 / _MM_PER_FT)
    ext = 0.0
    try:
        for column in DB.FilteredElementCollector(doc).OfCategory(DB.BuiltInCategory.OST_StructuralColumns) \
                .WhereElementIsNotElementType().WherePasses(
                    DB.BoundingBoxIntersectsFilter(DB.Outline(probe - reach, probe + reach))):
            bbox = column.get_BoundingBox(None)
            corners = [DB.XYZ(x, y, point.Z) for x in (bbox.Min.X, bbox.Max.X) for y in (bbox.Min.Y, bbox.Max.Y)]
            ext = max(ext, max((c - point).DotProduct(outward) for c in corners) * _MM_PER_FT - end_inset_mm)
    except Exception:
        ext = 0.0
    return ext if ext > 1.0 else 0.0


def build_curved_beam_curves(doc, host, cover_mm, bar_diameter_mm, n_top_bars, n_bottom_bars,
                             stirrup_spacing_mm, stirrup_bar_diameter_mm, end_offset_mm=50.0,
                             stock_length_mm=12000.0, lap_length_mm=None, anchorage_mm=None):
    """
    T8.58 — a beam curved on plan: top and bottom bars are arcs round the centre (into the columns at the
    ends, top bars with a leg down there), links are closed rectangles on radial planes with the pitch kept
    at the outer leg. Returns {'top': [[chains]], 'bottom': [[chains]], 'links': [(curves, normal)],
    'pitch_mm', 'warnings'}: top/bottom are one group of bar chains per stock-length piece.
    """
    from nosa_utils import curved_beams as cb
    from nosa_utils.bootstrap import load_module
    cw = load_module('curved_wall', os.path.join(_HERE, 'curved_wall.py'))
    engine = _ensure_engine()
    arc = get_beam_arc(host)
    if arc is None:
        raise ValueError(u'Beam centreline is not an arc on plan.')
    c = arc.Center
    center = (c.X * _MM_PER_FT, c.Y * _MM_PER_FT)
    p0 = arc.GetEndPoint(0)
    a_start = math.atan2(p0.Y - c.Y, p0.X - c.X)
    sweep = arc.Length / arc.Radius * (1.0 if arc.Normal.Z > 0 else -1.0)
    sign = 1.0 if sweep >= 0 else -1.0

    solid = engine.get_host_solid(host)
    if solid is None:
        raise ValueError(u'No solid geometry for the curved beam.')
    points = [p for edge in solid.Edges for p in edge.Tessellate()]
    t_min, t_max, r_min, r_max = cb.angle_range(
        [(p.X * _MM_PER_FT, p.Y * _MM_PER_FT) for p in points], center, a_start, sweep)
    z_min, z_max = min(p.Z for p in points), max(p.Z for p in points)
    warnings = [cb.torsion_note(u'Curved beam')]

    ld, bd = stirrup_bar_diameter_mm, bar_diameter_mm
    inset = cover_mm + ld + bd / 2.0
    z_top = z_max - inset / _MM_PER_FT
    z_bot = z_min + inset / _MM_PER_FT
    clear_mm = (z_top - z_bot) * _MM_PER_FT

    def xyz(r_mm, t, z_ft):
        x, y = cw.point(center, r_mm, cb.angle_at(a_start, sweep, t))
        return DB.XYZ(x / _MM_PER_FT, y / _MM_PER_FT, z_ft)

    def tangent(t):
        a = cb.angle_at(a_start, sweep, t)
        return DB.XYZ(-math.sin(a) * sign, math.cos(a) * sign, 0.0)

    r_mid = (r_min + r_max) / 2.0
    z_mid = (z_top + z_bot) / 2.0
    ends = []
    for t, outward in ((t_min, tangent(t_min).Negate()), (t_max, tangent(t_max))):
        ext = _column_reach_mm(doc, xyz(r_mid, t, z_mid), outward, cover_mm + ld + bd / 2.0)
        ends.append(ext if ext else -cover_mm)
    if not all(e > 0 for e in ends):
        warnings.append(u'Curved beam: no column found at {} — the bars stop at the beam end cover; '
                        u'check their anchorage.'.format(u'either end' if max(ends) <= 0 else u'one end'))

    stock = stock_length_mm if stock_length_mm and stock_length_mm >= 500.0 else 12000.0
    lap = lap_length_mm if lap_length_mm and lap_length_mm < stock else None
    anchor = anchorage_mm or 40.0 * bd

    def leg(ext, leg_sign):
        """Vertical leg offset (ft) where the bar runs ext mm into a column, else None."""
        if not leg_sign or ext <= 0:
            return None
        return DB.XYZ(0, 0, leg_sign * support_leg_mm(anchor, ext, bd, clear_mm) / _MM_PER_FT)

    def layer(count, z, leg_sign):
        groups = {}
        for r in (cb.bar_radii(r_min, r_max, inset, int(count)) if count else []):
            b0, b1 = t_min - ends[0] / r, t_max + ends[1] / r
            pieces = cw.split_arc(b0, b1, r, stock, lap) if lap else [(b0, b1)]
            for k, (s0, s1) in enumerate(pieces):
                chain = [DB.Arc.Create(xyz(r, s0, z), xyz(r, s1, z), xyz(r, (s0 + s1) / 2.0, z))]
                down = leg(ends[0], leg_sign) if k == 0 else None
                if down is not None:
                    p = chain[0].GetEndPoint(0)
                    chain.insert(0, DB.Line.CreateBound(p + down, p))
                down = leg(ends[1], leg_sign) if k == len(pieces) - 1 else None
                if down is not None:
                    p = chain[-1].GetEndPoint(1)
                    chain.append(DB.Line.CreateBound(p, p + down))
                groups.setdefault(k, []).append(chain)
        return [groups[k] for k in sorted(groups)]

    top = layer(n_top_bars, z_top, -1.0)
    bottom = layer(n_bottom_bars, z_bot, 0.0)

    r_lo, r_hi = r_min + cover_mm + ld / 2.0, r_max - cover_mm - ld / 2.0
    zl_lo, zl_hi = z_min + (cover_mm + ld / 2.0) / _MM_PER_FT, z_max - (cover_mm + ld / 2.0) / _MM_PER_FT
    r_c = (r_lo + r_hi) / 2.0
    pitch_c = cb.link_pitch_at_centre_mm(stirrup_spacing_mm, r_c, r_hi)
    links = []
    for t in cb.link_angles(t_min, t_max, r_c, pitch_c, end_offset_mm):
        corners = [xyz(r_lo, t, zl_lo), xyz(r_hi, t, zl_lo), xyz(r_hi, t, zl_hi), xyz(r_lo, t, zl_hi)]
        links.append(([DB.Line.CreateBound(corners[i], corners[(i + 1) % 4]) for i in range(4)], tangent(t)))
    return {'top': top, 'bottom': bottom, 'links': links, 'pitch_mm': stirrup_spacing_mm,
            'pitch_centre_mm': pitch_c, 'warnings': warnings}


def _end_ubar_sets(axis0, top, bottom, side_a, side_b, cover_mm, bar_dia_mm, link_dia_mm, normal, height,
                   at, ordered, exts, n_bottom, lap_mm, warnings):
    """
    End U-bars of the flexible detailing (SMDSC MB1): in the elevation plane, round the far face of
    each end column, the bottom leg lapping the span bottom bars (which stop 25 short of it) and the
    top leg the hanger bars (which stop 50 short); 30 % of the span bottom bars, at least two.
    [(host, group)].
    """
    import continuous_beam as cb
    n_u = cb.end_ubar_count(n_bottom)
    tops = compute_longitudinal_bar_lines(axis0, top, side_a, side_b, cover_mm, n_u, bar_dia_mm, link_dia_mm,
                                          seed_side_normal=normal)
    bots = compute_longitudinal_bar_lines(axis0, bottom, side_a, side_b, cover_mm, n_u, bar_dia_mm, link_dia_mm,
                                          seed_side_normal=normal)
    down = height.Negate().Multiply(bar_dia_mm / _MM_PER_FT)
    up = height.Multiply(bar_dia_mm / _MM_PER_FT)
    sp = tops[1].GetEndPoint(0).DistanceTo(tops[0].GetEndPoint(0)) * _MM_PER_FT if len(tops) > 1 else 0.0
    out = []
    for end, ext in enumerate(exts):
        if not ext:
            warnings.append(u'flexible detailing: no column found at the {} end, so no end U-bars there '
                            u'(SMDSC MB1: 50 % of the span bottom bars at a simple support).'.format(
                                u'start' if end == 0 else u'finish'))
            continue
        sign = 1.0 if end == 0 else -1.0
        face = ordered[0]['x0'] if end == 0 else ordered[-1]['x1']
        far = face - sign * ext
        top_in = face + sign * (cb.FLEX_TOP_GAP_MM + lap_mm)
        bot_in = face + sign * (cb.FLEX_BOTTOM_GAP_MM + lap_mm)
        chains = []
        for t, b in zip(tops, bots):
            pts = [at(t, top_in) + down, at(t, far) + down, at(b, far) + up, at(b, bot_in) + up]
            chains.append([[DB.Line.CreateBound(p, q) for p, q in zip(pts[:-1], pts[1:])]])
        host = ordered[0]['host'] if end == 0 else ordered[-1]['host']
        for group in group_parallel_bar_chains_into_sets(chains, sp, normal, u'Beam End U-Bars'):
            out.append((host, group))
    return out


def build_continuous_line(doc, hosts, cover_mm, bar_diameter_mm, n_top_bars, stirrup_bar_diameter_mm,
                          support_bar_diameter_mm, n_support_bars, stock_length_mm, lap_length_mm,
                          anchorage_mm, flexible=False, n_bottom_bars=2, top_drop_mm=0.0):
    """
    Hanger (continuous top) bars and support bars of one line of spans, plus how each span's
    own bars must end (continuous_beam's rules — see that module).
    flexible (IStructE SMDSC 4.2.3 / MB1): span bottom bars stop 25 short of the internal supports and
    lap with bottom splice bars across them (30 %, at least two, second layer); hanger bars stop 50
    short of them, the support bars giving the continuity.
    Returns {'hanger_sets': [(host, group)], 'support_sets': [(host, group)], 'splice_sets': [...],
             'spans': {host id value: {'continuous_ends', 'internal_bottom_ext_mm'}},
             'warnings': [...]} — group dicts as group_parallel_bar_chains_into_sets returns.
    """
    from nosa_utils import standards
    stock_length_mm = standards.bar_stock_length_mm(bar_diameter_mm, stock_length_mm)   # SMDSC 4.2.4
    import continuous_beam as cb
    from nosa_utils.revit_compat import get_id_value
    direction = get_beam_axis(hosts[0]).Direction.Normalize()
    origin = get_beam_axis(hosts[0]).GetEndPoint(0)
    axes, spans = {}, []
    for host in hosts:
        axis = _oriented_axis(host, direction)
        axes[host.Id] = axis
        x0 = (axis.GetEndPoint(0) - origin).DotProduct(direction) * _MM_PER_FT
        x1 = (axis.GetEndPoint(1) - origin).DotProduct(direction) * _MM_PER_FT
        spans.append({'id': get_id_value(host.Id), 'x0': x0, 'x1': x1, 'host': host})
    ordered, supports, warnings = cb.order_spans(spans)
    first, last = ordered[0]['host'], ordered[-1]['host']

    engine = _ensure_engine()
    faces = {}
    for span in ordered:
        top, bottom, side_a, side_b = _beam_faces(engine.CoverGeometryManager(doc, span['host']), direction)
        faces[span['id']] = (lowered_top(engine, top, top_drop_mm), bottom, side_a, side_b)
    top, bottom, side_a, side_b = faces[ordered[0]['id']]
    normal = direction.CrossProduct(top.normal.Normalize()).Normalize()
    axis0 = axes[first.Id]
    top_lines = compute_longitudinal_bar_lines(axis0, top, side_a, side_b, cover_mm, n_top_bars,
                                               bar_diameter_mm, stirrup_bar_diameter_mm,
                                               seed_side_normal=normal)
    bottom_lines = compute_longitudinal_bar_lines(axis0, bottom, side_a, side_b, cover_mm, 2,
                                                  bar_diameter_mm, stirrup_bar_diameter_mm,
                                                  seed_side_normal=normal)
    # one section along the whole line, or the hangers would not sit in every span's links
    for span in ordered[1:]:
        t2, _b2, a2, b2 = faces[span['id']]
        other = compute_longitudinal_bar_lines(axes[span['host'].Id], t2, a2, b2, cover_mm, n_top_bars,
                                               bar_diameter_mm, stirrup_bar_diameter_mm,
                                               seed_side_normal=normal)
        for mine, theirs in zip(top_lines, other):
            off = theirs.GetEndPoint(0) - mine.GetEndPoint(0)
            if (off - direction.Multiply(off.DotProduct(direction))).GetLength() * _MM_PER_FT > 5.0:
                raise ValueError(u'beams {} and {} do not share one section — reinforce them one '
                                 u'by one.'.format(ordered[0]['id'], span['id']))

    height = top.normal.Normalize()
    clear_mm = abs((top_lines[0].GetEndPoint(0) - bottom_lines[0].GetEndPoint(0)).DotProduct(height)) * _MM_PER_FT
    end_inset = cover_mm + stirrup_bar_diameter_mm
    from nosa_utils.revit_helpers import is_ground_beam
    ground = is_ground_beam(first)
    ext0, _e = support_extensions_mm(doc, axis0, end_inset, foundations=ground)
    _e, ext1 = support_extensions_mm(doc, axes[last.Id], end_inset, foundations=ground)
    x_start, x_end = ordered[0]['x0'] - ext0, ordered[-1]['x1'] + ext1

    def at(line, x):
        x_line = (line.GetEndPoint(0) - origin).DotProduct(direction) * _MM_PER_FT
        return line.GetEndPoint(0) + direction.Multiply((x - x_line) / _MM_PER_FT)

    def at_point(p, x):
        """The point of p's bar line at line coordinate x."""
        x_p = (p - origin).DotProduct(direction) * _MM_PER_FT
        return p + direction.Multiply((x - x_p) / _MM_PER_FT)

    def host_at(x):
        for span in ordered:
            if x <= span['x1'] + 1.0:
                return span['host']
        return last

    if flexible:
        # SMDSC MB1: at an end support with a column the hangers stop 50 short of it too, the
        # end U-bars giving the continuity into the column
        if ext0:
            x_start = ordered[0]['x0'] + cb.FLEX_TOP_GAP_MM
        if ext1:
            x_end = ordered[-1]['x1'] - cb.FLEX_TOP_GAP_MM
        segments = []
        for a, b in cb.flexible_hanger_runs(x_start, x_end, supports):
            segs, lap_notes = cb.lap_cuts(a, b, ordered, stock_length_mm, lap_length_mm)
            warnings.extend(lap_notes)
            segments.extend(segs)
        if not n_support_bars:
            warnings.append(u'flexible detailing: the hanger bars stop at the supports — give support bars '
                            u'for the continuity over them.')
    else:
        segments, lap_notes = cb.lap_cuts(x_start, x_end, ordered, stock_length_mm, lap_length_mm)
        warnings.extend(lap_notes)
    down = height.Negate().Multiply(bar_diameter_mm / _MM_PER_FT)     # contact lap under the bar
    leg0 = support_leg_mm(anchorage_mm, ext0, bar_diameter_mm, clear_mm) / _MM_PER_FT if ext0 and not flexible else 0.0
    leg1 = support_leg_mm(anchorage_mm, ext1, bar_diameter_mm, clear_mm) / _MM_PER_FT if ext1 and not flexible else 0.0
    spacing = (top_lines[1].GetEndPoint(0).DistanceTo(top_lines[0].GetEndPoint(0)) * _MM_PER_FT
               if len(top_lines) > 1 else 0.0)
    hanger_sets = []
    lowered = False
    for j, (a, b) in enumerate(segments):
        # a run that laps the previous one sits under it; a fresh run starts back in the top layer
        lowered = (not lowered) if j and a < segments[j - 1][1] - 1.0 else False
        chains = []
        for line in top_lines:
            p, q = at(line, a), at(line, b)
            if lowered:
                p, q = p + down, q + down
            curves = [DB.Line.CreateBound(p, q)]
            if j == 0 and leg0:
                curves.insert(0, DB.Line.CreateBound(p - height.Multiply(leg0), p))
            if j == len(segments) - 1 and leg1:
                curves.append(DB.Line.CreateBound(q, q - height.Multiply(leg1)))
            chains.append([curves])
        label = u'Beam Hanger Bars' if len(segments) == 1 else u'Beam Hanger Bars ({})'.format(j + 1)
        for group in group_parallel_bar_chains_into_sets(chains, spacing, normal, label):
            hanger_sets.append((host_at((a + b) / 2.0), group))

    support_sets, spacer_sets = [], []
    # support bars over the line's supports, SMDSC 6.3.2: at least 60 % to 0.25 L, none shorter than
    # max(0.15 L, 45 diameters), each side by its own span, L = clear span + d (user decision 2026-10-06)
    d_mm = clear_mm + longitudinal_bar_inset_mm(cover_mm, bar_diameter_mm, stirrup_bar_diameter_mm)
    warnings.extend(cb.simplified_rules_warnings([s['x1'] - s['x0'] for s in ordered]) if n_support_bars else [])
    n_long, _n_short = cb.hogging_groups(n_support_bars or 0)
    by_id = dict((s['id'], s) for s in ordered)
    for support in supports:
        if not support['continuous'] or not n_support_bars:
            continue
        left, right = by_id[support['left']], by_id[support['right']]
        reach_l = cb.hogging_reaches_mm(cb.effective_span_mm(left['x1'] - left['x0'], d_mm), support_bar_diameter_mm)
        reach_r = cb.hogging_reaches_mm(cb.effective_span_mm(right['x1'] - right['x0'], d_mm), support_bar_diameter_mm)
        rows = {}
        for k, (kind, p) in enumerate(_slot_points(top_lines, n_support_bars, support_bar_diameter_mm,
                                                   bar_diameter_mm, height, 0.0, direction, vibrator=True)):
            g = 1 if k < n_long else 0
            xa, xb = support['x0'] - reach_l[g], support['x1'] + reach_r[g]
            q = at_point(p, xa)
            rows.setdefault((kind, g), []).append(
                [[DB.Line.CreateBound(q, q + direction.Multiply((xb - xa) / _MM_PER_FT))]])
        for group in _grouped(rows, normal, u'Beam Support Bars'):
            support_sets.append((left['host'], group))
        for group in _spacer_groups(rows, top_lines, bar_diameter_mm, height, direction):
            spacer_sets.append((left['host'], group))

    span_ends = {}
    for i, span in enumerate(ordered):
        cont0 = i > 0 and supports[i - 1]['continuous']
        cont1 = i < len(ordered) - 1 and supports[i]['continuous']
        ext_b = [0.0, 0.0]
        for k, (cont, sup) in enumerate(((cont0, supports[i - 1] if i > 0 else None),
                                         (cont1, supports[i] if i < len(supports) else None))):
            if cont and flexible:
                ext_b[k] = -cb.FLEX_BOTTOM_GAP_MM
            elif cont:
                ext_b[k], note = cb.bottom_anchor_into_support(bar_diameter_mm, sup['width'])
                if note and k == 1:
                    warnings.append(note)
        own = get_beam_axis(span['host']).Direction.DotProduct(direction) >= 0
        ends = (cont0, cont1) if own else (cont1, cont0)
        exts = tuple(ext_b) if own else (ext_b[1], ext_b[0])
        stop = [None, None]
        if flexible and i == 0 and ext0:
            stop[0] = -cb.FLEX_BOTTOM_GAP_MM
        if flexible and i == len(ordered) - 1 and ext1:
            stop[1] = -cb.FLEX_BOTTOM_GAP_MM
        stops = tuple(stop) if own else (stop[1], stop[0])
        span_ends[span['id']] = {'continuous_ends': ends, 'internal_bottom_ext_mm': exts,
                                 'bottom_stop_mm': stops}
    splice_sets = []
    if flexible:
        n_splice = cb.splice_bar_count(n_bottom_bars)
        up = height.Multiply(bar_diameter_mm / _MM_PER_FT)          # second layer, on the span bars
        splice_lines = compute_longitudinal_bar_lines(axis0, bottom, side_a, side_b, cover_mm, n_splice,
                                                      bar_diameter_mm, stirrup_bar_diameter_mm,
                                                      seed_side_normal=normal)
        sp = (splice_lines[1].GetEndPoint(0).DistanceTo(splice_lines[0].GetEndPoint(0)) * _MM_PER_FT
              if len(splice_lines) > 1 else 0.0)
        for support in supports:
            if not support['continuous']:
                continue
            xa = support['x0'] - cb.FLEX_BOTTOM_GAP_MM - lap_length_mm
            xb = support['x1'] + cb.FLEX_BOTTOM_GAP_MM + lap_length_mm
            chains = [[[DB.Line.CreateBound(at(l, xa) + up, at(l, xb) + up)]] for l in splice_lines]
            for group in group_parallel_bar_chains_into_sets(chains, sp, normal, u'Beam Bottom Splice Bars'):
                splice_sets.append((by_id[support['left']]['host'], group))
        end_u_sets = _end_ubar_sets(axis0, top, bottom, side_a, side_b, cover_mm, bar_diameter_mm,
                                    stirrup_bar_diameter_mm, normal, height, at, ordered, (ext0, ext1),
                                    n_bottom_bars, lap_length_mm, warnings)
    else:
        end_u_sets = []
    return {'hanger_sets': hanger_sets, 'support_sets': support_sets, 'spans': span_ends,
            'splice_sets': splice_sets, 'end_u_sets': end_u_sets, 'spacer_sets': spacer_sets,
            'warnings': warnings}
