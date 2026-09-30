# -*- coding: utf-8 -*-
import json
import os
import sys

from Autodesk.Revit import DB

_lib = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', '..', 'lib'))
if _lib not in sys.path:
    sys.path.insert(0, _lib)

from nosa_utils.revit_helpers import get_id_value
from nosa_utils.telemetry import log_swallowed
_LOG = u'ModelHealthHub/parameter_drift'


def get_shared_param_names(doc):
    """Return sorted list of shared parameter names defined in the project."""
    names = []
    try:
        for spe in DB.FilteredElementCollector(doc) \
                     .OfClass(DB.SharedParameterElement).ToElements():
            try:
                names.append(spe.GetDefinition().Name)
            except Exception:
                log_swallowed(_LOG, u'get_shared_param_names')
    except Exception:
        log_swallowed(_LOG, u'get_shared_param_names#2')
    return sorted(set(names))


def snapshot_model(doc, param_names):
    """
    Return {element_key: {param_name: value_str}} for all elements that carry
    any of the given shared parameter names.
    element_key = "{category}:{mark}" or "{category}:{element_id}".
    """
    if not param_names:
        return {}

    param_set = set(param_names)
    result = {}

    categories = [
        DB.BuiltInCategory.OST_StructuralColumns,
        DB.BuiltInCategory.OST_StructuralFraming,
        DB.BuiltInCategory.OST_StructuralFoundation,
        DB.BuiltInCategory.OST_Floors,
        DB.BuiltInCategory.OST_Walls,
        DB.BuiltInCategory.OST_GenericModel,
    ]

    def _collect(bic):
        try:
            return list(DB.FilteredElementCollector(doc)
                        .OfCategory(bic)
                        .WhereElementIsNotElementType()
                        .ToElements())
        except Exception:
            return []

    for bic in categories:
        cat_name = bic.ToString().replace('OST_', '')
        for el in _collect(bic):
            vals = {}
            for pname in param_set:
                try:
                    p = el.LookupParameter(pname)
                    if p and p.HasValue:
                        vals[pname] = p.AsValueString() or p.AsString() or u''
                except Exception:
                    log_swallowed(_LOG, u'snapshot_model')
            if vals:
                try:
                    mark_p = el.LookupParameter(u'Mark')
                    mark = (mark_p.AsString() or u'').strip() if (mark_p and mark_p.HasValue) else u''
                    key = u'{}:{}'.format(cat_name, mark or str(get_id_value(el.Id)))
                except Exception:
                    key = u'{}:{}'.format(cat_name, get_id_value(el.Id))
                result[key] = vals

    return result


def compare_snapshots(baseline, current):
    """
    Return list of drift records:
    {'key': el_key, 'param': param_name, 'baseline': old_val, 'current': new_val, 'change': type}
    change: 'modified' | 'added' | 'removed'
    """
    diffs = []
    all_keys = set(list(baseline.keys()) + list(current.keys()))

    for key in sorted(all_keys):
        base_params = baseline.get(key, {})
        curr_params = current.get(key, {})
        all_params = set(list(base_params.keys()) + list(curr_params.keys()))
        for pname in sorted(all_params):
            bv = base_params.get(pname, u'')
            cv = curr_params.get(pname, u'')
            if bv == cv:
                continue
            if not bv and cv:
                change = u'Added'
            elif bv and not cv:
                change = u'Removed'
            else:
                change = u'Modified'
            diffs.append({
                'key':      key,
                'param':    pname,
                'baseline': bv,
                'current':  cv,
                'change':   change,
            })
    return diffs


def import_from_excel(path):
    """
    Read an Excel reference file as a flat baseline.
    Expected columns: Element Key | Parameter Name | Value
    Returns same format as snapshot_model.
    """
    try:
        import openpyxl
        wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
        ws = wb.active
        rows = list(ws.iter_rows(min_row=2, values_only=True))
        wb.close()
    except Exception as e:
        raise IOError(u'Cannot read Excel file: {}'.format(e))

    result = {}
    for row in rows:
        if not row or len(row) < 3:
            continue
        key   = u'{}'.format(row[0] or u'').strip()
        pname = u'{}'.format(row[1] or u'').strip()
        value = u'{}'.format(row[2] or u'').strip()
        if key and pname:
            result.setdefault(key, {})[pname] = value
    return result


def resolve_key_elements(doc, keys):
    """
    Return ElementIds for drift keys ('Category:Mark' or 'Category:id').
    Numeric suffixes resolve directly; mark suffixes are matched by scanning
    model elements of the same category name.
    """
    from nosa_utils.revit_helpers import element_id_from_int
    ids = []
    marks = {}
    for key in keys:
        try:
            cat, _, suffix = key.partition(u':')
        except Exception:
            continue
        if not suffix:
            continue
        if suffix.isdigit():
            try:
                ids.append(element_id_from_int(int(suffix)))
                continue
            except Exception:
                log_swallowed(_LOG, u'resolve_key_elements')
        marks.setdefault(cat, set()).add(suffix)
    if marks:
        for el in (DB.FilteredElementCollector(doc)
                   .WhereElementIsNotElementType()
                   .ToElements()):
            try:
                cat = el.Category
                if cat is None or cat.Name not in marks:
                    continue
                p = el.LookupParameter(u'Mark')
                mark = (p.AsString() or u'').strip() if (p and p.HasValue) else u''
                if mark and mark in marks[cat.Name]:
                    ids.append(el.Id)
            except Exception:
                log_swallowed(_LOG, u'resolve_key_elements#2')
    return ids


def export_diffs_csv(diffs, path):
    """Write drift report to CSV."""
    import csv
    with open(path, 'wb') as f:
        w = csv.writer(f)
        w.writerow(['Element', 'Parameter', 'Change', 'Baseline Value', 'Current Value'])
        for d in diffs:
            w.writerow([
                d['key'].encode('utf-8'),
                d['param'].encode('utf-8'),
                d['change'].encode('utf-8'),
                d['baseline'].encode('utf-8'),
                d['current'].encode('utf-8'),
            ])
