# -*- coding: utf-8 -*-
"""
Template v30 (T8.31/T8.32, 2026-10-07): create the RC layer notation and reinforcement notes legends
with RebarAutomate's own rc_legends, optionally placing them on a sheet (SHEET number) or removing
their viewports from it (UNPLACE). Scope: doc, LIB (RebarAutomate lib dir), SHEET, UNPLACE. Result: RESULT.
"""
import sys
import clr
clr.AddReference('RevitAPI')
from Autodesk.Revit import DB

if u'template' not in doc.Title:
    raise RuntimeError(u'not the template: ' + doc.Title)
for p in (LIB, LIB + u'\\..\\..\\..\\..\\lib'):
    if p not in sys.path:
        sys.path.insert(0, p)
for name in [m for m in sys.modules if m == 'rc_legends']:
    del sys.modules[name]
import rc_legends


class _Rollback(DB.IFailuresPreprocessor):
    def __init__(self):
        self.errors = []

    def PreprocessFailures(self, accessor):
        accessor.DeleteAllWarnings()
        errors = [f for f in accessor.GetFailureMessages() if f.GetSeverity() != DB.FailureSeverity.Warning]
        if not errors:
            return DB.FailureProcessingResult.Continue
        self.errors.extend(f.GetDescriptionText() for f in errors)
        return DB.FailureProcessingResult.ProceedWithRollBack


_log = []
guard = _Rollback()
t = DB.Transaction(doc, u'NOSA — RC drawing legends (SMDSC 3.7, 4.2.1)')
opts = t.GetFailureHandlingOptions()
opts.SetFailuresPreprocessor(guard)
opts.SetClearAfterRollback(True)
opts.SetForcedModalHandling(False)
t.SetFailureHandlingOptions(opts)
t.Start()
try:
    legends = rc_legends.ensure(doc)
    _log.append(u'legends: ' + u', '.join(u'{} #{} 1:{}'.format(v.Name, v.Id, v.Scale) for v in legends))
    sheet = None
    if SHEET:
        sheet = [s for s in DB.FilteredElementCollector(doc).OfClass(DB.ViewSheet) if s.SheetNumber == SHEET][0]
    ids = set(v.Id for v in legends)
    if sheet is not None and UNPLACE:
        for vp in [doc.GetElement(i) for i in sheet.GetAllViewports()]:
            if vp.ViewId in ids:
                doc.Delete(vp.Id)
                _log.append(u'removed from ' + SHEET)
    elif sheet is not None:
        for port in rc_legends.place(doc, sheet, legends):
            box = port.GetBoxOutline()
            _log.append(u'placed {:.0f},{:.0f} - {:.0f},{:.0f}'.format(
                box.MinimumPoint.X * 304.8, box.MinimumPoint.Y * 304.8,
                box.MaximumPoint.X * 304.8, box.MaximumPoint.Y * 304.8))
    status = t.Commit()
    _log.append(u'commit: {} {}'.format(status, u'; '.join(guard.errors)))
except Exception as e:
    import traceback
    if t.HasStarted() and not t.HasEnded():
        t.RollBack()
    _log.append(u'ERROR ' + traceback.format_exc())
RESULT = u'\n'.join(_log)
