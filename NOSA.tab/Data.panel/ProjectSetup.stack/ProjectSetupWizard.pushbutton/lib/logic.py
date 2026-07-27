# -*- coding: utf-8 -*-
"""Project Setup Wizard — Logic

Performs one-click project configuration: worksets, project info,
levels, title block sheets, project parameters.
"""
from Autodesk.Revit import DB
from pyrevit import revit
_NOSA_WORKSETS = [
    'NOSA_Structure',
    'NOSA_Architecture',
    'NOSA_MEP',
    'NOSA_Links',
    'NOSA_Coordination',
    'Shared Levels and Grids',
]

_DEFAULT_LEVELS = [
    ('Foundation', -1500),
    ('Ground Floor', 0),
    ('First Floor', 3000),
    ('Roof', 6000),
]


def _ft(mm):
    return mm / 304.8


def set_project_info(doc, info):
    """
    Set project information fields.
    info: dict with keys 'name', 'number', 'client', 'address', 'status', 'code'
    """
    pi = doc.ProjectInformation
    with revit.Transaction('NOSA Setup — Project Information'):
        if 'name' in info and info['name']:
            try: pi.Name = info['name']
            except Exception: pass
        if 'number' in info and info['number']:
            try: pi.Number = info['number']
            except Exception: pass
        if 'client' in info and info['client']:
            try: pi.ClientName = info['client']
            except Exception: pass
        if 'address' in info and info['address']:
            try: pi.Address = info['address']
            except Exception: pass
        if 'status' in info and info['status']:
            try: pi.Status = info['status']
            except Exception: pass
        if 'code' in info and info['code']:
            p = pi.LookupParameter('Building Code')
            if p and not p.IsReadOnly:
                try: p.Set(info['code'])
                except Exception: pass
    return True


def create_worksets(doc):
    """Create NOSA standard worksets (skips existing ones)."""
    if not doc.IsWorkshared:
        return 0, 'Model is not workshared. Enable worksharing first.'
    existing = set()
    try:
        for ws in (DB.FilteredWorksetCollector(doc)
                     .OfKind(DB.WorksetKind.UserWorkset)):
            existing.add(ws.Name)
    except Exception:
        pass

    created = 0
    with revit.Transaction('NOSA Setup — Create Worksets'):
        for name in _NOSA_WORKSETS:
            if name not in existing:
                try:
                    DB.Workset.Create(doc, name)
                    created += 1
                except Exception:
                    pass
    return created, None


def create_standard_levels(doc):
    """Create default NOSA levels if fewer than 2 levels exist."""
    existing = list(
        DB.FilteredElementCollector(doc)
          .OfClass(DB.Level)
          .ToElements()
    )
    if len(existing) >= 2:
        return 0, 'Levels already exist ({} found) — skipped.'.format(len(existing))

    created = 0
    with revit.Transaction('NOSA Setup — Create Levels'):
        for name, elev_mm in _DEFAULT_LEVELS:
            already = any(lv.Name == name for lv in existing)
            if already:
                continue
            try:
                lv = DB.Level.Create(doc, _ft(elev_mm))
                lv.Name = name
                created += 1
            except Exception:
                pass
    return created, None


def create_cover_sheet(doc, sheet_number='00-00', sheet_name='Cover Sheet'):
    """Create a cover sheet using the first available title block."""
    tb = _get_title_block(doc)
    with revit.Transaction('NOSA Setup — Cover Sheet'):
        sheet = DB.ViewSheet.Create(doc, tb)
        sheet.SheetNumber = sheet_number
        sheet.Name = sheet_name
    return sheet


def create_drawing_index(doc, sheet_number='00-01', sheet_name='Drawing Index'):
    """Create a drawing index sheet."""
    tb = _get_title_block(doc)
    with revit.Transaction('NOSA Setup — Drawing Index Sheet'):
        sheet = DB.ViewSheet.Create(doc, tb)
        sheet.SheetNumber = sheet_number
        sheet.Name = sheet_name
    return sheet


def _get_title_block(doc):
    tbs = list(
        DB.FilteredElementCollector(doc)
          .OfCategory(DB.BuiltInCategory.OST_TitleBlocks)
          .WhereElementIsElementType()
          .ToElements()
    )
    if tbs:
        return tbs[0].Id
    return DB.ElementId.InvalidElementId


def get_project_info(doc):
    """Return dict of current project information."""
    pi = doc.ProjectInformation
    return {
        'name':    getattr(pi, 'Name',       '') or '',
        'number':  getattr(pi, 'Number',     '') or '',
        'client':  getattr(pi, 'ClientName', '') or '',
        'address': getattr(pi, 'Address',    '') or '',
        'status':  getattr(pi, 'Status',     '') or '',
    }
