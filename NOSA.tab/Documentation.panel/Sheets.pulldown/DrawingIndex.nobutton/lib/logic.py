# -*- coding: utf-8 -*-
import io
"""
DrawingIndex Logic — collect sheet data and build a drawing index.
Can export to CSV/HTML or create a Revit key schedule.
"""
import csv, os, sys

from pyrevit import DB

_lib = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', '..', 'lib'))
if _lib not in sys.path:
    sys.path.insert(0, _lib)
from nosa_utils import sheet_protocol as _sp

# NOSA File Naming Protocol fields — in display order
_NOSA_PARAM_ORDER = [
    # Core identification (NOSA protocol fields 1-8)
    'Sheet Number',           # F1+F2+F3+F4+F5+F6+F7 encoded
    'Sheet Name',             # Description
    'Project Number',         # Field 1
    'Originator',             # Field 2 (NOSA)
    'Functional Breakdown',   # Field 3 (DT, GA, SC...)
    'Spatial Breakdown',      # Field 4 (000, FND, ZZZ...)
    'Form',                   # Field 5 — read/write via sheet + title blocks
    'Discipline',             # Field 6 (S, C, X...)
    'Document Number',        # Field 7 (2200, 4000...)
    'Current Revision',       # Field 8 (P01, I01, C01...)
    'Current Revision Date',
    'Current Revision Description',
    # Standard sheet params
    'Scale',
    'Drawn By',
    'Checked By',
    'Designed By',
    'Approved By',
    'Sheet Issue Date',
    'File Path',
]

def _get_id(eid):
    if hasattr(eid, 'Value'): return eid.Value
    if hasattr(eid, 'IntegerValue'): return eid.IntegerValue
    return int(str(eid))

def _param_str(el, name_or_bip):
    try:
        if isinstance(name_or_bip, DB.BuiltInParameter):
            p = el.get_Parameter(name_or_bip)
        else:
            p = el.LookupParameter(name_or_bip)
        if p: return (p.AsString() or p.AsValueString() or '').strip()
    except Exception:
        pass
    return ''

def get_all_sheet_param_names(doc):
    """
    Return ordered param names for the Drawing Index, combining NOSA order
    with any extra custom parameters found on the first sheet.
    """
    all_names = list(_NOSA_PARAM_ORDER)
    sheets = list(DB.FilteredElementCollector(doc).OfClass(DB.ViewSheet).ToElements())
    if sheets:
        first = sheets[0]
        for p in first.Parameters:
            try:
                if p.Definition:
                    n = p.Definition.Name
                    if n and n not in all_names:
                        all_names.append(n)
            except Exception:
                pass
    return all_names


def _get_originator(doc, sheet):
    """Try sheet param 'Originator' first; fall back to project info 'Organization Name'."""
    val = _param_str(sheet, 'Originator')
    if not val:
        try:
            pi = doc.ProjectInformation
            if pi:
                val = _param_str(pi, 'Organization Name')
        except Exception:
            pass
    return val

def _get_revision_role(doc, sheet, role_name):
    """Read a field from the most recent revision record on the sheet."""
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

def collect_sheets(doc, filter_text='', param_names=None):
    sheets = []
    filter_lower = filter_text.lower()
    names = param_names or get_all_sheet_param_names(doc)
    for s in DB.FilteredElementCollector(doc).OfClass(DB.ViewSheet).ToElements():
        num  = s.SheetNumber or ''
        name = s.Name or ''
        if filter_lower and filter_lower not in num.lower() and filter_lower not in name.lower():
            continue
        row = {'id': _get_id(s.Id), 'number': num, 'name': name, 'element': s}
        # Collect all NOSA + custom params
        for pname in names:
            if pname in ('Sheet Number', 'Sheet Name'):
                continue
            if pname == 'Form':
                row[pname] = _sp.read_form_value(doc, s)
                continue
            row[pname] = _param_str(s, pname)
            # Legacy CSV / grids may still carry "Form Identifier"
            if pname == 'Form Identifier' and not row[pname]:
                row[pname] = _sp.read_form_value(doc, s)
        # Originator: sheet param → project info "Organization Name"
        row['Originator'] = _get_originator(doc, s)
        # Align project number fallback with Sheet Composer / project info
        if not row.get('Project Number'):
            row['Project Number'] = _sp.read_project_number(doc, s)
        # Checked By / Approved By: from revision record if not on sheet param
        if not row.get('Checked By'):
            row['Checked By'] = _get_revision_role(doc, s, 'Issued By') or _param_str(s, DB.BuiltInParameter.SHEET_CHECKED_BY)
        if not row.get('Approved By'):
            row['Approved By'] = _get_revision_role(doc, s, 'Issued to') or _param_str(s, 'Approved By')
        # BIP-based revision shortcut keys
        row['revision']       = _param_str(s, DB.BuiltInParameter.SHEET_CURRENT_REVISION) or row.get('Current Revision', '')
        row['revision_date']  = _param_str(s, DB.BuiltInParameter.SHEET_CURRENT_REVISION_DATE) or row.get('Current Revision Date', '')
        row['revision_desc']  = _param_str(s, DB.BuiltInParameter.SHEET_CURRENT_REVISION_DESCRIPTION) or row.get('Current Revision Description', '')
        # Shortcut keys for common params used in exports
        row['scale']    = row.get('Scale', '')
        row['drawn_by'] = row.get('Drawn By', '') or _param_str(s, DB.BuiltInParameter.SHEET_DRAWN_BY)
        try:
            row['viewport_count'] = len(list(s.GetAllViewports()))
        except Exception:
            row['viewport_count'] = 0
        sheets.append(row)
    return sorted(sheets, key=lambda x: x['number'])

def export_csv(sheets, path, param_names=None):
    if not sheets:
        return
    names = param_names or _NOSA_PARAM_ORDER
    with io.open(path, 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.writer(f)
        header = ['#', 'Sheet Number', 'Sheet Name'] + [n for n in names if n not in ('Sheet Number','Sheet Name')] + ['Views']
        w.writerow(header)
        for i, s in enumerate(sheets, 1):
            row = [i, s['number'], s['name']]
            for n in names:
                if n in ('Sheet Number','Sheet Name'):
                    continue
                row.append(s.get(n, ''))
            row.append(s.get('viewport_count', 0))
            w.writerow(row)

def export_html(sheets, path, project_name=''):
    rows = ''
    for i, s in enumerate(sheets, 1):
        rows += ("<tr><td>{}</td><td><b>{}</b></td><td>{}</td><td>{}</td>"
                 "<td>{}</td><td>{}</td><td>{}</td></tr>").format(
            i, s['number'], s['name'], s['scale'], s['revision'],
            s['revision_desc'], s['drawn_by'])
    html = """<!DOCTYPE html><html><head><meta charset='utf-8'>
<style>body{{font-family:'Century Gothic',sans-serif;padding:20px}}
h1{{color:#FF5F00}}table{{border-collapse:collapse;width:100%}}
th{{background:#FF5F00;color:white;padding:8px 10px;text-align:left}}
td{{padding:6px 10px;border-bottom:1px solid #eee}}
tr:nth-child(even){{background:#f9f9f9}}</style></head><body>
<h1>Drawing Index — {proj}</h1>
<table><tr><th>#</th><th>Number</th><th>Name</th><th>Scale</th>
<th>Rev</th><th>Rev Description</th><th>Drawn By</th></tr>
{rows}</table></body></html>""".format(proj=project_name or 'Project', rows=rows)
    with io.open(path, 'w', encoding='utf-8-sig', newline='') as f:
        f.write(html)

def get_project_name(doc):
    try:
        if doc.ProjectInformation:
            return doc.ProjectInformation.Name or ''
    except Exception:
        pass
    return ''
