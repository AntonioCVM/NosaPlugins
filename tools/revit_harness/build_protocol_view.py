# -*- coding: utf-8 -*-
"""
T8.23: drafting view "0002 File naming protocols" built from nosa_utils.protocol_rules (the tables the
T8.12 drawing check uses), placed on sheet 0002 instead of the two raster pages of the PDF.
Scope: doc, EXT_ROOT, PYREVIT, DRY (bool: roll back), IMAGE (optional PNG path prefix), REBUILD (bool:
replace an existing view). Result: RESULT.
"""
import sys
import os
import traceback

import clr
clr.AddReference('RevitAPI')
from Autodesk.Revit import DB

for _p in (os.path.join(PYREVIT, 'pyrevitlib'), os.path.join(PYREVIT, 'site-packages'),
           os.path.join(EXT_ROOT, 'lib')):
    if _p not in sys.path:
        sys.path.insert(0, _p)

VIEW_NAME = u'0002 File naming protocols'
SHEET = u'0002'
_MM = 1.0 / 304.8
ROW = 4.2           # mm between rows of 2.0 mm text
HEAD_GAP = 6.0
_log = []

REVISIONS = [(u'P01', u'Preliminary (work in progress, for comment)'),
             (u'I01', u'Information'),
             (u'C01', u'Contractual (for construction)'),
             (u'PC01', u'Post-contractual (after contract award)'),
             (u'P01.01', u'Draft of P01: remove the suffix before a formal issue')]


def _sorted(codes):
    return sorted(codes.items(), key=lambda kv: kv[0])


def run():
    from nosa_utils import protocol_rules as pr
    from nosa_utils import transactions as nosa_tx
    from nosa_utils.revit_helpers import element_name

    def col(cls):
        return list(DB.FilteredElementCollector(doc).OfClass(cls))

    types = dict((element_name(t), t) for t in col(DB.TextNoteType))
    body = types[u'2.0mm Century Gothic']
    head = types[u'2.5mm Century Gothic Bold (schedule text)']
    title = types[u'3.0mm Century Gothic - Schedule Text']
    line_style = None
    for gs in DB.FilteredElementCollector(doc).OfClass(DB.GraphicsStyle):
        if gs.GraphicsStyleCategory is not None and gs.GraphicsStyleCategory.Name == u'Thin Lines':
            line_style = gs

    group = DB.TransactionGroup(doc, u'NOSA — 0002 File naming protocols (T8.23)')
    group.Start()
    collector = nosa_tx.FailureCollector()
    t = DB.Transaction(doc, u'NOSA — 0002 File naming protocols (T8.23)')
    nosa_tx._install(t, collector)
    t.Start()
    try:
        old = [v for v in col(DB.ViewDrafting) if v.Name == VIEW_NAME]
        if old:
            try:
                rebuild = REBUILD
            except NameError:
                rebuild = False
            if not rebuild:
                raise RuntimeError(u'"{}" already exists (pass REBUILD=True to replace it)'.format(VIEW_NAME))
            doc.Delete(old[0].Id)      # its viewport on 0002 goes with it
            doc.Regenerate()
        vft = [v for v in col(DB.ViewFamilyType) if v.ViewFamily == DB.ViewFamily.Drafting][0]
        view = DB.ViewDrafting.Create(doc, vft.Id)
        view.Name = VIEW_NAME
        view.Scale = 1

        def text(x, y, value, ttype=body, width=None):
            opts = DB.TextNoteOptions(ttype.Id)
            opts.HorizontalAlignment = DB.HorizontalTextAlignment.Left
            pt = DB.XYZ(x * _MM, y * _MM, 0)
            if width:
                return DB.TextNote.Create(doc, view.Id, pt, width * _MM, value, opts)
            return DB.TextNote.Create(doc, view.Id, pt, value, opts)

        def rule(x0, x1, y):
            c = doc.Create.NewDetailCurve(view, DB.Line.CreateBound(DB.XYZ(x0 * _MM, y * _MM, 0),
                                                                     DB.XYZ(x1 * _MM, y * _MM, 0)))
            if line_style is not None:
                c.LineStyle = line_style

        def table(x, y, heading, rows, code_w=16.0, desc_w=118.0):
            text(x, y, heading, head, code_w + desc_w)
            y -= HEAD_GAP
            rule(x, x + code_w + desc_w, y + 2.0)
            for code, desc in rows:
                text(x, y, code, body, code_w)
                text(x + code_w, y, desc, body, desc_w)
                y -= ROW
            return y - 4.0

        x1, x2, x3 = 0.0, 155.0, 310.0
        top = 0.0
        text(x1, top, u'NOSA FILE NAMING PROTOCOL  (V2.2 — 00000-NOSA-TN-XXX-T-X-0018-I23)', title, 450)
        y = top - 9.0
        text(x1, y, u'Format:  F1-F2-F3-F4-F5-F6-F7-F8 Description', head, 300)
        y -= 6.0
        text(x1, y, u'Example: 22041-NOSA-DT-ZZZ-D-S-4100-P01 Substructure details', body, 300)
        y -= 10.0
        start = y
        y = table(x1, y, u'F1 Project number (5 digits)',
                  [(u'00000', u'Company-wide documents'), (u'nnnnn', u'Project number')])
        y = table(x1, y, u'F2 Originator (4 characters)', [(pr.ORIGINATOR, u'NOSA — always')])
        y = table(x1, y, u'F3 Functional breakdown (2 characters)', _sorted(pr.F3_CODES))

        y = start
        y = table(x2, y, u'F4 Spatial breakdown (3 characters)', _sorted(pr.F4_CODES))
        y = table(x2, y, u'F5 Form (1 character)', _sorted(pr.F5_CODES))
        y = table(x2, y, u'F6 Discipline (1 character)', _sorted(pr.F6_CODES))

        y = start
        rows = []
        for first, last, label, _f3, _f5 in pr.SERIES:
            rows.append((u'{:04d}'.format(first) if first == last else u'{:04d}–{:04d}'.format(first, last), label))
        y = table(x3, y, u'F7 Document number (4 digits) — NOSA template series', rows, code_w=24.0, desc_w=118.0)
        y = table(x3, y, u'F8 Revision', REVISIONS, code_w=24.0, desc_w=118.0)
        text(x3, y, u'Codes not listed here are allowed when they keep the length of their field; record them in the '
                    u'project BEP. The Sheet Export Hub checks every drawing against these tables before export.',
             body, 142)

        sheet = [s for s in col(DB.ViewSheet) if s.SheetNumber == SHEET][0]
        images = [i for i in DB.FilteredElementCollector(doc, sheet.Id).OfClass(DB.ImageInstance)]
        image_types = set(i.GetTypeId() for i in images)
        centre = DB.XYZ(506.0 * _MM, 221.0 * _MM, 0)
        doc.Regenerate()
        vp = DB.Viewport.Create(doc, sheet.Id, view.Id, centre)
        for vt in DB.FilteredElementCollector(doc).OfClass(DB.ElementType):
            if vt.FamilyName == u'Viewport' and u'no title' in element_name(vt).lower():
                vp.ChangeTypeId(vt.Id)
                break
        for i in images:
            doc.Delete(i.Id)
        for tid in image_types:
            if not any(x.GetTypeId() == tid for x in col(DB.ImageInstance)):
                doc.Delete(tid)
        _log.append(u'view {} created, viewport {} on {}; {} raster pages removed'.format(
            view.Id, element_name(doc.GetElement(vp.GetTypeId())), SHEET, len(images)))
        t.Commit()
        try:
            image = IMAGE
        except NameError:
            image = None
        if image:
            from System.Collections.Generic import List
            opts = DB.ImageExportOptions()
            opts.ExportRange = DB.ExportRange.SetOfViews
            opts.SetViewsAndSheets(List[DB.ElementId]([sheet.Id]))
            opts.FilePath = image
            opts.HLRandWFViewsFileType = DB.ImageFileType.PNG
            opts.ZoomType = DB.ZoomFitType.FitToPage
            opts.PixelSize = 3000
            doc.ExportImage(opts)
    except Exception:
        if t.HasStarted() and not t.HasEnded():
            t.RollBack()
        group.RollBack()
        _log.append(u'EXCEPTION, rolled back:\n' + traceback.format_exc())
        return
    if DRY:
        group.RollBack()
        _log.append(u'DRY RUN: rolled back')
    else:
        _log.append(u'commit: {}'.format(group.Assimilate()))
    if collector.errors:
        _log.append(u'REVIT ERRORS: ' + u' | '.join(collector.errors[:5]))


try:
    run()
except Exception:
    _log.append(traceback.format_exc())
RESULT = u'\n'.join(_log)
