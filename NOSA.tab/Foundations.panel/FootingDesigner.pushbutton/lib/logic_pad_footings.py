# -*- coding: utf-8 -*-
import os, sys

from Autodesk.Revit import DB
from nosa_utils.telemetry import log_swallowed
_LOG = u'footingdesigner'

_lib = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', 'lib'))
if _lib not in sys.path:
    sys.path.insert(0, _lib)

from nosa_utils.revit_helpers import get_id_value, element_name
from nosa_utils import unit_conversion as _uc10
from nosa_utils import transactions as nosa_tx  # T8.1: no Revit failure dialogs

_MM_TO_FT = _uc10.MM_TO_FT
_FOOTING_XY_TOL_FT = 300.0 * _MM_TO_FT   # footing within 300 mm of column base = existing


def _symbol_label(sym):
    try:
        fam = sym.Family.Name
    except Exception:
        fam = u'?'
    try:
        p = sym.get_Parameter(DB.BuiltInParameter.ALL_MODEL_TYPE_NAME)
        tname = p.AsString() if p else None
        if not tname:
            tname = element_name(sym) or str(get_id_value(sym.Id))
    except Exception:
        tname = str(get_id_value(sym.Id))
    return u'{} : {}'.format(fam, tname)


def _column_base_point(col):
    try:
        loc = col.Location
        if isinstance(loc, DB.LocationPoint):
            return loc.Point
    except Exception:
        log_swallowed(_LOG, u'_column_base_point')
    try:
        bb = col.get_BoundingBox(None)
        if bb:
            return DB.XYZ((bb.Min.X + bb.Max.X) / 2.0,
                          (bb.Min.Y + bb.Max.Y) / 2.0,
                          bb.Min.Z)
    except Exception:
        log_swallowed(_LOG, u'_column_base_point')
    return None


def _column_base_level_id(doc, col):
    for bip in (DB.BuiltInParameter.FAMILY_BASE_LEVEL_PARAM,
                DB.BuiltInParameter.SCHEDULE_BASE_LEVEL_PARAM):
        try:
            p = col.get_Parameter(bip)
            if p:
                lid = p.AsElementId()
                if lid and lid != DB.ElementId.InvalidElementId:
                    return lid
        except Exception:
            log_swallowed(_LOG, u'_column_base_level_id')
    try:
        if col.LevelId and col.LevelId != DB.ElementId.InvalidElementId:
            return col.LevelId
    except Exception:
        log_swallowed(_LOG, u'_column_base_level_id')
    return None


def _existing_footing_points(doc):
    pts = []
    try:
        for f in (DB.FilteredElementCollector(doc)
                    .OfCategory(DB.BuiltInCategory.OST_StructuralFoundation)
                    .WhereElementIsNotElementType()
                    .ToElements()):
            try:
                loc = f.Location
                if isinstance(loc, DB.LocationPoint):
                    pts.append(loc.Point)
            except Exception:
                log_swallowed(_LOG, u'_existing_footing_points')
    except Exception:
        log_swallowed(_LOG, u'_existing_footing_points')
    return pts


def _has_footing_near(pt, footing_pts):
    for fp in footing_pts:
        dx = pt.X - fp.X
        dy = pt.Y - fp.Y
        if (dx * dx + dy * dy) ** 0.5 <= _FOOTING_XY_TOL_FT:
            return True
    return False


def collect_structural_columns(doc):
    """
    Return list of dicts for structural columns with a point location:
    {element, id, type_name, level, level_id, point, has_footing}
    """
    footing_pts = _existing_footing_points(doc)
    rows = []
    for col in (DB.FilteredElementCollector(doc)
                  .OfCategory(DB.BuiltInCategory.OST_StructuralColumns)
                  .WhereElementIsNotElementType()
                  .ToElements()):
        try:
            pt = _column_base_point(col)
            if pt is None:
                continue
            lid = _column_base_level_id(doc, col)
            lname = u'No Level'
            if lid is not None:
                lv = doc.GetElement(lid)
                if lv:
                    lname = lv.Name
            rows.append({
                'element':     col,
                'id':          get_id_value(col.Id),
                'type_name':   getattr(col, 'Name', u'?'),
                'level':       lname,
                'level_id':    lid,
                'point':       pt,
                'has_footing': _has_footing_near(pt, footing_pts),
            })
        except Exception:
            log_swallowed(_LOG, u'collect_structural_columns')
    rows.sort(key=lambda r: (r['level'], r['type_name']))
    return rows


def collect_footing_symbols(doc):
    """Point-based structural foundation family symbols: [{symbol, name}]."""
    result = []
    try:
        for sym in (DB.FilteredElementCollector(doc)
                      .OfCategory(DB.BuiltInCategory.OST_StructuralFoundation)
                      .WhereElementIsElementType()
                      .ToElements()):
            try:
                if not isinstance(sym, DB.FamilySymbol):
                    continue
                fpt = sym.Family.FamilyPlacementType
                if fpt != DB.FamilyPlacementType.OneLevelBased:
                    continue
                result.append({'symbol': sym, 'name': _symbol_label(sym)})
            except Exception:
                log_swallowed(_LOG, u'collect_footing_symbols')
    except Exception:
        log_swallowed(_LOG, u'collect_footing_symbols')
    result.sort(key=lambda r: r['name'].lower())
    return result


def create_footings(doc, columns, symbol):
    """
    Place one pad footing per column at its base point/level.
    Columns already flagged with a nearby footing are skipped.
    Returns (created, skipped, failed, errors).
    """
    created = skipped = failed = 0
    errors = []

    t = nosa_tx.guard(DB.Transaction(doc, u'NOSA — Create Pad Footings'))
    t.Start()
    try:
        if not symbol.IsActive:
            symbol.Activate()
            doc.Regenerate()

        for rec in columns:
            if rec['has_footing']:
                skipped += 1
                continue
            if rec['level_id'] is None:
                failed += 1
                errors.append(u'Column {}: no base level.'.format(rec['id']))
                continue
            level = doc.GetElement(rec['level_id'])
            try:
                try:
                    from Autodesk.Revit.DB.Structure import StructuralType
                    doc.Create.NewFamilyInstance(
                        rec['point'], symbol, level, StructuralType.Footing)
                except ImportError:
                    doc.Create.NewFamilyInstance(
                        rec['point'], symbol, level,
                        DB.Structure.StructuralType.Footing)
                created += 1
            except Exception as ex:
                failed += 1
                errors.append(u'Column {} ({}): {}'.format(
                    rec['id'], rec['type_name'], ex))
        t.Commit()
    except Exception as ex:
        try:
            t.RollBack()
        except Exception:
            log_swallowed(_LOG, u'create_footings')
        errors.append(u'Transaction failed: {}'.format(ex))
        return 0, 0, len(columns), errors
    return created, skipped, failed, errors
