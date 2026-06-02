# -*- coding: utf-8 -*-
"""
Shared NOSA sheet / titleblock parameter helpers (Drawing Index, Sheet Composer).

The 'Form' field often lives on title block instances rather than the ViewSheet.
"""
from pyrevit import DB

_FORM_READ_NAMES = (
    'Form',
    'FORM',
    'Form Identifier',
    'IDS_FORM',
    'NOSA_FORM',
)

_FORM_WRITE_NAMES = (
    'Form',
    'FORM',
    'Form Identifier',
)


def _as_text(p):
    if not p:
        return ''
    try:
        return (p.AsString() or p.AsValueString() or '').strip()
    except Exception:
        return ''


def find_parameter_by_names(element, names):
    """LookupParameter by explicit names, then case-insensitive Definition.Name match."""
    for n in names:
        try:
            p = element.LookupParameter(n)
            if p:
                return p
        except Exception:
            pass
    try:
        lower = {n.lower() for n in names}
        for p in element.Parameters:
            try:
                d = p.Definition
                if d and d.Name and d.Name.strip().lower() in lower:
                    return p
            except Exception:
                pass
    except Exception:
        pass
    return None


def iter_sheet_and_titleblocks(doc, sheet):
    """Yield the sheet, then title block instances placed on that sheet."""
    yield sheet
    try:
        for tb in (DB.FilteredElementCollector(doc, sheet.Id)
                   .OfCategory(DB.BuiltInCategory.OST_TitleBlocks)
                   .WhereElementIsNotElementType()
                   .ToElements()):
            yield tb
    except Exception:
        pass


def read_form_value(doc, sheet):
    """Readable Form value from sheet and/or its title blocks."""
    for el in iter_sheet_and_titleblocks(doc, sheet):
        p = find_parameter_by_names(el, _FORM_READ_NAMES)
        if p:
            t = _as_text(p)
            if t:
                return t
    return ''


def param_str(el, name_or_bip):
    """Read a parameter as display text (same pattern as Drawing Index / Sheet Composer)."""
    try:
        if isinstance(name_or_bip, DB.BuiltInParameter):
            p = el.get_Parameter(name_or_bip)
        else:
            p = el.LookupParameter(name_or_bip)
        if p:
            return (p.AsString() or p.AsValueString() or '').strip()
    except Exception:
        pass
    return ''


def read_project_number(doc, sheet):
    v = param_str(sheet, 'Project Number')
    if v:
        return v
    try:
        pi = doc.ProjectInformation
        if pi:
            p = pi.get_Parameter(DB.BuiltInParameter.PROJECT_NUMBER)
            if p:
                return (p.AsString() or p.AsValueString() or '').strip()
    except Exception:
        pass
    return ''


def read_originator(doc, sheet):
    v = param_str(sheet, 'Originator')
    if not v:
        try:
            pi = doc.ProjectInformation
            if pi:
                v = param_str(pi, 'Organization Name')
        except Exception:
            pass
    return v


def read_revision_role(doc, sheet, role_name):
    """Read Issued By / Issued to from the latest revision cloud on the sheet."""
    try:
        rev_ids = list(sheet.GetAllRevisionIds())
        if not rev_ids:
            return ''
        rev = doc.GetElement(rev_ids[-1])
        if rev is None:
            return ''
        p = rev.LookupParameter(role_name)
        if p:
            return (p.AsString() or p.AsValueString() or '').strip()
    except Exception:
        pass
    return ''


def write_form_value(doc, sheet, value):
    """
    Write Form-like text to every host (sheet + title blocks) that exposes a writable param.
    Returns (ok_count, fail_count).
    """
    ok = fail = 0
    for el in iter_sheet_and_titleblocks(doc, sheet):
        wrote = False
        for n in _FORM_WRITE_NAMES:
            try:
                p = el.LookupParameter(n)
                if not p:
                    p = find_parameter_by_names(el, (n,))
                if p and not p.IsReadOnly:
                    p.Set(value)
                    ok += 1
                    wrote = True
                    break
            except Exception:
                pass
        if not wrote:
            try:
                p = find_parameter_by_names(el, _FORM_WRITE_NAMES)
                if p and not p.IsReadOnly:
                    p.Set(value)
                    ok += 1
                    wrote = True
            except Exception:
                pass
        if not wrote:
            fail += 1
    return ok, fail
