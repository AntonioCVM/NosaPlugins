# -*- coding: utf-8 -*-
"""
RebarCoverage Logic — Detect structural elements with no rebar assigned.
Groups results by category and level.
"""
from pyrevit import DB

_STRUCTURAL_BICS = [
    ('Structural Columns',    DB.BuiltInCategory.OST_StructuralColumns),
    ('Structural Framing',    DB.BuiltInCategory.OST_StructuralFraming),
    ('Structural Foundations',DB.BuiltInCategory.OST_StructuralFoundation),
    ('Floors',                DB.BuiltInCategory.OST_Floors),
    ('Walls',                 DB.BuiltInCategory.OST_Walls),
]


def _get_id(eid):
    if hasattr(eid, 'Value'):        return eid.Value
    if hasattr(eid, 'IntegerValue'): return eid.IntegerValue
    return int(str(eid))


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
        pass
    try:
        p = el.get_Parameter(DB.BuiltInParameter.FAMILY_LEVEL_PARAM)
        if p:
            lv = doc.GetElement(p.AsElementId())
            if lv: return lv.Name
    except Exception:
        pass
    return 'No Level'


def _has_rebar(doc, el):
    """Return True if element has at least one rebar bar hosted to it."""
    try:
        eid = el.Id
        # Use GetDependentElements to find rebar
        dep = el.GetDependentElements(
            DB.ElementCategoryFilter(DB.BuiltInCategory.OST_Rebar)
        )
        return len(list(dep)) > 0
    except Exception:
        pass
    # Fallback: FilteredElementCollector with host filter
    try:
        rebars = DB.FilteredElementCollector(doc)\
            .OfCategory(DB.BuiltInCategory.OST_Rebar)\
            .WhereElementIsNotElementType()\
            .ToElements()
        for r in rebars:
            try:
                if hasattr(r, 'GetHostId') and r.GetHostId() == el.Id:
                    return True
            except Exception:
                pass
    except Exception:
        pass
    return False


def check_rebar_coverage(doc, selected_cats=None):
    """
    Returns:
      elements_with_rebar:    list of {id, name, category, level}
      elements_without_rebar: list of {id, name, category, level}
    """
    with_rebar    = []
    without_rebar = []

    for cat_name, bic in _STRUCTURAL_BICS:
        if selected_cats and cat_name not in selected_cats:
            continue
        for el in _collect(doc, bic):
            try:
                level = _level_name(doc, el)
                entry = {
                    'id':       _get_id(el.Id),
                    'name':     getattr(el, 'Name', str(el.Id)),
                    'category': cat_name,
                    'level':    level,
                }
                if _has_rebar(doc, el):
                    with_rebar.append(entry)
                else:
                    without_rebar.append(entry)
            except Exception:
                pass

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
    return [n for n, _ in _STRUCTURAL_BICS]
