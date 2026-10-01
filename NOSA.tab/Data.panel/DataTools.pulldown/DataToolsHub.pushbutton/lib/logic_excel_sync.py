# -*- coding: utf-8 -*-
import io
"""Excel Sync Logic — import CSV data and map to Revit parameters."""
import sys, os, csv
from Autodesk.Revit import DB
_lib = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', '..', 'lib'))
if _lib not in sys.path:
    sys.path.insert(0, _lib)
from nosa_utils.revit_helpers import get_id_value
from nosa_utils.telemetry import log_swallowed
_LOG = u'DataToolsHub'


def load_csv(path):
    """Parse CSV file. Returns (headers, rows) where rows is list of dicts."""
    with io.open(path, 'r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        headers = list(reader.fieldnames or [])
        rows    = [dict(row) for row in reader]
    return headers, rows


def load_xlsx(path):
    """
    Parse .xlsx / .xlsm file using openpyxl.
    Returns (headers, rows) where rows is list of dicts.
    First non-empty row is treated as headers.
    Raises ImportError if openpyxl is unavailable.
    """
    import openpyxl
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    ws = wb.active
    rows_iter = ws.iter_rows(values_only=True)

    # First row → headers
    header_row = next(rows_iter, None)
    if header_row is None:
        wb.close()
        return [], []
    headers = [str(h).strip() if h is not None else u'' for h in header_row]

    rows = []
    for raw in rows_iter:
        if all(c is None for c in raw):
            continue  # skip blank rows
        row = {}
        for h, v in zip(headers, raw):
            row[h] = u'' if v is None else str(v)
        rows.append(row)

    wb.close()
    return headers, rows


def load_file(path):
    """
    Auto-detect format by extension and delegate to the appropriate loader.
    Supports .csv, .xlsx, .xlsm.  Falls back to CSV for unknown extensions.
    """
    ext = os.path.splitext(path)[1].lower()
    if ext in ('.xlsx', '.xlsm', '.xls'):
        return load_xlsx(path)
    return load_csv(path)


def list_workbook_sheets(path):
    """Return sheet names from an Excel workbook."""
    import openpyxl
    wb = openpyxl.load_workbook(path, read_only=True)
    names = list(wb.sheetnames)
    wb.close()
    return names


def load_xlsx_sheet(path, sheet_name):
    """Load a named sheet from an Excel workbook. Returns (headers, rows)."""
    import openpyxl
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    if sheet_name not in wb.sheetnames:
        wb.close()
        raise ValueError(u'Sheet not found: {}'.format(sheet_name))
    ws = wb[sheet_name]
    rows_iter = ws.iter_rows(values_only=True)
    header_row = next(rows_iter, None)
    if header_row is None:
        wb.close()
        return [], []
    headers = [str(h).strip() if h is not None else u'' for h in header_row]
    rows = []
    for raw in rows_iter:
        if all(c is None for c in raw):
            continue
        row = {}
        for h, v in zip(headers, raw):
            row[h] = u'' if v is None else str(v)
        rows.append(row)
    wb.close()
    return headers, rows


def _build_mark_index(doc):
    """Returns dict: mark_value_lower -> list of elements with that mark."""
    idx = {}
    els = DB.FilteredElementCollector(doc)\
            .WhereElementIsNotElementType()\
            .ToElements()
    for el in els:
        try:
            p = el.get_Parameter(DB.BuiltInParameter.ALL_MODEL_MARK)
            if p and p.HasValue:
                v = (p.AsString() or '').strip()
                if v:
                    k = v.lower()
                    if k not in idx:
                        idx[k] = []
                    idx[k].append(el)
        except Exception:
            log_swallowed(_LOG, u'_build_mark_index')
    return idx


def match_elements(doc, rows, key_col, match_by):
    """
    Match CSV rows to Revit elements using key_col.
    match_by: 'UniqueId' | 'Mark'
    Returns list of dicts: { 'row', 'element', 'matched', 'multiple', 'key' }
    """
    results = []
    if match_by == 'UniqueId':
        for row in rows:
            uid = str(row.get(key_col, '') or '').strip()
            el  = None
            try:
                if uid:
                    el = doc.GetElement(uid)
            except Exception:
                log_swallowed(_LOG, u'match_elements')
            results.append({'row': row, 'element': el,
                            'matched': el is not None, 'multiple': False, 'key': uid})
    else:
        idx = _build_mark_index(doc)
        for row in rows:
            mark = str(row.get(key_col, '') or '').strip()
            els  = idx.get(mark.lower(), [])
            el   = els[0] if els else None
            results.append({'row': row, 'element': el,
                            'matched': el is not None, 'multiple': len(els) > 1, 'key': mark})
    return results


def apply_mapping(doc, matched_rows, mapping):
    """
    Set parameter values on matched elements.
    mapping: list of (csv_col_name, revit_param_name) strings.
    Returns (ok_count, failed_count, skipped_count).
    """
    ok = failed = skipped = 0
    active_mapping = [(c, p) for c, p in mapping if c and p and p.strip()]
    if not active_mapping:
        return 0, 0, len(matched_rows)

    with DB.Transaction(doc, u"NOSA — Excel Sync — Apply Parameters") as t:
        t.Start()
        for item in matched_rows:
            if not item['matched']:
                skipped += 1
                continue
            el       = item['element']
            row_data = item['row']
            for csv_col, param_name in active_mapping:
                val = str(row_data.get(csv_col, '') or '').strip()
                try:
                    p = el.LookupParameter(param_name.strip())
                    if p is None or p.IsReadOnly:
                        failed += 1
                        continue
                    st = p.StorageType
                    if st == DB.StorageType.String:
                        p.Set(val)
                        ok += 1
                    elif st == DB.StorageType.Integer:
                        p.Set(int(float(val)))
                        ok += 1
                    elif st == DB.StorageType.Double:
                        p.Set(float(val))
                        ok += 1
                    else:
                        failed += 1
                except Exception:
                    failed += 1
        t.Commit()
    return ok, failed, skipped


def export_to_csv(doc, param_names, match_by, output_path):
    """
    Read param_names from every non-type element and write to CSV.
    First column is UniqueId or Mark (determined by match_by).
    Returns (row_count, missing_params).
    """
    from nosa_utils.progress import nosa_progress

    key_col = 'UniqueId' if match_by == 'UniqueId' else 'Mark'
    param_names = [p.strip() for p in param_names if p.strip()]
    headers = [key_col] + param_names
    missing = set()
    rows = []

    els = list(DB.FilteredElementCollector(doc)
                 .WhereElementIsNotElementType()
                 .ToElements())

    with nosa_progress(len(els), u'Exporting parameters', step=200) as pb:
        for i, el in enumerate(els):
            pb.update(i)
            if pb.cancelled:
                break
            # key
            if match_by == 'UniqueId':
                key = el.UniqueId
            else:
                try:
                    p = el.get_Parameter(DB.BuiltInParameter.ALL_MODEL_MARK)
                    key = (p.AsString() or '').strip() if (p and p.HasValue) else ''
                except Exception:
                    key = ''
            if not key:
                continue

            row = {key_col: key}
            for pname in param_names:
                try:
                    p = el.LookupParameter(pname)
                    if p is None:
                        missing.add(pname)
                        row[pname] = ''
                    else:
                        st = p.StorageType
                        if st == DB.StorageType.String:
                            row[pname] = p.AsString() or ''
                        elif st == DB.StorageType.Integer:
                            row[pname] = str(p.AsInteger())
                        elif st == DB.StorageType.Double:
                            row[pname] = str(p.AsDouble())
                        else:
                            row[pname] = ''
                except Exception:
                    row[pname] = ''
                    missing.add(pname)
            rows.append(row)

    with io.open(output_path, 'w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=headers)
        writer.writeheader()
        writer.writerows(rows)

    return len(rows), sorted(missing)


def format_preview(headers, rows, max_rows=20):
    """Return a fixed-width text preview of the CSV data."""
    display_rows = rows[:max_rows]
    if not display_rows:
        return '(empty)'

    widths = {h: len(h) for h in headers}
    for row in display_rows:
        for h in headers:
            widths[h] = max(widths[h], len(str(row.get(h, '') or '')))

    sep = '+' + '+'.join('-' * (widths[h] + 2) for h in headers) + '+'
    header_line = '|' + '|'.join(
        ' ' + h.ljust(widths[h]) + ' ' for h in headers
    ) + '|'

    lines = [sep, header_line, sep]
    for row in display_rows:
        line = '|' + '|'.join(
            ' ' + str(row.get(h, '') or '').ljust(widths[h]) + ' ' for h in headers
        ) + '|'
        lines.append(line)
    lines.append(sep)
    if len(rows) > max_rows:
        lines.append('  ... and {} more rows'.format(len(rows) - max_rows))
    return '\n'.join(lines)
