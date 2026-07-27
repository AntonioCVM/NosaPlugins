# -*- coding: utf-8 -*-
import os, sys

from Autodesk.Revit import DB

_lib = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', '..', 'lib'))
if _lib not in sys.path:
    sys.path.insert(0, _lib)

from nosa_utils.revit_helpers import get_id_value, element_id_from_int

# ViewType enums accessed inside functions — safe (no Revit document context needed)
_VT = DB.ViewType


def _vtype_labels_map():
    return {
        _VT.FloorPlan:       u'Floor Plan',
        _VT.CeilingPlan:     u'Ceiling Plan',
        _VT.Elevation:       u'Elevation',
        _VT.Section:         u'Section',
        _VT.Detail:          u'Detail',
        _VT.ThreeD:          u'3D View',
        _VT.DraftingView:    u'Drafting',
        _VT.Schedule:        u'Schedule',
        _VT.EngineeringPlan: u'Engineering Plan',
        _VT.AreaPlan:        u'Area Plan',
        _VT.Legend:          u'Legend',
    }


def _excluded_types():
    try:
        return {_VT.Internal, _VT.Walkthrough, _VT.Rendering}
    except Exception:
        return set()


def collect_views(doc):
    labels = _vtype_labels_map()
    excluded = _excluded_types()

    all_views = list(
        DB.FilteredElementCollector(doc)
        .OfClass(DB.View)
        .ToElements()
    )
    placed_ids = set()
    for sheet in DB.FilteredElementCollector(doc).OfClass(DB.ViewSheet).ToElements():
        for vp_id in sheet.GetAllViewports():
            try:
                vp = doc.GetElement(vp_id)
                if vp is not None:
                    placed_ids.add(get_id_value(vp.ViewId))
            except Exception:
                pass

    result = []
    for v in all_views:
        try:
            if v.IsTemplate:
                continue
            vtype = v.ViewType
            if vtype in excluded:
                continue
            try:
                level_name = v.GenLevel.Name if v.GenLevel is not None else u''
            except Exception:
                level_name = u''
            vid = get_id_value(v.Id)
            result.append({
                'id':      vid,
                'name':    v.Name,
                'vtype':   labels.get(vtype, str(vtype)),
                'level':   level_name,
                'placed':  vid in placed_ids,
                'element': v,
            })
        except Exception:
            pass
    return sorted(result, key=lambda r: (r['vtype'], r['name'].lower()))


def view_type_labels():
    return sorted(set(_vtype_labels_map().values())) + [u'All types']


def rename_views(doc, pairs):
    renamed = 0
    failed = 0
    errors = []
    with DB.Transaction(doc, u'NOSA — Rename views') as t:
        t.Start()
        for el, new_name in pairs:
            try:
                el.Name = new_name
                renamed += 1
            except Exception as ex:
                failed += 1
                errors.append(u'{}: {}'.format(new_name, ex))
        t.Commit()
    return renamed, failed, errors


def delete_views(doc, element_id_ints):
    deleted = 0
    failed = 0
    with DB.Transaction(doc, u'NOSA — Delete views') as t:
        t.Start()
        for eid_int in element_id_ints:
            try:
                doc.Delete(element_id_from_int(eid_int))
                deleted += 1
            except Exception:
                failed += 1
        t.Commit()
    return deleted, failed


def preview_rename(names, mode, find, replace, prefix, suffix):
    results = []
    for name in names:
        if mode == 'find_replace':
            new_name = name.replace(find, replace) if find else name
        else:
            new_name = u'{}{}{}'.format(prefix, name, suffix)
        results.append((name, new_name))
    return results
