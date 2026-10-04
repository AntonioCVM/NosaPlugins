# -*- coding: utf-8 -*-
"""
GA Auto-Dimension v1.0 — Logic

Module 1: Off-grid elements (columns, foundations) → H/V dims to nearest grid
Module 2: Structural walls    → length dim + alignment to grid
Module 3: Floor/slab corners  → corner dims to nearest H/V grid
"""
from Autodesk.Revit import DB
from pyrevit import revit
from nosa_utils import unit_conversion as _uc10
from nosa_utils.telemetry import log_swallowed
from nosa_utils import transactions as nosa_tx  # T8.1: no Revit failure dialogs
_LOG = u'annotationhub'
# ── constants ──────────────────────────────────────────────────────────────────
FT2MM      = _uc10.FT_TO_MM  # feet → mm
MM2FT      = _uc10.MM_TO_FT   # mm  → feet

DEFAULT_OFFSET_PAPER_MM = 8.0            # element-to-dimension-line distance on paper
_FALLBACK_OFFSET_FT     = 2000.0 * MM2FT  # 2 m model units if view scale unreadable


def dim_offset_ft(view, paper_mm=DEFAULT_OFFSET_PAPER_MM):
    """
    Dimension-line offset in feet, constant on paper: paper_mm × view scale.
    8 mm at 1:50 → 400 mm model; at 1:100 → 800 mm model.
    """
    try:
        scale = int(view.Scale)
        if scale > 0:
            return paper_mm * scale * MM2FT
    except Exception:
        log_swallowed(_LOG, u'dim_offset_ft')
    return _FALLBACK_OFFSET_FT

# BuiltInCategory constants resolved lazily inside functions — not at module level
# (module-level DB.BuiltInCategory.* fails in IronPython before Revit context is active)

# ── helpers ────────────────────────────────────────────────────────────────────

def _col(doc, bic):
    return list(DB.FilteredElementCollector(doc)
                .OfCategory(bic)
                .WhereElementIsNotElementType()
                .ToElements())


def _elem_center(el):
    """Return XYZ centre of element from location or bounding box."""
    try:
        loc = el.Location
        if isinstance(loc, DB.LocationPoint):
            return loc.Point
        if isinstance(loc, DB.LocationCurve):
            c = loc.Curve
            return c.Evaluate(0.5, True)
    except Exception:
        log_swallowed(_LOG, u'_elem_center')
    try:
        bb = el.get_BoundingBox(None)
        if bb:
            return (bb.Min + bb.Max) * 0.5
    except Exception:
        log_swallowed(_LOG, u'_elem_center')
    return None


def _line_pt(line):
    """Mid-point of a line."""
    return line.Evaluate(0.5, True)


# ── GRID UTILITIES ─────────────────────────────────────────────────────────────

def get_grids(doc):
    """
    Return {'h': [...], 'v': [...]} separating grids by dominant direction.
    'h' grids run in X (define Y positions).
    'v' grids run in Y (define X positions).
    Non-linear grids are ignored.
    """
    h_grids, v_grids = [], []
    for g in (DB.FilteredElementCollector(doc)
              .OfClass(DB.Grid)
              .WhereElementIsNotElementType()
              .ToElements()):
        try:
            curve = g.Curve
            if not isinstance(curve, DB.Line):
                continue
            d = curve.Direction
            if abs(d.X) >= abs(d.Y):
                h_grids.append(g)  # mostly horizontal
            else:
                v_grids.append(g)  # mostly vertical
        except Exception:
            log_swallowed(_LOG, u'get_grids')
    return {'h': h_grids, 'v': v_grids}


def _grid_fixed_coord(grid):
    """
    For a grid that runs horizontally (h): returns the Y coordinate.
    For a grid that runs vertically (v): returns the X coordinate.
    """
    pt = grid.Curve.GetEndPoint(0)
    d  = grid.Curve.Direction
    if abs(d.X) >= abs(d.Y):
        return pt.Y  # horizontal grid → fixed Y
    else:
        return pt.X  # vertical grid   → fixed X


def _nearest_grid(grids, coord):
    """Return the grid whose fixed coordinate is nearest to `coord`."""
    best, best_dist = None, float('inf')
    for g in grids:
        dist = abs(_grid_fixed_coord(g) - coord)
        if dist < best_dist:
            best_dist = dist
            best = g
    return best, best_dist


def _grid_ref(grid):
    """Return a Reference to the grid for use in Dimension."""
    return DB.Reference(grid)


# ── GEOMETRY REFERENCE HELPERS ─────────────────────────────────────────────────

def _geo_opts(view=None):
    opts = DB.Options()
    opts.ComputeReferences = True
    opts.IncludeNonVisibleObjects = False
    if view is not None:
        opts.View = view
    return opts


def _faces_in_direction(el, target_normal, view=None):
    """
    Return all PlanarFace references whose normal is closest to target_normal.
    target_normal: DB.XYZ (e.g. BasisX or BasisY)
    """
    opts = _geo_opts(view)
    result = []
    try:
        geo = el.get_Geometry(opts)
    except Exception:
        return result

    def _process_solid(solid):
        for face in solid.Faces:
            try:
                if not isinstance(face, DB.PlanarFace):
                    continue
                n = face.FaceNormal
                dot = abs(n.X * target_normal.X + n.Y * target_normal.Y)
                if dot > 0.85:
                    result.append(face.Reference)
            except Exception:
                log_swallowed(_LOG, u'_process_solid')

    for obj in geo:
        if isinstance(obj, DB.GeometryInstance):
            for sub in obj.GetInstanceGeometry():
                if isinstance(sub, DB.Solid) and sub.Volume > 1e-9:
                    _process_solid(sub)
        elif isinstance(obj, DB.Solid) and obj.Volume > 1e-9:
            _process_solid(obj)

    return result


def _center_ref_family(el, direction):
    """
    Try GetReferenceByName for family instance center planes.
    direction: 'x' or 'y'
    Returns DB.Reference or None.
    """
    if not isinstance(el, DB.FamilyInstance):
        return None
    names = {
        'x': ["Center (Left/Right)", "Centro (Izq/Der)", "Eje X", "Left",  "Right",
              "Centre (Left/Right)", "CL", "Center LR"],
        'y': ["Center (Front/Back)", "Centro (Del/Det)", "Eje Y", "Front", "Back",
              "Centre (Front/Back)", "Center FB"],
    }
    for name in names.get(direction, []):
        try:
            ref = el.GetReferenceByName(name)
            if ref:
                return ref
        except Exception:
            log_swallowed(_LOG, u'_center_ref_family')
    return None


def _best_ref_for_dir(el, direction, view=None):
    """
    Return the best single DB.Reference for dimensioning in `direction`.
    For X direction: a face whose normal is in ±X → allows measuring X distance.
    For Y direction: a face whose normal is in ±Y → allows measuring Y distance.
    Falls back to geometry faces if named refs not found.
    """
    # Try named center references first (columns)
    ref = _center_ref_family(el, direction)
    if ref:
        return ref

    # Fall back to geometry face in the required direction
    normal = DB.XYZ.BasisX if direction == 'x' else DB.XYZ.BasisY
    refs = _faces_in_direction(el, normal, view)
    if refs:
        return refs[0]
    return None


# ── DIMENSION CREATION HELPERS ─────────────────────────────────────────────────

def _existing_dim_signatures(view):
    """
    Build a set of frozensets of stable reference representations for all
    dimensions already in the view. Used to skip duplicate dimensions.
    """
    sigs = set()
    try:
        for dim in (DB.FilteredElementCollector(view.Document)
                      .OwnedByView(view.Id)
                      .OfClass(DB.Dimension)
                      .ToElements()):
            try:
                refs = dim.References
                if refs is None:
                    continue
                key = frozenset(r.ConvertToStableRepresentation(view.Document)
                                for r in refs)
                sigs.add(key)
            except Exception:
                log_swallowed(_LOG, u'_existing_dim_signatures')
    except Exception:
        log_swallowed(_LOG, u'_existing_dim_signatures')
    return sigs


def _create_dim(doc, view, refs, line, existing_sigs=None):
    """
    Create a dimension in `view` along `line` through `refs`.
    Skips creation if an equivalent dimension already exists (same references).
    Returns DB.Dimension or None.
    """
    if len(refs) < 2:
        return None

    # Duplicate check
    if existing_sigs is not None:
        try:
            key = frozenset(r.ConvertToStableRepresentation(doc) for r in refs)
            if key in existing_sigs:
                return None
            existing_sigs.add(key)
        except Exception:
            log_swallowed(_LOG, u'_create_dim')

    ref_arr = DB.ReferenceArray()
    for r in refs:
        ref_arr.Append(r)
    try:
        return doc.Create.NewDimension(view, line, ref_arr)
    except Exception:
        return None


def _horiz_dim_line(y, x0, x1):
    """Horizontal dimension line at Y=y from x0 to x1."""
    return DB.Line.CreateBound(DB.XYZ(x0, y, 0), DB.XYZ(x1, y, 0))


def _vert_dim_line(x, y0, y1):
    """Vertical dimension line at X=x from y0 to y1."""
    return DB.Line.CreateBound(DB.XYZ(x, y0, 0), DB.XYZ(x, y1, 0))


# ── MODULE 1: OFF-GRID ELEMENTS ────────────────────────────────────────────────

def _is_off_grid(center, grids_h, grids_v, tol_ft):
    """Returns (off_h, off_v) booleans. off_h=True means not on any H grid."""
    off_h = all(abs(_grid_fixed_coord(g) - center.Y) > tol_ft for g in grids_h)
    off_v = all(abs(_grid_fixed_coord(g) - center.X) > tol_ft for g in grids_v)
    return off_h, off_v


def run_module1(doc, view, grids, tolerance_mm=50, dry_run=False, offset_ft=None):
    """
    Dimension structural columns + foundations that are off-grid.
    Returns (dims_created, elements_skipped, errors).
    """
    if offset_ft is None:
        offset_ft = dim_offset_ft(view)
    existing_sigs = _existing_dim_signatures(view)
    tol_ft  = tolerance_mm * MM2FT
    grids_h = grids['h']
    grids_v = grids['v']

    if not grids_h and not grids_v:
        return 0, 0, ['No gridlines found in the project.']

    bics = [DB.BuiltInCategory.OST_StructuralColumns, DB.BuiltInCategory.OST_StructuralFoundation]
    elements = []
    for bic in bics:
        elements.extend(_col(doc, bic))

    dims_created = 0
    skipped      = 0
    errors       = []

    for el in elements:
        try:
            center = _elem_center(el)
            if center is None:
                skipped += 1
                continue

            off_h, off_v = _is_off_grid(center, grids_h, grids_v, tol_ft)
            if not off_h and not off_v:
                continue

            if dry_run:
                dims_created += (1 if off_h else 0) + (1 if off_v else 0)
                continue

            # ── dim measuring Y distance (to horizontal grid) ──────────────
            if off_h and grids_h:
                nearest_hg, _ = _nearest_grid(grids_h, center.Y)
                hg_y   = _grid_fixed_coord(nearest_hg)
                el_ref = _best_ref_for_dir(el, 'y', view)
                gref   = _grid_ref(nearest_hg)
                if el_ref and gref:
                    x_pos = center.X + offset_ft
                    y_min = min(center.Y, hg_y) - 0.5
                    y_max = max(center.Y, hg_y) + 0.5
                    line  = _vert_dim_line(x_pos, y_min, y_max)
                    dim   = _create_dim(doc, view, [el_ref, gref], line, existing_sigs)
                    if dim:
                        dims_created += 1
                    else:
                        skipped += 1
                else:
                    skipped += 1

            # ── dim measuring X distance (to vertical grid) ────────────────
            if off_v and grids_v:
                nearest_vg, _ = _nearest_grid(grids_v, center.X)
                vg_x   = _grid_fixed_coord(nearest_vg)
                el_ref = _best_ref_for_dir(el, 'x', view)
                gref   = _grid_ref(nearest_vg)
                if el_ref and gref:
                    y_pos = center.Y - offset_ft
                    x_min = min(center.X, vg_x) - 0.5
                    x_max = max(center.X, vg_x) + 0.5
                    line  = _horiz_dim_line(y_pos, x_min, x_max)
                    dim   = _create_dim(doc, view, [el_ref, gref], line, existing_sigs)
                    if dim:
                        dims_created += 1
                    else:
                        skipped += 1
                else:
                    skipped += 1

        except Exception as e:
            errors.append(u'Element {}: {}'.format(el.Id, e))
            skipped += 1

    return dims_created, skipped, errors


# ── MODULE 2: WALL DIMENSIONS ──────────────────────────────────────────────────

def _wall_refs_at_ends(wall, view):
    """
    Return references at the start and end faces of the wall
    (faces perpendicular to the wall axis).
    """
    try:
        loc = wall.Location
        if not isinstance(loc, DB.LocationCurve):
            return None, None
        curve = loc.Curve
        wall_dir = (curve.GetEndPoint(1) - curve.GetEndPoint(0)).Normalize()

        opts = _geo_opts(view)
        geo  = wall.get_Geometry(opts)
        refs = []
        for obj in geo:
            if isinstance(obj, DB.Solid) and obj.Volume > 1e-9:
                for face in obj.Faces:
                    if not isinstance(face, DB.PlanarFace):
                        continue
                    n   = face.FaceNormal
                    dot = abs(n.X * wall_dir.X + n.Y * wall_dir.Y)
                    if dot > 0.85:
                        refs.append(face.Reference)
            if len(refs) >= 2:
                break
        if len(refs) >= 2:
            return refs[0], refs[1]
    except Exception:
        log_swallowed(_LOG, u'_wall_refs_at_ends')
    return None, None


def _wall_side_refs(wall, view, grids_h, grids_v):
    """
    Return references of wall faces perpendicular to wall normal
    (for perpendicular-to-grid dimension).
    """
    try:
        loc = wall.Location
        if not isinstance(loc, DB.LocationCurve):
            return []
        curve = loc.Curve
        wall_dir = (curve.GetEndPoint(1) - curve.GetEndPoint(0)).Normalize()
        # wall normal (perpendicular to axis, in XY plane)
        wall_normal = DB.XYZ(-wall_dir.Y, wall_dir.X, 0)

        opts = _geo_opts(view)
        geo  = wall.get_Geometry(opts)
        refs = []
        for obj in geo:
            if isinstance(obj, DB.Solid) and obj.Volume > 1e-9:
                for face in obj.Faces:
                    if not isinstance(face, DB.PlanarFace):
                        continue
                    n   = face.FaceNormal
                    dot = abs(n.X * wall_normal.X + n.Y * wall_normal.Y)
                    if dot > 0.85:
                        refs.append(face.Reference)
            if len(refs) >= 2:
                return refs[:2]
    except Exception:
        log_swallowed(_LOG, u'_wall_side_refs')
    return []


def run_module2(doc, view, grids, dry_run=False, offset_ft=None):
    """
    Dimension structural walls: length + nearest-grid alignment.
    Returns (dims_created, skipped, errors).
    """
    if offset_ft is None:
        offset_ft = dim_offset_ft(view)
    existing_sigs = _existing_dim_signatures(view)
    walls = [w for w in _col(doc, DB.BuiltInCategory.OST_Walls)
             if w.StructuralUsage != DB.Structure.StructuralWallUsage.NonBearing
             or w.get_Parameter(DB.BuiltInParameter.WALL_STRUCTURAL_SIGNIFICANT) is not None]
    # Fallback: all walls in view
    if not walls:
        walls = _col(doc, DB.BuiltInCategory.OST_Walls)

    dims_created = 0
    skipped      = 0
    errors       = []
    grids_h = grids['h']
    grids_v = grids['v']

    for wall in walls:
        try:
            loc = wall.Location
            if not isinstance(loc, DB.LocationCurve):
                skipped += 1
                continue
            curve    = loc.Curve
            pt_start = curve.GetEndPoint(0)
            pt_end   = curve.GetEndPoint(1)
            center   = _elem_center(wall)
            wall_dir = (pt_end - pt_start).Normalize()

            if dry_run:
                dims_created += 2
                continue

            # ── Length dimension ──────────────────────────────────────────
            ref0, ref1 = _wall_refs_at_ends(wall, view)
            if ref0 and ref1:
                perp     = DB.XYZ(-wall_dir.Y, wall_dir.X, 0)
                mid      = (pt_start + pt_end) * 0.5
                off_pt   = mid + perp * offset_ft
                half_len = curve.Length * 0.5 + 1.0
                d0       = off_pt - wall_dir * half_len
                d1       = off_pt + wall_dir * half_len
                dline    = DB.Line.CreateBound(d0, d1)
                dim      = _create_dim(doc, view, [ref0, ref1], dline, existing_sigs)
                if dim:
                    dims_created += 1
                else:
                    skipped += 1
            else:
                skipped += 1

            # ── Alignment dimension (wall to nearest grid) ────────────────
            side_refs = _wall_side_refs(wall, view, grids_h, grids_v)
            if len(side_refs) >= 2 and center:
                is_horiz = abs(wall_dir.X) > abs(wall_dir.Y)
                if is_horiz and grids_h:
                    nearest_hg, _ = _nearest_grid(grids_h, center.Y)
                    gref  = _grid_ref(nearest_hg)
                    hg_y  = _grid_fixed_coord(nearest_hg)
                    x_pos = center.X + offset_ft * 1.5
                    y_min = min(center.Y, hg_y) - 0.5
                    y_max = max(center.Y, hg_y) + 0.5
                    dline = _vert_dim_line(x_pos, y_min, y_max)
                    dim   = _create_dim(doc, view, [side_refs[0], gref], dline, existing_sigs)
                    if dim:
                        dims_created += 1
                    else:
                        skipped += 1
                elif not is_horiz and grids_v:
                    nearest_vg, _ = _nearest_grid(grids_v, center.X)
                    gref  = _grid_ref(nearest_vg)
                    vg_x  = _grid_fixed_coord(nearest_vg)
                    y_pos = center.Y - offset_ft * 1.5
                    x_min = min(center.X, vg_x) - 0.5
                    x_max = max(center.X, vg_x) + 0.5
                    dline = _horiz_dim_line(y_pos, x_min, x_max)
                    dim   = _create_dim(doc, view, [side_refs[0], gref], dline, existing_sigs)
                    if dim:
                        dims_created += 1
                    else:
                        skipped += 1

        except Exception as e:
            errors.append(u'Wall {}: {}'.format(wall.Id, e))
            skipped += 1

    return dims_created, skipped, errors


# ── MODULE 3: FLOOR/SLAB CORNERS ───────────────────────────────────────────────

def _floor_corner_points(floor):
    """
    Extract corner points from the floor's top face boundary.
    Returns list of (XYZ, edge_ref_along_X, edge_ref_along_Y) tuples.
    Uses geometry edges of the top face.
    """
    opts = _geo_opts()
    corners = []  # list of (pt, ref_h, ref_v) — refs may be None
    try:
        geo = floor.get_Geometry(opts)
        top_face = None
        for obj in geo:
            if isinstance(obj, DB.Solid) and obj.Volume > 1e-9:
                for face in obj.Faces:
                    if not isinstance(face, DB.PlanarFace):
                        continue
                    n = face.FaceNormal
                    if n.Z > 0.9:
                        top_face = face
                        break
            if top_face:
                break

        if top_face is None:
            return []

        # Build vertex → edge map for the outer loop
        outer_loop = list(top_face.EdgeLoops)[0]
        edges      = list(outer_loop)

        # Find corner vertices (where two edges meet)
        for i, edge in enumerate(edges):
            pt  = edge.AsCurve().GetEndPoint(0)
            ref = edge.Reference
            corners.append((pt, ref))

    except Exception:
        log_swallowed(_LOG, u'_floor_corner_points')
    return corners


def run_module3(doc, view, grids, dry_run=False, offset_ft=None):
    """
    Dimension floor/slab corners to nearest H and V grids.
    Returns (dims_created, skipped, errors).
    """
    if offset_ft is None:
        offset_ft = dim_offset_ft(view)
    existing_sigs = _existing_dim_signatures(view)
    floors   = _col(doc, DB.BuiltInCategory.OST_Floors)
    grids_h  = grids['h']
    grids_v  = grids['v']

    if not grids_h and not grids_v:
        return 0, 0, ['No gridlines to dimension slab corners.']

    dims_created = 0
    skipped      = 0
    errors       = []

    for floor in floors:
        try:
            corners = _floor_corner_points(floor)
            if not corners:
                skipped += 1
                continue

            if dry_run:
                dims_created += len(corners) * 2
                continue

            for (pt, edge_ref) in corners:
                if edge_ref is None:
                    skipped += 2
                    continue

                # ── Y dim: corner to nearest H grid ────────────────────────
                if grids_h:
                    nearest_hg, dist_h = _nearest_grid(grids_h, pt.Y)
                    if dist_h > 0.01:
                        hg_y  = _grid_fixed_coord(nearest_hg)
                        gref  = _grid_ref(nearest_hg)
                        x_pos = pt.X + offset_ft
                        y_min = min(pt.Y, hg_y) - 0.5
                        y_max = max(pt.Y, hg_y) + 0.5
                        dline = _vert_dim_line(x_pos, y_min, y_max)
                        dim   = _create_dim(doc, view, [edge_ref, gref], dline, existing_sigs)
                        if dim:
                            dims_created += 1
                        else:
                            skipped += 1

                # ── X dim: corner to nearest V grid ────────────────────────
                if grids_v:
                    nearest_vg, dist_v = _nearest_grid(grids_v, pt.X)
                    if dist_v > 0.01:
                        vg_x  = _grid_fixed_coord(nearest_vg)
                        gref  = _grid_ref(nearest_vg)
                        y_pos = pt.Y - offset_ft
                        x_min = min(pt.X, vg_x) - 0.5
                        x_max = max(pt.X, vg_x) + 0.5
                        dline = _horiz_dim_line(y_pos, x_min, x_max)
                        dim   = _create_dim(doc, view, [edge_ref, gref], dline, existing_sigs)
                        if dim:
                            dims_created += 1
                        else:
                            skipped += 1

        except Exception as e:
            errors.append(u'Slab {}: {}'.format(floor.Id, e))
            skipped += 1

    return dims_created, skipped, errors


# ── MODULE 4: GRID SPACING CHAINS ─────────────────────────────────────────────

def _grid_extents(grids):
    """Return (min_x, max_x, min_y, max_y) across all grid curves."""
    xs, ys = [], []
    for g in grids:
        try:
            c  = g.Curve
            p0 = c.GetEndPoint(0)
            p1 = c.GetEndPoint(1)
            xs.extend([p0.X, p1.X])
            ys.extend([p0.Y, p1.Y])
        except Exception:
            log_swallowed(_LOG, u'_grid_extents')
    if not xs:
        return 0.0, 0.0, 0.0, 0.0
    return min(xs), max(xs), min(ys), max(ys)


def run_module4(doc, view, grids, dry_run=False, offset_ft=None):
    """
    Create one continuous dimension chain between all H-grids (measuring Y spacings)
    and one between all V-grids (measuring X spacings).
    Returns (dims_created, skipped, errors).
    """
    if offset_ft is None:
        offset_ft = dim_offset_ft(view)
    existing_sigs = _existing_dim_signatures(view)
    h_grids = sorted(grids['h'], key=lambda g: _grid_fixed_coord(g))
    v_grids = sorted(grids['v'], key=lambda g: _grid_fixed_coord(g))

    dims_created = 0
    skipped      = 0
    errors       = []

    if len(h_grids) < 2 and len(v_grids) < 2:
        return 0, 0, [u'Need at least 2 parallel gridlines in each direction.']

    if dry_run:
        if len(h_grids) >= 2:
            dims_created += 1
        if len(v_grids) >= 2:
            dims_created += 1
        return dims_created, skipped, errors

    all_grids = h_grids + v_grids
    min_x, max_x, min_y, max_y = _grid_extents(all_grids)
    margin = 2.0  # feet

    # ── H-grid chain: vertical dimension line placed to the right ──────────────
    if len(h_grids) >= 2:
        try:
            h_ys  = [_grid_fixed_coord(g) for g in h_grids]
            dim_x = max_x + offset_ft * 2.5
            line  = _vert_dim_line(dim_x,
                                   min(h_ys) - margin,
                                   max(h_ys) + margin)
            refs  = [_grid_ref(g) for g in h_grids]
            dim   = _create_dim(doc, view, refs, line, existing_sigs)
            if dim:
                dims_created += 1
            else:
                skipped += 1
        except Exception as e:
            errors.append(u'H-grid chain: {}'.format(e))
            skipped += 1

    # ── V-grid chain: horizontal dimension line placed below ───────────────────
    if len(v_grids) >= 2:
        try:
            v_xs  = [_grid_fixed_coord(g) for g in v_grids]
            dim_y = min_y - offset_ft * 2.5
            line  = _horiz_dim_line(dim_y,
                                    min(v_xs) - margin,
                                    max(v_xs) + margin)
            refs  = [_grid_ref(g) for g in v_grids]
            dim   = _create_dim(doc, view, refs, line, existing_sigs)
            if dim:
                dims_created += 1
            else:
                skipped += 1
        except Exception as e:
            errors.append(u'V-grid chain: {}'.format(e))
            skipped += 1

    return dims_created, skipped, errors


# ── MAIN RUNNER ────────────────────────────────────────────────────────────────

def run(doc, view, options):
    """
    options = {
        'mod1': bool, 'mod2': bool, 'mod3': bool,
        'tolerance_mm': float,
        'offset_paper_mm': float,   # dimension line offset on paper (default 8)
        'dry_run': bool,
    }
    Returns dict with results per module.
    """
    grids       = get_grids(doc)
    tolerance   = options.get('tolerance_mm', 50)
    dry_run     = options.get('dry_run', False)
    offset_ft   = dim_offset_ft(view, options.get('offset_paper_mm',
                                                  DEFAULT_OFFSET_PAPER_MM))

    results = {
        'grids_h': len(grids['h']),
        'grids_v': len(grids['v']),
        'mod1':    None,
        'mod2':    None,
        'mod3':    None,
        'mod4':    None,
    }

    def _wrap(fn, *args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except Exception as e:
            return 0, 0, [u'General error: {}'.format(e)]

    if options.get('mod1', True):
        if dry_run:
            c, s, e = _wrap(run_module1, doc, view, grids, tolerance, True,
                            offset_ft=offset_ft)
        else:
            with nosa_tx.revit_transaction(u'NOSA — GA Auto-Dim: Off-grid elements'):
                c, s, e = _wrap(run_module1, doc, view, grids, tolerance, False,
                                offset_ft=offset_ft)
        results['mod1'] = {'created': c, 'skipped': s, 'errors': e}

    if options.get('mod2', True):
        if dry_run:
            c, s, e = _wrap(run_module2, doc, view, grids, True,
                            offset_ft=offset_ft)
        else:
            with nosa_tx.revit_transaction(u'NOSA — GA Auto-Dim: Walls'):
                c, s, e = _wrap(run_module2, doc, view, grids, False,
                                offset_ft=offset_ft)
        results['mod2'] = {'created': c, 'skipped': s, 'errors': e}

    if options.get('mod3', True):
        if dry_run:
            c, s, e = _wrap(run_module3, doc, view, grids, True,
                            offset_ft=offset_ft)
        else:
            with nosa_tx.revit_transaction(u'NOSA — GA Auto-Dim: Slab corners'):
                c, s, e = _wrap(run_module3, doc, view, grids, False,
                                offset_ft=offset_ft)
        results['mod3'] = {'created': c, 'skipped': s, 'errors': e}

    if options.get('mod4', False):
        if dry_run:
            c, s, e = _wrap(run_module4, doc, view, grids, True,
                            offset_ft=offset_ft)
        else:
            with nosa_tx.revit_transaction(u'NOSA — GA Auto-Dim: Grid spacing chains'):
                c, s, e = _wrap(run_module4, doc, view, grids, False,
                                offset_ft=offset_ft)
        results['mod4'] = {'created': c, 'skipped': s, 'errors': e}

    return results
