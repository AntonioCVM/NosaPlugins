# -*- coding: utf-8 -*-
import io
"""Material Manager Logic — audit and clean up Revit materials."""
import sys, os, csv
from Autodesk.Revit import DB
from System.Collections.Generic import List
_lib = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', '..', 'lib'))
if _lib not in sys.path:
    sys.path.insert(0, _lib)
from nosa_utils.revit_helpers import get_id_value


# ── material asset helpers ────────────────────────────────────────────────────

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

    for el in DB.FilteredElementCollector(doc).WhereElementIsNotElementType().ToElements():
        try:
            for mid in el.GetMaterialIds(False):
                key = get_id_value(mid)
                use_counts[key] = use_counts.get(key, 0) + 1
        except Exception:
            pass

    for t in DB.FilteredElementCollector(doc).WhereElementIsElementType().ToElements():
        try:
            for mid in t.GetMaterialIds(False):
                key = get_id_value(mid)
                use_counts[key] = use_counts.get(key, 0) + 1
        except Exception:
            pass

    mats = DB.FilteredElementCollector(doc).OfClass(DB.Material).ToElements()
    result = []
    for mat in mats:
        try:
            mid = get_id_value(mat.Id)
            cnt = use_counts.get(mid, 0)
            result.append({
                'id':        mat.Id,
                'name':      mat.Name or u'—',
                'class':     _mat_class(mat),
                'category':  _mat_category(mat),
                'use_count': cnt,
                'is_unused': cnt == 0,
                'material':  mat,
            })
        except Exception:
            pass

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
    with DB.Transaction(doc, u"NOSA — Material Manager — Delete Materials") as t:
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
    with io.open(path, 'w', encoding='utf-8-sig', newline='') as f:
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
    pairs = [(m.Id, m.Name or u'—') for m in mats]
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
        pass
    try:
        param = el.get_Parameter(DB.BuiltInParameter.SCHEDULE_LEVEL_PARAM)
        if param:
            return param.AsValueString() or u'—'
    except Exception:
        pass
    return u'—'


def _cat_name(el):
    try:
        return el.Category.Name if el.Category else u'—'
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
                    return mat_id, mat.Name
    except Exception:
        pass
    try:
        ids = list(el.GetMaterialIds(False))
        if ids:
            mat = doc.GetElement(ids[0])
            if mat:
                return ids[0], mat.Name
    except Exception:
        pass
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


def collect_element_materials(doc):
    """
    Scan structural elements for material assignments.
    Returns list of dicts sorted by (category, level, type_name):
      { 'id', 'category', 'level', 'type_name',
        'material_id', 'material_name', 'is_missing',
        'proposed_id', 'proposed_name' }
    """
    mat_list = get_all_materials(doc)
    result = []

    for bic in _struct_bics():
        try:
            els = DB.FilteredElementCollector(doc)\
                    .OfCategory(bic)\
                    .WhereElementIsNotElementType()\
                    .ToElements()
        except Exception:
            continue
        for el in els:
            try:
                el_type   = doc.GetElement(el.GetTypeId())
                type_name = el_type.Name if el_type else u'—'
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
                pass

    result.sort(key=lambda r: (r['category'], r['level'], r['type_name']))
    return result


def assign_material_to_elements(doc, element_ids, material_id):
    """
    Assign material_id to each element_id via STRUCTURAL_MATERIAL_PARAM,
    falling back to MATERIAL_ID_PARAM. Returns (ok_count, failed_count).
    """
    ok = failed = 0
    with DB.Transaction(doc, u"NOSA — Material Manager — Assign Material") as t:
        t.Start()
        for eid in element_ids:
            try:
                el = doc.GetElement(eid)
                if el is None:
                    failed += 1
                    continue
                assigned = False
                p = el.get_Parameter(DB.BuiltInParameter.STRUCTURAL_MATERIAL_PARAM)
                if p and not p.IsReadOnly:
                    p.Set(material_id)
                    assigned = True
                if not assigned:
                    p2 = el.get_Parameter(DB.BuiltInParameter.MATERIAL_ID_PARAM)
                    if p2 and not p2.IsReadOnly:
                        p2.Set(material_id)
                        assigned = True
                if assigned:
                    ok += 1
                else:
                    failed += 1
            except Exception:
                failed += 1
        t.Commit()
    return ok, failed


def export_element_materials_csv(rows, path):
    with io.open(path, 'w', encoding='utf-8-sig', newline='') as f:
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



