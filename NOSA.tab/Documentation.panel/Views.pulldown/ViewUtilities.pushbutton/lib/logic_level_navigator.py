# -*- coding: utf-8 -*-
# Ported unchanged from LevelNavigator.pushbutton/lib/logic.py as part of the
# ViewUtilities hub consolidation. Business logic is untouched — only the
# filename changed (to avoid a sys.modules collision with any other
# same-named 'logic.py' loaded elsewhere in the Revit session).
import os, sys
from Autodesk.Revit import DB

_lib = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', '..', 'lib'))
if _lib not in sys.path:
    sys.path.insert(0, _lib)
from nosa_utils.revit_helpers import get_id_value, element_id_from_int
from nosa_utils import unit_conversion as _uc10

_FT_TO_M = _uc10.FT_TO_M


def get_levels_with_views(doc):
    """Return list of dicts sorted by elevation ascending."""
    levels = sorted(
        DB.FilteredElementCollector(doc).OfClass(DB.Level).ToElements(),
        key=lambda lv: lv.Elevation
    )

    # Collect all non-template floor-plan views, keyed by GenLevel id
    all_views = DB.FilteredElementCollector(doc).OfClass(DB.ViewPlan).ToElements()
    level_views = {}  # level_id_int → best ViewPlan
    for v in all_views:
        if v.IsTemplate:
            continue
        gen = v.GenLevel
        if gen is None:
            continue
        lid = get_id_value(gen.Id)
        existing = level_views.get(lid)
        if existing is None:
            level_views[lid] = v
        else:
            # Prefer structural discipline over architectural
            try:
                if v.Discipline == DB.ViewDiscipline.Structural:
                    level_views[lid] = v
            except Exception:
                pass

    result = []
    for lv in levels:
        lid = get_id_value(lv.Id)
        view = level_views.get(lid)
        result.append({
            'id':          lid,
            'name':        lv.Name,
            'elevation_m': round(lv.Elevation * _FT_TO_M, 3),
            'view_id':     get_id_value(view.Id) if view else None,
            'view_name':   view.Name if view else None,
            'view_disc':   _discipline_label(view) if view else u'',
        })
    return result


def activate_view(uidoc, view_id):
    doc = uidoc.Document
    v = doc.GetElement(element_id_from_int(view_id))
    if v is not None:
        uidoc.ActiveView = v


def _discipline_label(view):
    try:
        d = view.Discipline
        if d == DB.ViewDiscipline.Structural:
            return u'Structural'
        if d == DB.ViewDiscipline.Architectural:
            return u'Architectural'
        if d == DB.ViewDiscipline.Mechanical:
            return u'Mechanical'
        if d == DB.ViewDiscipline.Electrical:
            return u'Electrical'
        return u'Coordination'
    except Exception:
        return u''
