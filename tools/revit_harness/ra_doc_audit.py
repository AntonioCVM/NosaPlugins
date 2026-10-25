# -*- coding: utf-8 -*-
"""
Read-only documentation audit of the RebarAutomate output in a test model: inventory of the RC drawings (45xx) and
bar schedule sheets (55xx), their views and schedules, the title block fields, every BBS exported to CSV and compared
with the model's rebars. Scope: doc, OUTDIR (folder for the CSVs and the JSON report). Writes OUTDIR/audit.json.
Only the test models are accepted. Exporting a schedule to CSV does not change the model.
"""
import io
import os
import json
import clr
clr.AddReference('RevitAPI')
import System
from Autodesk.Revit import DB
from Autodesk.Revit.DB.Structure import Rebar

TEST_MODELS = (u'Rebar test 2024', u'Rebar test 2026',
               u'Rebar test 2025 (copia de 2024)', u'Rebar test 2027 (copia de 2026)', u'Rebar test 2024 (copia)')  # T10.11 copies
if doc.Title not in TEST_MODELS:
    raise RuntimeError(u'not a test model')
FT = 304.8


def name(e):
    try:
        return DB.Element.Name.GetValue(e)
    except Exception:
        return u''


def text(e, pname):
    p = e.LookupParameter(pname)
    if p is None:
        return None
    try:
        return p.AsString() if p.StorageType == DB.StorageType.String else p.AsValueString()
    except Exception:
        return None


def ours(sheet):
    try:
        n = int(sheet.SheetNumber)
    except ValueError:
        return False
    return 4501 <= n <= 4999 or 5500 <= n <= 5999


report = {'model': doc.Title, 'path': doc.PathName, 'version': doc.Application.VersionNumber,
          'units_length': u'{}'.format(doc.GetUnits().GetFormatOptions(DB.SpecTypeId.Length).GetUnitTypeId().TypeId),
          'sheets': [], 'schedules': [], 'rebars': {}}
for s in sorted(DB.FilteredElementCollector(doc).OfClass(DB.ViewSheet), key=lambda x: x.SheetNumber):
    if not ours(s):
        continue
    tbs = list(DB.FilteredElementCollector(doc, s.Id).OfCategory(DB.BuiltInCategory.OST_TitleBlocks)  # nosa-lint: disable=NOSA002 - harness script runs in Revit
               .WhereElementIsNotElementType())
    tb = tbs[0] if tbs else None
    tbinfo = {}
    if tb is not None:
        bb = tb.get_BoundingBox(s)
        tbinfo = {'family': name(doc.GetElement(tb.GetTypeId())), 'w': round((bb.Max.X - bb.Min.X) * FT),
                  'h': round((bb.Max.Y - bb.Min.Y) * FT)}
    fields = {}
    for p in s.Parameters:
        try:
            if p.Definition is None:
                continue
            v = p.AsString() if p.StorageType == DB.StorageType.String else p.AsValueString()
            fields[p.Definition.Name] = v
        except Exception:
            continue
    ports = []
    for vid in s.GetAllViewports():
        vp = doc.GetElement(vid)
        v = doc.GetElement(vp.ViewId)
        o = vp.GetBoxOutline()
        ports.append({'view': v.Name, 'type': u'{}'.format(v.ViewType), 'scale': v.Scale,
                      'box': [round(o.MinimumPoint.X * FT), round(o.MinimumPoint.Y * FT),
                              round(o.MaximumPoint.X * FT), round(o.MaximumPoint.Y * FT)],
                      'title': text(v, u'Title on Sheet')})
    scheds = []
    for si in DB.FilteredElementCollector(doc, s.Id).OfClass(DB.ScheduleSheetInstance):
        if si.IsTitleblockRevisionSchedule:
            continue
        bb = si.get_BoundingBox(s)
        scheds.append({'schedule': name(doc.GetElement(si.ScheduleId)),
                       'box': [round(bb.Min.X * FT), round(bb.Min.Y * FT), round(bb.Max.X * FT), round(bb.Max.Y * FT)]})
    notes = [n.Text for n in DB.FilteredElementCollector(doc, s.Id).OfClass(DB.TextNote)]
    report['sheets'].append({'number': s.SheetNumber, 'name': s.Name, 'id': s.Id.Value, 'titleblock': tbinfo,
                             'fields': fields, 'viewports': ports, 'schedules': scheds, 'notes': notes})

placed = {}
for si in DB.FilteredElementCollector(doc).OfClass(DB.ScheduleSheetInstance):
    try:
        placed.setdefault(name(doc.GetElement(si.ScheduleId)), []).append(doc.GetElement(si.OwnerViewId).SheetNumber)
    except Exception:
        continue
opts = DB.ViewScheduleExportOptions()
opts.FieldDelimiter = u';'
for vs in DB.FilteredElementCollector(doc).OfClass(DB.ViewSchedule):
    nm = vs.Name
    if vs.IsTemplate or not (nm.startswith(u'BBS')):
        continue
    d = vs.Definition
    fields = []
    for i in range(d.GetFieldCount()):
        f = d.GetField(i)
        fields.append({'name': f.GetName(), 'hidden': f.IsHidden, 'heading': f.ColumnHeading})
    filters = []
    for i in range(d.GetFilterCount()):
        fl = d.GetFilter(i)
        filters.append({'field': d.GetField(fl.FieldId).GetName(), 'type': u'{}'.format(fl.FilterType),
                        'value': fl.GetStringValue() if fl.IsStringValue else u'{}'.format(fl.GetDoubleValue()
                                                                                         if fl.IsDoubleValue else u'')})
    csv = u'{}.csv'.format(nm.replace(u' ', u'_').replace(u'/', u'-'))
    try:
        vs.Export(OUTDIR, csv, opts)
    except Exception as e:
        csv = u'EXPORT FAILED {}'.format(e)
    report['schedules'].append({'name': nm, 'id': vs.Id.Value, 'category': name(doc.GetElement(d.CategoryId))
                                if doc.GetElement(d.CategoryId) else u'{}'.format(d.CategoryId.Value),
                                'fields': fields, 'filters': filters, 'itemized': d.IsItemized,
                                'sheets': placed.get(nm, []), 'csv': csv})

for r in DB.FilteredElementCollector(doc).OfClass(Rebar):
    try:
        bt = doc.GetElement(r.GetTypeId())
        try:
            shape_name = name(doc.GetElement(r.GetShapeId()))
        except Exception:      # a FreeForm set of several shapes (W2 U-bars): the plugin's own code
            shape_name = text(r, u'NOSA_Rebar_Shape_Code') or u''
        n = r.NumberOfBarPositions
        lens = []
        for i in range(n):
            try:
                lens.append(round(r.GetBarLengthAtIndex(i) * FT) if hasattr(r, 'GetBarLengthAtIndex') else None)
            except Exception:
                lens.append(None)
        report['rebars'][str(r.Id.Value)] = {
            'host': r.GetHostId().Value, 'mark': text(r, u'NOSA_Rebar_Mark'), 'schedule_mark':
            r.get_Parameter(DB.BuiltInParameter.REBAR_ELEM_SCHEDULE_MARK).AsString(),  # nosa-lint: disable=NOSA002 - harness script runs in Revit
            'key': text(r, u'NOSA_Rebar_Assembly'), 'drawing': text(r, u'NOSA_Rebar_Group'),
            'dia': round(bt.BarNominalDiameter * FT, 1), 'n': n, 'qty': r.Quantity, 'shape': shape_name,
            'bar_length': round(r.get_Parameter(DB.BuiltInParameter.REBAR_ELEM_LENGTH).AsDouble() * FT),  # nosa-lint: disable=NOSA002 - harness script runs in Revit
            'total_length': round(r.TotalLength * FT), 'volume_cm3': round(r.Volume * 28316.8466, 1),
            'layer': text(r, u'NOSA_Rebar_Layer'), 'partition': text(r, u'Partition'),
            'varying': text(r, u'NOSA_Rebar_Is_Variable'), 'lens_sample': lens[:3]}
    except Exception as e:
        report['rebars'][str(r.Id.Value)] = {'error': u'{}'.format(e)}

def ascii_only(o):
    # IPY2.7's json cannot encode non-ASCII text (the user's name in paths and title blocks): escape it first
    if isinstance(o, dict):
        return dict((k, ascii_only(v)) for k, v in o.items())
    if isinstance(o, list):
        return [ascii_only(v) for v in o]
    if isinstance(o, basestring):
        return u''.join(c if ord(c) < 128 else u'&#{};'.format(ord(c)) for c in unicode(o))
    if isinstance(o, (long, System.Int64)):
        return int(o)
    return o


with io.open(os.path.join(OUTDIR, 'audit.json'), 'w', encoding='utf-8') as fh:
    fh.write(unicode(json.dumps(ascii_only(report), indent=1)))
RESULT = u'sheets {} schedules {} rebars {}'.format(len(report['sheets']), len(report['schedules']),
                                                     len(report['rebars']))
