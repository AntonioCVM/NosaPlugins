# -*- coding: utf-8 -*-
"""
PilecapLoadChecker Logic — rule-based geometric consistency checks for pilecaps.
Supports phase filters, element-type selection, and editable rules (JSON-persisted).
"""
import math
import json
import os
from pyrevit import DB

_FT_TO_MM = 304.8
_RULES_FILE = os.path.join(os.path.dirname(__file__), 'pilecap_rules.json')

_DEFAULT_RULES = {
    'min_pile_spacing_diameters':  3.0,
    'min_edge_distance_diameters': 1.5,
    'max_cap_aspect_ratio':        2.5,
    'min_cap_depth_mm':            600,
    'min_cutoff_embedment_mm':     75,
}


def load_rules():
    """Load rules from JSON, falling back to defaults for missing keys."""
    try:
        if os.path.exists(_RULES_FILE):
            with open(_RULES_FILE, 'r') as f:
                data = json.load(f)
            rules = dict(_DEFAULT_RULES)
            rules.update({k: v for k, v in data.items() if k in _DEFAULT_RULES})
            return rules
    except Exception:
        pass
    return dict(_DEFAULT_RULES)


def save_rules(rules):
    """Persist rules dict to JSON. Returns True on success."""
    try:
        with open(_RULES_FILE, 'w') as f:
            json.dump(rules, f, indent=2)
        return True
    except Exception:
        return False


def get_phases(doc):
    """Return list of {id, name} for each phase in the document."""
    phases = []
    try:
        for ph in doc.Phases:
            try:
                pid = ph.Id.Value if hasattr(ph.Id, 'Value') else ph.Id.IntegerValue
                phases.append({'id': pid, 'name': ph.Name})
            except Exception:
                pass
    except Exception:
        pass
    return phases


# ── helpers ──────────────────────────────────────────────────────────────────

def _get_id(eid):
    if hasattr(eid, 'Value'):        return eid.Value
    if hasattr(eid, 'IntegerValue'): return eid.IntegerValue
    return int(str(eid))


def _ft(mm): return mm / _FT_TO_MM


def _bbox_dims(el):
    try:
        bb = el.get_BoundingBox(None)
        if not bb:
            return None
        w = abs(bb.Max.X - bb.Min.X) * _FT_TO_MM
        d = abs(bb.Max.Y - bb.Min.Y) * _FT_TO_MM
        h = abs(bb.Max.Z - bb.Min.Z) * _FT_TO_MM
        return {'w': w, 'd': d, 'h': h, 'bb': bb}
    except Exception:
        return None


def _pile_diameter_mm(pile):
    try:
        bb = pile.get_BoundingBox(None)
        if not bb:
            return 300.0
        dia = min(abs(bb.Max.X - bb.Min.X), abs(bb.Max.Y - bb.Min.Y)) * _FT_TO_MM
        return max(dia, 100.0)
    except Exception:
        return 300.0


def _pile_location(pile):
    try:
        if isinstance(pile.Location, DB.LocationPoint):
            pt = pile.Location.Point
            return (pt.X, pt.Y)
    except Exception:
        pass
    return None


def _element_phase_id(el):
    """Return integer phase-created ID, or None."""
    try:
        p = el.get_Parameter(DB.BuiltInParameter.PHASE_CREATED)
        if p:
            eid = p.AsElementId()
            if eid != DB.ElementId.InvalidElementId:
                return _get_id(eid)
    except Exception:
        pass
    return None


def _piles_on_pilecap(doc, pilecap):
    """Find piles spatially grouped with this pilecap."""
    try:
        bb = pilecap.get_BoundingBox(None)
        if not bb:
            return []
        margin = _ft(500)
        outline = DB.Outline(
            DB.XYZ(bb.Min.X - margin, bb.Min.Y - margin, bb.Min.Z - 5),
            DB.XYZ(bb.Max.X + margin, bb.Max.Y + margin, bb.Max.Z + 5),
        )
        bbf   = DB.BoundingBoxIntersectsFilter(outline)
        piles = list(
            DB.FilteredElementCollector(doc)
              .OfCategory(DB.BuiltInCategory.OST_StructuralFoundation)
              .WherePasses(bbf)
              .WhereElementIsNotElementType()
              .ToElements()
        )
        return [p for p in piles
                if _get_id(p.Id) != _get_id(pilecap.Id)
                and isinstance(p.Location, DB.LocationPoint)]
    except Exception:
        return []


# ── geometric checks ──────────────────────────────────────────────────────────

def _check_single_element(doc, el, rules):
    """Run all geometric rule checks on one element; return list of issue dicts."""
    issues = []
    dims = _bbox_dims(el)
    if not dims:
        return issues

    # Depth
    if dims['h'] < rules['min_cap_depth_mm']:
        issues.append({
            'check': 'Min depth',
            'value': '{:.0f} mm'.format(dims['h']),
            'limit': '>= {} mm'.format(rules['min_cap_depth_mm']),
            'severity': 'High',
        })

    # Aspect ratio
    if dims['w'] > 0 and dims['d'] > 0:
        ar = max(dims['w'], dims['d']) / min(dims['w'], dims['d'])
        if ar > rules['max_cap_aspect_ratio']:
            issues.append({
                'check': 'Aspect ratio',
                'value': '{:.1f}'.format(ar),
                'limit': '<= {}'.format(rules['max_cap_aspect_ratio']),
                'severity': 'Medium',
            })

    piles = _piles_on_pilecap(doc, el)
    if not piles:
        return issues

    diam        = _pile_diameter_mm(piles[0])
    min_spacing = diam * rules['min_pile_spacing_diameters']
    locs        = [_pile_location(p) for p in piles if _pile_location(p)]

    # Pile spacing
    spacing_fail = False
    for i in range(len(locs)):
        for j in range(i + 1, len(locs)):
            dx = (locs[i][0] - locs[j][0]) * _FT_TO_MM
            dy = (locs[i][1] - locs[j][1]) * _FT_TO_MM
            spacing = math.sqrt(dx * dx + dy * dy)
            if spacing < min_spacing:
                issues.append({
                    'check': 'Pile spacing',
                    'value': '{:.0f} mm'.format(spacing),
                    'limit': '>= {:.0f} mm ({:.0f}xD)'.format(
                        min_spacing, rules['min_pile_spacing_diameters']),
                    'severity': 'High',
                })
                spacing_fail = True
                break
        if spacing_fail:
            break

    # Edge distance
    min_edge = diam * rules['min_edge_distance_diameters']
    try:
        bb = dims['bb']
        if bb and locs:
            half_w = abs(bb.Max.X - bb.Min.X) / 2.0
            half_d = abs(bb.Max.Y - bb.Min.Y) / 2.0
            cx     = (bb.Min.X + bb.Max.X) / 2.0
            cy     = (bb.Min.Y + bb.Max.Y) / 2.0
            for loc in locs:
                ex        = (half_w - abs(loc[0] - cx)) * _FT_TO_MM
                ey        = (half_d - abs(loc[1] - cy)) * _FT_TO_MM
                edge_dist = min(ex, ey)
                if edge_dist < min_edge:
                    issues.append({
                        'check': 'Edge distance',
                        'value': '{:.0f} mm'.format(edge_dist),
                        'limit': '>= {:.0f} mm ({:.1f}xD)'.format(
                            min_edge, rules['min_edge_distance_diameters']),
                        'severity': 'High',
                    })
                    break
    except Exception:
        pass

    return issues


# ── main entry ────────────────────────────────────────────────────────────────

def check_all_pilecaps(doc, phase_id=None, selected_bics=None, rules=None):
    """
    Run pilecap checks.

    phase_id     : int or None — skip elements created in this phase.
    selected_bics: set/list of strings {'caps', 'strips', 'walls'}.
                   Default: {'caps'} (isolated pilecaps only).
    rules        : dict of rule overrides; None -> load from JSON.
    """
    if rules is None:
        rules = load_rules()
    if selected_bics is None:
        selected_bics = {'caps'}
    else:
        selected_bics = set(selected_bics)

    results = []

    # Isolated pilecaps (LocationPoint, not pile-like)
    if 'caps' in selected_bics:
        foundations = list(
            DB.FilteredElementCollector(doc)
              .OfCategory(DB.BuiltInCategory.OST_StructuralFoundation)
              .WhereElementIsNotElementType()
              .ToElements()
        )
        for el in foundations:
            try:
                if phase_id is not None and _element_phase_id(el) == phase_id:
                    continue
                if not isinstance(el.Location, DB.LocationPoint):
                    continue
                dims = _bbox_dims(el)
                if dims:
                    plan_size = max(dims['w'], dims['d'])
                    if dims['h'] > 0 and plan_size > 0 and dims['h'] / plan_size > 4.0:
                        continue
                    if plan_size < 200:
                        continue
                issues = _check_single_element(doc, el, rules)
                piles  = _piles_on_pilecap(doc, el)
                try:
                    cap_name = getattr(el, 'Name', str(el.Id))
                except Exception:
                    cap_name = str(el.Id)
                results.append({
                    'id': _get_id(el.Id), 'name': cap_name,
                    'pile_count': len(piles), 'issues': issues,
                    'status': 'FAIL' if issues else 'OK',
                    'type': 'Cap',
                })
            except Exception:
                pass

    # Strip foundations (LocationCurve)
    if 'strips' in selected_bics:
        foundations = list(
            DB.FilteredElementCollector(doc)
              .OfCategory(DB.BuiltInCategory.OST_StructuralFoundation)
              .WhereElementIsNotElementType()
              .ToElements()
        )
        for el in foundations:
            try:
                if phase_id is not None and _element_phase_id(el) == phase_id:
                    continue
                if not isinstance(el.Location, DB.LocationCurve):
                    continue
                issues = _check_single_element(doc, el, rules)
                try:
                    el_name = getattr(el, 'Name', str(el.Id))
                except Exception:
                    el_name = str(el.Id)
                results.append({
                    'id': _get_id(el.Id), 'name': el_name,
                    'pile_count': 0, 'issues': issues,
                    'status': 'FAIL' if issues else 'OK',
                    'type': 'Strip',
                })
            except Exception:
                pass

    # Retaining walls (OST_Walls)
    if 'walls' in selected_bics:
        walls = list(
            DB.FilteredElementCollector(doc)
              .OfCategory(DB.BuiltInCategory.OST_Walls)
              .WhereElementIsNotElementType()
              .ToElements()
        )
        for el in walls:
            try:
                if phase_id is not None and _element_phase_id(el) == phase_id:
                    continue
                issues = _check_single_element(doc, el, rules)
                try:
                    el_name = getattr(el, 'Name', str(el.Id))
                except Exception:
                    el_name = str(el.Id)
                results.append({
                    'id': _get_id(el.Id), 'name': el_name,
                    'pile_count': 0, 'issues': issues,
                    'status': 'FAIL' if issues else 'OK',
                    'type': 'Wall',
                })
            except Exception:
                pass

    ok   = sum(1 for r in results if r['status'] == 'OK')
    fail = sum(1 for r in results if r['status'] == 'FAIL')
    return {'results': results, 'total': len(results), 'ok': ok, 'fail': fail}


# ── parameter editor ──────────────────────────────────────────────────────────

def get_editable_params(doc, cap_id):
    """
    Return list of {name, value, bip_or_name, unit} for editable geometric
    parameters of the pilecap element identified by cap_id.

    Tries known BuiltInParameters first, then LookupParameter by common names.
    All length values are converted to mm for display.
    """
    results = []
    try:
        el = doc.GetElement(DB.ElementId(int(cap_id)))
        if el is None:
            return results

        seen = set()

        # BuiltInParameter candidates (lengths stored in feet)
        bip_candidates = [
            ('Thickness',   DB.BuiltInParameter.STRUCTURAL_FOUNDATION_THICKNESS),
            ('Width',       DB.BuiltInParameter.STRUCTURAL_BEAM_WIDTH_PARAM),
            ('Depth',       DB.BuiltInParameter.STRUCTURAL_BEAM_DEPTH_PARAM),
        ]
        for label, bip in bip_candidates:
            try:
                p = el.get_Parameter(bip)
                if p and not p.IsReadOnly and p.StorageType == DB.StorageType.Double:
                    val_mm = round(p.AsDouble() * _FT_TO_MM, 1)
                    results.append({'name': label, 'value': val_mm,
                                    'bip_or_name': bip, 'unit': 'mm'})
                    seen.add(label)
            except Exception:
                pass

        # LookupParameter candidates
        name_candidates = [
            'Width', 'Length', 'Thickness', 'Depth', 'b', 'h', 'Cover',
            'Pile Cap Depth', 'Cap Thickness', 'Founding Depth',
        ]
        for pname in name_candidates:
            if pname in seen:
                continue
            try:
                p = el.LookupParameter(pname)
                if p and not p.IsReadOnly and p.StorageType == DB.StorageType.Double:
                    val_mm = round(p.AsDouble() * _FT_TO_MM, 1)
                    results.append({'name': pname, 'value': val_mm,
                                    'bip_or_name': pname, 'unit': 'mm'})
                    seen.add(pname)
            except Exception:
                pass

    except Exception:
        pass
    return results
