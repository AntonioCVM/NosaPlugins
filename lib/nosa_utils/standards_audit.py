# -*- coding: utf-8 -*-
"""
Project standards audit against NOSA conventions (T8.14): leftovers from other languages and DWG
imports, duplicates, non-NOSA fonts, unused filters, broken images, duplicate project parameters,
views without a template. Each finding says whether Revit could purge the element (unused).
"""
import re

from nosa_utils.telemetry import log_swallowed

_LOG = u'nosa_utils.standards_audit'
NOSA_FONT = u'Century Gothic'

_SPANISH = re.compile(u'(por defecto|renderizaci|relleno|vidrio|cubierta|muro |^muro$|origen de luz|centro$|'
                      u'^oculto$|^trazo|^punto$|derribado|^elevado$|l[ií]nea de|l[ií]neas de|recubrimiento)',
                      re.IGNORECASE)
_IMPERIAL = re.compile(r'\d+/\d+"|\d"')
_COPY = re.compile(r'(\(\d+\)$|^copy of |\bcopy\b|[A-Za-z] [2-9]$)', re.IGNORECASE)


def looks_like_copy(name):
    """'Type (1)', 'Copy of Type', 'Title 2' — not 'Schedule 40', 'Scale 1 2' or 'Ceiling 1' (pure)."""
    return bool(_COPY.search(name or u''))


class Finding(object):
    def __init__(self, area, name, issue, element_id=None, unused=False):
        self.Area = area
        self.Item = name
        self.Issue = issue
        self.Unused = u'yes' if unused else u''
        self.element_id = element_id
        self.unused = unused


def normalise(name):
    """Name key for spotting duplicates that differ only in spaces, dashes or case."""
    return re.sub(r'[\s\-_]+', u'', (name or u'').lower())


def classify_name(name):
    """[issue] for a style/material name (pure)."""
    issues = []
    if _SPANISH.search(name or u''):
        issues.append(u'Spanish name (leftover of a Spanish template or family)')
    if (name or u'').upper().startswith(u'IMPORT-'):
        issues.append(u'Imported from a DWG')
    if re.match(r'^render material \d+-\d+-\d+$', (name or u'').lower()):
        issues.append(u'DWG render material')
    if _IMPERIAL.search(name or u''):
        issues.append(u'Imperial size in the name')
    return issues


def duplicates(names):
    """{normalised key: [names]} for keys with more than one name (pure)."""
    groups = {}
    for n in names:
        groups.setdefault(normalise(n), []).append(n)
    return dict((k, v) for k, v in groups.items() if len(v) > 1)


def purgeable_ids(doc):
    """Ids Revit reports as unused families/types/materials (Performance Adviser purge rule)."""
    from Autodesk.Revit import DB
    try:
        adviser = DB.PerformanceAdviser.GetPerformanceAdviser()
        rule = None
        for rid in adviser.GetAllRuleIds():
            if u'unused' in adviser.GetRuleName(rid).lower():
                rule = rid
                break
        if rule is None:
            return set()
        from System.Collections.Generic import List
        messages = adviser.ExecuteRules(doc, List[DB.PerformanceAdviserRuleId]([rule]))
        ids = set()
        for m in messages:
            for eid in m.GetFailingElements():
                ids.add(eid.IntegerValue)
        return ids
    except Exception:
        log_swallowed(_LOG, u'purgeable_ids')
        return set()


def _name(el):
    from nosa_utils.revit_helpers import element_name
    try:
        return element_name(el)
    except Exception:
        return u''


def audit(doc, check_purge=True):
    """[Finding] for the whole model; check_purge asks Revit what is unused (slow on big models)."""
    from Autodesk.Revit import DB
    unused = purgeable_ids(doc) if check_purge else set()
    out = []

    def add(area, el, issue):
        out.append(Finding(area, _name(el), issue, el.Id, el.Id.IntegerValue in unused))

    def collect(cls):
        return list(DB.FilteredElementCollector(doc).OfClass(cls))

    for area, cls in ((u'Material', DB.Material), (u'Line pattern', DB.LinePatternElement),
                      (u'Fill pattern', DB.FillPatternElement)):
        els = collect(cls)
        for el in els:
            for issue in classify_name(_name(el)):
                add(area, el, issue)
        by_name = dict((_name(e), e) for e in els)
        for _key, names in duplicates(by_name.keys()).items():
            for n in names[1:]:
                add(area, by_name[n], u'Duplicate of "{}"'.format(names[0]))

    for cls, area in ((DB.TextNoteType, u'Text type'), (DB.DimensionType, u'Dimension type')):
        for t in collect(cls):
            p = t.get_Parameter(DB.BuiltInParameter.TEXT_FONT)
            font = p.AsString() if p is not None and p.HasValue else u''
            if font and NOSA_FONT.lower() not in font.lower():
                add(area, t, u'Font "{}" (NOSA uses {})'.format(font, NOSA_FONT))
        names = [_name(t) for t in collect(cls)]
        for dup, group in duplicates(names).items():
            if len(group) > 1 and group[0] == group[1]:
                for t in [x for x in collect(cls) if _name(x) == group[0]][1:]:
                    add(area, t, u'Same name used {} times'.format(len(group)))

    used_filters = set()
    for v in collect(DB.View):
        try:
            for fid in v.GetFilters():
                used_filters.add(fid.IntegerValue)
        except Exception:
            log_swallowed(_LOG, u'audit')
    for f in collect(DB.ParameterFilterElement):
        if f.Id.IntegerValue not in used_filters:
            out.append(Finding(u'View filter', _name(f), u'Not used by any view or template', f.Id, True))

    import os
    placed = set(i.GetTypeId().IntegerValue for i in collect(DB.ImageInstance))
    for it in collect(DB.ImageType):
        path = u''
        try:
            path = it.Path or u''
        except Exception:
            log_swallowed(_LOG, u'audit')
        problems = []
        if path and not os.path.exists(path):
            problems.append(u'linked file not found ({})'.format(path))
        if it.Id.IntegerValue not in placed:
            problems.append(u'not placed anywhere')
        if problems:
            out.append(Finding(u'Image', _name(it), u'; '.join(problems), it.Id, it.Id.IntegerValue not in placed))

    names = {}
    it = doc.ParameterBindings.ForwardIterator()
    while it.MoveNext():
        names.setdefault(it.Key.Name, 0)
        names[it.Key.Name] += 1
    for n, count in sorted(names.items()):
        if count > 1:
            out.append(Finding(u'Project parameter', n, u'Bound {} times (shared and project parameter with the same '
                                                        u'name?)'.format(count)))

    model_types = (DB.ViewType.FloorPlan, DB.ViewType.EngineeringPlan, DB.ViewType.CeilingPlan, DB.ViewType.Section,
                   DB.ViewType.Elevation, DB.ViewType.ThreeD)
    for v in collect(DB.View):
        if not v.IsTemplate and v.ViewType in model_types and v.ViewTemplateId == DB.ElementId.InvalidElementId:
            add(u'View', v, u'Model view without a view template')

    for el in DB.FilteredElementCollector(doc).WhereElementIsElementType():
        n = _name(el)
        if n and looks_like_copy(n):
            cat = el.Category.Name if el.Category is not None else el.GetType().Name
            out.append(Finding(u'Type', u'{}: {}'.format(cat, n), u'Looks like a copy ("(1)", " 2", "Copy of")',
                               el.Id, el.Id.IntegerValue in unused))
    return out
