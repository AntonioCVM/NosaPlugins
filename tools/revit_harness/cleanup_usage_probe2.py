# -*- coding: utf-8 -*-
"""T8.18: read-only second pass — fill pattern usage, where dimension types are used, values and
schedule fields of the parameters bound twice. Scope: doc, EXT_ROOT, PYREVIT, OUT. Result: RESULT."""
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
    usage = {}

    def use(eid, where):
        if eid is not None and eid != DB.ElementId.InvalidElementId:
            usage.setdefault(get_id_value(eid), []).append(where)

    for m in col(DB.Material):
        for attr in ('SurfaceForegroundPatternId', 'SurfaceBackgroundPatternId', 'CutForegroundPatternId',
                     'CutBackgroundPatternId'):
            use(getattr(m, attr, None), u'material ' + element_name(m))
    for f in col(DB.FilledRegionType):
        use(f.ForegroundPatternId, u'filled region ' + element_name(f))
        use(f.BackgroundPatternId, u'filled region ' + element_name(f))
    attrs = ('SurfaceForegroundPatternId', 'SurfaceBackgroundPatternId', 'CutForegroundPatternId',
             'CutBackgroundPatternId')
    for v in col(DB.View):
        try:
            fids = list(v.GetFilters())
        except Exception:
            fids = []
        for fid in fids:
            o = v.GetFilterOverrides(fid)
            for a in attrs:
                use(getattr(o, a), u'filter in ' + v.Name)
        if v.IsTemplate:
            for c in doc.Settings.Categories:
                try:
                    o = v.GetCategoryOverrides(c.Id)
                except Exception:
                    continue
                for a in attrs:
                    use(getattr(o, a), u'tpl ' + v.Name)
    lines.append(u'== FILL PATTERN USAGE')
    for fp in sorted(col(DB.FillPatternElement), key=element_name):
        u = usage.get(get_id_value(fp.Id), [])
        lines.append(u'{}\t{}\t{}\t{}'.format(get_id_value(fp.Id), element_name(fp), len(u), u'; '.join(sorted(set(u))[:3])))

    lines.append(u'== DIMENSIONS BY VIEW (types 305, 316, 1068540)')
    where = {}
    for d in col(DB.Dimension):
        tid = get_id_value(d.GetTypeId())
        if tid not in (305, 316, 1068540):
            continue
        v = doc.GetElement(d.OwnerViewId)
        key = (tid, element_name(v) if v else u'?', u'{}'.format(v.ViewType) if v else u'')
        where[key] = where.get(key, 0) + 1
    for k in sorted(where):
        lines.append(u'{}\t{}\t{}\t{}'.format(k[0], k[1], k[2], where[k]))
    for tid in (305, 316, 1040712, 1068515):
        t = doc.GetElement(DB.ElementId(tid))  # nosa-lint: disable=NOSA010 - harness, Revit 2024 only
        vals = []
        for name in (u'Tick Mark', u'Line Weight', u'Text Size', u'Text Font', u'Witness Line Control',
                     u'Dimension Line Extension', u'Text Offset', u'Color'):
            p = t.LookupParameter(name)
            if p is not None:
                vals.append(u'{}={}'.format(name, p.AsValueString() or p.AsString()))
        lines.append(u'{} {}: {}'.format(tid, element_name(t), u', '.join(vals)))

    lines.append(u'== DOUBLE PARAMETERS')
    names = (u'Manufacturer_ISO', u'Revit version', u'UniclassCode', u'UniclassDescription')
    it = doc.ParameterBindings.ForwardIterator()
    defs = []
    while it.MoveNext():
        if it.Key.Name in names:
            defs.append(it.Key)
    fields = {}
    for s in col(DB.ViewSchedule):
        try:
            sd = s.Definition
            for i in range(sd.GetFieldCount()):
                fld = sd.GetField(i)
                fields.setdefault(get_id_value(fld.ParameterId), []).append(s.Name)
        except Exception:
            pass
    for d in defs:
        el = doc.GetElement(d.Id)
        guid = el.GuidValue if isinstance(el, DB.SharedParameterElement) else u'project'
        n = 0
        for e in DB.FilteredElementCollector(doc).WhereElementIsNotElementType():
            p = e.get_Parameter(guid) if isinstance(el, DB.SharedParameterElement) else None
            if p is None:
                for q in e.GetParameters(d.Name):
                    if get_id_value(q.Id) == get_id_value(d.Id):
                        p = q
            if p is not None and p.HasValue and (p.AsString() or p.AsValueString()):
                n += 1
        sch = fields.get(get_id_value(d.Id), [])
        lines.append(u'{}\tid {}\t{}\tvalues {}\tschedules {}: {}'.format(
            d.Name, get_id_value(d.Id), guid, n, len(sch), u', '.join(sch[:4])))


try:
    run()
    with io.open(OUT, 'w', encoding='utf-8') as f:
        f.write(u'\n'.join(lines))
    _out.append(u'ok {} lines'.format(len(lines)))
except Exception:
    _out.append(traceback.format_exc())
RESULT = u'\n'.join(_out)
