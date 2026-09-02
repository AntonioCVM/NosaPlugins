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

    vertical_pt = engine.compute_cover_point(face_info, cover_mm + stirrup_diameter_mm)
    side_inset_mm = cover_mm + stirrup_diameter_mm + bar_diameter_mm / 2.0
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
                    'curves': [seg], 'all_curves': [[seg]], 'count': 1,
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
            'curves': [chains[0][seg_idx]],
            'all_curves': [[chain[seg_idx]] for chain in chains],
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
    length_mm = axis_curve.Length * _MM_PER_FT
    lo = start_offset_mm
    hi = length_mm - end_offset_mm
    return _evenly_spaced(lo, hi, spacing_mm)


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

    groups = []
    if confine_each > dense * 0.5:
        start_hi = lo + confine_each
        end_lo = hi - confine_each
        if start_hi > lo:
            groups.append({
                'zone': u'start',
                'spacing_mm': dense,
                'positions': _evenly_spaced(lo, start_hi, dense),
            })
        if end_lo > start_hi + spacing_mm * 0.5:
            groups.append({
                'zone': u'middle',
                'spacing_mm': spacing_mm,
                'positions': _evenly_spaced(start_hi, end_lo, spacing_mm),
            })
        if hi > end_lo:
            groups.append({
                'zone': u'end',
                'spacing_mm': dense,
                'positions': _evenly_spaced(end_lo, hi, dense),
            })
    else:
        groups.append({
            'zone': u'middle',
            'spacing_mm': spacing_mm,
            'positions': _evenly_spaced(lo, hi, spacing_mm),
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
                             confine_length_mm=None):
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
        }
    """
    engine = _ensure_engine()
    axis = get_beam_axis(host)
    _raw_axis_len_mm = axis.Length * _MM_PER_FT
    # BUG FIX (2026-09-01) — see _clamp_axis_to_bbox's own docstring:
    # the raw LocationCurve can run past the beam's actual (mitred)
    # solid at each end; every downstream use of `axis` (longitudinal
    # bars AND stirrup zones) needs the clamped version, so this
    # happens once, immediately, before anything else derives from it.
    axis = _clamp_axis_to_bbox(axis, host)
    # DIAGNOSTIC (2026-09-02) — two different clamp strategies
    # (get_BoundingBox, then get_isolated_solid_bbox) both reportedly
    # produced NO visible change live. Rather than guess a third one
    # blindly, this makes the clamp's own before/after effect visible
    # in ui.py's (now unlimited) result log — settles definitively
    # whether this code path is even running (pyRevit module caching —
    # a Reload is required after every lib/*.py edit — is the leading
    # suspect given two different fixes produced byte-identical
    # "unchanged" results) and, if it IS running, exactly what it
    # computed.
    _clamped_axis_len_mm = axis.Length * _MM_PER_FT
    warnings = [u'DIAGNOSTIC: beam axis length before clamp = {:.1f}mm, '
                u'after _clamp_axis_to_bbox = {:.1f}mm ({})'.format(
                    _raw_axis_len_mm, _clamped_axis_len_mm,
                    u'unchanged — LocationCurve already fits the solid, or no '
                    u'bbox was available' if abs(_raw_axis_len_mm - _clamped_axis_len_mm) < 0.5
                    else u'shortened by {:.1f}mm total'.format(
                        _raw_axis_len_mm - _clamped_axis_len_mm))]
    cover_mgr = engine.CoverGeometryManager(doc, host)
    top, bottom, side_a, side_b = _beam_faces(cover_mgr, axis.Direction)

    # DIAGNOSTIC (2026-09-02, round 3) — reported live: the LENGTH
    # diagnostic above confirmed the bar's own axial length is exact
    # (matches the clamped axis), yet the CREATED rebar still visibly
    # sits outside the beam. Live bounding-box comparison (beam
    # 1318407: X=[19165,19465], 300mm wide vs its own bar rows:
    # X=[19391,19589]) showed the bars are NOT extending past the beam's
    # ENDS — they are offset ~175mm sideways, off the beam's own
    # centreline, on a 300mm-wide section — pushing most/all of the row
    # outside the WIDTH of the beam instead. This surfaces exactly where
    # `side_a`/`side_b` (this beam's own detected long-side faces) and
    # their cover-offset points land relative to the axis, in the
    # WIDTH direction only — isolating whether _beam_faces picked the
    # wrong faces (e.g. this beam's Family is a custom "RC Beam" with
    # Revit's own Section Shape reported as "Not Defined" — its
    # geometry may not expose 2 simple rectangular side faces the way
    # a standard parametric framing type would) or whether
    # engine.compute_cover_point's own offset is the culprit.
    try:
        _height_dir_dbg = top.normal.Normalize()
        _width_dir_dbg = axis.Direction.CrossProduct(_height_dir_dbg).Normalize()
        _p0_dbg = axis.GetEndPoint(0)
        _side_inset_dbg = cover_mm + stirrup_bar_diameter_mm + bar_diameter_mm / 2.0
        _edge_a_dbg = engine.compute_cover_point(side_a, _side_inset_dbg)
        _edge_b_dbg = engine.compute_cover_point(side_b, _side_inset_dbg)
        _w_a_mm = (_edge_a_dbg - _p0_dbg).DotProduct(_width_dir_dbg) * _MM_PER_FT
        _w_b_mm = (_edge_b_dbg - _p0_dbg).DotProduct(_width_dir_dbg) * _MM_PER_FT
        _n_a_dbg = side_a.normal
        _n_b_dbg = side_b.normal
        warnings.append(
            u'DIAGNOSTIC: side_a/side_b width offsets from axis (mm) = '
            u'{:.1f} / {:.1f} (span {:.1f}mm; should straddle 0 — i.e. '
            u'opposite signs — and span roughly the beam\'s own width '
            u'minus 2x cover+stirrup+half-bar-dia); side_a.normal=({:.2f},'
            u'{:.2f},{:.2f}), side_b.normal=({:.2f},{:.2f},{:.2f}) '
            u'(should be near-opposite unit vectors, each roughly '
            u'perpendicular to the axis).'.format(
                _w_a_mm, _w_b_mm, abs(_w_b_mm - _w_a_mm),
                _n_a_dbg.X, _n_a_dbg.Y, _n_a_dbg.Z,
                _n_b_dbg.X, _n_b_dbg.Y, _n_b_dbg.Z))
    except Exception as _dbg_exc:
        warnings.append(u'DIAGNOSTIC: side_a/side_b width-offset check itself '
                         u'failed ({}) — see console for the original '
                         u'traceback.'.format(_dbg_exc))

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

    # DIAGNOSTIC (2026-09-02, round 2) — the axis-clamp diagnostic above
    # proved the clamp is a no-op for this beam (axis already fits the
    # solid), yet the CREATED rebar still overshoots the solid by 20mm at
    # EACH end. This checks the bar line's own length immediately after
    # compute_longitudinal_bar_lines returns, BEFORE split_long_bars runs —
    # isolating whether the 40mm (20mm/end) extension is introduced by bar
    # construction itself or by the stock-length split/lap-offset transform.
    if top_lines:
        _first_top_len_mm = top_lines[0].Length * _MM_PER_FT
        warnings.append(
            u'DIAGNOSTIC: clamped axis = {:.1f}mm, first TOP bar line '
            u'(pre-split, from compute_longitudinal_bar_lines) = {:.1f}mm '
            u'({})'.format(
                _clamped_axis_len_mm, _first_top_len_mm,
                u'matches axis' if abs(_first_top_len_mm - _clamped_axis_len_mm) < 0.5
                else u'DIFFERS by {:.1f}mm — extension introduced in '
                     u'compute_longitudinal_bar_lines'.format(
                         _first_top_len_mm - _clamped_axis_len_mm)))

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
        top_chains, top_spacing_mm, long_bar_normal_vec, u'Beam Top Bars')
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

    if densify_ends:
        dens = dense_spacing_mm if dense_spacing_mm else max(stirrup_spacing_mm * 0.5, 75.0)
        zone_groups = generate_stirrup_positions_densified(
            axis, stirrup_spacing_mm, dens, confine_length_mm,
            stirrup_start_offset_mm, stirrup_end_offset_mm)
    else:
        positions = generate_stirrup_positions(
            axis, stirrup_spacing_mm, stirrup_start_offset_mm, stirrup_end_offset_mm)
        zone_groups = [{
            'zone': u'middle',
            'spacing_mm': stirrup_spacing_mm,
            'positions': positions,
        }] if positions else []

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
        spacing = zg['spacing_mm']
        array_mm = (n - 1) * spacing if n > 1 else 0.0
        stirrup_sets.append({
            'zone': zg['zone'],
            'curves': zone_curves[0],
            'all_curves': zone_curves,
            'spacing_mm': spacing,
            'array_length_mm': array_mm,
            'count': n,
            'normal': axis.Direction.Normalize(),
        })

    return {
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
        'warnings': warnings,
    }
