# -*- coding: utf-8 -*-
"""
Sheet 0003 "NOSA standards": the drafting views NOSA colours, Lines and Symbols plus the loose font
samples on the sheet merged into one drafting view "0003 NOSA standards" at the same sheet positions;
the old viewports and views are deleted. Scope: doc, EXT_ROOT, PYREVIT, DRY (bool: roll back),
IMAGE (optional PNG path prefix for the sheet before/after). Result: RESULT.
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

SHEET = u'0003'
VIEW_NAME = u'0003 NOSA standards'
SOURCES = (u'NOSA colours', u'Lines', u'Symbols')
_log = []


def export(sheet, suffix):
    try:
        prefix = IMAGE
    except NameError:
        prefix = None
    if not prefix:
        return
    from System.Collections.Generic import List
    opts = DB.ImageExportOptions()
    opts.ExportRange = DB.ExportRange.SetOfViews
    opts.SetViewsAndSheets(List[DB.ElementId]([sheet.Id]))
    opts.FilePath = prefix + suffix
    opts.HLRandWFViewsFileType = DB.ImageFileType.PNG
    opts.ZoomType = DB.ZoomFitType.FitToPage
    opts.PixelSize = 2400
    doc.ExportImage(opts)


def run():
    from System.Collections.Generic import List
    from nosa_utils import transactions as nosa_tx

    sheet = [s for s in DB.FilteredElementCollector(doc).OfClass(DB.ViewSheet) if s.SheetNumber == SHEET][0]
    export(sheet, u' before')
    viewports = [doc.GetElement(i) for i in sheet.GetAllViewports()]
    sources = [(vp, doc.GetElement(vp.ViewId)) for vp in viewports if doc.GetElement(vp.ViewId).Name in SOURCES]
    if len(sources) != len(SOURCES):
        raise RuntimeError(u'expected {} viewports, found {}'.format(SOURCES, [v.Name for _vp, v in sources]))
    scale = sources[0][1].Scale
    if any(v.Scale != scale for _vp, v in sources):
        raise RuntimeError(u'the three views do not share one scale')
    vp_type = sources[0][0].GetTypeId()
    loose = list(DB.FilteredElementCollector(doc, sheet.Id).OfClass(DB.TextNote))

    group = DB.TransactionGroup(doc, u'NOSA — Merge 0003 NOSA standards')
    group.Start()
    collector = nosa_tx.FailureCollector()
    t = DB.Transaction(doc, u'NOSA — Merge 0003 NOSA standards')
    nosa_tx._install(t, collector)
    t.Start()
    try:
        vft = [v for v in DB.FilteredElementCollector(doc).OfClass(DB.ViewFamilyType)
               if v.ViewFamily == DB.ViewFamily.Drafting][0]
        target = DB.ViewDrafting.Create(doc, vft.Id)
        target.Name = VIEW_NAME
        target.Scale = scale
        everything = list(DB.FilteredElementCollector(doc).WhereElementIsNotElementType())
        copied = overridden = 0
        for vp, view in sources:
            kinds = (DB.FilledRegion, DB.CurveElement, DB.TextNote, DB.Dimension, DB.FamilyInstance,
                     DB.IndependentTag, DB.Group, DB.ImageInstance)
            mine = [e for e in everything if e.OwnerViewId == view.Id and e.Category is not None and
                    isinstance(e, kinds) and
                    e.Category.Id.IntegerValue != int(DB.BuiltInCategory.OST_SketchLines)]  # nosa-lint: disable=NOSA002 - runs in Revit
            owned = set()         # boundary sketches of filled regions travel with their region
            for e in mine:
                if isinstance(e, DB.FilledRegion):
                    owned.update(i.IntegerValue for i in e.GetDependentElements(None) if i != e.Id)
            mine = [e for e in mine if e.Id.IntegerValue not in owned]
            ids = [e.Id for e in mine]
            boxes = [e.get_BoundingBox(view) for e in mine]
            boxes = [b for b in boxes if b is not None]
            cx = (min(b.Min.X for b in boxes) + max(b.Max.X for b in boxes)) / 2.0
            cy = (min(b.Min.Y for b in boxes) + max(b.Max.Y for b in boxes)) / 2.0
            centre = vp.GetBoxCenter()
            move = DB.Transform.CreateTranslation(DB.XYZ(centre.X * scale - cx, centre.Y * scale - cy, 0))
            new = DB.ElementTransformUtils.CopyElements(view, List[DB.ElementId](ids), target, move,
                                                        DB.CopyPasteOptions())
            copied += new.Count
            # per-element graphic overrides (halftone swatches) stay with the old view: match by position
            news = [doc.GetElement(i) for i in new]
            doc.Regenerate()
            for e in mine:
                ogs = view.GetElementOverrides(e.Id)
                if not (ogs.Halftone or ogs.ProjectionLineColor.IsValid or ogs.SurfaceForegroundPatternColor.IsValid
                        or ogs.Transparency or ogs.ProjectionLinePatternId != DB.ElementId.InvalidElementId
                        or ogs.SurfaceForegroundPatternId != DB.ElementId.InvalidElementId):
                    continue
                b = e.get_BoundingBox(view)
                want = move.OfPoint((b.Min + b.Max) * 0.5)
                for n in news:
                    nb = n.get_BoundingBox(target) if n.GetType() == e.GetType() else None
                    if nb is not None and ((nb.Min + nb.Max) * 0.5).DistanceTo(want) < 1e-3:
                        target.SetElementOverrides(n.Id, ogs)
                        overridden += 1
                        break
            _log.append(u'{}: {} elements copied'.format(view.Name, new.Count))
        for note in loose:
            p = note.Coord
            opts = DB.TextNoteOptions(note.GetTypeId())
            opts.HorizontalAlignment = note.HorizontalAlignment
            n = DB.TextNote.Create(doc, target.Id, DB.XYZ(p.X * scale, p.Y * scale, 0), note.Text, opts)
            try:
                n.Width = note.Width * scale
            except Exception:
                _log.append(u'  kept the default width for "{}"'.format(note.Text.strip()))
            n.SetFormattedText(note.GetFormattedText())
        _log.append(u'{} loose text notes moved into the view; {} element overrides carried over'.format(
            len(loose), overridden))
        doc.Regenerate()
        boxes = [e.get_BoundingBox(target) for e in DB.FilteredElementCollector(doc, target.Id)
                 .WhereElementIsNotElementType() if e.Category is not None]
        boxes = [b for b in boxes if b is not None]
        cx = (min(b.Min.X for b in boxes) + max(b.Max.X for b in boxes)) / 2.0
        cy = (min(b.Min.Y for b in boxes) + max(b.Max.Y for b in boxes)) / 2.0
        for note in loose:
            doc.Delete(note.Id)
        for _vp, view in sources:
            doc.Delete(view.Id)        # removes its viewport too
        vp = DB.Viewport.Create(doc, sheet.Id, target.Id, DB.XYZ(cx / scale, cy / scale, 0))
        vp.ChangeTypeId(vp_type)
        doc.Regenerate()
        # the viewport box centre is the view extents centre: nudge if Revit padded the box
        shift = DB.XYZ(cx / scale, cy / scale, 0) - vp.GetBoxCenter()
        if shift.GetLength() > 1e-6:
            vp.SetBoxCenter(vp.GetBoxCenter() + shift)
        _log.append(u'view {} placed on {}, {} elements'.format(target.Id, SHEET, copied + len(loose)))
        t.Commit()
        export(sheet, u' after')
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
    if collector.warnings:
        _log.append(u'warnings: ' + u' | '.join(sorted(set(collector.warnings))[:5]))
    if collector.errors:
        _log.append(u'REVIT ERRORS: ' + u' | '.join(collector.errors[:5]))


try:
    run()
except Exception:
    _log.append(traceback.format_exc())
RESULT = u'\n'.join(_log)
