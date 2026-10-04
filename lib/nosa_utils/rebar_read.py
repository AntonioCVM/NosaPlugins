# -*- coding: utf-8 -*-
"""Read one Revit Rebar into plain values for schedules (RebarHub BS 8666 / Rebar Schedule tabs)."""
from nosa_utils.revit_helpers import element_name, get_id_value
from nosa_utils.telemetry import log_swallowed
_LOG = u'nosa_utils.rebar_read'

FT_TO_MM = 304.8

# kg/m by nominal diameter (BS 4449 / EN 10080)
BAR_MASS_PER_M = {6: 0.222, 8: 0.395, 10: 0.617, 12: 0.888, 16: 1.579, 20: 2.466,
                  25: 3.854, 32: 6.313, 40: 9.864, 50: 15.413}


def mass_per_m(diameter_mm):
    """kg/m of a bar: the BS table for standard sizes, else the 7850 kg/m3 section."""
    d = int(round(diameter_mm or 0))
    if d in BAR_MASS_PER_M:
        return BAR_MASS_PER_M[d]
    return 7850.0 * 3.141592653589793 * (d / 2000.0) ** 2


def _param(el, bip_name):
    from Autodesk.Revit import DB
    bip = getattr(DB.BuiltInParameter, bip_name, None)
    if bip is None or el is None:
        return None
    try:
        return el.get_Parameter(bip)
    except Exception:
        return None


def _text(el, bip_name=None, name=None):
    p = _param(el, bip_name) if bip_name else (el.LookupParameter(name) if el is not None else None)
    try:
        if p is not None and p.HasValue:
            return p.AsString() or p.AsValueString() or u''
    except Exception:
        log_swallowed(_LOG, u'_text')
    return u''


def _double(el, bip_name):
    p = _param(el, bip_name)
    try:
        if p is not None and p.HasValue:
            return p.AsDouble()
    except Exception:
        log_swallowed(_LOG, u'_double')
    return 0.0


def rebar_mark(rebar):
    """BS bar mark: Schedule Mark (RebarAutomate copies its mark there), else NOSA_Rebar_Mark, else Mark."""
    return (_text(rebar, 'REBAR_ELEM_SCHEDULE_MARK') or _text(rebar, name='NOSA_Rebar_Mark')
            or _text(rebar, 'ALL_MODEL_MARK'))


def read_rebar(doc, rebar):
    """
    {'id', 'mark', 'partition', 'diameter', 'quantity', 'bar_length_mm', 'total_length_mm',
     'shape', 'host_id', 'host_category', 'host_mark', 'level', 'mass_kg', 'members'}
    Lengths are Revit's own (rounded as the project's reinforcement rounding says);
    quantity is the bars actually in the set (Quantity, not bar positions).
    """
    bar_type = doc.GetElement(rebar.GetTypeId())
    diameter = 0.0
    for getter in (lambda: bar_type.BarNominalDiameter, lambda: bar_type.BarModelDiameter,
                   lambda: _double(bar_type, 'REBAR_BAR_DIAMETER')):
        try:
            diameter = getter() * FT_TO_MM
            if diameter > 0:
                break
        except Exception:
            continue
    try:
        quantity = int(rebar.Quantity)
    except Exception:
        quantity = 1
    quantity = max(1, quantity)
    total_mm = _double(rebar, 'REBAR_ELEM_TOTAL_LENGTH') * FT_TO_MM
    if total_mm <= 0:
        try:
            total_mm = rebar.TotalLength * FT_TO_MM
        except Exception:
            total_mm = 0.0
    bar_mm = _double(rebar, 'REBAR_ELEM_LENGTH') * FT_TO_MM or (total_mm / quantity)

    shape = u''
    try:
        shape = element_name(doc.GetElement(rebar.GetShapeId()))
    except Exception:
        shape = _text(rebar, 'REBAR_SHAPE')

    host, host_id = None, None
    try:
        host_id = rebar.GetHostId()
        host = doc.GetElement(host_id)
    except Exception:
        host = None
    host_category, host_mark, level = u'', u'', u''
    if host is not None:
        try:
            host_category = host.Category.Name
        except Exception:
            host_category = u''
        host_mark = _text(host, 'ALL_MODEL_MARK')
        try:
            lvl = doc.GetElement(host.LevelId)
            level = element_name(lvl) if lvl is not None else u''
        except Exception:
            level = u''
        if not level:
            for bip in ('FAMILY_BASE_LEVEL_PARAM', 'SCHEDULE_LEVEL_PARAM', 'LEVEL_PARAM', 'WALL_BASE_CONSTRAINT'):
                level = _text(host, bip)
                if level:
                    break

    members = 1
    try:
        p = rebar.LookupParameter('Number of Members')
        if p is not None and p.HasValue:
            members = max(1, int(round(p.AsDouble() if p.StorageType.ToString() == 'Double' else p.AsInteger())))
    except Exception:
        members = 1

    return {
        'id': get_id_value(rebar.Id),
        'mark': rebar_mark(rebar),
        'partition': _text(rebar, 'NUMBER_PARTITION_PARAM'),
        'diameter': int(round(diameter)),
        'quantity': quantity,
        'bar_length_mm': float(round(bar_mm)),
        'total_length_mm': float(round(total_mm)),
        'shape': shape,
        'host_id': get_id_value(host_id) if host_id is not None else None,
        'host_category': host_category,
        'host_mark': host_mark,
        'level': level,
        'members': members,
        'mass_kg': float(total_mm / 1000.0 * mass_per_m(diameter) * members),
    }
