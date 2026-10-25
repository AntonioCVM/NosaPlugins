# -*- coding: utf-8 -*-
"""
The QA's findings on the reinforced building, the first examples of each kind with the two bar sets named (layer,
mark, shape) and their first bar's centreline (mm), to tell a real clash from a lap the QA does not recognise.
Scope (building_test PROBE): doc, ids, _log, _mem.
"""
import re

import clr
clr.AddReference('RevitAPI')
from Autodesk.Revit import DB

from nosa_utils import rebar_qa as qa
from nosa_utils.revit_helpers import get_id_value

found = qa.audit(doc, [i for k in ('bases', 'columns', 'beams', 'slabs', 'walls', 'stairs') for i in ids[k]])
groups = {}
for f in found:
    groups.setdefault((f.Check, re.sub(u'[0-9]+', u'n', f.Issue or u'')[:60]), []).append(f)

by_mark = {}
for r in DB.FilteredElementCollector(doc).OfClass(DB.Structure.Rebar):
    m = r.LookupParameter(u'NOSA_Rebar_Mark')
    key = (get_id_value(r.GetHostId()), m.AsString() if m else u'')
    by_mark.setdefault(key, []).append(r)


def describe(rebar):
    layer = rebar.LookupParameter(u'NOSA_Rebar_Layer')
    chain = qa._chain(DB, rebar, 0)
    pts = [chain[0][0]] + [b for _a, b, _bend in chain] if chain else []
    return u'{} [{}] n{} {}'.format(layer.AsString() if layer else u'', get_id_value(rebar.Id),
                                    rebar.NumberOfBarPositions,
                                    u' '.join(u'({:.0f},{:.0f},{:.0f})'.format(*p) for p in pts[:6]))


_log.append(u'== QA examples ({} findings)'.format(len(found)))
for (check, issue), fs in sorted(groups.items(), key=lambda kv: -len(kv[1]))[:8]:
    _log.append(u'  {} x {} | {}'.format(len(fs), check, issue))
    for f in fs[:3]:
        _log.append(u'    {} | {} | {}'.format(f.Host, f.Mark, f.Issue[:160]))
        try:
            el = doc.GetElement(f.ElementId)
            _log.append(u'      bar A: ' + describe(el))
            host = get_id_value(el.GetHostId())
            marks = [m.strip() for m in (f.Mark or u'').split(u'/')]
            for other in by_mark.get((host, marks[-1]), [])[:1]:
                _log.append(u'      bar B: ' + describe(other))
        except Exception as e:
            _log.append(u'      ({})'.format(e))
