# -*- coding: utf-8 -*-
"""
Everything the drawings place, for telling two runs apart (2026-10-26, speed work: a change is only 'identical' when
this matches): per RC sheet its viewports' boxes; per view on them every tag (head, orientation, leader ends and
elbows, text, tagged ids), text note (point, text), detail line (ends), dimension (origin, value, segments), filled
region (box) and the bars' shown positions - model mm rounded to 0.01, sorted, no annotation ids. Scope: doc, OUTDIR,
_log. Writes OUTDIR/layout_snapshot.json; tools/revit_harness/layout_compare.py tells two apart.
"""
import io
import json
import os

import clr
clr.AddReference('RevitAPI')
from Autodesk.Revit import DB
from Autodesk.Revit.DB import Structure as DBS

from nosa_utils.revit_helpers import get_id_value

FT = 304.8


def mm(p):
    return [round(p.X * FT, 2), round(p.Y * FT, 2), round(p.Z * FT, 2)] if p is not None else None


def name_of(e):
    try:
        return DB.Element.Name.GetValue(e)
    except Exception:
        return u''


def view_items(view):
    out = {'tags': [], 'notes': [], 'lines': [], 'dims': [], 'regions': [], 'bars': []}
    for tag in DB.FilteredElementCollector(doc, view.Id).OfClass(DB.IndependentTag):
        item = {'head': mm(tag.TagHeadPosition), 'orient': str(tag.TagOrientation), 'leader': bool(tag.HasLeader),
                'type': name_of(doc.GetElement(tag.GetTypeId()))}
        try:
            item['text'] = tag.TagText
        except Exception:
            item['text'] = None
        try:
            item['tagged'] = sorted(get_id_value(i) for i in tag.GetTaggedLocalElementIds())
        except Exception:
            item['tagged'] = []
        ends = []
        if tag.HasLeader:
            for ref in tag.GetTaggedReferences():
                try:
                    end = mm(tag.GetLeaderEnd(ref)) if tag.LeaderEndCondition == DB.LeaderEndCondition.Free else None
                except Exception:
                    end = None
                try:
                    elbow = mm(tag.GetLeaderElbow(ref)) if tag.HasLeaderElbow(ref) else None
                except Exception:
                    elbow = None
                ends.append([end, elbow])
        item['ends'] = ends
        out['tags'].append(item)
    for note in DB.FilteredElementCollector(doc, view.Id).OfClass(DB.TextNote):
        out['notes'].append({'at': mm(note.Coord), 'text': note.Text.strip(),
                             'type': name_of(doc.GetElement(note.GetTypeId()))})
    for c in DB.FilteredElementCollector(doc, view.Id).OfClass(DB.CurveElement):
        if not getattr(c, 'ViewSpecific', False):
            continue
        try:
            g = c.GeometryCurve
            out['lines'].append({'a': mm(g.GetEndPoint(0)), 'b': mm(g.GetEndPoint(1)),
                                 'style': c.LineStyle.Name if c.LineStyle is not None else u''})
        except Exception:
            continue
    for d in DB.FilteredElementCollector(doc, view.Id).OfClass(DB.Dimension):
        item = {'type': name_of(doc.GetElement(d.GetTypeId()))}
        try:
            item['origin'] = mm(d.Origin)
            item['value'] = round(d.Value * FT, 2) if d.Value is not None else None
        except Exception:
            pass
        try:
            item['segments'] = [[mm(s.Origin), round(s.Value * FT, 2), s.Below or u''] for s in d.Segments]
        except Exception:
            item['segments'] = []
        out['dims'].append(item)
    for r in DB.FilteredElementCollector(doc, view.Id).OfClass(DB.FilledRegion):
        bb = r.get_BoundingBox(view)
        out['regions'].append({'min': mm(bb.Min) if bb else None, 'max': mm(bb.Max) if bb else None,
                               'masking': bool(r.IsMasking)})
    for r in DB.FilteredElementCollector(doc, view.Id).OfClass(DBS.Rebar):
        try:
            mode = str(r.GetPresentationMode(view))
            shown = [i for i in range(r.NumberOfBarPositions) if not r.IsBarHidden(view, i)]
        except Exception:
            mode, shown = u'', []
        out['bars'].append({'id': get_id_value(r.Id), 'mode': mode, 'shown': shown})
    out = clean(out)
    for k in out:
        out[k] = sorted(out[k], key=lambda x: json.dumps(x, sort_keys=True))
    return out


def clean(o):
    """Plain ASCII strings (IronPython's json fails on some .NET strings with non-ASCII characters)."""
    if isinstance(o, dict):
        return dict((clean(k), clean(v)) for k, v in o.items())
    if isinstance(o, (list, tuple)):
        return [clean(v) for v in o]
    if isinstance(o, (str, unicode)) or (o is not None and not isinstance(o, (bool, int, long, float))):
        return u''.join(c if ord(c) < 128 else u'\\u{:04x}'.format(ord(c)) for c in unicode(o))
    return o


snap = {'sheets': {}, 'views': {}}
for s in DB.FilteredElementCollector(doc).OfClass(DB.ViewSheet):
    if not s.SheetNumber.startswith(u'45'):
        continue
    ports = []
    for vp in DB.FilteredElementCollector(doc, s.Id).OfClass(DB.Viewport):
        v = doc.GetElement(vp.ViewId)
        o = vp.GetBoxOutline()
        ports.append({'view': v.Name, 'min': mm(o.MinimumPoint), 'max': mm(o.MaximumPoint)})
        if v.ViewType != DB.ViewType.Legend:
            snap['views'][clean(u'{} | {}'.format(s.SheetNumber, v.Name))] = view_items(v)
    snap['sheets'][clean(s.SheetNumber)] = clean({'name': s.Name, 'viewports': sorted(ports, key=lambda p: p['view'])})
path = os.path.join(OUTDIR, 'layout_snapshot.json')
with io.open(path, 'w', encoding='utf-8') as fh:
    fh.write(u'{}'.format(json.dumps(snap, ensure_ascii=True, sort_keys=True, indent=0)))
_log.append(u'== layout snapshot: {} sheets, {} views -> {}'.format(len(snap['sheets']), len(snap['views']), path))
