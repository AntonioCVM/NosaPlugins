# -*- coding: utf-8 -*-
"""Structural Drawing Checker — pre-emission quality checks."""
import sys, os
from Autodesk.Revit import DB
_lib = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', '..', 'lib'))
if _lib not in sys.path:
    sys.path.insert(0, _lib)
from nosa_utils.telemetry import log_swallowed
from nosa_utils.collectors import has_view_template, placed_view_ids
from nosa_utils.revit_helpers import element_id_from_int
_LOG = u'StructuralQA/drawing_checker'

def _struct_cats():
    return [
        DB.BuiltInCategory.OST_StructuralColumns,
        DB.BuiltInCategory.OST_StructuralFraming,
        DB.BuiltInCategory.OST_StructuralFoundation,
        DB.BuiltInCategory.OST_Walls,
        DB.BuiltInCategory.OST_Floors,
    ]

def _scale_ranges():
    return {
        DB.ViewType.FloorPlan:       (50,  200),
        DB.ViewType.EngineeringPlan: (50,  200),
        DB.ViewType.Section:         (10,  100),
        DB.ViewType.Elevation:       (50,  200),
        DB.ViewType.Detail:          (5,   50),
    }


class CheckResult(object):
    def __init__(self, check_name, status, count, detail):
        self.check_name = check_name  # str
        self.status     = status      # 'green' | 'amber' | 'red'
        self.count      = count       # int — number of issues
        self.detail     = detail      # list of str — specific issues


def _collect_structural_elements(doc):
    els = []
    for cat in _struct_cats():
        try:
            col = (DB.FilteredElementCollector(doc)
                   .OfCategory(cat)
                   .WhereElementIsNotElementType()
                   .ToElements())
            els.extend(col)
        except Exception:
            log_swallowed(_LOG, u'_collect_structural_elements')
    return els


def check_elements_without_level(doc):
    """Structural elements with no level assigned."""
    issues = []
    for el in _collect_structural_elements(doc):
        try:
            lvl_id = el.LevelId
            if lvl_id is None or lvl_id == DB.ElementId.InvalidElementId:
                name = getattr(el, 'Name', None) or u'id:{}'.format(el.Id)
                issues.append(name)
        except Exception:
            log_swallowed(_LOG, u'check_elements_without_level')

    if not issues:
        return CheckResult('Elements without level', 'green', 0, [])
    status = 'red' if len(issues) > 5 else 'amber'
    return CheckResult('Elements without level', status, len(issues), issues[:20])


def check_viewport_scales(doc):
    """
    Viewports on sheets: flag if scale is outside expected range for the view type.
    Returns a list of (sheet_number, view_name, scale, status) tuples.
    """
    issues = []
    for sheet in DB.FilteredElementCollector(doc).OfClass(DB.ViewSheet):
        try:
            for vp_id in sheet.GetAllViewports():
                vp = doc.GetElement(vp_id)
                if not isinstance(vp, DB.Viewport):
                    continue
                view = doc.GetElement(vp.ViewId)
                if view is None or not hasattr(view, 'Scale'):
                    continue
                vtype = view.ViewType
                if vtype not in _scale_ranges():
                    continue
                scale = view.Scale
                lo, hi = _scale_ranges()[vtype]
                if scale < lo or scale > hi:
                    issues.append(u'Sheet {} — {} (1:{})'.format(
                        sheet.SheetNumber, view.Name, scale))
        except Exception:
            log_swallowed(_LOG, u'check_viewport_scales')

    if not issues:
        return CheckResult('Viewport scale consistency', 'green', 0, [])
    status = 'red' if len(issues) > 10 else 'amber'
    return CheckResult('Viewport scale consistency', status, len(issues), issues[:20])


def check_untagged_structural(doc, active_view=None):
    """
    Structural elements visible in the given view (or all sheets) that have
    no annotation tag of any kind.
    """
    view = active_view or doc.ActiveView
    if view is None:
        return CheckResult('Untagged structural elements', 'amber', 0,
                           ['No active view — open a plan view first'])

    # Collect all tags in the view
    tag_ids = set()
    try:
        tags = (DB.FilteredElementCollector(doc, view.Id)
                .OfClass(DB.IndependentTag)
                .ToElements())
        for t in tags:
            try:
                tag_ids.add(t.TaggedLocalElementId)
            except Exception:
                log_swallowed(_LOG, u'check_untagged_structural')
    except Exception:
        log_swallowed(_LOG, u'check_untagged_structural#2')

    issues = []
    for cat in _struct_cats():
        try:
            col = (DB.FilteredElementCollector(doc, view.Id)
                   .OfCategory(cat)
                   .WhereElementIsNotElementType()
                   .ToElements())
            for el in col:
                try:
                    if el.Id not in tag_ids:
                        name = getattr(el, 'Name', None) or u'id:{}'.format(el.Id)
                        issues.append(name)
                except Exception:
                    log_swallowed(_LOG, u'check_untagged_structural#3')
        except Exception:
            log_swallowed(_LOG, u'check_untagged_structural#4')

    if not issues:
        return CheckResult('Untagged structural elements', 'green', 0, [])
    status = 'red' if len(issues) > 20 else 'amber'
    return CheckResult('Untagged structural elements', status, len(issues), issues[:20])


def check_active_warnings(doc):
    """Revit warnings on structural categories."""
    issues = []
    try:
        warnings = doc.GetWarnings()
        struct_cat_ids = set()
        for cat in _struct_cats():
            try:
                c = doc.Settings.Categories.get_Item(cat)
                if c:
                    struct_cat_ids.add(c.Id)
            except Exception:
                log_swallowed(_LOG, u'check_active_warnings')

        for w in warnings:
            try:
                for eid in w.GetFailingElements():
                    el = doc.GetElement(eid)
                    if el is None or el.Category is None:
                        continue
                    if el.Category.Id in struct_cat_ids:
                        issues.append(w.GetDescriptionText()[:80])
                        break
            except Exception:
                log_swallowed(_LOG, u'check_active_warnings#2')
    except Exception:
        log_swallowed(_LOG, u'check_active_warnings#3')

    if not issues:
        return CheckResult('Active structural warnings', 'green', 0, [])
    status = 'red' if len(issues) > 5 else 'amber'
    return CheckResult('Active structural warnings', status, len(issues), issues[:20])


def check_views_without_template(doc):
    """Views placed on sheets that have no view template assigned."""
    issues = []
    try:
        for vid in placed_view_ids(doc):
            view = doc.GetElement(element_id_from_int(vid))
            if view is None:
                continue
            try:
                if not has_view_template(view):
                    issues.append(view.Name)
            except Exception:
                log_swallowed(_LOG, u'check_views_without_template#2')
    except Exception:
        log_swallowed(_LOG, u'check_views_without_template#3')

    if not issues:
        return CheckResult('Views without template', 'green', 0, [])
    status = 'amber'  # always amber — templates are best practice, not always mandatory
    return CheckResult('Views without template', status, len(issues), issues[:20])


# ── Template Guard checks (absorbed — lib lives in View Hub) ─────────

def _templateguard_logic():
    from nosa_utils.bootstrap import load_module
    views = os.path.abspath(os.path.join(
        os.path.dirname(__file__), '..', '..', '..', '..', '..', 'NOSA.tab', 'Documentation.panel', 'ViewHub.pushbutton'))
    for rel in (('lib', 'view_templates', 'logic_template_guard.py'),):
        path = os.path.join(views, *rel)
        if os.path.isfile(path):
            return load_module('drawingchecker_tg_logic', path)
    return None


def _templateguard_checks(doc):
    """Run Template Guard rule checks and adapt them to CheckResult rows."""
    tg = _templateguard_logic()
    if tg is None:
        return []
    try:
        rules = tg.load_rules()
    except Exception:
        return []
    labels = {
        'wrong_scale':        u'Non-standard scales (Template Guard rules)',
        'sheet_naming':       u'Sheet naming convention',
        'manual_overrides':   u'Manual graphic overrides on views',
        'crop_missing':       u'Views without crop region',
        'wrong_detail_level': u'Wrong detail level',
    }
    checkers = {
        'wrong_scale':        tg.check_wrong_scale,
        'sheet_naming':       tg.check_sheet_naming,
        'manual_overrides':   tg.check_viewport_overrides,
        'crop_missing':       tg.check_crop_region,
        'wrong_detail_level': tg.check_detail_level,
    }
    results = []
    for key in sorted(checkers.keys()):
        try:
            issues = checkers[key](doc, rules)
        except Exception:
            continue
        details = []
        for iss in issues[:50]:
            try:
                details.append(u' '.join(
                    x for x in (iss.get('view', ''), iss.get('sheet', ''),
                                iss.get('type', ''), iss.get('detail', '')) if x))
            except Exception:
                log_swallowed(_LOG, u'_templateguard_checks')
        status = 'green' if not issues else 'amber'
        results.append(CheckResult(labels[key], status, len(issues), details))
    return results


def run_all_checks(doc):
    """Run all checks (own + absorbed Template Guard) and return CheckResults."""
    results = [
        check_elements_without_level(doc),
        check_viewport_scales(doc),
        check_untagged_structural(doc),
        check_active_warnings(doc),
        check_views_without_template(doc),
    ]
    results.extend(_templateguard_checks(doc))
    return results



