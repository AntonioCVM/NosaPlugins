# -*- coding: utf-8 -*-
"""
nosa_utils.collectors
=====================
FilteredElementCollector wrappers.

All functions apply quick-filters (OfCategory / OfClass / WhereElementIsNotElementType)
BEFORE any Python-side filtering, following NOSA convention.
"""
from Autodesk.Revit import DB


def collect_by_category(doc, bic, is_type=False, view=None):
    """Elements of a BuiltInCategory — instances or types, optionally in a view."""
    if view is not None:
        col = DB.FilteredElementCollector(doc, view.Id)
    else:
        col = DB.FilteredElementCollector(doc)
    col = col.OfCategory(bic)
    if is_type:
        col = col.WhereElementIsElementType()
    else:
        col = col.WhereElementIsNotElementType()
    return list(col.ToElements())


def collect_by_class(doc, cls, view=None):
    """Elements of a specific .NET class."""
    if view is not None:
        col = DB.FilteredElementCollector(doc, view.Id)
    else:
        col = DB.FilteredElementCollector(doc)
    return list(col.OfClass(cls).ToElements())


def collect_sheets(doc):
    """All ViewSheet elements, sorted by SheetNumber."""
    sheets = list(
        DB.FilteredElementCollector(doc)
        .OfClass(DB.ViewSheet)
        .ToElements()
    )
    return sorted(sheets, key=lambda s: s.SheetNumber or u'')


def collect_views(doc, exclude_templates=True, exclude_types=None, include_types=None):
    """Views in collector order; drops templates, `exclude_types`, and anything not in `include_types`."""
    result = []
    for v in DB.FilteredElementCollector(doc).OfClass(DB.View).ToElements():
        try:
            if exclude_templates and v.IsTemplate:
                continue
            if exclude_types and v.ViewType in exclude_types:
                continue
            if include_types is not None and v.ViewType not in include_types:
                continue
            result.append(v)
        except Exception:
            pass
    return result


def collect_view_templates(doc):
    """View templates of any view type, in collector order."""
    result = []
    for v in DB.FilteredElementCollector(doc).OfClass(DB.View).ToElements():
        try:
            if v.IsTemplate:
                result.append(v)
        except Exception:
            pass
    return result


def template_id_of(view):
    """The view's ViewTemplateId, or None when no template is assigned."""
    tid = view.ViewTemplateId
    if tid is None or tid == DB.ElementId.InvalidElementId:
        return None
    return tid


def has_view_template(view):
    """True when the view has a view template assigned."""
    return template_id_of(view) is not None


def used_view_template_ids(doc):
    """Integer IDs of the templates assigned to at least one non-template view."""
    from nosa_utils.revit_helpers import get_id_value
    used = set()
    for v in collect_views(doc):
        try:
            tid = template_id_of(v)
            if tid is not None:
                used.add(get_id_value(tid))
        except Exception:
            pass
    return used


def apply_view_template(view, template_id):
    """Assign `template_id` to `view` (inside a transaction); False if the id is None/invalid."""
    if template_id is None or template_id == DB.ElementId.InvalidElementId:
        return False
    view.ViewTemplateId = template_id
    return True


def collect_levels(doc):
    """All Level elements, sorted by elevation."""
    levels = list(
        DB.FilteredElementCollector(doc)
        .OfClass(DB.Level)
        .ToElements()
    )
    return sorted(levels, key=lambda lv: lv.Elevation)


def collect_families(doc, category=None):
    """Family elements, optionally filtered by BuiltInCategory."""
    col = DB.FilteredElementCollector(doc).OfClass(DB.Family)
    families = list(col.ToElements())
    if category is not None:
        families = [f for f in families if f.FamilyCategoryId == DB.ElementId(category)]
    return families


def collect_family_symbols(doc, bic):
    """FamilySymbol elements of a BuiltInCategory."""
    return list(
        DB.FilteredElementCollector(doc)
        .OfClass(DB.FamilySymbol)
        .OfCategory(bic)
        .ToElements()
    )


def collect_worksets(doc):
    """User worksets (returns empty list if model is not workshared)."""
    try:
        if not doc.IsWorkshared:
            return []
        return list(
            DB.FilteredWorksetCollector(doc)
            .OfKind(DB.WorksetKind.UserWorkset)
            .ToWorksets()
        )
    except Exception:
        return []


def collect_rvt_links(doc):
    """RevitLinkType elements."""
    return list(
        DB.FilteredElementCollector(doc)
        .OfClass(DB.RevitLinkType)
        .ToElements()
    )


def collect_cad_imports(doc):
    """ImportInstance elements (CAD links and imports)."""
    return list(
        DB.FilteredElementCollector(doc)
        .OfClass(DB.ImportInstance)
        .ToElements()
    )


def placed_view_ids(doc, all_placed=False):
    """Integer IDs of views on any sheet — via viewports, or GetAllPlacedViews() when `all_placed`."""
    from nosa_utils.revit_helpers import get_id_value
    ids = set()
    for sheet in DB.FilteredElementCollector(doc).OfClass(DB.ViewSheet).ToElements():
        if all_placed:
            try:
                for vid in sheet.GetAllPlacedViews():
                    ids.add(get_id_value(vid))
            except Exception:
                pass
            continue
        for vp_id in sheet.GetAllViewports():
            try:
                vp = doc.GetElement(vp_id)
                if vp is not None:
                    ids.add(get_id_value(vp.ViewId))
            except Exception:
                pass
    return ids
