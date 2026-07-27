# -*- coding: utf-8 -*-
import os, sys

from Autodesk.Revit import DB

_lib = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', 'lib'))
if _lib not in sys.path:
    sys.path.insert(0, _lib)

from nosa_utils.revit_helpers import get_id_value

_FT_TO_M = 0.3048


def _type_name(el_type):
    try:
        p = el_type.get_Parameter(DB.BuiltInParameter.ALL_MODEL_TYPE_NAME)
        if p:
            n = p.AsString()
            if n:
                return n
    except Exception:
        pass
    try:
        return el_type.Name
    except Exception:
        return str(get_id_value(el_type.Id))


def _wall_level_name(doc, wall):
    try:
        p = wall.get_Parameter(DB.BuiltInParameter.WALL_BASE_CONSTRAINT)
        if p:
            lv = doc.GetElement(p.AsElementId())
            if lv:
                return lv.Name
    except Exception:
        pass
    try:
        lv = doc.GetElement(wall.LevelId)
        if lv:
            return lv.Name
    except Exception:
        pass
    return u'No Level'


def _is_structural(wall):
    try:
        if wall.StructuralUsage != DB.Structure.StructuralWallUsage.NonBearing:
            return True
    except Exception:
        pass
    try:
        p = wall.get_Parameter(DB.BuiltInParameter.WALL_STRUCTURAL_SIGNIFICANT)
        if p and p.AsInteger() == 1:
            return True
    except Exception:
        pass
    return False


def _is_basic(wall):
    try:
        return wall.WallType.Kind == DB.WallKind.Basic
    except Exception:
        return True


def walls_with_footing(doc):
    """Set of wall id ints that already host a WallFoundation."""
    ids = set()
    try:
        for wf in (DB.FilteredElementCollector(doc)
                     .OfClass(DB.WallFoundation)
                     .ToElements()):
            try:
                ids.add(get_id_value(wf.WallId))
            except Exception:
                pass
    except Exception:
        pass
    return ids


def collect_structural_walls(doc):
    """
    Return list of dicts for structural basic walls:
    {element, id, type_name, level, length_m, has_footing}
    """
    existing = walls_with_footing(doc)
    rows = []
    for wall in (DB.FilteredElementCollector(doc)
                   .OfCategory(DB.BuiltInCategory.OST_Walls)
                   .WhereElementIsNotElementType()
                   .ToElements()):
        try:
            if not isinstance(wall, DB.Wall):
                continue
            if not _is_basic(wall) or not _is_structural(wall):
                continue
            length_m = 0.0
            try:
                loc = wall.Location
                if isinstance(loc, DB.LocationCurve):
                    length_m = loc.Curve.Length * _FT_TO_M
            except Exception:
                pass
            wid = get_id_value(wall.Id)
            rows.append({
                'element':     wall,
                'id':          wid,
                'type_name':   wall.Name,
                'level':       _wall_level_name(doc, wall),
                'length_m':    length_m,
                'has_footing': wid in existing,
            })
        except Exception:
            pass
    rows.sort(key=lambda r: (r['level'], r['type_name']))
    return rows


def collect_footing_types(doc):
    """Return list of {id_obj, name} for all WallFoundationType in the project."""
    result = []
    try:
        for t in (DB.FilteredElementCollector(doc)
                    .OfClass(DB.WallFoundationType)
                    .ToElements()):
            result.append({'id_obj': t.Id, 'name': _type_name(t)})
    except Exception:
        pass
    result.sort(key=lambda r: r['name'].lower())
    return result


def create_footings(doc, walls, footing_type_id):
    """
    Create WallFoundation under each wall. Walls that already have a footing
    are skipped. Returns (created, skipped, failed, errors).
    """
    created = skipped = failed = 0
    errors = []
    existing = walls_with_footing(doc)

    t = DB.Transaction(doc, u'NOSA — Create Wall Footings')
    t.Start()
    try:
        for rec in walls:
            wall = rec['element']
            if rec['id'] in existing:
                skipped += 1
                continue
            try:
                DB.WallFoundation.Create(doc, footing_type_id, wall.Id)
                created += 1
            except Exception as ex:
                failed += 1
                errors.append(u'Wall {} ({}): {}'.format(
                    rec['id'], rec['type_name'], ex))
        t.Commit()
    except Exception as ex:
        try:
            t.RollBack()
        except Exception:
            pass
        errors.append(u'Transaction failed: {}'.format(ex))
        return 0, 0, len(walls), errors
    return created, skipped, failed, errors
