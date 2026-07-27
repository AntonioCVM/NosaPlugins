# -*- coding: utf-8 -*-
"""View Batch Manager Logic — bulk rename views and apply view templates."""
import sys, os
from Autodesk.Revit import DB
_lib = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', '..', 'lib'))
if _lib not in sys.path:
    sys.path.insert(0, _lib)

_INCLUDE_VIEW_TYPES = None


def _get_include_view_types():
    """Lazy init — avoids module-level DB.ViewType access that fails in Revit 2026+."""
    global _INCLUDE_VIEW_TYPES
    if _INCLUDE_VIEW_TYPES is not None:
        return _INCLUDE_VIEW_TYPES
    names = ['FloorPlan', 'CeilingPlan', 'Elevation', 'Section', 'Detail',
             'ThreeD', 'DraftingView', 'EngineeringPlan', 'AreaPlan']
    result = set()
    for name in names:
        try:
            result.add(getattr(DB.ViewType, name))
        except AttributeError:
            pass
    _INCLUDE_VIEW_TYPES = frozenset(result)
    return _INCLUDE_VIEW_TYPES


def collect_views(doc, filter_text=''):
    """Return list of dicts for non-template, non-schedule views."""
    txt = (filter_text or '').strip().lower()
    result = []
    for v in DB.FilteredElementCollector(doc).OfClass(DB.View).ToElements():
        try:
            if v.IsTemplate:
                continue
            if v.ViewType not in _get_include_view_types():
                continue
            name = v.Name or ''
            if txt and txt not in name.lower():
                continue
            # Current view template name
            tmpl_id = v.ViewTemplateId
            tmpl_name = ''
            if tmpl_id and tmpl_id != DB.ElementId.InvalidElementId:
                tmpl_el = doc.GetElement(tmpl_id)
                if tmpl_el:
                    tmpl_name = tmpl_el.Name or ''
            result.append({
                'id':        v.Id,
                'view':      v,
                'name':      name,
                'type':      str(v.ViewType).split('.')[-1],
                'template':  tmpl_name,
            })
        except Exception:
            pass
    result.sort(key=lambda r: (r['type'], r['name']))
    return result


def get_view_templates(doc):
    """Return [(ElementId, name)] of all view templates, sorted by name."""
    templates = []
    for v in DB.FilteredElementCollector(doc).OfClass(DB.View).ToElements():
        try:
            if v.IsTemplate and v.ViewType in _get_include_view_types():
                templates.append((v.Id, v.Name or u'(unnamed)'))
        except Exception:
            pass
    templates.sort(key=lambda x: x[1])
    return templates


def compute_new_name(old_name, mode, params):
    """
    Compute the new name for one view without touching Revit.
    mode: 'find_replace' | 'prefix_suffix' | 'case'
    params keys by mode:
        find_replace  → find (str), replace (str), case_sensitive (bool)
        prefix_suffix → prefix (str), suffix (str)
        case          → case_mode ('title' | 'upper' | 'lower' | 'sentence')
    """
    if mode == 'find_replace':
        find    = params.get('find', '')
        replace = params.get('replace', '')
        if not find:
            return old_name
        if params.get('case_sensitive', False):
            return old_name.replace(find, replace)
        import re
        return re.sub(re.escape(find), replace, old_name, flags=re.IGNORECASE)

    if mode == 'prefix_suffix':
        prefix = params.get('prefix', '')
        suffix = params.get('suffix', '')
        return prefix + old_name + suffix

    if mode == 'case':
        cm = params.get('case_mode', 'title')
        if cm == 'upper':
            return old_name.upper()
        if cm == 'lower':
            return old_name.lower()
        if cm == 'sentence':
            return old_name[0].upper() + old_name[1:].lower() if old_name else old_name
        return old_name.title()  # title case

    return old_name


def rename_views(doc, renames):
    """
    renames: [(DB.ElementId, new_name), ...]
    Returns (ok, failed).
    """
    ok = failed = 0
    with DB.Transaction(doc, "NOSA — Rename Views") as t:
        t.Start()
        for eid, new_name in renames:
            try:
                v = doc.GetElement(eid)
                if v and new_name and new_name != v.Name:
                    v.Name = new_name
                    ok += 1
                else:
                    ok += 1  # already matches — count as success
            except Exception:
                failed += 1
        t.Commit()
    return ok, failed


def apply_view_template(doc, view_ids, template_id):
    """
    Apply template_id to all views in view_ids.
    Pass template_id = DB.ElementId.InvalidElementId to remove template.
    Returns (ok, failed).
    """
    ok = failed = 0
    with DB.Transaction(doc, "NOSA — Apply View Template") as t:
        t.Start()
        for eid in view_ids:
            try:
                v = doc.GetElement(eid)
                if v:
                    v.ViewTemplateId = template_id
                    ok += 1
            except Exception:
                failed += 1
        t.Commit()
    return ok, failed
