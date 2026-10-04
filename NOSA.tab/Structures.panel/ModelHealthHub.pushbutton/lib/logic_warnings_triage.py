# -*- coding: utf-8 -*-
"""
WarningsTriage Logic — Classify Revit model warnings by structural impact.
Uses warning_rules.json to map descriptions to severity + action.
"""
import os
import json
from Autodesk.Revit import DB
from nosa_utils.revit_helpers import get_id_value
from nosa_utils.telemetry import log_swallowed
from nosa_utils.revit_helpers import element_id_from_int
from nosa_utils import transactions as nosa_tx  # T8.1: no Revit failure dialogs
_LOG = u'ModelHealthHub/warnings_triage'
_RULES_FILE = os.path.join(os.path.dirname(__file__), 'warning_rules.json')




def load_warning_rules():
    try:
        if os.path.exists(_RULES_FILE):
            with open(_RULES_FILE, 'r') as f:
                return json.load(f)
    except Exception:
        log_swallowed(_LOG, u'load_warning_rules')
    return {"rules": [], "default_severity": "Low",
            "default_action": "Review the warning description."}


def _classify(description, rules_data):
    desc_lower = (description or '').lower()
    for rule in rules_data.get('rules', []):
        kw = rule.get('keyword', '').lower()
        if kw and kw in desc_lower:
            return rule.get('severity', 'Low'), rule.get('action', '')
    return (rules_data.get('default_severity', 'Low'),
            rules_data.get('default_action', ''))


def _element_label(doc, eid):
    try:
        el = doc.GetElement(eid)
        if el is None:
            return 'ID:{}'.format(get_id_value(eid))
        cat  = el.Category.Name if el.Category else ''
        name = getattr(el, 'Name', '') or ''
        return '{} {}'.format(cat, name).strip() or 'ID:{}'.format(get_id_value(eid))
    except Exception:
        return 'ID:{}'.format(get_id_value(eid))


def get_warnings(doc):
    """Return raw Revit failure messages."""
    try:
        return list(doc.GetWarnings())
    except Exception:
        return []


def classify_warnings(doc, active_severities=None):
    """
    Returns list of dicts:
      {index, description, severity, action, element_ids, element_labels, group_key}
    active_severities: set e.g. {'High','Medium','Low'} — None means all.
    """
    rules_data = load_warning_rules()
    warnings   = get_warnings(doc)
    results    = []

    for i, w in enumerate(warnings):
        try:
            desc     = w.GetDescriptionText() or ''
            severity, action = _classify(desc, rules_data)

            if active_severities and severity not in active_severities:
                continue

            eids   = list(w.GetFailingElements())
            labels = [_element_label(doc, eid) for eid in eids[:5]]
            if len(eids) > 5:
                labels.append('... +{}'.format(len(eids) - 5))

            results.append({
                'index':          i + 1,
                'description':    desc[:200],
                'severity':       severity,
                'action':         action,
                'element_ids':    [get_id_value(eid) for eid in eids],
                'element_labels': labels,
                'elements_str':   ', '.join(labels[:3]),
                'count_elements': len(eids),
                'ignored':        False,
            })
        except Exception:
            log_swallowed(_LOG, u'classify_warnings')

    # Sort: High -> Medium -> Low, then by description
    _order = {'High': 0, 'Medium': 1, 'Low': 2}
    results.sort(key=lambda x: (_order.get(x['severity'], 9), x['description']))

    high   = sum(1 for r in results if r['severity'] == 'High')
    medium = sum(1 for r in results if r['severity'] == 'Medium')
    low    = sum(1 for r in results if r['severity'] == 'Low')

    return {
        'warnings': results,
        'total':    len(results),
        'high':     high,
        'medium':   medium,
        'low':      low,
    }


# ── auto-fix ──────────────────────────────────────────────────────────────────

FIXABLE_KEYWORDS = {
    'highlighted elements are joined': 'unjoin',
    'elements are joined but do not intersect': 'unjoin',
    'room separation':                          'delete_room_separation',
}


def _detect_fix_type(description):
    """Return fix action key or None."""
    desc_lower = (description or '').lower()
    for keyword, action in FIXABLE_KEYWORDS.items():
        if keyword in desc_lower:
            return action
    return None


def auto_fix_warning(doc, warning_row_data):
    """
    Attempt to auto-fix a warning.

    warning_row_data: dict with keys 'description' and 'element_ids' (list of int).
    Returns (success: bool, message: str).
    """
    description = warning_row_data.get('description', '')
    element_ids = warning_row_data.get('element_ids', [])
    fix_type    = _detect_fix_type(description)

    if fix_type is None:
        return False, "No automatic fix available for this warning type."

    if fix_type == 'unjoin':
        return _fix_unjoin(doc, element_ids)

    if fix_type == 'delete_room_separation':
        return _fix_delete_room_separation(doc, element_ids)

    return False, "Fix type '{}' not implemented.".format(fix_type)


def _fix_unjoin(doc, element_ids):
    """Unjoin all pairs among element_ids that are currently joined."""
    fixed  = 0
    errors = 0
    try:
        elements = []
        for eid in element_ids:
            try:
                el = doc.GetElement(element_id_from_int(eid))
                if el is not None:
                    elements.append(el)
            except Exception:
                log_swallowed(_LOG, u'_fix_unjoin')

        if len(elements) < 2:
            return False, "Need at least 2 valid elements to unjoin."

        with nosa_tx.guard(DB.Transaction(doc, u"NOSA — Auto-Fix: Unjoin Elements")) as t:
            t.Start()
            for i in range(len(elements)):
                for j in range(i + 1, len(elements)):
                    try:
                        if DB.JoinGeometryUtils.AreElementsJoined(
                                doc, elements[i], elements[j]):
                            DB.JoinGeometryUtils.UnjoinGeometry(
                                doc, elements[i], elements[j])
                            fixed += 1
                    except Exception:
                        errors += 1
            t.Commit()
    except Exception as e:
        return False, "Transaction failed: {}".format(e)

    if fixed == 0 and errors == 0:
        return False, "No joined pairs found among the warning elements."
    msg = "Unjoined {} pair(s).".format(fixed)
    if errors:
        msg += " {} pair(s) could not be unjoined.".format(errors)
    return fixed > 0, msg


def _fix_delete_room_separation(doc, element_ids):
    """Delete room-separation lines referenced in the warning."""
    deleted = 0
    try:
        with nosa_tx.guard(DB.Transaction(doc, u"NOSA — Auto-Fix: Delete Room Separation")) as t:
            t.Start()
            for eid in element_ids:
                try:
                    el = doc.GetElement(element_id_from_int(eid))
                    if el is None:
                        continue
                    cat = el.Category
                    if cat and cat.Id == DB.ElementId(
                            DB.BuiltInCategory.OST_RoomSeparationLines):
                        doc.Delete(el.Id)
                        deleted += 1
                except Exception:
                    log_swallowed(_LOG, u'_fix_delete_room_separation')
            t.Commit()
    except Exception as e:
        return False, "Transaction failed: {}".format(e)

    if deleted == 0:
        return False, "No room-separation lines found to delete."
    return True, "Deleted {} room-separation line(s).".format(deleted)


def get_fixable_description(description):
    """Return human-readable fix label for a warning description, or None."""
    fix_type = _detect_fix_type(description)
    labels = {
        'unjoin':                  'Unjoin elements',
        'delete_room_separation':  'Delete room separation line(s)',
    }
    return labels.get(fix_type)
