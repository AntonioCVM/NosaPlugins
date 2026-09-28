# -*- coding: utf-8 -*-
"""
Shared sheet-parameter write helper for Sheet Export Hub.

Generalizes the pending-changes + single-Transaction pattern already proven
in Drawing Index (lib/ui.py Apply_Click): both the inline DataGrid cell edit
(Apply Parameter Edits button) and the batch "Edit Parameters..." dialog
funnel through apply_changes() so there is exactly one write path.

Sheet Number is deliberately excluded from what this module treats as
editable — renumbering (F1-F7) is Sheet Hub's job, not this plugin's.
"""
from Autodesk.Revit import DB
from pyrevit import revit

from nosa_utils import sheet_protocol as _sp

# Parameters this plugin will never write, even if present in a column
# preset. Sheet Number renumbering belongs to Sheet Hub; Document Number
# (NOSA field 7) is displayed as a read-only mirror of Sheet Number, not a
# parameter of its own — editing it would look like it worked and then
# revert on the next reload.
NON_EDITABLE_PARAMS = frozenset(['Sheet Number', 'Document Number'])

# LookupParameter-by-name fails for a few standard sheet fields on some
# templates; fall back to the known BuiltInParameter (same map Drawing
# Index already validated).
_BIP_FALLBACK_NAMES = {
    'Sheet Name': 'SHEET_NAME',
    'Drawn By':   'SHEET_DRAWN_BY',
    'Checked By': 'SHEET_CHECKED_BY',
    'Scale':      'VIEW_SCALE_PULLDOWN_METRIC',
}


def _bip_fallback(param_name):
    name = _BIP_FALLBACK_NAMES.get(param_name)
    return getattr(DB.BuiltInParameter, name, None) if name else None


def is_editable(param_name):
    return param_name not in NON_EDITABLE_PARAMS


def resolve_parameter(element, param_name):
    """Find the DB.Parameter for param_name on element, via name lookup
    then a known BuiltInParameter fallback. Returns None if not found."""
    try:
        p = element.LookupParameter(param_name)
        if p:
            return p
    except Exception:
        pass
    bip = _bip_fallback(param_name)
    if bip is not None:
        try:
            p = element.get_Parameter(bip)
            if p:
                return p
        except Exception:
            pass
    return None


def apply_changes(doc, elements_by_number, changes_by_number,
                   transaction_name='Sheet Export Hub — Apply parameter edits'):
    """
    Write pending parameter edits in a single transaction.

    Args:
        doc: active Document.
        elements_by_number: {sheet_number: ViewSheet/View element}
        changes_by_number:  {sheet_number: {param_name: new_value_str}}

    Returns:
        (ok_count, fail_count)
    """
    ok = fail = 0
    if not changes_by_number:
        return ok, fail

    with revit.Transaction(transaction_name):
        for number, changes in changes_by_number.items():
            element = elements_by_number.get(number)
            if element is None:
                fail += len(changes)
                continue
            for param_name, new_val in changes.items():
                if not is_editable(param_name):
                    fail += 1
                    continue
                try:
                    if param_name == 'Form':
                        wrote, _failed, _host = _sp.write_form_value(doc, element, new_val)
                        if wrote > 0:
                            ok += 1
                        else:
                            fail += 1
                        continue
                    p = resolve_parameter(element, param_name)
                    if p is not None and not p.IsReadOnly:
                        p.Set(new_val)
                        ok += 1
                    else:
                        fail += 1
                except Exception:
                    fail += 1

    return ok, fail
