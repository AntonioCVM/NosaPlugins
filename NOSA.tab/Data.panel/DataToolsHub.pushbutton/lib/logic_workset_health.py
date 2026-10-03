# -*- coding: utf-8 -*-
import os, sys

from Autodesk.Revit import DB

_lib = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', 'lib'))
if _lib not in sys.path:
    sys.path.insert(0, _lib)

from nosa_utils.revit_helpers import get_id_value
from nosa_utils.telemetry import log_swallowed
_LOG = u'DataToolsHub'


def is_workshared(doc):
    try:
        return doc.IsWorkshared
    except Exception:
        return False


def collect_worksets(doc):
    try:
        return list(
            DB.FilteredWorksetCollector(doc)
            .OfKind(DB.WorksetKind.UserWorkset)
            .ToWorksets()
        )
    except Exception:
        return []


def get_workset_stats(doc):
    if not is_workshared(doc):
        return []

    worksets = collect_worksets(doc)
    if not worksets:
        return []

    counts = {get_id_value(ws.Id): 0 for ws in worksets}

    all_els = list(
        DB.FilteredElementCollector(doc)
        .WhereElementIsNotElementType()
        .ToElements()
    )
    for el in all_els:
        try:
            ws_id = el.WorksetId
            if ws_id is not None:
                key = get_id_value(ws_id)
                if key in counts:
                    counts[key] += 1
        except Exception:
            log_swallowed(_LOG, u'get_workset_stats')

    result = []
    for ws in worksets:
        key = get_id_value(ws.Id)
        result.append({
            'id':       key,
            'name':     ws.Name,
            'owner':    ws.Owner or u'',
            'editable': ws.IsEditable,
            'open':     ws.IsOpen,
            'visible':  ws.IsVisibleByDefault,
            'count':    counts.get(key, 0),
        })
    return sorted(result, key=lambda r: r['name'].lower())


def get_elements_on_worksets(doc, workset_id_ints):
    """
    Elements on any of the given worksets, in a single document-wide scan —
    used when the caller wants several source worksets at once, instead of
    calling get_elements_on_workset() once per workset (each of which scans
    the whole document independently for a single ElementWorksetFilter).
    """
    wanted = set(workset_id_ints)
    result = []
    all_els = DB.FilteredElementCollector(doc).WhereElementIsNotElementType().ToElements()
    for el in all_els:
        try:
            ws_id = el.WorksetId
            if ws_id is not None and get_id_value(ws_id) in wanted:
                result.append(el)
        except Exception:
            log_swallowed(_LOG, u'get_elements_on_worksets')
    return result


def move_elements_to_workset(doc, element_ids, target_workset_id):
    moved = 0
    failed = 0
    with DB.Transaction(doc, u'NOSA — Move to workset') as t:
        t.Start()
        for eid in element_ids:
            try:
                el = doc.GetElement(eid)
                if el is None:
                    continue
                p = el.get_Parameter(DB.BuiltInParameter.ELEM_PARTITION_PARAM)
                if p is not None and not p.IsReadOnly:
                    p.Set(target_workset_id)
                    moved += 1
                else:
                    failed += 1
            except Exception:
                failed += 1
        t.Commit()
    return moved, failed
