# -*- coding: utf-8 -*-
"""
Rebar Auditor v1.0 — Logic

Checks per EC2 EN 1992-1-1:
  A: Cover (Table 4.4N + Δc_dev)
  B: Minimum rebar ratio ρ_min (§9)
  C: Maximum rebar ratio ρ_max (§9.2.1)
  D: Structural elements with no rebar
"""
import math
from Autodesk.Revit import DB
from nosa_utils.revit_helpers import get_id_value
from System import Int64

FT2MM = 304.8
MM2FT = 1.0 / 304.8

# ── EC2 EXPOSURE CLASS → min cover c_min,dur (mm) ─────────────────────────────
# EC2 Table 4.4N (structural class S4 default)
EC2_COVER = {
    'X0':   10,
    'XC1':  15,
    'XC2':  25,
    'XC3':  25,
    'XC4':  30,
    'XD1':  30,
    'XD2':  35,
    'XD3':  40,
    'XS1':  35,
    'XS2':  40,
    'XS3':  45,
    'XF1':  15,
    'XF2':  25,
    'XF3':  25,
    'XF4':  30,
    'XA1':  25,
    'XA2':  30,
    'XA3':  35,
}
EC2_DEV_MARGIN = 10   # Δc_dev default (mm) EC2 §4.4.1.3

# ── EC2 REBAR RATIO LIMITS ──────────────────────────────────────────────────────
# Simplified — assumes C25/30, B500 (fctm=2.6 MPa, fyk=500 MPa)
# ρ_min_beam  = max(0.26 × fctm/fyk, 0.0013) EC2 §9.2.1.1
# ρ_min_col   = 0.002  (As ≥ 0.2% Ac)  EC2 §9.5.2
# ρ_min_slab  = 0.0015 EC2 §9.3.1.1
# ρ_max_all   = 0.04   EC2 §9.2.1.1

def _rho_min_beam(fctm_mpa=2.6, fyk_mpa=500):
    return max(0.26 * fctm_mpa / fyk_mpa, 0.0013)

LIMITS = {
    'beam':   {'rho_min': _rho_min_beam(),   'rho_max': 0.04},
    'column': {'rho_min': 0.002,             'rho_max': 0.04},
    'slab':   {'rho_min': 0.0015,            'rho_max': 0.04},
    'wall':   {'rho_min': 0.002,             'rho_max': 0.04},
    'other':  {'rho_min': 0.0013,            'rho_max': 0.04},
}

# ── REVIT API HELPERS ──────────────────────────────────────────────────────────



def _param_double(el, bip, default=0.0):
    try:
        p = el.get_Parameter(bip)
        if p and p.HasValue:
            return p.AsDouble()
    except Exception:
        pass
    return default


def _param_int(el, bip, default=0):
    try:
        p = el.get_Parameter(bip)
        if p and p.HasValue:
            return p.AsInteger()
    except Exception:
        pass
    return default


def _collect(doc, cls):
    return list(DB.FilteredElementCollector(doc)
                .OfClass(cls)
                .WhereElementIsNotElementType()
                .ToElements())


def _collect_bic(doc, bic):
    return list(DB.FilteredElementCollector(doc)
                .OfCategory(bic)
                .WhereElementIsNotElementType()
                .ToElements())


# ── REBAR DATA ─────────────────────────────────────────────────────────────────

def _bar_diameter_mm(rebar, doc):
    """Bar diameter in mm from the rebar type."""
    try:
        # BarDiameter parameter on type
        rtype = doc.GetElement(rebar.GetTypeId())
        d = _param_double(rtype, DB.BuiltInParameter.REBAR_BAR_DIAMETER)
        if d > 0:
            return d * FT2MM
        # Fallback: look for instance parameter
        d = _param_double(rebar, DB.BuiltInParameter.REBAR_BAR_DIAMETER)
        if d > 0:
            return d * FT2MM
    except Exception:
        pass
    return 0.0


def _bar_count(rebar):
    """Total number of bar positions."""
    try:
        # Rebar.NumberOfBarPositions (IronPython accessible as property)
        return rebar.NumberOfBarPositions
    except Exception:
        try:
            n = _param_int(rebar, DB.BuiltInParameter.REBAR_NUMBER_OF_SETS)
            return max(n, 1)
        except Exception:
            return 1


def _cover_mm(rebar, doc):
    """
    Nominal cover of this rebar from the host's cover settings.
    Uses REBAR_COVER_CLEARANCE parameter on the rebar instance, which
    stores the clear distance in feet.
    """
    try:
        d = _param_double(rebar, DB.BuiltInParameter.REBAR_COVER_CLEARANCE)
        if d > 0:
            return d * FT2MM
    except Exception:
        pass
    # Try host element cover type
    try:
        host_id  = rebar.GetHostId()
        host     = doc.GetElement(host_id)
        cover_id = None
        for bip in [DB.BuiltInParameter.REBAR_COVER_TOP_EXTENSION,
                    DB.BuiltInParameter.REBAR_COVER_BOTTOM_EXTENSION,
                    DB.BuiltInParameter.REBAR_COVER_OTHER_EXTENSION]:
            p = host.get_Parameter(bip)
            if p and p.HasValue:
                cover_id = p.AsElementId()
                break
        if cover_id and get_id_value(cover_id) > 0:
            ctype = doc.GetElement(cover_id)
            if isinstance(ctype, DB.RebarCoverType):
                return ctype.CoverDistance * FT2MM
    except Exception:
        pass
    return None


def _host_section_area_mm2(host):
    """
    Gross cross-section area of the host element in mm².
    Uses bounding box or volume/length heuristic.
    """
    try:
        # Volume / length = A
        vol_ft3 = _param_double(host, DB.BuiltInParameter.HOST_VOLUME_COMPUTED)
        if vol_ft3 > 0:
            loc = host.Location
            if isinstance(loc, DB.LocationCurve):
                length_ft = loc.Curve.Length
                if length_ft > 0:
                    area_ft2 = vol_ft3 / length_ft
                    return area_ft2 * (FT2MM ** 2)
    except Exception:
        pass
    # Fallback: bounding box
    try:
        bb = host.get_BoundingBox(None)
        if bb:
            dx = (bb.Max.X - bb.Min.X) * FT2MM
            dy = (bb.Max.Y - bb.Min.Y) * FT2MM
            return dx * dy
    except Exception:
        pass
    return None


def _element_type_label(host):
    """Return 'beam', 'column', 'slab', 'wall', or 'other'."""
    try:
        cat = host.Category
        if cat is None:
            return 'other'
        bic = get_id_value(cat.Id)
        mapping = {
            int(DB.BuiltInCategory.OST_StructuralFraming):   'beam',
            int(DB.BuiltInCategory.OST_StructuralColumns):   'column',
            int(DB.BuiltInCategory.OST_Floors):              'slab',
            int(DB.BuiltInCategory.OST_Walls):               'wall',
            int(DB.BuiltInCategory.OST_StructuralFoundation):'other',
        }
        return mapping.get(bic, 'other')
    except Exception:
        return 'other'


# ── CHECK A: COVER ─────────────────────────────────────────────────────────────

def check_cover(doc, exposure_class, custom_required_mm=None):
    """
    Returns list of dicts:
      id, element_type, host_mark, bar_dia_mm, actual_cover_mm,
      required_cover_mm, status ('OK'/'FAIL'/'N/D')
    """
    required_mm = (custom_required_mm
                   if custom_required_mm is not None
                   else EC2_COVER.get(exposure_class, 25) + EC2_DEV_MARGIN)

    rows = []
    try:
        # DB.Structure.Rebar or DB.Rebar depending on version
        rebar_class = DB.Structure.Rebar
    except AttributeError:
        try:
            rebar_class = DB.Rebar
        except AttributeError:
            return rows

    for rebar in _collect(doc, rebar_class):
        try:
            host_id   = rebar.GetHostId()
            host      = doc.GetElement(host_id)
            dia_mm    = _bar_diameter_mm(rebar, doc)
            cover_mm  = _cover_mm(rebar, doc)
            el_type   = _element_type_label(host) if host else 'other'
            host_mark = ''
            if host:
                try:
                    p = host.get_Parameter(DB.BuiltInParameter.ALL_MODEL_MARK)
                    if p and p.HasValue:
                        host_mark = p.AsString() or ''
                except Exception:
                    pass

            if cover_mm is None:
                status = 'N/D'
            elif cover_mm >= required_mm:
                status = u'OK'
            else:
                status = u'FAIL'

            rows.append({
                'id':           get_id_value(rebar.Id),
                'host_id':      get_id_value(host_id) if host_id else '',
                'element_type': el_type,
                'host_mark':    host_mark,
                'bar_dia_mm':   round(dia_mm, 1) if dia_mm else '',
                'actual_cover': round(cover_mm, 1) if cover_mm is not None else 'N/D',
                'required_cover': required_mm,
                'status':       status,
            })
        except Exception:
            pass
    return rows


# ── CHECK B+C: REBAR RATIO ────────────────────────────────────────────────────

def check_rebar_ratio(doc):
    """
    Per structural element: compute As (total rebar area) and Ac (section area),
    then compare ρ = As/Ac against EC2 min/max limits.
    Returns list of dicts per element.
    """
    try:
        rebar_class = DB.Structure.Rebar
    except AttributeError:
        try:
            rebar_class = DB.Rebar
        except AttributeError:
            return []

    # Group rebars by host element
    host_rebars = {}
    for rebar in _collect(doc, rebar_class):
        try:
            host_id = get_id_value(rebar.GetHostId())
            if host_id not in host_rebars:
                host_rebars[host_id] = []
            host_rebars[host_id].append(rebar)
        except Exception:
            pass

    rows = []
    for host_id, rebars in host_rebars.items():
        try:
            host = doc.GetElement(DB.ElementId(Int64(int(host_id))))
            if host is None:
                continue
            el_type  = _element_type_label(host)
            limits   = LIMITS.get(el_type, LIMITS['other'])
            ac_mm2   = _host_section_area_mm2(host)
            if not ac_mm2 or ac_mm2 <= 0:
                continue

            # Sum bar areas
            as_mm2 = 0.0
            for rebar in rebars:
                dia   = _bar_diameter_mm(rebar, doc)
                count = _bar_count(rebar)
                if dia > 0:
                    as_mm2 += math.pi * (dia / 2) ** 2 * count

            if as_mm2 <= 0:
                continue

            rho = as_mm2 / ac_mm2

            status = u'OK'
            issues = []
            if rho < limits['rho_min']:
                status = u'FAIL'
                issues.append(u'ρ < ρ_min ({:.4f} < {:.4f})'.format(rho, limits['rho_min']))
            if rho > limits['rho_max']:
                status = u'FAIL'
                issues.append(u'ρ > ρ_max ({:.4f} > {:.4f})'.format(rho, limits['rho_max']))

            host_mark = ''
            try:
                p = host.get_Parameter(DB.BuiltInParameter.ALL_MODEL_MARK)
                if p and p.HasValue:
                    host_mark = p.AsString() or ''
            except Exception:
                pass

            rows.append({
                'id':           host_id,
                'element_type': el_type,
                'host_mark':    host_mark,
                'Ac_mm2':       round(ac_mm2, 0),
                'As_mm2':       round(as_mm2, 1),
                'rho':          round(rho, 5),
                'rho_min':      limits['rho_min'],
                'rho_max':      limits['rho_max'],
                'status':       status,
                'issues':       u'; '.join(issues),
            })
        except Exception:
            pass
    return rows


# ── CHECK D: ELEMENTS WITHOUT REBAR ───────────────────────────────────────────

def check_unreinforced(doc):
    """
    Returns structural elements (columns, beams, foundations, walls, floors)
    that have no rebar assigned.
    """
    try:
        rebar_class = DB.Structure.Rebar
    except AttributeError:
        try:
            rebar_class = DB.Rebar
        except AttributeError:
            return []

    # Build set of host IDs that have rebar
    reinforced = set()
    for rebar in _collect(doc, rebar_class):
        try:
            reinforced.add(get_id_value(rebar.GetHostId()))
        except Exception:
            pass

    rows = []
    bics = [
        DB.BuiltInCategory.OST_StructuralColumns,
        DB.BuiltInCategory.OST_StructuralFraming,
        DB.BuiltInCategory.OST_StructuralFoundation,
        DB.BuiltInCategory.OST_Walls,
        DB.BuiltInCategory.OST_Floors,
    ]
    for bic in bics:
        for el in _collect_bic(doc, bic):
            if get_id_value(el.Id) in reinforced:
                continue
            # Skip non-concrete structural usage
            try:
                mat_p = el.get_Parameter(DB.BuiltInParameter.STRUCTURAL_MATERIAL_PARAM)
                if mat_p and mat_p.HasValue:
                    mat = doc.GetElement(mat_p.AsElementId())
                    if mat and 'concrete' not in (mat.Name or '').lower() and \
                       'hormigón' not in (mat.Name or '').lower() and \
                       'horm' not in (mat.Name or '').lower():
                        continue
            except Exception:
                pass

            mark = ''
            try:
                p = el.get_Parameter(DB.BuiltInParameter.ALL_MODEL_MARK)
                if p and p.HasValue:
                    mark = p.AsString() or ''
            except Exception:
                pass

            level = ''
            try:
                lp = el.get_Parameter(DB.BuiltInParameter.FAMILY_LEVEL_PARAM) or \
                     el.get_Parameter(DB.BuiltInParameter.LEVEL_PARAM)
                if lp and lp.HasValue:
                    lv = doc.GetElement(lp.AsElementId())
                    if lv:
                        level = lv.Name or ''
            except Exception:
                pass

            rows.append({
                'id':           get_id_value(el.Id),
                'element_type': _element_type_label(el),
                'mark':         mark,
                'level':        level,
                'family_type':  el.Name if hasattr(el, 'Name') else '',
            })
    return rows


# ── MAIN RUNNER ───────────────────────────────────────────────────────────────

def run_audit(doc, options):
    """
    options = {
        'chk_cover':  bool, 'exposure_class': str, 'custom_cover_mm': float|None,
        'chk_ratio':  bool,
        'chk_unrein': bool,
    }
    Returns dict with 'cover', 'ratio', 'unreinforced' lists.
    """
    result = {}
    if options.get('chk_cover', True):
        result['cover'] = check_cover(
            doc,
            options.get('exposure_class', 'XC1'),
            options.get('custom_cover_mm', None),
        )
    if options.get('chk_ratio', True):
        result['ratio'] = check_rebar_ratio(doc)
    if options.get('chk_unrein', True):
        result['unreinforced'] = check_unreinforced(doc)
    return result
