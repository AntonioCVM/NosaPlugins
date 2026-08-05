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

from nosa_utils.revit_helpers import get_id_value

# ---------------------------------------------------------------------------
# Target categories
# ---------------------------------------------------------------------------

CATEGORY_CHOICES = (
    ('StructuralFraming',    u'Beams (incl. ground beams)', DB.BuiltInCategory.OST_StructuralFraming),
    ('StructuralColumns',    u'Columns',                     DB.BuiltInCategory.OST_StructuralColumns),
    ('StructuralFoundation', u'Foundations (piles, pilecaps)', DB.BuiltInCategory.OST_StructuralFoundation),
    ('Floors',               u'Floors / slabs',              DB.BuiltInCategory.OST_Floors),
    ('Walls',                u'Walls',                       DB.BuiltInCategory.OST_Walls),
)

CATEGORY_KEYS = tuple(c[0] for c in CATEGORY_CHOICES)
_BIC_BY_KEY = {c[0]: c[2] for c in CATEGORY_CHOICES}
_LABEL_BY_KEY = {c[0]: c[1] for c in CATEGORY_CHOICES}

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
        if int(bic) == bic_int:
            return key
    return None


def _family_code(family_name):
    """
    Short, human-recognisable code derived from a family name, so families
    that differ only in a digit (e.g. "Pile Cap-2 Pile" vs "Pile Cap-3
    Pile") still get visibly different default prefixes: first letter of
    the name plus any digits found in it (e.g. "Pile Cap-2 Pile" -> "P2",
    "Pile Cap-3 Pile" -> "P3", "UC Universal Column" -> "U").
    """
    if not family_name:
        return u''
    name = family_name.strip()
    first_letter = next((c for c in name if c.isalpha()), u'')
    digits = u''.join(re.findall(r'\d+', name))[:2]
    code = (first_letter.upper() + digits) if (first_letter or digits) else name[:2].upper()
    return code[:4]


def default_prefix_for(category_key, family_name, type_name):
    """
    Deterministic default prefix — same heuristic used by the manual grid
    and by the automatic DMU, so both agree on a brand-new Type. Always
    incorporates the Family (not just the Category), so different families
    within one category (e.g. two beam families, or 2-pile vs 3-pile
    pilecaps) get visibly different default codes rather than sharing one
    category-wide letter and only differing by an arbitrary number.
    """
    if category_key == 'StructuralFoundation':
        text = u'{} {}'.format(family_name or u'', type_name or u'').lower()
        if any(k in text for k in _GROUND_KEYWORDS):
            base = u'GB'
        elif any(k in text for k in _CAP_KEYWORDS):
            base = u'PC'
        elif any(k in text for k in _PILE_KEYWORDS):
            base = u'P'
        else:
            base = u'F'
    else:
        base = _DEFAULT_PREFIX.get(category_key, u'X')
    fam_code = _family_code(family_name)
    if fam_code and not fam_code.startswith(base) and not base.startswith(fam_code):
        return u'{}{}'.format(base, fam_code)
    return base


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
            wanted_ints = {int(_BIC_BY_KEY[k]): k for k in wanted}
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
            bic = _BIC_BY_KEY[key]
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
            fam_name = getattr(type_elem, 'FamilyName', None)
            if not fam_name:
                p = type_elem.get_Parameter(DB.BuiltInParameter.SYMBOL_FAMILY_NAME_PARAM)
                fam_name = p.AsString() if p else u''
            type_name = getattr(type_elem, 'Name', None) or u''
            return cat_key, fam_name or u'', type_name
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
                    pass
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
        with revit.Transaction(u'NOSA — Element Comments'):
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
                        pass
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
    bic = _BIC_BY_KEY.get(category_key)
    if bic is None:
        return u''
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
            fam = getattr(type_elem, 'FamilyName', u'') or u''
            tname = getattr(type_elem, 'Name', u'') or u''
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


def _type_size_code(type_name):
    """
    First number found in a Type name (e.g. '300x300mm' -> '300',
    '450mm dia' -> '450'). Used so a Comments code hints at real size
    instead of an arbitrary sequence position — two Types that only
    differ by dimension (e.g. two square columns) get visibly different,
    recognisable codes rather than an opaque incrementing digit.
    """
    if not type_name:
        return u''
    m = re.search(r'\d+', type_name)
    return m.group(0) if m else u''


def compute_group_values(groups, config_map, only_empty=False):
    """
    Deterministic {key: value} for every group — shared by the manual
    grid's live preview and the actual Apply so they can never disagree.

    Each group's numeric part is its own Type's size digits when
    available (self-explanatory codes). A collision — two different
    Types under the same prefix extracting the same digits, or a Type
    name with no digits at all — always falls back to the next free
    sequential number under that prefix, so two different Types can
    NEVER end up with the identical Comments value, regardless of
    whether their default prefixes happened to look similar.
    """
    values = {}
    seq = defaultdict(int)
    used = defaultdict(set)
    for key in sorted(groups.keys(), key=lambda k: (k[0], k[1], k[2])):
        grp = groups[key]
        if only_empty and grp.current_comment:
            values[key] = grp.current_comment
            continue
        prefix, suffix = config_map.get(key, (u'', u''))
        prefix = prefix or u''
        suffix = suffix or u''
        num_part = _type_size_code(grp.type_name)
        if not num_part or num_part in used[prefix]:
            seq[prefix] += 1
            num_part = u'{}'.format(seq[prefix])
            while num_part in used[prefix]:
                seq[prefix] += 1
                num_part = u'{}'.format(seq[prefix])
        used[prefix].add(num_part)
        values[key] = u'{}{}{}'.format(prefix, num_part, suffix)
    return values


def _comments_value_taken(doc, value):
    """True if any element in the target categories already has exactly
    this Comments value."""
    if not value:
        return False
    for bic in _BIC_BY_KEY.values():
        for el in (DB.FilteredElementCollector(doc)
                   .OfCategory(bic).WhereElementIsNotElementType()):
            try:
                p = el.get_Parameter(DB.BuiltInParameter.ALL_MODEL_INSTANCE_COMMENTS)
                if ((p.AsString() or u'').strip() if p else u'') == value:
                    return True
            except Exception:
                continue
    return False


def next_code_for_new_type(doc, prefix, type_name):
    """
    Numeric part of a brand-new Type's Comments code for the automatic
    DMU — prefers the Type's own size digits (same rule as
    compute_group_values), falling back to the next free sequential
    number when those digits are already used by a different Type under
    the same prefix, or the Type name has no digits. Guarantees two
    different Types can never end up with the same Comments value.
    """
    size_code = _type_size_code(type_name)
    if size_code and not _comments_value_taken(doc, prefix + size_code):
        return size_code
    return u'{}'.format(next_free_number(doc, prefix))
