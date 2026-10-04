# -*- coding: utf-8 -*-
"""
Element Comments Hub — logic.

Assigns a shared Comments code to every element of the same exact Type
(Category + Family + Type — never looser than that), matching the
"Structural dimensions" legend convention: same size => same code,
different size => different code. Generalizes the grouping shape of
PileMaster's NumberingLogic (logic_numbering.py) but keys on the exact
Type instead of Family alone, and always writes Comments (never Mark),
so it can safely cover every structural category including piles and
pilecaps without colliding with PileMaster's own Mark numbering.
"""
import re
from collections import defaultdict

from Autodesk.Revit import DB
from pyrevit import revit

from nosa_utils.revit_helpers import get_id_value, element_name
from nosa_utils.telemetry import log_swallowed
from nosa_utils import transactions as nosa_tx  # T8.1: no Revit failure dialogs
_LOG = u'elementcommentshub'

# ---------------------------------------------------------------------------
# Target categories
# ---------------------------------------------------------------------------

CATEGORY_CHOICES = (
    ('StructuralFraming',    u'Beams (incl. ground beams)', 'OST_StructuralFraming'),
    ('StructuralColumns',    u'Columns',                     'OST_StructuralColumns'),
    ('StructuralFoundation', u'Foundations (piles, pilecaps)', 'OST_StructuralFoundation'),
    ('Floors',               u'Floors / slabs',              'OST_Floors'),
    ('Walls',                u'Walls',                       'OST_Walls'),
)

CATEGORY_KEYS = tuple(c[0] for c in CATEGORY_CHOICES)
_BIC_BY_KEY = {c[0]: c[2] for c in CATEGORY_CHOICES}
_LABEL_BY_KEY = {c[0]: c[1] for c in CATEGORY_CHOICES}


def _bic(name):
    return getattr(DB.BuiltInCategory, name)

_DEFAULT_PREFIX = {
    'StructuralFraming':    u'B',
    'StructuralColumns':    u'C',
    'Floors':                u'F',
    'Walls':                 u'W',
}

# Keyword heuristics — only used to pick a sensible *default* prefix the
# user can freely override per row; grouping itself never depends on them.
_CAP_KEYWORDS    = (u'cap', u'slab', u'raft', u'foundation', u'enc', u'zapat')
_PILE_KEYWORDS   = (u'pile', u'piling', u'pilote')
_GROUND_KEYWORDS = (u'ground beam', u'ground', u'riostra', u'viga de atado', u'tie beam')


def _category_key_for_bic(bic_int):
    for key, _label, bic in CATEGORY_CHOICES:
        if int(_bic(bic)) == bic_int:
            return key
    return None


def _read_family_and_type(type_elem):
    """
    (family_name, type_name) for a Type element, read the reliable way —
    BuiltInParameter first (proven in PileMaster's logic_numbering.py),
    falling back to the direct .FamilyName/.Name properties. Shared by
    every place in this module that needs a Type's real name, so the
    exact-Type grouping guarantee only has one implementation to trust.
    """
    fam_name = u''
    try:
        p = type_elem.get_Parameter(DB.BuiltInParameter.SYMBOL_FAMILY_NAME_PARAM)
        if p:
            fam_name = p.AsString() or u''
    except Exception:
        log_swallowed(_LOG, u'_read_family_and_type')
    if not fam_name:
        try:
            fam_name = type_elem.FamilyName or u''
        except Exception:
            fam_name = u''

    type_name = u''
    try:
        p = type_elem.get_Parameter(DB.BuiltInParameter.SYMBOL_NAME_PARAM)
        if p:
            type_name = p.AsString() or u''
    except Exception:
        log_swallowed(_LOG, u'_read_family_and_type')
    if not type_name:
        type_name = element_name(type_elem)

    return fam_name, type_name


def default_prefix_for(category_key, family_name, type_name):
    """
    Deterministic default prefix — same heuristic used by the manual grid
    and by the automatic DMU, so both agree on a brand-new Type. One
    plain letter per category (C/B/F/W, or GB/PC/P for foundations),
    matching the reference convention (C1, C2, C3 / B1, B2 / PC1, PC2 /
    GB1 / P1 / F1, F2 / W1, W2) — the sequential number is what tells
    different Types apart, not the prefix itself.
    """
    if category_key == 'StructuralFoundation':
        text = u'{} {}'.format(family_name or u'', type_name or u'').lower()
        if any(k in text for k in _GROUND_KEYWORDS):
            return u'GB'
        if any(k in text for k in _CAP_KEYWORDS):
            return u'PC'
        if any(k in text for k in _PILE_KEYWORDS):
            return u'P'
        return u'F'
    return _DEFAULT_PREFIX.get(category_key, u'X')


class ElementGroup(object):
    """One row = one exact (Category, Family, Type)."""
    def __init__(self, key, category_key, family_name, type_name):
        self.key           = key            # tuple, stable grouping key
        self.category_key  = category_key
        self.category_label = _LABEL_BY_KEY.get(category_key, category_key)
        self.family_name   = family_name
        self.type_name     = type_name
        self.elements      = []
        self.current_comment = u''           # first non-empty Comments value found, if any


class TypeCommentsLogic(object):
    def __init__(self, doc):
        self.doc = doc

    # -- collection ---------------------------------------------------------

    def get_elements(self, scope, category_keys, uidoc=None):
        """
        scope: 'active_view' | 'selection' | 'project'.
        Returns [(category_key, element), ...]. Collects one category at a
        time with the plain .OfCategory(...) collector idiom used
        everywhere else in this codebase (PileMaster, WorksetHealth, etc.)
        instead of ElementMulticategoryFilter, so category membership is
        never re-derived (and never silently lost) after collection.
        """
        wanted = [k for k in category_keys if k in _BIC_BY_KEY]
        if not wanted:
            return []

        if scope == 'selection':
            if uidoc is None:
                return []
            wanted_ints = {int(_bic(_BIC_BY_KEY[k])): k for k in wanted}
            result = []
            for eid in uidoc.Selection.GetElementIds():
                el = self.doc.GetElement(eid)
                if el is None or el.Category is None:
                    continue
                key = wanted_ints.get(get_id_value(el.Category.Id))
                if key:
                    result.append((key, el))
            return result

        result = []
        for key in wanted:
            bic = _bic(_BIC_BY_KEY[key])
            try:
                if scope == 'active_view':
                    collector = DB.FilteredElementCollector(self.doc, self.doc.ActiveView.Id)
                else:
                    collector = DB.FilteredElementCollector(self.doc)
                elems = collector.OfCategory(bic).WhereElementIsNotElementType().ToElements()
            except Exception:
                elems = []
            for el in elems:
                result.append((key, el))
        return result

    # -- grouping -------------------------------------------------------------

    def element_type_info(self, element, category_key=None):
        """
        (category_key, family_name, type_name) or (None, None, None).
        Pass category_key when it is already known (manual grid, from
        get_elements) to skip re-deriving it; the DMU (which only has a
        raw added ElementId) leaves it None and it is looked up here.
        """
        try:
            cat_key = category_key
            if cat_key is None:
                cat = element.Category
                if cat is None:
                    return None, None, None
                cat_key = _category_key_for_bic(get_id_value(cat.Id))
                if cat_key is None:
                    return None, None, None
            type_id = element.GetTypeId()
            if type_id == DB.ElementId.InvalidElementId:
                return None, None, None
            type_elem = self.doc.GetElement(type_id)
            if type_elem is None:
                return None, None, None
            fam_name, type_name = _read_family_and_type(type_elem)
            return cat_key, fam_name, type_name
        except Exception:
            return None, None, None

    def group_by_type(self, pairs):
        """
        pairs: [(category_key, element), ...] from get_elements.
        {(category_key, family_name, type_name): ElementGroup}
        Strictly exact-Type grouping — the guarantee that different sizes
        never end up sharing a Comments code.
        """
        groups = {}
        for cat_key, el in pairs:
            _cat_key, fam_name, type_name = self.element_type_info(el, category_key=cat_key)
            key = (cat_key, fam_name, type_name)
            grp = groups.get(key)
            if grp is None:
                grp = ElementGroup(key, cat_key, fam_name, type_name)
                groups[key] = grp
            grp.elements.append(el)
            if not grp.current_comment:
                try:
                    p = el.get_Parameter(DB.BuiltInParameter.ALL_MODEL_INSTANCE_COMMENTS)
                    val = (p.AsString() or u'').strip() if p else u''
                    if val:
                        grp.current_comment = val
                except Exception:
                    log_swallowed(_LOG, u'TypeCommentsLogic.group_by_type')
        return groups

    # -- apply ------------------------------------------------------------

    def apply_comments(self, groups, config_map, only_empty=False):
        """
        groups: {key: ElementGroup} from group_by_type.
        config_map: {key: (prefix, suffix)} — one entry per group row.
        Each group gets ONE Comments value shared by every element in it.
        Values are computed by compute_group_values — the same function
        the manual-grid preview uses — so what's shown before Apply is
        exactly what gets written.
        Returns (elements_written, groups_written).
        """
        values = compute_group_values(groups, config_map, only_empty=only_empty)
        written = 0
        groups_written = 0
        with nosa_tx.revit_transaction(u'NOSA — Element Comments'):
            for key, grp in groups.items():
                if only_empty and grp.current_comment:
                    continue
                value = values.get(key, u'')
                if not value:
                    continue
                any_ok = False
                for el in grp.elements:
                    try:
                        p = el.get_Parameter(DB.BuiltInParameter.ALL_MODEL_INSTANCE_COMMENTS)
                        if p and not p.IsReadOnly:
                            p.Set(value)
                            written += 1
                            any_ok = True
                    except Exception:
                        log_swallowed(_LOG, u'TypeCommentsLogic.apply_comments')
                if any_ok:
                    groups_written += 1
        return written, groups_written


# ---------------------------------------------------------------------------
# Shared helpers used by both the manual grid and the automatic DMU so the
# two modes always agree on prefixes and next-free numbers.
# ---------------------------------------------------------------------------

def existing_comment_for_type(doc, category_key, family_name, type_name, exclude_id=None):
    """Return an existing non-empty Comments value already used by another
    element of this exact Type, or u'' if the Type is genuinely new."""
    bic_name = _BIC_BY_KEY.get(category_key)
    if bic_name is None:
        return u''
    bic = _bic(bic_name)
    collector = (DB.FilteredElementCollector(doc)
                 .OfCategory(bic).WhereElementIsNotElementType())
    for el in collector:
        if exclude_id is not None and el.Id == exclude_id:
            continue
        try:
            type_id = el.GetTypeId()
            if type_id == DB.ElementId.InvalidElementId:
                continue
            type_elem = doc.GetElement(type_id)
            if type_elem is None:
                continue
            fam, tname = _read_family_and_type(type_elem)
            if fam != family_name or tname != type_name:
                continue
            p = el.get_Parameter(DB.BuiltInParameter.ALL_MODEL_INSTANCE_COMMENTS)
            val = (p.AsString() or u'').strip() if p else u''
            if val:
                return val
        except Exception:
            continue
    return u''


def next_free_number(doc, prefix):
    """Highest existing Comments value under this prefix (across the whole
    model, any category) + 1. Keeps sequences unique per prefix so two
    Types under the same code family never collide."""
    pat = re.compile(u'^' + re.escape(prefix or u'') + u'(\\d+)$')
    best = 0
    for bic in _BIC_BY_KEY.values():
        for el in (DB.FilteredElementCollector(doc)
                   .OfCategory(bic).WhereElementIsNotElementType()):
            try:
                p = el.get_Parameter(DB.BuiltInParameter.ALL_MODEL_INSTANCE_COMMENTS)
                val = (p.AsString() or u'').strip() if p else u''
                m = pat.match(val)
                if m:
                    n = int(m.group(1))
                    if n > best:
                        best = n
            except Exception:
                continue
    return best + 1


def compute_group_values(groups, config_map, only_empty=False):
    """
    Deterministic {key: value} for every group — shared by the manual
    grid's live preview and the actual Apply so they can never disagree.

    Plain per-prefix sequential numbering (C1, C2, C3 / B1, B2 / PC1,
    PC2 / GB1 / P1 / F1, F2 / W1, W2 — the reference convention). Each
    group is a distinct exact Type, so every Type gets its own number;
    the guarantee against two Types sharing a code comes from grouping
    always being exact-Type (group_by_type), not from the numbering
    scheme itself.
    """
    values = {}
    seq = defaultdict(int)
    for key in sorted(groups.keys(), key=lambda k: (k[0], k[1], k[2])):
        grp = groups[key]
        if only_empty and grp.current_comment:
            values[key] = grp.current_comment
            continue
        prefix, suffix = config_map.get(key, (u'', u''))
        prefix = prefix or u''
        suffix = suffix or u''
        seq[prefix] += 1
        values[key] = u'{}{}{}'.format(prefix, seq[prefix], suffix)
    return values


def next_code_for_new_type(doc, prefix):
    """
    Numeric part of a brand-new Type's Comments code for the automatic
    DMU — the next free sequential number under this prefix, matching
    the manual grid's plain numbering convention.
    """
    return u'{}'.format(next_free_number(doc, prefix))
