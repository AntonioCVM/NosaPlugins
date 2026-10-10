# -*- coding: utf-8 -*-
"""
T8.27 visual test model in an unsaved test project (never the template): Create Views (with sheets and tags,
so the SMDSC 6.2.2 presentation runs) for the hosts in IDS, then a summary of what each view carries.
Scope: doc, EXT_ROOT, IDS. Result: RESULT.
"""
import sys
import os
import clr
clr.AddReference('RevitAPI')
from Autodesk.Revit import DB

if doc.PathName or u'template' in doc.Title:
    raise RuntimeError(u'not an unsaved test project: ' + doc.Title)
LIB = os.path.join(EXT_ROOT, 'NOSA.tab', 'Reinforcement.panel', 'RebarAutomate.pushbutton', 'lib')
for p in (LIB, os.path.join(EXT_ROOT, 'lib')):
    if p not in sys.path:
        sys.path.insert(0, p)
for name in ('rebar_views', 'rebar_presentation', 'rebar_detailing', 'view_plan'):
    sys.modules.pop(name, None)
import rebar_engine as re_engine
import rebar_detailing
import view_plan
import rebar_views
import beam_rebar
from nosa_utils.revit_helpers import element_id_from_int, element_name

_log = []
try:
    groups = [[doc.GetElement(element_id_from_int(i)) for i in ids] for ids in IDS]
    existing = [s.SheetNumber for s in DB.FilteredElementCollector(doc).OfClass(DB.ViewSheet)]
    numbers = view_plan.next_sheet_numbers(existing, 30)
    for hosts in groups:
        report = rebar_views.build_element_views(doc, hosts, re_engine, rebar_detailing, view_plan, numbers,
                                                 beam_rebar=beam_rebar, place_on_sheets=True, tag=True)
        _log.append(u'views {} sheets {} tags {} errors {}'.format(report['views'], report['sheets'], report['tags'],
                                                                 report['errors']))
    for view in DB.FilteredElementCollector(doc).OfClass(DB.View):
        if view.IsTemplate or not element_name(view).startswith((u'Slab', u'Beam', u'Floor')):
            continue
        notes = [n.Text.strip() for n in DB.FilteredElementCollector(doc, view.Id).OfClass(DB.TextNote)]
        mras = DB.FilteredElementCollector(doc, view.Id).OfClass(DB.MultiReferenceAnnotation).GetElementCount()
        tags = DB.FilteredElementCollector(doc, view.Id).OfClass(DB.IndependentTag).GetElementCount()
        lines = DB.FilteredElementCollector(doc, view.Id).OfClass(DB.CurveElement).GetElementCount()
        _log.append(u'{} [{}]: MRA {} tags {} detail lines {} notes {}'.format(
            element_name(view), view.Id, mras, tags, lines, notes))
except Exception:
    import traceback
    _log.append(u'EXCEPTION ' + traceback.format_exc())
RESULT = u'\n'.join(_log)
