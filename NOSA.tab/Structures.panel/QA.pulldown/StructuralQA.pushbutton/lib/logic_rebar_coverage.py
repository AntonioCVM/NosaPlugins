# -*- coding: utf-8 -*-
"""
RebarCoverage Logic — Detect structural elements with no rebar assigned.
Groups results by category and level.
"""
from Autodesk.Revit import DB
from nosa_utils.revit_helpers import get_id_value
from nosa_utils.telemetry import log_swallowed
_LOG = u'StructuralQA/rebar_coverage'
_STRUCTURAL_BICS = None


def _structural_bics():
    global _STRUCTURAL_BICS
    if _STRUCTURAL_BICS is None:
        _STRUCTURAL_BICS = [
            ('Structural Columns',     DB.BuiltInCategory.OST_StructuralColumns),
            ('Structural Framing',     DB.BuiltInCategory.OST_StructuralFraming),
            ('Structural Foundations', DB.BuiltInCategory.OST_StructuralFoundation),
            ('Floors',                 DB.BuiltInCategory.OST_Floors),
            ('Walls',                  DB.BuiltInCategory.OST_Walls),
        ]
    return _STRUCTURAL_BICS




def _collect(doc, bic):
    return list(DB.FilteredElementCollector(doc)
                  .OfCategory(bic)
                  .WhereElementIsNotElementType()
                  .ToElements())


def _level_name(doc, el):
    try:
        lid = el.LevelId
        if lid and lid != DB.ElementId.InvalidElementId:
            lv = doc.GetElement(lid)
            if lv: return lv.Name
    except Exception:
        log_swallowed(_LOG, u'_level_name')
    try:
        p = el.get_Parameter(DB.BuiltInParameter.FAMILY_LEVEL_PARAM)
        if p:
            lv = doc.GetElement(p.AsElementId())
            if lv: return lv.Name
    except Exception:
        log_swallowed(_LOG, u'_level_name#2')
    return 'No Level'


def _build_rebar_host_index(doc):
    """
    One-time OST_Rebar scan building a set of host element ids — used only
    as a fallback when GetDependentElements fails for a given element,
    instead of re-running this same whole-category collector once per
    element checked (previously O(N_structural_elements) collector scans
    in the worst case where the primary path keeps failing).
    """
    host_ids = set()
    try:
        rebars = DB.FilteredElementCollector(doc)\
            .OfCategory(DB.BuiltInCategory.OST_Rebar)\
            .WhereElementIsNotElementType()\
            .ToElements()
        for r in rebars:
            try:
                if hasattr(r, 'GetHostId'):
                    host_ids.add(get_id_value(r.GetHostId()))
            except Exception:
                log_swallowed(_LOG, u'_build_rebar_host_index')
    except Exception:
        log_swallowed(_LOG, u'_build_rebar_host_index#2')
    return host_ids


def _has_rebar(doc, el, index_cache):
    """
    Return True if element has at least one rebar bar hosted to it.
    index_cache: a dict reused across calls within one check_rebar_coverage()
    run — the OST_Rebar fallback index is built at most once (lazily, on
    first need), on the fallback path only, instead of re-scanning the whole
    category once per element checked.
    """
    try:
        dep = el.GetDependentElements(
            DB.ElementCategoryFilter(DB.BuiltInCategory.OST_Rebar)
        )
        return len(list(dep)) > 0
    except Exception:
        log_swallowed(_LOG, u'_has_rebar')
    if 'index' not in index_cache:
        index_cache['index'] = _build_rebar_host_index(doc)
    return get_id_value(el.Id) in index_cache['index']


def check_rebar_coverage(doc, selected_cats=None):
    """
    Returns:
      elements_with_rebar:    list of {id, name, category, level}
      elements_without_rebar: list of {id, name, category, level}
    """
    with_rebar    = []
    without_rebar = []
    index_cache   = {}  # lazy OST_Rebar fallback index, built at most once

    for cat_name, bic in _structural_bics():
        if selected_cats and cat_name not in selected_cats:
            continue
        for el in _collect(doc, bic):
            try:
                level = _level_name(doc, el)
                entry = {
                    'id':       get_id_value(el.Id),
                    'name':     getattr(el, 'Name', str(el.Id)),
                    'category': cat_name,
                    'level':    level,
                }
                if _has_rebar(doc, el, index_cache):
                    with_rebar.append(entry)
                else:
                    without_rebar.append(entry)
            except Exception:
                log_swallowed(_LOG, u'check_rebar_coverage')

    total = len(with_rebar) + len(without_rebar)
    coverage_pct = round(len(with_rebar) / float(total) * 100, 1) if total else 0.0

    # Sort without_rebar by category + level
    without_rebar.sort(key=lambda x: (x['category'], x['level'], x['name']))

    # Summary by category
    from collections import defaultdict
    cat_summary = defaultdict(lambda: {'with': 0, 'without': 0})
    for r in with_rebar:    cat_summary[r['category']]['with']    += 1
    for r in without_rebar: cat_summary[r['category']]['without'] += 1
    summary = [
        {'category': c, 'with_rebar': v['with'], 'without_rebar': v['without'],
         'total': v['with'] + v['without'],
         'coverage': round(v['with'] / float(v['with'] + v['without']) * 100, 1) if (v['with'] + v['without']) else 0}
        for c, v in sorted(cat_summary.items())
    ]

    return {
        'with_rebar':    with_rebar,
        'without_rebar': without_rebar,
        'total':         total,
        'coverage_pct':  coverage_pct,
        'summary':       summary,
    }


def get_available_categories():
    return [n for n, _ in _structural_bics()]
