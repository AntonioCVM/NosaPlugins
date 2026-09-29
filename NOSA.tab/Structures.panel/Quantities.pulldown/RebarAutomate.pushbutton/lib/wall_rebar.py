# -*- coding: utf-8 -*-
"""
NOSA.RebarAutomate — Wall Rebar (Phase F7)
============================================================================

Category module for structural walls. Pure geometry — returns curve
sets for rebar_engine.RebarWrapper. Straight walls only in v1.
Openings / boundary ties / dowels are deferred.
"""
import os

from Autodesk.Revit import DB

_HERE = os.path.dirname(os.path.abspath(__file__))
re_engine = None

_MM_PER_FT = 304.8


def _ensure_engine():
    global re_engine
    if re_engine is None:
        from nosa_utils.bootstrap import load_module
        re_engine = load_module('re_engine', os.path.join(_HERE, 'rebar_engine.py'))
    return re_engine


def get_wall_axis(host):
    """Straight wall centreline as DB.Line."""
    loc = getattr(host, 'Location', None)
    curve = getattr(loc, 'Curve', None) if loc is not None else None
    if curve is None:
        raise ValueError(u'Wall has no LocationCurve.')
    if not isinstance(curve, DB.Line):
        raise ValueError(u'Curved walls are not supported yet.')
    return curve


def _wall_height_ft(host):
    """Unconnected height or bbox Z extent."""
    try:
        p = host.get_Parameter(DB.BuiltInParameter.WALL_USER_HEIGHT_PARAM)
        if p and p.HasValue:
            h = p.AsDouble()
            if h > 1e-6:
                return h
    except Exception:
        pass
    bbox = host.get_BoundingBox(None)
    if bbox is None:
        raise ValueError(u'Could not determine wall height.')
    return abs(bbox.Max.Z - bbox.Min.Z)


def _wall_faces(cover_mgr, axis_dir):
    """
    Classify wall faces into (exterior-ish, interior-ish, top, bottom).

    Side faces: normal roughly perpendicular to axis (horizontal).
    Top/bottom: |normal.Z| > 0.7.
    """
    sides = []
    top = bottom = None
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
        if abs(f.normal.DotProduct(axis_dir)) < 0.35 and abs(z) < 0.35:
            sides.append(f)

    if len(sides) < 1:
        raise ValueError(u'Could not find wall side faces.')
    # Prefer the two largest side faces if more than two (openings etc.)
    sides = sorted(sides, key=lambda fi: getattr(fi, 'area', 0.0) or 0.0, reverse=True)
    face_a = sides[0]
    face_b = sides[1] if len(sides) > 1 else None
    return face_a, face_b, top, bottom


def _evenly_spaced_mm(length_mm, spacing_mm, end_clear_mm):
    """Positions from end_clear to length-end_clear at spacing (inclusive ends)."""
    if length_mm <= 2.0 * end_clear_mm or spacing_mm <= 0:
        return []
    usable = length_mm - 2.0 * end_clear_mm
    if usable < 1.0:
        return [length_mm / 2.0]
    n = int(usable / spacing_mm) + 1
    if n < 2:
        return [end_clear_mm + usable / 2.0]
    return [end_clear_mm + i * usable / float(n - 1) for i in range(n)]


def get_wall_elevation_mm(host):
    """Return (length_mm, height_mm) for preview from a straight wall."""
    axis = get_wall_axis(host)
    length_mm = axis.Length * _MM_PER_FT
    height_mm = _wall_height_ft(host) * _MM_PER_FT
    return length_mm, height_mm


def build_wall_foundation_starters(doc, host, vert_spacing_mm, end_clear_mm,
                                    anchor_length_mm, splice_length_mm,
                                    foundation_cover_mm=25.0, search_depth_mm=3000.0):
    """
    PHASE F7.18 (2026-09-02, explicit user request — "Starter bars con
    forma de L en columnas y muros... unidas a la cimentación... zapata
    aislada, solera o zapata corrida") — companion to column_rebar.
    build_column_foundation_starters, same convention, for a wall: ONE
    straight starter Line per vertical-bar position ALONG THE WALL'S
    OWN LENGTH (_evenly_spaced_mm — the SAME spacing the real vertical
    mesh uses), reaching DOWN from the wall's own base into whatever
    foundation (isolated/strip footing OR floor/mat slab — see
    rebar_engine.find_foundation_below) is detected directly below it.
    Each returned Line is meant to get a 90° hook at its own BOTTOM end
    (start_hook, applied by the caller at creation time — see 'normal'
    below), exactly like footing_rebar.build_dowel_curves' own dowels.

    DISCLOSED SIMPLIFICATION: positioned along the wall's own AXIS
    (centreline), not offset to either face the real vertical mesh may
    sit on (build_wall_reinforcement's own vert_is_outer/both_faces
    layering) — a starter bar's own exact transverse position within
    the wall's thickness is a minor detail next to it landing on the
    right foundation, at the right length-wise spacing; a future caller
    that needs per-face starters can offset the returned Lines' own X/Y
    itself before creation.

    Args:
        doc, host                    as elsewhere.
        vert_spacing_mm                (float): the wall's own vertical
                                      bar spacing, mm — reused so starter
                                      positions match the real mesh.
        end_clear_mm                     (float): end clearance from
                                      each free end, mm — same meaning
                                      as build_wall_reinforcement's own.
        anchor_length_mm                   (float): straight length
                                      WITHIN the detected foundation,
                                      mm.
        splice_length_mm                     (float): additional length
                                      ABOVE the foundation's own top,
                                      mm.
        foundation_cover_mm                    (float): the
                                      FOUNDATION's own bottom cover, mm
                                      — defaults to 25mm (a normative
                                      floor/footing minimum) since,
                                      unlike columns, a wall has no
                                      single "cover_mm" already in scope
                                      here to fall back to.
        search_depth_mm                          (float): how far below
                                      the wall's own base to search for
                                      a foundation, mm.

    Returns:
        {'bars': list[DB.Line], 'normals': list[DB.XYZ] (one hook-plane normal per bar), 'skipped': int} —
        same meaning as build_column_foundation_starters' own.
    """
    engine = _ensure_engine()
    axis = get_wall_axis(host)
    axis_dir = axis.Direction.Normalize()
    p0 = axis.GetEndPoint(0)
    length_mm = axis.Length * _MM_PER_FT

    base_z_ft = p0.Z
    try:
        bbox = host.get_BoundingBox(None)
        if bbox is not None:
            base_z_ft = bbox.Min.Z
    except Exception:
        pass

    vert_positions_mm = _evenly_spaced_mm(length_mm, vert_spacing_mm, end_clear_mm)
    search_depth_ft = search_depth_mm / _MM_PER_FT

    # Hook foot points across the wall thickness, into the footing's width.
    across = DB.XYZ.BasisZ.CrossProduct(axis_dir)

    bars = []
    normals = []
    skipped = 0
    for dist_mm in vert_positions_mm:
        p = p0 + axis_dir.Multiply(dist_mm / _MM_PER_FT)
        result = engine.build_starter_into_foundation(
            doc, p.X, p.Y, base_z_ft, anchor_length_mm, splice_length_mm,
            foundation_cover_mm, search_depth_ft=search_depth_ft, hook_dir=across)
        if result is None:
            skipped += 1
            continue
        bars.append(result['line'])
        normals.append(result['normal'])
    return {'bars': bars, 'normals': normals, 'skipped': skipped}


def build_wall_reinforcement(doc, host, cover_mm,
                              vert_dia_mm, vert_spacing_mm,
                              horiz_dia_mm, horiz_spacing_mm,
                              both_faces=True, end_clear_mm=50.0,
                              include_ties=False, tie_dia_mm=None,
                              tie_spacing_mm=400.0,
                              include_end_ubars=False, ubar_dia_mm=None,
                              ubar_spacing_mm=None,
                              include_top_ubars=False,
                              include_starter_bars=False,
                              starter_length_mm=None,
                              stock_length_mm=12000.0,
                              lap_length_mm=None,
                              horiz_lap_length_mm=None,
                              vert_is_outer=True):
    """
    Build vertical + horizontal mesh curve sets for one straight wall.

    Optional:
      - Ties: straight through-wall ties linking both faces
      - End U-bars: horizontal U wrapping wall thickness at each free end
      - Starter bars: verticals extended below the wall base (foundation lap)
      - Stock split: vertical / horizontal bars longer than stock_length_mm
        are split with a lap length the caller must supply. BUG FIX
        (2026-09-01) — `lap_length_mm` (vert_dia's own normative lap) used
        to be reused UNCHANGED for the horizontal mesh too, splicing
        horiz_dia bars with a lap length sized for a DIFFERENT, usually
        larger, diameter. `horiz_lap_length_mm` is now a separate value
        for horiz_dia's own splices; if not given, falls back to
        `lap_length_mm` (old behaviour, still wrong but never worse than
        before for a caller that hasn't been updated yet).
      - vert_is_outer (bool, default True): which mesh direction sits
        in the OUTER layer (touching cover) vs the INNER layer (behind
        the full diameter of whichever direction is outer) — user-
        selectable (2026-09-01) rather than hardcoded, since the
        correct order is a project/detailing convention, not a fixed
        rule. True = vertical outer / horizontal inner (this project's
        stated default); False flips it. End U-bars always follow
        whichever mesh they anchor (vertical), Top U-bars follow
        horizontal — so flipping this flips the U-bars' own layer too,
        consistently.

    Returns 'end_ubars'/'top_ubars' as {'sets': [...], 'bars': [...]} —
    the same shape floor_rebar.py's perimeter closure U-bars use — so
    ui.py's existing _create_grouped_bars (Set first, FreeForm-group
    fallback, individual bars as the last resort) applies unchanged;
    every other key here is still a flat list.
    """
    engine = _ensure_engine()
    axis = get_wall_axis(host)
    axis_dir = axis.Direction.Normalize()
    p0 = axis.GetEndPoint(0)
    length_mm = axis.Length * _MM_PER_FT
    height_ft = _wall_height_ft(host)
    height_mm = height_ft * _MM_PER_FT

    cover_mgr = engine.CoverGeometryManager(doc, host)
    face_a, face_b, top, bottom = _wall_faces(cover_mgr, axis_dir)

    faces = [face_a]
    if both_faces and face_b is not None:
        faces.append(face_b)

    warnings = []
    if both_faces and face_b is None:
        warnings.append(u'Only one side face found — mesh placed on a single face.')

    z0 = p0.Z
    try:
        bbox = host.get_BoundingBox(None)
        if bbox is not None:
            z0 = bbox.Min.Z
    except Exception:
        pass

    starter_mm = 0.0
    if include_starter_bars:
        starter_mm = starter_length_mm if starter_length_mm and starter_length_mm > 0 \
            else max(40.0 * vert_dia_mm, 500.0)

    vert_bottom_z = z0 + (cover_mm + vert_dia_mm / 2.0) / _MM_PER_FT
    if include_starter_bars:
        vert_bottom_z = z0 - starter_mm / _MM_PER_FT
    vert_top_z = z0 + height_ft - (cover_mm + vert_dia_mm / 2.0) / _MM_PER_FT
    if vert_top_z <= vert_bottom_z + 1.0 / _MM_PER_FT:
        raise ValueError(u'Wall is too short for the given cover and bar diameter.')

    vert_positions = _evenly_spaced_mm(length_mm, vert_spacing_mm, end_clear_mm)
    horiz_positions = _evenly_spaced_mm(height_mm, horiz_spacing_mm, end_clear_mm)

    vertical_sets = []
    horizontal_sets = []
    ties = []
    end_ubars = {'sets': [], 'bars': []}
    top_ubars = {'sets': [], 'bars': []}
    starter_bars = []

    # BUG FIX (2026-09-01) — reported live: "no mantiene las capas...
    # chocarían". Vertical and horizontal mesh bars used to share a
    # SINGLE `depth` (both computed from cover_mm + vert_dia_mm/2.0),
    # meaning they were modelled coplanar — physically impossible,
    # since one direction must sit behind the other. `vert_is_outer`
    # (user-selectable, default True) picks which direction sits in
    # the OUTER layer (cover + own_dia/2) vs the INNER layer (cover +
    # the OUTER direction's full diameter + own_dia/2) — the same
    # B1/B2 pattern footing_rebar.py's main mat already uses for
    # along_x (layer 1) vs along_y (layer 2).
    if vert_is_outer:
        vert_inset_mm = cover_mm + vert_dia_mm / 2.0
        horiz_inset_mm = cover_mm + vert_dia_mm + horiz_dia_mm / 2.0
    else:
        horiz_inset_mm = cover_mm + horiz_dia_mm / 2.0
        vert_inset_mm = cover_mm + horiz_dia_mm + vert_dia_mm / 2.0

    face_depths = {}
    for face in faces:
        face_normal = face.normal.Normalize()
        cover_pt = engine.compute_cover_point(face, vert_inset_mm)
        depth = (cover_pt - p0).DotProduct(face_normal)
        horiz_cover_pt = engine.compute_cover_point(face, horiz_inset_mm)
        horiz_depth = (horiz_cover_pt - p0).DotProduct(face_normal)
        face_depths[id(face)] = (face, face_normal, depth)

        if vert_positions:
            d0_mm = vert_positions[0]
            start = p0 + axis_dir.Multiply(d0_mm / _MM_PER_FT) + face_normal.Multiply(depth)
            start = DB.XYZ(start.X, start.Y, vert_bottom_z)
            end = DB.XYZ(start.X, start.Y, vert_top_z)
            curves = [DB.Line.CreateBound(start, end)]
            array_mm = (vert_positions[-1] - vert_positions[0]) if len(vert_positions) > 1 else 0.0
            spacing = vert_spacing_mm
            if len(vert_positions) > 1:
                spacing = (vert_positions[-1] - vert_positions[0]) / float(len(vert_positions) - 1)
            vertical_sets.append({
                'curves': curves,
                'spacing_mm': spacing,
                'array_length_mm': array_mm,
                'normal': axis_dir,
                'count': len(vert_positions),
                'label': u'Wall Vertical Mesh',
            })

        if horiz_positions:
            h0_mm = horiz_positions[0]
            clear_ft = end_clear_mm / _MM_PER_FT
            start = p0 + axis_dir.Multiply(clear_ft) + face_normal.Multiply(horiz_depth)
            end = p0 + axis_dir.Multiply(axis.Length - clear_ft) + face_normal.Multiply(horiz_depth)
            z = z0 + h0_mm / _MM_PER_FT
            start = DB.XYZ(start.X, start.Y, z)
            end = DB.XYZ(end.X, end.Y, z)
            if start.DistanceTo(end) >= 1.0 / _MM_PER_FT:
                curves = [DB.Line.CreateBound(start, end)]
                array_mm = (horiz_positions[-1] - horiz_positions[0]) if len(horiz_positions) > 1 else 0.0
                spacing = horiz_spacing_mm
                if len(horiz_positions) > 1:
                    spacing = (horiz_positions[-1] - horiz_positions[0]) / float(len(horiz_positions) - 1)
                horizontal_sets.append({
                    'curves': curves,
                    'spacing_mm': spacing,
                    'array_length_mm': array_mm,
                    'normal': DB.XYZ.BasisZ,
                    'count': len(horiz_positions),
                    'label': u'Wall Horizontal Mesh',
                })

    # Ties — through-wall at intervals
    if include_ties and face_b is not None and len(faces) >= 2:
        t_dia = tie_dia_mm if tie_dia_mm else horiz_dia_mm
        t_spacing = tie_spacing_mm if tie_spacing_mm and tie_spacing_mm > 0 else 400.0
        fa, na, da = face_depths[id(face_a)]
        fb, nb, db = face_depths[id(face_b)]
        ca = engine.compute_cover_point(fa, cover_mm + t_dia / 2.0)
        cb = engine.compute_cover_point(fb, cover_mm + t_dia / 2.0)
        da = (ca - p0).DotProduct(na)
        db = (cb - p0).DotProduct(nb)
        tie_positions = _evenly_spaced_mm(length_mm, t_spacing, end_clear_mm)
        z_levels = [
            z0 + height_ft * 0.25,
            z0 + height_ft * 0.5,
            z0 + height_ft * 0.75,
        ]
        for d_mm in tie_positions:
            base = p0 + axis_dir.Multiply(d_mm / _MM_PER_FT)
            pa = base + na.Multiply(da)
            pb = base + nb.Multiply(db)
            for z in z_levels:
                a = DB.XYZ(pa.X, pa.Y, z)
                b = DB.XYZ(pb.X, pb.Y, z)
                if a.DistanceTo(b) < 1.0 / _MM_PER_FT:
                    continue
                ties.append({
                    'curves': [DB.Line.CreateBound(a, b)],
                    'normal': axis_dir,
                    'label': u'Wall Tie',
                })
    elif include_ties and face_b is None:
        warnings.append(u'Ties require both wall faces — skipped.')

    # End U-bars — horizontal U wrapping thickness at each free end.
    # BUG FIX (2026-09-01) — these used to come out as N individual
    # Rebar elements per end (one per height in u_heights), reported
    # live as "los ubars ... los hace individuales, cuando deberían ser
    # rebar sets". Every height's shape is IDENTICAL except for its Z
    # translation, so it is a textbook Rebar Set candidate — the SAME
    # {'sets':[...],'bars':[...]} shape floor_rebar.py's own perimeter
    # closure U-bars already return (see floor_rebar._build_direction_
    # bars / _build_edge_ubars), consumed by ui.py's existing
    # _create_grouped_bars (Set first, FreeForm-group fallback, then
    # individual bars as the true last resort — never a silent loop of
    # loose create_from_curves calls). style is left as the dict
    # default (None / Standard), matching _build_edge_ubars' own choice
    # for this exact open leg-back-leg U topology — RebarStyle.
    # StirrupTie is reserved for a CLOSED loop shape (see
    # rebar_engine.RebarWrapper.create_rebar_set's own docstring).
    if include_end_ubars and face_b is not None and len(faces) >= 2:
        u_dia = ubar_dia_mm if ubar_dia_mm else vert_dia_mm
        u_sp = ubar_spacing_mm if ubar_spacing_mm and ubar_spacing_mm > 0 else horiz_spacing_mm
        fa, na, _ = face_depths[id(face_a)]
        fb, nb, _ = face_depths[id(face_b)]
        # End U-bars anchor the VERTICAL mesh — sit in whichever layer
        # vert_is_outer assigns to vertical (see vert_inset_mm above).
        end_u_inset_mm = (cover_mm + u_dia / 2.0) if vert_is_outer \
            else (cover_mm + horiz_dia_mm + u_dia / 2.0)
        ca = engine.compute_cover_point(fa, end_u_inset_mm)
        cb = engine.compute_cover_point(fb, end_u_inset_mm)
        da = (ca - p0).DotProduct(na)
        db = (cb - p0).DotProduct(nb)
        # Leg length along wall from end (~ 15Ø or 300mm min)
        leg_mm = max(15.0 * u_dia, 300.0)
        leg_mm = min(leg_mm, length_mm * 0.4)
        u_heights = _evenly_spaced_mm(height_mm, u_sp, end_clear_mm)
        end_ubar_sets, end_ubar_bars = [], []
        for d_end in (end_clear_mm, length_mm - end_clear_mm):
            # Direction into the wall from this end: at the start end
            # (d=end_clear_mm) inward is +axis; at the finish end, -axis.
            inward = axis_dir if d_end < length_mm * 0.5 else axis_dir.Multiply(-1.0)
            base = p0 + axis_dir.Multiply(d_end / _MM_PER_FT)
            per_height_curves = []
            for h_mm in u_heights:
                z = z0 + h_mm / _MM_PER_FT
                pa = DB.XYZ((base + na.Multiply(da)).X, (base + na.Multiply(da)).Y, z)
                pb = DB.XYZ((base + nb.Multiply(db)).X, (base + nb.Multiply(db)).Y, z)
                # Legs extend inward along each face
                pa_leg = pa + inward.Multiply(leg_mm / _MM_PER_FT)
                pb_leg = pb + inward.Multiply(leg_mm / _MM_PER_FT)
                if pa.DistanceTo(pb) < 1.0 / _MM_PER_FT:
                    continue
                per_height_curves.append([
                    DB.Line.CreateBound(pa_leg, pa),
                    DB.Line.CreateBound(pa, pb),
                    DB.Line.CreateBound(pb, pb_leg),
                ])
            if not per_height_curves:
                continue
            # A Set needs every array position to share the same shape —
            # only true if NONE of this end's heights degenerated above.
            if len(per_height_curves) >= 2 and len(per_height_curves) == len(u_heights):
                array_length_mm = u_heights[-1] - u_heights[0]
                spacing = array_length_mm / float(len(u_heights) - 1)
                materialized = [{'curves': c, 'normal': DB.XYZ.BasisZ}
                                 for c in per_height_curves]
                end_ubar_sets.append({
                    'curves': per_height_curves[0],
                    'normal': DB.XYZ.BasisZ,
                    'array_length_mm': array_length_mm,
                    'spacing_mm': spacing,
                    'materialized_bars': materialized,
                    'label': u'Wall End U-Bar',
                })
            else:
                for c in per_height_curves:
                    end_ubar_bars.append({
                        'curves': c, 'normal': DB.XYZ.BasisZ,
                        'label': u'Wall End U-Bar',
                    })
        end_ubars = {'sets': end_ubar_sets, 'bars': end_ubar_bars}
    elif include_end_ubars and face_b is None:
        warnings.append(u'End U-bars require both wall faces — skipped.')

    # Top U-bars — horizontal closure at wall head (both faces).
    # BUG FIX (2026-09-01) — reported live: End U-bars (capa vertical)
    # and Top U-bars (capa horizontal) used the exact SAME `cover_mm +
    # u_dia/2.0` inset, i.e. the same B, so at a corner where a wall
    # end meets the wall top the two systems occupied the identical
    # slot inside the wall's thickness and would physically collide.
    # Top U-bars anchor the HORIZONTAL mesh, so they sit in whichever
    # layer vert_is_outer assigns to horizontal (see horiz_inset_mm
    # above) — the SAME B1/B2 pattern as the main mesh fix and as
    # footing_rebar.py's along_x/along_y mat layers, now flippable via
    # vert_is_outer instead of hardcoded to "vertical always outer".
    if include_top_ubars and face_b is not None and len(faces) >= 2:
        u_dia = ubar_dia_mm if ubar_dia_mm else vert_dia_mm
        u_sp = ubar_spacing_mm if ubar_spacing_mm and ubar_spacing_mm > 0 else horiz_spacing_mm
        fa, na, _ = face_depths[id(face_a)]
        fb, nb, _ = face_depths[id(face_b)]
        top_u_inset_mm = (cover_mm + vert_dia_mm + u_dia / 2.0) if vert_is_outer \
            else (cover_mm + u_dia / 2.0)
        ca = engine.compute_cover_point(fa, top_u_inset_mm)
        cb = engine.compute_cover_point(fb, top_u_inset_mm)
        da = (ca - p0).DotProduct(na)
        db = (cb - p0).DotProduct(nb)
        leg_mm = max(15.0 * u_dia, 300.0)
        leg_mm = min(leg_mm, height_mm * 0.4)
        z_top = vert_top_z
        u_positions = _evenly_spaced_mm(length_mm, u_sp, end_clear_mm)
        # BUG FIX (2026-09-01) — same Set-grouping fix as End U-bars
        # above: every position's shape is identical except for its
        # translation along axis_dir, so this is grouped into ONE Rebar
        # Set instead of len(u_positions) individual elements. normal
        # stays axis_dir per the BUG FIX note kept below (this shape's
        # own plane/array-propagation direction), and style is left as
        # the dict default (None), matching floor_rebar's own precedent
        # for this identical open leg-back-leg U topology.
        per_pos_curves = []
        for d_mm in u_positions:
            base = p0 + axis_dir.Multiply(d_mm / _MM_PER_FT)
            pa = DB.XYZ((base + na.Multiply(da)).X, (base + na.Multiply(da)).Y, z_top)
            pb = DB.XYZ((base + nb.Multiply(db)).X, (base + nb.Multiply(db)).Y, z_top)
            pa_leg = DB.XYZ(pa.X, pa.Y, z_top - leg_mm / _MM_PER_FT)
            pb_leg = DB.XYZ(pb.X, pb.Y, z_top - leg_mm / _MM_PER_FT)
            if pa.DistanceTo(pb) < 1.0 / _MM_PER_FT:
                continue
            per_pos_curves.append([
                DB.Line.CreateBound(pa_leg, pa),
                DB.Line.CreateBound(pa, pb),
                DB.Line.CreateBound(pb, pb_leg),
            ])
        top_ubar_sets, top_ubar_bars = [], []
        if per_pos_curves:
            if len(per_pos_curves) >= 2 and len(per_pos_curves) == len(u_positions):
                array_length_mm = u_positions[-1] - u_positions[0]
                spacing = array_length_mm / float(len(u_positions) - 1)
                materialized = [{'curves': c, 'normal': axis_dir} for c in per_pos_curves]
                top_ubar_sets.append({
                    'curves': per_pos_curves[0],
                    # BUG FIX: all three curves vary only in Z (the legs) and
                    # in the face-normal/thickness direction (the middle
                    # segment, pa->pb) — X/Y along the wall's length is fixed
                    # at this loop's own d_mm for every point. The shape's
                    # plane is therefore {Z, thickness-direction}, whose
                    # normal is the wall's own axis direction — NOT
                    # na x axis_dir (that cross product is ~Z, the WRONG
                    # plane: it told Revit this shape was horizontal when it
                    # is actually vertical, same mistake this file's End
                    # U-bars/beam stirrups deliberately avoid elsewhere).
                    'normal': axis_dir,
                    'array_length_mm': array_length_mm,
                    'spacing_mm': spacing,
                    'materialized_bars': materialized,
                    'label': u'Wall Top U-Bar',
                })
            else:
                for c in per_pos_curves:
                    top_ubar_bars.append({
                        'curves': c, 'normal': axis_dir, 'label': u'Wall Top U-Bar',
                    })
        top_ubars = {'sets': top_ubar_sets, 'bars': top_ubar_bars}
    elif include_top_ubars and face_b is None:
        warnings.append(u'Top U-bars require both wall faces — skipped.')

    # Explicit starter bars (when mesh already extended, still list for marking)
    if include_starter_bars and starter_mm > 0:
        for vs in vertical_sets:
            # Mark that verticals already include starter projection
            vs['includes_starter'] = True
            vs['starter_length_mm'] = starter_mm

    # Stock-length split — keep Rebar Sets; never explode mesh into loose bars
    if stock_length_mm and stock_length_mm > 0:
        if stock_length_mm < 500.0:
            warnings.append(
                u'Stock length {:.0f} mm is too small — using 12000 mm.'.format(stock_length_mm))
            stock_length_mm = 12000.0
        def _resolve_lap_mm(raw_lap_mm):
            """Clamp one direction's own lap to < stock_length_mm, or None."""
            lap = raw_lap_mm if raw_lap_mm and raw_lap_mm > 0 else None
            if lap is not None and lap >= stock_length_mm:
                lap = max(stock_length_mm * 0.25, 200.0)
                warnings.append(
                    u'Lap length capped to {:.0f} mm (must be < stock length).'.format(lap))
            return lap

        # BUG FIX (2026-09-01) — reported live: "el solape... también
        # tenemos el problema que no solapan" tracked back partly to
        # THIS: the vertical mesh's own normative lap (sized for
        # vert_dia) was being reused unchanged for the horizontal mesh
        # (horiz_dia), splicing the wrong-diameter bar with the wrong
        # lap length. Each direction now resolves its OWN lap.
        lap_mm = _resolve_lap_mm(lap_length_mm)
        horiz_lap_mm = _resolve_lap_mm(
            horiz_lap_length_mm if horiz_lap_length_mm is not None else lap_length_mm)

        def _split_mesh_sets(mesh_sets, axis_label, own_lap_mm):
            """Split each mesh set by stock length; output remains Rebar Sets."""
            out = []
            for ms in mesh_sets:
                c0 = ms['curves'][0] if ms.get('curves') else None
                if c0 is None:
                    continue
                bar_len = c0.Length * _MM_PER_FT
                if bar_len <= stock_length_mm + 1.0 or own_lap_mm is None:
                    out.append(ms)
                    continue
                try:
                    seg_list = engine.split_rebar_by_stock_length(c0, stock_length_mm, own_lap_mm)
                except Exception as ex:
                    warnings.append(u'{} mesh stock split skipped: {}'.format(axis_label, ex))
                    out.append(ms)
                    continue
                for i, seg in enumerate(seg_list):
                    out.append({
                        'curves': [seg.curve],
                        'spacing_mm': ms['spacing_mm'],
                        'array_length_mm': ms['array_length_mm'],
                        'normal': ms['normal'],
                        'count': ms['count'],
                        'label': u'{} (segment {})'.format(ms.get('label', axis_label), i + 1),
                    })
            return out

        vertical_sets = _split_mesh_sets(vertical_sets, u'Wall Vertical', lap_mm)
        horizontal_sets = _split_mesh_sets(horizontal_sets, u'Wall Horizontal', horiz_lap_mm)

    if (not vertical_sets and not horizontal_sets
            and not (end_ubars['sets'] or end_ubars['bars'])
            and not (top_ubars['sets'] or top_ubars['bars'])):
        raise ValueError(u'No wall reinforcement curves could be generated.')

    return {
        'vertical_sets': vertical_sets,
        'horizontal_sets': horizontal_sets,
        'ties': ties,
        'end_ubars': end_ubars,
        'top_ubars': top_ubars,
        'starter_bars': starter_bars,
        'starter_length_mm': starter_mm,
        'warnings': warnings,
    }
