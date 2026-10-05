# -*- coding: utf-8 -*-
"""Read-only dump of every schedule: category, material takeoff, filters, sorting, fields (T8.24 review).
Scope: doc, OUT (file). Result: RESULT."""
import io
import traceback

import clr
clr.AddReference('RevitAPI')
from Autodesk.Revit import DB

_lines = []


def _value(f):
    for getter in ('GetStringValue', 'GetDoubleValue', 'GetIntegerValue', 'GetElementIdValue'):
        try:
            v = getattr(f, getter)()
            if v is not None and v != u'':
                return u'{}'.format(v)
        except Exception:
            continue
    return u''


def run():
    for s in sorted(DB.FilteredElementCollector(doc).OfClass(DB.ViewSchedule), key=lambda x: x.Name):
        if s.IsTitleblockRevisionSchedule or s.IsTemplate or s.Name.startswith(u'<'):
            continue
        d = s.Definition
        cat = DB.Category.GetCategory(doc, d.CategoryId)
        kind = u'material takeoff' if d.IsMaterialTakeoff else (u'key' if d.IsKeySchedule else u'schedule')
        _lines.append(u'=== {} | {} | {} | itemize {} | links {}'.format(
            s.Name, cat.Name if cat else u'Multi-Category', kind, d.IsItemized, d.IncludeLinkedFiles))
        names = []
        for i in range(d.GetFieldCount()):
            f = d.GetField(i)
            names.append(u'{}{}'.format(f.GetName(), u' (hidden)' if f.IsHidden else u''))
        _lines.append(u'  fields: ' + u', '.join(names))
        for i in range(d.GetFilterCount()):
            fl = d.GetFilter(i)
            fld = d.GetField(fl.FieldId)
            _lines.append(u'  filter: {} {} "{}"'.format(fld.GetName(), fl.FilterType, _value(fl)))
        for i in range(d.GetSortGroupFieldCount()):
            sg = d.GetSortGroupField(i)
            _lines.append(u'  sort/group: {} {}{}'.format(d.GetField(sg.FieldId).GetName(), sg.SortOrder,
                                                       u' header' if sg.ShowHeader else u''))
        try:
            rows = s.GetTableData().GetSectionData(DB.SectionType.Body).NumberOfRows
        except Exception:
            rows = u'?'
        _lines.append(u'  body rows now: {}'.format(rows))


try:
    run()
    with io.open(OUT, 'w', encoding='utf-8') as fh:
        fh.write(u'\n'.join(_lines))
    RESULT = u'ok {} lines'.format(len(_lines))
except Exception:
    RESULT = traceback.format_exc()
