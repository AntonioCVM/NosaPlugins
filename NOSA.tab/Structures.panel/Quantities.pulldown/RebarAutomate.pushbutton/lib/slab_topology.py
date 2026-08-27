# -*- coding: utf-8 -*-
"""
NOSA.RebarAutomate — Slab Topology (Phase 2.2)
============================================================================

Pure geometry module for extracting a floor's REAL plan boundary and
interior openings from its Revit face, and for clipping straight
reinforcement lines against that real shape — replacing Phase 2's
`host.get_BoundingBox(None)`-only approach, which silently assumed
every floor is a perfect axis-aligned rectangle with no holes. Live
testing on real slabs proved that wrong in three ways: reinforcement
generated outside the concrete at chamfered/irregular edges, bars
running straight through large interior openings (stairs, shafts), and
uncut bars exceeding commercial stock length. This module fixes the
first two; stock-length splitting itself is
rebar_engine.split_rebar_by_stock_length (already existed, just never
wired into floor_rebar.py's main grid).

Meant to be loaded in isolation the same way every other module in
this plugin is:

    import imp
    slab_topology = imp.load_source(
        'slab_topology', os.path.join(os.path.dirname(__file__), 'slab_topology.py'))

SCOPE
-----
Only usable for a FLAT (single-plane) top/bottom face — the same
horizontal-face assumption footing_rebar.py already makes throughout.
A face is read via Face.GetEdgesAsCurveLoops(), and every loop's
curves are tessellated (Curve.Tessellate()) into 2D (x_mm, y_mm)
points in the DOCUMENT's own X/Y — a straight edge tessellates to just
its two endpoints (no unnecessary densification), a curved edge
(arc/spline, e.g. a circular stair opening) tessellates into many
short segments, which the scanline math below treats exactly like any
other polygon edge.

OUTER LOOP VS HOLES: classified by AREA (largest = outer, everything
else = a hole) rather than by winding direction — Revit's own
outer-CCW/inner-CW convention is real, but trusting an area comparison
is more robust against getting a face's reference-direction convention
subtly wrong, and costs nothing extra since every loop's area is
already needed for the small-hole filter.

SMALL-HOLE FILTER: any hole with area <= small_hole_area_mm2 (default
40000 mm^2, i.e. an 200x200mm equivalent) is dropped entirely before
returning — the caller never sees it, so the main grid runs straight
through it uncut and it never gets a perimeter closure U-bar. This is
the Phase 2.2 brief's literal rule, applied via an AREA equivalent
rather than requiring a squarer bounding box, since "o un area
equivalente" makes an area-only test a legitimate, simpler reading of
the same rule.

COVER — PHASE 2.2 HOTFIX (real polygon offset, not a scan-axis inset):
the nominal cover value is now enforced by actually offsetting the
polygons themselves (offset_polygon_mm) BEFORE any scanline clipping —
the outer boundary is shrunk inward by cover_mm, every large hole is
grown outward by cover_mm — so reinforcement can never touch the
element's real outer face or a hole's real edge, at any edge
orientation, not just axes-aligned ones. material_intervals()'s own
`inset_mm` parameter remains, but callers now only pass a SMALL
residual (half the bar's own diameter — the distance from the bar's
CENTRELINE to its own outer face) rather than the full cover value, so
that parameter's own scan-axis-only simplification (see its docstring)
now only affects a few mm, not the full cover distance.

POLYGON OFFSET — DISCLOSED LIMITATION: offset_polygon_mm() uses the
standard "translate every edge along its own inward normal, then
re-intersect each pair of adjacent offset edges to find the new
vertex" technique. This is exact for a convex polygon and correct for
a typical concave (chamfered/notched) architectural floor outline, but
it does NOT detect or repair a self-intersecting result — a
pathologically narrow re-entrant notch (narrower than roughly 2x the
offset distance) could offset into a bow-tied/crossed polygon that
this module does not clean up. A true polygon Boolean/buffer library
would handle that; out of scope here, and not expected to matter for
a real, buildable floor plate.
"""
import math

_MM_PER_FT = 304.8

# PHASE 3.5.1 item 2 — minimum edge length polygon_edges_mm will treat
# as a real polygon side, mm. A REAL Revit floor boundary tessellates
# curves (extract_loops_mm's own docstring) and can carry modelling
# noise well above the previous 1e-6mm de-dup tolerance — a sliver
# edge that size still has a well-defined (if geometrically
# meaningless) direction/inward-normal, and floor_rebar._build_edge_ubars
# gave each one its own U-bar/closed-link treatment, producing many
# tiny, spurious Rebar.CreateFromCurves calls against near-degenerate
# geometry (the live "Internal Error x54" reports). 15mm is well above
# realistic tessellation/modelling noise and well below any genuine
# structural edge worth its own reinforcement.
_MIN_EDGE_LENGTH_MM = 15.0


def extract_loops_mm(face):
    """
    Every boundary loop of `face` (outer + every interior opening,
    small or large — filtering happens in classify_loops, not here),
    each as a list of (x_mm, y_mm) tuples in document coordinates.
    Consecutive coincident points (each curve's tessellation typically
    repeats the previous curve's endpoint) are de-duplicated. A loop
    that collapses to fewer than 3 distinct points (degenerate) is
    dropped.

    Args:
        face (DB.Face): a horizontal planar face — typically from
            footing_rebar.get_footing_bottom_face/get_footing_top_face
            (reused unchanged by floor_rebar.py for this).

    Returns:
        list[list[(float, float)]]
    """
    loops = []
    for curve_loop in face.GetEdgesAsCurveLoops():
        pts = []
        for curve in curve_loop:
            for p in curve.Tessellate():
                pts.append((p.X * _MM_PER_FT, p.Y * _MM_PER_FT))
        cleaned = []
        for pt in pts:
            if (not cleaned or abs(pt[0] - cleaned[-1][0]) > 1e-6
                    or abs(pt[1] - cleaned[-1][1]) > 1e-6):
                cleaned.append(pt)
        if len(cleaned) >= 2 and (abs(cleaned[0][0] - cleaned[-1][0]) < 1e-6
                                   and abs(cleaned[0][1] - cleaned[-1][1]) < 1e-6):
            cleaned.pop()  # tessellation closed the loop back to its start point
        if len(cleaned) >= 3:
            loops.append(cleaned)
    return loops


def polygon_area_mm2(points):
    """Shoelace formula — absolute (unsigned) area, mm^2."""
    n = len(points)
    area = 0.0
    for i in range(n):
        x1, y1 = points[i]
        x2, y2 = points[(i + 1) % n]
        area += x1 * y2 - x2 * y1
    return abs(area) / 2.0


def polygon_bbox_mm(points):
    """(xmin_mm, xmax_mm, ymin_mm, ymax_mm)."""
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    return min(xs), max(xs), min(ys), max(ys)


def classify_loops(loops, small_hole_area_mm2=10000.0):
    """
    Splits `loops` (from extract_loops_mm) into the outer boundary and
    the "large" interior openings, dropping every opening at or below
    small_hole_area_mm2 (default 10000mm^2 = 100x100mm equivalent —
    PHASE 3.5.8 item 4: lowered from the Phase 2.2 default of
    40000mm^2/200x200mm so any real functional opening — a 300x300mm
    hole per the user's own stated minimum, and everything above it —
    is comfortably above this threshold and always gets perimeter
    closure U-bars. Only true small penetrations (rebar sleeves,
    conduit stubs) at or below ~100x100mm are still dropped.

    Args:
        loops               (list[list[(float,float)]])
        small_hole_area_mm2 (float): openings at or below this area are
                             dropped — main reinforcement must run
                             straight through them, uncut, with no
                             closure U-bars.

    Returns:
        (outer, large_holes, n_small_holes_ignored)
        outer: list[(float,float)] — the largest-area loop.
        large_holes: list[list[(float,float)]] — every other loop
            above the area threshold.
        n_small_holes_ignored: int — how many openings were dropped.

    Raises:
        ValueError: if `loops` is empty (no usable face boundary at all).
    """
    if not loops:
        raise ValueError(u'No usable boundary loops found on this face.')
    ranked = sorted(((polygon_area_mm2(pts), pts) for pts in loops),
                     key=lambda t: t[0], reverse=True)
    outer = ranked[0][1]
    large_holes = []
    n_small = 0
    for area, pts in ranked[1:]:
        if area <= small_hole_area_mm2:
            n_small += 1
        else:
            large_holes.append(pts)
    return outer, large_holes, n_small


def polygon_winding_sign(points):
    """
    +1.0 if `points` winds counter-clockwise (standard maths
    convention, Y up), -1.0 if clockwise — the same signed-area test
    offset_polygon_mm already computes internally, exposed here so a
    caller needing PER-EDGE inward normals directly (without a full
    polygon offset) doesn't have to re-derive it — see
    floor_rebar.py's edge-based perimeter U-bars (Phase 3.5 item 5).
    """
    n = len(points)
    signed_area = 0.0
    for i in range(n):
        x1, y1 = points[i]
        x2, y2 = points[(i + 1) % n]
        signed_area += x1 * y2 - x2 * y1
    return 1.0 if signed_area > 0 else -1.0


def polygon_edges_mm(points):
    """
    Every edge of a closed polygon loop as
    (p0, p1, unit_dir, inward_normal, length_mm) — p0/p1 the edge's own
    two endpoints in order, unit_dir the edge's own unit direction
    vector, inward_normal the SAME winding-aware inward unit normal
    offset_polygon_mm computes per edge (perpendicular to unit_dir,
    pointing into the polygon's own interior regardless of whether
    `points` is CCW (a typical outer boundary) or CW (a typical hole)).
    An edge shorter than _MIN_EDGE_LENGTH_MM is skipped entirely — see
    that constant's own comment for why a plain near-zero-length
    de-dup tolerance isn't enough on a real, tessellated boundary.

    Args:
        points (list[(float,float)]): a closed loop, >= 3 points.

    Returns:
        list[((float,float), (float,float), (float,float), (float,float), float)]
        — (p0, p1, unit_dir, inward_normal, length_mm).
    """
    n = len(points)
    winding_sign = polygon_winding_sign(points)
    edges = []
    for i in range(n):
        p0 = points[i]
        p1 = points[(i + 1) % n]
        dx, dy = p1[0] - p0[0], p1[1] - p0[1]
        length = math.hypot(dx, dy)
        if length < _MIN_EDGE_LENGTH_MM:
            continue
        ux, uy = dx / length, dy / length
        nx, ny = winding_sign * (-uy), winding_sign * ux
        edges.append((p0, p1, (ux, uy), (nx, ny), length))
    return edges


def point_in_material_mm(x_mm, y_mm, outer, large_holes):
    """
    True if (x_mm, y_mm) lies inside `outer` and outside every polygon
    in `large_holes` — a plain even-odd (ray-casting) point-in-polygon
    test, used by floor_rebar.py's edge-based U-bar legs to verify a
    leg's own tip hasn't wandered into a nearby hole or past the
    outer boundary (see that module's own disclosed limitation note on
    narrow-rib collisions).

    Args:
        x_mm, y_mm   (float)
        outer        (list[(float,float)]): the floor's outer boundary.
        large_holes  (list[list[(float,float)]]): interior openings.

    Returns:
        bool
    """
    def _inside(px, py, poly):
        inside = False
        n = len(poly)
        for i in range(n):
            x1, y1 = poly[i]
            x2, y2 = poly[(i + 1) % n]
            if ((y1 > py) != (y2 > py)) and \
                    (px < (x2 - x1) * (py - y1) / (y2 - y1) + x1):
                inside = not inside
        return inside

    if not _inside(x_mm, y_mm, outer):
        return False
    for hole in large_holes:
        if _inside(x_mm, y_mm, hole):
            return False
    return True


def _line_intersect(p1, d1, p2, d2):
    """Intersection of line (p1 + t*d1) and (p2 + s*d2), or None if parallel."""
    x1, y1 = p1
    dx1, dy1 = d1
    x2, y2 = p2
    dx2, dy2 = d2
    denom = dx1 * dy2 - dy1 * dx2
    if abs(denom) < 1e-9:
        return None
    t = ((x2 - x1) * dy2 - (y2 - y1) * dx2) / denom
    return (x1 + t * dx1, y1 + t * dy1)


def offset_polygon_mm(points, offset_mm):
    """
    `points` with every edge moved offset_mm along ITS OWN inward
    normal (relative to that loop's own winding direction, determined
    from its signed area — so this works correctly regardless of
    whether `points` came in as the CCW outer boundary or a hole of
    either winding), then re-intersected pairwise to find each new
    vertex. See module docstring's POLYGON OFFSET note for the
    disclosed self-intersection limitation.

    A POSITIVE offset_mm shrinks the polygon toward its own interior —
    for the outer boundary that IS "shrink toward the material", for a
    hole that is "shrink the void" (the WRONG direction for cover); to
    grow a hole outward (away from material, toward the void) instead,
    pass a NEGATIVE offset_mm.

    Args:
        points     (list[(float,float)]): a closed loop, >= 3 points.
        offset_mm  (float): signed inward offset, mm — 0 returns
                   `points` unchanged.

    Returns:
        list[(float,float)] — same vertex count as `points`.
    """
    n = len(points)
    if n < 3 or offset_mm == 0.0:
        return list(points)

    signed_area = 0.0
    for i in range(n):
        x1, y1 = points[i]
        x2, y2 = points[(i + 1) % n]
        signed_area += x1 * y2 - x2 * y1
    winding_sign = 1.0 if signed_area > 0 else -1.0

    offset_edges = []  # (point_on_offset_line, direction) per edge i, i -> i+1
    for i in range(n):
        x1, y1 = points[i]
        x2, y2 = points[(i + 1) % n]
        dx, dy = x2 - x1, y2 - y1
        length = math.hypot(dx, dy)
        if length < 1e-9:
            offset_edges.append(((x1, y1), (1.0, 0.0)))
            continue
        ux, uy = dx / length, dy / length
        nx, ny = winding_sign * (-uy), winding_sign * ux  # inward normal
        offset_edges.append(((x1 + nx * offset_mm, y1 + ny * offset_mm), (ux, uy)))

    new_points = []
    for i in range(n):
        prev_pt, prev_dir = offset_edges[i - 1]
        cur_pt, cur_dir = offset_edges[i]
        inter = _line_intersect(prev_pt, prev_dir, cur_pt, cur_dir)
        if inter is None:
            new_points.append(cur_pt)
            continue
        # Miter-limit safeguard (Phase 2.4 hardening): a sharp/narrow
        # reflex corner can push the naive edge-intersection point
        # pathologically far from the original vertex — exactly the
        # kind of spike that showed up live as reinforcement
        # "protruding" past the real boundary. If the intersection
        # lands further than 4x the offset distance from the original
        # vertex, fall back to the offset edge's own start point
        # instead — less perfectly mitered at that one corner, but
        # never a wild overshoot.
        orig_vertex = points[i]
        dist = math.hypot(inter[0] - orig_vertex[0], inter[1] - orig_vertex[1])
        if dist > abs(offset_mm) * 4.0:
            new_points.append(cur_pt)
        else:
            new_points.append(inter)

    if offset_mm > 0.0:
        # PHASE 2.5 item 3 — hard safety net, independent of whatever
        # subtlety the miter-limit above did or didn't catch: a genuine
        # INWARD shrink (the outer boundary's own case) can never
        # legitimately produce a vertex outside the ORIGINAL polygon's
        # own bounding box. Any vertex that does is clamped back onto
        # that box, with a console warning — the live-tested "bars
        # protruding past a chamfered edge" symptom should now be
        # geometrically impossible for the outer boundary, whatever the
        # residual cause turns out to be. Skipped for a NEGATIVE offset
        # (growing a hole outward) since exceeding the hole's own bbox
        # is the entire point there.
        xmin = min(p[0] for p in points)
        xmax = max(p[0] for p in points)
        ymin = min(p[1] for p in points)
        ymax = max(p[1] for p in points)
        clamped = []
        for (x, y) in new_points:
            cx = min(max(x, xmin), xmax)
            cy = min(max(y, ymin), ymax)
            if abs(cx - x) > 1e-6 or abs(cy - y) > 1e-6:
                print(u'WARNING [slab_topology.offset_polygon_mm]: offset vertex '
                      u'({:.2f}, {:.2f}) fell outside the original boundary\'s own '
                      u'bounding box — clamped to ({:.2f}, {:.2f}).'.format(x, y, cx, cy))
            clamped.append((cx, cy))
        new_points = clamped

    return new_points


def _scanline_crossings(polygon, coord, axis):
    """
    Sorted crossing coordinates where `polygon`'s edges cross a
    scanline at `coord` on `axis`: axis='x' is a HORIZONTAL scanline
    (fixed y=coord), returning the x-coordinates it crosses the
    polygon at; axis='y' is a VERTICAL scanline (fixed x=coord),
    returning y-crossings. Standard even-odd polygon-scanline
    algorithm — edges parallel to the scan direction contribute no
    crossing (a coincident edge is a degenerate case this module
    doesn't attempt to resolve specially).
    """
    n = len(polygon)
    crossings = []
    for i in range(n):
        x1, y1 = polygon[i]
        x2, y2 = polygon[(i + 1) % n]
        if axis == 'x':
            a, b, pa, pb = y1, y2, x1, x2
        else:
            a, b, pa, pb = x1, x2, y1, y2
        if a == b:
            continue
        if (a <= coord < b) or (b <= coord < a):
            t = (coord - a) / (b - a)
            crossings.append(pa + t * (pb - pa))
    crossings.sort()
    return crossings


def _pair_up(xs):
    return [(xs[i], xs[i + 1]) for i in range(0, len(xs) - 1, 2)]


def _subtract_intervals(base, remove):
    """base minus every interval in `remove` — splits a base interval
    in two if a removed interval falls strictly inside it."""
    result = list(base)
    for (r0, r1) in remove:
        nxt = []
        for (b0, b1) in result:
            if r1 <= b0 or r0 >= b1:
                nxt.append((b0, b1))
                continue
            if r0 > b0:
                nxt.append((b0, min(r0, b1)))
            if r1 < b1:
                nxt.append((max(r1, b0), b1))
        result = nxt
    return [iv for iv in result if iv[1] - iv[0] > 1e-6]


def material_intervals(outer, large_holes, coord, axis, inset_mm=0.0):
    """
    The concrete-present intervals along `axis` at scanline `coord`:
    `outer`'s own scanline intervals minus every large hole's — see
    module docstring's COVER INSET note for what `inset_mm` does and
    its disclosed limitation on diagonal edges.

    Args:
        outer       (list[(float,float)]): from classify_loops.
        large_holes (list[list[(float,float)]]): from classify_loops.
        coord       (float): the scanline's fixed coordinate, mm.
        axis        (str): 'x' (horizontal scan) or 'y' (vertical scan).
        inset_mm    (float): shrink each resulting interval by this much
                    on BOTH ends (0 = no inset, the raw boundary).

    Returns:
        list[(float, float)] — sorted, non-overlapping (lo_mm, hi_mm)
        intervals, each with positive length.
    """
    ivs = _pair_up(_scanline_crossings(outer, coord, axis))
    for hole in large_holes:
        hole_ivs = _pair_up(_scanline_crossings(hole, coord, axis))
        ivs = _subtract_intervals(ivs, hole_ivs)
    if inset_mm:
        ivs = [(lo + inset_mm, hi - inset_mm) for lo, hi in ivs]
        ivs = [iv for iv in ivs if iv[1] - iv[0] > 1e-6]
    return ivs
