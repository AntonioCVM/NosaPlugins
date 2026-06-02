# -*- coding: utf-8 -*-
"""Create Pile Cap Logic — calculate dimensions, collect types, create assembly."""
import sys, os
from pyrevit import DB

_lib = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', '..', 'lib'))
if _lib not in sys.path:
    sys.path.insert(0, _lib)

_MM_TO_FT = 1.0 / 304.8


def calc_dimensions(n_h, n_v, spacing_mm, clearance_mm):
    """Return (width_mm, height_mm) of the pile cap."""
    width  = (n_h - 1) * spacing_mm + 2 * clearance_mm
    height = (n_v - 1) * spacing_mm + 2 * clearance_mm
    return float(width), float(height)


_EXCLUDE_FOUNDATION_KEYS = (
    'foundation slab', 'foundation_slab',
    'raft', 'pile cap', 'pilecap', 'pile cap slab',
    'strip footing', 'strap', 'combined footing',
    'wall footing', 'wall foundation',
    'isolated footing', 'spread footing', 'spread_footing',
    'bearing pad',
)

_PILE_INCLUDE_KEYS = (
    'pile', 'piling', 'pilote', 'micropile', 'percussion pile',
    'bored pile', 'steel pipe circular', 'pipe pile', 'tubular pile',
)


def _type_label(ft):
    fam_name = ft.Family.Name if (hasattr(ft, 'Family') and ft.Family) else u''
    sym_param = ft.get_Parameter(DB.BuiltInParameter.SYMBOL_NAME_PARAM)
    type_name = sym_param.AsString() if sym_param else u''
    return fam_name, type_name


def _is_pile_candidate_foundation(fam_name, type_name):
    """True for pile / piling foundation types — excludes slabs, straps, pads…"""
    blob = u'{} {}'.format((fam_name or u'').lower(), (type_name or u'').lower())
    if any(k in blob for k in _EXCLUDE_FOUNDATION_KEYS):
        return False
    return any(k in blob for k in _PILE_INCLUDE_KEYS)


def get_pile_types(doc):
    """Structural foundation types usable as piles (checks family + type name)."""
    result = []
    for t in (DB.FilteredElementCollector(doc)
              .OfCategory(DB.BuiltInCategory.OST_StructuralFoundation)
              .WhereElementIsElementType()
              .ToElements()):
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
    """Floor types for the cap slab — prefers 'Foundation Slab' naming (Floors category)."""
    result = []
    for t in DB.FilteredElementCollector(doc).OfClass(DB.FloorType).ToElements():
        try:
            fam_name, type_name = _type_label(t)
            blob = u'{} {}'.format((fam_name or u'').lower(), (type_name or u'').lower())
            ok = False
            if 'foundation slab' in blob:
                ok = True
            elif 'foundation_slab' in blob:
                ok = True
            elif 'foundation' in blob and 'slab' in blob:
                ok = True
            if not ok:
                continue
            label = u'{} : {}'.format(fam_name, type_name) if fam_name else type_name
            result.append((t.Id, label or u'(unnamed)'))
        except Exception:
            pass
    result.sort(key=lambda x: x[1])

    # Last resort: any Floor type that looks structural / bearing (narrower than "all floors").
    if not result:
        for t in DB.FilteredElementCollector(doc).OfClass(DB.FloorType).ToElements():
            try:
                fam_name, type_name = _type_label(t)
                blob = u'{} {}'.format((fam_name or u'').lower(), (type_name or u'').lower())
                if not any(k in blob for k in ('structural', 'foundation', 'footing')):
                    continue
                label = u'{} : {}'.format(fam_name, type_name) if fam_name else type_name
                result.append((t.Id, label or u'(unnamed)'))
            except Exception:
                pass
        result.sort(key=lambda x: x[1])
    return result


def get_all_levels(doc):
    """Return [(ElementId, name)] sorted by elevation (lowest first)."""
    levels = []
    for l in DB.FilteredElementCollector(doc).OfClass(DB.Level).ToElements():
        try:
            levels.append((l.Id, l.Name, l.Elevation))
        except Exception:
            pass
    levels.sort(key=lambda x: x[2])
    return [(lid, name) for lid, name, _ in levels]


def _build_cap_profile(cx, cy, cz, width_mm, height_mm):
    """Return (DB.CurveArray, four corner DB.XYZ) for the cap rectangle."""
    half_w = width_mm  * _MM_TO_FT / 2.0
    half_h = height_mm * _MM_TO_FT / 2.0
    p1 = DB.XYZ(cx - half_w, cy - half_h, cz)
    p2 = DB.XYZ(cx + half_w, cy - half_h, cz)
    p3 = DB.XYZ(cx + half_w, cy + half_h, cz)
    p4 = DB.XYZ(cx - half_w, cy + half_h, cz)
    arr = DB.CurveArray()
    arr.Append(DB.Line.CreateBound(p1, p2))
    arr.Append(DB.Line.CreateBound(p2, p3))
    arr.Append(DB.Line.CreateBound(p3, p4))
    arr.Append(DB.Line.CreateBound(p4, p1))
    return arr, (p1, p2, p3, p4)


def _build_cap_curve_loop(cx, cy, cz, width_mm, height_mm):
    """Return a DB.CurveLoop for use with Revit 2022+ Floor.Create."""
    half_w = width_mm  * _MM_TO_FT / 2.0
    half_h = height_mm * _MM_TO_FT / 2.0
    p1 = DB.XYZ(cx - half_w, cy - half_h, cz)
    p2 = DB.XYZ(cx + half_w, cy - half_h, cz)
    p3 = DB.XYZ(cx + half_w, cy + half_h, cz)
    p4 = DB.XYZ(cx - half_w, cy + half_h, cz)
    loop = DB.CurveLoop()
    loop.Append(DB.Line.CreateBound(p1, p2))
    loop.Append(DB.Line.CreateBound(p2, p3))
    loop.Append(DB.Line.CreateBound(p3, p4))
    loop.Append(DB.Line.CreateBound(p4, p1))
    return loop


def _create_cap_slab(doc, cx, cy, cz, width_mm, height_mm, cap_type_id, level_id):
    """Create the pile cap slab. Tries new API first, falls back to legacy."""
    level    = doc.GetElement(level_id)
    cap_type = doc.GetElement(cap_type_id)

    # Try Revit 2022+ API: Floor.Create(doc, IList[CurveLoop], FloorTypeId, LevelId)
    try:
        from System.Collections.Generic import List as _SCGList
        loop  = _build_cap_curve_loop(cx, cy, cz, width_mm, height_mm)
        loops = _SCGList[DB.CurveLoop]()
        loops.Add(loop)
        return DB.Floor.Create(doc, loops, cap_type_id, level_id)
    except Exception:
        pass

    # Fallback: legacy NewFloor API
    arr, _ = _build_cap_profile(cx, cy, cz, width_mm, height_mm)
    return doc.Create.NewFloor(arr, cap_type, level, True)


def _create_pile(doc, cx, cy, cz, pile_type_id, level_id):
    """Place one pile (as a structural foundation) at (cx, cy, cz)."""
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


def create_pilecap(doc, config, center_pt):
    """
    Create pile cap assembly at center_pt.

    config keys:
        n_h (int), n_v (int)             — pile grid
        spacing_mm (float)               — centre-to-centre pile spacing
        clearance_mm (float)             — edge clearance (cap edge to pile centre)
        cutoff_mm (float)                — pile cutoff below top of cap
        cap_type_id (DB.ElementId)
        pile_type_id (DB.ElementId)
        level_id (DB.ElementId)

    Returns (created_count, error_list).
    """
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

    cx = center_pt.X
    cy = center_pt.Y
    cz = center_pt.Z

    with DB.Transaction(doc, "NOSA — Create Pile Cap") as t:
        t.Start()
        try:
            # Cap slab at the placement elevation
            _create_cap_slab(doc, cx, cy, cz, width_mm, height_mm, cap_type_id, level_id)
            created += 1
        except Exception as e:
            errors.append("Cap slab: {}".format(e))

        # Piles — below cap top by cutoff_mm
        pile_z = cz - cutoff_mm * _MM_TO_FT
        for row_idx in range(n_v):
            for col_idx in range(n_h):
                x_off = (col_idx * spacing_mm - (n_h - 1) * spacing_mm / 2.0) * _MM_TO_FT
                y_off = (row_idx * spacing_mm - (n_v - 1) * spacing_mm / 2.0) * _MM_TO_FT
                try:
                    _create_pile(doc, cx + x_off, cy + y_off, pile_z,
                                 pile_type_id, level_id)
                    created += 1
                except Exception as e:
                    errors.append("Pile [{},{}]: {}".format(col_idx, row_idx, e))
        t.Commit()

    return created, errors
