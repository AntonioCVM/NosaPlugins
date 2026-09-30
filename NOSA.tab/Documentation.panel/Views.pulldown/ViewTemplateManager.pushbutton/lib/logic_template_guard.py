# -*- coding: utf-8 -*-
"""
TemplateGuard Logic — View & Sheet Compliance Checks
Checks views/sheets against configurable NOSA rules (rules.json).
"""
import os
import re
import json
from Autodesk.Revit import DB
from nosa_utils.revit_helpers import get_id_value
from nosa_utils.collectors import collect_views, has_view_template
_RULES_FILE = os.path.join(os.path.dirname(__file__), 'rules.json')

_DEFAULT_RULES = {
    "allowed_scales": [5, 10, 20, 50, 100, 200, 500, 1000],
    "sheet_number_pattern": r"^[A-Z]{1,3}[-_]?\d{2,5}$",
    "sheet_name_min_length": 4,
    "required_view_types_with_template": ["FloorPlan","CeilingPlan","Section","Elevation","Detail"],
    "allowed_detail_levels": {
        "FloorPlan": ["Medium","Fine"],
        "Section":   ["Medium","Fine"],
        "Elevation": ["Medium","Fine"],
        "Detail":    ["Fine"],
    },
    "require_crop_on_sheet_views": True,
    "flag_manual_overrides": True,
}

_SEVERITY_LABELS = {
    "no_template":        "High",
    "wrong_scale":        "Medium",
    "sheet_naming":       "Medium",
    "manual_overrides":   "Low",
    "crop_missing":       "Medium",
    "wrong_detail_level": "Low",
}

_RULE_LABELS = {
    "no_template":        "View without template",
    "wrong_scale":        "Non-standard scale",
    "sheet_naming":       "Sheet number/name convention",
    "manual_overrides":   "Manual graphic overrides",
    "crop_missing":       "Crop region not active",
    "wrong_detail_level": "Incorrect detail level",
}

# ─────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────

def load_rules():
    try:
        if os.path.exists(_RULES_FILE):
            with open(_RULES_FILE, 'r') as f:
                data = json.load(f)
                merged = _DEFAULT_RULES.copy()
                merged.update(data)
                return merged
    except Exception:
        pass
    return _DEFAULT_RULES.copy()




def _view_type_name(view):
    try:
        return str(view.ViewType).replace('ViewType.', '')
    except Exception:
        return 'Unknown'


def _collect_views(doc):
    return [
        v for v in collect_views(doc, exclude_types=(
            DB.ViewType.Schedule,
            DB.ViewType.DrawingSheet,
            DB.ViewType.Legend,
            DB.ViewType.Undefined,
        ))
        if hasattr(v, 'ViewType')
    ]


def _collect_sheets(doc):
    return list(
        DB.FilteredElementCollector(doc)
          .OfClass(DB.ViewSheet)
          .ToElements()
    )


def _get_scale(view):
    try:
        p = view.get_Parameter(DB.BuiltInParameter.VIEW_SCALE)
        if p: return p.AsInteger()
        return view.Scale
    except Exception:
        return None


def _detail_level_name(view):
    try:
        dl = view.DetailLevel
        return str(dl).split('.')[-1]  # 'Fine' / 'Medium' / 'Coarse'
    except Exception:
        return None


def _has_manual_overrides(view):
    """True if view has any graphic overrides applied (simplified check)."""
    try:
        cats = view.Document.Settings.Categories
        for cat in cats:
            try:
                ov = view.GetCategoryOverrides(cat.Id)
                if ov and not ov.IsEmpty():
                    return True
            except Exception:
                pass
        return False
    except Exception:
        return False


# ─────────────────────────────────────────────────
# Individual checks
# ─────────────────────────────────────────────────

def check_views_without_template(doc, rules):
    required_types = rules.get('required_view_types_with_template', [])
    issues = []
    for v in _collect_views(doc):
        vtype = _view_type_name(v)
        if vtype not in required_types:
            continue
        try:
            if not has_view_template(v):
                issues.append({
                    'id':    get_id_value(v.Id),
                    'sheet': _sheet_for_view(doc, v),
                    'view':  v.Name,
                    'type':  vtype,
                    'rule':  'no_template',
                    'detail': 'No template assigned',
                })
        except Exception:
            pass
    return issues


def check_wrong_scale(doc, rules):
    allowed = rules.get('allowed_scales', [])
    issues = []
    for v in _collect_views(doc):
        scale = _get_scale(v)
        if scale and allowed and scale not in allowed:
            issues.append({
                'id':    get_id_value(v.Id),
                'sheet': _sheet_for_view(doc, v),
                'view':  v.Name,
                'type':  _view_type_name(v),
                'rule':  'wrong_scale',
                'detail': 'Scale 1:{} not in allowed list'.format(scale),
            })
    return issues


def check_sheet_naming(doc, rules):
    pattern     = rules.get('sheet_number_pattern', '')
    min_len     = rules.get('sheet_name_min_length', 4)
    issues = []
    for s in _collect_sheets(doc):
        try:
            num  = s.SheetNumber or ''
            name = s.Name or ''
            detail_parts = []
            if pattern and not re.match(pattern, num):
                detail_parts.append("Number '{}' does not match pattern".format(num))
            if min_len and len(name.strip()) < min_len:
                detail_parts.append("Name too short ({} chars)".format(len(name.strip())))
            if detail_parts:
                issues.append({
                    'id':    get_id_value(s.Id),
                    'sheet': num,
                    'view':  name,
                    'type':  'DrawingSheet',
                    'rule':  'sheet_naming',
                    'detail': '; '.join(detail_parts),
                })
        except Exception:
            pass
    return issues


def check_viewport_overrides(doc, rules):
    if not rules.get('flag_manual_overrides', True):
        return []
    issues = []
    for v in _collect_views(doc):
        try:
            if _has_manual_overrides(v):
                issues.append({
                    'id':    get_id_value(v.Id),
                    'sheet': _sheet_for_view(doc, v),
                    'view':  v.Name,
                    'type':  _view_type_name(v),
                    'rule':  'manual_overrides',
                    'detail': 'View has manual graphic overrides',
                })
        except Exception:
            pass
    return issues


def check_crop_region(doc, rules):
    if not rules.get('require_crop_on_sheet_views', True):
        return []
    issues = []
    sheets = _collect_sheets(doc)
    sheet_view_ids = set()
    for s in sheets:
        for vid in s.GetAllViewports():
            try:
                vp = doc.GetElement(vid)
                sheet_view_ids.add(get_id_value(vp.ViewId))
            except Exception:
                pass
    for v in _collect_views(doc):
        if get_id_value(v.Id) not in sheet_view_ids:
            continue
        try:
            if not v.CropBoxActive:
                issues.append({
                    'id':    get_id_value(v.Id),
                    'sheet': _sheet_for_view(doc, v),
                    'view':  v.Name,
                    'type':  _view_type_name(v),
                    'rule':  'crop_missing',
                    'detail': 'View on sheet has no active crop region',
                })
        except Exception:
            pass
    return issues


def check_detail_level(doc, rules):
    allowed_map = rules.get('allowed_detail_levels', {})
    issues = []
    for v in _collect_views(doc):
        vtype = _view_type_name(v)
        allowed = allowed_map.get(vtype)
        if not allowed:
            continue
        dl = _detail_level_name(v)
        if dl and dl not in allowed:
            issues.append({
                'id':    get_id_value(v.Id),
                'sheet': _sheet_for_view(doc, v),
                'view':  v.Name,
                'type':  vtype,
                'rule':  'wrong_detail_level',
                'detail': 'Detail level {} not in {}'.format(dl, allowed),
            })
    return issues


def _sheet_for_view(doc, view):
    """Return sheet number if this view is placed on a sheet, else '—'."""
    try:
        param = view.get_Parameter(DB.BuiltInParameter.VIEW_ASSOCIATED_SHEET)
        if param:
            sheet = doc.GetElement(param.AsElementId())
            if sheet:
                return sheet.SheetNumber
    except Exception:
        pass
    return '—'


# ─────────────────────────────────────────────────
# Main entry
# ─────────────────────────────────────────────────

def run_all_checks(doc, active_checks=None):
    rules = load_rules()
    all_keys = {'no_template','wrong_scale','sheet_naming',
                'manual_overrides','crop_missing','wrong_detail_level'}
    active = active_checks or all_keys

    results = {}
    if 'no_template'     in active: results['no_template']     = check_views_without_template(doc, rules)
    if 'wrong_scale'     in active: results['wrong_scale']     = check_wrong_scale(doc, rules)
    if 'sheet_naming'    in active: results['sheet_naming']    = check_sheet_naming(doc, rules)
    if 'manual_overrides'in active: results['manual_overrides']= check_viewport_overrides(doc, rules)
    if 'crop_missing'    in active: results['crop_missing']    = check_crop_region(doc, rules)
    if 'wrong_detail_level'in active: results['wrong_detail_level']= check_detail_level(doc, rules)

    # Flatten into single list for table
    all_issues = []
    for key, issues in results.items():
        for issue in issues:
            all_issues.append({
                'key':      key,
                'label':    _RULE_LABELS.get(key, key),
                'severity': _SEVERITY_LABELS.get(key, 'Low'),
                'sheet':    issue.get('sheet', '—'),
                'view':     issue.get('view', ''),
                'type':     issue.get('type', ''),
                'detail':   issue.get('detail', ''),
                'id':       issue.get('id'),
            })

    # Sort: High first, then alphabetically
    _sev_order = {'High': 0, 'Medium': 1, 'Low': 2}
    all_issues.sort(key=lambda x: (_sev_order.get(x['severity'], 9), x['sheet']))

    counts = {k: len(v) for k, v in results.items()}
    return {
        'issues': all_issues,
        'counts': counts,
        'total':  len(all_issues),
        'rules':  rules,
    }
