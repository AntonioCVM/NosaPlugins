# -*- coding: utf-8 -*-
"""
NOSA.RebarAutomate — phase 11 tools, the parts without Revit: bars grouped by layer for visibility (T11.4), the
issue log of a drawing (T11.2) and the test for identical members (T11.3).
"""
from __future__ import absolute_import, division, print_function, unicode_literals
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)       # its siblings (rebar_batch, bar_schedules, rebar_bending) by name

# (key, label) in the order the window lists them
LAYER_GROUPS = (
    (u'T1', u'T1 - top outer layer'), (u'T2', u'T2 - top second layer'),
    (u'B1', u'B1 - bottom outer layer'), (u'B2', u'B2 - bottom second layer'),
    (u'N1', u'N1 - near face outer'), (u'N2', u'N2 - near face second'),
    (u'F1', u'F1 - far face outer'), (u'F2', u'F2 - far face second'),
    (u'UBAR', u'U-bars and edge bars'), (u'OPENING', u'Trimmers and diagonals'),
    (u'STARTER', u'Starters and dowels'), (u'LINK', u'Links and ties'),
)
_CODES = (u'T1', u'T2', u'B1', u'B2', u'N1', u'N2', u'F1', u'F2')


def layer_groups(layer, location):
    """The groups a bar falls in, from its NOSA layer and its location code (Comments: B1, T2, N1 ...)."""
    out = set()
    code = (location or u'').strip().upper()
    for c in _CODES:
        if code.startswith(c):
            out.add(c)
    lay = (layer or u'').strip().lower()
    if u'ubar' in lay or u'u_bar' in lay or u'edge' in lay or lay.startswith(u'closure'):
        out.add(u'UBAR')
    if lay.startswith((u'trimmer', u'diagonal', u'opening')):
        out.add(u'OPENING')
    if lay.startswith((u'dowel', u'starter')) or u'starter' in lay:
        out.add(u'STARTER')
    if u'link' in lay or u'stirrup' in lay or u'tie' in lay:
        out.add(u'LINK')
    return out


def parse_marks(text):
    """'01, 3 05' -> ['01', '3', '05']: the bar marks typed in the window."""
    return [m for m in (text or u'').replace(u';', u',').replace(u',', u' ').split() if m]


def mark_matches(mark, wanted):
    """A bar's mark is one of the typed ones; '1' finds '01', and 'S1-01' is found by '01' or 'S1-01'."""
    m = (mark or u'').strip().upper()
    if not m:
        return False
    tail = m.rsplit(u'-', 1)[-1]
    for w in wanted:
        w = w.strip().upper()
        if w in (m, tail) or (w.isdigit() and tail.isdigit() and int(w) == int(tail)):
            return True
    return False


STATUSES = (u'P', u'T', u'C')          # preliminary, tender, construction (SMDSC 4th ed. 4.5.1 status letter)


def next_revision(previous):
    """'' -> 'A', 'A' -> 'B', 'Z' -> 'AA': the next revision letter of a drawing's issues."""
    p = (previous or u'').strip().upper()
    if not p:
        return u'A'
    letters = [ord(ch) - 64 for ch in p if u'A' <= ch <= u'Z']
    n = 0
    for v in letters:
        n = n * 26 + v
    n += 1
    out = u''
    while n:
        n, r = divmod(n - 1, 26)
        out = chr(65 + r) + out
    return out


def snapshot_changes(before, after):
    """
    What changed between two issues of a drawing: before / after {mark: [number, size, length mm]}. Returns
    [text] - added, removed and changed marks, in mark order.
    """
    out = []
    for mark in sorted(set(before) | set(after), key=lambda m: (len(m), m)):
        a, b = before.get(mark), after.get(mark)
        if a is None:
            out.append(u'{} added ({} H{} x {:.0f})'.format(mark, b[0], b[1], b[2]))
        elif b is None:
            out.append(u'{} removed'.format(mark))
        elif list(a) != list(b):
            bits = []
            for name, x, y in ((u'number', a[0], b[0]), (u'size', a[1], b[1]), (u'length', a[2], b[2])):
                if abs(float(x) - float(y)) > 0.5:
                    bits.append(u'{} {:g} -> {:g}'.format(name, float(x), float(y)))
            out.append(u'{} {}'.format(mark, u', '.join(bits)))
    return out


def history_text(issues):
    """The issue log of one drawing, newest first, for the window."""
    lines = []
    for issue in reversed(issues or []):
        lines.append(u'{} {} {} - {} mark(s){}'.format(
            issue.get('revision', u''), issue.get('status', u''), issue.get('date', u''),
            len(issue.get('bars') or {}), u': ' + u'; '.join(issue['changes']) if issue.get('changes') else u''))
    return u'\n'.join(lines) or u'Not issued yet.'


def same_member(a, b, tol_mm=2.0):
    """
    Two members are identical for copying their bars: the same type and the same size along their own axes.
    a, b: (type id, (length, width, height) mm in the member's own axes).
    """
    if a[0] != b[0]:
        return False
    return all(abs(x - y) <= tol_mm for x, y in zip(a[1], b[1]))


# ── In Revit (lazy imports) ─────────────────────────────────────────────

def _text(element, name):
    p = element.LookupParameter(name)
    return (p.AsString() or u'') if p is not None and p.HasValue else u''


def bar_mark(rebar):
    from Autodesk.Revit import DB
    mark = _text(rebar, u'NOSA_Rebar_Mark')
    if not mark:
        p = rebar.get_Parameter(DB.BuiltInParameter.REBAR_ELEM_SCHEDULE_MARK)
        mark = (p.AsString() or u'') if p is not None else u''
    return mark


def bar_location(rebar):
    """The location code on the bar's label (Comments), or the one its NOSA layer gives."""
    from Autodesk.Revit import DB
    p = rebar.get_Parameter(DB.BuiltInParameter.ALL_MODEL_INSTANCE_COMMENTS)
    code = (p.AsString() or u'') if p is not None else u''
    if code:
        return code
    import rebar_batch
    return rebar_batch.location_code(_text(rebar, u'NOSA_Rebar_Layer'))


def model_rebars(doc, view=None):
    from Autodesk.Revit import DB
    from Autodesk.Revit.DB.Structure import Rebar
    collector = DB.FilteredElementCollector(doc, view.Id) if view is not None else DB.FilteredElementCollector(doc)
    return [r for r in collector.OfClass(Rebar)]


def bars_in_group(rebars, key):
    return [r for r in rebars if key in layer_groups(_text(r, u'NOSA_Rebar_Layer'), bar_location(r))]


def bars_with_marks(rebars, wanted):
    return [r for r in rebars if mark_matches(bar_mark(r), wanted)]


def _diameter_mm(doc, rebar):
    from Autodesk.Revit import DB
    try:
        bar_type = doc.GetElement(rebar.GetTypeId())
        return int(round(bar_type.BarNominalDiameter * 304.8))
    except Exception:
        p = rebar.get_Parameter(DB.BuiltInParameter.REBAR_BAR_DIAMETER)
        return int(round(p.AsDouble() * 304.8)) if p is not None else 0


def drawing_bars(doc, drawing):
    """The NOSA bars detailed on a drawing (NOSA_Rebar_Group)."""
    import bar_schedules
    return [r for r in model_rebars(doc) if _text(r, bar_schedules.DRAWING_PARAM) == drawing]


def drawings(doc):
    """Every drawing NOSA bars are detailed on, in sheet order."""
    import bar_schedules
    found = set(_text(r, bar_schedules.DRAWING_PARAM) for r in model_rebars(doc))
    found.discard(u'')
    return sorted(found, key=bar_schedules.natural_key)


def snapshot(doc, rebars):
    """{mark: [number of bars, size, cut length mm]} of a drawing's bars, as its schedule lists them."""
    import rebar_bending
    out = {}
    for r in rebars:
        mark = bar_mark(r) or u'?'
        try:
            n = int(r.Quantity)
        except Exception:
            n = 1
        try:
            length = float(rebar_bending.unit_cut_length_mm(r))
        except Exception:
            length = 0.0
        row = out.setdefault(mark, [0, _diameter_mm(doc, r), round(length)])
        row[0] += n
    return out


def _set_finalized(rebars, value):
    n = 0
    for r in rebars:
        p = r.LookupParameter(u'NOSA_Rebar_Finalized')
        if p is not None and not p.IsReadOnly:
            p.Set(1 if value else 0)
            n += 1
    return n


def _stamp_sheets(doc, drawing, revision, status):
    """The drawing's bar schedule sheets carry the issue's revision and status (SMDSC 4th ed. 4.5.1)."""
    from Autodesk.Revit import DB
    import bar_schedules
    n = 0
    for sheet in DB.FilteredElementCollector(doc).OfClass(DB.ViewSheet):
        if _text(sheet, u'NOSA_BBS_Drawing') != drawing:
            continue
        ref, old = _text(sheet, u'NOSA_BBS_Ref'), _text(sheet, u'NOSA_BBS_Revision')
        key = ref[:-len(old) - 1] if old and ref.endswith(u'-' + old) else ref
        for name, value in ((u'NOSA_BBS_Revision', revision), (u'NOSA_BBS_Status', status),
                            (u'NOSA_BBS_Ref', bar_schedules.schedule_ref(key, revision))):
            p = sheet.LookupParameter(name)
            if p is not None and not p.IsReadOnly:
                p.Set(value)
        n += 1
    return n


def issue(doc, drawing, status, date, project):
    """
    T11.2 — issue a drawing: its bars are frozen (NOSA_Rebar_Finalized: renumbering and deleting leave them
    alone), its schedules take the next revision and the issue is logged with what changed since the last one.
    project: the rebar_project data, updated in place. In a transaction. Returns the issue.
    """
    bars = drawing_bars(doc, drawing)
    log = project.setdefault('issues', {}).setdefault(drawing, [])
    previous = log[-1] if log else None
    bars_now = snapshot(doc, bars)
    entry = {'revision': next_revision(previous['revision'] if previous else u''), 'status': status,
             'date': date, 'bars': bars_now,
             'changes': snapshot_changes(previous['bars'], bars_now) if previous else []}
    _set_finalized(bars, True)
    entry['sheets'] = _stamp_sheets(doc, drawing, entry['revision'], status)
    log.append(entry)
    return entry


def reopen(doc, drawing):
    """A drawing's bars unfrozen to be revised; the next issue logs what changed. In a transaction."""
    return _set_finalized(drawing_bars(doc, drawing), False)


def frozen_hosts(doc, hosts):
    """The hosts with issued (Finalized) bars: generating on them again would double their bars."""
    from Autodesk.Revit.DB.Structure import RebarHostData
    out = []
    for host in hosts:
        data = RebarHostData.GetRebarHostData(host)
        if data is None:
            continue
        for r in data.GetRebarsInHost():
            p = r.LookupParameter(u'NOSA_Rebar_Finalized')
            if p is not None and p.HasValue and p.AsInteger() == 1:
                out.append(host)
                break
    return out


# ── T11.3: copy a member's bars to the identical members ───────────────

def _frame(element):
    """The member's own axes as a Transform, or None for a member that is only ever moved (floors)."""
    from Autodesk.Revit import DB
    loc = getattr(element, 'Location', None)
    curve = getattr(loc, 'Curve', None) if loc is not None else None
    if isinstance(curve, DB.Line) and abs(curve.Direction.Z) < 0.999:
        t = DB.Transform.Identity
        x = curve.Direction.Normalize()
        t.Origin = curve.GetEndPoint(0)
        t.BasisX = x
        t.BasisY = DB.XYZ.BasisZ.CrossProduct(x).Normalize()
        t.BasisZ = x.CrossProduct(t.BasisY)
        return t
    if isinstance(element, DB.FamilyInstance):
        try:
            return element.GetTransform()
        except Exception:
            return None
    return None


def signature(element):
    """(type id, sizes mm along the member's own axes) for same_member."""
    from Autodesk.Revit import DB
    from nosa_utils.revit_helpers import get_id_value
    box = element.get_BoundingBox(None)
    if box is None:
        return None
    loc = getattr(element, 'Location', None)
    curve = getattr(loc, 'Curve', None) if loc is not None else None
    height = round((box.Max.Z - box.Min.Z) * 304.8)
    if curve is not None:
        sizes = (round(curve.Length * 304.8), height)
    elif isinstance(element, DB.FamilyInstance):
        sizes = (height,)
    else:
        sizes = (round((box.Max.X - box.Min.X) * 304.8), round((box.Max.Y - box.Min.Y) * 304.8), height)
    return get_id_value(element.GetTypeId()), sizes


def _transform(source, target):
    from Autodesk.Revit import DB
    a, b = _frame(source), _frame(target)
    if a is not None and b is not None:
        return b.Multiply(a.Inverse)
    sa, sb = source.get_BoundingBox(None), target.get_BoundingBox(None)
    return DB.Transform.CreateTranslation((sb.Min + sb.Max) * 0.5 - (sa.Min + sa.Max) * 0.5)


def identical_members(doc, source, candidates=None):
    """The members of the source's category and type with its size and no bars of their own."""
    from Autodesk.Revit import DB
    from Autodesk.Revit.DB.Structure import RebarHostData
    sig = signature(source)
    if sig is None:
        return []
    if candidates is None:
        candidates = DB.FilteredElementCollector(doc).OfCategoryId(source.Category.Id) \
            .WhereElementIsNotElementType().ToElements()
    out = []
    for el in candidates:
        if el.Id == source.Id:
            continue
        other = signature(el)
        if other is None or len(other[1]) != len(sig[1]) or not same_member(sig, other):
            continue
        data = RebarHostData.GetRebarHostData(el)
        if data is None or not data.IsValidHost() or data.GetRebarsInHost().Count:
            continue
        out.append(el)
    return out


def copy_bars(doc, source, targets):
    """
    The source's free bars copied onto each target with the transform from one member to the other, and
    hosted by it. In a transaction. Returns {'members': n, 'bars': n, 'errors': [text]}.
    """
    from Autodesk.Revit import DB
    from Autodesk.Revit.DB.Structure import Rebar, RebarHostData
    from System.Collections.Generic import List
    data = RebarHostData.GetRebarHostData(source)
    bars = [r for r in data.GetRebarsInHost() if isinstance(r, Rebar)] if data is not None else []
    report = {'members': 0, 'bars': 0, 'errors': []}
    if not bars:
        report['errors'].append(u'The source member has no bars to copy.')
        return report
    ids = List[DB.ElementId]([r.Id for r in bars])
    options = DB.CopyPasteOptions()
    for target in targets:
        try:
            new = DB.ElementTransformUtils.CopyElements(doc, ids, doc, _transform(source, target), options)
            for eid in new:
                bar = doc.GetElement(eid)
                if not isinstance(bar, Rebar):
                    continue
                if bar.GetHostId() != target.Id:
                    bar.SetHostId(doc, target.Id)
                p = bar.LookupParameter(u'NOSA_Rebar_Finalized')
                if p is not None and not p.IsReadOnly:
                    p.Set(0)
            report['members'] += 1
            report['bars'] += new.Count
        except Exception as e:
            report['errors'].append(u'{}: {}'.format(target.Id, e))
    return report
