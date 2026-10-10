# -*- coding: utf-8 -*-
"""
nosa_utils.ties — structural tying for robustness (T8.50, IStructE SMDSC 5.1.9, EC2 9.10 with the UK NA), no
Revit: the tie forces of a building, the steel they need (accidental situation: fyd = fyk) and whether the bars
modelled along an edge or across a floor make a continuous tie.
"""
from __future__ import absolute_import, division, print_function, unicode_literals

import math

FYK_MPA = 500.0
PERIPHERAL_BAND_MM = 1200.0      # within 1.2 m of the edge of the structure


def ft_kn(storeys):
    """Ft = (20 + 4 n0) <= 60 kN (per metre for internal ties), n0 the number of storeys."""
    return min(20.0 + 4.0 * storeys, 60.0)


def peripheral_kn(storeys):
    """Peripheral tie force at each floor and roof: Ft kN."""
    return ft_kn(storeys)


def internal_kn_per_m(gk_qk_kpa, lr_m, storeys):
    """Internal ties, each direction: [(gk + qk) / 7.5] (lr / 5) Ft >= Ft kN/m."""
    ft = ft_kn(storeys)
    return max(gk_qk_kpa / 7.5 * lr_m / 5.0 * ft, ft)


def internal_max_spacing_m(lr_m):
    """Internal ties grouped in beams or walls: at most 1.5 lr apart."""
    return 1.5 * lr_m


def column_tie_kn(storeys, ls_m, vertical_kn):
    """Horizontal tie of an edge column (kN) or wall (kN/m): the greater of 2 Ft <= (ls / 2.5) Ft and 3 % of the load."""
    ft = ft_kn(storeys)
    return max(min(2.0 * ft, ls_m / 2.5 * ft), 0.03 * vertical_kn)


def area_mm2(force_kn, fyk_mpa=FYK_MPA):
    """Steel for a tie force, accidental situation (gamma_s = 1.0)."""
    return force_kn * 1000.0 / fyk_mpa


def bars_needed(force_kn, dia_mm, fyk_mpa=FYK_MPA):
    """Number of bars of dia_mm that carry force_kn."""
    return int(math.ceil(area_mm2(force_kn, fyk_mpa) / (math.pi * dia_mm ** 2 / 4.0) - 1e-9))


def coverage(intervals, lo, hi, lap_mm=0.0):
    """
    How a tie runs along lo..hi: the bars' intervals merged where they overlap by at least lap_mm (a lap).
    Returns (share of lo..hi covered 0..1, [gaps (a, b)], [joints without a full lap: position]); a continuous
    tie has share 1, no gap and no such joint.
    """
    runs, joints = [], []
    for a, b in sorted((min(i), max(i)) for i in intervals):
        if runs and a <= runs[-1][1] - lap_mm + 1e-6:
            runs[-1][1] = max(runs[-1][1], b)
            continue
        if runs and a <= runs[-1][1] + 1e-6 and b > runs[-1][1]:
            joints.append(runs[-1][1])               # touching or a short overlap: not a lap
        runs.append([a, b])
    covered, gaps, cursor = 0.0, [], lo
    for a, b in runs:
        a, b = max(a, lo), min(b, hi)
        if b <= a:
            continue
        if a > cursor + 1e-6:
            gaps.append((cursor, a))
        if b > cursor:
            covered += b - max(a, cursor)
        cursor = max(cursor, b)
    if cursor < hi - 1e-6:
        gaps.append((cursor, hi))
    length = hi - lo
    return (covered / length if length > 0 else 0.0), gaps, [j for j in joints if lo < j < hi]


# ---------------------------------------------------------------------------------------------------------------
# Revit side (read-only)

_MM = 304.8
LAP_PHI = 40.0          # a tie's laps: a full tension lap, taken as 40 phi here


def _rows(doc, floor, axis):
    """{(offset across, dia): [(a, b) along]} of the floor's bars running along axis 0 (X) or 1 (Y), one per bar."""
    from Autodesk.Revit import DB
    from Autodesk.Revit.DB.Structure import RebarHostData, MultiplanarOption
    rows = {}
    data = RebarHostData.GetRebarHostData(floor)
    if data is None:
        return rows
    for rebar in data.GetRebarsInHost():
        try:
            dia = doc.GetElement(rebar.GetTypeId()).BarNominalDiameter * _MM
            n = rebar.NumberOfBarPositions
        except Exception:
            continue
        for i in range(n):
            try:
                curves = rebar.GetTransformedCenterlineCurves(False, False, False,
                                                              MultiplanarOption.IncludeOnlyPlanarCurves, i)
            except Exception:
                break
            lines = [c for c in curves if isinstance(c, DB.Line)]
            if not lines:
                continue
            main = max(lines, key=lambda c: c.Length)
            d = main.Direction
            if abs((d.X, d.Y)[axis]) < 0.995:
                break                                    # not along this axis: the whole set is not
            p, q = main.GetEndPoint(0), main.GetEndPoint(1)
            along = sorted(((p.X, p.Y)[axis] * _MM, (q.X, q.Y)[axis] * _MM))
            across = round((p.Y, p.X)[axis] * _MM / 10.0) * 10.0
            rows.setdefault((across, round(dia)), []).append(tuple(along))
    return rows


def check_floor(doc, floor, storeys, gk_qk_kpa, lr_m, fyk_mpa=FYK_MPA):
    """
    Ties provided by a floor's own bars (SMDSC 5.1.9): along each edge of its box, the continuous lapped rows
    within 1.2 m against the peripheral force; in X and Y the continuous rows across the whole floor per metre
    against the internal force. [(check, ok, text)].
    """
    box = floor.get_BoundingBox(None)
    if box is None:
        return []
    out = []
    lo = (box.Min.X * _MM, box.Min.Y * _MM)
    hi = (box.Max.X * _MM, box.Max.Y * _MM)
    need_per = area_mm2(peripheral_kn(storeys), fyk_mpa)
    need_int = area_mm2(internal_kn_per_m(gk_qk_kpa, lr_m, storeys), fyk_mpa)
    for axis, name in ((0, u'X'), (1, u'Y')):
        rows = _rows(doc, floor, axis)
        a0, a1 = lo[axis], hi[axis]
        c0, c1 = lo[1 - axis], hi[1 - axis]
        whole = []
        for (across, dia), spans in rows.items():
            share, gaps, joints = coverage(spans, a0 + 100.0, a1 - 100.0, LAP_PHI * dia)
            if share > 0.999 and not joints:
                whole.append((across, dia))
        for edge, side in ((c0, u'min'), (c1, u'max')):
            band = [(x, dia) for x, dia in whole if abs(x - edge) <= PERIPHERAL_BAND_MM]
            have = sum(math.pi * dia ** 2 / 4.0 for _x, dia in band)
            ok = have >= need_per - 0.5
            out.append((u'Peripheral tie', ok, u'edge along {} at {} {:.0f}: {:.0f} mm2 continuous within 1.2 m, '
                        u'{:.0f} needed for {:.0f} kN'.format(name, u'Y' if axis == 0 else u'X', edge, have,
                                                               need_per, peripheral_kn(storeys))))
        width_m = max((c1 - c0) / 1000.0, 1e-6)
        have = sum(math.pi * dia ** 2 / 4.0 for _x, dia in whole) / width_m
        ok = have >= need_int - 0.5
        broken = len(rows) - len(whole)
        out.append((u'Internal tie', ok, u'{}: {:.0f} mm2/m continuous across the floor, {:.0f} needed for {:.1f} kN/m'
                    u'{}'.format(name, have, need_int, internal_kn_per_m(gk_qk_kpa, lr_m, storeys),
                                 u' ({} row(s) not continuous or not lapped 40 phi)'.format(broken) if broken else u'')))
    return out
