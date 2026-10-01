# -*- coding: utf-8 -*-
import io
"""Sheet Composer Logic — clone sheets, renumber, edit params, import/export CSV."""
import sys, os, csv
from Autodesk.Revit import DB
_lib = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', '..', 'lib'))
if _lib not in sys.path:
    sys.path.insert(0, _lib)
from nosa_utils.revit_helpers import coerce_element_id, get_id_value
from nosa_utils import sheet_protocol as _sp

# ── helpers ───────────────────────────────────────────────────────────────────

def _get_id_int(eid):
    try:
        return get_id_value(eid)
    except Exception:
        return int(str(eid))


def get_all_sheets(doc):
    """Returns list of dicts: { id, name, number, sheet }."""
    result = []
    for s in DB.FilteredElementCollector(doc).OfClass(DB.ViewSheet).ToElements():
        try:
            result.append({
                'id':     get_id_value(s.Id),
                'name':   s.Name or u'',
                'number': s.SheetNumber or u'',
                'sheet':  s,
            })
        except Exception:
            pass
    result.sort(key=lambda r: r['number'])
    return result


def get_titleblock_types(doc):
    """Returns list of (ElementId, name) for title block types."""
    tbs = DB.FilteredElementCollector(doc)\
            .OfCategory(DB.BuiltInCategory.OST_TitleBlocks)\
            .WhereElementIsElementType()\
            .ToElements()
    pairs = []
    for t in tbs:
        try:
            fam_name  = t.Family.Name if (hasattr(t, 'Family') and t.Family) else u''
            sym_param = t.get_Parameter(DB.BuiltInParameter.SYMBOL_NAME_PARAM)
            type_name = sym_param.AsString() if sym_param else u''
            label = u'{} : {}'.format(fam_name, type_name) if fam_name else type_name
            pairs.append((t.Id, label))
        except Exception:
            pass
    pairs.sort(key=lambda x: x[1])
    return pairs


def _is_legend_or_schedule(view):
    try:
        vt = view.ViewType
        return vt in (DB.ViewType.Legend, DB.ViewType.Schedule,
                      DB.ViewType.ColumnSchedule, DB.ViewType.PanelSchedule)
    except Exception:
        return False


# ── clone sheets ──────────────────────────────────────────────────────────────

def clone_sheet(doc, source_sheet, new_number, new_name, titleblock_id):
    new_sheet = DB.ViewSheet.Create(doc, titleblock_id)
    new_sheet.SheetNumber = new_number
    new_sheet.Name        = new_name
    for vp_id in list(source_sheet.GetAllViewports()):
        try:
            vp   = doc.GetElement(vp_id)
            view = doc.GetElement(vp.ViewId)
            center = vp.GetBoxCenter()
            if _is_legend_or_schedule(view):
                try:
                    DB.Viewport.Create(doc, new_sheet.Id, view.Id, center)
                except Exception:
                    pass
            else:
                try:
                    dup_id = view.Duplicate(DB.ViewDuplicateOption.WithDetailing)
                    DB.Viewport.Create(doc, new_sheet.Id, dup_id, center)
                except Exception:
                    pass
        except Exception:
            pass
    return new_sheet


def _existing_sheet_numbers_lower(doc):
    out = set()
    for sheet in DB.FilteredElementCollector(doc).OfClass(DB.ViewSheet).ToElements():
        try:
            sn = (sheet.SheetNumber or u'').strip().lower()
            if sn:
                out.add(sn)
        except Exception:
            pass
    return out


def allocate_unique_sheet_number(lowered_set, stem):
    """
    Produce a Revit-safe unique sheet number (case-insensitive) not in lowered_set,
    suffixing stem with -COPY, -COPY2, … and register it in lowered_set.
    lowered_set entries must be lowercase.
    """
    stem = (stem or u'').strip() or u'SHEET'
    cand = stem + u'-COPY'
    suffix_n = None
    while cand.lower() in lowered_set:
        suffix_n = 2 if suffix_n is None else suffix_n + 1
        cand = u'{}-COPY{}'.format(stem, suffix_n)
    lowered_set.add(cand.lower())
    return cand


def propose_unique_sheet_number(doc, stem):
    """Compute a guaranteed-unique candidate sheet number (does not modify the doc)."""
    lowered = _existing_sheet_numbers_lower(doc)
    stem_norm = (stem or u'').strip() or u'SHEET'
    return allocate_unique_sheet_number(lowered, stem_norm)


def duplicate_sheets_with_viewports(doc, source_elements, titleblock_id,
                                    name_suffix=u' (copy)'):
    """
    One duplicate per source sheet, preserving viewports (clone_sheet logic).
    Sheet numbers allocated as ORIG-COPY | ORIG-COPY2 | …
    Returns (created_count, [error_strings]).
    """
    lowered = _existing_sheet_numbers_lower(doc)
    created = 0
    errors  = []
    with DB.Transaction(doc, u'NOSA — Sheet Composer — Duplicate sheets (full clone)') as t:
        t.Start()
        for src in sorted(source_elements, key=lambda x: (x.SheetNumber or u'')):
            stem = (src.SheetNumber or u'SHEET').strip() or u'SHEET'
            cand = allocate_unique_sheet_number(lowered, stem)
            nm_src = src.Name or u''
            nm = ((nm_src or u'') + name_suffix).strip()
            try:
                clone_sheet(doc, src, cand, nm, titleblock_id)
                created += 1
            except Exception as ex:
                errors.append(u'{}: {}'.format(cand, ex))
        t.Commit()
    return created, errors


def duplicate_sheets_nosa_incremental(doc, source_sheets, count, titleblock_id,
                                      copy_viewports=True, name_suffix=u' (copy)',
                                      copy_package=True):
    """
    Create `count` duplicates per source sheet with incrementing F7 (document number).
    Writes full NOSA protocol fields on each new sheet.
    Returns (created_count, [error_strings]).
    """
    from nosa_utils import sheet_protocol as sp

    created = 0
    errors = []
    existing = set()
    for s in DB.FilteredElementCollector(doc).OfClass(DB.ViewSheet).ToElements():
        try:
            n = (s.SheetNumber or u'').strip()
            if n:
                existing.add(n)
        except Exception:
            pass

    with DB.Transaction(doc, u'NOSA — Duplicate Sheets') as t:
        t.Start()
        for src in sorted(source_sheets, key=lambda x: (x.SheetNumber or u'')):
            fields = sp.read_nosa_fields_from_sheet(doc, src)
            parsed = sp.parse_nosa_number(src.SheetNumber or u'')
            if parsed:
                for k, v in parsed.items():
                    fields.setdefault(k, v)
            f1 = fields.get('f1', u'00000')
            f3 = fields.get('f3', u'GA')
            f4 = fields.get('f4', u'ZZZ')
            f5 = fields.get('f5', u'D')
            f6 = fields.get('f6', u'S')
            f7 = fields.get('f7', u'2200')
            f8 = fields.get('f8', u'P01')
            base_name = src.Name or u''

            for i in range(1, count + 1):
                new_f7 = sp.increment_document_number(f7, i)
                suffix_n = 1
                while new_f7 in existing:
                    new_f7 = sp.increment_document_number(new_f7, 1)
                    suffix_n += 1
                    if suffix_n > 500:
                        break
                existing.add(new_f7)
                nm = (base_name + name_suffix).strip()
                if count > 1:
                    nm = u'{} {}'.format(nm, i).strip()
                try:
                    if copy_viewports:
                        new_sheet = clone_sheet(doc, src, new_f7, nm, titleblock_id)
                    else:
                        new_sheet = DB.ViewSheet.Create(doc, titleblock_id)
                        new_sheet.SheetNumber = new_f7
                        new_sheet.Name = nm
                    if new_sheet:
                        sp.write_nosa_protocol_fields(
                            doc, new_sheet, f1, f3, f4, f5, f6, new_f7, f8)
                        if copy_package:
                            pkg = _param_str(src, 'Package')
                            if pkg:
                                try:
                                    p = new_sheet.LookupParameter('Package')
                                    if p and not p.IsReadOnly:
                                        p.Set(pkg)
                                except Exception:
                                    pass
                    created += 1
                except Exception as ex:
                    errors.append(u'{}: {}'.format(new_f7, ex))
        t.Commit()
    return created, errors


def clone_sheets_batch(doc, source_sheet, count, start_number, name_template, titleblock_id):
    created = 0
    errors  = []
    source_num_prefix = ''.join(c for c in source_sheet.SheetNumber if not c.isdigit())
    with DB.Transaction(doc, u"NOSA — Sheet Composer — Clone Sheets") as t:
        t.Start()
        for i in range(count):
            num = "{}{}".format(source_num_prefix, start_number + i)
            try:
                name = name_template.replace('{n}', str(i + 1))
                clone_sheet(doc, source_sheet, num, name, titleblock_id)
                created += 1
            except Exception as e:
                errors.append("Sheet {}: {}".format(num, e))
        t.Commit()
    return created, errors


# ── renumber sheets ───────────────────────────────────────────────────────────

def renumber_sheets(doc, sheet_ids, prefix, start, step, suffix, pad):
    ok = failed = 0
    temp_prefix = '__NOSA_TEMP_{}__'.format(id(sheet_ids))
    with DB.Transaction(doc, u"NOSA — Sheet Composer — Renumber Sheets") as t:
        t.Start()
        for i, sid in enumerate(sheet_ids):
            try:
                s = doc.GetElement(coerce_element_id(sid))
                s.SheetNumber = "{}{}".format(temp_prefix, i)
            except Exception:
                pass
        for i, sid in enumerate(sheet_ids):
            try:
                s = doc.GetElement(coerce_element_id(sid))
                n = start + i * step
                num_part = str(n).zfill(pad) if pad > 0 else str(n)
                s.SheetNumber = "{}{}{}".format(prefix, num_part, suffix)
                ok += 1
            except Exception:
                failed += 1
        t.Commit()
    return ok, failed


# ── NOSA param helpers ────────────────────────────────────────────────────────

NOSA_PARAMS = [
    'Project Number', 'Originator', 'Functional Breakdown', 'Spatial Breakdown',
    'Form', 'Discipline', 'Document Number',
    'Current Revision', 'Current Revision Date', 'Current Revision Description',
    'Scale', 'Drawn By', 'Checked By', 'Approved By', 'Sheet Issue Date',
]

_BIP_MAP = {
    'Sheet Name': 'SHEET_NAME',
    'Drawn By':   'SHEET_DRAWN_BY',
    'Checked By': 'SHEET_CHECKED_BY',
}


def _param_str(el, pname):
    try:
        p = el.LookupParameter(pname)
        if p:
            return (p.AsString() or p.AsValueString() or '').strip()
    except Exception:
        pass
    return ''


def get_sheet_param_names(doc):
    """
    Writable text parameters found on sheets, excluding the fixed NOSA
    columns — candidates for extra Edit-tab columns.
    """
    exclude = set(NOSA_PARAMS) | {u'Sheet Name', u'Sheet Number'}
    names = set()
    sampled = 0
    for s in DB.FilteredElementCollector(doc).OfClass(DB.ViewSheet).ToElements():
        try:
            for p in s.Parameters:
                try:
                    if p.IsReadOnly:
                        continue
                    if p.StorageType != DB.StorageType.String:
                        continue
                    d = p.Definition
                    if d and d.Name and d.Name not in exclude:
                        names.add(d.Name)
                except Exception:
                    pass
        except Exception:
            pass
        sampled += 1
        if sampled >= 5:
            break
    return sorted(names)


def write_param(element, param_name, value, doc=None):
    """Write a string value to a named parameter. Pass doc when writing Form (titleblocks)."""
    if param_name == 'Form' and doc is not None:
        wrote, _, _ = _sp.write_form_value(doc, element, value)
        return wrote > 0
    p = element.LookupParameter(param_name)
    if not p and param_name in _BIP_MAP:
        p = element.get_Parameter(getattr(DB.BuiltInParameter, _BIP_MAP[param_name]))
    if p and not p.IsReadOnly:
        p.Set(value)
        return True
    return False


# ── collect editable sheets ───────────────────────────────────────────────────

def collect_editable_sheets(doc, filter_text=''):
    """Return all sheets with NOSA params. filter_text matches number or name."""
    txt = (filter_text or '').strip().lower()
    result = []
    for s in DB.FilteredElementCollector(doc).OfClass(DB.ViewSheet).ToElements():
        num  = s.SheetNumber or ''
        name = s.Name or ''
        if txt and txt not in num.lower() and txt not in name.lower():
            continue
        row = {'element': s, 'id': get_id_value(s.Id), 'number': num, 'name': name}
        for pname in NOSA_PARAMS:
            if pname == 'Form':
                row[pname] = _sp.read_form_value(doc, s)
                continue
            row[pname] = _param_str(s, pname)
        row['Originator']        = _sp.read_originator(doc, s)
        if not row.get('Project Number'):
            row['Project Number'] = _sp.read_project_number(doc, s)
        if not row.get('Checked By'):
            row['Checked By'] = (
                _sp.read_revision_role(doc, s, 'Issued By')
                or _param_str(s, DB.BuiltInParameter.SHEET_CHECKED_BY))
        if not row.get('Approved By'):
            row['Approved By'] = (
                _sp.read_revision_role(doc, s, 'Issued to')
                or _param_str(s, 'Approved By'))
        try:
            row['view_count'] = len(list(s.GetAllViewports()))
        except Exception:
            row['view_count'] = 0
        result.append(row)
    return sorted(result, key=lambda r: r['number'])


# ── update sheets ─────────────────────────────────────────────────────────────

def update_sheets_batch(doc, changes):
    """
    changes: {sheet_number_str: {'_element': el, attr_name: val, ...}}
    param_map: {attr_name: param_name}
    Returns (ok, failed).
    """
    ok = failed = 0
    with DB.Transaction(doc, u"NOSA — Sheet Composer — Update Sheet Params") as t:
        t.Start()
        for snum, change_dict in changes.items():
            el = change_dict.get('_element')
            if el is None:
                failed += 1
                continue
            for pname, val in change_dict.items():
                if pname == '_element':
                    continue
                try:
                    if write_param(el, pname, val, doc):
                        ok += 1
                    else:
                        failed += 1
                except Exception:
                    failed += 1
        t.Commit()
    return ok, failed


# ── create sheets from data ───────────────────────────────────────────────────

def create_sheets_from_data(doc, rows, titleblock_id):
    """rows: list of dicts with 'number', 'name', and optional NOSA param keys."""
    created = 0
    errors  = []
    with DB.Transaction(doc, u"NOSA — Sheet Composer — Create Sheets") as t:
        t.Start()
        for row in rows:
            num  = (row.get('number') or row.get('Number') or '').strip()
            name = (row.get('name')   or row.get('Name')   or '').strip()
            if not num:
                errors.append("Skipped: missing sheet number")
                continue
            try:
                new_sheet = DB.ViewSheet.Create(doc, titleblock_id)
                new_sheet.SheetNumber = num
                if name:
                    new_sheet.Name = name
                for pname in NOSA_PARAMS:
                    val = row.get(pname)
                    if not val and pname == 'Form':
                        val = row.get('Form Identifier', '')
                    if val:
                        try:
                            write_param(new_sheet, pname, val, doc)
                        except Exception:
                            pass
                created += 1
            except Exception as e:
                errors.append("{}: {}".format(num, e))
        t.Commit()
    return created, errors


# ── CSV import ────────────────────────────────────────────────────────────────

def parse_csv_sheets(path):
    """Parse CSV file. Returns (headers, rows_as_dicts)."""
    rows = []
    headers = []
    with io.open(path, 'r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        headers = list(reader.fieldnames or [])
        for r in reader:
            rows.append({k: (v or '') for k, v in r.items()})
    return headers, rows


def import_sheets_from_csv(doc, rows, titleblock_id, mode='create'):
    """
    mode: 'create' | 'update' | 'both'
    Rows need a 'Number' or 'Sheet Number' column.
    Returns (created, updated, skipped).
    """
    existing = {}
    for s in DB.FilteredElementCollector(doc).OfClass(DB.ViewSheet).ToElements():
        existing[(s.SheetNumber or '').strip()] = s

    created = updated = skipped = 0
    with DB.Transaction(doc, u"NOSA — Sheet Composer — Import CSV") as t:
        t.Start()
        for row in rows:
            num  = (row.get('Number') or row.get('Sheet Number') or row.get('number') or '').strip()
            name = (row.get('Name')   or row.get('Sheet Name')   or row.get('name')   or '').strip()
            if not num:
                skipped += 1
                continue

            if num in existing:
                if mode in ('update', 'both'):
                    el = existing[num]
                    if name:
                        try: write_param(el, 'Sheet Name', name)
                        except Exception: pass
                    for pname in NOSA_PARAMS:
                        val = row.get(pname)
                        if not val and pname == 'Form':
                            val = row.get('Form Identifier', '')
                        if val:
                            try:
                                write_param(el, pname, val, doc)
                            except Exception:
                                pass
                    updated += 1
                else:
                    skipped += 1
            else:
                if mode in ('create', 'both'):
                    try:
                        new_sheet = DB.ViewSheet.Create(doc, titleblock_id)
                        new_sheet.SheetNumber = num
                        if name:
                            new_sheet.Name = name
                        for pname in NOSA_PARAMS:
                            val = row.get(pname)
                            if not val and pname == 'Form':
                                val = row.get('Form Identifier', '')
                            if val:
                                try:
                                    write_param(new_sheet, pname, val, doc)
                                except Exception:
                                    pass
                        created += 1
                    except Exception:
                        skipped += 1
                else:
                    skipped += 1
        t.Commit()
    return created, updated, skipped


# ── export CSV ────────────────────────────────────────────────────────────────

def export_csv_sheets(sheets, path):
    """Export editable sheet list (from collect_editable_sheets) to CSV."""
    if not sheets:
        return
    _FIELDS  = ['number', 'name'] + NOSA_PARAMS
    _HEADERS = {'number': 'Number', 'name': 'Name'}
    with io.open(path, 'w', encoding='utf-8', newline='') as f:
        f.write(u'\ufeff')  # one BOM: 'utf-8-sig' repeats it on every write in IronPython
        w = csv.writer(f)
        w.writerow([_HEADERS.get(k, k) for k in _FIELDS])
        for s in sheets:
            w.writerow([s.get(k, '') for k in _FIELDS])


def parse_xlsx_sheets(path):
    """
    Parse the first worksheet of an Excel file.
    Returns (headers, rows_as_dicts) — same shape as parse_csv_sheets,
    so import_sheets_from_csv() accepts the rows directly.
    """
    import openpyxl
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    ws = wb.active
    it = ws.iter_rows(values_only=True)
    first = next(it, None) or []
    headers = [u'{}'.format(h if h is not None else u'').strip() for h in first]
    rows = []
    for raw in it:
        if raw is None:
            continue
        row = {}
        empty = True
        for i, h in enumerate(headers):
            if not h:
                continue
            v = raw[i] if i < len(raw) else None
            s = u'' if v is None else u'{}'.format(v).strip()
            if s:
                empty = False
            row[h] = s
        if not empty:
            rows.append(row)
    wb.close()
    return headers, rows


def export_xlsx_sheets(sheets, path):
    """Export editable sheet list to an Excel workbook (round-trip ready)."""
    import openpyxl
    if not sheets:
        return
    _FIELDS  = ['number', 'name'] + NOSA_PARAMS
    _HEADERS = {'number': 'Number', 'name': 'Name'}
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = 'Sheets'
    ws.append([_HEADERS.get(k, k) for k in _FIELDS])
    try:
        from openpyxl.styles import Font, PatternFill
        fill = PatternFill('solid', fgColor='FF5F00')
        font = Font(bold=True, color='FFFFFF')
        for c in ws[1]:
            c.fill = fill
            c.font = font
        ws.freeze_panes = 'A2'
    except Exception:
        pass
    for s in sheets:
        ws.append([u'{}'.format(s.get(k, '') or u'') for k in _FIELDS])
    try:
        for col in ws.columns:
            width = max(len(u'{}'.format(c.value or u'')) for c in col) + 2
            ws.column_dimensions[col[0].column_letter].width = min(width, 60)
    except Exception:
        pass
    wb.save(path)
