# -*- coding: utf-8 -*-
"""Element Join logic: priority-aware join, unjoin and swap, with a preview and per-pair rollback."""
import io
import json
import os
import sys

from Autodesk.Revit import DB

_lib = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', '..', 'lib'))
if _lib not in sys.path:
    sys.path.insert(0, _lib)

from nosa_utils.bootstrap import load_module
from nosa_utils.revit_helpers import get_id_value, element_name
from nosa_utils.telemetry import log_swallowed
from nosa_utils import solids as _solids
from nosa_utils import unit_conversion as _uc
from nosa_utils import transactions as nosa_tx

_plan = load_module('elemjoin_plan', os.path.join(os.path.dirname(__file__), 'join_plan.py'))

_LOG = u'elementjoin'
_FT_TO_MM = _uc.FT_TO_MM
MIN_OVERLAP_MM3 = 1000.0            # 1 cm3: below this two elements only touch

DEFAULT_PRIORITY = ['Floors', 'Framing', 'Columns', 'Walls', 'Foundations', 'Roofs', 'Ceilings']

_CONFIGS_ROOT = os.path.join(os.getenv('APPDATA', ''), 'pyRevit', 'Extensions', 'NOSA.extension', 'NOSA_Configs')
_CONFIG_FILE = os.path.join(_CONFIGS_ROOT, '_smartjoin.json')

PREVIEW_STATUS = {u'join': u'will join', u'fix': u'will fix', u'unjoin': u'will unjoin', u'swap': u'will swap'}
DONE_STATUS = {u'join': u'joined', u'fix': u'fixed', u'unjoin': u'unjoined', u'swap': u'swapped'}


def _joinable_bics():
    return {
        'Columns':     DB.BuiltInCategory.OST_StructuralColumns,
        'Framing':     DB.BuiltInCategory.OST_StructuralFraming,
        'Floors':      DB.BuiltInCategory.OST_Floors,
        'Walls':       DB.BuiltInCategory.OST_Walls,
        'Foundations': DB.BuiltInCategory.OST_StructuralFoundation,
        'Roofs':       DB.BuiltInCategory.OST_Roofs,
        'Ceilings':    DB.BuiltInCategory.OST_Ceilings,
    }


# ── priority config ─────────────────────────────────────────────────────────

def _read_config():
    try:
        if os.path.exists(_CONFIG_FILE):
            with io.open(_CONFIG_FILE, 'r', encoding='utf-8') as f:
                return json.loads(f.read())
    except Exception:
        log_swallowed(_LOG, u'read_config')
    return {}


def load_priority():
    saved = _read_config().get('priority', [])
    if saved and set(saved) <= set(DEFAULT_PRIORITY):
        return list(saved) + [c for c in DEFAULT_PRIORITY if c not in saved]
    return list(DEFAULT_PRIORITY)


def save_priority(priority_list):
    try:
        if not os.path.exists(_CONFIGS_ROOT):
            os.makedirs(_CONFIGS_ROOT)
        data = _read_config()
        data['priority'] = list(priority_list)
        text = json.dumps(data, indent=2)
        if isinstance(text, bytes):
            text = text.decode('utf-8')
        with io.open(_CONFIG_FILE, 'w', encoding='utf-8') as f:
            f.write(text)
    except Exception:
        log_swallowed(_LOG, u'save_priority')


# ── element collection ──────────────────────────────────────────────────────

def _category_lookup():
    return dict((int(bic), name) for name, bic in _joinable_bics().items())


def _box_of(el):
    try:
        bb = el.get_BoundingBox(None)
        if bb is None:
            return None
        return (bb.Min.X, bb.Min.Y, bb.Min.Z, bb.Max.X, bb.Max.Y, bb.Max.Z)
    except Exception:
        return None


def _item(el, category):
    return {'id': get_id_value(el.Id), 'name': element_name(el) or str(get_id_value(el.Id)),
            'category': category, 'element': el, 'box': _box_of(el)}


def collect_joinable_elements(doc, category_names=None):
    """Every element of the chosen categories as {id, name, category, element, box}."""
    names = category_names if category_names is not None else list(_joinable_bics().keys())
    bics = _joinable_bics()
    items = []
    for cat_name in names:
        bic = bics.get(cat_name)
        if bic is None:
            continue
        try:
            for el in DB.FilteredElementCollector(doc).OfCategory(bic).WhereElementIsNotElementType().ToElements():
                try:
                    items.append(_item(el, cat_name))
                except Exception:
                    log_swallowed(_LOG, u'collect_joinable_elements.item')
        except Exception:
            log_swallowed(_LOG, u'collect_joinable_elements')
    return items


def items_from_ids(doc, ids, category_names):
    """Selected elements that belong to one of the chosen categories."""
    lookup = _category_lookup()
    items = []
    for eid in ids:
        try:
            el = doc.GetElement(eid)
            cat = el.Category if el is not None else None
            name = lookup.get(get_id_value(cat.Id)) if cat is not None else None
            if name in category_names:
                items.append(_item(el, name))
        except Exception:
            log_swallowed(_LOG, u'items_from_ids')
    return items


def item_from_element(el):
    cat = el.Category
    name = _category_lookup().get(get_id_value(cat.Id)) if cat is not None else None
    return _item(el, name or (cat.Name if cat is not None else u''))


# ── join primitives ─────────────────────────────────────────────────────────

def is_joined(doc, el1, el2):
    try:
        return DB.JoinGeometryUtils.AreElementsJoined(doc, el1, el2)
    except Exception:
        return False


def cuts(doc, el1, el2):
    """True when el1 cuts el2 in their join; None when the pair is not joined or the answer is unknown."""
    try:
        return DB.JoinGeometryUtils.IsCuttingElementInJoin(doc, el1, el2)
    except Exception:
        return None


def _overlap_mm3(a, b, cache):
    """Overlap volume of two not-yet-joined elements in mm3; None when a solid cannot be read."""
    solids = []
    for it in (a, b):
        key = it['id']
        if key not in cache:
            try:
                cache[key] = _solids.get_element_solid(it['element'])
            except Exception:
                log_swallowed(_LOG, u'overlap.solid')
                cache[key] = None
        solids.append(cache[key])
    if solids[0] is None or solids[1] is None:
        return None
    return _solids.intersection_volume(solids[0], solids[1]) * _FT_TO_MM ** 3


# ── planning ────────────────────────────────────────────────────────────────

class Settings(object):
    def __init__(self, priority=None, tolerance_mm=50.0, fix_existing=True, require_overlap=True, simple=False):
        self.rank = None if simple else dict((c, i) for i, c in enumerate(priority or DEFAULT_PRIORITY))
        self.simple = simple
        self.tolerance_ft = tolerance_mm / _FT_TO_MM
        self.fix_existing = fix_existing and not simple
        self.require_overlap = require_overlap


def _rank(settings, item):
    if settings.rank is None:
        return 0
    return settings.rank.get(item['category'])


def evaluate(doc, a, b, settings, cache, forced=None):
    """Decide what to do with one pair: {a, b, action, dominant, msg}."""
    joined = is_joined(doc, a['element'], b['element'])
    a_cuts = cuts(doc, a['element'], b['element']) if joined else None
    overlap = None
    if not joined and settings.require_overlap:
        mm3 = _overlap_mm3(a, b, cache)
        overlap = True if mm3 is None else mm3 >= MIN_OVERLAP_MM3
    action, dominant, msg = _plan.decide(_rank(settings, a), _rank(settings, b), joined, a_cuts, overlap,
                                         settings.fix_existing, settings.require_overlap, forced)
    return {'a': a, 'b': b, 'action': action, 'dominant': dominant, 'msg': msg}


def plan_join(doc, universe, primary, settings):
    """Rows for every near pair that has at least one element in `primary` (None = all)."""
    primary_ids = None if primary is None else set(it['id'] for it in primary)
    cache, rows = {}, []
    pairs = _plan.candidate_pairs([it['box'] for it in universe], settings.tolerance_ft)
    for i, j in pairs:
        a, b = universe[i], universe[j]
        if primary_ids is not None and a['id'] not in primary_ids and b['id'] not in primary_ids:
            continue
        rows.append(evaluate(doc, a, b, settings, cache))
    return rows


def plan_one_to_many(doc, anchor, universe, settings, anchor_cuts):
    """Rows pairing `anchor` with every near element of the universe; the anchor cuts them or is cut by them."""
    cache, rows = {}, []
    for other in universe:
        if other['id'] == anchor['id'] or anchor['box'] is None or other['box'] is None:
            continue
        if not _plan.boxes_touch(anchor['box'], other['box'], settings.tolerance_ft):
            continue
        rows.append(evaluate(doc, anchor, other, settings, cache, forced=u'a' if anchor_cuts else u'b'))
    return rows


def plan_pair(doc, a, b, settings):
    """The manual pair: always joined, whatever the overlap, with `a` cutting `b`."""
    settings.require_overlap = False
    return [evaluate(doc, a, b, settings, {}, forced=u'a')]


def plan_joined(doc, universe, primary, operation):
    """Rows for the joins that already exist (unjoin / swap); both elements must be in the universe."""
    by_id = dict((it['id'], it) for it in universe)
    seen, rows = set(), []
    for it in (universe if primary is None else primary):
        try:
            joined_ids = list(DB.JoinGeometryUtils.GetJoinedElements(doc, it['element']))
        except Exception:
            log_swallowed(_LOG, u'plan_joined')
            continue
        for eid in joined_ids:
            other = by_id.get(get_id_value(eid))
            if other is None:
                continue
            key = (min(it['id'], other['id']), max(it['id'], other['id']))
            if key in seen:
                continue
            seen.add(key)
            rows.append({'a': it, 'b': other, 'action': operation, 'dominant': None,
                         'msg': u'Joined'})
    return rows


# ── execution ───────────────────────────────────────────────────────────────

def _ordered(row):
    """(first, second) with the dominant element first when there is one."""
    if row['dominant'] == u'b':
        return row['b'], row['a']
    return row['a'], row['b']


def _result(row, status, msg):
    first, second = _ordered(row)
    return {'id1': first['id'], 'name1': first['name'], 'cat1': first['category'],
            'id2': second['id'], 'name2': second['name'], 'cat2': second['category'],
            'status': status, 'msg': msg}


def _make_cut(doc, dominant, subordinate):
    if cuts(doc, dominant, subordinate):
        return
    DB.JoinGeometryUtils.SwitchJoinOrder(doc, dominant, subordinate)
    if not cuts(doc, dominant, subordinate):
        raise Exception(u'Revit would not change the cutting order')


def _apply(doc, row):
    """Do one row inside a SubTransaction; (True, message) or (False, reason) with that pair undone."""
    first, second = _ordered(row)
    e1, e2 = first['element'], second['element']
    action = row['action']
    st = DB.SubTransaction(doc)
    try:
        st.Start()
        if action == u'join':
            DB.JoinGeometryUtils.JoinGeometry(doc, e1, e2)
            if row['dominant'] is not None:
                _make_cut(doc, e1, e2)
            msg = u'%s cuts %s' % (first['name'], second['name']) if row['dominant'] is not None else u'Joined'
        elif action == u'fix':
            _make_cut(doc, e1, e2)
            msg = u'%s now cuts %s' % (first['name'], second['name'])
        elif action == u'unjoin':
            DB.JoinGeometryUtils.UnjoinGeometry(doc, e1, e2)
            msg = u'Unjoined'
        else:
            DB.JoinGeometryUtils.SwitchJoinOrder(doc, e1, e2)
            msg = u'Join order swapped'
        st.Commit()
        return True, msg
    except Exception as ex:
        log_swallowed(_LOG, u'apply.%s' % action)
        try:
            if st.HasStarted():
                st.RollBack()
        except Exception:
            log_swallowed(_LOG, u'apply.rollback')
        return False, u'%s failed: %s' % (action, ex)


def execute(doc, rows, preview, tx_name):
    """Result dicts for the rows; nothing is changed when `preview` is true."""
    results = []
    todo = [r for r in rows if r['action'] in DONE_STATUS]
    if preview:
        for row in rows:
            if row['action'] in DONE_STATUS:
                results.append(_result(row, PREVIEW_STATUS[row['action']], row['msg']))
            else:
                results.append(_result(row, u'ok' if row['action'] == u'ok' else u'skipped', row['msg']))
        return results
    t = None
    if todo:
        t = nosa_tx.guard(DB.Transaction(doc, u'NOSA — Element Join — %s' % tx_name))
        t.Start()
    try:
        for row in rows:
            if row['action'] not in DONE_STATUS:
                results.append(_result(row, u'ok' if row['action'] == u'ok' else u'skipped', row['msg']))
                continue
            ok, msg = _apply(doc, row)
            results.append(_result(row, DONE_STATUS[row['action']] if ok else u'failed', msg))
        if t is not None:
            t.Commit()
    except Exception:
        if t is not None and t.HasStarted():
            t.RollBack()
        raise
    return results
