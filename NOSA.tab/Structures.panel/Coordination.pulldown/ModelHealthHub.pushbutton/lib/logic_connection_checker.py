# -*- coding: utf-8 -*-
"""
ConnectionChecker Logic — verify End Join and Analytical connections
for structural beams and columns.
"""
from Autodesk.Revit import DB
from System.Collections.Generic import List
from nosa_utils.revit_helpers import get_id_value
from nosa_utils.telemetry import log_swallowed
_LOG = u'ModelHealthHub/connection_checker'


def _collect(doc, bic):
    return list(DB.FilteredElementCollector(doc).OfCategory(bic)
                  .WhereElementIsNotElementType().ToElements())

def _level_name(doc, el):
    try:
        lid = el.LevelId
        if lid and lid != DB.ElementId.InvalidElementId:
            lv = doc.GetElement(lid)
            if lv: return lv.Name
    except Exception: log_swallowed(_LOG, u'_level_name')
    return '—'

# ── Analytical model check ────────────────────────────────────────────────────

def check_analytical_disabled(doc):
    """Structural elements with analytical model disabled."""
    issues = []
    for bic, label in [
        (DB.BuiltInCategory.OST_StructuralColumns, 'Column'),
        (DB.BuiltInCategory.OST_StructuralFraming,  'Beam'),
    ]:
        for el in _collect(doc, bic):
            try:
                p = el.get_Parameter(DB.BuiltInParameter.STRUCTURAL_ANALYTICAL_MODEL)
                if p and p.AsInteger() == 0:
                    issues.append({'id': get_id_value(el.Id), 'name': el.Name,
                                   'category': label, 'level': _level_name(doc, el),
                                   'check': 'Analytical disabled', 'severity': 'High'})
            except Exception: log_swallowed(_LOG, u'check_analytical_disabled')
    return issues

# ── End join / structural usage ───────────────────────────────────────────────

def check_structural_usage(doc):
    """Beams with non-structural or undefined usage."""
    issues = []
    for el in _collect(doc, DB.BuiltInCategory.OST_StructuralFraming):
        try:
            p = el.get_Parameter(DB.BuiltInParameter.INSTANCE_STRUCT_USAGE_TEXT_PARAM)
            val = p.AsString() if p else None
            if not val or val.strip() == '':
                issues.append({'id': get_id_value(el.Id), 'name': el.Name,
                               'category': 'Beam', 'level': _level_name(doc, el),
                               'check': 'Structural usage empty', 'severity': 'Medium'})
        except Exception: log_swallowed(_LOG, u'check_structural_usage')
    return issues

# ── Column base / top attachment ──────────────────────────────────────────────

def check_column_attachment(doc):
    """Columns not attached to a base or top level."""
    issues = []
    for el in _collect(doc, DB.BuiltInCategory.OST_StructuralColumns):
        try:
            base_p = el.get_Parameter(DB.BuiltInParameter.COLUMN_BASE_ATTACHMENT_PARAM)
            top_p  = el.get_Parameter(DB.BuiltInParameter.COLUMN_TOP_ATTACHMENT_PARAM)
            # 0 = not attached (column is free)
            if base_p and base_p.AsInteger() == 0:
                issues.append({'id': get_id_value(el.Id), 'name': el.Name,
                               'category': 'Column', 'level': _level_name(doc, el),
                               'check': 'Column base not attached', 'severity': 'Medium'})
            if top_p and top_p.AsInteger() == 0:
                issues.append({'id': get_id_value(el.Id), 'name': el.Name,
                               'category': 'Column', 'level': _level_name(doc, el),
                               'check': 'Column top not attached', 'severity': 'Low'})
        except Exception: log_swallowed(_LOG, u'check_column_attachment')
    return issues

# ── Beam end join check ───────────────────────────────────────────────────────

def check_beam_joins(doc):
    """
    Beams where End 0 or End 1 has no join (checks via LocationCurve endpoints
    against nearby elements — simplified heuristic).
    """
    issues = []
    beams = _collect(doc, DB.BuiltInCategory.OST_StructuralFraming)

    # Restrict the per-endpoint spatial query to plausibly-adjacent
    # structural categories instead of the whole model — previously ran
    # unfiltered (every category) twice per beam, which also meant any
    # nearby annotation/tag/dimension would count as a false "join".
    adjacency_cats = List[DB.BuiltInCategory]([
        DB.BuiltInCategory.OST_StructuralColumns,
        DB.BuiltInCategory.OST_StructuralFraming,
        DB.BuiltInCategory.OST_StructuralFoundation,
    ])
    cat_filter = DB.ElementMulticategoryFilter(adjacency_cats)

    for el in beams:
        try:
            curve = el.Location.Curve
            for end_idx in range(2):
                pt = curve.GetEndPoint(end_idx)
                # Check if any column/beam/foundation is within 50mm of endpoint
                outline = DB.Outline(
                    DB.XYZ(pt.X - 0.17, pt.Y - 0.17, pt.Z - 0.5),
                    DB.XYZ(pt.X + 0.17, pt.Y + 0.17, pt.Z + 0.5)
                )
                bbf = DB.BoundingBoxIntersectsFilter(outline)
                nearby = list(
                    DB.FilteredElementCollector(doc)
                      .WherePasses(cat_filter)
                      .WherePasses(bbf)
                      .WhereElementIsNotElementType()
                      .ToElements()
                )
                nearby = [n for n in nearby if get_id_value(n.Id) != get_id_value(el.Id)]
                if not nearby:
                    issues.append({
                        'id': get_id_value(el.Id), 'name': el.Name,
                        'category': 'Beam', 'level': _level_name(doc, el),
                        'check': 'End {} — no adjacent element'.format(end_idx),
                        'severity': 'Medium'
                    })
        except Exception: log_swallowed(_LOG, u'check_beam_joins')
    return issues

# ── Custom rules engine ───────────────────────────────────────────────────────
import io, json, os

_RULES_DIR  = os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', '..', '..', 'NOSA_Configs')
_RULES_FILE = os.path.join(_RULES_DIR, 'connection_checker_rules.json')

_RULE_CATEGORIES = ['Structural Columns', 'Beams', 'Foundations', 'Any']

_CONDITION_OPS = ['is_empty', 'is_not_empty', 'equals', 'not_equals',
                  'contains', 'greater_than', 'less_than']


def load_custom_rules():
    """Return list of custom rule dicts."""
    try:
        if os.path.isfile(_RULES_FILE):
            with io.open(_RULES_FILE, encoding='utf-8') as f:
                return json.load(f)
    except Exception:
        log_swallowed(_LOG, u'load_custom_rules')
    return []


def save_custom_rules(rules):
    try:
        os.makedirs(_RULES_DIR, exist_ok=True)
    except TypeError:
        if not os.path.isdir(_RULES_DIR):
            os.makedirs(_RULES_DIR)
    with io.open(_RULES_FILE, 'w', encoding='utf-8') as f:
        json.dump(rules, f, indent=2, ensure_ascii=False)


def _bic_for_cat(cat_label):
    mapping = {
        'Structural Columns': DB.BuiltInCategory.OST_StructuralColumns,
        'Beams':              DB.BuiltInCategory.OST_StructuralFraming,
        'Foundations':        DB.BuiltInCategory.OST_StructuralFoundation,
    }
    return mapping.get(cat_label)


def run_custom_rules(doc, rules):
    """Evaluate each custom rule against the model and return issue list."""
    issues = []
    for rule in rules:
        param_name = rule.get('param', '').strip()
        op         = rule.get('condition', 'is_empty')
        threshold  = str(rule.get('threshold', '')).strip()
        severity   = rule.get('severity', 'Medium')
        cat_label  = rule.get('category', 'Any')
        label      = rule.get('label') or u'Rule: {} {} {}'.format(param_name, op, threshold)

        if not param_name:
            continue

        bic = _bic_for_cat(cat_label)
        if bic:
            all_els = _collect(doc, bic)
        else:
            all_els = []
            for b in [DB.BuiltInCategory.OST_StructuralColumns,
                      DB.BuiltInCategory.OST_StructuralFraming,
                      DB.BuiltInCategory.OST_StructuralFoundation]:
                all_els += _collect(doc, b)

        for el in all_els:
            try:
                p = el.LookupParameter(param_name)
                if p is None:
                    continue
                raw = ''
                if p.StorageType == DB.StorageType.String:
                    raw = p.AsString() or ''
                elif p.StorageType == DB.StorageType.Double:
                    raw = str(p.AsDouble())
                elif p.StorageType == DB.StorageType.Integer:
                    raw = str(p.AsInteger())
                elif p.StorageType == DB.StorageType.ElementId:
                    raw = str(get_id_value(p.AsElementId()))

                raw_l = raw.strip().lower()
                thr_l = threshold.strip().lower()
                fail  = False
                if op == 'is_empty':
                    fail = raw_l == ''
                elif op == 'is_not_empty':
                    fail = raw_l != ''
                elif op == 'equals':
                    fail = raw_l == thr_l
                elif op == 'not_equals':
                    fail = raw_l != thr_l
                elif op == 'contains':
                    fail = thr_l in raw_l
                elif op == 'greater_than':
                    try: fail = float(raw) > float(threshold)
                    except ValueError: pass  # nosa-lint: disable=NOSA006 - non-numeric value simply does not fail a numeric rule
                elif op == 'less_than':
                    try: fail = float(raw) < float(threshold)
                    except ValueError: pass  # nosa-lint: disable=NOSA006 - non-numeric value simply does not fail a numeric rule

                if fail:
                    issues.append({
                        'id':       get_id_value(el.Id),
                        'name':     el.Name,
                        'category': el.Category.Name if el.Category else cat_label,
                        'level':    _level_name(doc, el),
                        'check':    label,
                        'severity': severity,
                    })
            except Exception:
                log_swallowed(_LOG, u'run_custom_rules')
    return issues


# ── Main ──────────────────────────────────────────────────────────────────────

def run_all_checks(doc, active_checks=None, custom_rules=None):
    active = active_checks or {'analytical', 'usage', 'attachment', 'joins'}
    results = []
    if 'analytical'  in active: results += check_analytical_disabled(doc)
    if 'usage'       in active: results += check_structural_usage(doc)
    if 'attachment'  in active: results += check_column_attachment(doc)
    if 'joins'       in active: results += check_beam_joins(doc)
    if custom_rules:            results += run_custom_rules(doc, custom_rules)
    _order = {'High': 0, 'Medium': 1, 'Low': 2}
    results.sort(key=lambda x: (_order.get(x['severity'], 9), x['category'], x['level']))
    high   = sum(1 for r in results if r['severity'] == 'High')
    medium = sum(1 for r in results if r['severity'] == 'Medium')
    low    = sum(1 for r in results if r['severity'] == 'Low')
    return {'issues': results, 'total': len(results), 'high': high, 'medium': medium, 'low': low}
