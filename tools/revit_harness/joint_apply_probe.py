# -*- coding: utf-8 -*-
"""
Point 3.2 (user 2026-10-28) in a test copy: joint_apply.resolve over every beam of the reinforced building (R1
applied; APPLY = False: proposals only, for the QA before), then each applied shift checked bar by bar - the set
keeps its host, its other bars and their spacing, the moved bar keeps host, shape, mark, size and length and sits
where the rule put it - and the joints analysed again (a moved bar must have no row left).
Writes OUT + '.joints_applied.json'. Scope (building_test PROBE): doc, ids, _log, OUT; optional APPLY.
"""
import io
import json

from Autodesk.Revit import DB
from Autodesk.Revit.DB.Structure import MultiplanarOption

import joint_apply
from nosa_utils import transactions as nosa_tx
from nosa_utils.revit_helpers import element_id_from_int, get_id_value

FT = 304.8
APPLY = globals().get('APPLY', True)
CROSSING = globals().get('CROSSING', True)      # False: R1 applied past crossing bars, to test the shift itself


def text(el, name):
    p = el.LookupParameter(name)
    return (p.AsString() or u'') if p is not None and p.HasValue else u''


def state(r, w, o):
    """Host, shape, mark, size, length, and the across-beam position of every existing bar."""
    ys = []
    for i in range(r.NumberOfBarPositions):
        if not r.DoesBarExistAtPosition(i):
            continue
        cs = [c for c in r.GetTransformedCenterlineCurves(False, False, False,
                                                           MultiplanarOption.IncludeOnlyPlanarCurves, i)
              if isinstance(c, DB.Line)]
        if cs:
            ys.append(round((cs[0].GetEndPoint(0) - o).DotProduct(w) * FT, 1))
    return {'host': get_id_value(r.GetHostId()), 'shape': get_id_value(r.GetShapeId()),
            'mark': text(r, u'NOSA_Rebar_Mark'), 'type': get_id_value(r.GetTypeId()),
            'length': round(r.LookupParameter(u'Bar Length').AsDouble() * FT, 1) if r.LookupParameter(u'Bar Length')
            else None, 'quantity': r.Quantity, 'ys': sorted(ys)}


beams = [doc.GetElement(i) for i in ids['beams']]
errors, log, before = [], [], {}
for beam in beams:
    for row in joint_apply.analyse(doc, beam, crossing_check=CROSSING):
        if row['rule'] == u'R1':
            curve = beam.Location.Curve
            r = doc.GetElement(element_id_from_int(row['bar_id']))
            before[(row['bar_id'], row['position'])] = state(r, row['axis'], curve.GetEndPoint(0))
if APPLY:
    with nosa_tx.guard(DB.Transaction(doc, u'NOSA test - beam/column joints')) as t:
        t.Start()
        counts = joint_apply.resolve(doc, beams, errors, log, crossing_check=CROSSING)
        t.Commit()
else:
    counts = {'proposals only': True}
checks = []
for row in log:
    if row.get('status') != u'applied':
        continue
    beam = doc.GetElement(element_id_from_int(row['beam_id']))
    o = beam.Location.Curve.GetEndPoint(0)
    d = (beam.Location.Curve.GetEndPoint(1) - o).Normalize()
    w = DB.XYZ(-d.Y, d.X, 0.0).Normalize()
    old = before[(row['bar_id'], row['position'])]
    kept = state(doc.GetElement(element_id_from_int(row['bar_id'])), w, o)
    moved = state(doc.GetElement(element_id_from_int(row['moved_id'])), w, o)
    target = round(row['y_mm'] + row['shift_mm'], 1)
    expect_kept = sorted(y for y in old['ys'] if abs(y - row['y_mm']) > 1.0)
    result = {
        'bar': row['bar_id'], 'moved_id': row['moved_id'], 'beam': row['beam_id'],
        'set kept its host': kept['host'] == old['host'] == row['beam_id'],
        'set kept its other bars where they were': kept['ys'] == expect_kept,
        'set quantity one less': kept['quantity'] == old['quantity'] - 1,
        'moved bar in the same beam': moved['host'] == row['beam_id'],
        'same shape, mark, size, length': all(moved[k] == old[k] for k in ('shape', 'mark', 'type', 'length')),
        'moved bar where the rule put it': len(moved['ys']) == 1 and abs(moved['ys'][0] - target) <= 1.0,
        'detail': {'before': old, 'set after': kept, 'moved': moved, 'target_y': target}}
    checks.append(result)
after = []
for beam in beams:
    after.extend(joint_apply.analyse(doc, beam, crossing_check=CROSSING))
moved_at = set((r['beam_id'], r['layer'], round(r['y_mm'] + r['shift_mm'])) for r in log if r.get('status') == u'applied')
still = [r for r in after if (r['beam_id'], r['layer'], round(r['y_mm'])) in moved_at]
for r in log:
    r['checks'] = [dict(c, value=str(c['value']), limit=str(c['limit'])) for c in r['checks']]
with io.open(OUT + '.joints_applied.json', 'w', encoding='utf-8') as fh:
    fh.write(u'{}'.format(json.dumps({'apply': APPLY, 'counts': counts, 'rows': log, 'bar_checks': checks,
                                      'after': [dict((k, v) for k, v in r.items() if k not in ('axis', 'checks'))
                                                for r in after]}, ensure_ascii=True, indent=1)))
failed = [c for c in checks if not all(v for k, v in c.items() if isinstance(v, bool))]
_log.append(u'== joints applied: {} | bar checks {} ok, {} failed | after: {} rows {} | moved bars still clashing: {}'
            .format(counts, len(checks) - len(failed), len(failed), len(after),
                    dict((k, sum(1 for r in after if r['rule'] == k)) for k in (u'R1', u'R2', u'R3')), len(still)))
for c in failed[:4]:
    _log.append(u'    FAILED {}'.format(dict((k, v) for k, v in c.items() if k != 'detail')))
for e in errors[:6]:
    _log.append(u'    ' + e)
