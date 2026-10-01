# -*- coding: utf-8 -*-
"""
NOSA.RebarAutomate — Wall Rebar (Phase F7)
============================================================================

Category module for structural walls. Pure geometry — returns curve
sets for rebar_engine.RebarWrapper. Straight walls only in v1.
Openings / boundary ties / dowels are deferred.
"""
import math
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


NEAR_FACE = u'NF'   # the face towards the slab (inside the building)
FAR_FACE = u'FF'    # the face away from it (outside the building)
_SLAB_PROBE_MM = 300.0


def face_codes(slab_beside, exterior):
    """
    NF/FF per wall face: a face with a slab beside it is NF, the other FF.
    When the slabs do not tell the faces apart, Revit's exterior side is FF.
    """
    if len(slab_beside) == 1 and slab_beside[0]:
        return [NEAR_FACE]
    if any(slab_beside) and not all(slab_beside):
        return [NEAR_FACE if beside else FAR_FACE for beside in slab_beside]
    return [FAR_FACE if out else NEAR_FACE for out in exterior]


def _floor_solids(doc, near_bbox):
    """Solids of the floors whose bounding box reaches near_bbox (an Outline)."""
    solids = []
    floors = DB.FilteredElementCollector(doc).OfClass(DB.Floor).WherePasses(
        DB.BoundingBoxIntersectsFilter(near_bbox))
    options = DB.Options()
    for floor in floors:
        for geom in floor.get_Geometry(options):
            if isinstance(geom, DB.Solid) and geom.Volume > 0:
                solids.append(geom)
    return solids


def _slab_at(solids, x, y, z_lo, z_hi):
    line = DB.Line.CreateBound(DB.XYZ(x, y, z_lo), DB.XYZ(x, y, z_hi))
    options = DB.SolidCurveIntersectionOptions()
    for solid in solids:
        try:
            if solid.IntersectWithCurve(line, options).SegmentCount > 0:
                return True
        except Exception:
            continue
    return False


def wall_face_codes(doc, host, faces, axis):
    """{id(face): 'NF' | 'FF'} — NF towards the slab, FF towards the outside (user rule 2026-10-01)."""
    try:
        bbox = host.get_BoundingBox(None)
        half_ft = (host.Width / 2.0) + _SLAB_PROBE_MM / _MM_PER_FT
        reach = DB.XYZ(half_ft, half_ft, 1.0)
        solids = _floor_solids(doc, DB.Outline(bbox.Min - reach, bbox.Max + reach))
        z_lo, z_hi = bbox.Min.Z - 1.0, bbox.Max.Z + 1.0
        slab_beside = []
        for face in faces:
            n = face.normal.Normalize()
            hits = False
            for t in (0.25, 0.5, 0.75):
                p = axis.Evaluate(t, True) + n.Multiply(half_ft)
                hits = hits or _slab_at(solids, p.X, p.Y, z_lo, z_hi)
            slab_beside.append(hits)
        exterior = [face.normal.DotProduct(host.Orientation) > 0 for face in faces]
        codes = face_codes(slab_beside, exterior)
    except Exception:
        return {}
    return dict((id(face), code) for face, code in zip(faces, codes))


def _evenly_spaced_mm(length_mm, spacing_mm, end_clear_mm, far_clear_mm=None):
    """Positions exactly spacing_mm apart, centred between end_clear and length - far_clear."""
    far_clear_mm = end_clear_mm if far_clear_mm is None else far_clear_mm
    lo, hi = end_clear_mm, length_mm - far_clear_mm
    span = hi - lo
    if span <= 0 or spacing_mm <= 0:
        return []
    gaps = int(math.floor(span / spacing_mm + 1e-9))
    if gaps == 0:
        return [lo + span / 2.0]
    start = lo + (span - gaps * spacing_mm) / 2.0
    return [start + k * spacing_mm for k in range(gaps + 1)]


SNAP_CLEARANCE_MM = 10.0   # Revit pulls a bar end lying closer than this onto the cover


def whole_step_length_mm(length_mm, step_mm=25.0):
    """
    Longest whole-step length that fits, leaving the trimmed end at least SNAP_CLEARANCE_MM
    off the cover so Revit does not stretch it back (BS 8666 A = cut length).
    """
    if length_mm < step_mm:
        return length_mm
    whole = step_mm * math.floor(length_mm / step_mm + 1e-9)
    if 1e-6 < length_mm - whole < SNAP_CLEARANCE_MM:
        whole -= step_mm
    return whole


def find_slab_on_wall(doc, host, axis, wall_top_z, tol_mm=50.0):
    """(floor, slab top z) for a slab cast on the wall head (its underside at the wall top), else None."""
    tol = tol_mm / _MM_PER_FT
    best = None
    try:
        for floor in DB.FilteredElementCollector(doc).OfClass(DB.Floor):
            bbox = floor.get_BoundingBox(None)
            if bbox is None or abs(bbox.Min.Z - wall_top_z) > tol + 1.0:
                continue
            solids = _floor_solids(doc, DB.Outline(bbox.Min, bbox.Max))
            hits = 0
            for t in (0.25, 0.5, 0.75):
                p = axis.Evaluate(t, True)
                if _slab_at(solids, p.X, p.Y, wall_top_z + tol, wall_top_z + 3 * tol):
                    hits += 1
            if hits >= 2 and (best is None or bbox.Max.Z < best[1]):
                best = (floor, bbox.Max.Z)
    except Exception:
        return None
    return best


def slab_top_mat_mm(doc, floor, fallback_mm=24.0):
    """Depth of the slab's top mat (T1 + T2 NOSA bar diameters), else fallback_mm."""
    layers = {}
    try:
        for rebar in DB.FilteredElementCollector(doc).OfCategory(
                DB.BuiltInCategory.OST_Rebar).WhereElementIsNotElementType():
            if rebar.GetHostId() != floor.Id:
                continue
            param = rebar.LookupParameter(u'NOSA_Rebar_Layer')
            layer = param.AsString() if param is not None else None
            if layer in (u'top_x', u'top_y'):
                dia = doc.GetElement(rebar.GetTypeId()).BarNominalDiameter * _MM_PER_FT
                layers[layer] = max(layers.get(layer, 0.0), dia)
    except Exception:
        layers = {}
    return sum(layers.values()) if layers else fallback_mm


def slab_foot_directions(doc, host, faces, axis, slab_top_z):
    """
    {id(face): direction} of the L feet into the slab: towards the slab where it only lies on
    one side of the wall (an edge wall), else each face turned outwards (slab on both sides).
    """
    half_ft = (host.Width / 2.0) + _SLAB_PROBE_MM / _MM_PER_FT
    bbox = host.get_BoundingBox(None)
    reach = DB.XYZ(half_ft, half_ft, 1.0)
    solids = _floor_solids(doc, DB.Outline(bbox.Min - reach, bbox.Max + reach))
    z = slab_top_z - 50.0 / _MM_PER_FT
    beside = []
    for face in faces:
        n = face.normal.Normalize()
        p = axis.Evaluate(0.5, True) + n.Multiply(half_ft)
        beside.append(_slab_at(solids, p.X, p.Y, z - 1.0 / _MM_PER_FT, z))
    dirs = {}
    if sum(1 for b in beside if b) == 1:
        towards = [f for f, b in zip(faces, beside) if b][0].normal.Normalize()
        towards = DB.XYZ(towards.X, towards.Y, 0.0).Normalize()
        for face in faces:
            dirs[id(face)] = towards
    else:
        for face in faces:
            n = face.normal.Normalize()
            dirs[id(face)] = DB.XYZ(n.X, n.Y, 0.0).Normalize()
    return dirs


def _trim_to_step_mm(lo_mm, hi_mm, step_mm=25.0):
    """Shorten a span equally at both ends to a whole number of step_mm."""
    length = hi_mm - lo_mm
    if length < step_mm:
        return lo_mm, hi_mm
    trim = (length - math.floor(length / step_mm + 1e-9) * step_mm) / 2.0
    if 1e-6 < trim < SNAP_CLEARANCE_MM:
        # Revit pulls an end this close back onto the cover, undoing the trim
        trim += step_mm / 2.0
    return lo_mm + trim, hi_mm - trim


def top_ubar_positions_mm(vert_positions_mm, length_mm, vert_dia_mm, ubar_dia_mm, end_clear_mm):
    """One coronation U-bar beside each vertical bar (in contact), turned back at the far end."""
    contact = (vert_dia_mm + ubar_dia_mm) / 2.0
    out = []
    for d in vert_positions_mm:
        out.append(d + contact if d + contact <= length_mm - end_clear_mm + 1e-6 else d - contact)
    return out


def uniform_runs_mm(positions_mm, tol_mm=0.5):
    """Split positions into runs of equal step (each run can be one Rebar Set)."""
    runs = []
    for d in positions_mm:
        run = runs[-1] if runs else None
        if run is None or (len(run) >= 2 and abs((d - run[-1]) - (run[1] - run[0])) > tol_mm):
            runs.append([d])
        else:
            run.append(d)
    return runs


def get_wall_elevation_mm(host):
    """Return (length_mm, height_mm) for preview from a straight wall."""
    axis = get_wall_axis(host)
    length_mm = axis.Length * _MM_PER_FT
    height_mm = _wall_height_ft(host) * _MM_PER_FT
    return length_mm, height_mm


def build_wall_foundation_starters(doc, host, bar_points, main_dia_mm, starter_dia_mm,
                                    anchor_length_mm, splice_length_mm,
                                    foundation_cover_mm=25.0, search_depth_mm=3000.0):
    """
    PHASE F7.18 — L-shaped starters from the foundation below into the wall.

    One starter per vertical of BOTH faces (bar_points: plan start points of
    the wall's own vertical mesh, read from the Rebar elements just created),
    contact-lapped towards the wall's mid-plane so it stays inside the mesh,
    with its foot pointing outwards across the footing width (user decision
    2026-09-29). See rebar_engine.build_contact_starters for the return value.
    """
    engine = _ensure_engine()
    axis = get_wall_axis(host)
    axis_dir = axis.Direction.Normalize()
    origin = axis.GetEndPoint(0)
    across = DB.XYZ.BasisZ.CrossProduct(axis_dir)

    inward_dirs = []
    for p in bar_points:
        side = DB.XYZ(p.X - origin.X, p.Y - origin.Y, 0.0).DotProduct(across)
        inward_dirs.append(across.Multiply(-1.0 if side > 0 else 1.0))

    base_z_ft = min(p.Z for p in bar_points) if bar_points else origin.Z
    return engine.build_contact_starters(
        doc, bar_points, inward_dirs, base_z_ft, main_dia_mm, starter_dia_mm,
        anchor_length_mm, splice_length_mm, foundation_cover_mm,
        search_depth_ft=search_depth_mm / _MM_PER_FT)


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
                              vert_is_outer=True,
                              ubar_lap_length_mm=None,
                              anchorage_mm=None):
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
    # a straight bar's end sits ON the cover (Revit snaps it there anyway, 2026-10-01)
    vert_bottom_z = z0 + cover_mm / _MM_PER_FT
    if include_starter_bars:
        # Straight extension down to the real bottom of the foundation below
        # (less cover), so it never pokes out of a shallow strip footing
        # (T2.13, 2026-09-29). The typed length is only a fallback.
        mid = p0 + axis_dir.Multiply(axis.Length / 2.0)
        foundation = engine.find_foundation_below(doc, mid.X, mid.Y, z0)
        if foundation is not None:
            own = engine.get_isolated_solid_bbox(foundation) or foundation.get_BoundingBox(None)
            vert_bottom_z = own.Min.Z + cover_mm / _MM_PER_FT
            starter_mm = (z0 - vert_bottom_z) * _MM_PER_FT
        else:
            starter_mm = starter_length_mm if starter_length_mm and starter_length_mm > 0 \
                else max(40.0 * vert_dia_mm, 15.0 * vert_dia_mm, 500.0)
            vert_bottom_z = z0 - starter_mm / _MM_PER_FT
            warnings.append(u'No foundation detected below the wall — straight starter '
                            u'extension uses the typed length ({:.0f} mm).'.format(starter_mm))
    vert_top_z = z0 + height_ft - cover_mm / _MM_PER_FT
    vert_top_z = vert_bottom_z + whole_step_length_mm(
        (vert_top_z - vert_bottom_z) * _MM_PER_FT) / _MM_PER_FT

    # A slab cast on the wall head (user decision 2026-10-01): the verticals run on into it
    # and end in an L foot under its top mat, turned into the slab; no coronation U-bars.
    slab_top = find_slab_on_wall(doc, host, axis, z0 + height_ft)
    if slab_top is not None:
        slab, slab_top_z = slab_top
        vert_top_z = slab_top_z - (cover_mm + slab_top_mat_mm(doc, slab) + vert_dia_mm / 2.0) / _MM_PER_FT
        if include_top_ubars:
            include_top_ubars = False
        try:
            if not DB.JoinGeometryUtils.AreElementsJoined(doc, host, slab):
                warnings.append(u'The wall and the slab on it ({}) are not joined in the model: '
                                u'join them (Modify > Join) so the section reads as one '
                                u'monolithic element.'.format(slab.Id))
        except Exception:
            pass
    if vert_top_z <= vert_bottom_z + 1.0 / _MM_PER_FT:
        raise ValueError(u'Wall is too short for the given cover and bar diameter.')

    vert_positions = _evenly_spaced_mm(length_mm, vert_spacing_mm, end_clear_mm)
    top_u_dia = ubar_dia_mm if ubar_dia_mm else vert_dia_mm
    # With coronation U-bars the top horizontal bar stays under the U-bar back.
    top_clear_mm = (cover_mm + top_u_dia + horiz_dia_mm / 2.0) if include_top_ubars else end_clear_mm
    horiz_positions = _evenly_spaced_mm(height_mm, horiz_spacing_mm, end_clear_mm,
                                        max(end_clear_mm, top_clear_mm))

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
    locations = wall_face_codes(doc, host, faces, axis)
    foot_dirs, foot_mm = {}, 0.0
    if slab_top is not None:
        foot_dirs = slab_foot_directions(doc, host, faces, axis, slab_top[1])
        anchor = anchorage_mm if anchorage_mm else 40.0 * vert_dia_mm
        embed_mm = (vert_top_z - (z0 + height_ft)) * _MM_PER_FT
        foot_mm = 25.0 * math.ceil(max(anchor - embed_mm, 12.0 * vert_dia_mm) / 25.0 - 1e-9)
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
            top_z = vert_top_z
            if foot_mm and id(face) in foot_dirs and foot_dirs[id(face)].DotProduct(face_normal) < 0:
                # this face's feet cross over the other face's bars: one diameter lower
                top_z -= vert_dia_mm / _MM_PER_FT
            end = DB.XYZ(start.X, start.Y, top_z)
            curves = [DB.Line.CreateBound(start, end)]
            if foot_mm and id(face) in foot_dirs:
                curves.append(DB.Line.CreateBound(
                    end, end + foot_dirs[id(face)].Multiply(foot_mm / _MM_PER_FT)))
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
                'location': locations.get(id(face)),
            })

        if horiz_positions:
            h0_mm = horiz_positions[0]
            # whole 25 mm length, so the scheduled A and cut length agree (BS 8666)
            lo_mm, hi_mm = _trim_to_step_mm(end_clear_mm, length_mm - end_clear_mm)
            start = p0 + axis_dir.Multiply(lo_mm / _MM_PER_FT) + face_normal.Multiply(horiz_depth)
            end = p0 + axis_dir.Multiply(hi_mm / _MM_PER_FT) + face_normal.Multiply(horiz_depth)
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
                    'location': locations.get(id(face)),
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
        # End U-bars as on slab edges (2026-10-01): one beside each horizontal bar, in
        # the horizontal bars' own layer, legs a full lap with them, back at cover +
        # radius from the wall end.
        u_dia = ubar_dia_mm if ubar_dia_mm else vert_dia_mm
        fa, na, _ = face_depths[id(face_a)]
        fb, nb, _ = face_depths[id(face_b)]
        da = (engine.compute_cover_point(fa, horiz_inset_mm) - p0).DotProduct(na)
        db = (engine.compute_cover_point(fb, horiz_inset_mm) - p0).DotProduct(nb)
        leg_mm = ubar_lap_length_mm if ubar_lap_length_mm else max(40.0 * u_dia, 15.0 * u_dia, 300.0)
        max_leg_mm = length_mm - 2.0 * cover_mm - u_dia
        if leg_mm > max_leg_mm:
            warnings.append(u'End U-bar legs cut to {:.0f} mm by the wall length (lap {:.0f} mm).'.format(
                max_leg_mm, leg_mm))
            leg_mm = max_leg_mm
        back_mm = cover_mm + u_dia / 2.0
        top_limit_mm = height_mm - max(end_clear_mm, top_clear_mm)
        u_heights = top_ubar_positions_mm(horiz_positions, top_limit_mm + end_clear_mm,
                                          horiz_dia_mm, u_dia, end_clear_mm)
        end_ubar_sets, end_ubar_bars = [], []
        for d_end, inward in ((back_mm, axis_dir), (length_mm - back_mm, axis_dir.Multiply(-1.0))):
            base = p0 + axis_dir.Multiply(d_end / _MM_PER_FT)

            def _u_at(h_mm, base=base, inward=inward):
                z = z0 + h_mm / _MM_PER_FT
                pa = DB.XYZ((base + na.Multiply(da)).X, (base + na.Multiply(da)).Y, z)
                pb = DB.XYZ((base + nb.Multiply(db)).X, (base + nb.Multiply(db)).Y, z)
                if pa.DistanceTo(pb) < 1.0 / _MM_PER_FT:
                    return None
                return [DB.Line.CreateBound(pa + inward.Multiply(leg_mm / _MM_PER_FT), pa),
                        DB.Line.CreateBound(pa, pb),
                        DB.Line.CreateBound(pb, pb + inward.Multiply(leg_mm / _MM_PER_FT))]

            for run in uniform_runs_mm(u_heights):
                chains = [c for c in (_u_at(h) for h in run) if c is not None]
                if len(chains) >= 2 and len(chains) == len(run):
                    end_ubar_sets.append({
                        'curves': chains[0], 'normal': DB.XYZ.BasisZ,
                        'array_length_mm': run[-1] - run[0],
                        'spacing_mm': (run[1] - run[0]) + 0.01,
                        'materialized_bars': [{'curves': c, 'normal': DB.XYZ.BasisZ} for c in chains],
                        'label': u'Wall End U-Bar',
                    })
                else:
                    for c in chains:
                        end_ubar_bars.append({'curves': c, 'normal': DB.XYZ.BasisZ,
                                              'label': u'Wall End U-Bar'})
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
        # Coronation U-bars as on slab and footing edges (2026-10-01): one beside each
        # vertical bar, in the vertical bars' own layer, legs a full lap with them,
        # back at cover + radius under the wall head.
        u_dia = top_u_dia
        fa, na, da = face_depths[id(face_a)]
        fb, nb, db = face_depths[id(face_b)]
        leg_mm = ubar_lap_length_mm if ubar_lap_length_mm else max(40.0 * u_dia, 15.0 * u_dia, 300.0)
        max_leg_mm = height_mm - 2.0 * cover_mm - u_dia
        if leg_mm > max_leg_mm:
            warnings.append(u'Top U-bar legs cut to {:.0f} mm by the wall height (lap {:.0f} mm).'.format(
                max_leg_mm, leg_mm))
            leg_mm = max_leg_mm
        z_top = z0 + height_ft - (cover_mm + u_dia / 2.0) / _MM_PER_FT
        u_positions = top_ubar_positions_mm(vert_positions, length_mm, vert_dia_mm, u_dia, end_clear_mm)

        def _u_at(d_mm):
            base = p0 + axis_dir.Multiply(d_mm / _MM_PER_FT)
            pa = DB.XYZ((base + na.Multiply(da)).X, (base + na.Multiply(da)).Y, z_top)
            pb = DB.XYZ((base + nb.Multiply(db)).X, (base + nb.Multiply(db)).Y, z_top)
            if pa.DistanceTo(pb) < 1.0 / _MM_PER_FT:
                return None
            return [DB.Line.CreateBound(DB.XYZ(pa.X, pa.Y, z_top - leg_mm / _MM_PER_FT), pa),
                    DB.Line.CreateBound(pa, pb),
                    DB.Line.CreateBound(pb, DB.XYZ(pb.X, pb.Y, z_top - leg_mm / _MM_PER_FT))]

        top_ubar_sets, top_ubar_bars = [], []
        for run in uniform_runs_mm(u_positions):
            chains = [c for c in (_u_at(d) for d in run) if c is not None]
            if len(chains) >= 2 and len(chains) == len(run):
                # The shape lies in the plane {Z, wall thickness}: its normal is the wall axis.
                top_ubar_sets.append({
                    'curves': chains[0], 'normal': axis_dir,
                    'array_length_mm': run[-1] - run[0],
                    # a hair over the true step, so Revit never lays out one bar too many
                    'spacing_mm': (run[1] - run[0]) + 0.01,
                    'materialized_bars': [{'curves': c, 'normal': axis_dir} for c in chains],
                    'label': u'Wall Top U-Bar',
                })
            else:
                for c in chains:
                    top_ubar_bars.append({'curves': c, 'normal': axis_dir, 'label': u'Wall Top U-Bar'})
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
                    tail = ms['curves'][1:] if i == len(seg_list) - 1 else []
                    out.append({
                        'curves': [seg.curve] + tail,
                        'spacing_mm': ms['spacing_mm'],
                        'array_length_mm': ms['array_length_mm'],
                        'normal': ms['normal'],
                        'count': ms['count'],
                        'label': u'{} (segment {})'.format(ms.get('label', axis_label), i + 1),
                        'location': ms.get('location'),
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
