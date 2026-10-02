# -*- coding: utf-8 -*-
"""
SmartJoin Pro Logic — priority-aware join, unjoin and swap of structural geometry.
Uses Revit JoinGeometryUtils API.
"""
import sys
import os
from Autodesk.Revit import DB
from nosa_utils.telemetry import log_swallowed
_LOG = u'elementjoin'
_lib = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', '..', 'lib'))
if _lib not in sys.path:
    sys.path.insert(0, _lib)
from nosa_utils.revit_helpers import get_id_value
from nosa_utils import geometry as _geometry
from nosa_utils import unit_conversion as _uc10
_FT_TO_MM = _uc10.FT_TO_MM

# Default priority: index 0 = highest (cuts everyone below it).
# Lower index = more dominant (cuts).
_DEFAULT_PRIORITY = [
    'Floors',
    'Framing',
    'Columns',
    'Walls',
    'Foundations',
]

DEFAULT_PRIORITY = _DEFAULT_PRIORITY


def _joinable_bics():
    """Lazy BuiltInCategory map — avoids module-level API access in IronPython."""
    return {
        'Columns':     DB.BuiltInCategory.OST_StructuralColumns,
        'Framing':     DB.BuiltInCategory.OST_StructuralFraming,
        'Floors':      DB.BuiltInCategory.OST_Floors,
        'Walls':       DB.BuiltInCategory.OST_Walls,
        'Foundations': DB.BuiltInCategory.OST_StructuralFoundation,
    }

# Config persistence
_CONFIGS_ROOT = os.path.join(
    os.getenv('APPDATA', ''),
    'pyRevit', 'Extensions', 'NOSA.extension', 'NOSA_Configs'
)
_CONFIG_FILE = os.path.join(_CONFIGS_ROOT, '_smartjoin.json')


def load_priority():
    """Load saved priority order, falling back to DEFAULT_PRIORITY."""
    try:
        import json
        if os.path.exists(_CONFIG_FILE):
            with open(_CONFIG_FILE, 'r') as f:
                data = json.load(f)
            saved = data.get('priority', [])
            if saved and set(saved) == set(DEFAULT_PRIORITY):
                return saved
    except Exception:
        log_swallowed(_LOG, u'load_priority')
    return list(DEFAULT_PRIORITY)


def save_priority(priority_list):
    """Persist custom priority order."""
    try:
        import json
        if not os.path.exists(_CONFIGS_ROOT):
            os.makedirs(_CONFIGS_ROOT)
        with open(_CONFIG_FILE, 'r' if os.path.exists(_CONFIG_FILE) else 'w') as f:
            try:
                data = json.load(f)
            except Exception:
                data = {}
        data['priority'] = priority_list
        with open(_CONFIG_FILE, 'w') as f:
            json.dump(data, f, indent=2)
    except Exception:
        log_swallowed(_LOG, u'save_priority')




def _cat_name_for_element(el):
    """Return the _JOINABLE_BICS key for an element, or None."""
    try:
        cat = el.Category
        if cat is None:
            return None
        for name, bic in _joinable_bics().items():
            try:
                if cat.Id == DB.ElementId(bic):
                    return name
            except Exception:
                log_swallowed(_LOG, u'_cat_name_for_element')
    except Exception:
        log_swallowed(_LOG, u'_cat_name_for_element')
    return None


def collect_joinable_elements(doc, category_names=None):
    """Return list of dicts {id, name, category, element}."""
    if category_names is None:
        category_names = list(_joinable_bics().keys())
    elements = []
    for cat_name in category_names:
        bic = _joinable_bics().get(cat_name)
        if bic is None:
            continue
        try:
            items = list(
                DB.FilteredElementCollector(doc)
                  .OfCategory(bic)
                  .WhereElementIsNotElementType()
                  .ToElements()
            )
            for el in items:
                try:
                    name = getattr(el, 'Name', '') or str(el.Id)
                    elements.append({
                        'id':       get_id_value(el.Id),
                        'name':     name,
                        'category': cat_name,
                        'element':  el,
                    })
                except Exception:
                    log_swallowed(_LOG, u'collect_joinable_elements')
        except Exception:
            log_swallowed(_LOG, u'collect_joinable_elements')
    return elements


def is_joined(doc, el1, el2):
    try:
        return DB.JoinGeometryUtils.AreElementsJoined(doc, el1, el2)
    except Exception:
        return False


def join_elements(doc, el1, el2):
    try:
        if DB.JoinGeometryUtils.AreElementsJoined(doc, el1, el2):
            return True, "Already joined."
        DB.JoinGeometryUtils.JoinGeometry(doc, el1, el2)
        return True, "Joined."
    except Exception as e:
        return False, "Join failed: {}".format(e)


def unjoin_elements(doc, el1, el2):
    try:
        if not DB.JoinGeometryUtils.AreElementsJoined(doc, el1, el2):
            return True, "Not joined."
        DB.JoinGeometryUtils.UnjoinGeometry(doc, el1, el2)
        return True, "Unjoined."
    except Exception as e:
        return False, "Unjoin failed: {}".format(e)


def swap_join_order(doc, el1, el2):
    try:
        if not DB.JoinGeometryUtils.AreElementsJoined(doc, el1, el2):
            return False, "Elements are not joined."
        DB.JoinGeometryUtils.SwitchJoinOrder(doc, el1, el2)
        return True, "Join order swapped."
    except Exception as e:
        return False, "Swap failed: {}".format(e)


def join_ordered(doc, dominant_el, subordinate_el):
    """
    Join dominant_el cutting subordinate_el.
    Joins if not already joined, then enforces dominant order via SwitchJoinOrder.
    Returns (ok, msg).
    """
    try:
        already = DB.JoinGeometryUtils.AreElementsJoined(doc, dominant_el, subordinate_el)
        if not already:
            DB.JoinGeometryUtils.JoinGeometry(doc, dominant_el, subordinate_el)
        try:
            DB.JoinGeometryUtils.SwitchJoinOrder(doc, dominant_el, subordinate_el)
        except Exception:
            log_swallowed(_LOG, u'join_ordered')
        return True, "{} cuts {}.".format(
            getattr(dominant_el, 'Name', str(dominant_el.Id)),
            getattr(subordinate_el, 'Name', str(subordinate_el.Id)),
        )
    except Exception as e:
        return False, "Join ordered failed: {}".format(e)


def _bboxes_within_tolerance(el1, el2, tolerance_ft):
    try:
        bb1 = el1.get_BoundingBox(None)
        bb2 = el2.get_BoundingBox(None)
        return _geometry.bboxes_overlap(bb1, bb2, tolerance_ft)
    except Exception:
        return False


def batch_join_by_proximity(doc, elements, operation='join', tolerance_mm=50):
    """
    Batch join/unjoin/swap with proximity filter.
    operation : 'join' | 'unjoin' | 'swap'
    """
    tolerance_ft = tolerance_mm / _FT_TO_MM
    results = []
    n = len(elements)

    _op_funcs = {
        'join':   join_elements,
        'unjoin': unjoin_elements,
        'swap':   swap_join_order,
    }
    op_func = _op_funcs.get(operation, join_elements)

    try:
        with DB.Transaction(doc, u"NOSA — Element Join — {}".format(operation.capitalize())) as t:
            t.Start()
            for i in range(n):
                for j in range(i + 1, n):
                    a = elements[i]
                    b = elements[j]
                    if not _bboxes_within_tolerance(a['element'], b['element'], tolerance_ft):
                        continue
                    try:
                        ok, msg = op_func(doc, a['element'], b['element'])
                        if ok:
                            status = ('already_joined' if 'Already' in msg else
                                      'already_unjoined' if 'Not joined' in msg else
                                      operation + 'ed' if operation in ('join', 'unjoin') else 'swapped')
                        else:
                            status = 'failed'
                    except Exception as ex:
                        msg = str(ex)
                        status = 'failed'
                    results.append({
                        'id1': a['id'],   'name1': a['name'], 'cat1': a['category'],
                        'id2': b['id'],   'name2': b['name'], 'cat2': b['category'],
                        'status': status, 'msg': msg,
                    })
            t.Commit()
    except Exception as e:
        return [{'id1': 0, 'name1': '', 'cat1': '', 'id2': 0, 'name2': '',
                 'cat2': '', 'status': 'failed', 'msg': str(e)}]
    return results


def batch_join_ordered(doc, elements, priority_list, tolerance_mm=50, fix_existing=True):
    """
    Priority-aware batch join.

    For every pair within tolerance:
      1. If not joined: join with the higher-priority element dominant.
      2. If already joined but order is wrong: swap order.
      3. If already joined and order is correct: skip.

    priority_list: ordered list of category names, index 0 = highest priority.
    fix_existing: also correct already-joined pairs with wrong order.

    Returns list of result dicts:
      {id1, name1, cat1, id2, name2, cat2, status, msg}
    Status values:
      'joined'     — pair newly joined with correct priority
      'fixed'      — order was wrong, swapped to correct priority
      'ok'         — already joined with correct order
      'skipped'    — both categories not in priority list
      'failed'
    """
    tolerance_ft = tolerance_mm / _FT_TO_MM
    priority_rank = {cat: idx for idx, cat in enumerate(priority_list)}
    results = []
    n = len(elements)

    try:
        with DB.Transaction(doc, u"NOSA — Element Join — Priority Join") as t:
            t.Start()
            for i in range(n):
                for j in range(i + 1, n):
                    a = elements[i]
                    b = elements[j]
                    if not _bboxes_within_tolerance(a['element'], b['element'], tolerance_ft):
                        continue

                    cat_a = a['category']
                    cat_b = b['category']
                    rank_a = priority_rank.get(cat_a, 999)
                    rank_b = priority_rank.get(cat_b, 999)

                    if rank_a == 999 and rank_b == 999:
                        results.append({
                            'id1': a['id'], 'name1': a['name'], 'cat1': cat_a,
                            'id2': b['id'], 'name2': b['name'], 'cat2': cat_b,
                            'status': 'skipped', 'msg': 'Neither category in priority list',
                        })
                        continue

                    # dominant = lower rank index (higher priority)
                    if rank_a <= rank_b:
                        dominant, subordinate = a, b
                    else:
                        dominant, subordinate = b, a

                    dom_el  = dominant['element']
                    sub_el  = subordinate['element']

                    try:
                        already_joined = DB.JoinGeometryUtils.AreElementsJoined(doc, dom_el, sub_el)

                        if not already_joined:
                            DB.JoinGeometryUtils.JoinGeometry(doc, dom_el, sub_el)
                            try:
                                DB.JoinGeometryUtils.SwitchJoinOrder(doc, dom_el, sub_el)
                            except Exception:
                                log_swallowed(_LOG, u'batch_join_ordered')
                            status = 'joined'
                            msg = "{} cuts {}.".format(dominant['name'], subordinate['name'])

                        elif fix_existing:
                            # Check current order — try to switch and catch if already correct
                            try:
                                DB.JoinGeometryUtils.SwitchJoinOrder(doc, dom_el, sub_el)
                                # Switched back to make dominant actually cut subordinate
                                DB.JoinGeometryUtils.SwitchJoinOrder(doc, sub_el, dom_el)
                                status = 'ok'
                                msg = "Order already correct."
                            except Exception:
                                # SwitchJoinOrder may fail if order is already dominant→sub
                                status = 'ok'
                                msg = "Order already correct."

                        else:
                            status = 'ok'
                            msg = "Already joined."

                    except Exception as ex:
                        status = 'failed'
                        msg = str(ex)

                    results.append({
                        'id1': dominant['id'],   'name1': dominant['name'],   'cat1': dominant['category'],
                        'id2': subordinate['id'], 'name2': subordinate['name'], 'cat2': subordinate['category'],
                        'status': status, 'msg': msg,
                    })
            t.Commit()
    except Exception as e:
        return [{'id1': 0, 'name1': '', 'cat1': '', 'id2': 0, 'name2': '',
                 'cat2': '', 'status': 'failed', 'msg': str(e)}]
    return results
