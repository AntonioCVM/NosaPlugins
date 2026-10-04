# -*- coding: utf-8 -*-
"""T8.18: read-only usage dump for the template cleanup (line patterns, materials, dimension types,
duplicate parameters, copied types). Scope: doc, EXT_ROOT, PYREVIT, OUT (file path). Result: RESULT."""
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
try:
    from nosa_utils.revit_helpers import element_name, get_id_value

    def col(cls):
        return list(DB.FilteredElementCollector(doc).OfClass(cls))

    # line patterns: categories / subcategories, filter overrides, template category overrides
    lp_use = {}

    def use(d, eid, where):
        if eid is None or eid == DB.ElementId.InvalidElementId:
            return
        d.setdefault(get_id_value(eid), []).append(where)

    cats = []
    for c in doc.Settings.Categories:
        cats.append(c)
        for s in c.SubCategories:
            cats.append(s)
    for c in cats:
        for gst in (DB.GraphicsStyleType.Projection, DB.GraphicsStyleType.Cut):
            try:
                use(lp_use, c.GetLinePatternId(gst), u'cat:' + c.Name)
            except Exception:
                pass
    views = [v for v in col(DB.View)]
    for v in views:
        try:
            fids = list(v.GetFilters())
        except Exception:
            fids = []
        for fid in fids:
            o = v.GetFilterOverrides(fid)
            for eid in (o.ProjectionLinePatternId, o.CutLinePatternId):
                use(lp_use, eid, u'filter in ' + v.Name)
        if v.IsTemplate:
            for c in doc.Settings.Categories:
                try:
                    o = v.GetCategoryOverrides(c.Id)
                except Exception:
                    continue
                for eid in (o.ProjectionLinePatternId, o.CutLinePatternId):
                    use(lp_use, eid, u'tpl {} / {}'.format(v.Name, c.Name))
    lines.append(u'== LINE PATTERNS')
    for lp in sorted(col(DB.LinePatternElement), key=element_name):
        u = lp_use.get(get_id_value(lp.Id), [])
        lines.append(u'{}\t{}\t{}\t{}'.format(get_id_value(lp.Id), element_name(lp), len(u), u'; '.join(u[:4])))

    # materials: categories, compound layers, ElementId parameters, instance material ids
    mat_ids = set(get_id_value(m.Id) for m in col(DB.Material))
    m_use = {}
    for c in cats:
        try:
            if c.Material is not None:
                use(m_use, c.Material.Id, u'cat:' + c.Name)
        except Exception:
            pass
    for el in DB.FilteredElementCollector(doc).WhereElementIsElementType():
        try:
            cs = el.GetCompoundStructure() if hasattr(el, 'GetCompoundStructure') else None
            if cs is not None:
                for layer in cs.GetLayers():
                    use(m_use, layer.MaterialId, u'layer:' + element_name(el))
        except Exception:
            pass
    for coll in (DB.FilteredElementCollector(doc).WhereElementIsElementType(),
                 DB.FilteredElementCollector(doc).WhereElementIsNotElementType()):
        for el in coll:
            try:
                for p in el.Parameters:
                    if p.StorageType == DB.StorageType.ElementId and p.HasValue:
                        v = p.AsElementId()
                        if get_id_value(v) in mat_ids:
                            use(m_use, v, u'{}:{}'.format(element_name(el), p.Definition.Name))
            except Exception:
                pass
    for el in DB.FilteredElementCollector(doc).WhereElementIsNotElementType():
        if el.Category is None:
            continue
        try:
            for mid in el.GetMaterialIds(False):
                use(m_use, mid, u'inst:' + el.Category.Name)
        except Exception:
            pass
    lines.append(u'== MATERIALS')
    for m in sorted(col(DB.Material), key=element_name):
        u = m_use.get(get_id_value(m.Id), [])
        lines.append(u'{}\t{}\t{}\t{}'.format(get_id_value(m.Id), element_name(m), len(u), u'; '.join(sorted(set(u))[:4])))

    # fill patterns used by name duplicates
    lines.append(u'== FILL PATTERNS')
    for f in sorted(col(DB.FillPatternElement), key=element_name):
        lines.append(u'{}\t{}\t{}'.format(get_id_value(f.Id), element_name(f), f.GetFillPattern().Target))

    # dimension types
    d_use = {}
    for d in col(DB.Dimension):
        use(d_use, d.GetTypeId(), u'dim')
    lines.append(u'== DIMENSION TYPES')
    for t in sorted(col(DB.DimensionType), key=element_name):
        p = t.get_Parameter(DB.BuiltInParameter.TEXT_FONT)  # nosa-lint: disable=NOSA002 - harness script runs in Revit
        font = p.AsString() if p is not None and p.HasValue else u''
        ts = t.get_Parameter(DB.BuiltInParameter.TEXT_SIZE)  # nosa-lint: disable=NOSA002 - harness script runs in Revit
        size = ts.AsDouble() * 304.8 if ts is not None and ts.HasValue else 0
        lines.append(u'{}\t{}\t{}\t{}\t{:.2f}mm\tused {}'.format(get_id_value(t.Id), element_name(t), t.StyleType, font,
                                                                size, len(d_use.get(get_id_value(t.Id), []))))

    # parameters bound twice
    lines.append(u'== PARAMETER BINDINGS')
    it = doc.ParameterBindings.ForwardIterator()
    while it.MoveNext():
        d = it.Key
        if d.Name not in (u'Manufacturer_ISO', u'Revit version', u'UniclassCode', u'UniclassDescription'):
            continue
        b = it.Current
        shared = None
        try:
            sp = doc.GetElement(d.Id) if hasattr(d, 'Id') else None
            shared = isinstance(sp, DB.SharedParameterElement)
            guid = sp.GuidValue if shared else u''
        except Exception:
            guid = u''
        catnames = sorted(c.Name for c in b.Categories)
        kind = u'instance' if isinstance(b, DB.InstanceBinding) else u'type'
        lines.append(u'{}\tshared={} {}\t{}\t{} cats: {}'.format(d.Name, shared, guid, kind, len(catnames),
                                                              u', '.join(catnames[:8])))

    # copied types vs originals
    lines.append(u'== COPIED TYPES')
    pairs = []
    all_types = list(DB.FilteredElementCollector(doc).WhereElementIsElementType())
    by_name = {}
    for t in all_types:
        by_name.setdefault((t.GetType().Name, element_name(t)), []).append(t)
    import re
    for t in all_types:
        n = element_name(t)
        m = re.match(r'^(.*?)(?: \((\d+)\)| (\d))$', n or u'')
        if not m:
            continue
        base = by_name.get((t.GetType().Name, m.group(1)))
        if not base:
            continue
        o = base[0]
        diffs = []
        for p in t.Parameters:
            if p.IsReadOnly or p.Definition is None:
                continue
            q = o.LookupParameter(p.Definition.Name)
            if q is None:
                diffs.append(u'{}: only in copy'.format(p.Definition.Name))
                continue
            a, b = p.AsValueString() or p.AsString() or u'', q.AsValueString() or q.AsString() or u''
            if a != b and p.Definition.Name not in (u'Type Name',):
                diffs.append(u'{}: copy "{}" / original "{}"'.format(p.Definition.Name, a, b))
        n_inst = len([1 for e in DB.FilteredElementCollector(doc).WhereElementIsNotElementType()
                      if e.GetTypeId() == t.Id])
        lines.append(u'{}\t{} -> {}\tinstances {}\t{}'.format(get_id_value(t.Id), n, element_name(o), n_inst,
                                                               u' | '.join(diffs) or u'IDENTICAL'))

    lines.append(u'== IMAGES')
    placed = set(get_id_value(i.GetTypeId()) for i in col(DB.ImageInstance))
    for it_ in col(DB.ImageType):
        lines.append(u'{}\t{}\tplaced={}'.format(get_id_value(it_.Id), element_name(it_), get_id_value(it_.Id) in placed))

    with io.open(OUT, 'w', encoding='utf-8') as f:
        f.write(u'\n'.join(lines))
    _out.append(u'ok {} lines'.format(len(lines)))
except Exception:
    _out.append(traceback.format_exc())
RESULT = u'\n'.join(_out)
