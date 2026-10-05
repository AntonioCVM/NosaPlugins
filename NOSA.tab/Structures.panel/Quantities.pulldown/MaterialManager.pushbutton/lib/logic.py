# -*- coding: utf-8 -*-
import io
"""Material Manager Logic — audit and clean up Revit materials."""
import sys, os, csv
from Autodesk.Revit import DB
from System.Collections.Generic import List
from nosa_utils.telemetry import log_swallowed
_LOG = u'materialmanager'
_lib = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', '..', 'lib'))
if _lib not in sys.path:
    sys.path.insert(0, _lib)
from nosa_utils.revit_helpers import get_id_value, get_element_type_name
from nosa_utils import transactions as nosa_tx  # T8.1: no Revit failure dialogs


# ── material asset helpers ────────────────────────────────────────────────────

def _safe_name(el):
    """
    getattr(..., default) form of `.Name` — bare `el.Name` raises
    AttributeError on this Revit/pyRevit build for at least ElementType and
    Material (confirmed live); getattr() catches that internally and falls
    back, regardless of the underlying cause.
    """
    return getattr(el, 'Name', None) or u'—'


def _mat_class(mat):
    try:
        return mat.MaterialClass or u'—'
    except Exception:
        return u'—'


def _mat_category(mat):
    try:
        return mat.MaterialCategory or u'—'
    except Exception:
        return u'—'


def collect_materials(doc):
    """
    Returns list of dicts sorted by (class, name):
      { 'id', 'name', 'class', 'category', 'use_count', 'is_unused', 'material' }
    """
    use_counts = {}

    # Materials can be used by any category (instances or types), so this
    # can't be narrowed with a category filter the way most other collectors
    # in this codebase are. A prior "optimization" here (iterating one bare
    # FilteredElementCollector(doc) with no filter method at all) broke
    # scanning in production on this Revit/pyRevit build — reverted to two
    # explicitly-filtered passes, which is the reliable, previously-working
    # form.
    for el in DB.FilteredElementCollector(doc).WhereElementIsNotElementType().ToElements():
        try:
            for mid in el.GetMaterialIds(False):
                key = get_id_value(mid)
                use_counts[key] = use_counts.get(key, 0) + 1
        except Exception:
            log_swallowed(_LOG, u'collect_materials')

    for t in DB.FilteredElementCollector(doc).WhereElementIsElementType().ToElements():
        try:
            for mid in t.GetMaterialIds(False):
                key = get_id_value(mid)
                use_counts[key] = use_counts.get(key, 0) + 1
        except Exception:
            log_swallowed(_LOG, u'collect_materials')

    mats = DB.FilteredElementCollector(doc).OfClass(DB.Material).ToElements()
    result = []
    for mat in mats:
        try:
            mid = get_id_value(mat.Id)
            cnt = use_counts.get(mid, 0)
            result.append({
                'id':        mat.Id,
                'name':      _safe_name(mat),
                'class':     _mat_class(mat),
                'category':  _mat_category(mat),
                'use_count': cnt,
                'is_unused': cnt == 0,
                'material':  mat,
            })
        except Exception:
            log_swallowed(_LOG, u'collect_materials')

    result.sort(key=lambda r: (r['class'], r['name'].lower()))
    return result


def find_near_duplicates(material_dicts, threshold=3):
    """Return set of material names that have a near-duplicate (Levenshtein distance <= threshold)."""
    names = [r['name'] for r in material_dicts]
    flagged = set()
    for i in range(len(names)):
        for j in range(i + 1, len(names)):
            if _lev(names[i].lower(), names[j].lower()) <= threshold:
                flagged.add(names[i])
                flagged.add(names[j])
    return flagged


def _lev(a, b):
    if abs(len(a) - len(b)) > 4:
        return 99
    m, n = len(a), len(b)
    dp = list(range(n + 1))
    for i in range(1, m + 1):
        prev = dp[:]
        dp[0] = i
        for j in range(1, n + 1):
            cost = 0 if a[i-1] == b[j-1] else 1
            dp[j] = min(dp[j] + 1, dp[j-1] + 1, prev[j-1] + cost)
    return dp[n]


def delete_materials(doc, material_ids):
    """Delete materials by ElementId. Returns (deleted_count, failed_count)."""
    deleted = failed = 0
    with nosa_tx.guard(DB.Transaction(doc, u"NOSA — Material Manager — Delete Materials")) as t:
        t.Start()
        for mid in material_ids:
            try:
                doc.Delete(List[DB.ElementId]([mid]))
                deleted += 1
            except Exception:
                failed += 1
        t.Commit()
    return deleted, failed


def export_csv(rows, path):
    with io.open(path, 'w', encoding='utf-8', newline='') as f:
        f.write(u'\ufeff')  # one BOM: 'utf-8-sig' repeats it on every write in IronPython
        w = csv.writer(f)
        w.writerow(['Name', 'Class', 'Category', 'Use Count', 'Status'])
        for r in rows:
            w.writerow([
                r['name'], r['class'], r['category'],
                r['use_count'],
                'Unused' if r['is_unused'] else 'In use',
            ])


def get_all_materials(doc):
    """Returns sorted list of (ElementId, name) tuples for all materials in doc."""
    mats = DB.FilteredElementCollector(doc).OfClass(DB.Material).ToElements()
    pairs = [(m.Id, _safe_name(m)) for m in mats]
    pairs.sort(key=lambda x: x[1].lower())
    return pairs


# ── element material helpers ───────────────────────────────────────────────────

def _struct_bics():
    return [
        DB.BuiltInCategory.OST_StructuralFraming,
        DB.BuiltInCategory.OST_StructuralColumns,
        DB.BuiltInCategory.OST_Walls,
        DB.BuiltInCategory.OST_Floors,
        DB.BuiltInCategory.OST_StructuralFoundation,
    ]

_MATERIAL_KEYWORDS = [
    ('concrete', ['concrete', 'hormigon', 'concreto', 'c25', 'c30', 'c35', 'c40', 'c45']),
    ('steel',    ['steel', 'acero', 'metal', 'hss', 's275', 's355']),
    ('timber',   ['timber', 'wood', 'madera', 'glulam', 'clt']),
]


def _level_name(doc, el):
    try:
        lvl_id = el.LevelId
        if lvl_id and lvl_id != DB.ElementId.InvalidElementId:
            lvl = doc.GetElement(lvl_id)
            if lvl:
                return lvl.Name
    except Exception:
        log_swallowed(_LOG, u'_level_name')
    try:
        param = el.get_Parameter(DB.BuiltInParameter.SCHEDULE_LEVEL_PARAM)
        if param:
            return param.AsValueString() or u'—'
    except Exception:
        log_swallowed(_LOG, u'_level_name')
    return u'—'


def _cat_name(el):
    try:
        return _safe_name(el.Category) if el.Category else u'—'
    except Exception:
        return u'—'


def _get_structural_material(doc, el):
    """Return (ElementId, name) for the element's structural material, or (None, None)."""
    try:
        param = el.get_Parameter(DB.BuiltInParameter.STRUCTURAL_MATERIAL_PARAM)
        if param and param.HasValue:
            mat_id = param.AsElementId()
            if mat_id and mat_id != DB.ElementId.InvalidElementId:
                mat = doc.GetElement(mat_id)
                if mat:
                    return mat_id, _safe_name(mat)
    except Exception:
        log_swallowed(_LOG, u'_get_structural_material')
    try:
        ids = list(el.GetMaterialIds(False))
        if ids:
            mat = doc.GetElement(ids[0])
            if mat:
                return ids[0], _safe_name(mat)
    except Exception:
        log_swallowed(_LOG, u'_get_structural_material')
    return None, None


def _propose_material(type_name, mat_list):
    """Return (ElementId, name) best keyword match from type_name, or (None, None)."""
    tn = type_name.lower()
    for _kw, variants in _MATERIAL_KEYWORDS:
        if any(v in tn for v in variants):
            for mid, mname in mat_list:
                if any(v in mname.lower() for v in variants):
                    return mid, mname
    return None, None


def collect_element_materials(doc, diagnostics=None):
    """
    Scan structural elements for material assignments.
    Returns list of dicts sorted by (category, level, type_name):
      { 'id', 'category', 'level', 'type_name',
        'material_id', 'material_name', 'is_missing',
        'proposed_id', 'proposed_name' }

    diagnostics: optional dict — if given, filled in-place with
      {'<BuiltInCategory name>': {'collected': N, 'rows_built': M, 'errors': [...]}}
      so callers can tell "the collector found nothing" apart from
      "the collector found elements but every row build failed" when the
      scan comes back empty.
    """
    mat_list = get_all_materials(doc)
    result = []

    for bic in _struct_bics():
        bic_label = str(bic).rsplit('.', 1)[-1]
        stats = {'collected': 0, 'rows_built': 0, 'errors': []}
        if diagnostics is not None:
            diagnostics[bic_label] = stats
        try:
            els = DB.FilteredElementCollector(doc)\
                    .OfCategory(bic)\
                    .WhereElementIsNotElementType()\
                    .ToElements()
        except Exception as e:
            stats['errors'].append(u'collector: {}'.format(e))
            continue
        els = list(els)
        stats['collected'] = len(els)
        for el in els:
            try:
                # el_type.Name (bare property access) raises AttributeError
                # under this Revit/pyRevit CPython build — confirmed live,
                # 100% of elements across every category failed on it.
                # get_element_type_name() reads BuiltInParameter.SYMBOL_NAME_PARAM
                # instead, the same safe pattern already used elsewhere in
                # this codebase, and doesn't hit whatever pythonnet property
                # resolution issue this is.
                type_name = get_element_type_name(el) or u'—'
                mat_id, mat_name = _get_structural_material(doc, el)
                is_missing = mat_id is None
                prop_id = prop_name = None
                if is_missing:
                    prop_id, prop_name = _propose_material(type_name, mat_list)
                result.append({
                    'id':            el.Id,
                    'category':      _cat_name(el),
                    'level':         _level_name(doc, el),
                    'type_name':     type_name,
                    'material_id':   mat_id,
                    'material_name': mat_name or u'—',
                    'is_missing':    is_missing,
                    'proposed_id':   prop_id,
                    'proposed_name': prop_name or u'—',
                })
                stats['rows_built'] += 1
            except Exception as e:
                if len(stats['errors']) < 3:
                    stats['errors'].append(str(e))

    result.sort(key=lambda r: (r['category'], r['level'], r['type_name']))
    return result


def collect_element_materials_from_selection(doc, element_ids):
    """
    Same row shape as collect_element_materials(), but built from an explicit
    list of ElementIds instead of the fixed structural-category scan — lets
    the user work on whatever they've selected in Revit, regardless of
    category (Generic Models, in-place families, categories not covered by
    _struct_bics(), etc.).
    """
    mat_list = get_all_materials(doc)
    result = []
    for eid in element_ids:
        try:
            el = doc.GetElement(eid)
            if el is None:
                continue
            type_name  = get_element_type_name(el) or u'—'
            mat_id, mat_name = _get_structural_material(doc, el)
            is_missing = mat_id is None
            prop_id = prop_name = None
            if is_missing:
                prop_id, prop_name = _propose_material(type_name, mat_list)
            result.append({
                'id':            el.Id,
                'category':      _cat_name(el),
                'level':         _level_name(doc, el),
                'type_name':     type_name,
                'material_id':   mat_id,
                'material_name': mat_name or u'—',
                'is_missing':    is_missing,
                'proposed_id':   prop_id,
                'proposed_name': prop_name or u'—',
            })
        except Exception:
            log_swallowed(_LOG, u'collect_element_materials_from_selection')

    result.sort(key=lambda r: (r['category'], r['level'], r['type_name']))
    return result


def _assign_material_any_param(el, material_id, reason_log=None):
    """
    Try STRUCTURAL_MATERIAL_PARAM, then MATERIAL_ID_PARAM, then — for nested/
    generic family instances that expose their material through a family-
    defined parameter with no fixed BuiltInParameter at all (common for
    components nested inside a host family) — any writable ElementId-storage
    parameter whose name mentions "material". Returns True if assigned.

    If reason_log (a list) is passed, appends a short human-readable reason
    when no writable parameter could be found — e.g. many family materials
    are TYPE parameters, which read as IsReadOnly=True on the instance and
    can only be changed by editing the family/type, not the placed instance.
    """
    readonly_names = []

    p = el.get_Parameter(DB.BuiltInParameter.STRUCTURAL_MATERIAL_PARAM)
    if p:
        if not p.IsReadOnly:
            p.Set(material_id)
            return True
        readonly_names.append(u'Structural Material')

    p2 = el.get_Parameter(DB.BuiltInParameter.MATERIAL_ID_PARAM)
    if p2:
        if not p2.IsReadOnly:
            p2.Set(material_id)
            return True
        readonly_names.append(u'Material')

    checked = 0
    try:
        for param in el.Parameters:
            try:
                if (param.StorageType == DB.StorageType.ElementId
                        and param.Definition
                        and 'material' in param.Definition.Name.lower()):
                    checked += 1
                    if not param.IsReadOnly:
                        param.Set(material_id)
                        return True
                    readonly_names.append(param.Definition.Name)
            except Exception:
                continue
    except Exception:
        log_swallowed(_LOG, u'_assign_material_any_param')

    if reason_log is not None:
        if readonly_names:
            unique_names = []
            for n in readonly_names:
                if n not in unique_names:
                    unique_names.append(n)
            reason_log.append(
                u'read-only material parameter(s): {} — likely a Type '
                u'parameter in this family, only editable via Edit Type/'
                u'Edit Family, not from the placed instance'.format(
                    u', '.join(unique_names)))
        elif checked == 0:
            reason_log.append(u'no ElementId-typed "material" parameter found on this element')

    return False


def _nested_subcomponent_ids(el):
    """FamilyInstances can host their own nested FamilyInstances (e.g. a
    connection plate family with bolt/plate sub-families nested inside it).
    Selecting the HOST doesn't reach those nested instances' own material
    parameters — this recurses into them so assigning a material to the host
    also reaches everything nested inside it."""
    ids = []
    try:
        sub_ids = el.GetSubComponentIds()
    except Exception:
        return ids
    for sid in sub_ids:
        ids.append(sid)
    return ids


def assign_material_to_elements(doc, element_ids, material_id, diagnostics=None):
    """
    Assign material_id to each element_id — see _assign_material_any_param()
    for the fallback chain. Also recurses into nested sub-components (for
    family instances that host their own nested families) so a material
    assigned to the host reaches nested components too, not just the host's
    own parameters. Returns (ok_count, failed_count, readonly_type_eids).

    If diagnostics (a list) is passed, appends one line per failed element
    explaining why (e.g. every material parameter found was read-only),
    so a "Failed" result is actionable instead of a dead end.

    readonly_type_eids is the subset of element_ids that failed specifically
    because every material parameter found was read-only (almost always a
    Type parameter) — the caller can offer assign_material_to_types() for
    exactly these, rather than for every kind of failure.
    """
    ok = failed = 0
    readonly_type_eids = []
    with nosa_tx.guard(DB.Transaction(doc, u"NOSA — Material Manager — Assign Material")) as t:
        t.Start()
        for eid in element_ids:
            try:
                el = doc.GetElement(eid)
                if el is None:
                    failed += 1
                    if diagnostics is not None:
                        diagnostics.append(u'{}: element not found'.format(get_id_value(eid)))
                    continue

                host_reasons = [] if diagnostics is not None else None
                host_ok = _assign_material_any_param(el, material_id, host_reasons)

                nested_ok = nested_failed = 0
                nested_reasons = []
                for sub_id in _nested_subcomponent_ids(el):
                    try:
                        sub_el = doc.GetElement(sub_id)
                        sub_reasons = [] if diagnostics is not None else None
                        if sub_el is not None and _assign_material_any_param(sub_el, material_id, sub_reasons):
                            nested_ok += 1
                        else:
                            nested_failed += 1
                            if sub_reasons:
                                nested_reasons.extend(sub_reasons)
                    except Exception as ex:
                        nested_failed += 1
                        if diagnostics is not None:
                            nested_reasons.append(u'{}'.format(ex))

                if host_ok or nested_ok:
                    ok += 1
                    failed += nested_failed
                    if nested_failed and diagnostics is not None:
                        diagnostics.append(
                            u'{} ({}): host OK, {} nested sub-component(s) failed — {}'.format(
                                get_id_value(eid), _cat_name(el), nested_failed,
                                u'; '.join(nested_reasons[:2]) or u'unknown reason'))
                else:
                    failed += 1
                    reasons = list(host_reasons or [])
                    reasons.extend(nested_reasons)
                    if reasons and all(u'read-only' in r for r in reasons):
                        readonly_type_eids.append(eid)
                    if diagnostics is not None:
                        why = u'; '.join(reasons) if reasons else u'no writable material parameter found'
                        diagnostics.append(u'{} ({}): {}'.format(
                            get_id_value(eid), _cat_name(el), why))
            except Exception as ex:
                failed += 1
                if diagnostics is not None:
                    diagnostics.append(u'{}: {}'.format(get_id_value(eid), ex))
        t.Commit()
    return ok, failed, readonly_type_eids


def assign_material_to_types(doc, element_ids, material_id, diagnostics=None):
    """
    Assign material_id at the TYPE level for the ElementTypes of the given
    element_ids — for elements whose material is a Type parameter (read-only
    on the instance, confirmed via assign_material_to_elements' diagnostics).

    This changes the material for EVERY instance of that Type in the whole
    project, not just the ones selected — callers must get explicit user
    confirmation before calling this. Returns (ok_count, failed_count) where
    counts are per unique Type touched, not per input element.
    """
    ok = failed = 0
    seen_type_ids = set()
    with nosa_tx.guard(DB.Transaction(doc, u"NOSA — Material Manager — Assign Material (Type)")) as t:
        t.Start()
        for eid in element_ids:
            try:
                el = doc.GetElement(eid)
                if el is None:
                    continue
                type_id = el.GetTypeId()
                if type_id is None or type_id == DB.ElementId.InvalidElementId:
                    continue
                key = get_id_value(type_id)
                if key in seen_type_ids:
                    continue
                seen_type_ids.add(key)

                type_el = doc.GetElement(type_id)
                if type_el is None:
                    failed += 1
                    continue

                reason_log = [] if diagnostics is not None else None
                if _assign_material_any_param(type_el, material_id, reason_log):
                    ok += 1
                else:
                    failed += 1
                    if diagnostics is not None:
                        why = u'; '.join(reason_log) if reason_log else u'no writable material parameter found'
                        diagnostics.append(u'Type {} ({}): {}'.format(
                            key, _safe_name(type_el), why))
            except Exception as ex:
                failed += 1
                if diagnostics is not None:
                    diagnostics.append(u'{}: {}'.format(get_id_value(eid), ex))
        t.Commit()
    return ok, failed


def export_element_materials_csv(rows, path):
    with io.open(path, 'w', encoding='utf-8', newline='') as f:
        f.write(u'\ufeff')  # one BOM: 'utf-8-sig' repeats it on every write in IronPython
        w = csv.writer(f)
        w.writerow(['Element ID', 'Category', 'Level', 'Type', 'Material', 'Missing', 'Proposed'])
        for r in rows:
            w.writerow([
                get_id_value(r['id']),
                r['category'], r['level'], r['type_name'],
                r['material_name'],
                'YES' if r['is_missing'] else '',
                r['proposed_name'] if r['is_missing'] else '',
            ])





# ── replace material (bulk) ────────────────────────────────────────────────────

REPLACE_CATEGORIES = [
    (u'Structural Columns', ('OST_StructuralColumns',)),
    (u'Structural Framing', ('OST_StructuralFraming',)),
    (u'Structural Foundations', ('OST_StructuralFoundation',)),
    (u'Floors', ('OST_Floors',)),
    (u'Walls', ('OST_Walls',)),
    (u'Stairs', ('OST_Stairs', 'OST_StairsRuns', 'OST_StairsLandings')),
]
ALL_STRUCTURAL = u'All structural categories'
_TYPE_MATERIAL_PARAMS = (u'Structural Material', u'Monolithic Material', u'Material', u'Tread Material',
                         u'Riser Material', u'Stringer Material', u'Landing Material')


def replace_scope(label):
    """BuiltInCategory names for a category label of the Replace box (pure)."""
    if label in (None, u'', ALL_STRUCTURAL):
        return [b for _l, bics in REPLACE_CATEGORIES for b in bics]
    for name, bics in REPLACE_CATEGORIES:
        if name == label:
            return list(bics)
    return []


def _replace_in_type(doc, el_type, from_id, to_id):
    """Swap from -> to in a type's compound layers and material parameters. True when changed."""
    changed = False
    try:
        cs = el_type.GetCompoundStructure() if hasattr(el_type, 'GetCompoundStructure') else None
    except Exception:
        cs = None
    if cs is not None:
        hit = False
        for i in range(cs.LayerCount):
            if cs.GetMaterialId(i) == from_id:
                cs.SetMaterialId(i, to_id)
                hit = True
        if hit:
            el_type.SetCompoundStructure(cs)
            changed = True
    for name in _TYPE_MATERIAL_PARAMS:
        p = el_type.LookupParameter(name)
        if p is not None and not p.IsReadOnly and p.StorageType == DB.StorageType.ElementId \
                and p.AsElementId() == from_id:
            p.Set(to_id)
            changed = True
    return changed


def replace_material(doc, from_id, to_id, category_label=None, level_name=None):
    """
    Every element of the scope made of `from_id` gets `to_id`: the instance Structural Material when the
    element has one (or none set but its geometry is `from_id`, e.g. a concrete column taking the category
    material), otherwise its TYPE (walls, floors, wall foundations, stair runs/landings: every instance of
    that type changes). Returns {'instances': n, 'types': [names], 'errors': [..]}.
    """
    report = {'instances': 0, 'types': [], 'errors': []}
    seen_types = set()
    with nosa_tx.guard(DB.Transaction(doc, u"NOSA — Material Manager — Replace Material")) as t:
        t.Start()
        for bic_name in replace_scope(category_label):
            bic = getattr(DB.BuiltInCategory, bic_name, None)
            if bic is None:
                continue
            for el in DB.FilteredElementCollector(doc).OfCategory(bic).WhereElementIsNotElementType():
                if level_name and _level_name(doc, el) != level_name:
                    continue
                try:
                    p = el.get_Parameter(DB.BuiltInParameter.STRUCTURAL_MATERIAL_PARAM)
                    if p is not None and not p.IsReadOnly and p.StorageType == DB.StorageType.ElementId:
                        cur = p.AsElementId()
                        empty = cur is None or cur == DB.ElementId.InvalidElementId
                        if cur == from_id or (empty and from_id in list(el.GetMaterialIds(False))):
                            p.Set(to_id)
                            report['instances'] += 1
                            continue
                    el_type = doc.GetElement(el.GetTypeId())
                    if el_type is None or get_id_value(el_type.Id) in seen_types:
                        continue
                    seen_types.add(get_id_value(el_type.Id))
                    if _replace_in_type(doc, el_type, from_id, to_id):
                        from nosa_utils.revit_helpers import element_name
                        report['types'].append(u'{}: {}'.format(_cat_name(el), element_name(el_type)))
                except Exception as e:
                    if len(report['errors']) < 5:
                        report['errors'].append(u'{} {}: {}'.format(_cat_name(el), get_id_value(el.Id), e))
        t.Commit()
    return report
