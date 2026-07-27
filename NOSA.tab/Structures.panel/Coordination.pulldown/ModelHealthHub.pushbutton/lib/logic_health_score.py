# -*- coding: utf-8 -*-
"""
HealthScore Logic v2 — Structural Model Health Check
Checks: materials, analytical model, orphan foundations, warnings,
        parameter completeness, level offsets, duplicate marks,
        elements not on a level, unhosted rebar.
Returns a weighted score 0-100 with per-check detail.
"""
import math, os, sys, json
from Autodesk.Revit import DB
_lib = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', '..', 'lib'))
if _lib not in sys.path:
    sys.path.insert(0, _lib)
from nosa_utils.revit_helpers import get_id_value

_HISTORY_FILE = os.path.join(
    os.path.dirname(__file__), '..', '..', '..', '..', '..', 'NOSA_Configs', '_healthscore_history.json'
)

# ─────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────



def _collect(doc, bic):
    return list(
        DB.FilteredElementCollector(doc)
          .OfCategory(bic)
          .WhereElementIsNotElementType()
          .ToElements()
    )


def _mm_to_ft(mm):
    return mm / 304.8


# ─────────────────────────────────────────────────
# Individual checks
# ─────────────────────────────────────────────────

def check_elements_without_material(doc, categories=None):
    """Structural elements with no material assigned."""
    issues = []
    target_bics = categories or [
        DB.BuiltInCategory.OST_StructuralColumns,
        DB.BuiltInCategory.OST_StructuralFraming,
        DB.BuiltInCategory.OST_Floors,
        DB.BuiltInCategory.OST_Walls,
        DB.BuiltInCategory.OST_StructuralFoundation,
    ]
    for bic in target_bics:
        for el in _collect(doc, bic):
            try:
                has_material = False
                mat_param = el.get_Parameter(DB.BuiltInParameter.STRUCTURAL_MATERIAL_PARAM)
                if mat_param and mat_param.AsElementId() != DB.ElementId.InvalidElementId:
                    has_material = True
                if not has_material and hasattr(el, 'GetMaterialIds'):
                    if list(el.GetMaterialIds(False)):
                        has_material = True
                if not has_material:
                    issues.append({
                        'id': get_id_value(el.Id),
                        'name': getattr(el, 'Name', str(el.Id)),
                        'category': el.Category.Name if el.Category else 'Unknown',
                    })
            except Exception:
                pass
    return issues


def check_elements_without_analytical(doc, categories=None):
    """Structural elements where analytical model is disabled."""
    issues = []
    target_bics = categories or [
        DB.BuiltInCategory.OST_StructuralColumns,
        DB.BuiltInCategory.OST_StructuralFraming,
        DB.BuiltInCategory.OST_Floors,
    ]
    for bic in target_bics:
        for el in _collect(doc, bic):
            try:
                param = el.get_Parameter(DB.BuiltInParameter.STRUCTURAL_ANALYTICAL_MODEL)
                if param and param.AsInteger() == 0:
                    issues.append({
                        'id': get_id_value(el.Id),
                        'name': getattr(el, 'Name', str(el.Id)),
                        'category': el.Category.Name if el.Category else 'Unknown',
                    })
            except Exception:
                pass
    return issues


def check_orphan_foundations(doc, tolerance_mm=2000.0):
    """Isolated foundations with no structural column nearby."""
    issues = []
    tol = _mm_to_ft(tolerance_mm)
    foundations = _collect(doc, DB.BuiltInCategory.OST_StructuralFoundation)
    columns     = _collect(doc, DB.BuiltInCategory.OST_StructuralColumns)

    col_points = []
    for col in columns:
        if hasattr(col, 'Location') and hasattr(col.Location, 'Point'):
            col_points.append(col.Location.Point)

    for f in foundations:
        try:
            if not hasattr(f, 'Location') or not hasattr(f.Location, 'Point'):
                continue
            fp = f.Location.Point
            has_col = any(
                math.sqrt((fp.X - cp.X)**2 + (fp.Y - cp.Y)**2) < tol
                for cp in col_points
            )
            if not has_col:
                issues.append({
                    'id': get_id_value(f.Id),
                    'name': getattr(f, 'Name', str(f.Id)),
                    'category': 'Structural Foundation',
                })
        except Exception:
            pass
    return issues


def check_elements_with_warnings(doc):
    """Elements that appear in Revit model warnings."""
    issues = []
    try:
        for w in doc.GetWarnings():
            desc = w.GetDescriptionText()
            for eid in w.GetFailingElements():
                issues.append({'id': get_id_value(eid), 'warning': desc[:120] if desc else ''})
    except Exception:
        pass
    return issues


def check_parameter_completeness(doc, required_params=None):
    """Structural elements missing key parameters."""
    issues = []
    required = required_params or ['Mark']
    target_bics = [
        DB.BuiltInCategory.OST_StructuralColumns,
        DB.BuiltInCategory.OST_StructuralFraming,
        DB.BuiltInCategory.OST_StructuralFoundation,
    ]
    for bic in target_bics:
        for el in _collect(doc, bic):
            try:
                missing = []
                for pname in required:
                    p = el.LookupParameter(pname)
                    if not p:
                        p = el.get_Parameter(DB.BuiltInParameter.ALL_MODEL_MARK) if pname == 'Mark' else None
                    if not p or not p.AsString():
                        missing.append(pname)
                if missing:
                    issues.append({
                        'id': get_id_value(el.Id),
                        'name': getattr(el, 'Name', str(el.Id)),
                        'category': el.Category.Name if el.Category else 'Unknown',
                        'missing': ', '.join(missing),
                    })
            except Exception:
                pass
    return issues


def check_level_offsets(doc, max_offset_mm=3000.0):
    """Elements with FLOOR_HEIGHTABOVELEVEL_PARAM or BASE_OFFSET outside ±max_offset_mm."""
    issues = []
    limit = _mm_to_ft(max_offset_mm)
    bips = [
        DB.BuiltInParameter.FLOOR_HEIGHTABOVELEVEL_PARAM,
        DB.BuiltInParameter.INSTANCE_FREE_HOST_OFFSET_PARAM,
    ]
    target_bics = [
        DB.BuiltInCategory.OST_StructuralColumns,
        DB.BuiltInCategory.OST_StructuralFraming,
        DB.BuiltInCategory.OST_Floors,
    ]
    for bic in target_bics:
        for el in _collect(doc, bic):
            try:
                for bip in bips:
                    p = el.get_Parameter(bip)
                    if p and abs(p.AsDouble()) > limit:
                        issues.append({
                            'id': get_id_value(el.Id),
                            'name': getattr(el, 'Name', str(el.Id)),
                            'category': el.Category.Name if el.Category else 'Unknown',
                            'offset_mm': round(p.AsDouble() * 304.8, 0),
                        })
                        break
            except Exception:
                pass
    return issues


# ─── NEW CHECKS ──────────────────────────────────────────────────────────────

def check_duplicate_marks(doc):
    """
    Structural elements sharing the same non-empty Mark value.
    Returns issues for all elements that participate in a duplicate group.
    """
    target_bics = [
        DB.BuiltInCategory.OST_StructuralColumns,
        DB.BuiltInCategory.OST_StructuralFraming,
        DB.BuiltInCategory.OST_StructuralFoundation,
    ]
    mark_map = {}   # mark_value -> [{'id', 'name', 'category'}, ...]
    for bic in target_bics:
        for el in _collect(doc, bic):
            try:
                p = el.get_Parameter(DB.BuiltInParameter.ALL_MODEL_MARK)
                if not p:
                    p = el.LookupParameter('Mark')
                mark = (p.AsString() or '').strip() if p else ''
                if not mark:
                    continue
                if mark not in mark_map:
                    mark_map[mark] = []
                mark_map[mark].append({
                    'id': get_id_value(el.Id),
                    'name': getattr(el, 'Name', str(el.Id)),
                    'category': el.Category.Name if el.Category else 'Unknown',
                    'mark': mark,
                })
            except Exception:
                pass
    issues = []
    for mark, elems in mark_map.items():
        if len(elems) > 1:
            issues.extend(elems)
    return issues


def check_elements_not_on_level(doc):
    """
    Structural elements with no valid level assignment.
    """
    target_bics = [
        DB.BuiltInCategory.OST_StructuralColumns,
        DB.BuiltInCategory.OST_StructuralFraming,
        DB.BuiltInCategory.OST_Floors,
        DB.BuiltInCategory.OST_StructuralFoundation,
    ]
    issues = []
    level_bips = [
        DB.BuiltInParameter.FAMILY_LEVEL_PARAM,
        DB.BuiltInParameter.LEVEL_PARAM,
        DB.BuiltInParameter.STAIRS_BASE_LEVEL_PARAM,
        DB.BuiltInParameter.FLOOR_HEIGHTABOVELEVEL_PARAM,  # proxy — only exists if hosted to level
    ]
    for bic in target_bics:
        for el in _collect(doc, bic):
            try:
                has_level = False
                for bip in level_bips[:3]:
                    p = el.get_Parameter(bip)
                    if p and p.AsElementId() != DB.ElementId.InvalidElementId:
                        has_level = True
                        break
                if not has_level:
                    issues.append({
                        'id': get_id_value(el.Id),
                        'name': getattr(el, 'Name', str(el.Id)),
                        'category': el.Category.Name if el.Category else 'Unknown',
                    })
            except Exception:
                pass
    return issues


def check_unhosted_rebar(doc):
    """
    Rebar elements that have no valid host structural element.
    """
    issues = []
    try:
        for el in _collect(doc, DB.BuiltInCategory.OST_Rebar):
            try:
                host_id = el.HostId if hasattr(el, 'HostId') else None
                if host_id is None or host_id == DB.ElementId.InvalidElementId:
                    # Try GetHostId for Rebar
                    if hasattr(el, 'GetHostId'):
                        host_id = el.GetHostId()
                if host_id is None or host_id == DB.ElementId.InvalidElementId:
                    issues.append({
                        'id': get_id_value(el.Id),
                        'name': getattr(el, 'Name', str(el.Id)) or 'Rebar',
                        'category': 'Structural Rebar',
                    })
            except Exception:
                pass
    except Exception:
        pass
    return issues


# ─────────────────────────────────────────────────
# Score calculation
# ─────────────────────────────────────────────────

_WEIGHTS = {
    'no_material':    20,
    'no_analytical':  10,
    'orphan_found':   15,
    'warnings':       15,
    'param_missing':  10,
    'bad_offset':      5,
    'dup_marks':      10,
    'no_level':       10,
    'unhosted_rebar':  5,
}

_MAX_ISSUES_FOR_ZERO = {
    'no_material':   20,
    'no_analytical': 10,
    'orphan_found':   5,
    'warnings':      30,
    'param_missing': 30,
    'bad_offset':    10,
    'dup_marks':     20,
    'no_level':      10,
    'unhosted_rebar': 5,
}


def calculate_score(counts, weights=None):
    """Returns float score 0-100 (100 = no issues). Accepts optional weight overrides."""
    w = weights if weights else _WEIGHTS
    # Normalise so weights always sum to 100
    total_w = float(sum(w.values())) or 100.0
    total_deduction = 0.0
    for key, weight in w.items():
        n   = counts.get(key, 0)
        cap = _MAX_ISSUES_FOR_ZERO.get(key, 10)
        ratio = min(1.0, n / float(cap)) if cap > 0 else (1.0 if n > 0 else 0.0)
        total_deduction += (weight / total_w) * 100.0 * ratio
    return max(0.0, 100.0 - total_deduction)


# ─────────────────────────────────────────────────
# Score history
# ─────────────────────────────────────────────────

def save_score_history(doc_title, score, counts):
    """Append a score entry to the history file."""
    import datetime
    history = _load_history()
    entry = {
        'date':   datetime.datetime.now().strftime('%Y-%m-%d %H:%M'),
        'doc':    doc_title,
        'score':  round(score, 1),
        'counts': counts,
    }
    if doc_title not in history:
        history[doc_title] = []
    history[doc_title].append(entry)
    history[doc_title] = history[doc_title][-20:]  # keep last 20 per document
    try:
        try:
            os.makedirs(os.path.dirname(_HISTORY_FILE))
        except OSError:
            pass
        with open(_HISTORY_FILE, 'w') as f:
            json.dump(history, f, indent=2)
    except Exception:
        pass


def _load_history():
    try:
        with open(_HISTORY_FILE, 'r') as f:
            return json.load(f)
    except Exception:
        return {}


def get_score_history(doc_title):
    """Returns list of recent score entries for this document."""
    return _load_history().get(doc_title, [])


# ─────────────────────────────────────────────────
# Main entry — run all checks
# ─────────────────────────────────────────────────

_LABELS = {
    'no_material':   'Elements without material',
    'no_analytical': 'Analytical model disabled',
    'orphan_found':  'Orphan foundations',
    'warnings':      'Model warnings',
    'param_missing': 'Missing Mark parameter',
    'bad_offset':    'Excessive level offsets',
    'dup_marks':     'Duplicate Mark values',
    'no_level':      'Elements not on a level',
    'unhosted_rebar':'Unhosted rebar',
}
_SEVERITY = {
    'no_material':   'High',
    'no_analytical': 'Medium',
    'orphan_found':  'High',
    'warnings':      'High',
    'param_missing': 'Medium',
    'bad_offset':    'Low',
    'dup_marks':     'Medium',
    'no_level':      'High',
    'unhosted_rebar':'Medium',
}


def run_all_checks(doc, active_checks=None, weights=None):
    """
    Run all (or selected) checks.
    active_checks : set of key strings. None = run all.
    weights       : dict of {key: int} overrides for check weights (from UI sliders).
                    Falls back to _WEIGHTS defaults for any missing key.
    Returns dict:
      {'results', 'counts', 'score', 'checks'}
    """
    effective_weights = dict(_WEIGHTS)
    if weights:
        for k, v in weights.items():
            if k in effective_weights and v > 0:
                effective_weights[k] = int(v)

    all_checks = active_checks or set(effective_weights.keys())

    runners = {
        'no_material':   lambda: check_elements_without_material(doc),
        'no_analytical': lambda: check_elements_without_analytical(doc),
        'orphan_found':  lambda: check_orphan_foundations(doc),
        'warnings':      lambda: check_elements_with_warnings(doc),
        'param_missing': lambda: check_parameter_completeness(doc),
        'bad_offset':    lambda: check_level_offsets(doc),
        'dup_marks':     lambda: check_duplicate_marks(doc),
        'no_level':      lambda: check_elements_not_on_level(doc),
        'unhosted_rebar':lambda: check_unhosted_rebar(doc),
    }

    results = {}
    for key in all_checks:
        if key in runners:
            results[key] = runners[key]()

    counts = {k: len(v) for k, v in results.items()}
    score  = calculate_score(counts, effective_weights)

    checks_summary = [
        {
            'key':      key,
            'label':    _LABELS.get(key, key),
            'count':    counts.get(key, 0),
            'severity': _SEVERITY.get(key, 'Medium'),
            'weight':   effective_weights.get(key, 0),
        }
        for key in effective_weights
        if key in results
    ]

    return {
        'results': results,
        'counts':  counts,
        'score':   score,
        'checks':  checks_summary,
    }
