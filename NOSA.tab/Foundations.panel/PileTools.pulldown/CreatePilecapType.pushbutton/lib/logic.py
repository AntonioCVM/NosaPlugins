# -*- coding: utf-8 -*-
"""Create Pile Cap Logic — regular grid + irregular shapes (L, T, Plus, Z, U)."""
from Autodesk.Revit import DB
from nosa_utils import unit_conversion as _uc10
from nosa_utils.pilecap_utils import point_in_polygon, distance_to_polygon_edge

_MM_TO_FT = _uc10.MM_TO_FT


# ── Standard rectangular helpers ──────────────────────────────────────────────

def calc_dimensions(n_h, n_v, spacing_mm, clearance_mm):
    return float((n_h - 1) * spacing_mm + 2 * clearance_mm), \
           float((n_v - 1) * spacing_mm + 2 * clearance_mm)


_EXCLUDE_FOUNDATION_KEYS = (
    'foundation slab', 'foundation_slab', 'raft', 'pile cap', 'pilecap',
    'pile cap slab', 'strip footing', 'strap', 'combined footing',
    'wall footing', 'wall foundation', 'isolated footing', 'spread footing',
    'spread_footing', 'bearing pad',
)
_PILE_INCLUDE_KEYS = (
    'pile', 'piling', 'pilote', 'micropile', 'percussion pile',
    'bored pile', 'steel pipe circular', 'pipe pile', 'tubular pile',
)


def _type_label(ft):
    fam_name  = (getattr(ft.Family, 'Name', None) or u'') if (hasattr(ft, 'Family') and ft.Family) else u''
    sym_param = ft.get_Parameter(DB.BuiltInParameter.SYMBOL_NAME_PARAM)
    return fam_name, (sym_param.AsString() if sym_param else u'')


def _is_pile_candidate_foundation(fam_name, type_name):
    blob = u'{} {}'.format((fam_name or u'').lower(), (type_name or u'').lower())
    if any(k in blob for k in _EXCLUDE_FOUNDATION_KEYS):
        return False
    return any(k in blob for k in _PILE_INCLUDE_KEYS)


def get_pile_types(doc):
    result = []
    for t in (DB.FilteredElementCollector(doc)
              .OfCategory(DB.BuiltInCategory.OST_StructuralFoundation)
              .WhereElementIsElementType().ToElements()):
        try:
            fam_name, type_name = _type_label(t)
            if not _is_pile_candidate_foundation(fam_name, type_name):
                continue
            label = u'{} : {}'.format(fam_name, type_name) if fam_name else type_name
            result.append((t.Id, label or u'(unnamed)'))
        except Exception:
            pass
    result.sort(key=lambda x: x[1])
    return result


def get_cap_types(doc):
    result = []
    for t in DB.FilteredElementCollector(doc).OfClass(DB.FloorType).ToElements():
        try:
            fam_name, type_name = _type_label(t)
            blob = u'{} {}'.format((fam_name or u'').lower(), (type_name or u'').lower())
            if 'foundation slab' in blob or 'foundation_slab' in blob or \
               ('foundation' in blob and 'slab' in blob):
                label = u'{} : {}'.format(fam_name, type_name) if fam_name else type_name
                result.append((t.Id, label or u'(unnamed)'))
        except Exception:
            pass
    result.sort(key=lambda x: x[1])
    if not result:
        for t in DB.FilteredElementCollector(doc).OfClass(DB.FloorType).ToElements():
            try:
                fam_name, type_name = _type_label(t)
                blob = u'{} {}'.format((fam_name or u'').lower(), (type_name or u'').lower())
                if any(k in blob for k in ('structural', 'foundation', 'footing')):
                    label = u'{} : {}'.format(fam_name, type_name) if fam_name else type_name
                    result.append((t.Id, label or u'(unnamed)'))
            except Exception:
                pass
        result.sort(key=lambda x: x[1])
    return result


def get_all_levels(doc):
    levels = []
    for l in DB.FilteredElementCollector(doc).OfClass(DB.Level).ToElements():
        try:
            levels.append((l.Id, l.Name, l.Elevation))
        except Exception:
            pass
    levels.sort(key=lambda x: x[2])
    return [(lid, name) for lid, name, _ in levels]


# ── Revit creation helpers ────────────────────────────────────────────────────

def _create_cap_slab_rect(doc, cx, cy, cz, width_mm, height_mm, cap_type_id, level_id):
    half_w = width_mm  * _MM_TO_FT / 2.0
    half_h = height_mm * _MM_TO_FT / 2.0
    p = [DB.XYZ(cx + sx * half_w, cy + sy * half_h, cz)
         for sx, sy in [(-1,-1),(1,-1),(1,1),(-1,1)]]
    level    = doc.GetElement(level_id)
    cap_type = doc.GetElement(cap_type_id)
    try:
        from System.Collections.Generic import List as _L
        loop = DB.CurveLoop()
        for i in range(4):
            loop.Append(DB.Line.CreateBound(p[i], p[(i+1)%4]))
        loops = _L[DB.CurveLoop]()
        loops.Add(loop)
        return DB.Floor.Create(doc, loops, cap_type_id, level_id)
    except Exception:
        arr = DB.CurveArray()
        for i in range(4):
            arr.Append(DB.Line.CreateBound(p[i], p[(i+1)%4]))
        return doc.Create.NewFloor(arr, cap_type, level, True)


def _create_cap_slab_polygon(doc, pts_mm, cx, cy, cz, cap_type_id, level_id):
    """Create a cap slab from an arbitrary CCW polygon (list of (x_mm, y_mm))."""
    level    = doc.GetElement(level_id)
    cap_type = doc.GetElement(cap_type_id)
    verts = [DB.XYZ(cx + x * _MM_TO_FT, cy + y * _MM_TO_FT, cz) for x, y in pts_mm]
    n = len(verts)
    try:
        from System.Collections.Generic import List as _L
        loop = DB.CurveLoop()
        for i in range(n):
            loop.Append(DB.Line.CreateBound(verts[i], verts[(i+1) % n]))
        loops = _L[DB.CurveLoop]()
        loops.Add(loop)
        return DB.Floor.Create(doc, loops, cap_type_id, level_id)
    except Exception:
        arr = DB.CurveArray()
        for i in range(n):
            arr.Append(DB.Line.CreateBound(verts[i], verts[(i+1) % n]))
        return doc.Create.NewFloor(arr, cap_type, level, True)


def _group_pilecap_elements(doc, element_ids, group_name):
    """
    Group the cap slab + piles just created so the whole pilecap can be
    copy/pasted around the project as one unit, and rename the resulting
    GroupType to describe what kind of pilecap it is.
    Must be called inside the same transaction the elements were created in.
    Returns the Group, or None if grouping failed (never blocks the
    pilecap's own creation — grouping is a convenience, not a requirement).
    """
    ids = [eid for eid in element_ids if eid]
    if len(ids) < 2:
        return None
    try:
        from System.Collections.Generic import List as _L
        id_list = _L[DB.ElementId]()
        for eid in ids:
            id_list.Add(eid)
        group = doc.Create.NewGroup(id_list)
        try:
            group.GroupType.Name = group_name
        except Exception:
            pass
        return group
    except Exception:
        return None


def _create_pile(doc, cx, cy, cz, pile_type_id, level_id):
    level  = doc.GetElement(level_id)
    symbol = doc.GetElement(pile_type_id)
    if hasattr(symbol, 'IsActive') and not symbol.IsActive:
        symbol.Activate()
        doc.Regenerate()
    pt = DB.XYZ(cx, cy, cz)
    try:
        from Autodesk.Revit.DB.Structure import StructuralType
        return doc.Create.NewFamilyInstance(pt, symbol, level, StructuralType.Footing)
    except Exception:
        return doc.Create.NewFamilyInstance(pt, symbol, level,
                                            DB.Structure.StructuralType.Footing)


# ── Regular rectangular pile cap ──────────────────────────────────────────────

def create_pilecap(doc, config, center_pt):
    errors  = []
    created = 0
    n_h          = config['n_h']
    n_v          = config['n_v']
    spacing_mm   = config['spacing_mm']
    clearance_mm = config['clearance_mm']
    cutoff_mm    = config['cutoff_mm']
    cap_type_id  = config['cap_type_id']
    pile_type_id = config['pile_type_id']
    level_id     = config['level_id']

    width_mm, height_mm = calc_dimensions(n_h, n_v, spacing_mm, clearance_mm)
    cx, cy, cz = center_pt.X, center_pt.Y, center_pt.Z

    with DB.Transaction(doc, "NOSA — Create Pile Cap") as t:
        t.Start()
        new_ids = []
        try:
            slab = _create_cap_slab_rect(doc, cx, cy, cz, width_mm, height_mm,
                                         cap_type_id, level_id)
            new_ids.append(slab.Id)
            created += 1
        except Exception as e:
            errors.append("Cap slab: {}".format(e))

        pile_z = cz - cutoff_mm * _MM_TO_FT
        for row_idx in range(n_v):
            for col_idx in range(n_h):
                x_off = (col_idx * spacing_mm - (n_h - 1) * spacing_mm / 2.0) * _MM_TO_FT
                y_off = (row_idx * spacing_mm - (n_v - 1) * spacing_mm / 2.0) * _MM_TO_FT
                try:
                    pile = _create_pile(doc, cx + x_off, cy + y_off, pile_z,
                                        pile_type_id, level_id)
                    new_ids.append(pile.Id)
                    created += 1
                except Exception as e:
                    errors.append("Pile [{},{}]: {}".format(col_idx, row_idx, e))

        group_name = u"Pilecap {}x{} — {:.0f}x{:.0f}mm".format(n_h, n_v, width_mm, height_mm)
        _group_pilecap_elements(doc, new_ids, group_name)
        t.Commit()

    return created, errors


# ── Irregular shape definitions ───────────────────────────────────────────────
#
# Each shape has 4 named parameters (A, B, C, D).
# 'params': dict of key → (label, default_value) or None if unused (hidden).
#
# Pile positions are on an INTEGER grid: (col, row) ∈ ℤ², where
# pile centre = (col * spacing_mm, row * spacing_mm) relative to the centroid.
# Edge clearance is measured FROM PILE CENTRE to the cap boundary.

IRREGULAR_SHAPES = {
    'L': {
        'label': 'L-shape',
        'desc':  'Two arms at right angle — independent width per arm',
        'params': {
            'A': ('Arm A — length (piles)', 3),
            'B': ('Arm B — length (piles)', 3),
            'C': ('Arm A — width (lines)',  1),
            'D': ('Arm B — width (lines)',  1),
        },
    },
    'T': {
        'label': 'T-shape',
        'desc':  'Horizontal bar + central stem — independent width per arm',
        'params': {
            'A': ('Top bar — length (piles)', 5),
            'B': ('Stem — height (piles)',    3),
            'C': ('Top bar — depth (lines)',  1),
            'D': ('Stem — width (lines)',     1),
        },
    },
    'Plus': {
        'label': 'Plus / Cross',
        'desc':  'H-bar and V-bar crossing at centre — independent width',
        'params': {
            'A': ('H-bar — length (piles)', 5),
            'B': ('V-bar — length (piles)', 5),
            'C': ('H-bar — width (lines)',  1),
            'D': ('V-bar — width (lines)',  1),
        },
    },
    'Z': {
        'label': 'Z-shape',
        'desc':  'Two offset bars + diagonal connector',
        'params': {
            'A': ('Bar — length (piles)',    3),
            'B': ('Total height (piles)',    4),
            'C': ('Bar — width (lines)',     1),
            'D': None,
        },
    },
    'U': {
        'label': 'U-shape',
        'desc':  'Three sides of a rectangle — independent arm width',
        'params': {
            'A': ('Width (piles)',          4),
            'B': ('Depth (piles)',          3),
            'C': ('Side arms — width (lines)', 1),
            'D': ('Base — width (lines)',   1),
        },
    },
}


def get_irregular_cells(shape_key, a, b, c=1, d=1):
    """
    Return list of (col, row) INTEGER positions for the named shape.
    Pile centre = (col * spacing, row * spacing) — integers, 0-indexed.
    Params a, b = primary dimensions; c, d = arm widths (lines per arm).
    """
    a = max(2, int(a))
    b = max(2, int(b))
    c = max(1, int(c))
    d = max(1, int(d))

    cells = set()

    if shape_key == 'L':
        # Arm A: vertical, c lines wide × a piles tall (cols 0..c-1, rows 0..a-1)
        for col in range(c):
            for row in range(a):
                cells.add((col, row))
        # Arm B: horizontal, b piles wide × d lines tall (cols 0..b-1, rows 0..d-1)
        for col in range(b):
            for row in range(d):
                cells.add((col, row))

    elif shape_key == 'T':
        # Top bar: a piles wide × c lines deep (rows b-1 .. b+c-2)
        for col in range(a):
            for depth in range(c):
                cells.add((col, b - 1 + depth))
        # Stem: d lines wide, centred under bar, rows 0 .. b-2
        stem_left = (a - d) // 2
        for col in range(stem_left, stem_left + d):
            for row in range(b - 1):
                cells.add((col, row))

    elif shape_key == 'Plus':
        # H-bar: a piles wide × c lines tall, centred vertically
        h_mid = b // 2
        for col in range(a):
            for w in range(c):
                cells.add((col, h_mid - c // 2 + w))
        # V-bar: b piles tall × d lines wide, centred horizontally
        v_mid = a // 2
        for row in range(b):
            for w in range(d):
                cells.add((v_mid - d // 2 + w, row))

    elif shape_key == 'Z':
        # Bottom bar: cols 0..a-1, rows 0..c-1
        for col in range(a):
            for w in range(c):
                cells.add((col, w))
        # Vertical connector at col a-1 (right end of bottom bar), rows c..b-c-1
        # This keeps the shape fully connected — col a-1 is shared with both bars.
        for row in range(c, b - c):
            cells.add((a - 1, row))
        # Top bar: cols a-1..2a-2, rows b-c..b-1 (starts at same col as connector)
        for col in range(a - 1, 2 * a - 1):
            for w in range(c):
                cells.add((col, b - c + w))

    elif shape_key == 'U':
        # Base: cols 0..a-1, rows 0..d-1
        for col in range(a):
            for w in range(d):
                cells.add((col, w))
        # Left arm: cols 0..c-1, rows 0..b-1
        for col in range(c):
            for row in range(b):
                cells.add((col, row))
        # Right arm: cols a-c..a-1, rows 0..b-1
        for col in range(a - c, a):
            for row in range(b):
                cells.add((col, row))

    else:
        raise ValueError("Unknown shape: {}".format(shape_key))

    return sorted(cells)


# ── Cap polygon computation (corrected edge clearance) ────────────────────────
#
# KEY INVARIANT: pile centres are at INTEGER (col, row) positions.
# The cap boundary must be exactly `clearance_mm` from the nearest
# exposed pile centre — measured perpendicularly to each edge.
#
# Algorithm:
#   1. For each pile, its "half-unit cell" = [col-½, col+½] × [row-½, row+½].
#      In *doubled coordinates* (×2): cell = [2col-1, 2col+1] × [2row-1, 2row+1].
#   2. Build a directed-edge CCW boundary graph over the union of these cells.
#   3. Trace & de-collinear the polygon (vertices at odd doubled-coord pairs).
#   4. Convert vertex positions to mm: mm = (doubled_coord - 2*centroid) / 2 * spacing.
#      At this stage each vertex is exactly spacing/2 away from the nearest pile centre.
#   5. Shift each vertex by (clearance - spacing/2) in the outward-normal direction.
#      This moves the boundary FROM the half-spacing cell wall TO the clearance distance.
#      Result: every exposed cap edge is exactly `clearance_mm` from the pile centre. ✓

def _remove_collinear(poly):
    n = len(poly)
    if n < 4:
        return poly
    result = []
    for i in range(n):
        p  = poly[i]
        pp = poly[(i-1) % n]
        pn = poly[(i+1) % n]
        dx1, dy1 = p[0]-pp[0], p[1]-pp[1]
        dx2, dy2 = pn[0]-p[0], pn[1]-p[1]
        if dx1*dy2 - dy1*dx2 != 0:
            result.append(p)
    return result


def compute_cap_polygon(cells, spacing_mm, clearance_mm):
    """
    Return CCW polygon as list of (x_mm, y_mm) centred at centroid.
    Edge clearance is measured from pile centre to cap boundary edge.
    """
    cell_set = set(cells)

    # Build directed CCW boundary graph in doubled coords
    edges = {}
    for (col, row) in cells:
        BL = (2*col-1, 2*row-1)
        BR = (2*col+1, 2*row-1)
        TR = (2*col+1, 2*row+1)
        TL = (2*col-1, 2*row+1)
        if (col,   row-1) not in cell_set: edges[BL] = BR
        if (col+1, row  ) not in cell_set: edges[BR] = TR
        if (col,   row+1) not in cell_set: edges[TR] = TL
        if (col-1, row  ) not in cell_set: edges[TL] = BL

    if not edges:
        return []

    start = min(edges.keys())
    raw   = [start]
    curr  = edges[start]
    limit = len(edges) + 2
    while curr != start and limit > 0:
        raw.append(curr)
        curr = edges[curr]
        limit -= 1

    poly = _remove_collinear(raw)
    n    = len(poly)
    if n < 4:
        return []

    # Centroid of pile positions in doubled coords
    cx2 = 2.0 * sum(col for col, _ in cells) / float(len(cells))
    cy2 = 2.0 * sum(row for _, row in cells) / float(len(cells))

    # Effective clearance from cell wall (at spacing/2 from pile centre)
    # Moving from cell wall outward by (clearance - spacing/2) places the edge
    # at exactly clearance from the pile centre.
    eff = clearance_mm - spacing_mm / 2.0

    result = []
    for i in range(n):
        gx, gy   = poly[i]
        pgx, pgy = poly[(i-1) % n]
        ngx, ngy = poly[(i+1) % n]

        dx1, dy1 = gx-pgx, gy-pgy
        dx2, dy2 = ngx-gx, ngy-gy

        mag1 = (dx1*dx1 + dy1*dy1) ** 0.5
        mag2 = (dx2*dx2 + dy2*dy2) ** 0.5
        if mag1 == 0 or mag2 == 0:
            continue

        # Unit outward normals (CCW: outward = right of direction of travel)
        n1x, n1y = dy1/mag1, -dx1/mag1
        n2x, n2y = dy2/mag2, -dx2/mag2

        # At convex corners the normals add (both push outward).
        # At concave corners they partially cancel (cap edge moves inward into notch).
        ox = (n1x + n2x) * eff
        oy = (n1y + n2y) * eff

        x_mm = ((gx - cx2) / 2.0) * spacing_mm + ox
        y_mm = ((gy - cy2) / 2.0) * spacing_mm + oy
        result.append((x_mm, y_mm))

    return result


def pile_offsets_mm(cells, spacing_mm):
    """
    Return list of (dx_mm, dy_mm) from the group centroid for each pile.
    Pile centres are at INTEGER (col, row) positions.
    """
    cx = sum(col for col, _ in cells) / float(len(cells))
    cy = sum(row for _, row in cells) / float(len(cells))
    return [((col - cx) * spacing_mm, (row - cy) * spacing_mm)
            for col, row in cells]


# ── Cap polygon validation ────────────────────────────────────────────────────
# Belt-and-braces check before creating any geometry: every pile centre must
# sit inside the cap polygon and no closer than `clearance_mm` to any edge.
# If this fails the cap is NOT created — a wrong cap silently accepted is far
# worse than an explicit error.

def validate_cap_polygon(poly_mm, offsets_mm, clearance_mm, tol_mm=1.0):
    """
    Check every pile centre lies inside the cap polygon and no closer than
    clearance_mm - tol_mm to any boundary edge.
    Returns (ok, problems) — problems is a list of unicode messages.
    """
    if not poly_mm or len(poly_mm) < 3:
        return False, [u'Cap polygon could not be computed.']
    problems = []
    for k, (px, py) in enumerate(offsets_mm):
        if not point_in_polygon(px, py, poly_mm):
            problems.append(
                u'Pile {} at ({:.0f}, {:.0f}) mm falls outside the cap boundary.'
                .format(k + 1, px, py))
            continue
        min_d = distance_to_polygon_edge(px, py, poly_mm)
        if min_d < clearance_mm - tol_mm:
            problems.append(
                u'Pile {}: edge distance {:.0f} mm is below the {:.0f} mm clearance.'
                .format(k + 1, min_d, clearance_mm))
    return (not problems), problems


# ── Irregular pile cap creation ───────────────────────────────────────────────

def create_pilecap_irregular(doc, config, center_pt):
    """
    config keys: shape_key, param_a, param_b, param_c, param_d,
                 spacing_mm, clearance_mm, cutoff_mm,
                 cap_type_id, pile_type_id, level_id
    """
    shape_key    = config['shape_key']
    a            = config['param_a']
    b            = config['param_b']
    c            = config.get('param_c', 1)
    d            = config.get('param_d', 1)
    spacing_mm   = config['spacing_mm']
    clearance_mm = config['clearance_mm']
    cutoff_mm    = config['cutoff_mm']
    cap_type_id  = config['cap_type_id']
    pile_type_id = config['pile_type_id']
    level_id     = config['level_id']

    cells   = get_irregular_cells(shape_key, a, b, c, d)
    poly_mm = compute_cap_polygon(cells, spacing_mm, clearance_mm)
    offsets = pile_offsets_mm(cells, spacing_mm)

    ok, problems = validate_cap_polygon(poly_mm, offsets, clearance_mm)
    if not ok:
        return 0, [u'Cap geometry validation failed — nothing was created.'] + problems

    cx_ft, cy_ft, cz_ft = center_pt.X, center_pt.Y, center_pt.Z
    pile_z = cz_ft - cutoff_mm * _MM_TO_FT

    errors  = []
    created = 0

    with DB.Transaction(doc, u"NOSA — Create {} Pile Cap".format(shape_key)) as t:
        t.Start()
        new_ids = []
        try:
            slab = _create_cap_slab_polygon(doc, poly_mm, cx_ft, cy_ft, cz_ft,
                                            cap_type_id, level_id)
            new_ids.append(slab.Id)
            created += 1
        except Exception as e:
            errors.append(u"Cap slab: {}".format(e))

        for i, (dx, dy) in enumerate(offsets):
            try:
                pile = _create_pile(doc,
                                    cx_ft + dx * _MM_TO_FT,
                                    cy_ft + dy * _MM_TO_FT,
                                    pile_z, pile_type_id, level_id)
                new_ids.append(pile.Id)
                created += 1
            except Exception as e:
                errors.append(u"Pile {}: {}".format(i, e))

        shape_label = IRREGULAR_SHAPES.get(shape_key, {}).get('label', shape_key)
        group_name  = u"Pilecap {} — {}p".format(shape_label, len(offsets))
        _group_pilecap_elements(doc, new_ids, group_name)
        t.Commit()

    return created, errors
