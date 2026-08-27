# -*- coding: utf-8 -*-
"""
NOSA.RebarAutomate — Floor/Slab Rebar (Phase 2, refactored 2.2, hardened 2.3)
============================================================================

Category module for structural floor slabs (OST_Floors). Loads
rebar_engine.py, footing_rebar.py and slab_topology.py in isolation via
nosa_utils.bootstrap.load_module (unique aliases), matching this
extension's established sys.modules isolation convention.

PHASE 2.2 — REAL TOPOLOGY, NOT A BOUNDING BOX (background)
------------------------------------------------------------------
Replaced host.get_BoundingBox(None)-only positioning with real face
topology (slab_topology.py) — outer boundary + large interior openings
extracted from Face.GetEdgesAsCurveLoops, scanline-clipped per row —
fixing bars generated outside the concrete at irregular edges, bars
running through large openings, and unsplit bars exceeding stock
length.

PHASE 2.3 — PRODUCTION HARDENING (this revision)
------------------------------------------------------------------
Live testing of 2.2 found four more blockers:

  1. UI/preview — handled entirely in ui.xaml/ui.py/rebar_preview.py,
     not this module.

  2. MRA / Rebar Sets: 2.2 made EVERY clipped segment an individual
     Rebar element — correct geometry, but thousands of bars on a real
     floor, none groupable for Multi-Rebar Annotation or fast
     schedules. Fixed here by GROUPING: for each scan direction, rows
     are compared row-to-row: a maximal run of CONSECUTIVE rows whose
     clipped interval list is IDENTICAL (same count, same bounds
     within a small tolerance — i.e. a genuinely rectangular sub-zone,
     the common case away from any hole/chamfer) becomes ONE Rebar Set
     per interval slot, propagated across the run via the same
     create_rebar_set/SetLayoutAsMaximumSpacing mechanism already
     proven for footings. Only rows that DON'T fit into any such
     run — the genuinely irregular transition rows near a chamfer or a
     hole's non-axis-aligned edge — fall back to individual bars, a
     small fraction of a normal floor's total bar count, not all of
     it.

     NOT IMPLEMENTED: the brief also suggested Rebar.CreateFreeFormRebar
     for the irregular remainder specifically, on the theory that it
     produces "a single variable-length Rebar Set compatible with
     MRA". This module deliberately does NOT call that API. Free Form
     Rebar in the Revit Structure API is built for genuinely complex
     3D-swept rebar shapes; nothing in this project has ever exercised
     it, and there is no verified evidence it represents "several
     straight bars of different lengths, grouped for MRA" the way the
     brief assumes. Guessing at an entirely new, never-tested API
     surface risked burning a live-test cycle on a call that might not
     even compile. The individual-bar fallback below is the same
     proven create_from_curves path every other bar in this plugin
     already uses — safe, if not MRA-grouped, for that small remainder.

  3. Cover violation: 2.2's `material_intervals(..., inset_mm=...)`
     only ever insets along the SCAN AXIS, which under-covers a bar
     near a diagonal/chamfered edge. Fixed by actually offsetting the
     polygons themselves BEFORE clipping —
     slab_topology.offset_polygon_mm shrinks the outer boundary inward
     by the real cover and grows every large hole outward by it — see
     that function's own docstring. The residual inset_mm passed to
     material_intervals is now only half the bar's OWN diameter (the
     small centreline-to-outer-face distance), not the full cover.

  4. Perimeter closure U-bars protruding in narrow zones: a fixed
     40x-diameter leg length can exceed half the available material
     width between two nearby edges (a narrow strip between two holes,
     or between a hole and the outer edge), making the two opposing
     legs collide and poke out of the concrete. A CLOSED LINK (a
     StirrupTie-style closed rectangular tie spanning bottom-to-top at
     that narrow interval) replaces the two U-bars entirely wherever
     they wouldn't both fit — exactly as one stirrup replaces two
     colliding hooks in a narrow rib. See PHASE 3.1 below for how "wide
     enough" is now decided.

PHASE 3.1 — REGRESSION-CRITICAL FIXES: leg length is now BINARY, and
every closure-U-bar/hooked-leg coordinate is rounded before use
------------------------------------------------------------------
Two live-test bugs, found together, share one root cause and one fix:

  a. LAP-SPLICE MINIMUM (was silently violated): the item-4 fix above
     originally read as "dynamic leg length — min(40x diameter,
     available_width/2 - cover)" — i.e. whenever an interval was wide
     enough to avoid the CLOSED LINK fallback but not wide enough for
     two full 40x-diameter legs plus a cover gap between their tips,
     the leg length was silently SHRUNK below the normative minimum
     (down to as little as 1mm, per the old `max(leg_mm, 1.0)` floor).
     A U-bar leg shorter than 40x its own diameter does not anchor
     into the opposite mat as a real lap splice requires.

  b. "SHAPE 00" (generic) INSTEAD OF "SHAPE 21" (U-bar): Revit's
     RebarShapeMatch has to fit a bend radius into each leg; a leg
     shrunk down near that old 1mm floor is nowhere near long enough
     for that, so the shape recognizer gives up and the bar is created
     as an unrecognized generic shape instead of the normative U-bar.

  FIX for both: `_closure_treatments` no longer has a middle,
  "shrunk-leg" outcome at all. It is now a strict BINARY choice per
  interval — either BOTH legs get the full, code-derived
  `nominal_leg_mm` (always >= 40x diameter, always long enough for a
  normal bend radius), or the interval is judged too narrow for that
  and gets a CLOSED LINK instead. "Too narrow" is now measured
  explicitly against `2 * nominal_leg_mm + gap_cover_mm` — i.e. both
  full legs AND a clear cover gap between their facing tips have to
  fit — instead of only checking that after the fact via capping.
  DO NOT reintroduce a `min(nominal_leg_mm, ...)`-style cap here: any
  future change to this interval-width threshold must keep leg_mm
  either exactly `nominal_leg_mm` or absent (link), never a computed
  fraction of it.

  c. Floating-point drift feeding the same shape-match failure: even
     with (a)/(b) fixed, a curve endpoint computed from
     slab_topology's scanline/offset math can land a few ULPs off an
     otherwise-exact mm value (e.g. 1499.999999999997 instead of
     1500.0), which is enough for two segments in the same chain that
     are SUPPOSED to be exactly perpendicular/coincident to fail
     RebarShapeMatch's tolerance. Fixed by rounding every row/edge/lo/
     hi mm coordinate through the new `_round_mm()` helper immediately
     before it is used to build a DB.XYZ/DB.Line — see that function's
     own docstring. Any NEW curve-construction helper added to this
     module (main-grid bars, closure U-bars, or otherwise) must round
     its mm inputs the same way before building points, or this bug
     class can resurface for that helper specifically.

Everything above uses the SAME Z-layering (B1/B2/T1/T2), full-depth-leg,
and stock-length-splitting logic already built in earlier phases —
these phases change WHERE reinforcement is grouped, how narrow zones
are handled, and how leg-length/coordinates are computed, not the
underlying cover/Z/hook conventions.
"""
import os

_HERE = os.path.dirname(os.path.abspath(__file__))
re_engine = None
footing_rebar_mod = None
slab_topology = None

# PHASE 3.5.5 item 2 — explicit .NET exception type for
# _build_edge_ubars's per-edge except clause, on top of Python's own
# Exception, per an explicit request to guarantee a .NET-side failure
# (e.g. Autodesk.Revit.Exceptions.ArgumentException from
# DB.Line.CreateBound) is caught just as reliably as a Python-side one
# — even though IronPython's CLR interop already unifies the two
# hierarchies under plain `Exception` in practice. Guarded: `System`
# is always resolvable inside Revit/pyRevit, but this module is also
# loaded standalone by this project's own mocked test suite outside
# any .NET runtime, where it must stay None rather than fail to import.
try:
    import System
except Exception:
    System = None
_EDGE_EXCEPTION_TYPES = (Exception,) if System is None else (Exception, System.Exception)


def _ensure_engine():
    global re_engine
    if re_engine is None:
        # PHASE F0 — migrated from imp.load_source to
        # nosa_utils.bootstrap.load_module (tries importlib first,
        # falls back to imp). Registered name unchanged.
        from nosa_utils.bootstrap import load_module
        re_engine = load_module('re_engine', os.path.join(_HERE, 'rebar_engine.py'))
    return re_engine


def _ensure_footing_rebar():
    global footing_rebar_mod
    if footing_rebar_mod is None:
        from nosa_utils.bootstrap import load_module
        footing_rebar_mod = load_module(
            'footing_rebar_mod', os.path.join(_HERE, 'footing_rebar.py'))
    return footing_rebar_mod


def _ensure_topology():
    global slab_topology
    if slab_topology is None:
        from nosa_utils.bootstrap import load_module
        slab_topology = load_module(
            'slab_topology', os.path.join(_HERE, 'slab_topology.py'))
    return slab_topology


_MM_PER_FT = 304.8

# mm-coordinate rounding grain applied immediately before any curve
# endpoint is built (PHASE 3.1 item 3 — "Shape 00" fix, see
# _round_mm's own docstring below).
_COORD_ROUND_NDIGITS = 6


def _round_mm(value_mm):
    """
    PHASE 3.1 item 3 fix ("Shape 00" U-bars): round a coordinate, in
    mm, to a fixed, tiny grain (1e-6 mm — far finer than any real
    tolerance, purely to kill floating-point noise) immediately before
    it is used to build a DB.XYZ/DB.Line endpoint.

    Why this exists: coordinates that feed the perimeter closure
    U-bars and the main-grid hooked legs originate from
    slab_topology's scanline clipping and polygon-offset arithmetic
    (line-line intersections, offset-normal math) — operations that
    can leave a value that is CONCEPTUALLY exact (e.g. "this edge is
    at Y=1500.0mm") sitting a few ULPs off (1499.999999999997). Two
    curves in the same chain that both reference "the same" edge but
    arrived at it through slightly different arithmetic paths can then
    end up not-quite-coincident or not-quite-perpendicular by a
    sub-micron amount — invisible to a human, but enough for Revit's
    internal RebarShapeMatch (used to recognise a curve chain as a
    normative shape, e.g. Shape 21/U-bar) to reject the chain and fall
    back to a generic "Shape 00". Rounding every coordinate to a
    common, tiny grain right before curve construction guarantees any
    two endpoints that are SUPPOSED to coincide (or any two segments
    that are SUPPOSED to be perpendicular) actually do/are, in exact
    floating-point terms, without affecting real-world accuracy by
    anything a tape measure could register.
    """
    return round(value_mm, _COORD_ROUND_NDIGITS)


# PHASE 3.5.1 item 2 — same epsilon convention as
# column_rebar._AXIS_CLAMP_EPSILON_MM, duplicated here (not imported)
# so this module stays self-contained per its own established pattern.
_Z_CLAMP_EPSILON_MM = 2.0
_Z_CLAMP_EPSILON_FT = _Z_CLAMP_EPSILON_MM / _MM_PER_FT


def _solid_z_extent_ft(solid):
    """
    Same contract as column_rebar._solid_z_extent_ft — duplicated here
    (not imported) so this module stays self-contained; see that
    module's copy for the full derivation/edge-case notes. Returns
    (min_z_ft, max_z_ft) read from the solid's own Edges, or None if
    `solid` is None or exposes no usable Edges (e.g. a mocked/test
    solid) — callers fall back to their existing face-derived Z in
    that case, unchanged from pre-3.5.1 behaviour.
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


def _clamp_z_to_solid_ft(z_ft, z_extent_ft):
    """
    PHASE 3.5.1 item 2 fix — live floor U-bars kept throwing
    Rebar.CreateFromCurves "Internal Error" (reported x54 on one real
    floor): the B1/B2/T1/T2 Z values below were computed purely from
    Face.origin.Z (a single evaluated point per face, per this
    module's own flat-face SCOPE assumption) with no check against the
    floor's REAL solid — if the floor's actual geometry pinches
    thinner than that single evaluated point implies anywhere along
    its own boundary (a shape-edited slab, a non-uniform thickened
    region, or a face whose evaluation point isn't perfectly
    representative of the whole plate), every curve built from that Z
    silently assumed a thickness that wasn't there.

    Clamps `z_ft` to lie strictly inside `z_extent_ft` (the real
    solid's own Min/Max Z, from _solid_z_extent_ft), inset by
    _Z_CLAMP_EPSILON_FT for the same floating-point-boundary reason as
    column_rebar.get_column_axis's identical clamp. Falls straight
    through unchanged if z_extent_ft or z_ft is None (solid unreadable
    — matches this module's pre-3.5.1 behaviour exactly, including
    every existing mocked test, since a mock Solid exposes no .Edges).
    """
    if z_extent_ft is None or z_ft is None:
        return z_ft
    lo_ft, hi_ft = z_extent_ft
    lo_clamped = lo_ft + _Z_CLAMP_EPSILON_FT
    hi_clamped = hi_ft - _Z_CLAMP_EPSILON_FT
    if hi_clamped <= lo_clamped:
        lo_clamped, hi_clamped = lo_ft, hi_ft
    return min(max(z_ft, lo_clamped), hi_clamped)


# ══════════════════════════════════════════════════════════════════════════
# Run grouping — the shared "identical consecutive rows -> one Set" engine
# ══════════════════════════════════════════════════════════════════════════

def _group_uniform_runs(rows_with_data, equal_fn):
    """
    `rows_with_data`: list of (row_mm, data). Returns a list of runs —
    each a list of (row_mm, data) — split wherever equal_fn(data_i,
    data_{i-1}) is False. A run of length >= 2 means every row in it
    shares the identical `data` (per equal_fn), and so can become ONE
    Rebar Set spanning that run instead of N individual bars.
    """
    if not rows_with_data:
        return []
    runs = [[rows_with_data[0]]]
    for item in rows_with_data[1:]:
        if equal_fn(item[1], runs[-1][-1][1]):
            runs[-1].append(item)
        else:
            runs.append([item])
    return runs


def _intervals_equal(a, b, tol=0.5):
    if len(a) != len(b):
        return False
    return all(abs(a[i][0] - b[i][0]) < tol and abs(a[i][1] - b[i][1]) < tol for i in range(len(a)))


def _warn_if_outside_bbox(x_mm, y_mm, xmin_mm, xmax_mm, ymin_mm, ymax_mm, label, tol=1.0):
    """
    PHASE 2.5 item 3 — a direct diagnostic requested against the
    "protruding bars" report: any generated bar endpoint that falls
    outside the floor's own (already cover-offset) boundary bounding
    box prints a console warning naming exactly which point and by how
    much. With slab_topology.offset_polygon_mm's own bbox clamp (see
    that function) this should never actually fire for a correctly
    clipped bar — it exists to surface the FIRST sign of a regression
    here rather than let one ship silently.
    """
    if (x_mm < xmin_mm - tol or x_mm > xmax_mm + tol or
            y_mm < ymin_mm - tol or y_mm > ymax_mm + tol):
        print(u'WARNING [floor_rebar]: {} endpoint ({:.1f}, {:.1f}) falls outside '
              u'the floor\'s own boundary bounding box ([{:.1f}, {:.1f}] x '
              u'[{:.1f}, {:.1f}]) — geometry may be protruding.'.format(
                  label, x_mm, y_mm, xmin_mm, xmax_mm, ymin_mm, ymax_mm))


# ══════════════════════════════════════════════════════════════════════════
# Main grid
# ══════════════════════════════════════════════════════════════════════════

def _finalize_bar_pieces(engine, footing_mod, line, max_stock_length_mm, lap_length_mm,
                          use_legs, leg_length_mm, leg_direction):
    """
    One clipped, straight bar segment -> a list of curve chains: split
    into stock-length pieces (with normative lap splices) if needed,
    and — only at a piece's TRUE original end, never at an internal
    lap-splice cut — a full-depth U-bar leg via footing_rebar.add_end_hooks,
    if use_legs.
    """
    segments = engine.split_rebar_by_stock_length(line, max_stock_length_mm, lap_length_mm)
    chains = []
    for seg in segments:
        at_start = use_legs and not seg.has_start_lap
        at_end = use_legs and not seg.has_end_lap
        if at_start or at_end:
            chain = footing_mod.add_end_hooks(seg.curve, leg_length_mm, leg_direction,
                                               at_start=at_start, at_end=at_end)
        else:
            chain = [seg.curve]
        chains.append(chain)
    return chains


def _build_direction_bars(topo, footing_mod, engine, DB, outer, large_holes, own_axis,
                           own_dia_mm, perp_dia_mm, row_spacing_mm,
                           xmin_mm, xmax_mm, ymin_mm, ymax_mm, own_z_ft,
                           max_stock_length_mm, use_legs, leg_length_mm, leg_direction,
                           narrow_threshold_mm=None):
    """
    Every bar for ONE main-grid direction ('x' = along_x/Layer 1,
    running in X, one row per Y; 'y' = along_y/Layer 2, running in Y,
    one row per X) — real cover already baked into `outer`/`large_holes`
    (the caller passes the already-offset polygons; see
    build_floor_reinforcement), residual inset here is only half the
    bar's own diameter. Consecutive rows sharing an identical clipped
    interval list are grouped into ONE Rebar Set per interval slot;
    everything else falls back to individual bars — see module
    docstring's Phase 2.3 item 2.

    Args:
        narrow_threshold_mm (float or None): PHASE 2.4 item 3 — if
                             given, any clipped interval narrower than
                             this is skipped entirely (no main bar
                             generated for it at all). Set by the
                             caller to the SAME 2x-nominal-leg
                             threshold the perimeter closure U-bars use
                             on this axis, and ONLY when closure U-bars
                             are active: a zone this narrow is exactly
                             the kind of rib _build_edge_ubars' own
                             material-containment check (Phase 3.5)
                             falls back to a closed link for — a
                             separate straight main bar in that same
                             sliver would just be redundant clutter,
                             reported live as "basura" inside the
                             closed link.

    Returns:
        {'sets': [{'curves','normal','array_length_mm','spacing_mm'}],
         'bars': [{'curves','normal'}]}
    """
    own_inset_mm = own_dia_mm / 2.0
    perp_inset_mm = perp_dia_mm / 2.0
    if own_axis == 'x':
        row_lo, row_hi = ymin_mm + perp_inset_mm, ymax_mm - perp_inset_mm
        bar_direction = DB.XYZ(1.0, 0.0, 0.0)
        propagation_reference = DB.XYZ(0.0, 1.0, 0.0)
    else:
        row_lo, row_hi = xmin_mm + perp_inset_mm, xmax_mm - perp_inset_mm
        bar_direction = DB.XYZ(0.0, 1.0, 0.0)
        propagation_reference = DB.XYZ(1.0, 0.0, 0.0)
    rows_mm = footing_mod._evenly_spaced(row_lo, row_hi, row_spacing_mm)
    lap_length_mm = footing_mod.default_anchorage_length_mm(own_dia_mm)
    # PHASE 2.6 FIX ("flying bars") — bar_direction x global-Z has a
    # FIXED rotational handedness (see
    # rebar_engine.compute_vertical_hook_plane_normal's own Phase 5.6
    # note): it only agrees with ONE of the two perpendicular
    # directions' "propagate INTO the floor" sign, sending the whole
    # Rebar Set for the other direction backwards — entirely outside
    # the slab, parallel to the edge it should have started from. This
    # was fixed once already for footings (Phase 5.6) by passing
    # propagation_reference; that fix never carried over here because
    # this function used to build individual bars only, where the sign
    # didn't matter — Phase 2.3 reintroduced Rebar Sets for uniform
    # runs without restoring it.
    normal = engine.compute_vertical_hook_plane_normal(
        bar_direction, propagation_reference=propagation_reference)

    rows_with_ivs = []
    for row in rows_mm:
        ivs = topo.material_intervals(outer, large_holes, row, axis=own_axis, inset_mm=own_inset_mm)
        if narrow_threshold_mm is not None:
            ivs = [iv for iv in ivs if (iv[1] - iv[0]) >= narrow_threshold_mm]
        rows_with_ivs.append((row, ivs))

    def _make_line(row, lo_mm, hi_mm):
        row = _round_mm(row)
        lo_mm = _round_mm(lo_mm)
        hi_mm = _round_mm(hi_mm)
        if own_axis == 'x':
            x0_mm, y0_mm, x1_mm, y1_mm = lo_mm, row, hi_mm, row
        else:
            x0_mm, y0_mm, x1_mm, y1_mm = row, lo_mm, row, hi_mm
        _warn_if_outside_bbox(x0_mm, y0_mm, xmin_mm, xmax_mm, ymin_mm, ymax_mm,
                               'along_{} main bar'.format(own_axis))
        _warn_if_outside_bbox(x1_mm, y1_mm, xmin_mm, xmax_mm, ymin_mm, ymax_mm,
                               'along_{} main bar'.format(own_axis))
        p0 = DB.XYZ(x0_mm / _MM_PER_FT, y0_mm / _MM_PER_FT, own_z_ft)
        p1 = DB.XYZ(x1_mm / _MM_PER_FT, y1_mm / _MM_PER_FT, own_z_ft)
        return DB.Line.CreateBound(p0, p1)

    sets, bars = [], []
    for run in _group_uniform_runs(rows_with_ivs, _intervals_equal):
        first_row, ivs = run[0]
        if len(run) < 2:
            for (lo_mm, hi_mm) in ivs:
                line = _make_line(first_row, lo_mm, hi_mm)
                for chain in _finalize_bar_pieces(engine, footing_mod, line, max_stock_length_mm,
                                                   lap_length_mm, use_legs, leg_length_mm, leg_direction):
                    bars.append({'curves': chain, 'normal': normal})
            continue
        last_row = run[-1][0]
        array_length_mm = abs(last_row - first_row)
        for (lo_mm, hi_mm) in ivs:
            # Materialize EVERY row's own chain for this interval slot
            # (Phase 2.5 item 2) — a Rebar Set's own
            # SetLayoutAsMaximumSpacing propagation is not guaranteed
            # to succeed for every shape (see rebar_engine.py's own
            # confidence notes); ui.py's creation step needs the FULL
            # per-row geometry on hand so a failed Set can be rebuilt
            # via create_freeform_group instead of silently staying a
            # single un-propagated bar ("zero loose bars", per the
            # brief). Since every row in a uniform run shares the
            # identical (lo_mm, hi_mm), the split-piece COUNT and lap
            # pattern is identical too — only the row coordinate
            # differs — so each piece slot k lines up 1:1 across rows.
            per_row_chains = [
                _finalize_bar_pieces(engine, footing_mod, _make_line(row, lo_mm, hi_mm),
                                     max_stock_length_mm, lap_length_mm,
                                     use_legs, leg_length_mm, leg_direction)
                for row, _ in run
            ]
            n_pieces = len(per_row_chains[0])
            for k in range(n_pieces):
                materialized = [{'curves': per_row_chains[r][k], 'normal': normal}
                                 for r in range(len(run))]
                sets.append({'curves': per_row_chains[0][k], 'normal': normal,
                             'array_length_mm': array_length_mm, 'spacing_mm': row_spacing_mm,
                             'materialized_bars': materialized})
    return {'sets': sets, 'bars': bars}


# ══════════════════════════════════════════════════════════════════════════
# Perimeter Closure U-Bars — ONE continuous Set per polygon EDGE (Phase 3.5)
# ══════════════════════════════════════════════════════════════════════════

# PHASE 3.5.3/3.5.4 item 3 — test offset for the empirical
# inward-normal resolution below, mm. Raised from 1.0mm to 10.0mm
# (Phase 3.5.4): live U-Bar failures persisted with the smaller
# offset — a 1mm test point sits too close to a real, tessellated
# boundary (Revit-side coordinate/tolerance noise, or the ray-casting
# test itself landing ambiguously right at an edge), producing
# occasional false reads. 10mm clears that comfortably while staying
# well inside even a narrow structural rib (e.g. this module's own
# 200mm-wide-rib-between-two-holes test case leaves 90mm of margin on
# each side) and well below slab_topology's own 15mm minimum edge
# length, so it never crosses past the edge's own extent either.
_INWARD_NORMAL_TEST_OFFSET_MM = 10.0


def _resolve_inward_normal_mm(p0_mm, p1_mm, raw_normal, is_hole, topo, outer, large_holes):
    """
    PHASE 3.5.3 item 2 FIX — which of the two directions perpendicular
    to this edge actually points into REAL material, decided by
    testing directly against slab_topology.point_in_material_mm (the
    same ground-truth material test this module already trusts
    elsewhere for leg-tip validation) — not by trusting the
    theoretical "outer boundary CCW / hole CW" Revit winding
    convention this function used to assume unconditionally. That
    convention is common but not GUARANTEED for every real,
    tessellated boundary (edited sketches, self-intersection repairs,
    imported geometry) — live U-Bar failures traced to exactly that:
    an inward_normal computed from winding alone, pointing outward for
    some real edges. The geometry itself is now the source of truth,
    not an assumption about how Revit built the loop.

    Tests a point offset _INWARD_NORMAL_TEST_OFFSET_MM from the edge's
    own midpoint along `raw_normal`; if that lands in material,
    raw_normal IS the inward normal. Otherwise tests the FLIPPED
    direction. If NEITHER test point lands in material (a
    pathologically thin sliver this test can't resolve either way),
    falls back to the theoretical winding-based convention (raw_normal
    for the outer boundary, flipped for a hole loop) as a last resort
    rather than guessing further.

    Args:
        p0_mm, p1_mm     ((float,float)): this edge's own endpoints, mm.
        raw_normal       ((float,float)): the winding-derived normal
                         from slab_topology.polygon_edges_mm, unit.
        is_hole          (bool): whether this edge belongs to a hole
                         loop — only consulted for the last-resort
                         fallback.
        topo, outer, large_holes  as elsewhere — passed straight to
                         point_in_material_mm.

    Returns:
        (nx, ny) — unit vector, empirically confirmed (or, in the
        fallback case, assumed) to point into material.
    """
    mx = (p0_mm[0] + p1_mm[0]) / 2.0
    my = (p0_mm[1] + p1_mm[1]) / 2.0

    def _in_material(direction):
        return topo.point_in_material_mm(
            mx + direction[0] * _INWARD_NORMAL_TEST_OFFSET_MM,
            my + direction[1] * _INWARD_NORMAL_TEST_OFFSET_MM,
            outer, large_holes)

    if _in_material(raw_normal):
        return raw_normal
    flipped = (-raw_normal[0], -raw_normal[1])
    if _in_material(flipped):
        return flipped
    return flipped if is_hole else raw_normal


def _snap_normal_to_cardinal_mm(p0_mm, p1_mm, normal, topo, outer, large_holes,
                                 test_offset_mm=_INWARD_NORMAL_TEST_OFFSET_MM):
    """
    PHASE 3.5.7 item 3 — snap `normal` (already confirmed to point into
    material, via _resolve_inward_normal_mm) to whichever CARDINAL
    direction (+X, -X, +Y, -Y) it is closest to, so a U-bar leg on a
    DIAGONAL/chamfered edge still runs parallel to the main
    reinforcement mat's own X/Y bar directions — a leg embedded in the
    mat should read, and lap, as part of it rather than crossing it at
    an arbitrary diagonal angle.

    Never sacrifices correctness for this constructability preference:
    re-verifies the SNAPPED direction still points into material
    before accepting it (via the same point_in_material_mm ground
    truth this module already trusts elsewhere) — for a chamfer close
    to another hole/the outer boundary, snapping to a cardinal
    direction could point the leg where the diagonal one didn't. Falls
    back to the original, already-confirmed `normal` unchanged if the
    snapped direction fails that check. For an edge whose `normal` is
    ALREADY cardinal (the ordinary axis-aligned case), the snap
    trivially returns the identical direction — no special-casing
    needed, since it's already the closest cardinal to itself.

    Returns:
        (nx, ny) — the snapped cardinal direction if confirmed safe,
        otherwise the original `normal` unchanged.
    """
    candidates = [(1.0, 0.0), (-1.0, 0.0), (0.0, 1.0), (0.0, -1.0)]
    snapped = max(candidates, key=lambda c: c[0] * normal[0] + c[1] * normal[1])
    mx = (p0_mm[0] + p1_mm[0]) / 2.0
    my = (p0_mm[1] + p1_mm[1]) / 2.0
    if topo.point_in_material_mm(mx + snapped[0] * test_offset_mm,
                                  my + snapped[1] * test_offset_mm,
                                  outer, large_holes):
        return snapped
    return normal


def _link_loop_edge(DB, p0_mm, p1_mm, bottom_z_ft, top_z_ft):
    """
    A closed 4-segment vertical rectangle spanning the SHORT edge
    p0_mm->p1_mm (a StirrupTie-style tie), used by _build_edge_ubars
    whenever an edge is too short for even one corner-inset U-bar —
    the same narrow-zone closed-link fallback footing_rebar/older
    floor_rebar phases already established, just anchored to the
    edge's own two endpoints instead of a scanline interval's.
    """
    x0, y0 = _round_mm(p0_mm[0]), _round_mm(p0_mm[1])
    x1, y1 = _round_mm(p1_mm[0]), _round_mm(p1_mm[1])
    c0 = DB.XYZ(x0 / _MM_PER_FT, y0 / _MM_PER_FT, bottom_z_ft)
    c1 = DB.XYZ(x1 / _MM_PER_FT, y1 / _MM_PER_FT, bottom_z_ft)
    c2 = DB.XYZ(x1 / _MM_PER_FT, y1 / _MM_PER_FT, top_z_ft)
    c3 = DB.XYZ(x0 / _MM_PER_FT, y0 / _MM_PER_FT, top_z_ft)
    corners = [c0, c1, c2, c3]
    return [DB.Line.CreateBound(corners[i], corners[(i + 1) % 4]) for i in range(4)]


def _build_edge_ubars(topo, footing_mod, DB, outer, large_holes,
                       x_leg_mm, x_spacing_mm, b1_z_ft, t1_z_ft,
                       y_leg_mm, y_spacing_mm, b2_z_ft, t2_z_ft):
    """
    PHASE 3.5 item 5 — STRUCTURAL REWRITE: perimeter closure U-bars are
    no longer derived from the main grid's scanline (which fragmented a
    single continuous boundary into one bar per row interval, breaking
    at every hole/chamfer transition). Instead, this walks the floor's
    own TOPOLOGICAL polygon — the outer boundary plus every large
    interior opening, each already cover-offset by the caller — one
    EDGE (vertex-to-vertex straight segment) at a time, and produces
    ONE continuous Rebar Set of U-bars spanning that edge's ENTIRE
    length, corner-to-corner. A real slab edge closes with one
    uninterrupted run of ties, not a chain of fragments — this matches
    that reality directly instead of reconstructing it from a
    perpendicular scan.

    Per edge:
      - Classified as X-anchoring (edge runs mostly along Y — it is
        where the along_x mat's bars TERMINATE, so it needs to anchor
        B1/T1) or Y-anchoring (edge runs mostly along X — anchors
        B2/T2), by comparing the edge's own unit direction components;
        a perfectly diagonal edge (|ux| == |uy|) ties to Y, an
        arbitrary but harmless tie-break.
      - U-bar positions are distributed EVENLY along the edge's own
        length, INSET FROM EACH VERTEX by that anchor's own nominal
        leg length (x_leg_mm/y_leg_mm) — "restando los recubrimientos
        en los vértices" — so two edges meeting at a corner never place
        a U-bar back exactly on the miter point, and their (differently
        directed) legs never crowd that shared corner.
      - Each U-bar's leg points along the edge's own WINDING-AWARE
        INWARD NORMAL (slab_topology.polygon_edges_mm) rather than a
        fixed +-X/+-Y — correct for a diagonal/chamfered edge, not just
        an axis-aligned one.
      - If the edge is too short to fit even ONE corner-inset U-bar
        (length <= 2x the nominal leg), it gets ONE closed link
        (_link_loop_edge) spanning its own full length instead — the
        same "too narrow for opposing legs -> closed tie" principle
        used everywhere else in this project, just per-edge now.
      - >= 2 positions along one edge become ONE Rebar Set
        (SetLayoutAsMaximumSpacing, propagated along the edge's own
        direction); a single position stays an individual bar.

    DISCLOSED LIMITATION: this version does NOT detect a U-bar leg from
    one edge crossing INTO a nearby, geometrically close edge/hole (a
    narrow rib between two openings, or between a hole and the outer
    boundary) UNLESS the resulting leg would actually cross into
    another opening or past the outer edge — checked directly via
    slab_topology.point_in_material_mm at every position's own leg
    tip, edge-by-edge: if ANY position along an edge would poke a leg
    into material that isn't there (e.g. a narrow rib between two
    holes, or a hole close to the outer boundary), the WHOLE edge
    falls back to ONE closed link spanning its own full length instead
    of open U-bars — same "too narrow for opposing legs -> closed tie"
    principle as the too-short-edge case above, just triggered by an
    actual collision instead of by raw edge length. This is a courser
    check than the old scanline's own per-row interval width (it
    doesn't shrink/adjust anything mid-edge, only flips the WHOLE edge
    to a link), but it directly restores "narrow rib gets a closed
    link, not colliding legs" without reintroducing a shrunk/degenerate
    leg length.

    Args:
        topo, footing_mod, DB   as elsewhere.
        outer, large_holes      (already cover-offset) polygons, mm —
                                see build_floor_reinforcement.
        x_leg_mm, x_spacing_mm  (float): nominal leg length / row
                                spacing for X-anchoring edges (B1/T1).
        b1_z_ft, t1_z_ft        (float): Z, ft, for X-anchoring edges'
                                back spine (bottom mat to top mat).
        y_leg_mm, y_spacing_mm  (float): same, for Y-anchoring edges
                                (B2/T2).
        b2_z_ft, t2_z_ft        (float): Z, ft, for Y-anchoring edges.

    Returns:
        {'x_bars': {'sets':[...],'bars':[...]},
         'y_bars': {'sets':[...],'bars':[...]},
         'debug_failed_edges': [{'p0_mm','p1_mm','bz_ft','tz_ft',
                                  'inward_normal','error'}, ...]}
        — x_bars/y_bars keep the exact per-direction shape
        build_floor_reinforcement's callers (ui.py's
        _create_perimeter_closure_ubars) already expect; debug_failed_edges
        (Phase 3.5.3 item 3) is empty in the normal case — a diagnostic
        record only (also already printed to the console by this
        function's own per-edge except block below); PHASE 3.5.4 —
        ui.py does NOT draw ModelCurve elements from this any more
        (creating one without a SketchPlane guaranteed to exactly
        contain the curve threw a hard exception mid-Transaction,
        rolling back the whole floor) — console telemetry only.
    """
    x_sets, x_bars_out = [], []
    y_sets, y_bars_out = [], []
    debug_failed_edges = []

    loops = [(False, outer)] + [(True, h) for h in large_holes]
    for is_hole, loop in loops:
        edges = topo.polygon_edges_mm(loop)
        # PHASE 3.5.6 item 3 — offset_polygon_mm's own disclosed
        # limitation (slab_topology.py module docstring): a narrow
        # re-entrant notch offset outward by more than ~2x the cover
        # (always the case for a hole, which is grown OUTWARD, away
        # from material) can self-intersect into a bow-tied polygon
        # that isn't detected or repaired. That failure mode doesn't
        # raise an exception — it just quietly produces very few (or
        # zero) valid edges once _MIN_EDGE_LENGTH_MM filters them, so
        # a real "large" opening (by area) can end up with NO
        # perimeter closure U-bars at all with no error anywhere.
        # Flagged here as the earliest point this is detectable.
        if is_hole and len(edges) < 3:
            cx = sum(p[0] for p in loop) / len(loop)
            cy = sum(p[1] for p in loop) / len(loop)
            print(u'WARNING [floor_rebar]: a large interior opening near '
                  u'({:.0f}, {:.0f}) mm produced only {} valid edge(s) after the '
                  u'cover offset — it likely self-intersected (a narrow notch '
                  u'offset outward by more than ~2x the cover) and will get FEW '
                  u'OR NO perimeter closure U-bars around it. Verify this opening '
                  u'manually, or widen the narrow notch.'.format(cx, cy, len(edges)))
        for (p0, p1, unit_dir, raw_inward_normal, length_mm) in edges:
            # PHASE 3.5.3 FIX — no longer derived from winding/CW-CCW
            # convention at all (see _resolve_inward_normal_mm's own
            # docstring for why that assumption isn't safe on real,
            # tessellated boundaries). Resolved empirically instead,
            # against the actual material via point_in_material_mm.
            inward_normal = _resolve_inward_normal_mm(
                p0, p1, raw_inward_normal, is_hole, topo, outer, large_holes)
            # PHASE 3.5.7 item 3 — align the leg with the main mat's
            # own X/Y bar directions on a diagonal/chamfered edge,
            # never at the cost of pointing outside material (see
            # _snap_normal_to_cardinal_mm's own docstring).
            inward_normal = _snap_normal_to_cardinal_mm(
                p0, p1, inward_normal, topo, outer, large_holes)
            is_x_anchor = abs(unit_dir[1]) > abs(unit_dir[0])
            if is_x_anchor:
                nominal_leg_mm, spacing_mm, bz, tz = x_leg_mm, x_spacing_mm, b1_z_ft, t1_z_ft
                target_sets, target_bars = x_sets, x_bars_out
            else:
                nominal_leg_mm, spacing_mm, bz, tz = y_leg_mm, y_spacing_mm, b2_z_ft, t2_z_ft
                target_sets, target_bars = y_sets, y_bars_out

            normal_vec = DB.XYZ(unit_dir[0], unit_dir[1], 0.0)
            leg_dir = DB.XYZ(inward_normal[0], inward_normal[1], 0.0)

            def _chain_at(pos, _bz=bz, _tz=tz, _leg=nominal_leg_mm, _dir=leg_dir):
                x_mm, y_mm = _round_mm(pos[0]), _round_mm(pos[1])
                p_bottom = DB.XYZ(x_mm / _MM_PER_FT, y_mm / _MM_PER_FT, _bz)
                p_top = DB.XYZ(x_mm / _MM_PER_FT, y_mm / _MM_PER_FT, _tz)
                back = DB.Line.CreateBound(p_bottom, p_top)
                return footing_mod.add_end_hooks(back, _leg, _dir, at_start=True, at_end=True)

            # PHASE 3.5.2 item 1 — this edge's own curve construction
            # (and the material-containment check just before it) is
            # the ONLY thing in this loop that can throw a live Revit
            # exception (DB.Line.CreateBound on a degenerate/coincident
            # point pair). Previously an uncaught exception here
            # propagated all the way out of build_floor_reinforcement,
            # losing the WHOLE floor's reinforcement (main grid
            # included) over ONE bad edge — the "Internal Error x54"
            # reports. Isolated per-edge now: log the exact edge
            # geometry to the pyRevit console (telemetry only, no UI
            # pop-up — a single stray micro-edge must not interrupt the
            # user) and move on to the next edge, keeping every other
            # edge's reinforcement intact.
            try:
                usable_lo, usable_hi = nominal_leg_mm, length_mm - nominal_leg_mm
                if usable_hi <= usable_lo:
                    chain = _link_loop_edge(DB, p0, p1, bz, tz)
                    target_bars.append({'curves': chain, 'normal': normal_vec, 'style': 'StirrupTie'})
                    continue

                dists_mm = footing_mod._evenly_spaced(usable_lo, usable_hi, spacing_mm)
                positions = [(p0[0] + unit_dir[0] * d, p0[1] + unit_dir[1] * d) for d in dists_mm]

                leg_tips_ok = all(
                    topo.point_in_material_mm(
                        pos[0] + inward_normal[0] * nominal_leg_mm,
                        pos[1] + inward_normal[1] * nominal_leg_mm,
                        outer, large_holes)
                    for pos in positions)
                if not leg_tips_ok:
                    chain = _link_loop_edge(DB, p0, p1, bz, tz)
                    target_bars.append({'curves': chain, 'normal': normal_vec, 'style': 'StirrupTie'})
                    continue

                if len(positions) == 1:
                    target_bars.append({'curves': _chain_at(positions[0]),
                                         'normal': normal_vec, 'style': None})
                else:
                    array_length_mm = abs(dists_mm[-1] - dists_mm[0])
                    materialized = [{'curves': _chain_at(pos), 'normal': normal_vec} for pos in positions]
                    target_sets.append({
                        'curves': materialized[0]['curves'], 'normal': normal_vec,
                        'array_length_mm': array_length_mm, 'spacing_mm': spacing_mm,
                        'materialized_bars': materialized, 'style': None,
                    })
            except _EDGE_EXCEPTION_TYPES as e:
                # PHASE 3.5.4/3.5.5 item 2 — `except Exception` alone
                # already catches .NET exceptions too (IronPython
                # unifies the CLR exception hierarchy with Python's
                # own — a bare DB.Line.CreateBound failure, e.g.
                # Autodesk.Revit.Exceptions.ArgumentException on a
                # degenerate point pair, IS a Python-catchable
                # Exception); _EDGE_EXCEPTION_TYPES also names
                # System.Exception explicitly, per an explicit request
                # for zero ambiguity that a .NET-side failure is
                # caught, so this continue is unconditional: no edge,
                # however it fails, can escape this block and abort
                # the rest of the floor. This code is pure geometry (no
                # doc/Transaction open here — see this function's own
                # Returns docstring), so there is nothing here that
                # could itself corrupt a Transaction; that risk lived
                # entirely in ui.py's now-removed ModelCurve drawing.
                print(u'WARNING [floor_rebar]: perimeter closure U-bar edge FAILED '
                      u'({}) — p0=({:.3f}, {:.3f}) p1=({:.3f}, {:.3f}) mm, '
                      u'bz={:.6f} tz={:.6f} ft — skipping this edge only, the '
                      u'rest of the floor\'s reinforcement continues.'.format(
                          e, p0[0], p0[1], p1[0], p1[1], bz, tz))
                # Diagnostic record only (Phase 3.5.3) — console
                # telemetry above already carries everything needed;
                # ui.py no longer draws ModelCurve elements from this
                # (Phase 3.5.4 item 2 — see build_floor_reinforcement's
                # own docstring for why that was removed).
                debug_failed_edges.append({
                    'p0_mm': p0, 'p1_mm': p1, 'bz_ft': bz, 'tz_ft': tz,
                    'inward_normal': inward_normal, 'error': str(e),
                })
                continue

    return {'x_bars': {'sets': x_sets, 'bars': x_bars_out},
            'y_bars': {'sets': y_sets, 'bars': y_bars_out},
            'debug_failed_edges': debug_failed_edges}


# ══════════════════════════════════════════════════════════════════════════
# Orchestration
# ══════════════════════════════════════════════════════════════════════════

def build_floor_reinforcement(doc, host,
                               bottom_cover_mm, bottom_dia_x_mm, bottom_dia_y_mm,
                               bottom_spacing_mm, bottom_hooks=False,
                               include_top_mat=False, top_cover_mm=None,
                               top_dia_x_mm=None, top_dia_y_mm=None,
                               top_spacing_mm=None, top_hooks=False,
                               include_perimeter_closure_ubars=False,
                               x_anchor_ubar_dia_mm=None, x_anchor_ubar_spacing_mm=None,
                               y_anchor_ubar_dia_mm=None, y_anchor_ubar_spacing_mm=None,
                               max_stock_length_mm=12000.0):
    """
    Phase 2.3 pipeline for one floor/slab host. See module docstring
    for the four hardening fixes over Phase 2.2. Real cover is applied
    ONCE, up front, as an actual polygon offset — the outer boundary
    shrunk inward by bottom_cover_mm (and, if a top mat's cover
    differs, that offset is recomputed per mat — see below), every
    large hole grown outward by the same — before any scanline
    clipping happens for either mat or the closure U-bars.

    Args:
        (unchanged from Phase 2.2 — see that revision's docstring for
        the full parameter list.)

    Returns:
        {
          'bottom_mat': {'along_x': {'sets':[...],'bars':[...]},
                         'along_y': {'sets':[...],'bars':[...]}},
          'top_mat':    same shape, or None,
          'perimeter_closure_ubars': {
              'x_bars': {'sets':[...],'bars':[...]},
              'y_bars': {'sets':[...],'bars':[...]},
              'debug_failed_edges': [...],  # Phase 3.5.3 item 3
          } or None,
          'n_small_holes_ignored': int,
        }
        Each entry in 'sets' is ready for
        rebar_engine.RebarWrapper.create_rebar_set; each entry in
        'bars' is ready for .create_from_curves. Both carry an
        optional 'style' key ('StirrupTie' for a closed link, absent/
        None otherwise).

    Raises:
        ValueError: same conditions as Phase 2.2 (no usable bottom/top
        face or boundary loop, missing required top-mat/closure-ubar
        arguments, closure ubars requested without a top mat, or no
        positive usable height for full-depth legs).
    """
    engine = _ensure_engine()
    footing_mod = _ensure_footing_rebar()
    topo = _ensure_topology()
    DB = footing_mod.DB

    cover_mgr = engine.CoverGeometryManager(doc, host)
    z_extent_ft = _solid_z_extent_ft(cover_mgr.solid)
    bottom_face = footing_mod.get_footing_bottom_face(cover_mgr)
    if bottom_face is None:
        raise ValueError(u'Could not find a clearly downward-facing bottom face on this floor.')

    raw_loops = topo.extract_loops_mm(bottom_face.face)
    raw_outer, raw_holes, n_small_holes = topo.classify_loops(raw_loops)
    bottom_z_ft = bottom_face.origin.Z

    if include_top_mat and None in (top_cover_mm, top_dia_x_mm, top_dia_y_mm, top_spacing_mm):
        raise ValueError(u'include_top_mat requires top_cover_mm, top_dia_x_mm, '
                          u'top_dia_y_mm and top_spacing_mm to all be given.')

    top_z_ft = None
    if include_top_mat or bottom_hooks:
        top_face = footing_mod.get_footing_top_face(cover_mgr)
        if top_face is None:
            raise ValueError(u'Could not find a clearly upward-facing top face on this floor.')
        top_z_ft = top_face.origin.Z

    # Perimeter Closure U-Bar leg lengths, resolved up front (Phase 2.4
    # item 3): the main grid needs these BEFORE it builds any bars, so
    # it can skip a narrow interval that's about to get a closed link
    # instead of a redundant straight bar there (see
    # _build_direction_bars' own narrow_threshold_mm docstring).
    x_leg_mm = y_leg_mm = None
    if include_perimeter_closure_ubars:
        if not include_top_mat:
            raise ValueError(u'Perimeter Closure U-Bars require Include Top '
                              u'Reinforcement Mat to also be checked — the closure '
                              u'bars anchor between the bottom and top mats.')
        if None in (x_anchor_ubar_dia_mm, x_anchor_ubar_spacing_mm,
                    y_anchor_ubar_dia_mm, y_anchor_ubar_spacing_mm):
            raise ValueError(u'include_perimeter_closure_ubars requires '
                              u'x_anchor_ubar_dia_mm, x_anchor_ubar_spacing_mm, '
                              u'y_anchor_ubar_dia_mm and y_anchor_ubar_spacing_mm '
                              u'to all be given.')
        x_leg_mm = footing_mod.default_anchorage_length_mm(x_anchor_ubar_dia_mm)
        y_leg_mm = footing_mod.default_anchorage_length_mm(y_anchor_ubar_dia_mm)

    # PHASE 3.5.8 item 1 FIX — the PLAN (X/Y) boundary offset is a
    # LATERAL cover, not the bottom/top mat's own Z-direction FACE
    # cover. Reusing bottom_cover_mm/top_cover_mm here (as before) drags
    # in whatever the user typed for the mat's vertical face cover,
    # which is a different, independent value from the slab's real side
    # cover — the reported "excessive gap" on perimeter closure U-bars.
    # Resolved instead from this floor's own native "Exterior" cover
    # (CLEAR_COVER_OTHER — same lookup already used for columns/
    # footings), falling back to bottom_cover_mm only if that native
    # parameter isn't set on this element. This affects BOTH the main
    # mat's own plan clipping AND the perimeter closure U-bars (they
    # already shared bottom_outer/bottom_holes) — a disclosed side
    # effect, and the correct one: the main bars should not run past the
    # slab's real side cover either.
    side_cover_mm = engine.get_native_cover_mm(doc, host, u'Exterior', default_mm=bottom_cover_mm)

    # Real cover, per mat — the bottom mat's own outer/hole polygons
    # (offset inward/outward by side_cover_mm) drive B1/B2; the top mat
    # gets its OWN offset pair only if it needs a different Z depth —
    # the plan (lateral) offset itself is shared, since a slab has one
    # side cover regardless of which mat is being clipped.
    bottom_outer = topo.offset_polygon_mm(raw_outer, side_cover_mm)
    bottom_holes = [topo.offset_polygon_mm(h, -side_cover_mm) for h in raw_holes]
    xmin_mm, xmax_mm, ymin_mm, ymax_mm = topo.polygon_bbox_mm(bottom_outer)

    b1_z_ft = _clamp_z_to_solid_ft(bottom_z_ft + bottom_cover_mm / _MM_PER_FT, z_extent_ft)
    b2_z_ft = _clamp_z_to_solid_ft(
        bottom_z_ft + (bottom_cover_mm + bottom_dia_x_mm) / _MM_PER_FT, z_extent_ft)

    bottom_target_z_ft = None
    if bottom_hooks:
        effective_top_cover_mm = top_cover_mm if include_top_mat else bottom_cover_mm
        bottom_target_z_ft = top_z_ft - effective_top_cover_mm / _MM_PER_FT
        if bottom_target_z_ft <= b1_z_ft:
            raise ValueError(u'No usable internal height for the bottom mat\'s '
                              u'full-depth U-bar legs — covers exceed this '
                              u'floor\'s thickness.')

    along_x_bottom = _build_direction_bars(
        topo, footing_mod, engine, DB, bottom_outer, bottom_holes, 'x',
        bottom_dia_x_mm, bottom_dia_y_mm, bottom_spacing_mm,
        xmin_mm, xmax_mm, ymin_mm, ymax_mm, b1_z_ft, max_stock_length_mm,
        use_legs=bottom_hooks,
        leg_length_mm=(abs(bottom_target_z_ft - b1_z_ft) * _MM_PER_FT) if bottom_hooks else 0.0,
        leg_direction=DB.XYZ.BasisZ if bottom_hooks else None,
        narrow_threshold_mm=(2.0 * x_leg_mm) if include_perimeter_closure_ubars else None)
    along_y_bottom = _build_direction_bars(
        topo, footing_mod, engine, DB, bottom_outer, bottom_holes, 'y',
        bottom_dia_y_mm, bottom_dia_x_mm, bottom_spacing_mm,
        xmin_mm, xmax_mm, ymin_mm, ymax_mm, b2_z_ft, max_stock_length_mm,
        use_legs=bottom_hooks,
        leg_length_mm=(abs(bottom_target_z_ft - b2_z_ft) * _MM_PER_FT) if bottom_hooks else 0.0,
        leg_direction=DB.XYZ.BasisZ if bottom_hooks else None,
        narrow_threshold_mm=(2.0 * y_leg_mm) if include_perimeter_closure_ubars else None)

    result = {
        'bottom_mat': {'along_x': along_x_bottom, 'along_y': along_y_bottom},
        'top_mat': None,
        'perimeter_closure_ubars': None,
        'n_small_holes_ignored': n_small_holes,
    }

    top_outer = top_holes = None
    t1_z_ft = t2_z_ft = None
    if include_top_mat:
        top_outer = topo.offset_polygon_mm(raw_outer, side_cover_mm)
        top_holes = [topo.offset_polygon_mm(h, -side_cover_mm) for h in raw_holes]
        t1_z_ft = _clamp_z_to_solid_ft(
            top_z_ft - (top_cover_mm + top_dia_x_mm) / _MM_PER_FT, z_extent_ft)
        t2_z_ft = _clamp_z_to_solid_ft(
            top_z_ft - (top_cover_mm + top_dia_x_mm + top_dia_y_mm) / _MM_PER_FT, z_extent_ft)

        top_target_z_ft = None
        if top_hooks:
            top_target_z_ft = bottom_z_ft + bottom_cover_mm / _MM_PER_FT
            if top_target_z_ft >= t1_z_ft:
                raise ValueError(u'No usable internal height for the top mat\'s '
                                  u'full-depth U-bar legs — covers exceed this '
                                  u'floor\'s thickness.')

        # PHASE 2.6 FIX — row-scan bounds must come from THIS mat's own
        # offset polygon, not the bottom mat's: if top_cover_mm !=
        # bottom_cover_mm, bottom_outer's bbox is a different (wrong)
        # extent for the top mat's own material, which is exactly the
        # "scanning against the wrong polygon's Min/Max" failure mode
        # flagged live.
        top_xmin_mm, top_xmax_mm, top_ymin_mm, top_ymax_mm = topo.polygon_bbox_mm(top_outer)
        along_x_top = _build_direction_bars(
            topo, footing_mod, engine, DB, top_outer, top_holes, 'x',
            top_dia_x_mm, top_dia_y_mm, top_spacing_mm,
            top_xmin_mm, top_xmax_mm, top_ymin_mm, top_ymax_mm, t1_z_ft, max_stock_length_mm,
            use_legs=top_hooks,
            leg_length_mm=(abs(top_target_z_ft - t1_z_ft) * _MM_PER_FT) if top_hooks else 0.0,
            leg_direction=DB.XYZ.BasisZ.Multiply(-1.0) if top_hooks else None,
            narrow_threshold_mm=(2.0 * x_leg_mm) if include_perimeter_closure_ubars else None)
        along_y_top = _build_direction_bars(
            topo, footing_mod, engine, DB, top_outer, top_holes, 'y',
            top_dia_y_mm, top_dia_x_mm, top_spacing_mm,
            top_xmin_mm, top_xmax_mm, top_ymin_mm, top_ymax_mm, t2_z_ft, max_stock_length_mm,
            use_legs=top_hooks,
            leg_length_mm=(abs(top_target_z_ft - t2_z_ft) * _MM_PER_FT) if top_hooks else 0.0,
            leg_direction=DB.XYZ.BasisZ.Multiply(-1.0) if top_hooks else None,
            narrow_threshold_mm=(2.0 * y_leg_mm) if include_perimeter_closure_ubars else None)
        result['top_mat'] = {'along_x': along_x_top, 'along_y': along_y_top}

    if include_perimeter_closure_ubars:
        # Closure U-bars sit at the ALREADY cover-offset boundary (bottom
        # mat's own offset polygons are the reference here, since a
        # closure bar's own diameter/cover is independent of the main
        # mat's) — walked EDGE BY EDGE now (Phase 3.5 item 5), not
        # derived from the main grid's scanline.
        result['perimeter_closure_ubars'] = _build_edge_ubars(
            topo, footing_mod, DB, bottom_outer, bottom_holes,
            x_leg_mm, x_anchor_ubar_spacing_mm, b1_z_ft, t1_z_ft,
            y_leg_mm, y_anchor_ubar_spacing_mm, b2_z_ft, t2_z_ft)

    return result
