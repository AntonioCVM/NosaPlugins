# -*- coding: utf-8 -*-
"""
NOSA.RebarAutomate — Column Rebar (Phase 2)
============================================================================

Category module for structural columns. Loads rebar_engine.py in
isolation via nosa_utils.bootstrap.load_module (unique alias
're_engine'), matching this extension's established sys.modules
isolation convention.

Pure geometry/math — NO UI. Every public function returns DB.Curve
objects (or lists of them) for a caller to hand to
rebar_engine.RebarWrapper.

SCOPE
-----
Targets a STRAIGHT, vertical, RECTANGULAR column: a single Line
location curve and exactly 4 planar side faces (roughly vertical
normals excluded, roughly horizontal normals expected). A circular
column, or one whose faces don't resolve to 4 flat sides, raises a
clear ValueError — see _column_faces()'s docstring. Perimeter-only
vertical reinforcement (the common case) is generated; interior bars
are out of scope.

PHASE 3 — WIRED INTO THE MAIN DASHBOARD, STIRRUPS BECOME REBAR SETS
------------------------------------------------------------------
This module's face-based topology, perimeter bar layout, dowel/lap
extension, and joint-zone stirrup spacing all predate the Set/global-
bbox architecture footings and floors ended up with, and were never
wired into ui.py. Phase 3 adds the missing piece rather than replacing
what already worked: stirrups at a densified joint zone (or the single
uniform zone when densification is off) are now built as Rebar SETS
(RebarStyle.StirrupTie, propagated along the column's own axis
direction) via generate_column_stirrup_zones() + build_stirrup_sets() —
the exact same create_rebar_set/SetLayoutAsMaximumSpacing mechanism
footing_rebar.build_side_rebar_set already proved live ("absolutamente
perfecta") for a vertically-propagated closed rectangle; a column
stirrup zone is the identical shape and propagation axis, just with a
horizontal cross-section sized from the column's own faces instead of
a footing's plan footprint. generate_column_stirrup_positions() (the
Phase 2 flat-position list) is left fully INTACT as a lower-level
building block other callers may still want.

VERTICAL BARS remain individual Rebar elements (unchanged) — each sits
at its own distinct (u, v) position, not a repeated/evenly-spaced-in-
one-direction shape SetLayoutAsMaximumSpacing could represent, and a
column's bar count (typically 4-20) was never the "thousands of
elements" performance/MRA problem floors had.

ADAPTABILITY — DISCLOSED LIMITATION: every curve this module (and every
other category module in this plugin) produces is EXPLICIT, ABSOLUTE
geometry computed ONCE from the host's CURRENT dimensions via
Rebar.CreateFromCurves — genuinely "Shape Driven" in Revit's own sense
(rebar that re-associates with host FACE REFERENCES and re-solves
automatically when the host is later resized) would need
Rebar.CreateFromRebarShape driven by real geometric constraints, which
none of this plugin's output uses. If a column's dimensions change
after this tool runs, its rebar will NOT auto-adjust — the tool must be
re-run to regenerate correctly-sized curves. This is not a
columns-specific gap; it is how footings and floors already behave
today, and is called out here explicitly rather than left to be
discovered as a surprise.
"""
import math
import os
import sys

from Autodesk.Revit import DB

# PHASE F2 — same sys.path convention as rebar_batch.py: this module can
# be loaded standalone (a legacy phase test script, or a stub-Revit dev
# environment) without the extension-wide lib/ dir already on sys.path.
_HERE = os.path.dirname(os.path.abspath(__file__))
_EXT_LIB = os.path.abspath(os.path.join(_HERE, '..', '..', '..', '..', '..', 'lib'))
if _EXT_LIB not in sys.path:
    sys.path.insert(0, _EXT_LIB)

from nosa_utils import standards  # noqa: E402

_HERE = os.path.dirname(os.path.abspath(__file__))
re_engine = None


def _ensure_engine():
    global re_engine
    if re_engine is None:
        # PHASE F0 — migrated from imp.load_source to
        # nosa_utils.bootstrap.load_module. Registered name unchanged.
        from nosa_utils.bootstrap import load_module
        re_engine = load_module('re_engine', os.path.join(_HERE, 'rebar_engine.py'))
    return re_engine


_MM_PER_FT = 304.8

# PHASE 3.4/3.5/3.5.2 — how far INSIDE the host's own real vertical
# extent a clamped axis endpoint is pulled, mm — see get_column_axis's
# own docstring for why this is an inset, not an exact-boundary clamp.
# Raised from 2.0 to 5.0mm in Phase 3.5.2 per live confirmation that
# the smaller margin was still occasionally insufficient.
_AXIS_CLAMP_EPSILON_MM = 5.0
_AXIS_CLAMP_EPSILON_FT = _AXIS_CLAMP_EPSILON_MM / _MM_PER_FT

# PHASE 3.5.6 item 4 — how far inward from a stirrup zone's own
# boundary the FIRST/LAST crosstie of that zone is inset, mm — see
# build_crosstie_sets's own comment for why (zone boundaries are
# exactly where a detected floor's own thickness was cut out).
_CROSSTIE_Z_EPSILON_MM = 50.0

# PHASE 3.5.9 item 4 — number of straight chords approximating a
# circular column's tie (Revit rejects a closed 2-Arc loop outright —
# see _build_circular_column_reinforcement's own docstring). 24 chords
# keeps the polygon-to-circle deviation well under 1% of radius for any
# realistic column tie size, while staying a modest curve count.
_CIRCULAR_TIE_CHORD_COUNT = 24


# ══════════════════════════════════════════════════════════════════════════
# Location curve & face classification
# ══════════════════════════════════════════════════════════════════════════

def _solid_z_extent_ft(solid):
    """
    Real vertical extent of a Solid, read from its own Edges' curve
    endpoints — NOT from the host element's reported bounding box.

    PHASE 3.5.1 fix — ground-floor columns kept throwing
    Rebar.CreateFromCurves "Internal Error" even after the epsilon-
    inset Z clamp in get_column_axis (Phase 3.4/3.5 item 1):
    host.get_BoundingBox(None) can be skewed relative to a column's
    OWN solid once other elements are joined to it (join_geometry can
    affect what a bounding box query reports for the joined element),
    so clamping the axis against that bbox was clamping against the
    wrong reference in exactly the join-heavy ground-floor case. This
    reads the column's real geometry directly instead, unaffected by
    whatever else is joined to it.

    Args:
        solid (DB.Solid or None)

    Returns:
        (min_z_ft, max_z_ft), or None if `solid` is None, exposes no
        usable Edges (e.g. a mocked/test solid), or the resulting edge
        list has no evaluable curves — callers must fall back to the
        bounding box in that case.
    """
    if solid is None:
        return None
    try:
        edges = solid.Edges
    except Exception:
        return None

    z_values = []
    try:
        for edge in edges:
            try:
                curve = edge.AsCurve()
            except Exception:
                continue
            if curve is None:
                continue
            try:
                p0, p1 = curve.GetEndPoint(0), curve.GetEndPoint(1)
            except Exception:
                continue
            z_values.append(p0.Z)
            z_values.append(p1.Z)
    except Exception:
        return None

    if not z_values:
        return None
    return min(z_values), max(z_values)


def _base_top_z_ft_from_level_params(host):
    """
    PHASE 3.5.2 item 2 — the column instance's own AUTHORED Base/Top
    Level + Offset parameters, resolved to absolute Z (ft) — completely
    independent of Solid or BoundingBox geometry, and therefore immune
    to Join Geometry altering what a joined element's REPORTED
    geometry looks like.

    Root cause this fixes: _solid_z_extent_ft(get_host_solid(host)) —
    the Phase 3.5.1 fix — reads host.get_Geometry(opts), which for a
    column JOINED to its foundation can legitimately reflect the join
    (the same class of problem host.get_BoundingBox(None) already had,
    just moved to a different Revit API call). FAMILY_BASE_LEVEL_PARAM
    / FAMILY_TOP_LEVEL_PARAM and their _OFFSET_PARAM counterparts are
    parameters the user AUTHORED on this instance directly — Revit
    does not rewrite them in response to a join with another element,
    so they give the column's true intended vertical extent regardless
    of what its solid currently looks like after joining.

    Returns:
        (base_z_ft, top_z_ft), or None if any of the four parameters
        is missing or unreadable (a non-structural-column family
        without these BIPs, a slanted-column edge case, or an older
        Revit API surface) — callers fall back to Solid/BoundingBox in
        that case, unchanged from pre-3.5.2 behaviour.
    """
    try:
        doc = host.Document
        base_level_param = host.get_Parameter(DB.BuiltInParameter.FAMILY_BASE_LEVEL_PARAM)
        base_offset_param = host.get_Parameter(DB.BuiltInParameter.FAMILY_BASE_LEVEL_OFFSET_PARAM)
        top_level_param = host.get_Parameter(DB.BuiltInParameter.FAMILY_TOP_LEVEL_PARAM)
        top_offset_param = host.get_Parameter(DB.BuiltInParameter.FAMILY_TOP_LEVEL_OFFSET_PARAM)
        if None in (base_level_param, base_offset_param, top_level_param, top_offset_param):
            return None
        base_level = doc.GetElement(base_level_param.AsElementId())
        top_level = doc.GetElement(top_level_param.AsElementId())
        if base_level is None or top_level is None:
            return None
        base_z_ft = base_level.Elevation + base_offset_param.AsDouble()
        top_z_ft = top_level.Elevation + top_offset_param.AsDouble()
    except Exception:
        return None
    if top_z_ft <= base_z_ft:
        return None
    return base_z_ft, top_z_ft


def get_column_axis(host):
    """
    The column's vertical centreline, as a DB.Line — PHASE 3.1 FIX for
    a live crash ("Host has no LocationCurve"): OST_StructuralColumns
    instances are, in the common case, LocationPOINT-based (a single
    insertion point + rotation), not LocationCurve-based — this
    function's original LocationCurve-only assumption aborted on every
    ordinary column and only ever worked for the unusual
    slanted/legacy families that DO use a LocationCurve.

    Resolution order:
      1. host.Location.Curve, if present AND a straight Line — the
         most direct source when it exists (some slanted-column
         families genuinely do model this way); still rejects a
         curved/non-Line curve as out of scope, unchanged from before.
      2. Otherwise (the common LocationPoint case): build the axis from
         the host's own GLOBAL bounding box
         (host.get_BoundingBox(None)) — Z runs from Min.Z to Max.Z,
         which works regardless of how the column's family/instance is
         parametrised internally (Base/Top Level + offsets, a single
         extrusion height, etc. all resolve to the same overall
         bounding box). The horizontal (X, Y) position comes from
         host.Location.Point if available (the column's own real
         insertion point — more accurate than a bbox-derived centre
         for a column that isn't perfectly centred in its own bbox,
         e.g. one with an asymmetric family origin), falling back to
         the bbox's own X/Y centre only if there is no LocationPoint
         either.

    Args:
        host (DB.Element): the column instance.

    Returns:
        DB.Line — always vertical (Z-aligned) when derived via the
        bounding-box path; whatever direction Location.Curve itself
        has when that path is used.

    PHASE 3.4/3.5 item 1 FIX — a live "ground floor" crash
    (Rebar.CreateFromCurves: "An internal error has occurred.") traced
    to the LocationCurve path: some column families' LocationCurve
    extends slightly BELOW the real solid's own base (e.g. a family
    origin/extrusion quirk, or a base offset that doesn't line up
    exactly with the reported Location), so a bar built from that axis
    starts PARTIALLY OUTSIDE the host — which Rebar.CreateFromCurves
    can throw an opaque Internal Error for, rather than a clear
    message. Fixed by CLAMPING the returned axis's Z-range, INSET by a
    small epsilon (_AXIS_CLAMP_EPSILON_FT) rather than exactly to the
    boundary — a curve endpoint sitting EXACTLY ON a solid's own face
    is a classic floating-point containment edge case (Revit's own
    inside/outside test can flip either way at the boundary itself),
    so the clamp lands the bar's end a hair INSIDE the solid instead,
    guaranteeing strict containment rather than a knife-edge
    coincidence.

    PHASE 3.5.1 FIX — the clamp bound itself: this crash persisted
    live even with the epsilon inset, on ground-floor columns joined
    to other elements. Root cause: clamping against
    host.get_BoundingBox(None) clamps against whatever bbox Revit
    reports for the JOINED element, which is not reliably the
    column's own solid extent. The clamp bound preferred
    _solid_z_extent_ft(get_host_solid(host)) — the real solid's own
    Edges — falling back to the bounding box only when the solid isn't
    readable.

    PHASE 3.5.2 FIX — the crash persisted even against Solid.Edges: a
    JOINED column's own get_Geometry() can legitimately reflect the
    join too (the same class of problem, one API call over). The Z
    extent now prefers _base_top_z_ft_from_level_params(host) — the
    column's own AUTHORED Base/Top Level+Offset parameters, which
    Revit does not alter in response to a join — falling back to
    Solid.Edges, then the bounding box, only when those parameters
    aren't readable.

    PHASE 3.5.3 FIX (REVERTED in 3.5.7 — see below): briefly took the
    INTERSECTION of the Level+Offset extent and the Solid.Edges extent
    as a "belt-and-suspenders" safety net, on the theory that
    Level+Offset alone might be mis-parametrised. That intersection
    directly caused a live regression: when a column is JOINED to a
    floor ABOVE it and Join Geometry subtracts the floor's volume from
    the column's own solid (a common, often default, join outcome),
    Solid.Edges' own Max Z sits at the FLOOR'S UNDERSIDE — well short
    of the column's true structural top — and the intersection
    silently clamped the column's usable axis to stop right there,
    severing vertical bar continuity and eliminating the crank/starter
    entirely at every floor the column passes through.

    PHASE 3.5.7 FIX — reverted to STRICT priority, no blending:
    Base/Top Level+Offset is the AUTHORED design intent and the
    NON-NEGOTIABLE authority for the column's vertical extent whenever
    it is readable at all — Solid.Edges is consulted only as a
    fallback when Level+Offset genuinely isn't available (not to
    narrow it), and the bounding box only when neither is. A join
    notching the solid must never be allowed to amputate continuity
    reinforcement that the column's own authored parameters say should
    be there.

    Raises:
        ValueError: if a LocationCurve exists but isn't a straight
        Line, or if NEITHER a usable LocationCurve nor a readable
        global bounding box can be found at all.
    """
    loc = getattr(host, 'Location', None)
    curve = getattr(loc, 'Curve', None) if loc is not None else None
    bbox = host.get_BoundingBox(None)

    z_extent_ft = _base_top_z_ft_from_level_params(host)
    if z_extent_ft is None:
        try:
            solid = _ensure_engine().get_host_solid(host)
        except Exception:
            solid = None
        z_extent_ft = _solid_z_extent_ft(solid)

    if curve is not None:
        if not isinstance(curve, DB.Line):
            raise ValueError(u'Column centreline is not a straight Line — '
                              u'curved/slanted columns are not supported by '
                              u'this module yet.')
        result = curve
    else:
        if bbox is None and z_extent_ft is None:
            raise ValueError(u'Could not determine this column\'s axis — it has '
                              u'neither a usable LocationCurve nor a readable '
                              u'global bounding box or solid.')

        point = getattr(loc, 'Point', None) if loc is not None else None
        if point is not None:
            x, y = point.X, point.Y
        elif bbox is not None:
            x = (bbox.Min.X + bbox.Max.X) / 2.0
            y = (bbox.Min.Y + bbox.Max.Y) / 2.0
        else:
            raise ValueError(u'Could not determine this column\'s horizontal '
                              u'position — no LocationPoint and no readable '
                              u'bounding box.')

        lo_z = z_extent_ft[0] if z_extent_ft is not None else bbox.Min.Z
        hi_z = z_extent_ft[1] if z_extent_ft is not None else bbox.Max.Z
        result = DB.Line.CreateBound(DB.XYZ(x, y, lo_z), DB.XYZ(x, y, hi_z))

    clamp_lo_z = z_extent_ft[0] if z_extent_ft is not None else (bbox.Min.Z if bbox is not None else None)
    clamp_hi_z = z_extent_ft[1] if z_extent_ft is not None else (bbox.Max.Z if bbox is not None else None)
    if clamp_lo_z is not None and clamp_hi_z is not None:
        p0, p1 = result.GetEndPoint(0), result.GetEndPoint(1)
        lo, hi = (p0, p1) if p0.Z <= p1.Z else (p1, p0)
        clamped_lo_z = max(lo.Z, clamp_lo_z + _AXIS_CLAMP_EPSILON_FT)
        clamped_hi_z = min(hi.Z, clamp_hi_z - _AXIS_CLAMP_EPSILON_FT)
        if clamped_hi_z <= clamped_lo_z:
            # A pathologically short extent (thinner than 2x the
            # epsilon) — fall back to the raw, un-inset bounds rather
            # than producing an inverted or zero-length axis.
            clamped_lo_z, clamped_hi_z = clamp_lo_z, clamp_hi_z
        if abs(clamped_lo_z - lo.Z) > 1e-9 or abs(clamped_hi_z - hi.Z) > 1e-9:
            new_lo = DB.XYZ(lo.X, lo.Y, clamped_lo_z)
            new_hi = DB.XYZ(hi.X, hi.Y, clamped_hi_z)
            result = (DB.Line.CreateBound(new_lo, new_hi) if p0.Z <= p1.Z
                      else DB.Line.CreateBound(new_hi, new_lo))

    return result


def _column_faces(cover_mgr, axis_dir):
    """
    Classify a rectangular column host's 4 side faces into two opposite
    pairs spanning the local (u, v) horizontal cross-section directions.

    Side faces are those whose normal is roughly horizontal
    (|normal.Z| < 0.3 — the same threshold family used by
    footing_rebar/beam_rebar for their own face classification, so a
    column's top/bottom cap faces are excluded the same way a beam's
    end-cut faces are).

    Pairing: face[0] is taken as the "u+" reference; among the
    remaining 3, whichever face's normal is most nearly opposite
    face[0]'s (DotProduct closest to -1) is "u-". The last 2 faces are
    "v+"/"v-", assigned by the sign of their normal's dot product with
    v_dir = axis_dir x u_dir.

    Args:
        cover_mgr (rebar_engine.CoverGeometryManager)
        axis_dir  (DB.XYZ): unit vector, the column's (vertical) axis
                  direction.

    Returns:
        (u_pos, u_neg, v_pos, v_neg, u_dir, v_dir) — each face a
        rebar_engine.HostFaceInfo, u_dir/v_dir unit DB.XYZ.

    Raises:
        ValueError: if the host doesn't have exactly 4 side faces —
        see module SCOPE note (e.g. circular columns).
    """
    sides = [f for f in cover_mgr.faces if abs(f.normal.Z) < 0.3]
    if len(sides) != 4:
        raise ValueError(
            u'Expected exactly 4 vertical side faces for a rectangular '
            u'column, found {} — circular or non-rectangular columns are '
            u'not supported by this module yet.'.format(len(sides)))

    u_pos = sides[0]
    rest = sides[1:]
    u_neg = min(rest, key=lambda f: u_pos.normal.DotProduct(f.normal))
    rest = [f for f in rest if f is not u_neg]
    v_dir = axis_dir.CrossProduct(u_pos.normal.Normalize()).Normalize()
    if rest[0].normal.DotProduct(v_dir) >= rest[1].normal.DotProduct(v_dir):
        v_pos, v_neg = rest[0], rest[1]
    else:
        v_pos, v_neg = rest[1], rest[0]

    return u_pos, u_neg, v_pos, v_neg, u_pos.normal.Normalize(), v_dir


def _cross_section_half_extents(engine, axis, u_pos, u_neg, v_pos, v_neg,
                                 u_dir, v_dir, inset_mm):
    """
    Cover-inset half-width (along u_dir) and half-depth (along v_dir)
    of the column's cross-section, measured from the axis centreline.

    Args:
        engine  (module): rebar_engine, from _ensure_engine().
        axis    (DB.Line): the column's centreline.
        u_pos, u_neg, v_pos, v_neg (rebar_engine.HostFaceInfo): from
                _column_faces().
        u_dir, v_dir (DB.XYZ): unit vectors, from _column_faces().
        inset_mm (float): distance to inset from each face, mm (e.g.
                cover_mm, or cover_mm + bar_diameter_mm for stirrups
                sitting inside the main bars).

    Returns:
        (half_w_mm, half_d_mm)
    """
    p_ref = axis.GetEndPoint(0)
    pt_u_pos = engine.compute_cover_point(u_pos, inset_mm)
    pt_u_neg = engine.compute_cover_point(u_neg, inset_mm)
    pt_v_pos = engine.compute_cover_point(v_pos, inset_mm)
    pt_v_neg = engine.compute_cover_point(v_neg, inset_mm)

    half_w_mm = abs((pt_u_pos - p_ref).DotProduct(u_dir)
                     - (pt_u_neg - p_ref).DotProduct(u_dir)) / 2.0 * _MM_PER_FT
    half_d_mm = abs((pt_v_pos - p_ref).DotProduct(v_dir)
                     - (pt_v_neg - p_ref).DotProduct(v_dir)) / 2.0 * _MM_PER_FT
    return half_w_mm, half_d_mm


def _lookup_length_param_mm(host, names):
    """
    Best-effort length-parameter lookup by NAME — instance parameters
    first, then the host's own type (Symbol) — used as a fallback
    when a column's geometry can't be read from its Solid.Faces at
    all (see detect_column_geometry's PHASE 3.5.1 item 4 fallback).

    Args:
        host  (DB.Element)
        names (list[unicode]): candidate parameter names to try, in
              order; each tried on instance then type before moving to
              the next name.

    Returns:
        float (mm) — the first positive value found, or None.
    """
    candidates = [host]
    try:
        symbol = getattr(host, 'Symbol', None)
        if symbol is not None:
            candidates.append(symbol)
    except Exception:
        pass

    for elem in candidates:
        for name in names:
            try:
                param = elem.LookupParameter(name)
            except Exception:
                param = None
            if param is None:
                continue
            try:
                value_ft = param.AsDouble()
            except Exception:
                value_ft = None
            if value_ft is not None and value_ft > 0:
                return value_ft * _MM_PER_FT
    return None


def _resolve_column_geometry_source(host, axis, cover_mgr):
    """
    PHASE 3.5.6 item 1 — decide ONCE, per column, which geometry
    source drives its cross-section: ANALYTICAL (the column TYPE's own
    authored `b`/`h` dimensions + the instance's real in-plan rotation)
    as the PRIMARY path, falling back to the existing face-based
    `_column_faces` only when the type doesn't expose `b`/`h` or the
    instance's rotation isn't readable.

    Why analytical is now primary: `_column_faces` requires EXACTLY 4
    near-vertical planar side faces (abs(normal.Z) < 0.3) on the
    column's own Solid — a column genuinely JOINED to a floor/beam
    (JoinGeometry) routinely has that count altered (faces split or
    merged at the join), and a circular column never has 4 planar
    faces at all. `b`/`h` and `Location.Rotation` are the column's own
    AUTHORED design values — Revit does not rewrite them in response
    to a join, so they give the column's true intended cross-section
    regardless of what its solid currently looks like post-join. This
    mirrors the exact reasoning already applied to the column's
    VERTICAL extent in get_column_axis (Base/Top Level+Offset over
    Solid.Edges over BoundingBox) — same problem, same fix pattern,
    applied to the HORIZONTAL section instead.

    The face-based path is NOT deleted — it remains the fallback for
    a family that genuinely doesn't expose `b`/`h` (or a slanted/
    legacy family with an unreadable rotation), so a working
    cross-section detection is never lost for those edge cases.

    Args:
        host  (DB.Element): the column instance.
        axis  (DB.Line): from get_column_axis(host) — only its
              direction is used (for the face-based fallback).
        cover_mgr (rebar_engine.CoverGeometryManager): only consulted
              if the analytical path isn't available.

    Returns:
        dict — either
        {'kind': 'analytical', 'u_dir': DB.XYZ, 'v_dir': DB.XYZ,
         'b_mm': float, 'h_mm': float}
        or
        {'kind': 'faces', 'u_dir': DB.XYZ, 'v_dir': DB.XYZ,
         'u_pos': HostFaceInfo, 'u_neg': HostFaceInfo,
         'v_pos': HostFaceInfo, 'v_neg': HostFaceInfo}

    Raises:
        ValueError: propagated from _column_faces if the analytical
        path isn't available AND the host doesn't have exactly 4
        rectangular side faces either — same failure this function
        replaces, just reached one path later.
    """
    b_mm = _lookup_length_param_mm(host, [u'b', u'B'])
    h_mm = _lookup_length_param_mm(host, [u'h', u'H'])
    loc = getattr(host, 'Location', None)
    rotation = getattr(loc, 'Rotation', None) if loc is not None else None

    # PHASE 3.5.9 item 1 FIX — many genuine SQUARE column families
    # author only 'b' (no separate 'h' parameter at all, since a square
    # section has none to author) rather than omitting 'h' for a
    # circular column (circular families use "Diameter" instead — see
    # build_column_reinforcement's own branch above this call). A bare
    # 'b' with no 'h' is therefore treated as a square section,
    # h_mm = b_mm, analytically — NOT punted to the face-based fallback
    # (which is more fragile under Join Geometry) and NEVER treated as
    # a diameter (that was the live bug: square columns silently
    # running through the circular-column code path).
    if b_mm is not None and h_mm is None:
        h_mm = b_mm

    if b_mm is not None and h_mm is not None and rotation is not None:
        u_dir = DB.XYZ(math.cos(rotation), math.sin(rotation), 0.0)
        v_dir = DB.XYZ(-math.sin(rotation), math.cos(rotation), 0.0)
        return {'kind': 'analytical', 'u_dir': u_dir, 'v_dir': v_dir,
                'b_mm': b_mm, 'h_mm': h_mm}

    u_pos, u_neg, v_pos, v_neg, u_dir, v_dir = _column_faces(cover_mgr, axis.Direction)
    return {'kind': 'faces', 'u_dir': u_dir, 'v_dir': v_dir,
            'u_pos': u_pos, 'u_neg': u_neg, 'v_pos': v_pos, 'v_neg': v_neg}


def _half_extents_from_source(engine, axis, source, inset_mm):
    """
    Cover-inset half-width/half-depth for a column geometry `source`
    (from _resolve_column_geometry_source) at the given inset — the
    analytical-vs-faces counterpart to _cross_section_half_extents,
    dispatching on source['kind'] so callers don't need to know which
    path was used. For 'analytical', this is a plain subtraction
    (b_mm/2 - inset_mm) since there are no real faces to offset from;
    for 'faces', delegates to the existing _cross_section_half_extents
    unchanged.

    Returns:
        (half_w_mm, half_d_mm) — may be <= 0 if inset_mm exceeds the
        column's own half-dimension (a genuine "doesn't fit" case,
        left for the caller's own existing warnings check, same as
        the face-based path already produces).
    """
    if source['kind'] == 'analytical':
        return (source['b_mm'] / 2.0 - inset_mm, source['h_mm'] / 2.0 - inset_mm)
    return _cross_section_half_extents(
        engine, axis, source['u_pos'], source['u_neg'], source['v_pos'], source['v_neg'],
        source['u_dir'], source['v_dir'], inset_mm)


def detect_column_geometry(doc, host):
    """
    PHASE 3.4 item 4 — best-effort read of a column host's REAL
    cross-section, for the UI's PREVIEW only (this does NOT change
    what rebar generation itself supports — build_column_reinforcement
    remains rectangular-only, per this module's own SCOPE note at the
    top of the file; a circular host still raises ValueError there).

    PHASE 3.5.6 item 1 — ANALYTICAL detection is now tried FIRST: a
    "Diameter" (circular) or "b"+"h" (rectangular) TYPE parameter read
    by NAME — the same names Revit's own out-of-the-box round/
    rectangular structural column families use. These are the
    column's own AUTHORED dimensions, immune to Join Geometry altering
    the reported Solid's faces (a floor/beam joined to the column can
    split or merge its side faces, breaking every geometry-based
    detection below) — same reasoning already applied to the column's
    vertical extent (get_column_axis's Base/Top Level+Offset).

    Only when NEITHER of those parameters is found does this fall back
    to GEOMETRY, in order:
      1. A genuinely CIRCULAR column — a DB.CylindricalFace among the
         host's own solid faces (get_host_faces/_column_faces only
         ever look at PLANAR faces, so this inspects the raw solid
         directly) — reporting its real diameter.
      2. This module's own rectangular face classification
         (_column_faces + _cross_section_half_extents, with a ZERO
         inset — the raw concrete section, not a cover-inset one,
         since this is for drawing the OUTLINE, not placing bars).
      3. A purely GEOMETRIC read for a round column modelled as a
         many-sided FACETED approximation rather than a true
         DB.CylindricalFace (fails #1 above) with MORE than 4 planar
         side faces (fails #2 above) — that combination is itself the
         signature of a faceted circle; diameter estimated from the
         host's own bounding box (average of X/Y extents). No
         parameter names, no language dependency — a genuine last
         resort for a family with unreadable/absent Diameter/b/h
         parameters AND no true cylindrical face.

    Args:
        doc  (DB.Document)
        host (DB.Element): the column instance.

    Returns:
        {'shape': 'circle', 'diameter_mm': float} or
        {'shape': 'rect', 'width_mm': float, 'depth_mm': float} or
        None if nothing resolves at all — the caller should fall back
        to an illustrative default.
    """
    diameter_mm = _lookup_length_param_mm(host, [u'Diameter', u'DIAMETER', u'diameter'])
    if diameter_mm is not None:
        return {'shape': 'circle', 'diameter_mm': diameter_mm}
    b_mm = _lookup_length_param_mm(host, [u'b', u'B'])
    h_mm = _lookup_length_param_mm(host, [u'h', u'H'])

    engine = _ensure_engine()
    cover_mgr = engine.CoverGeometryManager(doc, host)

    def _find_cylindrical_face_diameter_mm():
        if cover_mgr.solid is None:
            return None
        has_cylindrical_face = any(
            isinstance(face, DB.CylindricalFace) for face in cover_mgr.solid.Faces)
        if not has_cylindrical_face:
            return None
        # BUG FIX (2026-09-01, confirmed via a real traceback from the
        # user's own Revit session): CylindricalFace.Radius (and its
        # get_Radius() accessor) does NOT behave as a plain float in
        # this pythonnet binding — it resolves to an "indexer#" wrapper
        # object, and `radius_ft * 2.0` throws exactly the reported
        # error: "unsupported operand type(s) for *: 'indexer#' and
        # 'float'". This is why the earlier fix (which correctly
        # detected the column as circular) still produced ZERO rebar
        # with no visible error until diagnostic hardening surfaced the
        # traceback. Sidestepping that fragile API surface entirely: a
        # column's bounding box IS its diameter on both horizontal axes
        # for a genuinely circular section (X-extent == Y-extent ==
        # diameter, exactly) — the SAME bounding-box arithmetic this
        # function's own "faceted circle" last-resort branch below
        # already uses; only reached here once a true CylindricalFace
        # confirms the column really is round (a rectangular column's
        # bbox is not its diameter, and never reaches this branch).
        bbox = host.get_BoundingBox(None)
        if bbox is None:
            return None
        width_ft = bbox.Max.X - bbox.Min.X
        depth_ft = bbox.Max.Y - bbox.Min.Y
        if width_ft <= 0 or depth_ft <= 0:
            return None
        return (width_ft + depth_ft) / 2.0 * _MM_PER_FT

    # PHASE F2.5/circular-bug-fix (2026-09-01) — a bare 'b' with no 'h'
    # is AMBIGUOUS by name alone: Phase 3.5.9 treated it as a SQUARE
    # section (h_mm = b_mm) to fix square columns being misdetected as
    # circular, but this silently broke the OPPOSITE case — Revit's own
    # stock "Concrete Round" family exposes ONLY 'b' (its diameter),
    # with no 'h' and no "Diameter" parameter at all, and got routed
    # into the rectangular path as a false "square" (live bug, confirmed
    # against a real project: reinforced as a 600x600 square instead of
    # a 600mm-diameter circle). Fix: when 'h' is absent, check the
    # SOLID's real geometry for a true CylindricalFace BEFORE assuming
    # square — geometry can't lie about which shape the column actually
    # is, unlike a bare parameter name. Falls back to the old "h=b,
    # square" assumption only when no CylindricalFace is found either
    # (a genuinely square/rectangular family that also only authors
    # 'b') — that original Phase 3.5.9 case is unaffected.
    if b_mm is not None and h_mm is None:
        cyl_diameter_mm = _find_cylindrical_face_diameter_mm()
        if cyl_diameter_mm is not None:
            return {'shape': 'circle', 'diameter_mm': cyl_diameter_mm}
        h_mm = b_mm
    if b_mm is not None and h_mm is not None:
        return {'shape': 'rect', 'width_mm': b_mm, 'depth_mm': h_mm}

    cyl_diameter_mm = _find_cylindrical_face_diameter_mm()
    if cyl_diameter_mm is not None:
        return {'shape': 'circle', 'diameter_mm': cyl_diameter_mm}

    try:
        axis = get_column_axis(host)
        u_pos, u_neg, v_pos, v_neg, u_dir, v_dir = _column_faces(cover_mgr, axis.Direction)
        half_w_mm, half_d_mm = _cross_section_half_extents(
            engine, axis, u_pos, u_neg, v_pos, v_neg, u_dir, v_dir, 0.0)
        return {'shape': 'rect', 'width_mm': half_w_mm * 2.0, 'depth_mm': half_d_mm * 2.0}
    except ValueError:
        # Last resort — see docstring item 3: more than 4 planar side
        # faces with no true CylindricalFace is the geometric signature
        # of a faceted circle.
        sides = [f for f in cover_mgr.faces if abs(f.normal.Z) < 0.3]
        if len(sides) > 4:
            bbox = host.get_BoundingBox(None)
            if bbox is not None:
                width_ft = bbox.Max.X - bbox.Min.X
                depth_ft = bbox.Max.Y - bbox.Min.Y
                if width_ft > 0 and depth_ft > 0:
                    return {'shape': 'circle',
                            'diameter_mm': (width_ft + depth_ft) / 2.0 * _MM_PER_FT}
        return None


# ══════════════════════════════════════════════════════════════════════════
# Vertical (longitudinal) bars — perimeter layout
# ══════════════════════════════════════════════════════════════════════════

def distribute_bar_count(total_count, half_w_mm, half_d_mm):
    """
    PHASE 3 — converts a single TOTAL desired vertical-bar count (the
    UI's own "Quantity" field — simpler than asking for per-edge n_u/n_v
    directly) into (n_u, n_v) for _perimeter_positions, distributed
    proportionally to each edge's own length so a non-square column
    gets more bars on its longer edges.

    DISCLOSED SIMPLIFICATION: _perimeter_positions' actual distinct-
    point count is 2*n_u + 2*n_v - 4 (shared corners), so the realised
    bar count matches total_count only approximately after rounding —
    a real column's bar layout is inherently an engineering choice with
    more valid conventions than "corners plus evenly spaced edges", so
    this does not attempt exact-count matching.

    Args:
        total_count (int): desired total vertical bar count, minimum 4.
        half_w_mm, half_d_mm (float): cross-section half-extents, mm —
                    used only for the proportional split, not corrected
                    for cover here (callers pass whichever half-extents
                    are relevant to their own use).

    Returns:
        (n_u, n_v) — both >= 2.
    """
    total_count = max(4, int(total_count))
    pair_sum = total_count / 2.0 + 2.0  # solves n_u + n_v from total = 2nu + 2nv - 4
    edge_total = half_w_mm + half_d_mm
    if edge_total <= 0:
        n_u = n_v = max(2, int(round(pair_sum / 2.0)))
    else:
        n_u = max(2, int(round(pair_sum * half_w_mm / edge_total)))
        n_v = max(2, int(round(pair_sum - n_u)))
    return n_u, n_v


def _perimeter_positions(half_w_mm, half_d_mm, n_u, n_v):
    """
    (u, v) offsets (mm, from the cross-section centre) of bars placed
    around a rectangular perimeter: n_u bars evenly spaced along each
    of the two u-edges (top/bottom, at v = +-half_d), n_v bars evenly
    spaced along each of the two v-edges (left/right, at u = +-half_w)
    — corner positions are shared between an edge and its neighbour,
    so each corner is emitted exactly once, not duplicated.

    n_u and n_v each must be >= 2 (every rectangular layout needs at
    least the 4 corner bars); requesting fewer raises ValueError.

    Args:
        half_w_mm, half_d_mm (float): cross-section half-extents, mm.
        n_u (int): bars per u-edge (top and bottom), corners included.
        n_v (int): bars per v-edge (left and right), corners included.

    Returns:
        list[(float, float)] — (u, v) positions, mm, corners
        deduplicated.
    """
    if n_u < 2 or n_v < 2:
        raise ValueError(u'n_u and n_v must each be >= 2 (a rectangular '
                          u'perimeter needs at least its 4 corners).')

    def _edge(lo, hi, n):
        if n == 1:
            return [(lo + hi) / 2.0]
        step = (hi - lo) / float(n - 1)
        return [lo + i * step for i in range(n)]

    us = _edge(-half_w_mm, half_w_mm, n_u)
    vs = _edge(-half_d_mm, half_d_mm, n_v)

    positions = []
    seen = set()

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


def compute_vertical_bar_lines(doc, host, cover_mm, n_u, n_v, bar_diameter_mm=16.0):
    """
    Generate perimeter vertical bar Lines for a rectangular column,
    running the full length of the column's centreline, offset inward
    from each face by cover_mm + bar_diameter_mm/2, and distributed
    around the perimeter via _perimeter_positions.

    Args:
        doc              (DB.Document)
        host             (DB.Element): the column.
        cover_mm         (float): nominal cover, mm — applied to all 4
                         faces alike.
        n_u, n_v         (int): bars per edge in each cross-section
                         direction — see _perimeter_positions.
        bar_diameter_mm  (float): longitudinal bar diameter, mm.

    Returns:
        list[DB.Line]

    Raises:
        ValueError: from get_column_axis / _column_faces /
        _perimeter_positions.
    """
    engine = _ensure_engine()
    axis = get_column_axis(host)
    cover_mgr = engine.CoverGeometryManager(doc, host)
    source = _resolve_column_geometry_source(host, axis, cover_mgr)
    u_dir, v_dir = source['u_dir'], source['v_dir']

    inset_mm = cover_mm + bar_diameter_mm / 2.0
    half_w_mm, half_d_mm = _half_extents_from_source(engine, axis, source, inset_mm)

    p_start = axis.GetEndPoint(0)
    p_end = axis.GetEndPoint(1)
    bars = []
    for u_mm, v_mm in _perimeter_positions(half_w_mm, half_d_mm, n_u, n_v):
        offset = u_dir.Multiply(u_mm / _MM_PER_FT) + v_dir.Multiply(v_mm / _MM_PER_FT)
        bars.append(DB.Line.CreateBound(p_start + offset, p_end + offset))
    return bars


def plan_inward_dirs(centre, points, hand, facing, circular):
    """Unit plan vectors pointing into the section from each bar: radial, or face-normal (diagonal at corners)."""
    offsets = [DB.XYZ(p.X - centre.X, p.Y - centre.Y, 0.0) for p in points]
    max_u = max([abs(v.DotProduct(hand)) for v in offsets] or [0.0])
    max_v = max([abs(v.DotProduct(facing)) for v in offsets] or [0.0])
    tol_ft = 5.0 / _MM_PER_FT

    inward_dirs = []
    for v in offsets:
        radial = DB.XYZ(-v.X, -v.Y, 0.0)
        if circular:
            inward = radial
        else:
            u, w = v.DotProduct(hand), v.DotProduct(facing)
            inward = DB.XYZ(0.0, 0.0, 0.0)
            if abs(u) > max_u - tol_ft:
                inward = inward - hand.Multiply(1.0 if u > 0 else -1.0)
            if abs(w) > max_v - tol_ft:
                inward = inward - facing.Multiply(1.0 if w > 0 else -1.0)
            if inward.GetLength() < 1e-9:
                inward = radial
        inward_dirs.append(inward.Normalize() if inward.GetLength() > 1e-9 else DB.XYZ.BasisX)
    return inward_dirs


def column_vertical_plan_layout(doc, host, cover_mm, bar_diameter_mm, bar_count,
                                stirrup_diameter_mm):
    """
    Plan positions (z = 0) of the verticals build_column_reinforcement would
    place in this column with these Columns-tab values, and their inward
    directions — used to put footing dowels exactly where each future
    vertical will be (T2.15b, 2026-09-29).

    Returns {'centre': DB.XYZ, 'points': list[DB.XYZ], 'inward': list[DB.XYZ]}.
    Raises ValueError when the bars do not fit inside the section.
    """
    engine = _ensure_engine()
    axis = get_column_axis(host)
    origin = axis.GetEndPoint(0)
    centre = DB.XYZ(origin.X, origin.Y, 0.0)
    inset_mm = cover_mm + stirrup_diameter_mm + bar_diameter_mm / 2.0

    geom = detect_column_geometry(doc, host)
    circular = geom is not None and geom.get('shape') == 'circle'
    points = []
    if circular:
        radius_mm = geom['diameter_mm'] / 2.0 - inset_mm
        if radius_mm <= 0:
            raise ValueError(u'Column bars do not fit inside the circular section.')
        n = max(3, int(bar_count))
        for i in range(n):
            theta = 2.0 * math.pi * i / n
            points.append(DB.XYZ(centre.X + radius_mm * math.cos(theta) / _MM_PER_FT,
                                 centre.Y + radius_mm * math.sin(theta) / _MM_PER_FT, 0.0))
        hand, facing = DB.XYZ.BasisX, DB.XYZ.BasisY
    else:
        source = _resolve_column_geometry_source(host, axis, engine.CoverGeometryManager(doc, host))
        hand, facing = source['u_dir'], source['v_dir']
        inset_mm += engine.link_corner_extra_inset_mm(bar_diameter_mm, stirrup_diameter_mm)
        half_w_mm, half_d_mm = _half_extents_from_source(engine, axis, source, inset_mm)
        if half_w_mm <= 0 or half_d_mm <= 0:
            raise ValueError(u'Column bars do not fit inside the section.')
        n_u, n_v = distribute_bar_count(bar_count, half_w_mm, half_d_mm)
        for u_mm, v_mm in _perimeter_positions(half_w_mm, half_d_mm, n_u, n_v):
            points.append(centre + hand.Multiply(u_mm / _MM_PER_FT) + facing.Multiply(v_mm / _MM_PER_FT))

    return {'centre': centre, 'points': points,
            'inward': plan_inward_dirs(centre, points, hand, facing, circular)}


def build_column_foundation_starters(doc, host, bar_points, main_dia_mm, starter_dia_mm,
                                      anchor_length_mm, splice_length_mm,
                                      foundation_cover_mm, search_depth_mm=3000.0):
    """
    PHASE F7.18 — L-shaped starters from the foundation below into the column.

    One starter per main vertical bar (bar_points: the plan start points of
    the column's own verticals, read from the Rebar elements just created),
    contact-lapped on the inner side of its vertical so it stays inside the
    links, with its foot pointing outwards (user decision 2026-09-29). Inward
    is radial for a circular column and perpendicular to the nearest face
    (diagonal at a corner) for a rectangular one. See
    rebar_engine.build_contact_starters for the return value.
    """
    engine = _ensure_engine()
    bbox = host.get_BoundingBox(None)
    centre = DB.XYZ((bbox.Min.X + bbox.Max.X) / 2.0, (bbox.Min.Y + bbox.Max.Y) / 2.0, 0.0)
    base_z_ft = min(p.Z for p in bar_points) if bar_points else bbox.Min.Z

    geom = detect_column_geometry(doc, host)
    circular = geom is not None and geom.get('shape') == 'circle'
    try:
        hand = DB.XYZ(host.HandOrientation.X, host.HandOrientation.Y, 0.0).Normalize()
        facing = DB.XYZ(host.FacingOrientation.X, host.FacingOrientation.Y, 0.0).Normalize()
    except Exception:
        hand, facing = DB.XYZ.BasisX, DB.XYZ.BasisY

    inward_dirs = plan_inward_dirs(centre, bar_points, hand, facing, circular)

    return engine.build_contact_starters(
        doc, bar_points, inward_dirs, base_z_ft, main_dia_mm, starter_dia_mm,
        anchor_length_mm, splice_length_mm, foundation_cover_mm,
        search_depth_ft=search_depth_mm / _MM_PER_FT)


# ══════════════════════════════════════════════════════════════════════════
# Esperas / dowels (lap extension at the column head)
# ══════════════════════════════════════════════════════════════════════════

def default_lap_length_mm(bar_diameter_mm, multiplier=40.0, std=None,
                           in_compression=False, pct_lapped=100.0, good_bond=True):
    """
    Rule-of-thumb lap ("empalme") length for a vertical bar splicing
    into the column above: bar_diameter_mm * multiplier. multiplier
    defaults to 40 (a common order-of-magnitude EC2 anchorage-length
    multiplier for good bond conditions) but is NOT a National-Annex-
    verified design value — caller should override with a project- or
    code-specific value where precision matters.

    PHASE F2 — compat wrapper: when `std` (a resolved
    nosa_utils.standards profile dict) is supplied, delegates to
    standards.lap_length_mm(std, bar_diameter_mm, in_compression,
    pct_lapped) instead, so a caller that has resolved a normativa
    gets that normativa's real lap factors. Every existing caller that
    omits `std` (the default, None) is completely unaffected — same
    bar_diameter_mm * multiplier as before this phase.
    """
    # Column splices and starters lap every bar at one section: 100 % lapped (alpha6 1.5).
    if std is not None:
        return standards.lap_length_mm(std, bar_diameter_mm, in_compression, pct_lapped, good_bond)
    return max(bar_diameter_mm * multiplier, 15.0 * bar_diameter_mm, 300.0)


def extend_bar_for_lap(line, extension_mm, direction, at_start=False, at_end=False):
    """
    Extend a vertical bar Line by extension_mm at its start and/or end,
    along `direction` — the "esperas"/dowel projection left protruding
    above (or below) the column for the next storey's bars to lap
    against.

    Args:
        line          (DB.Line): the bar to extend.
        extension_mm  (float): lap extension length, mm — see
                      default_lap_length_mm.
        direction     (DB.XYZ): unit vector the extension travels along
                      at the chosen end(s) (e.g. DB.XYZ.BasisZ pointing
                      up, for a dowel above the column head).
        at_start, at_end (bool): which end(s) to extend.

    Returns:
        list[DB.Curve] — the original line plus one Line segment per
        extended end, in order (start-extension, original, end-
        extension) where applicable.
    """
    ext_ft = extension_mm / _MM_PER_FT
    direction = direction.Normalize()
    chain = []
    if at_start:
        p0 = line.GetEndPoint(0)
        ext_p0 = p0 - direction.Multiply(ext_ft)
        chain.append(DB.Line.CreateBound(ext_p0, p0))
    chain.append(line)
    if at_end:
        p1 = line.GetEndPoint(1)
        ext_p1 = p1 + direction.Multiply(ext_ft)
        chain.append(DB.Line.CreateBound(p1, ext_p1))
    return chain


# ══════════════════════════════════════════════════════════════════════════
# Multi-story splitting & cranked laps (Phase 3.2)
# ══════════════════════════════════════════════════════════════════════════

_OST_FLOORS_TOL_FT = 0.01
_MIN_SPLIT_MARGIN_MM = 100.0  # PHASE 3.4 item 1 — see find_floor_split_elevations_ft
_MIN_SPLIT_MARGIN_FT = _MIN_SPLIT_MARGIN_MM / _MM_PER_FT


def find_floor_split_elevations_ft(doc, axis):
    """
    PHASE 3.2 item 1 (hardened — PHASE 3.4) — detect every OST_Floors
    element the column's vertical axis physically passes through, so a
    multi-story column (one instance spanning several levels) gets a
    mandatory bar-splice point at each floor it crosses instead of one
    continuous line the full column height, and gets a proper
    starter/lap at each of those points rather than only at the
    column's own top.

    DISCLOSED SIMPLIFICATION: a floor's own footprint is tested via its
    GLOBAL BOUNDING BOX in plan (does its XY range contain the column
    axis's own XY position), not its exact polygon — adequate for the
    common case of a column landing within a floor's rectangular
    extent, matching every other bbox-based host query in this
    project; a column sitting exactly on a floor's own irregular notch
    or edge may be missed or falsely matched.

    PHASE 3.4 item 1 FIX — a live ground-floor crash traced partly to a
    floor whose own top sits VERY close to the column's own base (a
    slab the column's base offset embeds slightly into, or simple
    axis/geometry rounding — see get_column_axis's own Phase 3.4 fix):
    the old exclusion band (_OST_FLOORS_TOL_FT, 3mm) was tight enough
    to let a near-base floor through as a "genuine" split, producing a
    razor-thin first storey segment that Rebar.CreateFromCurves can
    fail on with an opaque Internal Error. The exclusion band at BOTH
    ends is now _MIN_SPLIT_MARGIN_MM (100mm) — any floor whose own top
    lands within 100mm of the column's own base OR top is treated as
    that end itself (not a genuine mid-height split), guaranteeing
    every storey segment this produces is at least 100mm tall.

    Args:
        doc  (DB.Document)
        axis (DB.Line): the column's centreline, from get_column_axis —
             assumed vertical (this module's whole SCOPE is a straight,
             vertical column), so a floor's split elevation only needs
             the axis's own constant X/Y plus the floor's own Z.

    Returns:
        list[dict], sorted ascending by 'top_ft':
        {'top_ft': float, 'bottom_ft': float} — one per floor strictly
        between the axis's own base and top Z (at least
        _MIN_SPLIT_MARGIN_FT away from either), deduplicated (by
        top_ft) within _OST_FLOORS_TOL_FT. 'bottom_ft' is that SAME
        floor's own underside — see build_column_reinforcement's
        stirrup-zone splitting (Phase 3.4 item 2), which needs both.
        Empty for an ordinary single-story column that crosses no
        floor mid-height — the overwhelmingly common case, for which
        every function downstream of this one degrades to its
        original, pre-Phase-3.2 single-chain behaviour exactly.
    """
    p0 = axis.GetEndPoint(0)
    p1 = axis.GetEndPoint(1)
    z_lo, z_hi = min(p0.Z, p1.Z), max(p0.Z, p1.Z)
    x0, y0 = p0.X, p0.Y
    tol = _OST_FLOORS_TOL_FT
    margin = _MIN_SPLIT_MARGIN_FT

    collector = DB.FilteredElementCollector(doc).OfCategory(
        DB.BuiltInCategory.OST_Floors).WhereElementIsNotElementType()

    entries = []
    for floor in collector:
        bbox = floor.get_BoundingBox(None)
        if bbox is None:
            continue
        if not (bbox.Min.X - tol <= x0 <= bbox.Max.X + tol and
                bbox.Min.Y - tol <= y0 <= bbox.Max.Y + tol):
            continue
        floor_top_z = bbox.Max.Z
        if z_lo + margin < floor_top_z < z_hi - margin:
            entries.append({'top_ft': floor_top_z, 'bottom_ft': bbox.Min.Z})

    entries.sort(key=lambda e: e['top_ft'])
    deduped = []
    for e in entries:
        if not deduped or e['top_ft'] - deduped[-1]['top_ft'] > tol:
            deduped.append(e)
    return deduped


_OST_COLUMNS_TOL_FT = 0.05


def find_column_above(doc, host, elevation_ft, x0, y0, tol_ft=_OST_COLUMNS_TOL_FT):
    """
    PHASE 3.3 item 1 — detect the OST_StructuralColumns instance that
    picks up immediately above a given elevation (a floor top, or this
    column's own top) at the same plan position, EXCLUDING `host`
    itself — the real-world "stacked columns, section reduces per
    storey" modelling convention, and the building block
    resolve_crank_offset_mm uses to derive a REAL crank amount instead
    of a fixed heuristic.

    Many real columns are instead modelled as ONE genuinely
    multi-story instance continuing straight through with no section
    change at all — in that case there is no DIFFERENT element to find
    here (only `host` itself occupies that space), so this returns
    None, and the caller (resolve_crank_offset_mm) correctly treats
    that as "no crank needed," matching the common continuous case.

    Args:
        doc           (DB.Document)
        host          (DB.Element or None): the LOWER column — excluded
                      from the search even if its own bbox happens to
                      still cover this elevation.
        elevation_ft  (float): the Z to search at (this instance's own
                      base should sit here, within tol_ft).
        x0, y0        (float): plan position to test containment
                      against (the lower column's own axis X/Y — see
                      find_floor_split_elevations_ft's own
                      bbox-containment disclosure, identical here).
        tol_ft        (float): matching tolerance, ft.

    Returns:
        DB.Element or None.
    """
    # PHASE 3.5.8 item 3 FIX — matching purely against bbox.Min.Z (the
    # candidate's SOLID geometry) missed a real column above whenever
    # Join Geometry with the floor/foundation at its own base notches
    # that solid short of its true modelled base — the exact same
    # class of problem get_column_axis's own Z-extent already had to
    # fix (Phase 3.5.7 item 2). Base Z now prefers the candidate's
    # AUTHORED Base Level + Offset (_base_top_z_ft_from_level_params,
    # immune to Join Geometry) and only falls back to bbox.Min.Z when
    # those parameters aren't readable — matching get_column_axis's own
    # established fallback order. The X/Y plan-containment check is
    # left on bbox unchanged: Join Geometry notches the Z extent at a
    # joint face, not the column's own footprint in plan.
    collector = DB.FilteredElementCollector(doc).OfCategory(
        DB.BuiltInCategory.OST_StructuralColumns).WhereElementIsNotElementType()
    host_id = getattr(host, 'Id', None)
    for elem in collector:
        if host_id is not None and getattr(elem, 'Id', None) == host_id:
            continue
        bbox = elem.get_BoundingBox(None)
        if bbox is None:
            continue
        if not (bbox.Min.X - tol_ft <= x0 <= bbox.Max.X + tol_ft and
                bbox.Min.Y - tol_ft <= y0 <= bbox.Max.Y + tol_ft):
            continue
        level_extent = _base_top_z_ft_from_level_params(elem)
        base_z_ft = level_extent[0] if level_extent is not None else bbox.Min.Z
        if abs(base_z_ft - elevation_ft) <= tol_ft:
            return elem
    return None


def _resolve_upper_half_extents(doc, host, elevation_ft, x0, y0, engine, bar_inset_mm,
                                 tol_ft=_OST_COLUMNS_TOL_FT):
    """
    (upper_half_w_mm, upper_half_d_mm) for the column find_column_above
    finds at `elevation_ft`, computed with the SAME bar_inset_mm the
    lower column's own bars use (this module has no access to the
    upper column's own rebar parameters at this stage — a disclosed
    approximation; if bar/cover/stirrup sizes genuinely differ between
    storeys, the derived crank offset will be approximate, not exact),
    or None if no distinct column continues there, or if it isn't a
    rectangular column this module can read (_column_faces raises).
    """
    upper_host = find_column_above(doc, host, elevation_ft, x0, y0, tol_ft)
    if upper_host is None:
        return None
    try:
        upper_axis = get_column_axis(upper_host)
        upper_cover_mgr = engine.CoverGeometryManager(doc, upper_host)
        upper_source = _resolve_column_geometry_source(upper_host, upper_axis, upper_cover_mgr)
        return _half_extents_from_source(engine, upper_axis, upper_source, bar_inset_mm)
    except ValueError:
        return None


def build_cranked_starter(seg_end_point, inward_dir, axis_dir, lap_length_mm,
                           crank_offset_mm, crank_slope=6.0):
    """
    PHASE 3.2 item 1 — the crank-then-straight continuation of a
    vertical bar above a split point (a floor top, or the column's own
    top), for the "Use Cranked Laps (1:6 slope)" UI option: a short
    diagonal segment shifts the bar INWARD from its own perimeter
    position by crank_offset_mm while rising crank_slope times that (a
    "1:6" slope is 1 unit of lateral shift per 6 units of rise), then a
    straight vertical segment continues for the remaining lap_length_mm
    at the new, cranked position — the projecting starter the storey
    above laps against, moved to clear the interior side of the
    reinforcement above while respecting cover.

    `inward_dir` MUST be a CONSTANT unit vector for the whole face/edge
    this bar belongs to (that face's own inward normal, e.g. -v_dir for
    every bar on the v=+half_d edge) rather than computed per-bar
    toward the column's centroid — every bar on the same face then
    cranks by the IDENTICAL translation, which is what lets a whole
    face still be grouped into ONE Rebar Set
    (build_column_reinforcement's _face_groups) even with cranking on;
    a per-bar "toward centroid" direction would make each bar's crank
    vector different and break Set propagation's pure-translation
    requirement.

    Args:
        seg_end_point    (DB.XYZ): the bar's position AT the split
                         elevation, before cranking.
        inward_dir       (DB.XYZ): unit vector, this bar's own face's
                         inward normal.
        axis_dir         (DB.XYZ): unit vector, the column's (vertical)
                         axis direction.
        lap_length_mm    (float): straight lap length above the crank,
                         mm — see default_lap_length_mm.
        crank_offset_mm  (float): lateral shift, mm, along inward_dir —
                         POSITIVE shifts inward (the normal case, the
                         column above is the same size or smaller);
                         NEGATIVE shifts OUTWARD (the column above is
                         actually LARGER on this axis) — either way the
                         rise is always upward at crank_slope:1. See
                         resolve_crank_offset_mm for how this is
                         normally derived from the REAL column above,
                         rather than an assumed value.
        crank_slope      (float): the "1:N" slope's N — units of rise
                         per unit of lateral shift. Defaults to 6 (the
                         requested "1:6").

    Returns:
        list[DB.Line]: [crank_diagonal, straight_lap] — TWO segments,
        meant to be appended after the bar's own main segment (does
        NOT include it).
    """
    crank_offset_ft = crank_offset_mm / _MM_PER_FT
    rise_ft = crank_slope * abs(crank_offset_ft)
    lap_ft = lap_length_mm / _MM_PER_FT

    # PHASE 3.5.2 item 3 FIX — this used to SUBTRACT inward_dir here,
    # which for a POSITIVE crank_offset_mm (the common case: the
    # column above is the same size or smaller — see
    # resolve_crank_offset_mm) shifted the crank point OUTWARD, past
    # the smaller column's own face, exactly backwards from this
    # function's own documented "POSITIVE shifts inward" contract.
    # That is what a real Rebar.CreateFromCurves "Internal Error" on
    # cranked laps would look like: the bar's cranked segment ending
    # up outside the column above. Corrected to ADD inward_dir.
    crank_top = (seg_end_point + axis_dir.Multiply(rise_ft)
                 + inward_dir.Multiply(crank_offset_ft))
    lap_top = crank_top + axis_dir.Multiply(lap_ft)
    return [DB.Line.CreateBound(seg_end_point, crank_top),
            DB.Line.CreateBound(crank_top, lap_top)]


def resolve_crank_offset_mm(doc, host, axis, elevation_ft, edge_dir_key,
                             engine, bar_inset_mm, lower_half_w_mm, lower_half_d_mm,
                             tol_ft=_OST_COLUMNS_TOL_FT):
    """
    PHASE 3.3 item 1 — the REAL crank offset for one column face at one
    split elevation, derived from the ACTUAL column found above (see
    find_column_above) instead of an assumed constant: 0.0 if the SAME
    column continues there (no distinct instance found — the common
    "genuinely multi-story, one continuous instance" case, per the
    user's own clarification: no crank is needed when nothing above
    actually differs), otherwise the real difference between this
    column's own half-extent and the column-above's own half-extent,
    along whichever local axis this face's crank travels (v_dir's own
    axis for a 'u' face, u_dir's for a 'v' face — i.e. the axis
    PERPENDICULAR to the face, matching build_cranked_starter's
    inward_dir convention).

    Args:
        doc, host            as elsewhere — host is the LOWER column,
                             excluded from the search.
        axis                 (DB.Line): the lower column's centreline.
        elevation_ft         (float): the split (or the lower column's
                             own top) to search for a column above.
        edge_dir_key         ('u' or 'v'): which face group this is —
                             see _face_groups.
        engine               (module): rebar_engine, from
                             _ensure_engine().
        bar_inset_mm         (float): the SAME inset the lower column's
                             own bars use — see
                             _resolve_upper_half_extents's own
                             disclosure on why the upper column is
                             measured with this same value.
        lower_half_w_mm, lower_half_d_mm (float): the LOWER column's
                             own already-computed half-extents.
        tol_ft               (float): see find_column_above.

    Returns:
        float, mm — 0.0 if no distinct column is found above (no crank
        needed), otherwise lower_half - upper_half on the relevant
        axis (may be NEGATIVE if the column above is actually LARGER
        there — build_cranked_starter handles that as an outward
        crank, still rising at the same slope).
    """
    p0 = axis.GetEndPoint(0)
    upper = _resolve_upper_half_extents(
        doc, host, elevation_ft, p0.X, p0.Y, engine, bar_inset_mm, tol_ft)
    if upper is None:
        return 0.0
    upper_half_w_mm, upper_half_d_mm = upper
    if edge_dir_key == 'u':
        return lower_half_d_mm - upper_half_d_mm
    return lower_half_w_mm - upper_half_w_mm


def _merge_collinear_chain(chain, tol=1e-9):
    """
    PHASE 3.5.9 item 2 FIX — collapses consecutive DB.Line segments in
    `chain` that are COLLINEAR (parallel direction, sharing an
    endpoint) into a single Line. Telemetry confirmed the live
    "CreateFromCurves returned None" failure: a straight starter/lap
    extension (offset_mm == 0.0, no section change above — the common
    case) built the chain as [main_line, extension_line], two segments
    running in the exact same direction with a 0-degree "kink" at their
    shared point. Rebar.CreateFromCurves rejects that as an Internal
    Error even though the shape IS geometrically a single straight bar
    — Revit's own curve-chain validation apparently requires a genuine
    direction change at every internal vertex. Merging collinear
    neighbours here (applied uniformly, not just the offset==0.0 case)
    fixes both the cranked-laps-with-no-offset branch AND the plain
    (use_cranked_laps=False) extend_bar_for_lap path below, which has
    the identical two-collinear-segments shape.

    Args:
        chain (list[DB.Line]): ordered, head-to-tail curve chain — only
              ever Line segments in this module's own usage (radial/
              perimeter vertical bars and their straight lap
              extensions; the cranked diagonal is NOT collinear with
              the segment before it, so it is never merged away).
        tol   (float): 1 - dot(unit directions) below which two
              consecutive segments are treated as collinear.

    Returns:
        list[DB.Line] — same shape, with any collinear run collapsed
        to its own single Line spanning the run's own start/end points.
    """
    if len(chain) < 2:
        return chain
    merged = [chain[0]]
    for seg in chain[1:]:
        prev = merged[-1]
        if prev.Direction.DotProduct(seg.Direction) > 1.0 - tol:
            merged[-1] = DB.Line.CreateBound(prev.GetEndPoint(0), seg.GetEndPoint(1))
        else:
            merged.append(seg)
    return merged


def build_story_segment_chains(axis, offset, split_elevations_ft, lap_length_mm,
                                include_starter_bars, use_cranked_laps,
                                inward_dir, crank_offset_fn, crank_slope=6.0):
    """
    PHASE 3.2 item 1 (crank offset made per-split — PHASE 3.3) — ONE
    vertical bar position's full set of per-story curve chains: splits
    the bar at every intersecting floor's top elevation
    (split_elevations_ft) instead of returning a single base-to-top
    line, so a column spanning several storeys gets one properly
    lapped bar per storey instead of one continuous bar the length of
    the whole column (the previous behaviour, which is also what
    produced starters projecting an unbounded distance beyond a single
    storey's own solid). Every INTERMEDIATE split ALWAYS gets its own
    starter regardless of include_starter_bars — a multi-storey bar
    MUST lap at every storey join to physically continue upward at
    all; include_starter_bars only controls whether the column's OWN
    final top (the last segment) also gets one, for the storey above
    THIS column entirely.

    Args:
        axis                  (DB.Line): column centreline.
        offset                (DB.XYZ): this bar's horizontal offset
                              from the axis, in FEET (already scaled —
                              see compute_vertical_bar_lines's own use
                              of the same pattern).
        split_elevations_ft   (list[float]): from
                              find_floor_split_elevations_ft.
        lap_length_mm         (float): starter/dowel lap length at
                              every split AND at the column's own top
                              (if include_starter_bars).
        include_starter_bars  (bool): whether the column's OWN top also
                              gets a starter.
        use_cranked_laps      (bool): if True, every starter cranks
                              first via build_cranked_starter, using
                              crank_offset_fn to resolve HOW MUCH at
                              each point; if False, a plain straight
                              extension via extend_bar_for_lap,
                              unchanged from before Phase 3.2.
        inward_dir            (DB.XYZ): this bar's own face's inward
                              normal — only used if use_cranked_laps.
        crank_offset_fn       (callable or None): called as
                              crank_offset_fn(elevation_ft) -> float
                              (mm) for the elevation of EACH point
                              needing a starter — lets the caller
                              resolve a DIFFERENT, REAL crank offset
                              per split (see resolve_crank_offset_mm);
                              a plain `lambda z: constant` reproduces
                              the old fixed-heuristic behaviour. Only
                              used if use_cranked_laps.
        crank_slope           (float): see build_cranked_starter.

    Returns:
        list[list[DB.Curve]] — one curve chain per storey segment,
        ordered bottom to top. A column crossing NO floors (the
        ordinary single-story case) returns exactly ONE chain,
        identical to this module's pre-Phase-3.2 single-chain output.
    """
    p_start = axis.GetEndPoint(0) + offset
    p_end = axis.GetEndPoint(1) + offset
    axis_dir = axis.Direction

    points = [p_start]
    for z in split_elevations_ft:
        points.append(DB.XYZ(p_start.X, p_start.Y, z))
    points.append(p_end)
    elevations_ft = [axis.GetEndPoint(0).Z] + list(split_elevations_ft) + [axis.GetEndPoint(1).Z]

    chains = []
    n_segments = len(points) - 1
    for i in range(n_segments):
        seg_start, seg_end = points[i], points[i + 1]
        is_last = (i == n_segments - 1)
        needs_starter = (not is_last) or include_starter_bars
        main_line = DB.Line.CreateBound(seg_start, seg_end)
        if not needs_starter:
            chains.append([main_line])
            continue
        if use_cranked_laps:
            offset_mm = crank_offset_fn(elevations_ft[i + 1])
            if offset_mm == 0.0:
                extra = extend_bar_for_lap(main_line, lap_length_mm, axis_dir, at_end=True)[1:]
            else:
                extra = build_cranked_starter(
                    seg_end, inward_dir, axis_dir, lap_length_mm, offset_mm, crank_slope)
        else:
            extra = extend_bar_for_lap(main_line, lap_length_mm, axis_dir, at_end=True)[1:]
        # PHASE 3.5.9 item 2 FIX — telemetry (Phase 3.5.8 item 6)
        # confirmed a straight lap extension produces two COLLINEAR
        # segments ([main_line, extension_line], zero-degree kink at
        # the join), which Rebar.CreateFromCurves rejects outright
        # ("CreateFromCurves returned None"). Merged here — see
        # _merge_collinear_chain's own docstring. This applies to BOTH
        # the offset_mm == 0.0 cranked branch above AND the plain
        # (use_cranked_laps=False) branch, which has the identical
        # collinear shape.
        chain = _merge_collinear_chain([main_line] + extra)
        chains.append(chain)
    return chains


def _edge_positions(lo, hi, n):
    if n == 1:
        return [(lo + hi) / 2.0]
    step = (hi - lo) / float(n - 1)
    return [lo + i * step for i in range(n)]


def _face_groups(half_w_mm, half_d_mm, n_u, n_v):
    """
    Partition _perimeter_positions' own position set into 4
    non-overlapping per-face groups — Phase 3.2 item 2's Rebar Set
    grouping needs each face's bars to propagate as ONE Set along that
    face's own edge direction, which requires knowing which face each
    position belongs to; a plain flat position list (what
    _perimeter_positions returns) does not carry that.

    PHASE 3.4 item 3 FIX — minimise the TOTAL number of Rebar Sets:
    whichever axis has MORE bars (n_u vs n_v) becomes the CORNER-OWNING
    "main" pair (both its edges get ALL n bars, corners included); the
    PERPENDICULAR pair only gets Sets for whatever's left STRICTLY
    INTERIOR on the other axis. This used to always give corners to
    the 'u' edges unconditionally — for an 8-bar column where n_u == 2
    (no interior bars beyond the corners) and n_v == 4 (2 genuine
    interior bars per edge), that produced FOUR 2-bar Sets (2 corner-
    only U-edges + 2 interior V-edges); swapping which axis owns the
    corners for THIS case collapses it to just TWO 4-bar Sets (the
    V-edges now own the corners AND their own interior bars; the
    U-edges have zero interior bars left, since n_u - 2 == 0, and are
    skipped entirely) — same 8 bars, half the Rebar Sets. A tie
    (n_u == n_v) keeps 'u' as the corner-owner, the original default,
    so a square column's behaviour is UNCHANGED from before this fix.

    Args:
        half_w_mm, half_d_mm (float): cross-section half-extents, mm.
        n_u, n_v              (int): bars per edge — see
                              _perimeter_positions (both >= 2).

    Returns:
        list of 4 dicts, one per face:
          {'positions': [(u_mm, v_mm), ...] ordered along the edge
                        from one end to the other (possibly EMPTY for
                        the perpendicular pair when its own axis has no
                        interior positions — the caller skips those),
           'edge_dir':  'u' or 'v' — which local axis this face's bars
                        are spaced along,
           'inward_sign': +1.0 or -1.0 — multiplies the OTHER local
                        axis's unit vector to get this face's own
                        inward normal (e.g. for a 'u' face,
                        inward = v_dir.Multiply(inward_sign)).}
    """
    if n_v > n_u:
        vs = _edge_positions(-half_d_mm, half_d_mm, n_v)
        us_full = _edge_positions(-half_w_mm, half_w_mm, n_u)
        us_interior = us_full[1:-1] if n_u > 2 else []
        return [
            {'positions': [(half_w_mm, v) for v in vs], 'edge_dir': 'v', 'inward_sign': -1.0},
            {'positions': [(-half_w_mm, v) for v in vs], 'edge_dir': 'v', 'inward_sign': 1.0},
            {'positions': [(u, half_d_mm) for u in us_interior], 'edge_dir': 'u', 'inward_sign': -1.0},
            {'positions': [(u, -half_d_mm) for u in us_interior], 'edge_dir': 'u', 'inward_sign': 1.0},
        ]

    us = _edge_positions(-half_w_mm, half_w_mm, n_u)
    vs_full = _edge_positions(-half_d_mm, half_d_mm, n_v)
    vs_interior = vs_full[1:-1] if n_v > 2 else []

    return [
        {'positions': [(u, half_d_mm) for u in us], 'edge_dir': 'u', 'inward_sign': -1.0},
        {'positions': [(u, -half_d_mm) for u in us], 'edge_dir': 'u', 'inward_sign': 1.0},
        {'positions': [(half_w_mm, v) for v in vs_interior], 'edge_dir': 'v', 'inward_sign': -1.0},
        {'positions': [(-half_w_mm, v) for v in vs_interior], 'edge_dir': 'v', 'inward_sign': 1.0},
    ]


# ══════════════════════════════════════════════════════════════════════════
# Stirrups — joint-zone density
# ══════════════════════════════════════════════════════════════════════════

def default_joint_zone_length_mm(larger_dim_mm, clear_height_mm, std=None):
    """
    Rule-of-thumb ("EC2-style") joint/confinement-zone length at each
    end of a column: max(larger cross-section dimension, clear
    height / 6, 450 mm). This is a common order-of-magnitude rule used
    for preliminary stirrup densification zones — it is NOT a
    National-Annex-verified design value; verify against the
    applicable code before construction.

    PHASE F2 — compat wrapper: when `std` (a resolved
    nosa_utils.standards profile dict) is supplied, its own
    stirrups.confinement_zone_factor_h replaces the fixed 1x multiplier
    on larger_dim_mm below (the clear_height_mm/6 and 450mm floors are
    unchanged). Omitting `std` (the default, None) reproduces exactly
    the pre-F2 formula.
    """
    factor = 1.0
    if std is not None:
        try:
            factor = std['stirrups']['confinement_zone_factor_h']
        except (KeyError, TypeError):
            factor = 1.0
    return max(larger_dim_mm * factor, clear_height_mm / 6.0, 450.0)


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


def generate_column_stirrup_positions(clear_height_mm, joint_zone_length_mm,
                                       dense_spacing_mm, normal_spacing_mm,
                                       start_offset_mm=50.0, end_offset_mm=50.0):
    """
    Stirrup positions (distance in mm from the column base) along the
    clear height, denser (dense_spacing_mm) within joint_zone_length_mm
    of each end, and at normal_spacing_mm in the middle span between
    the two joint zones.

    If the two joint zones would overlap or leave no room for a middle
    span (2 * joint_zone_length_mm >= usable clear height), the entire
    usable height is treated as one joint zone at dense_spacing_mm —
    the safer (denser) outcome, rather than raising an error, since a
    short column is exactly the case where confinement matters most
    end-to-end.

    Args:
        clear_height_mm       (float): column clear height, mm.
        joint_zone_length_mm  (float): confinement zone length at each
                               end, mm — see default_joint_zone_length_mm.
        dense_spacing_mm      (float): stirrup spacing within joint
                               zones, mm.
        normal_spacing_mm     (float): stirrup spacing in the middle
                               span, mm.
        start_offset_mm, end_offset_mm (float): clearance from each
                               end before the first / after the last
                               stirrup.

    Returns:
        list[float], sorted ascending, distances in mm from the base.
    """
    lo = start_offset_mm
    hi = clear_height_mm - end_offset_mm
    usable = hi - lo
    if usable <= 0:
        return []

    if 2 * joint_zone_length_mm >= usable:
        return _evenly_spaced(lo, hi, dense_spacing_mm)

    bottom_zone = _evenly_spaced(lo, lo + joint_zone_length_mm, dense_spacing_mm)
    top_zone = _evenly_spaced(hi - joint_zone_length_mm, hi, dense_spacing_mm)
    middle_lo = lo + joint_zone_length_mm
    middle_hi = hi - joint_zone_length_mm
    middle_zone = _evenly_spaced(middle_lo, middle_hi, normal_spacing_mm)

    positions = sorted(set(bottom_zone + middle_zone + top_zone))
    return positions


def build_stirrup_rectangle(axis, dist_mm, u_dir, v_dir, half_w_mm, half_d_mm):
    """
    A closed 4-segment rectangular stirrup curve chain, centred on the
    column axis at dist_mm from its start, in the horizontal plane
    spanned by u_dir/v_dir, sized by the given (already cover-inset)
    half-extents.

    Args:
        axis            (DB.Line): the column's centreline.
        dist_mm         (float): distance along the axis from its start.
        u_dir, v_dir    (DB.XYZ): the column's local cross-section axes
                        — see _column_faces.
        half_w_mm, half_d_mm (float): stirrup leg half-extents, mm.

    Returns:
        list[DB.Line] — 4 segments forming a closed rectangle.
    """
    p_start = axis.GetEndPoint(0)
    center = p_start + axis.Direction.Multiply(dist_mm / _MM_PER_FT)
    u = u_dir.Multiply(half_w_mm / _MM_PER_FT)
    v = v_dir.Multiply(half_d_mm / _MM_PER_FT)
    p1 = center - u - v
    p2 = center + u - v
    p3 = center + u + v
    p4 = center - u + v
    return [DB.Line.CreateBound(p1, p2), DB.Line.CreateBound(p2, p3),
            DB.Line.CreateBound(p3, p4), DB.Line.CreateBound(p4, p1)]


def generate_column_stirrup_zones(clear_height_mm, joint_zone_length_mm,
                                   dense_spacing_mm, normal_spacing_mm,
                                   densify_at_nodes, start_offset_mm=50.0,
                                   end_offset_mm=50.0):
    """
    PHASE 3 — the ZONE-boundary counterpart of
    generate_column_stirrup_positions: same joint-zone/middle-span
    reasoning, but returns each zone's own (start, end, spacing) so a
    caller can build ONE Rebar Set per zone (via build_stirrup_sets)
    instead of one individual stirrup per flat position.

    If densify_at_nodes is False, the entire usable height is ONE zone
    at normal_spacing_mm — a single Set, no joint-zone concept at all.
    If True: 3 zones (bottom joint, middle span, top joint) at
    dense_spacing_mm / normal_spacing_mm / dense_spacing_mm — UNLESS
    the two joint zones would overlap or leave no middle span (a short
    column), in which case the ENTIRE usable height becomes ONE zone at
    dense_spacing_mm — the safer (denser) outcome, matching
    generate_column_stirrup_positions' own established fallback.

    Args:
        clear_height_mm      (float): column clear height, mm.
        joint_zone_length_mm (float): confinement zone length at each
                              end, mm — see default_joint_zone_length_mm.
        dense_spacing_mm     (float): stirrup spacing within joint
                              zones, mm.
        normal_spacing_mm    (float): stirrup spacing in the middle
                              span (or the whole height if
                              densify_at_nodes is False), mm.
        densify_at_nodes     (bool): whether to split into 3 zones at
                              all.
        start_offset_mm, end_offset_mm (float): clearance from each end
                              before the first / after the last stirrup.

    Returns:
        list[{'start_mm': float, 'end_mm': float, 'spacing_mm': float}]
        — 1 zone (densify off, or a short column) or 3 zones (densify
        on), each with end_mm > start_mm. Empty list if there's no
        usable height at all.
    """
    lo = start_offset_mm
    hi = clear_height_mm - end_offset_mm
    usable = hi - lo
    if usable <= 0:
        return []

    if not densify_at_nodes or 2 * joint_zone_length_mm >= usable:
        spacing = dense_spacing_mm if (densify_at_nodes and 2 * joint_zone_length_mm >= usable) \
            else normal_spacing_mm
        return [{'start_mm': lo, 'end_mm': hi, 'spacing_mm': spacing}]

    # The joint zones keep their boundary links; the middle zone starts and
    # ends one normal spacing inside them so no link is placed twice (T2.20).
    zones = [{'start_mm': lo, 'end_mm': lo + joint_zone_length_mm, 'spacing_mm': dense_spacing_mm}]
    mid_lo = lo + joint_zone_length_mm + normal_spacing_mm
    mid_hi = hi - joint_zone_length_mm - normal_spacing_mm
    if mid_hi > mid_lo + 1.0:
        zones.append({'start_mm': mid_lo, 'end_mm': mid_hi, 'spacing_mm': normal_spacing_mm})
    zones.append({'start_mm': hi - joint_zone_length_mm, 'end_mm': hi, 'spacing_mm': dense_spacing_mm})
    return zones


def build_stirrup_sets(axis, u_dir, v_dir, half_w_mm, half_d_mm, zones):
    """
    PHASE 3 — one Rebar Set descriptor per zone from
    generate_column_stirrup_zones: a representative closed stirrup
    rectangle (build_stirrup_rectangle, at the zone's own start),
    propagated along the column's own axis direction across the zone's
    span at the zone's own spacing — the exact create_rebar_set /
    SetLayoutAsMaximumSpacing mechanism footing_rebar.build_side_rebar_set
    already proved live for a vertically-propagated closed rectangle;
    a column stirrup zone is the identical shape/propagation, just
    sized from the column's own faces.

    Args:
        axis         (DB.Line): the column's centreline.
        u_dir, v_dir (DB.XYZ): the column's local cross-section axes.
        half_w_mm, half_d_mm (float): stirrup leg half-extents, mm
                     (already cover + own-radius inset — see
                     _cross_section_half_extents).
        zones        (list[dict]): from generate_column_stirrup_zones.

    Returns:
        list[{'curves': [DB.Line,...] (4, closed), 'normal': DB.XYZ,
               'array_length_mm': float, 'spacing_mm': float,
               'style': 'StirrupTie'}]
    """
    sets = []
    for zone in zones:
        chain = build_stirrup_rectangle(axis, zone['start_mm'], u_dir, v_dir, half_w_mm, half_d_mm)
        sets.append({
            'curves': chain,
            'normal': axis.Direction,
            'array_length_mm': zone['end_mm'] - zone['start_mm'],
            'spacing_mm': zone['spacing_mm'],
            'style': 'StirrupTie',
        })
    return sets


def generate_storey_stirrup_zones(clear_height_mm, larger_dim_mm, dense_spacing_mm,
                                  normal_spacing_mm, densify_at_nodes, start_offset_mm=50.0,
                                  end_offset_mm=50.0, floor_bands_mm=None, joint_zone_length_mm=None,
                                  std=None, floor_offset_mm=50.0):
    """
    Link zones for a column that may cross floors: every storey segment
    between floor slabs is densified at both of its ends, so intermediate
    nodes get confinement above and below the slab (D3 / T4.6, 2026-09-30).
    Each segment's joint zone uses its own clear height unless
    joint_zone_length_mm is given. No link falls inside a slab.
    """
    bands = sorted(floor_bands_mm or [])
    edges = [0.0]
    for lo, hi in bands:
        edges += [lo, hi]
    edges.append(clear_height_mm)
    zones = []
    for i in range(0, len(edges), 2):
        seg_lo, seg_hi = edges[i], edges[i + 1]
        height = seg_hi - seg_lo
        if height <= 0:
            continue
        joint = joint_zone_length_mm or default_joint_zone_length_mm(larger_dim_mm, height, std=std)
        first, last = i == 0, i + 2 >= len(edges)
        for z in generate_column_stirrup_zones(
                height, joint, dense_spacing_mm, normal_spacing_mm, densify_at_nodes,
                start_offset_mm if first else floor_offset_mm,
                end_offset_mm if last else floor_offset_mm):
            zones.append({'start_mm': z['start_mm'] + seg_lo, 'end_mm': z['end_mm'] + seg_lo,
                          'spacing_mm': z['spacing_mm']})
    return zones


def _subtract_floor_bands(zones, floor_bands_mm):
    """
    PHASE 3.4 item 2 — cut every floor's own thickness OUT of a
    continuous stirrup zone list (from generate_column_stirrup_zones):
    real stirrups exist only within the column's own confinement
    zones, never running THROUGH a slab they pass behind — the
    previous stirrup engine treated the whole clear height as one
    column with no floor awareness at all (a disclosed limitation from
    Phase 3.2), unlike the vertical bars, which already split at each
    floor.

    Any zone that straddles a band is split into up to 2 pieces (the
    portion below the band, the portion above), each keeping the
    ORIGINAL zone's own spacing_mm; a zone entirely inside a band is
    dropped; a zone untouched by any band passes through unchanged.
    Bands are independent (this project's floors don't overlap each
    other in Z), so they can be applied one at a time.

    Args:
        zones           (list[dict]): {'start_mm','end_mm','spacing_mm'}
                        — see generate_column_stirrup_zones, relative
                        to the column's own base (mm from start_offset_mm).
        floor_bands_mm  (list[(float, float)]): (bottom_mm, top_mm)
                        pairs, SAME relative-to-base convention, one
                        per intersecting floor — see
                        build_column_reinforcement's own conversion
                        from find_floor_split_elevations_ft's absolute
                        feet values.

    Returns:
        list[dict], same shape as `zones`, sorted by start_mm, with
        every degenerate (end_mm <= start_mm) piece dropped.
    """
    result = list(zones)
    for (band_lo, band_hi) in floor_bands_mm:
        next_result = []
        for z in result:
            if band_hi <= z['start_mm'] or band_lo >= z['end_mm']:
                next_result.append(z)
                continue
            if band_lo > z['start_mm']:
                next_result.append({'start_mm': z['start_mm'], 'end_mm': min(band_lo, z['end_mm']),
                                     'spacing_mm': z['spacing_mm']})
            if band_hi < z['end_mm']:
                next_result.append({'start_mm': max(band_hi, z['start_mm']), 'end_mm': z['end_mm'],
                                     'spacing_mm': z['spacing_mm']})
        result = next_result
    result = [z for z in result if z['end_mm'] > z['start_mm']]
    result.sort(key=lambda z: z['start_mm'])
    return result


def build_crosstie_sets(axis, u_dir, v_dir, half_w_mm, half_d_mm, n_u, n_v, zones,
                         layout='all'):
    """
    PHASE 3.4/3.5 item 5 — normative interior crossties ("grapas"):
    once a column has bars BEYOND its 4 corners (any n_u or n_v > 2),
    those intermediate bars have no stirrup leg directly restraining
    them — a straight crosstie connecting each intermediate bar to its
    DIRECT MIRROR across the section (same coordinate on the OTHER
    axis, negated on its own) is the normative fix. One Rebar Set per
    (crosstie pair, Z zone) — the SAME zones the main stirrups use
    (post floor-band exclusion, see _subtract_floor_bands), so
    crossties share the identical spacing/densification and likewise
    never run through a floor's own thickness.

    PHASE 3.5 item 2 (live-Revit fix): returned as INDIVIDUAL bars, one
    per (pair, zone, spacing position) — NOT as a Rebar Set spec.
    Earlier phases tried create_rebar_set (a Set has no hook slot) +
    Rebar.SetHookTypeId afterwards to add normative 135°/90° hooks;
    live testing confirmed Revit rejects that combination outright
    ("hookTypeId is not valid") because SetHookTypeId only works on a
    bar whose RebarShape already defines a hook end, which a plain
    Set-propagated line does not. The mechanism that DOES work is
    baking the hooks in AT creation via
    RebarWrapper.create_from_curves(start_hook=, end_hook=) — proven
    live for footing dowels — so crossties trade Set-grouping for
    per-bar hook creation here specifically; this does not apply to
    verticals/stirrups, which keep the Set architecture untouched.

    PHASE 3.5 — layout='alternate' ties only every OTHER intermediate
    position per edge (position 0, 2, 4, ... of that edge's own
    interior list) instead of every one — a common, code-permitted
    relaxation for lightly-loaded columns; 'all' (the default) ties
    every intermediate bar.

    Args:
        axis                  (DB.Line): column centreline.
        u_dir, v_dir          (DB.XYZ): local cross-section axes.
        half_w_mm, half_d_mm  (float): cross-section half-extents, mm —
                              SAME convention as _face_groups /
                              _perimeter_positions (cover + bar-radius
                              inset already applied by the caller).
        n_u, n_v              (int): bars per edge — see
                              _perimeter_positions.
        zones                 (list[dict]): {'start_mm','end_mm',
                              'spacing_mm'} — post floor-band exclusion.
        layout                ('all' or 'alternate'): which intermediate
                              bars get tied — see above.

    Returns:
        {'crosstie_bars': [{'curve': DB.Line, 'normal': DB.XYZ}, ...],
         'interior_stirrup_sets': [{'curves','normal','array_length_mm',
                                     'spacing_mm','style'}, ...]}
        — PHASE 3.5.8 item 2: 'interior_stirrup_sets' (one closed loop
        per zone, Set-propagated exactly like the main stirrups) is
        used INSTEAD OF 'crosstie_bars' whenever neither axis has more
        than one genuinely interior position (see collapse_to_loop
        below); otherwise 'interior_stirrup_sets' is empty and
        'crosstie_bars' holds one entry per individual crosstie bar
        (pair x evenly-spaced Z position across ALL zones, same
        max-spacing convention as _evenly_spaced/
        SetLayoutAsMaximumSpacing elsewhere in this module — a Z shared
        by two adjacent zones' own boundary is emitted exactly ONCE,
        Phase 3.5.3 item 1). Both are empty if the column has no
        genuinely interior bars at all (n_u <= 2 and n_v <= 2 — only
        the 4 corners, nothing to tie).
    """
    us = _edge_positions(-half_w_mm, half_w_mm, n_u)
    vs = _edge_positions(-half_d_mm, half_d_mm, n_v)
    us_interior = us[1:-1] if n_u > 2 else []
    vs_interior = vs[1:-1] if n_v > 2 else []

    # PHASE 3.5.8 item 2 FIX — normative redesign ("el refactor
    # normativo"): when NEITHER axis has more than one genuinely
    # interior bar position (e.g. 8 bars total on a square column — one
    # extra bar per long edge, at each edge's own midpoint), the up-to-2
    # individual straight crossties that used to connect each interior
    # bar straight across to its mirror are collapsed into ONE closed
    # interior stirrup loop PER Z ZONE instead — a normative interior
    # tie (EHE/BS-style) connecting all of that zone's interior bars in
    # one closed 4-segment Set, reusing the exact same
    # create_rebar_set/RebarStyle.StirrupTie mechanism already proven
    # live for the main stirrups, instead of dozens of individual
    # hooked create_from_curves calls per column (the reported mass
    # "Internal Error" source). Only collapses when at least one
    # interior position exists and NEITHER axis has more than one — an
    # axis with 2+ interior positions keeps the individual-crosstie
    # path below unchanged, since one loop cannot correctly embrace
    # more than one bar per side without leaving the others uncaught.
    collapse_to_loop = (len(us_interior) <= 1 and len(vs_interior) <= 1
                         and (bool(us_interior) or bool(vs_interior)))

    interior_stirrup_sets = []
    pairs = []
    if collapse_to_loop:
        u_int_mm = us_interior[0] if us_interior else 0.0
        v_int_mm = vs_interior[0] if vs_interior else 0.0
        p_start0 = axis.GetEndPoint(0)
        axis_dir0 = axis.Direction
        for zone in zones:
            base = p_start0 + axis_dir0.Multiply(zone['start_mm'] / _MM_PER_FT)
            p_top = (base + u_dir.Multiply(u_int_mm / _MM_PER_FT)
                     + v_dir.Multiply(half_d_mm / _MM_PER_FT))
            p_right = (base + u_dir.Multiply(half_w_mm / _MM_PER_FT)
                       + v_dir.Multiply(v_int_mm / _MM_PER_FT))
            p_bottom = (base + u_dir.Multiply(u_int_mm / _MM_PER_FT)
                        + v_dir.Multiply(-half_d_mm / _MM_PER_FT))
            p_left = (base + u_dir.Multiply(-half_w_mm / _MM_PER_FT)
                      + v_dir.Multiply(v_int_mm / _MM_PER_FT))
            loop = [DB.Line.CreateBound(p_top, p_right), DB.Line.CreateBound(p_right, p_bottom),
                    DB.Line.CreateBound(p_bottom, p_left), DB.Line.CreateBound(p_left, p_top)]
            interior_stirrup_sets.append({
                'curves': loop, 'normal': axis_dir0,
                'array_length_mm': zone['end_mm'] - zone['start_mm'],
                'spacing_mm': zone['spacing_mm'], 'style': 'StirrupTie',
            })
    else:
        if layout == 'alternate':
            us_interior = us_interior[0::2]
            vs_interior = vs_interior[0::2]
        pairs = [((u, half_d_mm), (u, -half_d_mm)) for u in us_interior]
        pairs += [((half_w_mm, v), (-half_w_mm, v)) for v in vs_interior]

    # PHASE 3.5.3 item 1 FIX — "Identical rebar" live warnings, x114:
    # generate_column_stirrup_zones' own 3-zone joint/middle/joint
    # split makes ADJACENT zones share a boundary Z exactly (zone[i]'s
    # end_mm == zone[i+1]'s start_mm, by construction). _evenly_spaced
    # is INCLUSIVE of both its own lo and hi by contract, so that
    # shared boundary was previously emitted TWICE — once as zone[i]'s
    # last position, once again as zone[i+1]'s first — producing two
    # geometrically IDENTICAL crossties per (pair, shared boundary).
    # Computed ONCE here (independent of `pairs`) and deduplicated
    # against the immediately preceding zone's own last position.
    z_positions_mm = []
    prev_end_mm = None
    for zone in zones:
        zone_positions = _evenly_spaced(zone['start_mm'], zone['end_mm'], zone['spacing_mm'])
        # PHASE 3.5.6 item 4 — inset the FIRST and LAST crosstie of
        # EVERY zone by _CROSSTIE_Z_EPSILON_MM inward from that zone's
        # own boundary. A zone boundary is exactly where
        # _subtract_floor_bands cut this zone at a detected floor's
        # own thickness — a crosstie landing precisely on that cut
        # sits right at the edge of the column's local notch from the
        # slab (a live "Internal Error" source, x32 reports). This
        # margin keeps every crosstie strictly inside the column's own
        # solid core, clear of any floor-band cut. Skipped for a zone
        # too short to absorb the margin on both ends (span <= 2x the
        # epsilon) or with only one position (already centred, not at
        # either boundary) — the dedup check just below still handles
        # the too-short case's shared-boundary duplicate correctly.
        span_mm = zone['end_mm'] - zone['start_mm']
        if len(zone_positions) >= 2 and span_mm > 2.0 * _CROSSTIE_Z_EPSILON_MM:
            zone_positions = list(zone_positions)
            zone_positions[0] = min(zone_positions[0] + _CROSSTIE_Z_EPSILON_MM, zone['end_mm'])
            zone_positions[-1] = max(zone_positions[-1] - _CROSSTIE_Z_EPSILON_MM, zone['start_mm'])
        if (zone_positions and prev_end_mm is not None
                and abs(zone_positions[0] - prev_end_mm) < 1e-6):
            zone_positions = zone_positions[1:]
        z_positions_mm.extend(zone_positions)
        prev_end_mm = zone['end_mm']

    p_start = axis.GetEndPoint(0)
    axis_dir = axis.Direction
    bars = []
    for (u1, v1), (u2, v2) in pairs:
        p1 = u_dir.Multiply(u1 / _MM_PER_FT) + v_dir.Multiply(v1 / _MM_PER_FT)
        p2 = u_dir.Multiply(u2 / _MM_PER_FT) + v_dir.Multiply(v2 / _MM_PER_FT)
        for z_mm in z_positions_mm:
            base = p_start + axis_dir.Multiply(z_mm / _MM_PER_FT)
            line = DB.Line.CreateBound(base + p1, base + p2)
            bars.append({'curve': line, 'normal': axis_dir})
    return {'crosstie_bars': bars, 'interior_stirrup_sets': interior_stirrup_sets}


# ══════════════════════════════════════════════════════════════════════════
# Orchestration
# ══════════════════════════════════════════════════════════════════════════

def build_column_rebar_curves(doc, host, cover_mm, bar_diameter_mm, n_u, n_v,
                               stirrup_diameter_mm, dense_spacing_mm, normal_spacing_mm,
                               joint_zone_length_mm=None, start_offset_mm=50.0,
                               end_offset_mm=50.0, add_dowels=False, lap_length_mm=None,
                               lap_multiplier=40.0):
    """
    High-level pipeline for one rectangular column host:
      1. Read the column's straight centreline (get_column_axis).
      2. Build a CoverGeometryManager and classify the 4 side faces
         into opposite (u, v) pairs (_column_faces).
      3. Build perimeter vertical bar Lines (compute_vertical_bar_lines).
      4. If add_dowels, extend each vertical bar's top end by a lap
         length (extend_bar_for_lap), using lap_length_mm if given, else
         default_lap_length_mm(bar_diameter_mm, lap_multiplier).
      5. Build stirrup rectangles at every
         generate_column_stirrup_positions() position, using
         joint_zone_length_mm if given, else
         default_joint_zone_length_mm(larger cross-section dimension,
         clear height).

    Args:
        doc                     (DB.Document)
        host                    (DB.Element): the column.
        cover_mm                (float): nominal cover, mm.
        bar_diameter_mm         (float): vertical bar diameter, mm.
        n_u, n_v                (int): vertical bars per edge — see
                                _perimeter_positions.
        stirrup_diameter_mm     (float): stirrup bar diameter, mm — used
                                only to inset the stirrup rectangle one
                                more radius inside the vertical-bar cover
                                line.
        dense_spacing_mm        (float): stirrup spacing in joint zones,
                                mm.
        normal_spacing_mm       (float): stirrup spacing in the middle
                                span, mm.
        joint_zone_length_mm    (float or None): confinement zone length
                                — computed via default_joint_zone_length_mm
                                if not supplied.
        start_offset_mm, end_offset_mm (float): see
                                generate_column_stirrup_positions.
        add_dowels               (bool): whether to extend vertical bars
                                for lapping with the storey above.
        lap_length_mm            (float or None): lap length, mm — only
                                used if add_dowels is True; computed via
                                default_lap_length_mm if not supplied.
        lap_multiplier            (float): see default_lap_length_mm.

    Returns:
        {
          'vertical_bars': list[list[DB.Curve]],  # one chain per bar
          'stirrups':      list[list[DB.Curve]],  # each a closed 4-segment chain
        }

    Raises:
        ValueError: from get_column_axis / _column_faces /
        _perimeter_positions.
    """
    engine = _ensure_engine()
    axis = get_column_axis(host)
    cover_mgr = engine.CoverGeometryManager(doc, host)
    source = _resolve_column_geometry_source(host, axis, cover_mgr)
    u_dir, v_dir = source['u_dir'], source['v_dir']

    vertical_lines = compute_vertical_bar_lines(doc, host, cover_mm, n_u, n_v, bar_diameter_mm)

    if add_dowels:
        lap_mm = lap_length_mm if lap_length_mm is not None else default_lap_length_mm(
            bar_diameter_mm, lap_multiplier)
        vertical_chains = [
            extend_bar_for_lap(line, lap_mm, DB.XYZ.BasisZ, at_end=True)
            for line in vertical_lines
        ]
    else:
        vertical_chains = [[line] for line in vertical_lines]

    stirrup_inset_mm = cover_mm + bar_diameter_mm
    half_w_mm, half_d_mm = _half_extents_from_source(engine, axis, source, stirrup_inset_mm)

    clear_height_mm = axis.Length * _MM_PER_FT
    if joint_zone_length_mm is None:
        larger_dim_mm = max(2 * half_w_mm, 2 * half_d_mm)
        joint_zone_length_mm = default_joint_zone_length_mm(larger_dim_mm, clear_height_mm)

    positions = generate_column_stirrup_positions(
        clear_height_mm, joint_zone_length_mm, dense_spacing_mm, normal_spacing_mm,
        start_offset_mm, end_offset_mm)

    stirrups = [
        build_stirrup_rectangle(axis, d, u_dir, v_dir, half_w_mm, half_d_mm)
        for d in positions
    ]

    return {'vertical_bars': vertical_chains, 'stirrups': stirrups}


def _resolve_circular_crank_offset_mm(doc, host, axis, elevation_ft, bar_inset_mm,
                                       bar_radius_mm, tol_ft=_OST_COLUMNS_TOL_FT):
    """
    Circular-column counterpart of resolve_crank_offset_mm: a UNIFORM
    radial offset (a circle has no distinct U/V faces to offset
    separately, unlike a rectangle) — 0.0 if no distinct column is
    found above, or if the column above isn't itself identifiable as
    circular (a circular-to-rectangular storey transition isn't
    supported by this auto-detect; pass crank_offset_mm explicitly for
    that case instead).

    Same disclosed approximation as resolve_crank_offset_mm: this
    module has no access to the upper column's own cover/stirrup
    values at this stage, so the UPPER column's bar radius is
    estimated using the LOWER column's own bar_inset_mm.

    Returns:
        float, mm — 0.0 if no crank is needed/resolvable, otherwise
        lower_bar_radius_mm - upper_bar_radius_mm (may be negative if
        the column above is actually LARGER — build_cranked_starter
        handles that as an outward crank, same as the rectangular
        case).
    """
    p0 = axis.GetEndPoint(0)
    upper_host = find_column_above(doc, host, elevation_ft, p0.X, p0.Y, tol_ft)
    if upper_host is None:
        return 0.0
    upper_diameter_mm = _lookup_length_param_mm(upper_host, [u'Diameter', u'DIAMETER', u'diameter'])
    if upper_diameter_mm is None:
        upper_b_mm = _lookup_length_param_mm(upper_host, [u'b', u'B'])
        upper_h_mm = _lookup_length_param_mm(upper_host, [u'h', u'H'])
        if upper_b_mm is not None and upper_h_mm is None:
            upper_diameter_mm = upper_b_mm
    if upper_diameter_mm is None:
        return 0.0
    upper_bar_radius_mm = upper_diameter_mm / 2.0 - bar_inset_mm
    return bar_radius_mm - upper_bar_radius_mm


def _build_circular_column_reinforcement(doc, host, axis, diameter_mm, cover_mm,
                                          bar_diameter_mm, bar_count, stirrup_diameter_mm,
                                          dense_spacing_mm, normal_spacing_mm,
                                          densify_at_nodes, include_starter_bars,
                                          starter_bar_length_mm, starter_bar_multiplier,
                                          use_cranked_laps, crank_offset_mm, crank_slope,
                                          joint_zone_length_mm, start_offset_mm, end_offset_mm,
                                          std=None):
    """
    PHASE 3.5.7 item 1 — circular column reinforcement: radial vertical
    bars (pure trigonometry — DB.XYZ(cos, sin)) and circular ties.

    PHASE 3.5.9 item 4 FIX — ties are NO LONGER two 180° DB.Arc halves.
    Live testing confirmed Revit rejects that shape outright
    (Rebar.CreateFromCurves returns None for a closed loop built from 2
    Arc curves and no straight segment) — abandoned per the user's own
    direction rather than chasing a workaround. Ties are now a CLOSED
    POLYGON approximation: _CIRCULAR_TIE_CHORD_COUNT (24) short straight
    Line chords computed trigonometrically around the tie's own radius
    — the exact same closed-polyline shape already proven live for
    rectangular StirrupTie sets, just with more, shorter sides.

    Vertical bars are INDIVIDUAL elements, never Rebar Sets: a circle's
    bar positions are not collinear, so SetLayoutAsMaximumSpacing (which
    propagates a shape along ONE straight direction) has nothing to
    propagate along — every position needs its own create_from_curves
    call, matching this module's existing "count of 1 -> individual
    element" convention for a rectangular face reduced to one bar.

    Crossties are NOT generated for circular columns: there is no
    established "tie to the opposite bar" convention for a radially
    distributed layout the way there is for a rectangular perimeter —
    crosstie_sets is always returned empty here, explicitly, rather
    than guessing a heuristic.

    Args: same meaning as build_column_reinforcement's own parameters
    of the identical name — see that function's docstring — plus:
        axis         (DB.Line): from get_column_axis(host), already
                     resolved by the caller.
        diameter_mm  (float): the column's real diameter, mm — PHASE
                     3.5.9 item 1: now resolved EXCLUSIVELY from a
                     "Diameter" type parameter (a bare "b" with no "h"
                     is a SQUARE column, not circular — see
                     build_column_reinforcement's own circular-branch
                     comment and _resolve_column_geometry_source).

    Returns:
        Same shape as build_column_reinforcement — 'vertical_bar_sets'
        and 'crosstie_sets' are always empty lists here.
    """
    engine = _ensure_engine()
    warnings = []
    radius_mm = diameter_mm / 2.0

    bar_inset_mm = cover_mm + stirrup_diameter_mm + bar_diameter_mm / 2.0
    bar_radius_mm = radius_mm - bar_inset_mm
    if bar_radius_mm <= 0:
        warnings.append(
            u'cover ({:.0f}mm) + stirrup ({:.0f}mm) + bar radius ({:.0f}mm) leaves '
            u'no room inside this column\'s own circular section for the vertical '
            u'bars — the requested combination does not fit; verify cover/bar/'
            u'stirrup sizes before construction.'.format(
                cover_mm, stirrup_diameter_mm, bar_diameter_mm / 2.0))

    p_start = axis.GetEndPoint(0)
    axis_dir = axis.Direction
    # Any orthogonal horizontal basis works for a circle — no
    # orientation dependency, unlike a rectangle's b/h (a circle looks
    # identical from every angle), so this doesn't need
    # Location.Rotation at all.
    u_dir = DB.XYZ(1.0, 0.0, 0.0)
    v_dir = DB.XYZ(0.0, 1.0, 0.0)

    # PHASE F2.5 — starters lap the vertical bar into the storey above,
    # under gravity load: assumed IN COMPRESSION (the conventional
    # default for a column's own main bars) so a resolved `std` uses
    # standards.lap_length_mm's compression_factor, not the tension
    # bands. A caller needing a tension-splice column (unusual) should
    # keep passing an explicit starter_bar_length_mm override instead.
    lap_mm = (starter_bar_length_mm if starter_bar_length_mm is not None
              else default_lap_length_mm(bar_diameter_mm, starter_bar_multiplier,
                                          std=std, in_compression=True))
    floor_entries = find_floor_split_elevations_ft(doc, axis)
    split_elevations_ft = [e['top_ft'] for e in floor_entries]

    n = max(3, int(bar_count))
    vertical_bars = []
    for i in range(n):
        theta = 2.0 * math.pi * i / n
        offset = u_dir.Multiply(bar_radius_mm * math.cos(theta) / _MM_PER_FT) \
            + v_dir.Multiply(bar_radius_mm * math.sin(theta) / _MM_PER_FT)
        # The crank/starter machinery needs a face-perpendicular
        # "inward" direction (build_cranked_starter bends the starter
        # toward it) — for a circle, that is simply the negative
        # radial unit vector AT THIS BAR'S OWN ANGLE. "normal" (the
        # plane the shape/hooks are considered to lie in) is set to
        # the TANGENT direction at this angle, matching this module's
        # existing convention for rectangular verticals (normal =
        # the direction ALONG the face, i.e. perpendicular to that
        # face's own inward normal — see build_column_reinforcement's
        # own edge_dir/inward_dir pairing).
        inward_dir = DB.XYZ(-math.cos(theta), -math.sin(theta), 0.0)
        tangent_dir = DB.XYZ(-math.sin(theta), math.cos(theta), 0.0)

        if crank_offset_mm is not None:
            crank_offset_fn = lambda z_ft: crank_offset_mm
        else:
            crank_offset_fn = lambda z_ft: _resolve_circular_crank_offset_mm(
                doc, host, axis, z_ft, bar_inset_mm, bar_radius_mm)

        chains_per_segment = build_story_segment_chains(
            axis, offset, split_elevations_ft, lap_mm, include_starter_bars,
            use_cranked_laps, inward_dir, crank_offset_fn, crank_slope)
        for chain in chains_per_segment:
            vertical_bars.append({'curves': chain, 'normal': tangent_dir})

    stirrup_inset_mm = cover_mm + stirrup_diameter_mm / 2.0
    stirrup_radius_mm = radius_mm - stirrup_inset_mm
    stirrup_radius_ft = stirrup_radius_mm / _MM_PER_FT

    clear_height_mm = axis.Length * _MM_PER_FT
    # A circle's "larger cross-section dimension" is the tie's own diameter;
    # the joint zone is resolved per storey by generate_storey_stirrup_zones.

    axis_base_ft = axis.GetEndPoint(0).Z
    floor_bands_mm = [((e['bottom_ft'] - axis_base_ft) * _MM_PER_FT,
                        (e['top_ft'] - axis_base_ft) * _MM_PER_FT) for e in (floor_entries or [])]
    zones = generate_storey_stirrup_zones(
        clear_height_mm, 2.0 * stirrup_radius_mm, dense_spacing_mm, normal_spacing_mm,
        densify_at_nodes, start_offset_mm, end_offset_mm, floor_bands_mm=floor_bands_mm,
        joint_zone_length_mm=joint_zone_length_mm, std=std)

    stirrup_sets = []
    for zone in zones:
        base = p_start + axis_dir.Multiply(zone['start_mm'] / _MM_PER_FT)
        chord_points = []
        for k in range(_CIRCULAR_TIE_CHORD_COUNT):
            theta = 2.0 * math.pi * k / _CIRCULAR_TIE_CHORD_COUNT
            chord_points.append(
                base + u_dir.Multiply(stirrup_radius_ft * math.cos(theta))
                     + v_dir.Multiply(stirrup_radius_ft * math.sin(theta)))
        n = _CIRCULAR_TIE_CHORD_COUNT
        curves = [DB.Line.CreateBound(chord_points[k], chord_points[(k + 1) % n])
                  for k in range(n)]
        stirrup_sets.append({
            'curves': curves,
            'normal': axis_dir,
            'array_length_mm': zone['end_mm'] - zone['start_mm'],
            'spacing_mm': zone['spacing_mm'],
            'style': 'StirrupTie',
            # Real lapped circle (shape 75) when the project has it; the
            # polygon above is the fallback. Tension lap (user, 2026-09-30).
            'circle': {'centre': base, 'radius_mm': stirrup_radius_mm,
                       'lap_mm': default_lap_length_mm(stirrup_diameter_mm, std=std,
                                                       in_compression=False)},
        })

    return {'vertical_bars': vertical_bars, 'vertical_bar_sets': [],
            'stirrup_sets': stirrup_sets, 'crosstie_sets': [],
            'interior_stirrup_sets': [], 'warnings': warnings}


def build_column_reinforcement(doc, host, cover_mm, bar_diameter_mm, bar_count,
                                stirrup_diameter_mm, dense_spacing_mm, normal_spacing_mm,
                                densify_at_nodes=False, include_starter_bars=False,
                                starter_bar_length_mm=None, starter_bar_multiplier=40.0,
                                use_cranked_laps=False, crank_offset_mm=None,
                                crank_slope=6.0, include_crossties=False,
                                crosstie_layout='all',
                                joint_zone_length_mm=None, start_offset_mm=50.0,
                                end_offset_mm=50.0, std=None):
    """
    PHASE 3 (multi-story + Rebar-Set verticals — PHASE 3.2) — the
    ui.py-facing pipeline for one rectangular column host, matching the
    naming/return-shape convention of
    footing_rebar.build_footing_reinforcement / floor_rebar.
    build_floor_reinforcement.

    PHASE 3.2 item 1 — MULTI-STORY SPLITTING: a live test found tall
    (multi-story) columns crashing on two counts — a single vertical
    bar the length of the whole column, and starters computed only at
    the column's absolute top (an Internal Error when that projected
    outside what Revit's cover/host association could validate for a
    genuinely multi-story instance). Fixed via
    find_floor_split_elevations_ft + build_story_segment_chains: every
    OST_Floors element the column's axis passes through becomes a
    mandatory split point, so each vertical bar position now yields ONE
    curve chain per storey segment instead of one for the whole column,
    each with its own starter at its own storey's floor top (as well
    as, if include_starter_bars, one more at the column's own final
    top). An ordinary single-story column (crossing no floor) is
    UNAFFECTED — exactly one chain per position, identical to this
    function's pre-3.2 output.

    PHASE 3.2 item 1 (cont'd) / PHASE 3.3 — CRANKED LAPS: if
    use_cranked_laps, every starter (at an intermediate floor AND, if
    include_starter_bars, the column's own top) kinks at crank_slope:1
    before projecting straight up for the lap length — see
    build_cranked_starter for the geometry. The crank amount is now
    resolved PER SPLIT from the REAL column found immediately above
    each elevation (find_column_above / resolve_crank_offset_mm):
    0.0 (no crank) if the SAME column instance continues there (the
    common case — a genuinely continuous multi-story column has no
    section change to crank around), or the real difference between
    this column's own section and the one found above, on whichever
    axis that face's crank travels. crank_offset_mm, if explicitly
    given, OVERRIDES this per-split detection with one fixed value
    everywhere instead (useful when no real column-above exists yet to
    detect against, e.g. testing, or a deliberately manual value).

    PHASE 3.2 item 2 — VERTICAL BARS AS REBAR SETS: verticals are no
    longer individual elements for every bar position. _face_groups
    partitions the perimeter layout into the column's own 4 faces (each
    U-edge owns its 2 corners; each V-edge gets only its strictly
    interior positions, so the 4 groups' union is the identical
    position set _perimeter_positions itself produces, just
    partitioned) and each face with >= 2 bar positions becomes ONE
    Rebar Set per storey segment via SetLayoutAsFixedNumber (the exact
    count/positions this module already computed, not a spacing-driven
    guess) — e.g. a 12-bar rectangular column, single story, becomes 4
    Sets, one per face, matching the explicit brief. A face reduced to
    a single bar position (e.g. a V-edge when n_v == 2, all bars
    already claimed by the two U-edges' corners) stays an individual
    element — SetLayoutAsFixedNumber has nothing to propagate for a
    count of 1 — returned separately in 'vertical_bars'.

    PHASE 3.4 item 2 — STIRRUPS STOP AT EACH FLOOR: the joint-zone
    generation below used to treat the ENTIRE axis length as one
    column for confinement purposes, running continuous Stirrup Sets
    straight through a floor's own thickness — physically wrong (a
    column's stirrups exist within ITS OWN concrete, not inside the
    slab/beam zone they pass behind). Fixed via _subtract_floor_bands:
    each intersecting floor's own [bottom_ft, top_ft] range (from
    find_floor_split_elevations_ft, which now returns both) is cut out
    of the continuous zone list BEFORE build_stirrup_sets, so a zone
    straddling a floor splits into "stops at the slab's underside" /
    "resumes at the slab's top" pieces, each keeping its own
    dense/normal spacing.

    PHASE 3.4 item 5 — INTERIOR CROSSTIES: if include_crossties, every
    intermediate (non-corner) vertical bar gets a straight crosstie to
    its direct mirror across the section — see build_crosstie_sets —
    using the SAME (floor-band-excluded) zones as the main stirrups.

    Args:
        doc, host              as elsewhere.
        cover_mm                (float): nominal cover, mm.
        bar_diameter_mm          (float): vertical bar diameter, mm.
        bar_count                (int): TOTAL desired vertical bar
                                 count — see distribute_bar_count for
                                 how this becomes a perimeter layout.
        stirrup_diameter_mm      (float): stirrup bar diameter, mm.
        dense_spacing_mm         (float): stirrup spacing at the joint
                                 zones (or everywhere, if
                                 densify_at_nodes is False and this is
                                 unused — normal_spacing_mm governs the
                                 single zone instead).
        normal_spacing_mm        (float): stirrup spacing in the middle
                                 span (or everywhere, if
                                 densify_at_nodes is False).
        densify_at_nodes         (bool): whether to split into 3 zones
                                 (bottom/middle/top) or use ONE uniform
                                 zone at normal_spacing_mm.
        include_starter_bars     (bool): whether the column's OWN final
                                 top also gets a starter ("esperas" for
                                 the storey above THIS column entirely —
                                 every INTERMEDIATE floor split always
                                 gets one regardless of this flag; see
                                 build_story_segment_chains).
        starter_bar_length_mm    (float or None): lap length, mm — see
                                 default_lap_length_mm if not given.
        starter_bar_multiplier   (float): see default_lap_length_mm.
        use_cranked_laps         (bool): if True, every starter cranks
                                 inward at crank_slope:1 first — see
                                 build_cranked_starter. Default False —
                                 a plain straight extension, unchanged
                                 from before Phase 3.2.
        crank_offset_mm          (float or None): if given, a FIXED
                                 crank shift, mm, applied uniformly at
                                 every split instead of per-split
                                 detection — see resolve_crank_offset_mm
                                 for the default (None) behaviour: the
                                 real difference between this column's
                                 section and whatever column is
                                 actually found above each split.
        crank_slope              (float): the "1:N" slope's N — see
                                 build_cranked_starter. Default 6 (the
                                 requested "1:6").
        include_crossties        (bool): whether to add interior
                                 crossties for every intermediate
                                 (non-corner) vertical bar — see
                                 build_crosstie_sets. Default False.
                                 Each returned bar's hooks must be baked
                                 in AT creation via
                                 RebarWrapper.create_from_curves(
                                 start_hook=, end_hook=) — a bare line
                                 is not a real crosstie.
        crosstie_layout          ('all' or 'alternate'): 'all' ties
                                 every intermediate bar; 'alternate'
                                 ties only every other one per edge.
                                 Only used if include_crossties.
        joint_zone_length_mm     (float or None): confinement zone
                                 length — see
                                 default_joint_zone_length_mm if not
                                 given.
        start_offset_mm, end_offset_mm (float): see
                                 generate_column_stirrup_zones.
        std                      (dict or None): PHASE F2.5 — a resolved
                                 nosa_utils.standards profile. When
                                 given, it replaces the fixed-multiplier
                                 defaults below wherever the caller has
                                 NOT already supplied an explicit
                                 override: starter_bar_length_mm (via
                                 default_lap_length_mm's std path,
                                 in_compression=True — see that call
                                 site's own comment) and
                                 joint_zone_length_mm (via
                                 default_joint_zone_length_mm's
                                 stirrups.confinement_zone_factor_h).
                                 Passed straight through to the circular
                                 branch too. Omitting std (the default,
                                 None) reproduces exactly this
                                 function's pre-F2.5 behaviour.

    Returns:
        {
          'vertical_bars': [{'curves': [DB.Curve,...], 'normal': DB.XYZ}, ...],
                           # individual elements — one per (single-bar
                           # face, storey segment) pair only; empty for
                           # the common case where every face has >= 2
                           # bar positions.
          'vertical_bar_sets': [{'curves','normal','count',
                                  'array_length_mm','style':None}, ...],
                           # one entry per (face with >= 2 positions,
                           # storey segment) pair — the common case.
          'stirrup_sets':  [{'curves','normal','array_length_mm',
                              'spacing_mm','style':'StirrupTie'}, ...],
                           # one entry per (zone, AFTER floor-band
                           # exclusion) — MORE entries than before for
                           # a column crossing a floor.
          'crosstie_sets': [{'curve','normal'}, ...],
                           # INDIVIDUAL bars (see build_crosstie_sets —
                           # not Rebar Sets, hooks are baked in at
                           # creation instead); empty unless
                           # include_crossties AND the column has
                           # genuinely interior bars.
          'warnings': [unicode, ...],
                           # PHASE 3.5.1 item 3 — non-fatal geometric
                           # warnings (e.g. cover+stirrup+bar radius
                           # not fitting inside the column's own
                           # section); empty in the normal case.
        }

    Raises:
        ValueError: from get_column_axis / _column_faces (no straight
        centreline, or not exactly 4 rectangular side faces).
    """
    axis = get_column_axis(host)

    # PHASE 3.5.7 item 1 — circular columns branch out ENTIRELY here,
    # before touching _column_faces / _resolve_column_geometry_source
    # at all. A circular column has ZERO planar side faces, so any
    # path that reaches _column_faces for one crashes ("Expected
    # exactly 4... found 0") no matter what b/h-based fallback exists
    # downstream.
    #
    # BUG FIX (2026-09-01, confirmed live against a real project):
    # this used to check ONLY the literal "Diameter" parameter name —
    # Phase 3.5.9's own reasoning for that ("many genuine SQUARE
    # families expose only 'b'") is sound, but it silently broke the
    # OPPOSITE real case: Revit's own stock "Concrete Round" structural
    # column family exposes ONLY 'b' (its diameter) and no "Diameter"
    # parameter at all — this column fell all the way through to the
    # rectangular path and got reinforced as a square. Now delegates to
    # detect_column_geometry(), which tries "Diameter" first (unchanged
    # fast path), then — for a bare 'b' with no 'h' — checks the SOLID's
    # real geometry for a true DB.CylindricalFace BEFORE assuming
    # square, so a genuinely round family is never misdetected by name
    # alone. A genuinely rectangular/square host (detect_column_geometry
    # returns 'rect' or the geometry doesn't resolve) falls through to
    # the unchanged rectangular path below exactly as before.
    geom = detect_column_geometry(doc, host)
    if geom is not None and geom.get('shape') == 'circle':
        diameter_mm = geom['diameter_mm']
        return _build_circular_column_reinforcement(
            doc, host, axis, diameter_mm, cover_mm, bar_diameter_mm, bar_count,
            stirrup_diameter_mm, dense_spacing_mm, normal_spacing_mm, densify_at_nodes,
            include_starter_bars, starter_bar_length_mm, starter_bar_multiplier,
            use_cranked_laps, crank_offset_mm, crank_slope,
            joint_zone_length_mm, start_offset_mm, end_offset_mm, std=std)

    engine = _ensure_engine()
    cover_mgr = engine.CoverGeometryManager(doc, host)
    section_source = _resolve_column_geometry_source(host, axis, cover_mgr)
    u_dir, v_dir = section_source['u_dir'], section_source['v_dir']

    # Corner bars seat in the link's bend (T2.10b); each face set shares their plane.
    bar_inset_mm = cover_mm + stirrup_diameter_mm + bar_diameter_mm / 2.0 +         engine.link_corner_extra_inset_mm(bar_diameter_mm, stirrup_diameter_mm)
    bar_half_w_mm, bar_half_d_mm = _half_extents_from_source(
        engine, axis, section_source, bar_inset_mm)

    # PHASE 3.5.1 item 3 — verify the vertical bars' full cylinder
    # (bar_diameter_mm/2 included, via bar_inset_mm above) doesn't
    # penetrate the real concrete face: bar_half_w_mm/bar_half_d_mm
    # are the axis-to-bar-centre distance AFTER subtracting
    # cover+stirrup+radius from the real face position, so <= 0 means
    # the requested cover/stirrup/bar combination doesn't fit inside
    # this column's own cross-section at all (the bar's outer surface
    # would sit past the opposite face, or past the axis itself) —
    # warn rather than silently generating degenerate bar positions.
    warnings = []
    if bar_half_w_mm <= 0 or bar_half_d_mm <= 0:
        warnings.append(
            u'cover ({:.0f}mm) + stirrup ({:.0f}mm) + bar radius '
            u'({:.0f}mm) leaves no room inside this column\'s own '
            u'cross-section for the vertical bars — the requested '
            u'combination does not fit; verify cover/bar/stirrup sizes '
            u'before construction.'.format(
                cover_mm, stirrup_diameter_mm, bar_diameter_mm / 2.0))

    n_u, n_v = distribute_bar_count(bar_count, bar_half_w_mm, bar_half_d_mm)
    # PHASE 3.5.9 item 3 — explicit, unconditional floor: the main cage's
    # perimeter faces (_face_groups, right below) must NEVER receive
    # n_u/n_v < 2 — n=1 on an axis collapses that axis's two edges to a
    # single shared midpoint, which is exactly a "bars at face centers,
    # corners skipped" layout. distribute_bar_count already clamps both
    # values to >= 2 internally, so this is defense-in-depth (never
    # actually observed firing) — see the analysis note below for what
    # ACTUALLY caused the reported "4 bars at face centers" symptom.
    #
    # ROOT CAUSE FOUND (not this clamp): PHASE 3.5.9 item 1 — a square
    # column family exposing only 'b' (no 'h') was being misdetected as
    # CIRCULAR (see the fix at this function's own circular-branch
    # above), so it never reached _face_groups at all — it went through
    # _build_circular_column_reinforcement's RADIAL placement instead,
    # which for n=4 puts bars at angles 0/90/180/270 degrees from
    # center. For a SQUARE section those angles land exactly on the
    # FACE MIDPOINTS (a square's own corners sit at 45/135/225/315
    # degrees) — reproducing the exact "face-center, corners skipped"
    # symptom reported, with no bug in the corner-placement math itself.
    # Fixing the misdetection routes these columns through THIS
    # (rectangular, corner-correct) path again.
    n_u = max(2, n_u)
    n_v = max(2, n_v)

    # PHASE F2.5 — see this function's own std docstring entry above:
    # assumed IN COMPRESSION, matching the circular branch's identical
    # comment.
    lap_mm = (starter_bar_length_mm if starter_bar_length_mm is not None
              else default_lap_length_mm(bar_diameter_mm, starter_bar_multiplier,
                                          std=std, in_compression=True))
    floor_entries = find_floor_split_elevations_ft(doc, axis)
    split_elevations_ft = [e['top_ft'] for e in floor_entries]

    vertical_bars = []
    vertical_bar_sets = []
    for face in _face_groups(bar_half_w_mm, bar_half_d_mm, n_u, n_v):
        positions = face['positions']
        if not positions:
            continue
        edge_dir_key = face['edge_dir']
        edge_dir = u_dir if edge_dir_key == 'u' else v_dir
        inward_dir = (v_dir if edge_dir_key == 'u' else u_dir).Multiply(face['inward_sign'])
        u0_mm, v0_mm = positions[0]
        offset0 = u_dir.Multiply(u0_mm / _MM_PER_FT) + v_dir.Multiply(v0_mm / _MM_PER_FT)

        if crank_offset_mm is not None:
            crank_offset_fn = lambda z_ft: crank_offset_mm
        else:
            crank_offset_fn = lambda z_ft, _k=edge_dir_key: resolve_crank_offset_mm(
                doc, host, axis, z_ft, _k, engine, bar_inset_mm,
                bar_half_w_mm, bar_half_d_mm)

        chains_per_segment = build_story_segment_chains(
            axis, offset0, split_elevations_ft, lap_mm, include_starter_bars,
            use_cranked_laps, inward_dir, crank_offset_fn, crank_slope)

        if len(positions) == 1:
            for chain in chains_per_segment:
                vertical_bars.append({'curves': chain, 'normal': edge_dir})
            continue

        u_last_mm, v_last_mm = positions[-1]
        array_length_mm = abs((u_last_mm - u0_mm) if face['edge_dir'] == 'u'
                               else (v_last_mm - v0_mm))
        for chain in chains_per_segment:
            vertical_bar_sets.append({
                'curves': chain, 'normal': edge_dir, 'count': len(positions),
                'array_length_mm': array_length_mm, 'style': None,
            })

    stirrup_inset_mm = cover_mm + stirrup_diameter_mm / 2.0
    stirrup_half_w_mm, stirrup_half_d_mm = _half_extents_from_source(
        engine, axis, section_source, stirrup_inset_mm)

    clear_height_mm = axis.Length * _MM_PER_FT
    larger_dim_mm = max(2 * stirrup_half_w_mm, 2 * stirrup_half_d_mm)
    axis_base_ft = axis.GetEndPoint(0).Z
    floor_bands_mm = [((e['bottom_ft'] - axis_base_ft) * _MM_PER_FT,
                        (e['top_ft'] - axis_base_ft) * _MM_PER_FT) for e in (floor_entries or [])]
    zones = generate_storey_stirrup_zones(
        clear_height_mm, larger_dim_mm, dense_spacing_mm, normal_spacing_mm, densify_at_nodes,
        start_offset_mm, end_offset_mm, floor_bands_mm=floor_bands_mm,
        joint_zone_length_mm=joint_zone_length_mm, std=std)

    stirrup_sets = build_stirrup_sets(
        axis, u_dir, v_dir, stirrup_half_w_mm, stirrup_half_d_mm, zones)

    crosstie_sets = []
    interior_stirrup_sets = []
    if include_crossties:
        crossties = build_crosstie_sets(
            axis, u_dir, v_dir, bar_half_w_mm, bar_half_d_mm, n_u, n_v, zones,
            layout=crosstie_layout)
        crosstie_sets = crossties['crosstie_bars']
        interior_stirrup_sets = crossties['interior_stirrup_sets']

    return {'vertical_bars': vertical_bars, 'vertical_bar_sets': vertical_bar_sets,
            'bar_inset_mm': bar_inset_mm,
            'stirrup_sets': stirrup_sets, 'crosstie_sets': crosstie_sets,
            'interior_stirrup_sets': interior_stirrup_sets,
            'warnings': warnings}
