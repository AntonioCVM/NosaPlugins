# -*- coding: utf-8 -*-
"""
Shared NOSA sheet / titleblock parameter helpers (Drawing Index, Sheet Composer).

The 'Form' field often lives on title block instances rather than the ViewSheet.
ViewSheet.SheetNumber stores F7 (document number) only — not the full NOSA string.
"""
import re

from Autodesk.Revit import DB

from nosa_utils.param_element_ops import param_edit_is_unchanged, set_param_from_string
from nosa_utils.revit_helpers import get_id_value

NOSA_ORIGINATOR = u'NOSA'

# F-key → parameter name aliases (sheet + title block LookupParameter names)
NOSA_FIELD_ALIASES = {
    u'f1': (
        u'Project Number', u'PROJECT_NUMBER', u'IDS_PROJECT_NUMBER', u'NOSA_PROJECT_NUMBER',
        u'Project No', u'Proj No', u'Proj. No.', u'Project No.',
    ),
    u'f2': (
        u'Originator', u'IDS_ORIGINATOR', u'NOSA_ORIGINATOR',
        u'Organization Name', u'ORGANIZATION_NAME',
    ),
    u'f3': (
        u'Functional Breakdown', u'FUNCTIONAL_BREAKDOWN', u'IDS_FUNCTIONAL',
        u'IDS_FUNCTIONAL_BREAKDOWN', u'NOSA_FUNCTIONAL',
    ),
    u'f4': (
        u'Spatial Breakdown', u'SPATIAL_BREAKDOWN', u'IDS_SPATIAL',
        u'IDS_SPATIAL_BREAKDOWN', u'NOSA_SPATIAL',
    ),
    u'f6': (
        u'Discipline', u'DISCIPLINE', u'IDS_DISCIPLINE', u'NOSA_DISCIPLINE',
    ),
    u'f7': (
        u'Number', u'Document Number', u'DOCUMENT_NUMBER',
        u'IDS_DOCUMENT_NUMBER', u'NOSA_DOCUMENT_NUMBER',
    ),
    u'f7_titleblock': (
        u'Sheet Number',
    ),
    u'f8': (
        u'Current Revision', u'Revision', u'CURRENT_REVISION',
        u'IDS_REVISION', u'IDS_CURRENT_REVISION', u'NOSA_REVISION',
    ),
}

# Legacy name → f-key (used by write_param_on_hosts callers)
NOSA_PARAM_MAP = {
    u'Project Number':       u'f1',
    u'Originator':           u'f2',
    u'Functional Breakdown': u'f3',
    u'Spatial Breakdown':    u'f4',
    u'Form':                 u'f5',
    u'Discipline':           u'f6',
    u'Document Number':      u'f7',
    u'Number':               u'f7',
    u'Current Revision':     u'f8',
    u'Revision':             u'f8',
}

NOSA_PROTOCOL_PARAMS = [
    (u'Project Number',        u'f1'),
    (u'Originator',            u'f2'),
    (u'Functional Breakdown',  u'f3'),
    (u'Spatial Breakdown',     u'f4'),
    (u'Form',                  u'f5'),
    (u'Discipline',            u'f6'),
    (u'Document Number',       u'f7'),
    (u'Current Revision',      u'f8'),
]

_BIP_FALLBACK = {
    u'Drawn By':   getattr(DB.BuiltInParameter, 'SHEET_DRAWN_BY', None),
    u'Checked By': getattr(DB.BuiltInParameter, 'SHEET_CHECKED_BY', None),
    u'Sheet Name': getattr(DB.BuiltInParameter, 'SHEET_NAME', None),
}

NOSA_NUMBER_RE = re.compile(
    r'^(\d{5})\s+NOSA\s+(\w{2})\s+(\w{3})\s+(\w)\s+(\w)\s+(\d{4})\s+(\S+)$'
)

_FORM_READ_NAMES = (
    u'Form',
    u'FORM',
    u'Form Identifier',
    u'IDS_FORM',
    u'NOSA_FORM',
)

_FORM_WRITE_NAMES = (
    u'Form',
    u'FORM',
    u'Form Identifier',
)

# F1/F2 often live on title blocks (sometimes project-linked labels).
_FKEY_PROJECT_BIP = {
    u'f1': getattr(DB.BuiltInParameter, 'PROJECT_NUMBER', None),
    u'f2': (getattr(DB.BuiltInParameter, 'ORGANIZATION_NAME', None)
            or getattr(DB.BuiltInParameter, 'PROJECT_ORGANIZATION_NAME', None)),
}

_FKEY_READONLY_INFO = {
    u'f1': u'F1 is project-linked (read-only)',
    u'f2': u'F2 is read-only — value already matches',
}

# Fields that prefer title block instances before ViewSheet.
_TB_FIRST_FKEYS = frozenset((u'f1', u'f2'))


def _as_text(p):
    if not p:
        return u''
    try:
        return (p.AsString() or p.AsValueString() or u'').strip()
    except Exception:
        return u''


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


def _host_label(el, sheet):
    if el is None:
        return u'unknown'
    try:
        if el.Id == sheet.Id:
            return u'ViewSheet'
    except Exception:
        pass
    try:
        if isinstance(el, DB.ElementType):
            return u'Title block type: {}'.format(el.Name or u'?')
    except Exception:
        pass
    try:
        cat = el.Category
        if cat and cat.Name:
            return u'{} instance'.format(cat.Name)
    except Exception:
        pass
    return u'Title block instance'


def iter_write_hosts(doc, sheet):
    """DiRoots order: ViewSheet, title block instances, then title block types."""
    yield sheet
    type_ids = []
    try:
        for tb in (DB.FilteredElementCollector(doc, sheet.Id)
                   .OfCategory(DB.BuiltInCategory.OST_TitleBlocks)
                   .WhereElementIsNotElementType()
                   .ToElements()):
            yield tb
            try:
                tid = tb.GetTypeId()
                if tid and tid != DB.ElementId.InvalidElementId:
                    type_ids.append(tid)
            except Exception:
                pass
    except Exception:
        pass
    seen = set()
    for tid in type_ids:
        try:
            key = get_id_value(tid)
        except Exception:
            key = id(tid)
        if key in seen:
            continue
        seen.add(key)
        try:
            el_type = doc.GetElement(tid)
            if el_type is not None:
                yield el_type
        except Exception:
            pass


def iter_write_hosts_tb_first(doc, sheet):
    """Title block instances, ViewSheet, then title block types (F1/F2)."""
    type_ids = []
    try:
        for tb in (DB.FilteredElementCollector(doc, sheet.Id)
                   .OfCategory(DB.BuiltInCategory.OST_TitleBlocks)
                   .WhereElementIsNotElementType()
                   .ToElements()):
            yield tb
            try:
                tid = tb.GetTypeId()
                if tid and tid != DB.ElementId.InvalidElementId:
                    type_ids.append(tid)
            except Exception:
                pass
    except Exception:
        pass
    yield sheet
    seen = set()
    for tid in type_ids:
        try:
            key = get_id_value(tid)
        except Exception:
            key = id(tid)
        if key in seen:
            continue
        seen.add(key)
        try:
            el_type = doc.GetElement(tid)
            if el_type is not None:
                yield el_type
        except Exception:
            pass


def _iter_element_parameters(el):
    """Ordered parameters when API supports it, else Parameters collection."""
    try:
        ordered = el.GetOrderedParameters()
        if ordered:
            for p in ordered:
                yield p
            return
    except Exception:
        pass
    try:
        for p in el.Parameters:
            yield p
    except Exception:
        pass


def collect_titleblock_param_names(doc, sheet):
    """Union of parameter Definition.Name on title block instances for one sheet."""
    names = set()
    try:
        for tb in (DB.FilteredElementCollector(doc, sheet.Id)
                   .OfCategory(DB.BuiltInCategory.OST_TitleBlocks)
                   .WhereElementIsNotElementType()
                   .ToElements()):
            for p in _iter_element_parameters(tb):
                try:
                    d = p.Definition
                    if d and d.Name:
                        names.add(d.Name.strip())
                except Exception:
                    pass
    except Exception:
        pass
    return sorted(names)


def _try_set_parameter(p, value, fkey=None):
    """Set param or treat read-only + matching value as success."""
    if not p:
        return False, u''
    if p.IsReadOnly:
        if param_edit_is_unchanged(p, value):
            info = _FKEY_READONLY_INFO.get(fkey, u'Read-only — value already matches')
            return True, info
        return False, u'Read-only — cannot write'
    if set_param_from_string(p, value):
        return True, u''
    return False, u''


def _write_aliases_on_element(el, aliases, value, fkey=None):
    for n in aliases:
        try:
            p = el.LookupParameter(n)
            if p:
                ok, info = _try_set_parameter(p, value, fkey)
                if ok:
                    return True, info
        except Exception:
            pass
    p = find_parameter_by_names(el, aliases)
    if p:
        ok, info = _try_set_parameter(p, value, fkey)
        if ok:
            return True, info
    bip = _FKEY_PROJECT_BIP.get(fkey)
    if bip is not None:
        try:
            p = el.get_Parameter(bip)
            if p:
                ok, info = _try_set_parameter(p, value, fkey)
                if ok:
                    return True, info
        except Exception:
            pass
    return False, u''


def _write_on_project_information(doc, fkey, value):
    bip = _FKEY_PROJECT_BIP.get(fkey)
    if bip is None:
        return False, u''
    try:
        pi = doc.ProjectInformation
        if pi is None:
            return False, u''
        p = pi.get_Parameter(bip)
        if p:
            ok, info = _try_set_parameter(p, value, fkey)
            if ok:
                return True, info or u'Project Information'
    except Exception:
        pass
    return False, u''


def _read_field_by_aliases(doc, sheet, aliases):
    for el in iter_sheet_and_titleblocks(doc, sheet):
        p = find_parameter_by_names(el, aliases)
        if p:
            t = _as_text(p)
            if t:
                return t
    return u''


def read_form_value(doc, sheet):
    """Readable Form value from sheet and/or its title blocks."""
    for el in iter_sheet_and_titleblocks(doc, sheet):
        p = find_parameter_by_names(el, _FORM_READ_NAMES)
        if p:
            t = _as_text(p)
            if t:
                return t
    return u''


def param_str(el, name_or_bip):
    """Read a parameter as display text (same pattern as Drawing Index / Sheet Composer)."""
    try:
        if isinstance(name_or_bip, DB.BuiltInParameter):
            p = el.get_Parameter(name_or_bip)
        else:
            p = el.LookupParameter(name_or_bip)
        if p:
            return (p.AsString() or p.AsValueString() or u'').strip()
    except Exception:
        pass
    return u''


def read_project_number(doc, sheet):
    v = _read_field_by_aliases(doc, sheet, NOSA_FIELD_ALIASES[u'f1'])
    if v:
        return v
    try:
        pi = doc.ProjectInformation
        if pi:
            p = pi.get_Parameter(DB.BuiltInParameter.PROJECT_NUMBER)
            if p:
                return (p.AsString() or p.AsValueString() or u'').strip()
    except Exception:
        pass
    return u''


def read_originator(doc, sheet):
    v = _read_field_by_aliases(doc, sheet, NOSA_FIELD_ALIASES[u'f2'])
    if v:
        return v
    try:
        pi = doc.ProjectInformation
        if pi:
            v = param_str(pi, u'Organization Name')
            if v:
                return v
    except Exception:
        pass
    return u''


def read_document_number(doc, sheet):
    """F7 — from Number/Document Number params, title block Sheet Number, or ViewSheet number."""
    v = _read_field_by_aliases(doc, sheet, NOSA_FIELD_ALIASES[u'f7'])
    if v:
        return v
    for el in iter_sheet_and_titleblocks(doc, sheet):
        if el.Id == sheet.Id:
            continue
        p = find_parameter_by_names(el, NOSA_FIELD_ALIASES[u'f7_titleblock'])
        if p:
            t = _as_text(p)
            if t:
                return t
    sn = (sheet.SheetNumber or u'').strip()
    parsed = parse_nosa_number(sn)
    if parsed:
        return parsed[u'f7']
    if sn and sn.isdigit() and len(sn) <= 4:
        return sn.zfill(4) if len(sn) < 4 else sn
    return u''


def read_revision_role(doc, sheet, role_name):
    """Read Issued By / Issued to from the latest revision cloud on the sheet."""
    try:
        rev_ids = list(sheet.GetAllRevisionIds())
        if not rev_ids:
            return u''
        rev = doc.GetElement(rev_ids[-1])
        if rev is None:
            return u''
        p = rev.LookupParameter(role_name)
        if p:
            return (p.AsString() or p.AsValueString() or u'').strip()
    except Exception:
        pass
    return u''


def build_nosa_number(f1, f3, f4, f5, f6, f7, f8):
    """Full NOSA display string — preview / index only, not for ViewSheet.SheetNumber."""
    return u'{} NOSA {} {} {} {} {} {}'.format(f1, f3, f4, f5, f6, f7, f8)


def build_nosa_display_from_sheet(doc, sheet):
    """Build full NOSA display string from individual sheet/title block parameters."""
    fields = read_nosa_fields_from_sheet(doc, sheet)
    if not fields.get(u'f7'):
        return (sheet.SheetNumber or u'').strip() if sheet else u''
    try:
        return build_nosa_number(
            fields.get(u'f1', u''), fields.get(u'f3', u''), fields.get(u'f4', u''),
            fields.get(u'f5', u''), fields.get(u'f6', u''), fields.get(u'f7', u''),
            fields.get(u'f8', u''))
    except Exception:
        return (sheet.SheetNumber or u'').strip() if sheet else u''


def parse_nosa_number(number):
    m = NOSA_NUMBER_RE.match((number or u'').strip())
    if not m:
        return None
    return {
        u'f1': m.group(1), u'f3': m.group(2), u'f4': m.group(3),
        u'f5': m.group(4), u'f6': m.group(5), u'f7': m.group(6), u'f8': m.group(7),
    }


def increment_document_number(f7, step=1):
    try:
        return u'{:04d}'.format(int(f7) + step)
    except Exception:
        return f7


def write_f7_on_hosts(doc, sheet, value):
    """F7: ViewSheet.SheetNumber + Number/Document Number on hosts; Sheet Number on title blocks."""
    if not value:
        return False, u''
    wrote = False
    host = u''
    try:
        sheet.SheetNumber = value
        wrote = True
        host = u'ViewSheet.SheetNumber'
    except Exception:
        pass
    sheet_aliases = NOSA_FIELD_ALIASES[u'f7']
    tb_aliases = sheet_aliases + NOSA_FIELD_ALIASES[u'f7_titleblock']
    for el in iter_write_hosts(doc, sheet):
        if el.Id == sheet.Id:
            names = sheet_aliases
        else:
            names = tb_aliases
        if _write_aliases_on_element(el, names, value)[0]:
            wrote = True
            host = _host_label(el, sheet)
    return wrote, host


def write_field_on_hosts(doc, sheet, fkey, value):
    """Write one NOSA field. Returns (ok, host, readonly, info)."""
    _fail = (False, u'', False, u'')
    if fkey == u'f8' and not value:
        return True, u'(skipped — empty)', False, u''
    if not value:
        return _fail
    if fkey == u'f5':
        ok, fail, host = write_form_value(doc, sheet, value)
        if ok > 0:
            return True, host or u'Form host', False, u''
        return _fail
    if fkey == u'f7':
        wrote, host = write_f7_on_hosts(doc, sheet, value)
        return wrote, host, False, u''
    aliases = NOSA_FIELD_ALIASES.get(fkey, ())
    if not aliases:
        return _fail
    host_iter = iter_write_hosts_tb_first if fkey in _TB_FIRST_FKEYS else iter_write_hosts
    for el in host_iter(doc, sheet):
        wrote, info = _write_aliases_on_element(el, aliases, value, fkey)
        if wrote:
            return True, _host_label(el, sheet), bool(info), info
    if fkey in _TB_FIRST_FKEYS:
        ok, info = _write_on_project_information(doc, fkey, value)
        if ok:
            host = u'Project Information'
            if info and info != u'Project Information':
                host = u'Project Information ({})'.format(info)
            return True, host, bool(info), info
    return _fail


def write_param_on_hosts(doc, sheet, param_name, value):
    """Write a string parameter on the sheet and any title blocks on it."""
    fkey = NOSA_PARAM_MAP.get(param_name)
    if fkey:
        ok, host, _, _ = write_field_on_hosts(doc, sheet, fkey, value)
        return ok
    if param_name == u'Form':
        ok, _, _ = write_form_value(doc, sheet, value)
        return ok > 0
    for el in iter_write_hosts(doc, sheet):
        p = find_parameter_by_names(el, (param_name,))
        if not p:
            try:
                p = el.LookupParameter(param_name)
            except Exception:
                p = None
        _bip = _BIP_FALLBACK.get(param_name)
        if not p and _bip is not None:
            try:
                p = el.get_Parameter(_bip)
            except Exception:
                p = None
        if p:
            ok, _ = _try_set_parameter(p, value)
            if ok:
                return True
    return False


NOSA_FIELD_DISPLAY_NAMES = {
    u'f1': u'F1 Project Number',
    u'f2': u'F2 Originator',
    u'f3': u'F3 Functional Breakdown',
    u'f4': u'F4 Spatial Breakdown',
    u'f5': u'F5 Form',
    u'f6': u'F6 Discipline',
    u'f7': u'F7 Document Number',
    u'f8': u'F8 Current Revision',
}


def write_nosa_protocol_fields(doc, sheet, f1, f3, f4, f5, f6, f7, f8, debug=False,
                               allow_renumber=True):
    """
    Write each NOSA protocol field to sheet/titleblock parameters individually.
    ViewSheet.SheetNumber is set to F7 (document number) only.
    When allow_renumber is False, F7 (and therefore SheetNumber) is left
    untouched — used once a sheet has been issued and must keep its number.
    Returns dict fkey -> {ok, host, skipped, readonly, info}.
    """
    vals = {
        u'f1': f1, u'f2': NOSA_ORIGINATOR, u'f3': f3, u'f4': f4, u'f5': f5,
        u'f6': f6, u'f7': f7, u'f8': f8,
    }
    results = {}
    for fkey in (u'f1', u'f2', u'f3', u'f4', u'f5', u'f6', u'f7', u'f8'):
        val = vals.get(fkey, u'')
        if fkey == u'f7' and not allow_renumber:
            results[fkey] = {
                u'ok': False, u'host': u'', u'skipped': True,
                u'readonly': False, u'info': u'Sheet numbering locked — not applied.',
            }
            continue
        if fkey == u'f8' and not val:
            results[fkey] = {
                u'ok': True, u'host': u'', u'skipped': True,
                u'readonly': False, u'info': u'',
            }
            continue
        if not val:
            results[fkey] = {
                u'ok': False, u'host': u'', u'skipped': True,
                u'readonly': False, u'info': u'',
            }
            continue
        ok, host, readonly, info = write_field_on_hosts(doc, sheet, fkey, val)
        entry = {
            u'ok': ok, u'host': host or u'', u'skipped': False,
            u'readonly': readonly, u'info': info or u'',
        }
        if debug and fkey in _TB_FIRST_FKEYS and not ok:
            entry[u'debug_params'] = collect_titleblock_param_names(doc, sheet)
        results[fkey] = entry
    return results


def _read_field_value(doc, sheet, pname):
    """Read a protocol field from sheet and title block hosts (with name aliases)."""
    fkey = NOSA_PARAM_MAP.get(pname)
    if fkey == u'f5':
        return read_form_value(doc, sheet)
    if fkey == u'f1':
        return read_project_number(doc, sheet)
    if fkey == u'f2':
        return read_originator(doc, sheet)
    if fkey == u'f7':
        return read_document_number(doc, sheet)
    if fkey:
        return _read_field_by_aliases(doc, sheet, NOSA_FIELD_ALIASES.get(fkey, (pname,)))
    return _read_field_by_aliases(doc, sheet, (pname,))


def read_nosa_fields_from_sheet(doc, sheet):
    """Read NOSA f1–f8 values from individual sheet/title block parameters."""
    fields = {}
    for fkey in (u'f1', u'f2', u'f3', u'f4', u'f5', u'f6', u'f7', u'f8'):
        if fkey == u'f5':
            v = read_form_value(doc, sheet)
        elif fkey == u'f1':
            v = read_project_number(doc, sheet)
        elif fkey == u'f2':
            v = read_originator(doc, sheet)
        elif fkey == u'f7':
            v = read_document_number(doc, sheet)
        else:
            v = _read_field_by_aliases(doc, sheet, NOSA_FIELD_ALIASES.get(fkey, ()))
        if v:
            fields[fkey] = v

    if len(fields) < 4:
        parsed = parse_nosa_number((sheet.SheetNumber or u'').strip())
        if parsed:
            for k, v in parsed.items():
                fields.setdefault(k, v)
            fields.setdefault(u'f2', NOSA_ORIGINATOR)
    return fields


def write_form_value(doc, sheet, value):
    """
    Write Form-like text to every host (sheet + title blocks + types) that exposes a writable param.
    Returns (ok_count, fail_count, first_host_label).
    """
    ok = fail = 0
    first_host = u''
    for el in iter_write_hosts(doc, sheet):
        wrote = False
        for n in _FORM_WRITE_NAMES:
            try:
                p = el.LookupParameter(n)
                if not p:
                    p = find_parameter_by_names(el, (n,))
                if p:
                    set_ok, _ = _try_set_parameter(p, value)
                    if set_ok:
                        ok += 1
                        wrote = True
                        if not first_host:
                            first_host = _host_label(el, sheet)
                        break
            except Exception:
                pass
        if not wrote:
            try:
                p = find_parameter_by_names(el, _FORM_WRITE_NAMES)
                if p:
                    set_ok, _ = _try_set_parameter(p, value)
                    if set_ok:
                        ok += 1
                        wrote = True
                        if not first_host:
                            first_host = _host_label(el, sheet)
            except Exception:
                pass
        if not wrote:
            fail += 1
    return ok, fail, first_host
