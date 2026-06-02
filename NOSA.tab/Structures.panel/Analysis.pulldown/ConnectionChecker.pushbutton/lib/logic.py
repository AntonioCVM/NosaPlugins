# -*- coding: utf-8 -*-
"""
ConnectionChecker Logic — verify End Join and Analytical connections
for structural beams and columns.
"""
from pyrevit import DB

def _get_id(eid):
    if hasattr(eid, 'Value'): return eid.Value
    if hasattr(eid, 'IntegerValue'): return eid.IntegerValue
    return int(str(eid))

def _collect(doc, bic):
    return list(DB.FilteredElementCollector(doc).OfCategory(bic)
                  .WhereElementIsNotElementType().ToElements())

def _level_name(doc, el):
    try:
        lid = el.LevelId
        if lid and lid != DB.ElementId.InvalidElementId:
            lv = doc.GetElement(lid)
            if lv: return lv.Name
    except Exception: pass
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
                    issues.append({'id': _get_id(el.Id), 'name': el.Name,
                                   'category': label, 'level': _level_name(doc, el),
                                   'check': 'Analytical disabled', 'severity': 'High'})
            except Exception: pass
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
                issues.append({'id': _get_id(el.Id), 'name': el.Name,
                               'category': 'Beam', 'level': _level_name(doc, el),
                               'check': 'Structural usage empty', 'severity': 'Medium'})
        except Exception: pass
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
                issues.append({'id': _get_id(el.Id), 'name': el.Name,
                               'category': 'Column', 'level': _level_name(doc, el),
                               'check': 'Column base not attached', 'severity': 'Medium'})
            if top_p and top_p.AsInteger() == 0:
                issues.append({'id': _get_id(el.Id), 'name': el.Name,
                               'category': 'Column', 'level': _level_name(doc, el),
                               'check': 'Column top not attached', 'severity': 'Low'})
        except Exception: pass
    return issues

# ── Beam end join check ───────────────────────────────────────────────────────

def check_beam_joins(doc):
    """
    Beams where End 0 or End 1 has no join (checks via LocationCurve endpoints
    against nearby elements — simplified heuristic).
    """
    issues = []
    beams = _collect(doc, DB.BuiltInCategory.OST_StructuralFraming)
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
                      .WherePasses(bbf)
                      .WhereElementIsNotElementType()
                      .ToElements()
                )
                nearby = [n for n in nearby if _get_id(n.Id) != _get_id(el.Id)]
                if not nearby:
                    issues.append({
                        'id': _get_id(el.Id), 'name': el.Name,
                        'category': 'Beam', 'level': _level_name(doc, el),
                        'check': 'End {} — no adjacent element'.format(end_idx),
                        'severity': 'Medium'
                    })
        except Exception: pass
    return issues

# ── Main ──────────────────────────────────────────────────────────────────────

def run_all_checks(doc, active_checks=None):
    active = active_checks or {'analytical', 'usage', 'attachment', 'joins'}
    results = []
    if 'analytical'  in active: results += check_analytical_disabled(doc)
    if 'usage'       in active: results += check_structural_usage(doc)
    if 'attachment'  in active: results += check_column_attachment(doc)
    if 'joins'       in active: results += check_beam_joins(doc)
    _order = {'High': 0, 'Medium': 1, 'Low': 2}
    results.sort(key=lambda x: (_order.get(x['severity'], 9), x['category'], x['level']))
    high   = sum(1 for r in results if r['severity'] == 'High')
    medium = sum(1 for r in results if r['severity'] == 'Medium')
    low    = sum(1 for r in results if r['severity'] == 'Low')
    return {'issues': results, 'total': len(results), 'high': high, 'medium': medium, 'low': low}
