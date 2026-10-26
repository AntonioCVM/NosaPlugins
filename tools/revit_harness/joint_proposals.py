# -*- coding: utf-8 -*-
"""
Beam/column joint clash proposals over the reinforced building, PROPOSAL MODE ONLY (user 2026-10-26, point 6: nothing
is applied; every proposal is for the user to accept or reject one by one). Per beam and layer ('top', 'bottom'):
its bars across the beam at its supports, the columns its line passes through (their vertical bars across it),
the link cage, the other bars parallel to it at its level (another beam's, the slab's, hairpins' legs), and
joint_resolution.propose. The model has no analysis results: 'forces' is None, so no R2 (decision 1).
Scope (building_test PROBE): doc, ids, _log, OUT. Writes OUT + '.joints.json' and '.joints.md'.
"""
import io
import json

import clr
clr.AddReference('RevitAPI')
from Autodesk.Revit import DB
from Autodesk.Revit.DB.Structure import MultiplanarOption, RebarHostData

from nosa_utils import joint_resolution as jr
from nosa_utils.revit_helpers import get_id_value

FT = 304.8


def text(el, name):
    p = el.LookupParameter(name)
    return (p.AsString() or u'') if p is not None and p.HasValue else u''


def mark_of(el):
    try:
        return (el.get_Parameter(DB.BuiltInParameter.ALL_MODEL_MARK).AsString() or u'').strip()
    except Exception:
        return u''


def dia(r):
    return doc.GetElement(r.GetTypeId()).BarNominalDiameter * FT


def lines_of(r):
    out = []
    for i in range(r.NumberOfBarPositions):
        try:
            cs = r.GetTransformedCenterlineCurves(False, False, False, MultiplanarOption.IncludeOnlyPlanarCurves, i)
        except Exception:
            continue
        for c in cs:
            if isinstance(c, DB.Line):
                out.append((c.GetEndPoint(0), c.GetEndPoint(1)))
    return out


columns = [doc.GetElement(i) for i in ids['columns']]
col_bars = {}
for col in columns:
    bars = []
    for r in RebarHostData.GetRebarHostData(col).GetRebarsInHost():
        if text(r, u'NOSA_Rebar_Layer') != u'vertical':
            continue
        for a, b in lines_of(r):
            if abs((b - a).Normalize().Z) > 0.99:
                bars.append((a, b, dia(r)))
    col_bars[get_id_value(col.Id)] = bars

others = []                         # (point a, point b, dia, host id) of every bar not in a column
for hid in ids['slabs'] + ids['beams']:
    for r in RebarHostData.GetRebarHostData(doc.GetElement(hid)).GetRebarsInHost():
        if text(r, u'NOSA_Rebar_Layer').startswith(u'stirrup'):
            continue
        for a, b in lines_of(r):
            others.append((a, b, dia(r), get_id_value(hid)))

rows, log = [], []
for bid in ids['beams']:
    beam = doc.GetElement(bid)
    curve = beam.Location.Curve
    o = curve.GetEndPoint(0)
    d = (curve.GetEndPoint(1) - o).Normalize()
    w = DB.XYZ(-d.Y, d.X, 0.0).Normalize()
    length = curve.Length * FT
    rebars = list(RebarHostData.GetRebarHostData(beam).GetRebarsInHost())
    links = [r for r in rebars if text(r, u'NOSA_Rebar_Layer').startswith(u'stirrup')]
    cage = None
    if links:
        ys = [abs((p - o).DotProduct(w)) * FT for a, b in lines_of(links[0])[:8] for p in (a, b)]
        cage = max(ys) - dia(links[0]) / 2.0 if ys else None
    supports = []
    for col in columns:
        bb = col.get_BoundingBox(None)
        cx, cy = (bb.Min.X + bb.Max.X) / 2.0, (bb.Min.Y + bb.Max.Y) / 2.0
        if bb.Min.Z > o.Z + 0.01 or bb.Max.Z < o.Z - 1.0:
            continue
        off = abs((DB.XYZ(cx, cy, o.Z) - o).DotProduct(w)) * FT
        if off > (bb.Max.X - bb.Min.X) * FT / 2.0:
            continue
        along = sorted((DB.XYZ(x, y, o.Z) - o).DotProduct(d) * FT for x in (bb.Min.X, bb.Max.X)
                       for y in (bb.Min.Y, bb.Max.Y))
        if along[-1] < -50.0 or along[0] > length + 50.0:
            continue
        supports.append((col, along[0], along[-1]))
    if not supports or cage is None:
        continue
    supports.sort(key=lambda s: s[1])
    faces = [(s[1], s[2]) for s in supports]
    for layer_name in (u'top', u'bottom'):
        bars = [r for r in rebars if text(r, u'NOSA_Rebar_Layer') == layer_name]
        if not bars:
            continue
        layer, z = [], []
        for r in bars:
            for a, b in lines_of(r):
                if abs((b - a).Normalize().DotProduct(d)) > 0.99:
                    layer.append((round((a - o).DotProduct(w) * FT, 1), dia(r), text(r, u'NOSA_Rebar_Mark'),
                                  get_id_value(r.Id)))
                    z.append(a.Z * FT)
        uniq = {}
        for y, dd, mk, rid in layer:
            uniq.setdefault(round(y), (y, dd, mk, rid))
        layer = sorted(uniq.values())
        if not layer:
            continue
        zl = sum(z) / len(z)
        sups = []
        for col, a, b in supports:
            cbs = col_bars[get_id_value(col.Id)]
            cys = sorted(set(round((p - o).DotProduct(w) * FT, 1) for p, q, _d in cbs
                             if min(p.Z, q.Z) * FT < zl < max(p.Z, q.Z) * FT
                             and a - 1.0 <= (p - o).DotProduct(d) * FT <= b + 1.0))
            cdia = max([cd for _p, _q, cd in cbs] or [20.0])
            centre = (a + b) / 2.0
            toward = -1.0 if centre < length / 2.0 else 1.0
            face = b if toward < 0 else a
            span = [f for f in faces if f != (a, b)]
            if not cys:
                continue                    # the column above, whose bars start at this level
            sups.append({'name': mark_of(col) or str(get_id_value(col.Id)), 'column_bars': cys, 'column_dia': cdia,
                         'forces': None, 'face_mm': face, 'toward': toward,
                         'span_mm': (face, (span[0][0] if toward < 0 else span[-1][1]) if span else face),
                         'zones_mm': []})
        if not sups:
            continue
        par = []
        for a3, b3, dd, hid in others:
            if hid == get_id_value(bid):
                continue
            if abs((b3 - a3).Normalize().DotProduct(d)) < 0.99:
                continue
            # at the layer's level: further up or down it cannot meet a shifted bar whatever its y
            if abs((a3.Z + b3.Z) / 2.0 * FT - zl) >= jr.centre_gap_mm(dd, layer[0][1]) - 0.5:
                continue
            # along this beam's own span, not the next beam's bars of the same line lapping at the support
            s0, s1 = sorted(((a3 - o).DotProduct(d) * FT, (b3 - o).DotProduct(d) * FT))
            inner = (faces[0][1], faces[-1][0]) if len(faces) > 1 else (0.0, length)
            if min(s1, inner[1]) - max(s0, inner[0]) < 500.0:
                continue
            yy = (a3 - o).DotProduct(w) * FT
            if abs(yy) < cage + 60.0:
                par.append((round(yy, 1), dd))
        props = jr.propose([(y, dd) for y, dd, _m, _r in layer], sups, cage, top=layer_name == u'top',
                           parallel=par)
        for p in props:
            y, dd, mk, rid = layer[p['bar']]
            rows.append({'beam': mark_of(beam) or str(get_id_value(bid)), 'beam_id': get_id_value(bid), 'layer': layer_name, 'mark': mk,
                         'bar_id': rid, 'y_mm': y, 'dia': dd, 'supports': [s['name'] for s in sups],
                         'rule': p['rule'], 'shift_mm': p.get('shift_mm'), 'crank_mm': p.get('crank_mm'),
                         'support': p.get('support'), 'reason': p['reason'],
                         'checks': [dict(c, value=str(c['value']), limit=str(c['limit'])) for c in p['checks']],
                         'status': u'proposed'})
        log.append(u'{} {} {} bars cage {:.0f} supports {} parallel {}'.format(
            mark_of(beam), layer_name, len(layer), cage, [(s['name'], s['column_bars']) for s in sups], len(par)))

with io.open(OUT + '.joints.json', 'w', encoding='utf-8') as fh:
    fh.write(u'{}'.format(json.dumps({'mode': 'proposal only, nothing applied', 'forces': None, 'rows': rows},
                                     ensure_ascii=True, indent=1)))
counts = {}
for r in rows:
    counts[r['rule']] = counts.get(r['rule'], 0) + 1
lines = [u'| Viga | Capa | Marca | Barra (id) | y (mm) | Pilares | Regla | Desplazamiento / acodado | Motivo |',
         u'|---|---|---|---|---|---|---|---|---|']
for r in rows:
    move = (u'δ = {} mm'.format(r['shift_mm']) if r['rule'] == u'R1' else
            u'e = {} mm en {}'.format(r['crank_mm'], r['support']) if r['rule'] == u'R2' else u'-')
    lines.append(u'| {} | {} | {} | {} | {} | {} | {} | {} | {} |'.format(
        r['beam'], r['layer'], r['mark'], r['bar_id'], r['y_mm'], u', '.join(r['supports']), r['rule'], move,
        r['reason'][:160]))
with io.open(OUT + '.joints.md', 'w', encoding='utf-8') as fh:
    fh.write(u'\n'.join(lines) + u'\n')
_log.append(u'== joint proposals (proposal only, nothing applied): {} - {}'.format(len(rows), counts))
for line in log[:6]:
    _log.append(u'    ' + line)
