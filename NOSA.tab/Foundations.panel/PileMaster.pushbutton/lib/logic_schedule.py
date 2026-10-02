# -*- coding: utf-8 -*-
"""PileMaster — create or open a Revit schedule for pile elements."""
from Autodesk.Revit import DB
from nosa_utils.revit_helpers import get_id_value
from nosa_utils.telemetry import log_swallowed
_LOG = u'pilemaster'

_SCHEDULE_NAME = u'NOSA — Pile Schedule'
_FIELD_PARAMS = None


def _field_params():
    global _FIELD_PARAMS
    if _FIELD_PARAMS is None:
        _FIELD_PARAMS = [
            DB.BuiltInParameter.ALL_MODEL_MARK,
            DB.BuiltInParameter.ELEM_FAMILY_PARAM,
            DB.BuiltInParameter.ELEM_TYPE_PARAM,
            DB.BuiltInParameter.INSTANCE_LENGTH_PARAM,
        ]
    return _FIELD_PARAMS


def list_pile_schedules(doc):
    """Return (name, element_id_int) for schedules on structural foundations."""
    cat = doc.Settings.Categories.get_Item(DB.BuiltInCategory.OST_StructuralFoundation)
    results = []
    for vs in DB.FilteredElementCollector(doc).OfClass(DB.ViewSchedule):
        try:
            defn = vs.Definition
            if defn and defn.CategoryId == cat.Id:
                results.append((vs.Name or u'', get_id_value(vs.Id)))
        except Exception:
            log_swallowed(_LOG, u'list_pile_schedules')
    return sorted(results, key=lambda x: x[0].lower())


def create_or_open_schedule(doc, uidoc):
    """Find NOSA pile schedule or create one with standard fields."""
    existing = None
    for vs in DB.FilteredElementCollector(doc).OfClass(DB.ViewSchedule):
        try:
            if vs.Name == _SCHEDULE_NAME:
                existing = vs
                break
        except Exception:
            log_swallowed(_LOG, u'create_or_open_schedule')

    if existing is not None:
        try:
            uidoc.ActiveView = existing
        except Exception:
            log_swallowed(_LOG, u'create_or_open_schedule')
        return existing, False, u'Opened existing schedule.'

    cat = doc.Settings.Categories.get_Item(DB.BuiltInCategory.OST_StructuralFoundation)
    sched = DB.ViewSchedule.CreateSchedule(doc, cat.Id)
    sched.Name = _SCHEDULE_NAME
    defn = sched.Definition
    added = 0
    for bip in _field_params():
        try:
            defn.AddField(DB.ScheduleFieldType.Instance, bip)
            added += 1
        except Exception:
            log_swallowed(_LOG, u'create_or_open_schedule')
    try:
        uidoc.ActiveView = sched
    except Exception:
        log_swallowed(_LOG, u'create_or_open_schedule')
    msg = u'Created schedule with {} field(s).'.format(added)
    return sched, True, msg
