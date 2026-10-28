# -*- coding: utf-8 -*-
"""
Points 3.1 and 3.2 left for technical review (user 2026-10-28): one row per element to review one by one -
element, id, mark, reason and proposal - for every top-storey column whose L feet turn in through the opposite
face's bars, and every beam bar the joint rules leave to R3. Nothing is changed.
Writes OUT + '.review.json' and OUT + '.review.md'. Scope (building_test PROBE): doc, ids, _log, OUT.
"""
import io
import json

from Autodesk.Revit import DB
from Autodesk.Revit.DB.Structure import MultiplanarOption, RebarHostData

import joint_apply
from nosa_utils import rebar_qa
from nosa_utils.revit_helpers import get_id_value

FT = 304.8


def text(el, name):
    p = el.LookupParameter(name)
    return (p.AsString() or u'') if p is not None and p.HasValue else u''


def mark(el):
    p = el.get_Parameter(DB.BuiltInParameter.ALL_MODEL_MARK)
    return (p.AsString() or u'').strip() if p is not None else u''


def proposal(reason):
    """What a designer could do about a joint, from the rule that stopped the plugin."""
    if u'corner bar' in reason:
        return (u'Corner bar held in the link corner (P3): move the column bars off the beam bar line, or put the '
                u'beam bars in a second layer (design change)')
    if u'crossing beam' in reason:
        return (u'Lower the crossing beam\'s layer by one bar at the joint (EC2 8.2(2)), then the shift (R1) '
                u'clears both; or confirm the crossing as detailed')
    if u'poker' in reason.lower():
        return u'No room for the shift and the 75 mm poker gap: pair the bars or use fewer, larger ones (SMDSC MD B1)'
    return (u'No shift within s/2 and 50 mm and no crank within min(75, 2d) clears the column bars: second layer, '
            u'smaller bars or the column bars moved (design change)')


rows = []
columns = [doc.GetElement(i) for i in ids['columns']]
top_z = max(c.get_BoundingBox(None).Max.Z for c in columns)
for col in columns:
    bb = col.get_BoundingBox(None)
    if abs(bb.Max.Z - top_z) > 0.01:
        continue
    cx, cy = (bb.Min.X + bb.Max.X) / 2.0, (bb.Min.Y + bb.Max.Y) / 2.0
    half = (bb.Max.X - bb.Min.X) * FT / 2.0
    dia, inward = 0.0, []
    for r in RebarHostData.GetRebarHostData(col).GetRebarsInHost():
        if text(r, u'NOSA_Rebar_Layer') != u'vertical':
            continue
        dia = doc.GetElement(r.GetTypeId()).BarNominalDiameter * FT
        for i in range(r.NumberOfBarPositions):
            if not r.DoesBarExistAtPosition(i):
                continue
            for c in r.GetTransformedCenterlineCurves(False, False, False, MultiplanarOption.IncludeOnlyPlanarCurves, i):
                if not isinstance(c, DB.Line) or abs(c.GetEndPoint(0).Z - c.GetEndPoint(1).Z) > 0.003:
                    continue
                a, b = c.GetEndPoint(0), c.GetEndPoint(1)
                near = lambda p: (p.X - cx) ** 2 + (p.Y - cy) ** 2
                if near(b) < near(a):
                    a, b = b, a                 # a: the foot's start (after the bend), b: its tip
                # turned in: from the bend toward the column's centre
                if (b.X - a.X) * (cx - a.X) + (b.Y - a.Y) * (cy - a.Y) > 0.0:
                    inward.append((c.Length * FT, 0.0))
    if not inward:
        continue
    foot = max(f for f, _d in inward)
    gap = rebar_qa.REAL_DIA * dia + rebar_qa.min_clear_mm(dia)
    rows.append({'element': u'column top', 'id': get_id_value(col.Id), 'mark': mark(col), 'feet_in': len(inward),
                 'at_mm': [round(cx * FT), round(cy * FT), round(top_z * FT)],
                 'reason': u'{} L feet turn in ({:.0f} mm) and run through the opposite face\'s bars; detail B\'s '
                           u'U-bars found no place clear of the opposite bars and the beams\' bars ({:.0f} mm centre '
                           u'gap needed)'.format(len(inward), foot, gap),
                 'proposal': u'Design decision: beam bars moved off the column bar lines at the joint, U-bars laid '
                             u'flat in the slab, or the L shortened with a calculated lb,rqd (option B)'})
for bid in ids['beams']:
    beam = doc.GetElement(bid)
    for r in joint_apply.analyse(doc, beam):
        if r['rule'] == u'R1':
            continue
        mid = beam.Location.Curve.Evaluate(0.5, True)
        rows.append({'element': u'beam/column joint', 'id': r['beam_id'], 'mark': mark(beam), 'bar_id': r['bar_id'],
                     'at_mm': [round(mid.X * FT), round(mid.Y * FT), round(mid.Z * FT)],
                     'layer': r['layer'], 'bar_mark': r['mark'], 'y_mm': r['y_mm'], 'columns': r['supports'],
                     'reason': r['reason'], 'proposal': proposal(r['reason']),
                     'failed': [u'{}: {} (limit {})'.format(c['check'], c['value'], c['limit'])
                                for c in r['checks'] if not c['ok']]})
with io.open(OUT + '.review.json', 'w', encoding='utf-8') as fh:
    fh.write(u'{}'.format(json.dumps(rows, ensure_ascii=True, indent=1)))
lines = [u'| # | Elemento | Id | Marca | Posición (mm) | Detalle | Motivo | Propuesta |', u'|---|---|---|---|---|---|---|---|']
for n, r in enumerate(rows, 1):
    detail = (u'barra {} ({}) capa {} y = {:.0f} mm; pilares {}'.format(r['bar_mark'], r['bar_id'], r['layer'],
                                                                     r['y_mm'], u', '.join(r['columns']))
              if r['element'] != u'column top' else u'{} patillas hacia dentro'.format(r['feet_in']))
    lines.append(u'| {} | {} | {} | {} | {} | {} | {} | {} |'.format(n, r['element'], r['id'], r['mark'], r['at_mm'], detail,
                                                                r['reason'], r['proposal']))
with io.open(OUT + '.review.md', 'w', encoding='utf-8') as fh:
    fh.write(u'\n'.join(lines) + u'\n')
_log.append(u'== review list: {} column tops, {} joint bars'.format(
    sum(1 for r in rows if r['element'] == u'column top'), sum(1 for r in rows if r['element'] != u'column top')))
