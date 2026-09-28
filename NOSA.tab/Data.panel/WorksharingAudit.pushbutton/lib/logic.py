# -*- coding: utf-8 -*-
"""
Worksharing Audit — Logic

Reads per-element worksharing metadata (creator, current owner, last changed
by, checkout status) via WorksharingUtils, and flags elements still sitting
on the model's original/default workset. Read-only — never touches
ownership or worksets.
"""
import os, sys

from Autodesk.Revit import DB

_lib = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', 'lib'))
if _lib not in sys.path:
    sys.path.insert(0, _lib)

from nosa_utils.revit_helpers import get_id_value

_CHECKOUT_LABELS = {
    u'OwnedByCurrentUser': u'Owned by me',
    u'OwnedByOtherUser':   u'Owned by other',
    u'NotOwned':           u'Not checked out',
}


def is_workshared(doc):
    try:
        return doc.IsWorkshared
    except Exception:
        return False


def get_user_worksets(doc):
    try:
        worksets = list(
            DB.FilteredWorksetCollector(doc)
            .OfKind(DB.WorksetKind.UserWorkset)
            .ToWorksets()
        )
        return sorted(worksets, key=lambda ws: get_id_value(ws.Id))
    except Exception:
        return []


def get_default_workset_id(doc):
    """The model's original/default user workset — the lowest-Id user
    workset, created automatically the first time a project is workshared.
    Elements left here (instead of a purpose-named workset) are usually a
    modelling hygiene issue worth flagging."""
    worksets = get_user_worksets(doc)
    return get_id_value(worksets[0].Id) if worksets else None


def _checkout_label(status):
    try:
        return _CHECKOUT_LABELS.get(str(status), str(status))
    except Exception:
        return u'—'


def _scan_scope(doc, active_view_only):
    collector = DB.FilteredElementCollector(doc, active_view_only.Id) if active_view_only \
        else DB.FilteredElementCollector(doc)
    return collector.WhereElementIsNotElementType().ToElements()


def audit(doc, active_view=None, scan_entire_model=False):
    """
    Returns:
        {
          'rows':      [{category, id, name, creator, owner, last_changed_by,
                         checkout, workset, on_default_workset}, ...],
          'checked_out': int,
          'on_default':  int,
          'scanned':     int,
          'error':       str or None,
        }
    """
    if not is_workshared(doc):
        return {'rows': [], 'checked_out': 0, 'on_default': 0, 'scanned': 0,
                'error': u'This model is not workshared — there is no '
                         u'ownership/editing history to audit.'}

    default_ws_id = get_default_workset_id(doc)
    view_scope = None if scan_entire_model else active_view
    elements = _scan_scope(doc, view_scope)

    rows = []
    checked_out = 0
    on_default = 0

    for el in elements:
        try:
            ws_id = el.WorksetId
        except Exception:
            continue
        if ws_id is None or get_id_value(ws_id) < 0:
            continue

        try:
            cat_name = el.Category.Name if el.Category else u'—'
        except Exception:
            cat_name = u'—'

        try:
            name = el.Name
        except Exception:
            name = u'—'

        try:
            tooltip = DB.WorksharingUtils.GetWorksharingTooltipInfo(doc, el.Id)
            creator = tooltip.Creator or u''
            owner = tooltip.Owner or u''
            last_changed_by = tooltip.LastChangedBy or u''
        except Exception:
            creator = owner = last_changed_by = u''

        try:
            status = DB.WorksharingUtils.GetCheckoutStatus(doc, el.Id)
            checkout = _checkout_label(status)
            if str(status) != u'NotOwned':
                checked_out += 1
        except Exception:
            checkout = u'—'

        try:
            ws_name = doc.GetWorksetTable().GetWorkset(ws_id).Name
        except Exception:
            ws_name = u'—'

        is_default = default_ws_id is not None and get_id_value(ws_id) == default_ws_id
        if is_default:
            on_default += 1

        rows.append({
            'category': cat_name,
            'id': get_id_value(el.Id),
            'name': name,
            'creator': creator,
            'owner': owner,
            'last_changed_by': last_changed_by,
            'checkout': checkout,
            'workset': ws_name,
            'on_default_workset': is_default,
        })

    rows.sort(key=lambda r: (r['category'].lower(), r['id']))
    return {'rows': rows, 'checked_out': checked_out, 'on_default': on_default,
            'scanned': len(rows), 'error': None}
