# -*- coding: utf-8 -*-
"""
nosa_utils.rc_register — the revision register of the reinforcement drawings (T9.14, IStructE SMDSC 4th ed. 3.9):
at each issue every bar set of a drawing is recorded by its UniqueId (mark, size, shape, length, number), compared
with the drawing's last issue and the changes written as a table on the drawing; revision clouds round the changed
bars are optional. Records are JSON files under NOSA_Configs/rc_register/<model>/<drawing>/<revision>.json.
"""
from __future__ import absolute_import, division, print_function, unicode_literals

import io
import json
import os
import re

FIELDS = (u'mark', u'size', u'shape', u'length', u'count')
LABELS = {u'mark': u'mark', u'size': u'size', u'shape': u'shape', u'length': u'length', u'count': u'number'}
DRAWING_PARAM = u'NOSA_Rebar_Group'
TABLE_TITLE = u'REINFORCEMENT CHANGES'
CLOUD_MARGIN_MM = 150.0


def diff(old, new):
    """
    Changes between two records {uid: {field: value}}: [(kind, mark, text)] sorted by mark, kind 'added', 'removed'
    or 'changed'; a set keeping its UniqueId but given another mark or bending is 'changed'.
    """
    out = []
    for uid in sorted(set(old) | set(new)):
        a, b = old.get(uid), new.get(uid)
        if a is None:
            out.append((u'added', b[u'mark'], u'{} {}H{} {} added'.format(b[u'mark'], b[u'count'], b[u'size'],
                                                                       b[u'shape'])))
        elif b is None:
            out.append((u'removed', a[u'mark'], u'{} {}H{} {} removed'.format(a[u'mark'], a[u'count'], a[u'size'],
                                                                           a[u'shape'])))
        else:
            what = [u'{} {} to {}'.format(LABELS[f], a[f], b[f]) for f in FIELDS if a.get(f) != b.get(f)]
            if what:
                out.append((u'changed', b[u'mark'], u'{}: {}'.format(a[u'mark'], u', '.join(what))))
    return sorted(out, key=lambda c: (c[1], c[0]))


def table(revision, changes):
    """The text of the changes table placed on the drawing."""
    lines = [u'{} - REVISION {}'.format(TABLE_TITLE, revision)]
    if not changes:
        lines.append(u'No change to the reinforcement.')
    lines.extend(u'- {}'.format(text) for _k, _m, text in changes)
    return u'\r'.join(lines)


def _safe(name):
    return re.sub(u'[^A-Za-z0-9_.-]+', u'_', name or u'model')


def folder(model, drawing, root=None):
    root = root or os.path.join(os.getenv('APPDATA', u''), u'pyRevit', u'Extensions', u'NOSA.extension',
                                u'NOSA_Configs', u'rc_register')
    return os.path.join(root, _safe(model), _safe(drawing))


def save(model, drawing, revision, record, root=None):
    path = folder(model, drawing, root)
    if not os.path.isdir(path):
        os.makedirs(path)
    with io.open(os.path.join(path, _safe(revision) + u'.json'), 'w', encoding='utf-8') as f:
        f.write(json.dumps(record, ensure_ascii=False, indent=1, sort_keys=True))


def last(model, drawing, before=None, root=None):
    """(revision, record) of the drawing's latest record (before the given revision), or (None, {})."""
    path = folder(model, drawing, root)
    if not os.path.isdir(path):
        return None, {}
    # in the order they were issued (C01 follows P03, though it sorts before it)
    files = [f for f in os.listdir(path) if f.endswith(u'.json') and (before is None or f[:-5] != before)]
    revs = [f[:-5] for f in sorted(files, key=lambda f: (os.path.getmtime(os.path.join(path, f)), f))]
    if not revs:
        return None, {}
    with io.open(os.path.join(path, revs[-1] + u'.json'), encoding='utf-8') as f:
        return revs[-1], json.loads(f.read())


# ---------------------------------------------------------------------------------------------------------------
# Revit side

_MM = 304.8


def record(doc, drawing):
    """{uid: {field: value}} of the bar sets scheduled on a drawing."""
    from Autodesk.Revit import DB
    from Autodesk.Revit.DB.Structure import Rebar
    from nosa_utils.revit_helpers import element_name
    out = {}
    for r in DB.FilteredElementCollector(doc).OfClass(Rebar):
        p = r.LookupParameter(DRAWING_PARAM)
        if p is None or (p.AsString() or u'') != drawing:
            continue
        mark = u''
        q = r.LookupParameter(u'NOSA_Rebar_Mark')
        if q is not None:
            mark = q.AsString() or u''
        try:
            size = element_name(doc.GetElement(r.GetTypeId())).replace(u'H', u'').strip()
        except Exception:
            size = u''
        try:
            shape = element_name(doc.GetElement(r.GetShapeId()))
        except Exception:
            shape = u''
        try:
            length = int(round(r.get_Parameter(DB.BuiltInParameter.REBAR_ELEM_LENGTH).AsDouble() * _MM / 5.0) * 5)
        except Exception:
            length = 0
        out[r.UniqueId] = {u'mark': mark, u'size': size, u'shape': shape, u'length': length,
                           u'count': r.NumberOfBarPositions}
    return out


def revise(doc, drawing, sheet, revision, clouds=False, root=None):
    """
    Record the drawing at its revision and put the changes since its last record on the sheet (a text table at the
    foot of the notes; with clouds, a revision cloud round each changed bar in the views of the sheet). In a
    transaction. Returns [(kind, mark, text)]; the first record of a drawing has no changes.
    """
    now = record(doc, drawing)
    previous, old = last(doc.Title, drawing, before=revision, root=root)
    changes = diff(old, now) if previous else []
    if previous:
        _table(doc, sheet, revision, changes)
        if clouds and changes:
            _clouds(doc, sheet, revision, set(uid for uid in set(old) | set(now)
                                              if old.get(uid) != now.get(uid)))
    save(doc.Title, drawing, revision, now, root)
    return changes


def _table(doc, sheet, revision, changes):
    from Autodesk.Revit import DB
    for n in DB.FilteredElementCollector(doc, sheet.Id).OfClass(DB.TextNote):
        if (n.Text or u'').startswith(TABLE_TITLE):
            doc.Delete(n.Id)
    notes = [n for n in DB.FilteredElementCollector(doc, sheet.Id).OfClass(DB.TextNote)
             if (n.Text or u'').startswith(u'REINFORCEMENT NOTES')]
    type_id = notes[0].GetTypeId() if notes else doc.GetDefaultElementTypeId(DB.ElementTypeGroup.TextNoteType)
    if notes:
        bb = notes[0].get_BoundingBox(sheet)
        at = DB.XYZ(bb.Min.X, bb.Min.Y - 8.0 / _MM, 0.0)
        width = bb.Max.X - bb.Min.X
    else:
        at, width = DB.XYZ(610.0 / _MM, 120.0 / _MM, 0.0), 100.0 / _MM
    DB.TextNote.Create(doc, sheet.Id, at, width, table(revision, changes), DB.TextNoteOptions(type_id))


def _revision_id(doc, revision):
    """The Revit revision of this issue (its number or description), else the latest one."""
    from Autodesk.Revit import DB
    revs = list(DB.FilteredElementCollector(doc).OfClass(DB.Revision))
    for r in revs:
        try:
            number = r.RevisionNumber or u''
        except Exception:
            number = u''                      # numbered per sheet: no project-wide number
        if revision and revision in (number, r.Description or u''):
            return r.Id
    return revs[-1].Id if revs else None


def _clouds(doc, sheet, revision, uids):
    from Autodesk.Revit import DB
    from System.Collections.Generic import List
    rev = _revision_id(doc, revision)
    if rev is None:
        return 0
    made = 0
    m = CLOUD_MARGIN_MM / _MM
    for port_id in sheet.GetAllViewports():
        view = doc.GetElement(doc.GetElement(port_id).ViewId)
        if view is None or view.ViewType == DB.ViewType.Legend:
            continue
        for r in DB.FilteredElementCollector(doc, view.Id).OfClass(DB.Structure.Rebar):
            if r.UniqueId not in uids:
                continue
            bb = r.get_BoundingBox(view)
            if bb is None:
                continue
            right, up = view.RightDirection, view.UpDirection
            pts = [DB.XYZ(x, y, z) for x in (bb.Min.X, bb.Max.X) for y in (bb.Min.Y, bb.Max.Y)
                   for z in (bb.Min.Z, bb.Max.Z)]
            xs = [p.DotProduct(right) for p in pts]
            ys = [p.DotProduct(up) for p in pts]
            depth = view.Origin.DotProduct(view.ViewDirection)
            corners = [(min(xs) - m, min(ys) - m), (max(xs) + m, min(ys) - m), (max(xs) + m, max(ys) + m),
                       (min(xs) - m, max(ys) + m)]
            loop = List[DB.Curve]()
            for i in range(4):
                a, b = corners[i], corners[(i + 1) % 4]
                pa = right.Multiply(a[0]) + up.Multiply(a[1]) + view.ViewDirection.Multiply(depth)
                pb = right.Multiply(b[0]) + up.Multiply(b[1]) + view.ViewDirection.Multiply(depth)
                loop.Add(DB.Line.CreateBound(pa, pb))
            try:
                DB.RevisionCloud.Create(doc, view, rev, loop)
                made += 1
            except Exception:
                continue
    return made
