# -*- coding: utf-8 -*-
import io
"""Excel Sync Logic — import CSV data and map to Revit parameters."""
import sys, os, csv
from pyrevit import DB

_lib = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', 'lib'))
if _lib not in sys.path:
    sys.path.insert(0, _lib)
from nosa_utils.revit_helpers import get_id_value


def load_csv(path):
    """
    Parse CSV file. Returns (headers, rows) where rows is list of dicts.
    Raises on file/parse errors.
    """
    headers = []
    rows    = []
    with io.open(path, 'r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        headers = reader.fieldnames or []
        for row in reader:
            rows.append(dict(row))
    return list(headers), rows


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
            pass
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
                pass
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

    with DB.Transaction(doc, "Excel Sync — Apply Parameters") as t:
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
