# -*- coding: utf-8 -*-
"""
NOSA.RebarAutomate — the tabular method (T8.54, IStructE SMDSC 4.1.1, 6.4.4, 6.7.4), the rules in
nosa_utils.tabular: each reinforced column and base gets the calling-up of its bars in NOSA_Tab_* parameters and
the references of the members alike in NOSA_Tab_Refs; two Revit schedules ('NOSA Column Schedule', 'NOSA Base
Schedule') list one row per type of member with its number off. bind() outside a transaction, update() in one.
"""
import os

from Autodesk.Revit import DB
from Autodesk.Revit.DB.Structure import RebarHostData, Rebar

from nosa_utils import tabular
from nosa_utils.revit_helpers import element_name, get_id_value

_MM_PER_FT = 304.8
COLUMN_SCHEDULE = u'NOSA Column Schedule'
BASE_SCHEDULE = u'NOSA Base Schedule'
CATEGORIES = ['OST_StructuralColumns', 'OST_StructuralFoundation']


def params_file():
    return os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', 'data',
                                        'shared_parameters', 'NOSA_Tabular.txt'))


def bind(doc):
    """NOSA_Tab_* on Structural Columns and Foundations (idempotent). Outside a transaction."""
    from nosa_utils import shared_params
    return shared_params.ensure_bound(doc, CATEGORIES, params_file())


def _text(el, name):
    p = el.LookupParameter(name)
    return (p.AsString() or u'') if p is not None and p.HasValue else u''


def _set(el, name, value):
    p = el.LookupParameter(name)
    if p is not None and not p.IsReadOnly:
        p.Set(value)


def _sets(doc, host, layers):
    """[(count, dia, mark, spacing or None)] of the host's bars in the given NOSA_Rebar_Layer values."""
    out = []
    data = RebarHostData.GetRebarHostData(host)
    if data is None:
        return out
    for r in data.GetRebarsInHost():
        if not isinstance(r, Rebar) or _text(r, u'NOSA_Rebar_Layer') not in layers:
            continue
        try:
            dia = doc.GetElement(r.GetTypeId()).BarNominalDiameter * _MM_PER_FT
            n = r.NumberOfBarPositions
        except Exception:
            continue
        p = r.get_Parameter(DB.BuiltInParameter.REBAR_ELEM_SCHEDULE_MARK)
        mark = (p.AsString() if p is not None else u'') or _text(r, u'NOSA_Rebar_Mark')
        spacing = None
        if n > 1 and _text(r, u'NOSA_Rebar_Layer') not in (u'vertical',):
            try:
                spacing = r.MaxSpacing * _MM_PER_FT
            except Exception:
                spacing = None
        out.append((n, dia, mark, spacing))
    return out


def _reference(el):
    """A member's reference: its Mark, else its grid location (columns), else its id."""
    p = el.get_Parameter(DB.BuiltInParameter.ALL_MODEL_MARK)
    mark = (p.AsString() or u'') if p is not None else u''
    if mark:
        return mark
    p = el.get_Parameter(DB.BuiltInParameter.COLUMN_LOCATION_MARK)
    loc = (p.AsString() or u'') if p is not None else u''
    return loc or u'{}'.format(get_id_value(el.Id))


def _level_name(doc, el, bip):
    p = el.get_Parameter(bip)
    lvl = doc.GetElement(p.AsElementId()) if p is not None else None
    return element_name(lvl) if lvl is not None else u''


def update(doc):
    """Write the NOSA_Tab_* parameters of every reinforced column and base. Returns (columns, bases, groups)."""
    members = {u'column': [], u'base': []}
    for cat, kind in ((DB.BuiltInCategory.OST_StructuralColumns, u'column'),
                      (DB.BuiltInCategory.OST_StructuralFoundation, u'base')):
        for el in DB.FilteredElementCollector(doc).OfCategory(cat).WhereElementIsNotElementType():
            data = RebarHostData.GetRebarHostData(el)
            if data is None or not list(data.GetRebarsInHost()):
                continue
            type_name = element_name(doc.GetElement(el.GetTypeId()))
            if kind == u'column':
                main = tabular.summarise(_sets(doc, el, (u'vertical',)))
                links = tabular.summarise(_sets(doc, el, (u'stirrup', u'crosstie')))
                _set(el, u'NOSA_Tab_Main_Bars', main)
                _set(el, u'NOSA_Tab_Links', links)
                sig = (type_name, _level_name(doc, el, DB.BuiltInParameter.FAMILY_BASE_LEVEL_PARAM),
                       _level_name(doc, el, DB.BuiltInParameter.FAMILY_TOP_LEVEL_PARAM), main, links)
            else:
                steel = u' / '.join(t for t in (tabular.summarise(_sets(doc, el, (u'bottom_x',))),
                                               tabular.summarise(_sets(doc, el, (u'bottom_y',)))) if t)
                starters = tabular.summarise(_sets(doc, el, (u'foundation_starter', u'dowel', u'starter_link')))
                _set(el, u'NOSA_Tab_Base_Steel', steel)
                _set(el, u'NOSA_Tab_Starters', starters)
                sig = (type_name, _level_name(doc, el, DB.BuiltInParameter.FAMILY_LEVEL_PARAM), steel, starters)
            members[kind].append((el, _reference(el), sig))
    n_groups = 0
    for kind, items in members.items():
        rows = tabular.groups([(ref, sig) for _el, ref, sig in items])
        n_groups += len(rows)
        refs_of = dict((sig, tabular.references_text(refs)) for sig, refs in rows)
        for el, _ref, sig in items:
            _set(el, u'NOSA_Tab_Refs', refs_of[sig])
    return len(members[u'column']), len(members[u'base']), n_groups


def _schedule(doc, name, category, fields, group_by):
    for v in DB.FilteredElementCollector(doc).OfClass(DB.ViewSchedule):
        if element_name(v) == name:
            return v
    schedule = DB.ViewSchedule.CreateSchedule(doc, DB.ElementId(category))
    schedule.Name = name
    definition = schedule.Definition
    by_name = {}
    for sf in definition.GetSchedulableFields():
        by_name.setdefault(sf.GetName(doc), sf)
    added = {}
    for field_name, heading in fields:
        sf = by_name.get(field_name)
        if sf is None:
            continue
        added[field_name] = definition.AddField(sf)
        if heading:
            added[field_name].ColumnHeading = heading
    if u'NOSA_Tab_Refs' in added:
        definition.AddFilter(DB.ScheduleFilter(added[u'NOSA_Tab_Refs'].FieldId, DB.ScheduleFilterType.HasValue))
    for field_name in group_by:
        if field_name in added:
            definition.AddSortGroupField(DB.ScheduleSortGroupField(added[field_name].FieldId))
    definition.IsItemized = False
    return schedule


def ensure_schedules(doc):
    """
    The column and base schedules of SMDSC 6.4.4 / 6.7.4, made on first use: [ViewSchedule]. One row per
    NOSA_Tab_Refs: the members alike share it, so it groups them by itself (Revit takes at most 4 grouping fields).
    """
    columns = _schedule(doc, COLUMN_SCHEDULE, DB.BuiltInCategory.OST_StructuralColumns, (
        (u'NOSA_Tab_Refs', u'Column reference'), (u'Count', u'No off'), (u'Base Level', u'Level A'),
        (u'Top Level', u'Level B'), (u'Type', u'Section'), (u'NOSA_Tab_Main_Bars', u'Main bars'),
        (u'NOSA_Tab_Links', u'Links')),
        (u'NOSA_Tab_Refs',))
    bases = _schedule(doc, BASE_SCHEDULE, DB.BuiltInCategory.OST_StructuralFoundation, (
        (u'NOSA_Tab_Refs', u'Column reference'), (u'Count', u'No off'), (u'Level', u'Base level'),
        (u'Type', u'Base'), (u'NOSA_Tab_Base_Steel', u'Base steel'), (u'NOSA_Tab_Starters', u'Starters')),
        (u'NOSA_Tab_Refs',))
    return [columns, bases]
