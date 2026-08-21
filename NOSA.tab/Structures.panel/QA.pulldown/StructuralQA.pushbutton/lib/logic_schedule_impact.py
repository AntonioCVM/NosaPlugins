# -*- coding: utf-8 -*-
import os
import sys

from Autodesk.Revit import DB

_lib = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', '..', 'lib'))
if _lib not in sys.path:
    sys.path.insert(0, _lib)

from nosa_utils.revit_helpers import get_id_value

def _schedulable_bics():
    return [
        DB.BuiltInCategory.OST_StructuralColumns,
        DB.BuiltInCategory.OST_StructuralFraming,
        DB.BuiltInCategory.OST_StructuralFoundation,
        DB.BuiltInCategory.OST_Floors,
        DB.BuiltInCategory.OST_Walls,
        DB.BuiltInCategory.OST_Doors,
        DB.BuiltInCategory.OST_Windows,
        DB.BuiltInCategory.OST_Rooms,
        DB.BuiltInCategory.OST_Furniture,
        DB.BuiltInCategory.OST_GenericModel,
        DB.BuiltInCategory.OST_Rebar,
    ]


def get_schedulable_categories(doc):
    """Return list of (display_name, DB.Category) for categories that have schedules."""
    result = []
    try:
        for bic in _schedulable_bics():
            try:
                cat = DB.Category.GetCategory(doc, bic)
                if cat:
                    result.append((cat.Name, cat))
            except Exception:
                pass
    except Exception:
        pass
    # Also add any extra categories found in existing schedules
    try:
        for vs in DB.FilteredElementCollector(doc).OfClass(DB.ViewSchedule).ToElements():
            try:
                cat = vs.Definition.GetCategoryId()
                if cat and get_id_value(cat) > 0:
                    c = doc.GetElement(cat)
                    if c and (c.Name, c) not in result:
                        result.append((c.Name, c))
            except Exception:
                pass
    except Exception:
        pass
    return sorted(set(result), key=lambda x: x[0])


def find_schedules_for_category(doc, category_id):
    """Return list of ViewSchedule that schedule the given category."""
    result = []
    try:
        for vs in DB.FilteredElementCollector(doc).OfClass(DB.ViewSchedule).ToElements():
            try:
                if get_id_value(vs.Definition.GetCategoryId()) == category_id:
                    result.append(vs)
            except Exception:
                pass
    except Exception:
        pass
    return result


def find_sheets_for_schedule(doc, schedule_id):
    """Return list of (sheet_number, sheet_name) for sheets containing this schedule."""
    sheets = []
    try:
        for sheet in DB.FilteredElementCollector(doc).OfClass(DB.ViewSheet).ToElements():
            try:
                placed_views = DB.SheetUtils.GetViewsOnSheet(sheet)
                for vid in placed_views:
                    if get_id_value(vid) == get_id_value(schedule_id):
                        sheets.append((sheet.SheetNumber, sheet.Name))
                        break
            except Exception:
                pass
    except Exception:
        pass
    return sheets


def analyse(doc, category_id):
    """
    Return list of impact records:
    {'schedule_name': ..., 'field_count': n, 'sheet_count': m, 'sheets': [(no, name), ...]}
    """
    schedules = find_schedules_for_category(doc, category_id)
    records = []
    for vs in schedules:
        try:
            field_count = vs.Definition.GetFieldCount()
        except Exception:
            field_count = 0
        sheets = find_sheets_for_schedule(doc, vs.Id)
        records.append({
            'schedule_name': vs.Name,
            'field_count':   field_count,
            'sheet_count':   len(sheets),
            'sheets':        sheets,
            'schedule_id':   get_id_value(vs.Id),
        })
    return sorted(records, key=lambda r: r['schedule_name'])
