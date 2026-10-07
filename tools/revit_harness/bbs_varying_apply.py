# -*- coding: utf-8 -*-
"""
Template v30: BBS sub-marks for varying rebar sets (2026-10-05). Varying sets numbered as a whole
with letter suffixes (05A, 05B ...), the BBS sorted by Rebar Number Suffix so each bar is its own
row with real dimensions, and its "Bar mark" column = Schedule Mark + suffix.
Scope: doc, DRY (bool). Result: RESULT.
"""
import clr
clr.AddReference('RevitAPI')
from Autodesk.Revit import DB
from Autodesk.Revit.DB import Structure as DBS
from System.Collections.Generic import List

SUBMARK_SUFFIX = u'a'  # IStructE SMDSC 4.5.1 (D8)

_log = []
if u'template' not in doc.Title:
    raise RuntimeError(u'not the template: ' + doc.Title)

schedule = [v for v in DB.FilteredElementCollector(doc).OfClass(DB.ViewSchedule) if v.Name == u'BBS'][0]
definition = schedule.Definition
settings = DBS.ReinforcementSettings.GetReinforcementSettings(doc)


def field_named(name):
    for i in range(definition.GetFieldCount()):
        f = definition.GetField(i)
        if f.GetName() == name:
            return i, f
    return None, None


t = DB.Transaction(doc, u'NOSA — BBS sub-marks for varying sets')
t.Start()
try:
    if settings.NumberVaryingLengthRebarsIndividually:
        settings.NumberVaryingLengthRebarsIndividually = False
        _log.append(u'varying sets numbered as a whole')
    if settings.RebarVaryingLengthNumberSuffix != SUBMARK_SUFFIX:
        settings.RebarVaryingLengthNumberSuffix = SUBMARK_SUFFIX
        _log.append(u'suffix A, B, C ...')

    _i, suffix = field_named(u'Rebar Number Suffix')
    sorted_ids = [definition.GetSortGroupField(i).FieldId for i in range(definition.GetSortGroupFieldCount())]
    if suffix.FieldId not in sorted_ids:
        definition.AddSortGroupField(DB.ScheduleSortGroupField(suffix.FieldId))
        _log.append(u'sorted by Rebar Number Suffix')

    combined_i, combined = field_named(u'Bar mark (with sub-mark)')
    if combined is None:
        mark_i, mark = field_named(u'Schedule Mark')
        first = DB.TableCellCombinedParameterData.Create()
        first.ParamId = mark.ParameterId
        first.Separator = u''
        second = DB.TableCellCombinedParameterData.Create()
        second.ParamId = suffix.ParameterId
        second.Separator = u''
        combined = definition.InsertCombinedParameterField(
            List[DB.TableCellCombinedParameterData]([first, second]), u'Bar mark (with sub-mark)', mark_i + 1)
        combined.ColumnHeading = mark.ColumnHeading
        combined.GridColumnWidth = mark.GridColumnWidth
        combined.HorizontalAlignment = mark.HorizontalAlignment
        try:
            combined.SetStyle(mark.GetStyle())
        except Exception as e:
            _log.append(u'style not copied: {}'.format(e))
        mark.IsHidden = True       # still sorts the rows
        _log.append(u'"{}" column shows the sub-mark'.format(mark.ColumnHeading.replace(u'\n', u' ')))
except Exception as e:
    _log.append(u'FAILED: {}'.format(e))
    t.RollBack()
    t = None
if t is not None:
    if DRY:
        t.RollBack()
        _log.append(u'dry run: rolled back')
    else:
        t.Commit()
RESULT = u'\n'.join(_log)
