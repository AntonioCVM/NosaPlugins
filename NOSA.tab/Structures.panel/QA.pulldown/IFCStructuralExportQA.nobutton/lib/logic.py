# -*- coding: utf-8 -*-
import os
import sys

from Autodesk.Revit import DB

_lib = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', '..', 'lib'))
if _lib not in sys.path:
    sys.path.insert(0, _lib)


def _struct_categories():
    return [
        ('Structural Columns', DB.BuiltInCategory.OST_StructuralColumns),
        ('Structural Framing', DB.BuiltInCategory.OST_StructuralFraming),
        ('Structural Foundations', DB.BuiltInCategory.OST_StructuralFoundation),
        ('Floors', DB.BuiltInCategory.OST_Floors),
        ('Walls', DB.BuiltInCategory.OST_Walls),
        ('Rebar', DB.BuiltInCategory.OST_Rebar),
    ]


_IFC_PSET_PARAMS = (
    'Mark', 'Comments', 'LoadBearing', 'FireRating',
    'Structural Material', 'Structural Usage',
)


class QAResult(object):
    def __init__(self, check_name, status, count, detail):
        self.check_name = check_name
        self.status = status
        self.count = count
        self.detail = detail


def check_category_counts(doc):
    detail = []
    zero_cats = []
    for label, cat in _struct_categories():
        try:
            n = len(list(DB.FilteredElementCollector(doc)
                         .OfCategory(cat)
                         .WhereElementIsNotElementType()
                         .ToElements()))
            detail.append(u'{}: {}'.format(label, n))
            if n == 0:
                zero_cats.append(label)
        except Exception:
            zero_cats.append(label)
    status = 'red' if len(zero_cats) > 3 else ('amber' if zero_cats else 'green')
    if zero_cats:
        detail.insert(0, u'Empty categories: ' + u', '.join(zero_cats))
    return QAResult(u'Structural categories', status, len(zero_cats), detail[:12])


def check_pset_coverage(doc):
    """Flag structural elements missing common IFC-relevant parameters."""
    issues = []
    checked = 0
    for label, cat in _struct_categories()[:5]:
        try:
            els = list(DB.FilteredElementCollector(doc)
                       .OfCategory(cat)
                       .WhereElementIsNotElementType()
                       .ToElements())
        except Exception:
            continue
        for el in els[:200]:
            checked += 1
            missing = []
            for pname in _IFC_PSET_PARAMS:
                try:
                    p = el.LookupParameter(pname)
                    if p is None or not p.HasValue:
                        missing.append(pname)
                except Exception:
                    missing.append(pname)
            if len(missing) >= 3:
                name = getattr(el, 'Name', None) or u'id:{}'.format(el.Id)
                issues.append(u'{} — missing: {}'.format(name, u', '.join(missing[:4])))
    if not issues:
        return QAResult(u'Property set coverage', 'green', 0,
                        [u'Checked {} elements — key parameters present.'.format(checked)])
    status = 'red' if len(issues) > 15 else 'amber'
    return QAResult(u'Property set coverage', status, len(issues), issues[:15])


def check_coordinates(doc):
    issues = []
    try:
        proj_loc = doc.ActiveProjectLocation
        if proj_loc:
            name = proj_loc.Name or u'(unnamed)'
            issues.append(u'Active project location: {}'.format(name))
    except Exception:
        issues.append(u'Could not read active project location.')

    try:
        bp = (DB.FilteredElementCollector(doc)
              .OfCategory(DB.BuiltInCategory.OST_ProjectBasePoint)
              .FirstElement())
        if bp:
            issues.append(u'Project base point found in model.')
        else:
            issues.append(u'Project base point not found.')
    except Exception:
        pass

    try:
        sp = (DB.FilteredElementCollector(doc)
              .OfCategory(DB.BuiltInCategory.OST_SharedBasePoint)
              .FirstElement())
        if sp:
            issues.append(u'Shared base point present — verify IFC export coordinates.')
        else:
            issues.append(u'No shared base point — internal coordinates only.')
    except Exception:
        pass

    try:
        site = doc.SiteLocation
        if site:
            issues.append(u'Site latitude/longitude configured.')
    except Exception:
        issues.append(u'Site location not configured.')

    status = 'amber' if any('not found' in i.lower() or 'not configured' in i.lower() for i in issues) else 'green'
    return QAResult(u'Coordinates and location', status, len(issues), issues)


def check_unplaced_links(doc):
    issues = []
    for link in (DB.FilteredElementCollector(doc)
                 .OfClass(DB.RevitLinkInstance)
                 .ToElements()):
        try:
            if link.GetLinkDocument() is None:
                issues.append(u'{} — link not loaded'.format(link.Name))
        except Exception:
            issues.append(u'{} — link status unknown'.format(link.Name))
    if not issues:
        return QAResult(u'Linked models', 'green', 0, [u'All links loaded.'])
    return QAResult(u'Linked models', 'amber', len(issues), issues[:10])


def run_all_checks(doc):
    return [
        check_category_counts(doc),
        check_pset_coverage(doc),
        check_coordinates(doc),
        check_unplaced_links(doc),
    ]
