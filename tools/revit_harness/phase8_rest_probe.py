# -*- coding: utf-8 -*-
"""T8.20-T8.24: read-only dump of revisions, steel framing/column types, view templates, browser
organisations and schedules. Scope: doc, EXT_ROOT, PYREVIT, OUT. Result: RESULT."""
import sys
import os
import io
import traceback

import clr
clr.AddReference('RevitAPI')
from Autodesk.Revit import DB

for _p in (os.path.join(PYREVIT, 'pyrevitlib'), os.path.join(PYREVIT, 'site-packages'),
           os.path.join(EXT_ROOT, 'lib')):
    if _p not in sys.path:
        sys.path.insert(0, _p)
_out = []
lines = []


def run():
    from nosa_utils.revit_helpers import element_name, get_id_value

    def col(cls):
        return list(DB.FilteredElementCollector(doc).OfClass(cls))

    lines.append(u'== REVISION SEQUENCES')
    try:
        for s in col(DB.RevisionNumberingSequence):
            settings = s.GetNumericRevisionSettings() if s.NumberType == DB.RevisionNumberType.Numeric else None
            alpha = s.GetAlphanumericRevisionSettings() if s.NumberType == DB.RevisionNumberType.Alphanumeric else None
            detail = u''
            if settings is not None:
                detail = u'prefix "{}" suffix "{}" start {} digits {}'.format(
                    settings.Prefix, settings.Suffix, settings.StartNumber, getattr(settings, 'MinimumDigits', u'?'))
            if alpha is not None:
                detail = u'prefix "{}" suffix "{}" seq {}'.format(alpha.Prefix, alpha.Suffix,
                                                                 u','.join(list(alpha.GetSequence())[:6]))
            lines.append(u'{}\t{}\t{}\t{}'.format(get_id_value(s.Id), s.SequenceName, s.NumberType, detail))
    except Exception as e:
        lines.append(u'sequences: {}'.format(e))
    lines.append(u'== REVISIONS (numbering {})'.format(DB.RevisionSettings.GetRevisionSettings(doc).RevisionNumbering))
    for r in DB.Revision.GetAllRevisionIds(doc):
        rev = doc.GetElement(r)
        seq = doc.GetElement(rev.RevisionNumberingSequenceId)
        try:
            number = rev.RevisionNumber
        except Exception:
            number = u'(per sheet)'
        lines.append(u'{}\t{}\t{}\t{}\t{}\tissued={}\tseq={}'.format(
            rev.SequenceNumber, number, rev.RevisionDate, rev.Description, rev.IssuedTo,
            rev.Issued, seq.SequenceName if seq else u'-'))

    lines.append(u'== STEEL TYPES (family: types, placed)')
    placed = {}
    for cat in (DB.BuiltInCategory.OST_StructuralFraming, DB.BuiltInCategory.OST_StructuralColumns):
        for e in DB.FilteredElementCollector(doc).OfCategory(cat).WhereElementIsNotElementType():
            placed[get_id_value(e.GetTypeId())] = placed.get(get_id_value(e.GetTypeId()), 0) + 1
        fams = {}
        for s in DB.FilteredElementCollector(doc).OfCategory(cat).WhereElementIsElementType():
            fam = getattr(s, 'FamilyName', u'?')
            mat = u''
            try:
                mat = u'{}'.format(s.Family.StructuralMaterialType)
            except Exception:
                pass
            row = fams.setdefault((fam, mat), [0, 0, []])
            row[0] += 1
            row[1] += placed.get(get_id_value(s.Id), 0)
            if len(row[2]) < 3:
                row[2].append(element_name(s))
        for (fam, mat), (n, used, sample) in sorted(fams.items()):
            lines.append(u'{}\t{}\t{}\ttypes {}\tplaced {}\te.g. {}'.format(cat, fam, mat, n, used, u', '.join(sample)))

    lines.append(u'== VIEW TEMPLATES (name, type, views using)')
    users = {}
    for v in col(DB.View):
        if not v.IsTemplate and v.ViewTemplateId != DB.ElementId.InvalidElementId:
            users[get_id_value(v.ViewTemplateId)] = users.get(get_id_value(v.ViewTemplateId), 0) + 1
    for v in sorted([v for v in col(DB.View) if v.IsTemplate], key=lambda x: x.Name):
        lines.append(u'{}\t{}\t{}'.format(v.Name, v.ViewType, users.get(get_id_value(v.Id), 0)))
    lines.append(u'== MODEL VIEWS WITHOUT TEMPLATE')
    model = (DB.ViewType.FloorPlan, DB.ViewType.EngineeringPlan, DB.ViewType.CeilingPlan, DB.ViewType.Section,
             DB.ViewType.Elevation, DB.ViewType.ThreeD)
    for v in col(DB.View):
        if not v.IsTemplate and v.ViewType in model and v.ViewTemplateId == DB.ElementId.InvalidElementId:
            lines.append(u'{}\t{}'.format(v.Name, v.ViewType))
    lines.append(u'== BROWSER ORGANISATIONS')
    for b in col(DB.BrowserOrganization):
        lines.append(u'{}\t{}'.format(element_name(b), b.Type if hasattr(b, 'Type') else u''))

    lines.append(u'== SCHEDULES (name, category, fields)')
    for s in sorted(col(DB.ViewSchedule), key=lambda x: x.Name):
        if s.IsTitleblockRevisionSchedule or s.IsTemplate:
            continue
        try:
            d = s.Definition
            cat = DB.Category.GetCategory(doc, d.CategoryId)
            fields = [d.GetField(i).GetName() for i in range(d.GetFieldCount())]
            lines.append(u'{}\t{}\t{}'.format(s.Name, cat.Name if cat else u'(multi)', u', '.join(fields)))
        except Exception as e:
            lines.append(u'{}\t?\t{}'.format(s.Name, e))


try:
    run()
    with io.open(OUT, 'w', encoding='utf-8') as f:
        f.write(u'\n'.join(lines))
    _out.append(u'ok {} lines'.format(len(lines)))
except Exception:
    _out.append(traceback.format_exc())
RESULT = u'\n'.join(_out)
