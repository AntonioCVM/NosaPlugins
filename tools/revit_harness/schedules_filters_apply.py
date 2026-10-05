# -*- coding: utf-8 -*-
"""
Template schedules filters (user 2026-10-05): concrete takeoffs = every material not in a non-concrete
NOSA_Material_Group (blank / <By Category> included, piles out), per category where the title says so;
Steelwork weight = "Structural steel"; Piling Schedule = pile families only (nested ones too); foundation
schedules without piles. Scope: doc, EXT_ROOT, PYREVIT, DRY (bool). Result: RESULT.
"""
import os
import sys
import traceback

import clr
clr.AddReference('RevitAPI')
from Autodesk.Revit import DB

for _p in (os.path.join(PYREVIT, 'pyrevitlib'), os.path.join(PYREVIT, 'site-packages'),
           os.path.join(EXT_ROOT, 'lib')):
    if _p not in sys.path:
        sys.path.insert(0, _p)

CONCRETE_ALL = [u'CONCRETE VOLUMES', u'Total concrete volumes']
BY_CATEGORY = {
    u'Concrete volume estimation - RC Beams': 'OST_StructuralFraming',
    u'Concrete volume estimation - RC Columns': 'OST_StructuralColumns',
    u'Concrete volume estimation - RC Floors': 'OST_Floors',
    u'Concrete volume estimation - RC Foundation': 'OST_StructuralFoundation',
    u'Concrete volume estimation - RC Staircases': 'OST_Stairs',
    u'Concrete volume estimation - RC Walls': 'OST_Walls',
    u'Rebar estimation - RC Beams': 'OST_StructuralFraming',
    u'Rebar estimation - RC Floors': 'OST_Floors',
    u'Rebar estimation - RC Staircases': 'OST_Stairs',
    u'Rebar estimation - RC Walls': 'OST_Walls',
}
FOUNDATIONS_NO_PILES = [u'Foundation types Schedule', u'Individual Foundation Schedule',
                        u'Rebar estimation - RC Foundation']
_log = []


def run():
    from nosa_utils import material_groups as mg
    from nosa_utils import transactions as nosa_tx

    group_name = u'Material: ' + mg.PARAM

    def field(d, name, add_hidden=True):
        for i in range(d.GetFieldCount()):
            f = d.GetField(i)
            if f.GetName() == name:
                return f
        if not add_hidden:
            return None
        for sf in d.GetSchedulableFields():
            if sf.GetName(doc) == name:
                f = d.AddField(sf)
                f.IsHidden = True
                return f
        raise RuntimeError(u'field "{}" not schedulable'.format(name))

    def concrete_filters(d):
        g = field(d, group_name)
        return [DB.ScheduleFilter(g.FieldId, DB.ScheduleFilterType.NotEqual, v) for v in mg.NON_CONCRETE]

    def set_filters(s, filters):
        d = s.Definition
        d.ClearFilters()
        for f in filters:
            d.AddFilter(f)
        _log.append(u'{}: {} filter(s)'.format(s.Name, len(filters)))

    schedules = dict((s.Name, s) for s in DB.FilteredElementCollector(doc).OfClass(DB.ViewSchedule))
    t = DB.Transaction(doc, u'NOSA — Schedule filters (concrete, steel, piles)')
    collector = nosa_tx.FailureCollector()
    nosa_tx._install(t, collector)
    t.Start()
    try:
        for name in CONCRETE_ALL:
            set_filters(schedules[name], concrete_filters(schedules[name].Definition))
        total = schedules[u'Total concrete volumes'].Definition
        for i in reversed(range(total.GetSortGroupFieldCount())):
            sg = total.GetSortGroupField(i)
            if total.GetField(sg.FieldId).GetName() == u'Family':
                total.RemoveSortGroupField(i)
            else:
                sg.ShowHeader = False
                sg.ShowFooter = False
                total.SetSortGroupField(i, sg)
        total.ShowGrandTotal = True
        total.ShowGrandTotalTitle = True
        _log.append(u'Total concrete volumes: one row per material + grand total')
        for name, bic in sorted(BY_CATEGORY.items()):
            d = schedules[name].Definition
            cat = field(d, u'Category')
            cat_id = DB.Category.GetCategory(doc, getattr(DB.BuiltInCategory, bic)).Id
            set_filters(schedules[name], [DB.ScheduleFilter(cat.FieldId, DB.ScheduleFilterType.Equal, cat_id)] +
                        concrete_filters(d))
        steel = schedules[u'Steelwork weight']
        set_filters(steel, [DB.ScheduleFilter(field(steel.Definition, group_name).FieldId,
                                              DB.ScheduleFilterType.Equal, mg.STEEL)])
        piling = schedules[u'Piling Schedule']
        fam = field(piling.Definition, u'Family')
        set_filters(piling, [DB.ScheduleFilter(fam.FieldId, DB.ScheduleFilterType.Contains, u'Pile'),
                             DB.ScheduleFilter(fam.FieldId, DB.ScheduleFilterType.NotContains, u'Cap')])
        for name in FOUNDATIONS_NO_PILES:
            s = schedules[name]
            fam = field(s.Definition, u'Family')
            set_filters(s, [DB.ScheduleFilter(fam.FieldId, DB.ScheduleFilterType.NotContains, u'Pile-'),
                            DB.ScheduleFilter(fam.FieldId, DB.ScheduleFilterType.NotContains, u'piling')])
    except Exception:
        t.RollBack()
        _log.append(u'EXCEPTION, rolled back:\n' + traceback.format_exc())
        return
    if DRY:
        t.RollBack()
        _log.append(u'DRY RUN: rolled back')
    else:
        _log.append(u'commit: {}'.format(t.Commit()))
    if collector.errors:
        _log.append(u'REVIT ERRORS: ' + u' | '.join(collector.errors))


try:
    run()
except Exception:
    _log.append(traceback.format_exc())
RESULT = u'\n'.join(_log)
