# -*- coding: utf-8 -*-
"""
NOSA.RebarAutomate — A4 bar schedules (T8.33/T8.34, IStructE SMDSC 4.5.1, BS 8666:2020).

Each reinforcement drawing gets its own schedules, separate A4 sheets numbered 01, 02 ... per
drawing; the schedule reference is drawing + schedule + revision (4002-01-A, user decision
2026-10-07). Members (partitions) stay whole on one schedule, listed level by level. Every A4
schedule is the template's BBS filtered by its reference, on a 5500-series sheet whose header
(NOSA_BBS_*) the plugin fills. Rebars carry the drawing in NOSA_Rebar_Group (set by Create Views)
and the schedule key in NOSA_Rebar_Assembly.
"""
from __future__ import absolute_import, division, print_function, unicode_literals
import os
import re

SHEET_SERIES = 5500
DEFAULT_STATUS = u'P'
ROWS_PER_A4 = 46            # body rows of the template BBS that fit the A4 BBS title block (live 2026-10-07)
MASTER_BBS = u'BBS'
TITLEBLOCK = u'NOSA_TitleBlock_A4 for Rebar Schedule'
DRAWING_PARAM = u'NOSA_Rebar_Group'       # on rebars: the drawing the member is detailed on
SCHEDULE_PARAM = u'NOSA_Rebar_Assembly'   # on rebars: the schedule key 4002-01
SHEET_PARAMS = (u'NOSA_BBS_Drawing', u'NOSA_BBS_Ref', u'NOSA_BBS_Revision', u'NOSA_BBS_Status')
SCHEDULE_ORIGIN_MM = (7.8, 261.9)        # top-left corner of the A4 frame; the template BBS is 199 mm, its full width


def schedule_key(drawing, number):
    """'4002', 1 -> '4002-01': the reference without its revision letter (sheet and filter key)."""
    return u'{}-{:02d}'.format(drawing, int(number))


def schedule_ref(key, revision):
    """'4002-01', 'A' -> '4002-01-A' (SMDSC 4.5.1: last character reserved for the revision)."""
    revision = (revision or u'').strip()
    return u'{}-{}'.format(key, revision) if revision else key


def natural_key(text):
    """'C10' after 'C9', 'B2-1' after 'B1-12': digit runs compared as numbers."""
    return [int(part) if part.isdigit() else part.lower() for part in re.split(r'(\d+)', text or u'')]


def pack(members, capacity=ROWS_PER_A4):
    """
    [(member, rows)] in schedule order -> [[member, ...], ...] one list per A4 schedule. A member
    is never split; one longer than a page gets a schedule of its own (Revit lets it run on).
    """
    schedules, current, used = [], [], 0
    for member, rows in members:
        need = rows + 1   # the member's header row in the BBS
        if current and used + need > capacity:
            schedules.append(current)
            current, used = [], 0
        current.append(member)
        used += need
    if current:
        schedules.append(current)
    return schedules


def plan(drawings, capacity=ROWS_PER_A4):
    """
    {drawing: [(level elevation, member, rows)]} -> {member: schedule key}, schedules numbered
    01, 02 ... per drawing, members level by level then in natural order (SMDSC 4.5.1).
    """
    out = {}
    for drawing in sorted(drawings, key=natural_key):
        ordered = sorted(drawings[drawing], key=lambda m: (m[0], natural_key(m[1])))
        for n, members in enumerate(pack([(m[1], m[2]) for m in ordered], capacity), start=1):
            for member in members:
                out[member] = schedule_key(drawing, n)
    return out


def schedule_marks(bars):
    """
    SMDSC 4.5.1 / D9: marks unique within a schedule. bars: [(member order, old mark number,
    identity key, bar id)] of ONE schedule -> {bar id: new number}: 1, 2 ... in member order then
    old mark order; identical bars (same identity key) share a number across members.
    """
    numbers, out = {}, {}
    for _order, _old, key, bar in sorted(bars, key=lambda b: (b[0], b[1])):
        if key not in numbers:
            numbers[key] = len(numbers) + 1
        out[bar] = numbers[key]
    return out


def params_file():
    return os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', 'data',
                                        'shared_parameters', 'NOSA_BarSchedules.txt'))


# ── Revit side ──────────────────────────────────────────────────────────────────────────────────

def bind(doc):
    """NOSA_BBS_* on Sheets (idempotent). Call outside a transaction."""
    from nosa_utils import shared_params
    return shared_params.ensure_bound(doc, ['OST_Sheets'], params_file())


def _text(element, name):
    p = element.LookupParameter(name)
    return (p.AsString() or u'') if p is not None and p.HasValue else u''


def _set(element, name, value):
    p = element.LookupParameter(name)
    if p is None or p.IsReadOnly:
        return False
    if (p.AsString() or u'') != value:
        p.Set(value)
    return True


def stamp_drawing(doc, rebars, drawing):
    """
    Create Views: the drawing a member is detailed on, kept from its first drawing while that sheet
    exists (a deleted one gives way to the new drawing). In a transaction.
    """
    from Autodesk.Revit import DB  # Lazy import
    sheets = set(s.SheetNumber for s in DB.FilteredElementCollector(doc).OfClass(DB.ViewSheet))
    n = 0
    for rebar in rebars:
        old = _text(rebar, DRAWING_PARAM)
        if (not old or old not in sheets) and old != drawing and _set(rebar, DRAWING_PARAM, drawing):
            n += 1
    return n


def _members(doc):
    """{drawing: {member: (level elevation, rows, [rebar])}} of the scheduled NOSA rebars."""
    from Autodesk.Revit import DB  # Lazy import
    import rebar_schedule
    out = {}
    marks = {}
    for rid in rebar_schedule.collect_rebars(doc):
        rebar = doc.GetElement(rid)
        drawing = _text(rebar, DRAWING_PARAM)
        if not drawing:
            continue
        member = rebar_schedule._partition_of(rebar)
        host = doc.GetElement(rebar.GetHostId())
        level = None
        try:
            level = doc.GetElement(host.LevelId) if host is not None else None
        except Exception:  # nosa-lint: disable=NOSA006 - a host without a level sorts first
            level = None
        elevation = level.Elevation if isinstance(level, DB.Level) else 0.0
        entry = out.setdefault(drawing, {}).setdefault(member, [elevation, 0, []])
        entry[0] = min(entry[0], elevation)
        entry[2].append(rebar)
        marks.setdefault((drawing, member), set()).add(_text(rebar, u'NOSA_Rebar_Mark'))
    for (drawing, member), found in marks.items():
        out[drawing][member][1] = len(found)
    return out


def _rows_per_member(doc):
    """{member: BBS rows}: one per mark, one per bar of a varying set (as the Revit BBS lists them)."""
    import rebar_schedule
    rows = {}
    for row in rebar_schedule.generate_schedule_data(doc):
        rows[row.get('member') or u''] = rows.get(row.get('member') or u'', 0) + 1
    return rows


def _renumber(doc, members, keys, order):
    """Give each schedule's bars marks unique within it (rebar_marking keeps per-member ones before)."""
    from Autodesk.Revit import DB  # Lazy import
    import rebar_marking
    from nosa_utils.revit_helpers import get_id_value
    per_schedule = {}
    for found in members.values():
        for name, entry in found.items():
            for rebar in entry[2]:
                varying = _text(rebar, u'NOSA_Rebar_Mark_Suffix') != u''
                try:
                    identity = rebar_marking._dedup_key(doc, rebar, 5.0, varying)
                except Exception:  # nosa-lint: disable=NOSA006 - unreadable bar: a mark of its own
                    identity = ('bar', get_id_value(rebar.Id))
                per_schedule.setdefault(keys[name], []).append(
                    (order[name], rebar_marking.mark_number(_text(rebar, u'NOSA_Rebar_Mark')), identity, rebar))
    changed = 0
    for bars in per_schedule.values():
        for rebar, number in schedule_marks(bars).items():
            mark = rebar_marking.format_mark(number)
            if _text(rebar, u'NOSA_Rebar_Mark') == mark:
                continue
            _set(rebar, u'NOSA_Rebar_Mark', mark)
            p = rebar.LookupParameter(u'NOSA_Rebar_Number')
            if p is not None and not p.IsReadOnly:
                p.Set(number)
            native = rebar.get_Parameter(DB.BuiltInParameter.REBAR_ELEM_SCHEDULE_MARK)
            if native is not None and not native.IsReadOnly:
                native.Set(mark)
            changed += 1
    return changed


def _schedulable_field(definition, doc, name):
    for sf in definition.GetSchedulableFields():
        if sf.GetName(doc) == name:
            return sf
    return None


def _field_index(definition, name):
    for i in range(definition.GetFieldCount()):
        if definition.GetField(i).GetName() == name:
            return i
    return None


def _schedule_view(doc, master, key):
    """'BBS 4002-01': the master BBS duplicated and filtered to this schedule key."""
    from Autodesk.Revit import DB  # Lazy import
    from nosa_utils.revit_helpers import element_name
    name = u'{} {}'.format(MASTER_BBS, key)
    for view in DB.FilteredElementCollector(doc).OfClass(DB.ViewSchedule):
        if element_name(view) == name:
            return view, False
    view = doc.GetElement(master.Duplicate(DB.ViewDuplicateOption.Duplicate))
    view.Name = name
    definition = view.Definition
    index = _field_index(definition, SCHEDULE_PARAM)
    if index is None:
        sf = _schedulable_field(definition, doc, SCHEDULE_PARAM)
        if sf is None:
            raise ValueError(u'{} is not a rebar parameter in this project.'.format(SCHEDULE_PARAM))
        field = definition.AddField(sf)
        field.IsHidden = True
    else:
        field = definition.GetField(index)
    definition.AddFilter(DB.ScheduleFilter(field.FieldId, DB.ScheduleFilterType.Equal, key))
    return view, True


def _sheet_for(doc, key):
    from Autodesk.Revit import DB  # Lazy import
    for sheet in DB.FilteredElementCollector(doc).OfClass(DB.ViewSheet):
        if _text(sheet, u'NOSA_BBS_Ref').startswith(key):
            return sheet
    return None


def _titleblock(doc):
    from Autodesk.Revit import DB  # Lazy import
    from nosa_utils.revit_helpers import element_name
    for symbol in DB.FilteredElementCollector(doc).OfClass(DB.FamilySymbol).OfCategory(
            DB.BuiltInCategory.OST_TitleBlocks):
        if element_name(symbol) == TITLEBLOCK:
            return symbol
    return None


def _next_number(doc, taken):
    from Autodesk.Revit import DB  # Lazy import
    taken |= set(s.SheetNumber for s in DB.FilteredElementCollector(doc).OfClass(DB.ViewSheet))
    n = SHEET_SERIES
    while u'{}'.format(n) in taken:
        n += 1
    taken.add(u'{}'.format(n))
    return u'{}'.format(n)


def create(doc, capacity=ROWS_PER_A4):
    """
    The A4 schedules of every drawing (in a transaction): rebars keyed, a filtered BBS per key on
    its own 5500-series sheet, header filled. Returns {'schedules': [ref], 'new_sheets': [number],
    'skipped': n rebars without a drawing, 'errors': [...]}.
    """
    from Autodesk.Revit import DB  # Lazy import
    from nosa_utils.revit_helpers import element_name
    report = {'schedules': [], 'new_sheets': [], 'skipped': 0, 'errors': []}
    master = None
    for view in DB.FilteredElementCollector(doc).OfClass(DB.ViewSchedule):
        if element_name(view) == MASTER_BBS:
            master = view
    titleblock = _titleblock(doc)
    if master is None or titleblock is None:
        report['errors'].append(u'The template BBS schedule or the A4 BBS title block is missing.')
        return report
    members = _members(doc)
    rows = _rows_per_member(doc)
    drawings = dict((d, [(m[0], name, rows.get(name, m[1])) for name, m in found.items()])
                    for d, found in members.items())
    keys = plan(drawings, capacity)
    used = {}
    for found in drawings.values():
        for _elevation, name, n in found:
            used[keys[name]] = used.get(keys[name], 0) + n + 1
    for drawing, found in members.items():
        for name, entry in found.items():
            for rebar in entry[2]:
                _set(rebar, SCHEDULE_PARAM, keys[name])
    order = dict((name, (m[0], natural_key(name))) for found in drawings.values() for m in found
                 for name in [m[1]])
    report['renumbered'] = _renumber(doc, members, keys, order)
    taken = set()
    for key in sorted(set(keys.values()), key=natural_key):
        drawing = key.rsplit(u'-', 1)[0]
        try:
            view, _new = _schedule_view(doc, master, key)
            sheet = _sheet_for(doc, key)
            if sheet is None:
                sheet = DB.ViewSheet.Create(doc, titleblock.Id)
                sheet.SheetNumber = _next_number(doc, taken)
                sheet.Name = u'Bar schedule {}'.format(key)
                report['new_sheets'].append(sheet.SheetNumber)
            revision = _text(sheet, u'NOSA_BBS_Revision')
            if not _text(sheet, u'NOSA_BBS_Status'):
                _set(sheet, u'NOSA_BBS_Status', DEFAULT_STATUS)
            _set(sheet, u'NOSA_BBS_Drawing', drawing)
            _set(sheet, u'NOSA_BBS_Ref', schedule_ref(key, revision))
            placed = [doc.GetElement(i).ScheduleId for i in sheet.GetDependentElements(
                DB.ElementClassFilter(DB.ScheduleSheetInstance))]
            if view.Id not in placed:
                x, y = SCHEDULE_ORIGIN_MM
                DB.ScheduleSheetInstance.Create(doc, sheet.Id, view.Id, DB.XYZ(x / 304.8, y / 304.8, 0.0))
            report['schedules'].append(schedule_ref(key, revision))
            if used.get(key, 0) > capacity:
                report['errors'].append(
                    u'{}: {} rows do not fit one A4 page ({}); a member is never split between schedules, '
                    u'so split the table on the sheet or detail the member in parts.'.format(
                        schedule_ref(key, revision), used[key], capacity))
        except Exception as e:
            report['errors'].append(u'{}: {}'.format(key, e))
    return report
