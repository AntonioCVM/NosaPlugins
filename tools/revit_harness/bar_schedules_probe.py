# -*- coding: utf-8 -*-
"""
T8.33/T8.34 live probe (inside the caller's TransactionGroup, rolled back by it): Create Views with
sheets (no tags) for IDS, then the A4 bar schedules; dumps the report and each schedule's rows.
Scope: doc, EXT_ROOT, IDS. Result: RESULT.
"""
import sys
import os
import clr
clr.AddReference('RevitAPI')
from Autodesk.Revit import DB

if u'template' not in doc.Title:
    raise RuntimeError(u'not the template: ' + doc.Title)
LIB = os.path.join(EXT_ROOT, 'NOSA.tab', 'Reinforcement.panel', 'RebarAutomate.pushbutton', 'lib')
for p in (LIB, os.path.join(EXT_ROOT, 'lib')):
    if p not in sys.path:
        sys.path.insert(0, p)
for name in ('rebar_views', 'bar_schedules', 'rc_legends', 'view_plan', 'rebar_schedule'):
    sys.modules.pop(name, None)
import rebar_engine as re_engine
import rebar_detailing
import view_plan
import rebar_views
import bar_schedules
from nosa_utils.revit_helpers import element_id_from_int, element_name
from nosa_utils import transactions as nosa_tx

_log = []
try:
    hosts = [doc.GetElement(element_id_from_int(i)) for i in IDS]
    existing = [s.SheetNumber for s in DB.FilteredElementCollector(doc).OfClass(DB.ViewSheet)]
    numbers = view_plan.next_sheet_numbers(existing, 10)
    report = rebar_views.build_element_views(doc, hosts, re_engine, rebar_detailing, view_plan, numbers,
                                             place_on_sheets=True, tag=False)
    _log.append(u'views {} sheets {} errors {}'.format(report['views'], report['sheets'], report['errors']))
    rebars = rebar_views.host_rebars(hosts[0])
    _log.append(u'drawing on rebars: {}'.format(sorted(set(bar_schedules._text(r, bar_schedules.DRAWING_PARAM) for r in rebars))))
    with nosa_tx.revit_transaction(u'NOSA — A4 Bar Schedules'):
        rep = bar_schedules.create(doc)
    _log.append(u'schedules {}'.format(rep))
    for view in DB.FilteredElementCollector(doc).OfClass(DB.ViewSchedule):
        if element_name(view).startswith(u'BBS '):
            body = view.GetTableData().GetSectionData(DB.SectionType.Body)
            _log.append(u'== {} rows {}'.format(element_name(view), body.NumberOfRows))
            for row in range(min(body.NumberOfRows, 8)):
                _log.append(u'  ' + u'|'.join(u' '.join(view.GetCellText(DB.SectionType.Body, row, c).split())
                                              for c in range(body.NumberOfColumns)))
    for sheet in DB.FilteredElementCollector(doc).OfClass(DB.ViewSheet):
        ref = bar_schedules._text(sheet, u'NOSA_BBS_Ref')
        if ref:
            _log.append(u'sheet {} "{}" ref {} drawing {} status {}'.format(
                sheet.SheetNumber, sheet.Name, ref, bar_schedules._text(sheet, u'NOSA_BBS_Drawing'),
                bar_schedules._text(sheet, u'NOSA_BBS_Status')))
            _log.append(u'  sheet id {}'.format(sheet.Id))
except Exception:
    import traceback
    _log.append(u'EXCEPTION ' + traceback.format_exc())
RESULT = u'\n'.join(_log)
