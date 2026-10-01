# -*- coding: utf-8 -*-
"""ViewFilter Batch Logic — bulk-manage view filters across multiple views."""
import sys, os
from Autodesk.Revit import DB
_lib = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', '..', 'lib'))
if _lib not in sys.path:
    sys.path.insert(0, _lib)
from nosa_utils.collectors import collect_views


def _skip_view_types():
    return {
        DB.ViewType.Internal,
        DB.ViewType.Undefined,
        DB.ViewType.ProjectBrowser,
        DB.ViewType.SystemBrowser,
        DB.ViewType.DrawingSheet,
        DB.ViewType.Legend,
        DB.ViewType.Schedule,
    }


def get_all_project_filters(doc):
    """
    Returns list of dicts:
      { 'id': ElementId, 'name': str, 'categories': [str, ...] }
    sorted by name.
    """
    col = DB.FilteredElementCollector(doc)\
          .OfClass(DB.ParameterFilterElement)\
          .ToElements()
    result = []
    for f in col:
        cats = []
        try:
            for cid in f.GetCategories():
                cat = doc.GetElement(cid)
                if cat is None:
                    cat = DB.Category.GetCategory(doc, cid)
                if cat and cat.Name:
                    cats.append(cat.Name)
        except Exception:
            pass
        result.append({'id': f.Id, 'name': f.Name, 'categories': cats})
    return sorted(result, key=lambda x: x['name'].lower())


def get_applicable_views(doc):
    """
    Returns all non-template views where filters can be applied,
    sorted by (ViewType, Name).
    """
    views = []
    for v in collect_views(doc, exclude_types=_skip_view_types()):
        if not v.Name:
            continue
        views.append(v)
    return sorted(views, key=lambda v: (str(v.ViewType), v.Name))


def copy_filters_from_view(doc, source_view, target_views, include_overrides=True):
    """
    Copy all filters from source_view to each target view.
    If include_overrides, also copies the graphic override settings.

    Returns (copied_total, skipped_total, results):
      results = [{'view': View, 'copied': int, 'skipped': int}, ...]
    """
    try:
        source_filter_ids = list(source_view.GetFilters())
    except Exception:
        return 0, 0, []

    copied_total = skipped_total = 0
    results = []

    with DB.Transaction(doc, u"NOSA — ViewFilter Batch — Copy Filters") as t:
        t.Start()
        for view in target_views:
            copied = skipped = 0
            for fid in source_filter_ids:
                try:
                    if not view.IsFilterApplied(fid):
                        view.AddFilter(fid)
                    if include_overrides:
                        ov = source_view.GetFilterOverrides(fid)
                        view.SetFilterOverrides(fid, ov)
                    vis = source_view.GetFilterVisibility(fid)
                    view.SetFilterVisibility(fid, vis)
                    copied += 1
                except Exception:
                    skipped += 1
            copied_total  += copied
            skipped_total += skipped
            results.append({'view': view, 'copied': copied, 'skipped': skipped})
        t.Commit()

    return copied_total, skipped_total, results


def apply_filters_to_views(doc, filter_infos, target_views, source_view=None):
    """
    Add filters to target views.
    filter_infos: list of dicts from get_all_project_filters()
    source_view:  if given, copies graphic overrides from it; else uses default (empty) overrides.

    Returns (applied_total, skipped_total, results):
      results = [{'view': View, 'applied': int, 'skipped': int}, ...]
    """
    applied_total = skipped_total = 0
    results = []

    with DB.Transaction(doc, u"NOSA — ViewFilter Batch — Apply Filters") as t:
        t.Start()
        for view in target_views:
            applied = skipped = 0
            for fi in filter_infos:
                fid = fi['id']
                try:
                    if not view.IsFilterApplied(fid):
                        view.AddFilter(fid)
                    if source_view is not None:
                        try:
                            ov = source_view.GetFilterOverrides(fid)
                            view.SetFilterOverrides(fid, ov)
                            vis = source_view.GetFilterVisibility(fid)
                            view.SetFilterVisibility(fid, vis)
                        except Exception:
                            pass
                    applied += 1
                except Exception:
                    skipped += 1
            applied_total  += applied
            skipped_total  += skipped
            results.append({'view': view, 'applied': applied, 'skipped': skipped})
        t.Commit()

    return applied_total, skipped_total, results


def toggle_filters_in_views(doc, filter_infos, target_views, enable):
    """
    Set filter visibility on/off for the given filters in the target views.
    Only acts on filters already applied to the view.

    Returns (toggled_total, skipped_total).
    """
    toggled = skipped = 0
    with DB.Transaction(doc, u"NOSA — ViewFilter Batch — Toggle Filters") as t:
        t.Start()
        for view in target_views:
            for fi in filter_infos:
                fid = fi['id']
                try:
                    if view.IsFilterApplied(fid):
                        view.SetFilterVisibility(fid, enable)
                        toggled += 1
                    else:
                        skipped += 1
                except Exception:
                    skipped += 1
        t.Commit()
    return toggled, skipped


def remove_filters_from_views(doc, filter_infos, target_views):
    """
    Remove filters from target views.
    Returns (removed_total, skipped_total).
    """
    removed = skipped = 0
    with DB.Transaction(doc, u"NOSA — ViewFilter Batch — Remove Filters") as t:
        t.Start()
        for view in target_views:
            for fi in filter_infos:
                fid = fi['id']
                try:
                    if view.IsFilterApplied(fid):
                        view.RemoveFilter(fid)
                        removed += 1
                    else:
                        skipped += 1
                except Exception:
                    skipped += 1
        t.Commit()
    return removed, skipped
