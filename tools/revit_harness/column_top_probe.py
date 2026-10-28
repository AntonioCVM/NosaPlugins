# -*- coding: utf-8 -*-
"""
Point 3.1 (user 2026-10-28, option a): the real geometry at the top of every top-storey column, to place detail B's
U-bars clear of everything - the column's bars (positions, ends, L feet), the links in its top 1.2 m, the beam bars
and slab bars that run through or over it (level, offset, direction). Positions in mm, relative to the column's
centre (x, y) and to the slab's top face (z, negative down). Writes OUT + '.column_top.json'.
Scope (building_test PROBE): doc, ids, _log, OUT.
"""
import io
import json

from Autodesk.Revit import DB
from Autodesk.Revit.DB.Structure import MultiplanarOption, RebarHostData

from nosa_utils.revit_helpers import get_id_value

FT = 304.8


def text(el, name):
    p = el.LookupParameter(name)
    return (p.AsString() or u'') if p is not None and p.HasValue else u''


def legs(r):
    out = []
    for i in range(r.NumberOfBarPositions):
        if not r.DoesBarExistAtPosition(i):
            continue
        for c in r.GetTransformedCenterlineCurves(False, False, False, MultiplanarOption.IncludeOnlyPlanarCurves, i):
            if isinstance(c, DB.Line):
                out.append((c.GetEndPoint(0), c.GetEndPoint(1)))
    return out


def dia(r):
    return round(doc.GetElement(r.GetTypeId()).BarNominalDiameter * FT, 1)


columns = [doc.GetElement(i) for i in ids['columns']]
top_z = max(c.get_BoundingBox(None).Max.Z for c in columns)
tops = [c for c in columns if abs(c.get_BoundingBox(None).Max.Z - top_z) < 0.01]
slab_top = max(doc.GetElement(i).get_BoundingBox(None).Max.Z for i in ids['slabs'])
others = []
for kind in ('beams', 'slabs'):
    for hid in ids[kind]:
        host = doc.GetElement(hid)
        if host.get_BoundingBox(None).Max.Z < top_z - 2.0:
            continue
        for r in RebarHostData.GetRebarHostData(host).GetRebarsInHost():
            for a, b in legs(r):
                others.append((kind, get_id_value(hid), text(r, u'NOSA_Rebar_Layer'), text(r, u'NOSA_Rebar_Mark'),
                               dia(r), a, b))
out = []
for col in tops:
    bb = col.get_BoundingBox(None)
    cx, cy = (bb.Min.X + bb.Max.X) / 2.0, (bb.Min.Y + bb.Max.Y) / 2.0

    def rel(p):
        return [round((p.X - cx) * FT, 1), round((p.Y - cy) * FT, 1), round((p.Z - slab_top) * FT, 1)]

    own = []
    for r in RebarHostData.GetRebarHostData(col).GetRebarsInHost():
        layer = text(r, u'NOSA_Rebar_Layer')
        for a, b in legs(r):
            if max(a.Z, b.Z) < slab_top - 1500.0 / FT:
                continue
            own.append({'layer': layer, 'mark': text(r, u'NOSA_Rebar_Mark'), 'dia': dia(r), 'a': rel(a), 'b': rel(b)})
    near = []
    for kind, hid, layer, mark, d, a, b in others:
        # a leg passing over the column's footprint within 1.5 m of the top
        lo, hi = min(a.Z, b.Z), max(a.Z, b.Z)
        if hi < slab_top - 1500.0 / FT:
            continue
        xs = (min(a.X, b.X), max(a.X, b.X))
        ys = (min(a.Y, b.Y), max(a.Y, b.Y))
        if xs[1] < bb.Min.X or xs[0] > bb.Max.X or ys[1] < bb.Min.Y or ys[0] > bb.Max.Y:
            continue
        near.append({'kind': kind, 'host': hid, 'layer': layer, 'mark': mark, 'dia': d, 'a': rel(a), 'b': rel(b)})
    out.append({'column': get_id_value(col.Id), 'size_mm': [round((bb.Max.X - bb.Min.X) * FT), round((bb.Max.Y - bb.Min.Y) * FT)],
                'centre': [round(cx * FT), round(cy * FT)], 'own': own, 'through': near})
with io.open(OUT + '.column_top.json', 'w', encoding='utf-8') as fh:
    fh.write(u'{}'.format(json.dumps({'slab_top_mm': round(slab_top * FT, 1), 'columns': out}, ensure_ascii=True,
                                     indent=1)))
_log.append(u'== column top probe: {} top columns, slab top {:.0f} mm'.format(len(out), slab_top * FT))
