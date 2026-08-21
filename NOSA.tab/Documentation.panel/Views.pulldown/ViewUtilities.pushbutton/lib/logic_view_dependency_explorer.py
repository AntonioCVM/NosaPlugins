# -*- coding: utf-8 -*-
# Ported unchanged from ViewDependencyExplorer.pushbutton/lib/logic.py as part
# of the ViewUtilities hub consolidation. Business logic is untouched — only
# the filename changed (to avoid a sys.modules collision with any other
# same-named 'logic.py' loaded elsewhere in the Revit session).
import os
import sys

from Autodesk.Revit import DB

_lib = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', '..', 'lib'))
if _lib not in sys.path:
    sys.path.insert(0, _lib)

from nosa_utils.revit_helpers import get_id_value

_SKIP_TYPES = {
    DB.ViewType.DrawingSheet,
    DB.ViewType.Schedule,
    DB.ViewType.Legend,
    DB.ViewType.Walkthrough,
    DB.ViewType.Internal,
    DB.ViewType.Undefined,
}


def get_all_views(doc):
    result = []
    try:
        for v in DB.FilteredElementCollector(doc).OfClass(DB.View).ToElements():
            try:
                if v.IsTemplate:
                    continue
                if v.ViewType in _SKIP_TYPES:
                    continue
                result.append({
                    'id':   get_id_value(v.Id),
                    'name': v.Name or u'',
                    'type': str(v.ViewType).replace('ViewType.', ''),
                })
            except Exception:
                pass
    except Exception:
        pass
    return sorted(result, key=lambda x: (x['type'], x['name'].lower()))


def _param_str(el, name):
    try:
        p = el.LookupParameter(name)
        if p and p.HasValue:
            return (p.AsString() or p.AsValueString() or u'').strip()
    except Exception:
        pass
    return u''


def analyse_view(doc, view_id_int):
    """
    Returns dict:
      view_name, view_type, template, filters, sheets, revisions, dependent_views
    """
    result = {
        'view_name':       u'',
        'view_type':       u'',
        'template':        None,
        'filters':         [],
        'sheets':          [],
        'revisions':       [],
        'dependent_views': [],
    }
    try:
        eid  = DB.ElementId(int(view_id_int))
        view = doc.GetElement(eid)
        if view is None:
            return result
        result['view_name'] = view.Name or u''
        result['view_type'] = str(view.ViewType).replace('ViewType.', '')
    except Exception:
        return result

    # Template
    try:
        tid = view.ViewTemplateId
        if tid and tid != DB.ElementId.InvalidElementId:
            tmpl = doc.GetElement(tid)
            if tmpl:
                result['template'] = {
                    'id':   get_id_value(tid),
                    'name': tmpl.Name or u'',
                }
    except Exception:
        pass

    # Filters
    try:
        for fid in view.GetFilters():
            filt = doc.GetElement(fid)
            if filt is None:
                continue
            try:
                visible = view.GetFilterVisibility(fid)
            except Exception:
                visible = True
            result['filters'].append({
                'name':    filt.Name or u'',
                'visible': visible,
            })
    except Exception:
        pass

    # Sheets that contain this view
    sheets = []
    try:
        for vp in DB.FilteredElementCollector(doc).OfClass(DB.Viewport).ToElements():
            try:
                if get_id_value(vp.ViewId) == view_id_int:
                    sheet = doc.GetElement(vp.SheetId)
                    if sheet is not None:
                        sheets.append({
                            'id':     get_id_value(sheet.Id),
                            'number': sheet.SheetNumber or u'',
                            'name':   sheet.Name or u'',
                        })
            except Exception:
                pass
    except Exception:
        pass
    result['sheets'] = sorted(sheets, key=lambda x: x['number'])

    # Revisions from those sheets
    rev_seen = set()
    for sh in result['sheets']:
        try:
            sheet = doc.GetElement(DB.ElementId(int(sh['id'])))
            if sheet is None:
                continue
            for rid in sheet.GetAdditionalRevisionIds():
                try:
                    rev = doc.GetElement(rid)
                    if rev is None:
                        continue
                    key = get_id_value(rid)
                    if key in rev_seen:
                        continue
                    rev_seen.add(key)
                    seq  = _param_str(rev, u'Revision Sequence') or _param_str(rev, u'Sequence Number') or u''
                    date = _param_str(rev, u'Revision Date') or u''
                    desc = _param_str(rev, u'Revision Description') or u''
                    if not seq:
                        try:
                            seq = str(rev.SequenceNumber)
                        except Exception:
                            pass
                    result['revisions'].append({
                        'sequence':    seq,
                        'date':        date,
                        'description': desc,
                        'sheet':       sh['number'],
                    })
                except Exception:
                    pass
        except Exception:
            pass

    # Dependent views
    try:
        dep_ids = view.GetDependentViewIds()
        for did in dep_ids:
            dv = doc.GetElement(did)
            if dv is None:
                continue
            result['dependent_views'].append({
                'id':   get_id_value(did),
                'name': dv.Name or u'',
            })
    except Exception:
        pass

    return result
