# -*- coding: utf-8 -*-
"""
NOSA.RebarAutomate — joints of a beam with what sits on it and what it frames into (T8.49, IStructE SMDSC
4.2.1 / 4.2.2), the rules in nosa_utils.joints: how much lower its links and top bars go under a slab flush
with its top (the slab's top mat keeps its cover) and under the top bars of the main beam it frames into.
Read-only.
"""
from Autodesk.Revit import DB

from nosa_utils import joints
from nosa_utils.revit_helpers import get_id_value

_MM_PER_FT = 304.8
FLUSH_MM = 50.0
ASSUMED_SLAB_TOP_DIA_MM = 12.0


def _bars_of(doc, host, layers):
    """Nominal sizes of the host's bars in the given NOSA_Rebar_Layer values: {layer: largest}."""
    out = {}
    data = DB.Structure.RebarHostData.GetRebarHostData(host)
    if data is None:
        return out
    for rebar in data.GetRebarsInHost():
        p = rebar.LookupParameter(u'NOSA_Rebar_Layer')
        layer = (p.AsString() or u'') if p is not None and p.HasValue else u''
        if layer in layers:
            try:
                dia = doc.GetElement(rebar.GetTypeId()).BarNominalDiameter * _MM_PER_FT
            except Exception:
                continue
            out[layer] = max(out.get(layer, 0.0), dia)
    return out


def _slab_on_top(doc, host, box):
    tol = DB.XYZ(0.1, 0.1, FLUSH_MM / _MM_PER_FT)
    found = DB.FilteredElementCollector(doc).OfCategory(DB.BuiltInCategory.OST_Floors) \
        .WhereElementIsNotElementType().WherePasses(DB.BoundingBoxIntersectsFilter(DB.Outline(box.Min - tol,
                                                                                                box.Max + tol)))
    for floor in found:
        fb = floor.get_BoundingBox(None)
        # flush with the beam's top and running into it; a slab cutting the beam sits on it (its bars above)
        if fb is None:
            continue
        flush = abs(fb.Max.Z - box.Max.Z) * _MM_PER_FT <= FLUSH_MM
        if not (flush and box.Min.Z + 1e-6 < fb.Min.Z < box.Max.Z - FLUSH_MM / _MM_PER_FT):
            continue
        try:
            if DB.JoinGeometryUtils.AreElementsJoined(doc, floor, host) and \
                    DB.JoinGeometryUtils.IsCuttingElementInJoin(doc, floor, host):
                continue              # the slab cuts the beam: the beam is reinforced below it, nothing to clear
        except Exception:
            pass
        return floor
    return None


def _main_beam_at_ends(doc, host, axis):
    """The beam another one frames into at either end (not one in line with it: the next span)."""
    direction = axis.Direction
    for point, outward in ((axis.GetEndPoint(0), direction.Negate()), (axis.GetEndPoint(1), direction)):
        probe = point + outward.Multiply(60.0 / _MM_PER_FT)
        reach = DB.XYZ(0.05, 0.05, 0.3)
        for el in DB.FilteredElementCollector(doc).OfCategory(DB.BuiltInCategory.OST_StructuralFraming) \
                .WhereElementIsNotElementType().WherePasses(DB.BoundingBoxIntersectsFilter(
                    DB.Outline(probe - reach, probe + reach))):
            if get_id_value(el.Id) == get_id_value(host.Id):
                continue
            try:
                other = el.Location.Curve.Direction
            except Exception:
                continue
            if abs(other.DotProduct(direction)) < 0.5:
                return el
    return None


def top_drop_mm(doc, host, axis, beam_cover_mm, bar_dia_mm, re_engine):
    """
    (mm, notes): how much lower the beam's links and top bars go (SMDSC 4.2.2: under the top mat of a slab flush
    with its top; 4.2.1: under the top bars of the main beam it frames into).
    """
    notes, drop = [], 0.0
    box = None
    try:
        box = re_engine.get_isolated_solid_bbox(host)     # the beam as cut: a slab cutting it sits on it
    except Exception:
        box = None
    box = box or host.get_BoundingBox(None)
    if box is None:
        return 0.0, notes
    slab = _slab_on_top(doc, host, box)
    if slab is not None:
        cover = re_engine.get_native_cover_mm(doc, slab, u'Top', default_mm=25.0)
        dias = _bars_of(doc, slab, (u'top_x', u'top_y'))
        sizes = [dias.get(u'top_x'), dias.get(u'top_y')]
        if not all(sizes):
            sizes = [s or ASSUMED_SLAB_TOP_DIA_MM for s in sizes]
            notes.append(u'slab {} on the beam has no top bars yet: H{:.0f} assumed both ways — reinforce the '
                         u'slab first and run the beam again.'.format(get_id_value(slab.Id), ASSUMED_SLAB_TOP_DIA_MM))
        d = joints.slab_on_beam_drop_mm(cover, sizes, beam_cover_mm)
        if d:
            drop += d
            notes.append(u'links and top bars {:.0f} mm lower, under the top mat of slab {} (cover {:.0f} + H{:.0f} '
                         u'+ H{:.0f}, SMDSC 4.2.2).'.format(d, get_id_value(slab.Id), cover, sizes[0], sizes[1]))
    main = _main_beam_at_ends(doc, host, axis)
    if main is not None:
        top = _bars_of(doc, main, (u'top',)).get(u'top') or bar_dia_mm
        d = joints.secondary_drop_mm(top)
        drop += d
        notes.append(u'frames into beam {}: its top bars go {:.0f} mm lower, under the main beam\'s H{:.0f} top bars '
                     u'(SMDSC 4.2.1).'.format(get_id_value(main.Id), d, top))
    return drop, notes
