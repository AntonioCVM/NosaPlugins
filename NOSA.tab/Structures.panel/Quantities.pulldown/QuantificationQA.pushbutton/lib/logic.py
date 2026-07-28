# -*- coding: utf-8 -*-
"""
QuantificationQA Logic — Concrete, Steel & Rebar Quantities + QA checks
Extracts volumes, areas, rebar counts by category, material and level.
Detects missing materials, volume outliers, zero-volume elements.
"""
import math
from Autodesk.Revit import DB
from nosa_utils.revit_helpers import get_id_value
# ─────────────────────────────────────────────────
# Category lists
# ─────────────────────────────────────────────────

def _concrete_bics():
    return [
        ('Structural Columns',     DB.BuiltInCategory.OST_StructuralColumns),
        ('Structural Framing',     DB.BuiltInCategory.OST_StructuralFraming),
        ('Structural Foundations', DB.BuiltInCategory.OST_StructuralFoundation),
        ('Floors',                 DB.BuiltInCategory.OST_Floors),
        ('Walls',                  DB.BuiltInCategory.OST_Walls),
    ]

def _steel_bics():
    return [
        ('Steel Columns',  DB.BuiltInCategory.OST_StructuralColumns),
        ('Steel Framing',  DB.BuiltInCategory.OST_StructuralFraming),
    ]

def _rebar_bic():
    return DB.BuiltInCategory.OST_Rebar

# ─────────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────────

STEEL_DENSITY_KGM3  = 7850.0
REBAR_DENSITY_KGM3  = 7850.0
_FT3_TO_M3          = 0.0283168
_FT2_TO_M2          = 0.0929030
_FT_TO_M            = 0.3048


# ─────────────────────────────────────────────────
# Internal helpers
# ─────────────────────────────────────────────────



def _collect(doc, bic):
    return list(
        DB.FilteredElementCollector(doc)
          .OfCategory(bic)
          .WhereElementIsNotElementType()
          .ToElements()
    )


def _level_name(doc, el):
    try:
        lid = el.LevelId
        if lid and lid != DB.ElementId.InvalidElementId:
            lv = doc.GetElement(lid)
            if lv: return lv.Name
    except Exception:
        pass
    try:
        p = el.get_Parameter(DB.BuiltInParameter.FAMILY_LEVEL_PARAM)
        if p:
            lv = doc.GetElement(p.AsElementId())
            if lv: return lv.Name
    except Exception:
        pass
    return 'No Level'


def _volume_m3(el):
    try:
        p = el.get_Parameter(DB.BuiltInParameter.HOST_VOLUME_COMPUTED)
        if p and p.AsDouble() > 0:
            return p.AsDouble() * _FT3_TO_M3
    except Exception:
        pass
    # Geometric fallback: parameter missing or zero — sum solid volumes directly
    try:
        from nosa_utils.solids import total_volume
        v = total_volume(el)
        if v > 0:
            return v * _FT3_TO_M3
    except Exception:
        pass
    return 0.0


def _area_m2(el):
    try:
        p = el.get_Parameter(DB.BuiltInParameter.HOST_AREA_COMPUTED)
        if p and p.AsDouble() > 0:
            return p.AsDouble() * _FT2_TO_M2
    except Exception:
        pass
    return 0.0


def _has_material(el):
    try:
        p = el.get_Parameter(DB.BuiltInParameter.STRUCTURAL_MATERIAL_PARAM)
        if p and p.AsElementId() != DB.ElementId.InvalidElementId:
            return True
        mids = list(el.GetMaterialIds(False)) if hasattr(el, 'GetMaterialIds') else []
        return bool(mids)
    except Exception:
        return False


def _is_existing_phase(doc, el):
    """Return True if element was created in an Existing/Demolition phase."""
    try:
        phase_id = el.CreatedPhaseId
        if phase_id and phase_id != DB.ElementId.InvalidElementId:
            phase = doc.GetElement(phase_id)
            if phase:
                name = phase.Name.lower()
                return ('existing' in name or 'existente' in name
                        or 'demol' in name or 'exist' in name)
    except Exception:
        pass
    return False


def _is_pile_family(el):
    """Return True if element looks like a pile based on family name keywords."""
    try:
        name = el.Symbol.Family.Name.lower()
        return ('pile' in name or 'pilote' in name or 'pilotis' in name
                or 'pila' in name or 'micro' in name)
    except Exception:
        return False


def _get_family_name(el):
    """Return family name of element."""
    try:
        return el.Symbol.Family.Name
    except Exception:
        pass
    try:
        return el.Name or ''
    except Exception:
        return ''


def _get_element_material_name(doc, el):
    """Return the material name of the first assigned material, or empty string."""
    try:
        p = el.get_Parameter(DB.BuiltInParameter.STRUCTURAL_MATERIAL_PARAM)
        if p and p.AsElementId() != DB.ElementId.InvalidElementId:
            mat = doc.GetElement(p.AsElementId())
            if mat:
                return mat.Name
    except Exception:
        pass
    try:
        mids = list(el.GetMaterialIds(False)) if hasattr(el, 'GetMaterialIds') else []
        if mids:
            mat = doc.GetElement(mids[0])
            if mat:
                return mat.Name
    except Exception:
        pass
    return ''


def _element_is_steel(doc, el):
    """Return True if element has a material with 'steel' / 'acero' in name."""
    name = _get_element_material_name(doc, el).lower()
    return 'steel' in name or 'acero' in name


# ─────────────────────────────────────────────────
# Concrete quantities
# ─────────────────────────────────────────────────

def collect_concrete_quantities_v2(doc, selected_cats=None, selected_levels=None,
                                    excluded_families=None, exclude_existing_phase=False,
                                    exclude_piles=False):
    """
    Collect concrete element quantities.
    excluded_families: set of family names to skip.
    exclude_existing_phase: skip elements created in Existing/Demolition phase.
    exclude_piles: skip elements identified as piles by family name keywords.
    """
    excluded = set(excluded_families) if excluded_families else set()
    rows = []
    for cat_name, bic in _concrete_bics():
        if selected_cats and cat_name not in selected_cats:
            continue
        for el in _collect(doc, bic):
            try:
                if exclude_existing_phase and _is_existing_phase(doc, el):
                    continue
                fam_name = _get_family_name(el)
                if excluded and fam_name in excluded:
                    continue
                if exclude_piles and _is_pile_family(el):
                    continue
                level = _level_name(doc, el)
                if selected_levels and level not in selected_levels:
                    continue
                mat_name = _get_element_material_name(doc, el)
                rows.append({
                    'id':            get_id_value(el.Id),
                    'name':          getattr(el, 'Name', str(el.Id)),
                    'category':      cat_name,
                    'level':         level,
                    'material_name': mat_name,
                    'volume_m3':     round(_volume_m3(el), 4),
                    'area_m2':       round(_area_m2(el), 3),
                    'has_material':  bool(mat_name),
                })
            except Exception:
                pass
    return rows


def collect_steel_quantities(doc, excluded_families=None, exclude_existing_phase=False):
    """
    Collect structural elements with steel material.
    Returns list of {id, name, category, level, material_name, weight_kg, area_m2}.
    weight_kg is calculated from volume × STEEL_DENSITY_KGM3.
    """
    excluded = set(excluded_families) if excluded_families else set()
    rows = []
    seen_ids = set()
    for cat_name, bic in _steel_bics():
        for el in _collect(doc, bic):
            try:
                el_id = get_id_value(el.Id)
                if el_id in seen_ids:
                    continue
                if exclude_existing_phase and _is_existing_phase(doc, el):
                    continue
                if not _element_is_steel(doc, el):
                    continue
                fam_name = _get_family_name(el)
                if excluded and fam_name in excluded:
                    continue
                level    = _level_name(doc, el)
                mat_name = _get_element_material_name(doc, el)
                vol_m3   = _volume_m3(el)
                weight   = round(vol_m3 * STEEL_DENSITY_KGM3, 1)
                rows.append({
                    'id':            el_id,
                    'name':          getattr(el, 'Name', str(el.Id)),
                    'category':      cat_name,
                    'level':         level,
                    'material_name': mat_name,
                    'weight_kg':     weight,
                    'area_m2':       round(_area_m2(el), 3),
                })
                seen_ids.add(el_id)
            except Exception:
                pass
    return rows


# ─────────────────────────────────────────────────
# Aggregation helpers
# ─────────────────────────────────────────────────

def aggregate_concrete_v2(rows):
    """Group by (category, material, level), returns volume and area totals."""
    agg = {}
    for r in rows:
        key = (r['category'], r.get('material_name', ''), r['level'])
        if key not in agg:
            agg[key] = {
                'category': r['category'],
                'material': r.get('material_name', ''),
                'level':    r['level'],
                'volume_m3': 0.0, 'area_m2': 0.0, 'count': 0,
            }
        agg[key]['volume_m3'] += r['volume_m3']
        agg[key]['area_m2']   += r['area_m2']
        agg[key]['count']     += 1
    result = sorted(agg.values(), key=lambda x: (x['level'], x['category'], x['material']))
    for row in result:
        row['volume_m3'] = round(row['volume_m3'], 3)
        row['area_m2']   = round(row['area_m2'], 2)
    return result


def aggregate_steel(rows):
    """Group steel rows by (category, material, level), compute weight_kg and weight_t."""
    agg = {}
    for r in rows:
        key = (r['category'], r.get('material_name', ''), r['level'])
        if key not in agg:
            agg[key] = {
                'category': r['category'],
                'material': r.get('material_name', ''),
                'level':    r['level'],
                'weight_kg': 0.0, 'area_m2': 0.0, 'count': 0,
            }
        agg[key]['weight_kg'] += r.get('weight_kg', 0.0)
        agg[key]['area_m2']   += r.get('area_m2', 0.0)
        agg[key]['count']     += 1
    result = sorted(agg.values(), key=lambda x: (x['level'], x['category'], x['material']))
    for row in result:
        row['weight_kg'] = round(row['weight_kg'], 1)
        row['weight_t']  = round(row['weight_kg'] / 1000.0, 3)
        row['area_m2']   = round(row['area_m2'], 2)
    return result


# ─────────────────────────────────────────────────
# Rebar quantities
# ─────────────────────────────────────────────────

def collect_rebar_quantities(doc, selected_levels=None):
    """Returns list of rebar element dicts {level, diam_mm, length_m}."""
    rows = []
    for el in _collect(doc, _rebar_bic()):
        try:
            level = _level_name(doc, el)
            if selected_levels and level not in selected_levels:
                continue
            diam_mm = 0.0
            p_diam = el.get_Parameter(DB.BuiltInParameter.REBAR_BAR_DIAMETER)
            if p_diam:
                diam_mm = round(p_diam.AsDouble() * 304.8, 1)
            length_m = 0.0
            p_len = el.get_Parameter(DB.BuiltInParameter.CURVE_ELEM_LENGTH)
            if p_len:
                length_m = round(p_len.AsDouble() * _FT_TO_M, 3)
            rows.append({
                'id':       get_id_value(el.Id),
                'level':    level,
                'diam_mm':  diam_mm,
                'length_m': length_m,
            })
        except Exception:
            pass
    return rows


def aggregate_rebar(rows):
    """Group by level+diameter, include weight_kg from linear density."""
    agg = {}
    for r in rows:
        key = (r['level'], r['diam_mm'])
        if key not in agg:
            agg[key] = {'level': r['level'], 'diam_mm': r['diam_mm'],
                        'count': 0, 'total_length_m': 0.0}
        agg[key]['count']          += 1
        agg[key]['total_length_m'] += r['length_m']
    result = sorted(agg.values(), key=lambda x: (x['level'], x['diam_mm']))
    for row in result:
        row['total_length_m'] = round(row['total_length_m'], 2)
        d_m = row['diam_mm'] / 1000.0
        linear_kg_per_m = (math.pi / 4.0) * d_m * d_m * REBAR_DENSITY_KGM3
        row['weight_kg'] = round(row['total_length_m'] * linear_kg_per_m, 1)
    return result


# ─────────────────────────────────────────────────
# Family names helper
# ─────────────────────────────────────────────────

def get_all_family_names(doc):
    """Return sorted list of distinct family names from all structural elements."""
    names = set()
    all_bics = list(_concrete_bics()) + [b for b in _steel_bics() if b not in _concrete_bics()]
    for _, bic in all_bics:
        try:
            for el in _collect(doc, bic):
                try:
                    n = _get_family_name(el)
                    if n:
                        names.add(n)
                except Exception:
                    pass
        except Exception:
            pass
    return sorted(names)


# ─────────────────────────────────────────────────
# QA checks
# ─────────────────────────────────────────────────

def check_qa_issues(concrete_rows, outlier_sigma=2.5):
    """
    Returns list of QA issues:
      - Missing material
      - Zero volume
      - Statistical volume outliers per category
    """
    issues = []

    for r in concrete_rows:
        if not r['has_material']:
            issues.append({
                'id': r['id'], 'category': r['category'], 'level': r['level'],
                'name': r['name'], 'problem': 'No material assigned', 'severity': 'High',
            })

    for r in concrete_rows:
        if r['volume_m3'] == 0.0:
            issues.append({
                'id': r['id'], 'category': r['category'], 'level': r['level'],
                'name': r['name'], 'problem': 'Zero volume — check element geometry',
                'severity': 'Medium',
            })

    from collections import defaultdict
    by_cat = defaultdict(list)
    for r in concrete_rows:
        if r['volume_m3'] > 0:
            by_cat[r['category']].append(r)

    for cat, cat_rows in by_cat.items():
        if len(cat_rows) < 4:
            continue
        vols = [r['volume_m3'] for r in cat_rows]
        mean = sum(vols) / len(vols)
        std  = math.sqrt(sum((v - mean)**2 for v in vols) / len(vols))
        if std < 1e-6:
            continue
        for r in cat_rows:
            z = abs(r['volume_m3'] - mean) / std
            if z > outlier_sigma:
                issues.append({
                    'id': r['id'], 'category': r['category'], 'level': r['level'],
                    'name': r['name'],
                    'problem': 'Volume outlier ({:.2f} m³, z={:.1f})'.format(r['volume_m3'], z),
                    'severity': 'Medium',
                })

    _order = {'High': 0, 'Medium': 1, 'Low': 2}
    issues.sort(key=lambda x: (_order.get(x['severity'], 9), x['category'], x['level']))
    return issues


# ─────────────────────────────────────────────────
# Available levels / categories helpers
# ─────────────────────────────────────────────────

def get_available_levels(doc):
    levels = DB.FilteredElementCollector(doc).OfClass(DB.Level).ToElements()
    return sorted([l.Name for l in levels])


def get_available_categories():
    return [n for n, _ in _concrete_bics()]


# ─────────────────────────────────────────────────
# Main entry
# ─────────────────────────────────────────────────

def run_all(doc, selected_cats=None, selected_levels=None, excluded_families=None,
            exclude_existing_phase=False, exclude_piles=False):
    concrete = collect_concrete_quantities_v2(
        doc, selected_cats, selected_levels, excluded_families,
        exclude_existing_phase=exclude_existing_phase,
        exclude_piles=exclude_piles,
    )
    steel = collect_steel_quantities(doc, excluded_families,
                                     exclude_existing_phase=exclude_existing_phase)
    rebar    = collect_rebar_quantities(doc, selected_levels)
    agg_con  = aggregate_concrete_v2(concrete)
    agg_ste  = aggregate_steel(steel)
    agg_reb  = aggregate_rebar(rebar)
    qa       = check_qa_issues(concrete)

    totals = {
        'volume_m3':      round(sum(r['volume_m3']         for r in concrete), 3),
        'area_m2':        round(sum(r['area_m2']           for r in concrete), 2),
        'elements':       len(concrete),
        'steel_kg':       round(sum(r.get('weight_kg', 0)  for r in steel),    1),
        'rebar_kg':       round(sum(r.get('weight_kg', 0)  for r in agg_reb),  1),
        'rebar_count':    len(rebar),
        'rebar_length_m': round(sum(r['length_m']          for r in rebar),    1),
        'qa_issues':      len(qa),
    }

    return {
        'concrete_rows': concrete,
        'steel_rows':    steel,
        'rebar_rows':    rebar,
        'agg_concrete':  agg_con,
        'agg_steel':     agg_ste,
        'agg_rebar':     agg_reb,
        'qa_issues':     qa,
        'totals':        totals,
    }


