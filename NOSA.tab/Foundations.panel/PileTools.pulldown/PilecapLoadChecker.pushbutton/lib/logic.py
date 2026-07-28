# -*- coding: utf-8 -*-
"""
PilecapLoadChecker Logic — rule-based geometric consistency checks for pilecaps.
Supports phase filters, element-type selection, and editable rules (JSON-persisted).
"""
import math
import json
import os
from Autodesk.Revit import DB
from nosa_utils.revit_helpers import get_id_value
from nosa_utils import geometry as _geometry
from nosa_utils import unit_conversion as _uc10
_FT_TO_MM = _uc10.FT_TO_MM
_RULES_FILE = os.path.join(os.path.dirname(__file__), 'pilecap_rules.json')

_DEFAULT_RULES = {
    'min_pile_spacing_diameters':  3.0,
    'min_edge_distance_diameters': 1.5,
    'max_cap_aspect_ratio':        2.5,
    'min_cap_depth_mm':            600,
    'min_cutoff_embedment_mm':     75,
    'pile_bearing_capacity_kN':    2000.0,  # single-pile bearing capacity for load check
}

# ── Analytical load constants ─────────────────────────────────────────────────
_FT2KN    = _uc10.FT_TO_M * 4.44822   # ft·lbf → kN
_FTLB2KNM = _FT2KN * _uc10.FT_TO_M    # ft·lbf → kN·m


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
                pid = get_id_value(ph.Id)
                phases.append({'id': pid, 'name': ph.Name})
            except Exception:
                pass
    except Exception:
        pass
    return phases


# ── helpers ──────────────────────────────────────────────────────────────────



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
                return get_id_value(eid)
    except Exception:
        pass
    return None


def _piles_on_pilecap(pilecap, foundations):
    """
    Find piles spatially grouped with this pilecap, filtering a pre-collected
    foundations list by bounding-box proximity — avoids re-running a
    FilteredElementCollector over the whole category once per pilecap
    (previously O(N_pilecaps x N_foundations) collector creations).
    """
    try:
        bb = pilecap.get_BoundingBox(None)
        if not bb:
            return []
        margin = _ft(500)
        cap_id = get_id_value(pilecap.Id)
        result = []
        for p in foundations:
            if get_id_value(p.Id) == cap_id:
                continue
            if not isinstance(p.Location, DB.LocationPoint):
                continue
            pbb = p.get_BoundingBox(None)
            if pbb and _geometry.bboxes_overlap(bb, pbb, margin):
                result.append(p)
        return result
    except Exception:
        return []


# ── analytical loads ─────────────────────────────────────────────────────────

def get_analytical_loads(doc, el):
    """
    Extract governing reactions (N, Mx, My) from the element's analytical model.
    Returns dict with keys 'N_kN', 'Mx_kNm', 'My_kNm' (float or None).
    """
    def _try():
        am = None
        try:
            am = DB.Structure.AnalyticalModelStick.GetAnalyticalModelStick(el)
        except Exception:
            pass
        if am is None:
            try: am = el.GetAnalyticalModel()
            except Exception: pass
        if am is None:
            return None
        bcs = None
        try: bcs = list(am.GetAnalyticalModelBoundaryConditions())
        except Exception: pass
        if not bcs:
            return None
        reactions = []
        for bc in bcs:
            try:
                r = bc.GetReactions()
                reactions.append({
                    'N':  r.Force.Z  * _FT2KN,
                    'Vx': r.Force.X  * _FT2KN,
                    'Vy': r.Force.Y  * _FT2KN,
                    'Mx': r.Moment.X * _FTLB2KNM,
                    'My': r.Moment.Y * _FTLB2KNM,
                })
            except Exception:
                pass
        if not reactions:
            return None
        gov = max(reactions, key=lambda r: abs(r.get('N', 0) or 0))
        return gov
    try:
        return _try()
    except Exception:
        return None


def _load_semaphore(N_kN, capacity_kN, pile_count):
    """Return utilisation ratio and semaphore string for load check."""
    if N_kN is None or capacity_kN <= 0 or pile_count <= 0:
        return None, u'—'
    total_cap = capacity_kN * pile_count
    ratio = abs(N_kN) / total_cap
    if ratio <= 0.75:
        sem = u'OK'
    elif ratio <= 1.0:
        sem = u'WARNING'
    else:
        sem = u'FAIL'
    return round(ratio, 2), sem


# ── geometric checks ──────────────────────────────────────────────────────────

def _check_single_element(el, rules, piles):
    """
    Run all geometric rule checks on one element; return list of issue dicts.
    piles: pre-computed list from _piles_on_pilecap (may be empty for
    strips/walls where no nearby piles were found).
    """
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

    # Foundations collected once and shared between 'caps' and 'strips'
    # (previously each branch ran its own identical collector over the
    # whole category — same list, queried twice).
    foundations = []
    if selected_bics & {'caps', 'strips', 'walls'}:
        foundations = list(
            DB.FilteredElementCollector(doc)
              .OfCategory(DB.BuiltInCategory.OST_StructuralFoundation)
              .WhereElementIsNotElementType()
              .ToElements()
        )

    # Isolated pilecaps (LocationPoint, not pile-like)
    if 'caps' in selected_bics:
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
                piles  = _piles_on_pilecap(el, foundations)
                issues = _check_single_element(el, rules, piles)
                try:
                    cap_name = getattr(el, 'Name', str(el.Id))
                except Exception:
                    cap_name = str(el.Id)
                loads      = get_analytical_loads(doc, el)
                cap_kN     = rules.get('pile_bearing_capacity_kN', 2000.0)
                N_kN       = loads['N']  if loads else None
                Mx_kNm     = loads['Mx'] if loads else None
                My_kNm     = loads['My'] if loads else None
                util, sem  = _load_semaphore(N_kN, cap_kN, len(piles))
                results.append({
                    'id': get_id_value(el.Id), 'name': cap_name,
                    'pile_count': len(piles), 'issues': issues,
                    'status': 'FAIL' if issues else 'OK',
                    'type': 'Cap',
                    'N_kN': round(N_kN, 1) if N_kN is not None else None,
                    'Mx_kNm': round(Mx_kNm, 1) if Mx_kNm is not None else None,
                    'My_kNm': round(My_kNm, 1) if My_kNm is not None else None,
                    'util': util,
                    'semaphore': sem,
                })
            except Exception:
                pass

    # Strip foundations (LocationCurve)
    if 'strips' in selected_bics:
        for el in foundations:
            try:
                if phase_id is not None and _element_phase_id(el) == phase_id:
                    continue
                if not isinstance(el.Location, DB.LocationCurve):
                    continue
                piles  = _piles_on_pilecap(el, foundations)
                issues = _check_single_element(el, rules, piles)
                try:
                    el_name = getattr(el, 'Name', str(el.Id))
                except Exception:
                    el_name = str(el.Id)
                results.append({
                    'id': get_id_value(el.Id), 'name': el_name,
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
                piles  = _piles_on_pilecap(el, foundations)
                issues = _check_single_element(el, rules, piles)
                try:
                    el_name = getattr(el, 'Name', str(el.Id))
                except Exception:
                    el_name = str(el.Id)
                results.append({
                    'id': get_id_value(el.Id), 'name': el_name,
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
