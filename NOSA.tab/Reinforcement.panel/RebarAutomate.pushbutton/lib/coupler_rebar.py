# -*- coding: utf-8 -*-
"""
NOSA.RebarAutomate — mechanical couplers between bars that meet end to end (T8.52, IStructE SMDSC 5.5), the rules
in nosa_utils.couplers: the NOSA Rebar Coupler family (content/couplers) loaded on first use, its type for the
bar size given that size, one Revit Rebar Coupler at every joint of two bars (sets included). In a transaction.
"""
import os

from Autodesk.Revit import DB
from Autodesk.Revit.DB import Structure as DBS

from nosa_utils import couplers
from nosa_utils.revit_helpers import element_name

_MM_PER_FT = 304.8
FAMILY_FILE = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', 'content', 'couplers',
                                           u'NOSA Rebar Coupler.rfa'))


def coupler_type(doc, bar_type):
    """The NOSA Rebar Coupler type for bar_type's size, its bar sizes set to it and active; None if none fits."""
    dia = bar_type.BarNominalDiameter * _MM_PER_FT
    name = couplers.type_name(dia)
    if name is None:
        return None

    def find():
        for s in DB.FilteredElementCollector(doc).OfClass(DB.FamilySymbol).OfCategory(DB.BuiltInCategory.OST_Coupler):
            if s.FamilyName == couplers.FAMILY and element_name(s) == name:
                return s
        return None
    symbol = find()
    if symbol is None and os.path.isfile(FAMILY_FILE):
        doc.LoadFamily(FAMILY_FILE)
        symbol = find()
    if symbol is None:
        return None
    for bip in (DB.BuiltInParameter.COUPLER_MAIN_BAR_SIZE, DB.BuiltInParameter.COUPLER_COUPLED_BAR_SIZE):
        p = symbol.get_Parameter(bip)
        if p is not None and not p.IsReadOnly and p.AsElementId() != bar_type.Id:
            p.Set(bar_type.Id)
    if not symbol.IsActive:
        symbol.Activate()
    return symbol


def _ends(rebar):
    """((start, end) of its first bar, (start, end) of its last bar) of a bar or set."""
    from Autodesk.Revit.DB.Structure import MultiplanarOption

    def bar(i):
        curves = list(rebar.GetTransformedCenterlineCurves(False, False, False,
                                                           MultiplanarOption.IncludeOnlyPlanarCurves, i))
        return (curves[0].GetEndPoint(0), curves[-1].GetEndPoint(1)) if curves else None
    first, last = bar(0), bar(rebar.NumberOfBarPositions - 1)
    return (first, last) if first and last else None


def couple(doc, rebars, tol_mm=1.0):
    """
    A coupler at every joint where one bar (or set) ends exactly where another of the same size starts.
    Returns (couplers made, [notes]).
    """
    ends = []
    for r in rebars:
        try:
            e = _ends(r)
        except Exception:
            e = None
        if e is not None:
            ends.append((r, e))
    made, notes, tol = 0, [], tol_mm / _MM_PER_FT
    taken = set()
    for lower, (lf, ll) in ends:
        for upper, (uf, ul) in ends:
            # the same bars one above the other: every bar of the lower set ends where one of the upper starts
            same = lower.GetTypeId() == upper.GetTypeId() and \
                lower.NumberOfBarPositions == upper.NumberOfBarPositions
            if lower.Id == upper.Id or upper.Id in taken or not same:
                continue
            if not (lf[1].IsAlmostEqualTo(uf[0], tol) and ll[1].IsAlmostEqualTo(ul[0], tol)):
                continue
            ctype = coupler_type(doc, doc.GetElement(lower.GetTypeId()))
            if ctype is None:
                notes.append(u'no NOSA Rebar Coupler for this bar size: lap the bars instead.')
                break
            # IronPython returns the out RebarCouplerError with the coupler: (coupler, error)
            result = DBS.RebarCoupler.Create(doc, ctype.Id, DBS.RebarReinforcementData.Create(lower.Id, 1),
                                             DBS.RebarReinforcementData.Create(upper.Id, 0))
            coupler = result[0] if isinstance(result, tuple) else result
            if coupler is not None:
                made += 1
                taken.add(upper.Id)
            else:
                notes.append(u'coupler not made between bars {} and {}: {}'.format(
                    lower.Id, upper.Id, result[1] if isinstance(result, tuple) else u'?'))
            break
    return made, notes

