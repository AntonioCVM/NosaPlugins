# -*- coding: utf-8 -*-
"""
Sheet content and naming checks before an issue (T8.12): the NOSA protocol fields
(nosa_utils.protocol_rules) plus what is on the sheet — title block data, empty sheets, viewports
off the title block, views without a template, title-block scale, non-NOSA fonts.
"""
from nosa_utils import protocol_rules as pr
from nosa_utils import sheet_protocol as sp
from nosa_utils.telemetry import log_swallowed

_LOG = u'nosa_utils.sheet_checks'
NOSA_FONT = u'Century Gothic'


class Finding(object):
    def __init__(self, sheet, severity, check, message):
        self.Sheet = sheet
        self.Severity = severity
        self.Check = check
        self.Message = message


def _param(el, bip_name):
    from Autodesk.Revit import DB
    try:
        p = el.get_Parameter(getattr(DB.BuiltInParameter, bip_name))
    except Exception:
        return u''
    if p is None or not p.HasValue:
        return u''
    return p.AsString() or p.AsValueString() or u''


def _titleblock(doc, sheet):
    from Autodesk.Revit import DB
    blocks = list(DB.FilteredElementCollector(doc, sheet.Id).OfCategory(
        DB.BuiltInCategory.OST_TitleBlocks).WhereElementIsNotElementType())
    return blocks[0] if blocks else None


def _model_view(view):
    from Autodesk.Revit import DB
    return view.ViewType in (DB.ViewType.FloorPlan, DB.ViewType.EngineeringPlan, DB.ViewType.CeilingPlan,
                             DB.ViewType.Section, DB.ViewType.Elevation, DB.ViewType.Detail,
                             DB.ViewType.ThreeD, DB.ViewType.AreaPlan)


def _fonts(doc, view):
    """Fonts of the text notes and dimensions shown in a view."""
    from Autodesk.Revit import DB
    fonts = set()
    for cls, bip in ((DB.TextNote, 'TEXT_FONT'), (DB.Dimension, 'TEXT_FONT')):
        for el in DB.FilteredElementCollector(doc, view.Id).OfClass(cls):
            t = doc.GetElement(el.GetTypeId())
            if t is not None:
                font = _param(t, bip)
                if font:
                    fonts.add(font)
    return fonts


def check_sheet(doc, sheet, number_counts=None):
    """[Finding] for one ViewSheet."""
    from Autodesk.Revit import DB
    label = u'{} - {}'.format(sheet.SheetNumber, sheet.Name)
    out = []

    def add(sev, check, message):
        out.append(Finding(label, sev, check, message))

    fields = sp.read_nosa_fields_from_sheet(doc, sheet)
    for sev, _key, message in pr.check_fields(fields):
        add(sev, u'Protocol', message)
    f7 = (fields.get(u'f7') or u'').strip()
    if f7 and f7 != (sheet.SheetNumber or u'').strip():
        add(pr.ERROR, u'Protocol', u'Sheet number "{}" differs from the document number F7 "{}".'.format(
            sheet.SheetNumber, f7))
    if number_counts and number_counts.get(sheet.SheetNumber, 0) > 1:
        add(pr.ERROR, u'Protocol', u'Sheet number used {} times.'.format(number_counts[sheet.SheetNumber]))

    for bip, what in (('SHEET_DRAWN_BY', u'Drawn by'), ('SHEET_CHECKED_BY', u'Checked by'),
                      ('SHEET_ISSUE_DATE', u'Sheet issue date')):
        value = _param(sheet, bip).strip()
        if not value or value.lower() in (u'author', u'checker', u'issue date', u'approver'):
            add(pr.WARNING, u'Title block', u'{} is empty or still the default ("{}").'.format(what, value))

    ports = [doc.GetElement(i) for i in sheet.GetAllViewports()]
    schedules = list(DB.FilteredElementCollector(doc, sheet.Id).OfClass(DB.ScheduleSheetInstance))
    schedules = [s for s in schedules if not s.IsTitleblockRevisionSchedule]
    if not ports and not schedules:
        add(pr.WARNING, u'Content', u'Empty sheet: no views or schedules placed.')

    tb = _titleblock(doc, sheet)
    tb_box = tb.get_BoundingBox(sheet) if tb is not None else None
    scales = set()
    fonts = set()
    for port in ports:
        view = doc.GetElement(port.ViewId)
        if view is None:
            continue
        name = view.Name
        try:
            outline = port.GetBoxOutline()
            if tb_box is not None and (outline.MinimumPoint.X < tb_box.Min.X - 1e-3 or
                                       outline.MinimumPoint.Y < tb_box.Min.Y - 1e-3 or
                                       outline.MaximumPoint.X > tb_box.Max.X + 1e-3 or
                                       outline.MaximumPoint.Y > tb_box.Max.Y + 1e-3):
                add(pr.WARNING, u'Content', u'View "{}" sticks out of the title block.'.format(name))
        except Exception:
            log_swallowed(_LOG, u'check_sheet')
        if _model_view(view):
            scales.add(view.Scale)
            if view.ViewTemplateId == DB.ElementId.InvalidElementId:
                add(pr.WARNING, u'Views', u'View "{}" has no view template.'.format(name))
        try:
            fonts |= _fonts(doc, view)
        except Exception:
            log_swallowed(_LOG, u'check_sheet')
    try:
        fonts |= _fonts(doc, sheet)
    except Exception:
        log_swallowed(_LOG, u'check_sheet')
    other = sorted(f for f in fonts if NOSA_FONT.lower() not in f.lower())
    if other:
        add(pr.WARNING, u'Graphics', u'Text or dimensions in a non-NOSA font: {}.'.format(u', '.join(other)))

    try:
        from nosa_utils import general_notes
        if any(getattr(doc.GetElement(p.ViewId), 'Name', None) == general_notes.VIEW_NAME for p in ports):
            for label, on_sheet, wanted in general_notes.differences(doc):
                add(pr.WARNING, u'General notes', u'{}: the sheet says "{}" but Project Information says "{}" '
                                                  u'(Project Setup > General Notes to update).'.format(
                                                      label, on_sheet, wanted))
    except Exception:
        log_swallowed(_LOG, u'check_sheet')

    if tb is not None and scales:
        shown = (_param(tb, 'SHEET_SCALE') or _param(sheet, 'SHEET_SCALE')).strip()
        expected = u'1 : {}'.format(list(scales)[0]) if len(scales) == 1 else u'As indicated'
        normalised = shown.replace(u' ', u'').lower()
        if shown and normalised != expected.replace(u' ', u'').lower():
            add(pr.WARNING, u'Title block', u'Title block scale "{}" but the views are {}.'.format(
                shown, u', '.join(u'1:{}'.format(s) for s in sorted(scales))))
    return out


def check_sheets(doc, sheets):
    """[Finding] for every sheet; sheet numbers are checked for duplicates across the model."""
    from Autodesk.Revit import DB
    counts = {}
    for s in DB.FilteredElementCollector(doc).OfClass(DB.ViewSheet):
        counts[s.SheetNumber] = counts.get(s.SheetNumber, 0) + 1
    findings = []
    for sheet in sheets:
        if isinstance(sheet, DB.ViewSheet):
            try:
                findings.extend(check_sheet(doc, sheet, counts))
            except Exception as e:
                findings.append(Finding(u'{} - {}'.format(sheet.SheetNumber, sheet.Name), pr.ERROR, u'Check',
                                        u'Could not check this sheet: {}'.format(e)))
    return findings
