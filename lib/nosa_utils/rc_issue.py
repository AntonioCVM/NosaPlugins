# -*- coding: utf-8 -*-
"""
nosa_utils.rc_issue — the check of the reinforcement drawings before an issue (T9.13, IStructE SMDSC 4th ed. 3.1,
4.5): bars without a mark, one mark on bars of different shape or size, bars drawn but not scheduled on the drawing
or scheduled but not drawn, sections nothing refers to, texts on top of each other, references to drawings that do
not exist, and the title block's placeholder data, which blocks a For Construction issue. Levels Error, Warning,
Info and Passed. The rules are pure; check(doc) reads the model and changes nothing.
"""
from __future__ import absolute_import, division, print_function, unicode_literals

import re

ERROR, WARNING, INFO, PASSED = u'Error', u'Warning', u'Info', u'Passed'
DRAWING_PARAM = u'NOSA_Rebar_Group'
SERIES = (4000, 4999)            # NOSA construction details: the reinforcement drawings
PLACEHOLDERS = (u'author', u'checker', u'designer', u'approver', u'client x', u'client name', u'project name',
                u'owner', u'issue date', u'project number', u'project address', u'enter address here')
TEXT_PAPER_MM = 2.5


class Finding(object):
    """One row of the gate (plain names: the WPF grid binds them)."""

    def __init__(self, sheet, severity, check, message):
        self.Sheet = sheet
        self.Severity = severity
        self.Check = check
        self.Message = message


def is_placeholder(value):
    """A title block value still the template's sample text (or empty)."""
    v = (value or u'').strip().lower()
    return not v or v in PLACEHOLDERS


def for_construction(revision):
    """F8 C01, C02 ...: an issue For Construction (NOSA protocol)."""
    return bool(re.match(u'^C\\d{2}', (revision or u'').strip().upper()))


def mark_conflicts(bars):
    """{mark: sorted signatures} of the marks of one drawing given to bars of more than one shape or size.
    bars [(mark, signature)]: the signature tells the bending (shape, bar size, rounded lengths)."""
    seen = {}
    for mark, sig in bars:
        if mark:
            seen.setdefault(mark, set()).add(sig)
    return dict((m, sorted(s)) for m, s in seen.items() if len(s) > 1)


def overlaps(boxes, gap=0.0):
    """[(i, j)] of the boxes (x0, y0, x1, y1) that overlap."""
    out = []
    for i in range(len(boxes)):
        a = boxes[i]
        for j in range(i + 1, len(boxes)):
            b = boxes[j]
            if a[0] < b[2] - gap and b[0] < a[2] - gap and a[1] < b[3] - gap and b[1] < a[3] - gap:
                out.append((i, j))
    return out


def drawing_refs(text):
    """Four-digit drawing numbers quoted in a free text ('see 1001, 1002' -> ['1001', '1002'])."""
    return re.findall(u'(?<!\\d)\\d{4}(?!\\d)', text or u'')


def gate(findings):
    """The gate card of the RC drawings: {'status', 'count', 'items'} in the IssueWorkflowHub shape."""
    sev = {ERROR: u'FAIL', WARNING: u'WARN', INFO: u'INFO', PASSED: u'PASS'}
    items = [{'number': f.Sheet.split(u' - ')[0], 'name': f.Check, 'issue': f.Message,
              'severity': sev.get(f.Severity, u'INFO')} for f in findings]
    errors = sum(1 for f in findings if f.Severity == ERROR)
    warnings = sum(1 for f in findings if f.Severity == WARNING)
    status = 'fail' if errors else ('warn' if warnings else 'pass')
    return {'status': status, 'count': errors + warnings, 'items': items}


# ---------------------------------------------------------------------------------------------------------------
# Revit side (read-only)

_MM = 304.8


def _text(el, name):
    p = el.LookupParameter(name)
    return (p.AsString() or u'') if p is not None and p.HasValue else u''


def _bip(el, name):
    from Autodesk.Revit import DB
    try:
        p = el.get_Parameter(getattr(DB.BuiltInParameter, name))
        return (p.AsString() or p.AsValueString() or u'') if p is not None and p.HasValue else u''
    except Exception:
        return u''


def _mark(rebar):
    return _text(rebar, u'NOSA_Rebar_Mark') or _bip(rebar, 'REBAR_ELEM_SCHEDULE_MARK')


def _signature(doc, rebar):
    """Shape, bar size and length to 5 mm of a set's bars: what one mark must keep the same."""
    from nosa_utils.revit_helpers import element_name
    try:
        shape = element_name(doc.GetElement(rebar.GetShapeId()))
    except Exception:
        shape = u'?'
    try:
        size = element_name(doc.GetElement(rebar.GetTypeId()))
    except Exception:
        size = u'?'
    length = 0.0
    try:
        from Autodesk.Revit import DB
        length = rebar.get_Parameter(DB.BuiltInParameter.REBAR_ELEM_LENGTH).AsDouble() * _MM
    except Exception:
        pass
    return u'{} {} {:.0f}'.format(size, shape, 5.0 * round(length / 5.0))


def _drawings(doc):
    """{drawing number: [sheet]}: the RC sheets of the 4000 series, a drawing's continuation sheets ('Beams
    reinforcement (2)') with its first one."""
    from Autodesk.Revit import DB
    sheets = [s for s in DB.FilteredElementCollector(doc).OfClass(DB.ViewSheet)
              if s.SheetNumber.isdigit() and SERIES[0] <= int(s.SheetNumber) <= SERIES[1]]
    by_name = dict((s.Name, s) for s in sheets)
    out = {}
    for s in sheets:
        base = re.sub(u' \\(\\d+\\)$', u'', s.Name)
        first = by_name.get(base, s)
        out.setdefault(first.SheetNumber, []).append(s)
    return out


def _views(doc, sheet):
    return [doc.GetElement(doc.GetElement(i).ViewId) for i in sheet.GetAllViewports()]


def _text_box(view, element):
    """Box (view mm) of a text note's or a tag's text: a tag's own box takes its leader in."""
    from Autodesk.Revit import DB
    right, up = view.RightDirection, view.UpDirection
    scale = max(1, int(getattr(view, 'Scale', 50) or 50))
    if isinstance(element, DB.IndependentTag):
        try:
            text = (element.TagText or u'').strip().rstrip(u'-').strip()
        except Exception:
            return None
        if not text:
            return None
        h = TEXT_PAPER_MM * scale
        w, t = (len(text) * 0.58 + 0.2) * h, 1.3 * h
        if element.TagOrientation == DB.TagOrientation.Vertical:
            w, t = t, w
        p = element.TagHeadPosition
        c = (p.DotProduct(right) * _MM, p.DotProduct(up) * _MM)
        return (c[0] - w / 2.0, c[1] - t / 2.0, c[0] + w / 2.0, c[1] + t / 2.0)
    bb = element.get_BoundingBox(view)
    if bb is None:
        return None
    pts = [(q.DotProduct(right) * _MM, q.DotProduct(up) * _MM) for q in (bb.Min, bb.Max)]
    return (min(p[0] for p in pts), min(p[1] for p in pts), max(p[0] for p in pts), max(p[1] for p in pts))


def check(doc):
    """[Finding] for every RC drawing of the model (sheets 4000-4999 that show rebar)."""
    from Autodesk.Revit import DB
    from Autodesk.Revit.DB.Structure import Rebar
    from nosa_utils.revit_helpers import get_id_value
    from nosa_utils import sheet_protocol as sp
    out = []
    numbers = set(s.SheetNumber for s in DB.FilteredElementCollector(doc).OfClass(DB.ViewSheet))
    info = doc.ProjectInformation
    for drawing, sheets in sorted(_drawings(doc).items()):
        views = [v for s in sheets for v in _views(doc, s) if v is not None]
        shown = {}
        for v in views:
            for r in DB.FilteredElementCollector(doc, v.Id).OfClass(Rebar):
                shown[get_id_value(r.Id)] = r
        if not shown:
            continue
        label = u'{} - {}'.format(drawing, sheets[0].Name)
        before = len(out)

        def add(sev, check, message):
            out.append(Finding(label, sev, check, message))

        own = [r for r in shown.values() if _text(r, DRAWING_PARAM) in (u'', drawing)]
        # bars without a mark
        unmarked = [r for r in own if not _mark(r)]
        if unmarked:
            add(ERROR, u'Bar marks', u'{} set(s) of bars without a mark (e.g. id {}).'.format(
                len(unmarked), get_id_value(unmarked[0].Id)))
        # one mark, one bending (SMDSC 4.5.1)
        conflicts = mark_conflicts([(_mark(r), _signature(doc, r)) for r in own])
        for mark, sigs in sorted(conflicts.items()):
            add(ERROR, u'Bar marks', u'Mark {} is given to bars of different shape or size: {}.'.format(
                mark, u'; '.join(sigs)))
        # drawing and schedule
        loose = [r for r in shown.values() if not _text(r, DRAWING_PARAM)]
        if loose:
            add(WARNING, u'Schedule', u'{} set(s) drawn here are on no bar schedule (no drawing stamped).'.format(
                len(loose)))
        stamped = [r for r in DB.FilteredElementCollector(doc).OfClass(Rebar) if _text(r, DRAWING_PARAM) == drawing]
        missing = [r for r in stamped if get_id_value(r.Id) not in shown]
        if missing:
            add(WARNING, u'Schedule', u'{} set(s) scheduled on this drawing are not drawn on it (e.g. mark {}).'.format(
                len(missing), _mark(missing[0]) or get_id_value(missing[0].Id)))
        # sections referred to
        notes = set()
        for v in views:
            for n in DB.FilteredElementCollector(doc, v.Id).OfClass(DB.TextNote):
                notes.add((n.Text or u'').strip())
        for v in views:
            title = _bip(v, 'VIEW_DESCRIPTION')
            m = re.search(u'Section (\\S+)-\\1$', title)
            if not m:
                continue
            referred = _bip(v, 'VIEW_REFERENCING_SHEET') or m.group(1) in notes
            if not referred:
                add(WARNING, u'Sections', u'"{}" is referred to from no view on the drawing.'.format(title))
        # texts on top of each other
        for v in views:
            if v.ViewType == DB.ViewType.Legend:
                continue                  # the layer key's labels sit close by design
            boxes = []
            for cls in (DB.TextNote, DB.IndependentTag):
                for el in DB.FilteredElementCollector(doc, v.Id).OfClass(cls):
                    b = _text_box(v, el)
                    if b is not None:
                        boxes.append(b)
            scale = max(1, int(getattr(v, 'Scale', 50) or 50))
            hits = overlaps(boxes, 0.3 * scale)
            if hits:
                add(WARNING, u'Texts', u'{}: {} pair(s) of texts on top of each other.'.format(v.Name, len(hits)))
        # references
        for ref in drawing_refs(_text(info, u'NOSA_GN_GA_Drawings')):
            if ref not in numbers:
                add(WARNING, u'References', u'The GA drawing {} the notes refer to is not in the model.'.format(ref))
        try:
            from nosa_utils import general_notes
            if general_notes.find_view(doc) is None:
                add(WARNING, u'References', u'The notes refer to the general notes (0900): no such view.')
        except Exception:
            pass
        # title block: placeholders block a For Construction issue
        revision = sp.read_nosa_fields_from_sheet(doc, sheets[0]).get(u'f8', u'')
        empty = [what for bip, what in (('SHEET_DRAWN_BY', u'Drawn by'), ('SHEET_CHECKED_BY', u'Checked by'),
                                        ('SHEET_DESIGNED_BY', u'Designed by'), ('SHEET_APPROVED_BY', u'Approved by'))
                 if is_placeholder(_bip(sheets[0], bip))]
        empty += [what for name, what in ((u'Client Name', u'Client'), (u'Project Name', u'Project name'))
                  if info.LookupParameter(name) is not None and is_placeholder(_text(info, name))]
        if empty:
            add(ERROR if for_construction(revision) else WARNING, u'Title block',
                u'{} still the template sample{}.'.format(u', '.join(empty), u': no For Construction issue ({})'
                                                         .format(revision) if for_construction(revision) else u''))
        if len(out) == before:
            add(PASSED, u'All checks', u'No issues: marks, schedule, sections, texts, references, title block.')
    return out
