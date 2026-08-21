# -*- coding: utf-8 -*-
import os, sys

from Autodesk.Revit import DB

_lib = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', '..', 'lib'))
if _lib not in sys.path:
    sys.path.insert(0, _lib)

from nosa_utils.revit_helpers import get_id_value, element_id_from_int


def _link_status_label(status):
    s = str(status)
    if 'Loaded' in s:
        return u'Loaded'
    if 'Unloaded' in s:
        return u'Unloaded'
    if 'NotFound' in s or 'Missing' in s:
        return u'Missing'
    return s


def collect_rvt_links(doc):
    result = []
    link_types = list(
        DB.FilteredElementCollector(doc)
        .OfClass(DB.RevitLinkType)
        .ToElements()
    )
    for lt in link_types:
        try:
            ref = lt.GetExternalFileReference()
            path = DB.ModelPathUtils.ConvertModelPathToUserVisiblePath(ref.GetAbsolutePath()) \
                   if ref is not None else u''
        except Exception:
            path = u''
        try:
            load_state = lt.GetLinkedFileStatus()
            status = _link_status_label(load_state)
        except Exception:
            status = u'Unknown'

        result.append({
            'id':       get_id_value(lt.Id),
            'name':     lt.Name or os.path.basename(path),
            'path':     path,
            'status':   status,
            'kind':     u'RVT Link',
            'element':  lt,
        })
    return sorted(result, key=lambda r: r['name'].lower())


def collect_cad_imports(doc):
    result = []
    cad_links = list(
        DB.FilteredElementCollector(doc)
        .OfClass(DB.ImportInstance)
        .ToElements()
    )
    for ci in cad_links:
        try:
            is_linked = ci.IsLinked
            kind = u'CAD Link' if is_linked else u'CAD Import'
        except Exception:
            kind = u'CAD'
        try:
            name = ci.Category.Name if ci.Category else u'CAD'
        except Exception:
            name = u'CAD'
        try:
            ext_ref = ci.GetExternalFileReference()
            path = DB.ModelPathUtils.ConvertModelPathToUserVisiblePath(
                ext_ref.GetAbsolutePath()) if ext_ref is not None else u''
        except Exception:
            path = u''
        result.append({
            'id':      get_id_value(ci.Id),
            'name':    os.path.basename(path) or name,
            'path':    path,
            'status':  u'Loaded',
            'kind':    kind,
            'element': ci,
        })
    return sorted(result, key=lambda r: r['name'].lower())


def collect_all(doc):
    return collect_rvt_links(doc) + collect_cad_imports(doc)


def reload_link(doc, link_type_el):
    with DB.Transaction(doc, u'NOSA — Reload link') as t:
        t.Start()
        try:
            link_type_el.Load()
        except AttributeError:
            link_type_el.Reload()
        t.Commit()


def unload_link(doc, link_type_el):
    with DB.Transaction(doc, u'NOSA — Unload link') as t:
        t.Start()
        link_type_el.Unload(None)
        t.Commit()


def remove_link(doc, element_id_int):
    with DB.Transaction(doc, u'NOSA — Remove link') as t:
        t.Start()
        doc.Delete(element_id_from_int(element_id_int))
        t.Commit()
