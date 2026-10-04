# -*- coding: utf-8 -*-
"""Shared parameter discovery / edit helpers for Element and ElementType (IronPython-safe)."""

from Autodesk.Revit import DB

from nosa_utils.revit_helpers import get_id_value
from nosa_utils.revit_helpers import element_id_from_int
from nosa_utils.telemetry import log_swallowed
from nosa_utils import transactions as nosa_tx  # T8.1: no Revit failure dialogs

try:
    unicode
except NameError:
    unicode = str  # CPython 3 compat
_LOG = u'nosa_utils.param_element_ops'


def param_value_display(param):
    """Human-oriented display using Revit formatting when possible."""
    if param is None or not param.HasValue:
        return u''
    st = param.StorageType
    try:
        if st == DB.StorageType.String:
            return param.AsString() or u''
        if st == DB.StorageType.Double:
            try:
                vs = param.AsValueString()
                if vs:
                    return vs
            except Exception:
                log_swallowed(_LOG, u'param_value_display')
            return u'{:.6g}'.format(param.AsDouble())
        if st == DB.StorageType.Integer:
            try:
                vs = param.AsValueString()
                if vs:
                    return vs
                return unicode(param.AsInteger())
            except Exception:
                return unicode(param.AsInteger())
        if st == DB.StorageType.ElementId:
            return unicode(get_id_value(param.AsElementId()))
    except Exception:
        log_swallowed(_LOG, u'param_value_display')
    try:
        return param.AsValueString() or u''
    except Exception:
        return u''


def _param_kind_label(p):
    """'built_in' | 'shared' | 'other' — best-effort classification."""
    try:
        d = p.Definition
        edef = getattr(DB, 'ExternalDefinition', None)
        if edef is not None and isinstance(d, edef):
            return u'shared'
        bip = getattr(d, 'BuiltInParameter', None)
        inv = getattr(DB.BuiltInParameter, 'INVALID', None)
        if bip is not None and (inv is None or bip != inv):
            return u'built_in'
    except Exception:
        log_swallowed(_LOG, u'_param_kind_label')
    return u'other'


def discover_param_specs(sample_elements, writable_only=False, max_sample=350):
    """
    Sorted list of {'name','kind'} kind in built_in|shared|other (union across samples).
    """
    buckets = {}  # name -> set(kind)
    samp = sample_elements[: max(1, min(len(sample_elements), max_sample))]
    for el in samp:
        try:
            for p in el.Parameters:
                try:
                    if not p or not p.Definition:
                        continue
                    if writable_only and p.IsReadOnly:
                        continue
                    n = p.Definition.Name
                    if not n:
                        continue
                    k = _param_kind_label(p)
                    buckets.setdefault(n, set()).add(k)
                except Exception:
                    log_swallowed(_LOG, u'discover_param_specs')
        except Exception:
            log_swallowed(_LOG, u'discover_param_specs')
    out = []
    for name in sorted(buckets):
        ks = buckets[name]
        if u'shared' in ks:
            kind = u'shared'
        elif u'built_in' in ks:
            kind = u'built_in'
        else:
            kind = u'other'
        out.append({u'name': name, u'kind': kind})
    return out


def discover_param_names(sample_elements, writable_only=False, max_sample=350):
    return [x[u'name'] for x in discover_param_specs(
        sample_elements, writable_only, max_sample)]


def lookup_param_named(el, name):
    """Parameter on element/type matching Definition.Name."""
    try:
        p = el.LookupParameter(name)
        if p:
            return p
    except Exception:
        log_swallowed(_LOG, u'lookup_param_named')
    try:
        for p in el.Parameters:
            try:
                if p and p.Definition and p.Definition.Name == name:
                    return p
            except Exception:
                log_swallowed(_LOG, u'lookup_param_named')
    except Exception:
        log_swallowed(_LOG, u'lookup_param_named')
    return None


def user_double_to_internal(param, txt):
    """
    Interpret user-entered numeric string as display units → internal Revit units.
    Falls back to raw float(parse) like legacy scripts if conversion unavailable.
    """
    t = (txt if txt is not None else u'') or u''
    t = unicode(t).strip().replace(u',', u'.')
    if not t:
        return None
    try:
        display_val = float(t)
    except Exception:
        return None
    try:
        uid = param.GetUnitTypeId()
        uu = getattr(DB, 'UnitUtils', None)
        if uid is not None and uu is not None:
            return uu.ConvertToInternalUnits(display_val, uid)
    except Exception:
        log_swallowed(_LOG, u'user_double_to_internal')
    return display_val


def param_edit_is_unchanged(param, new_txt):
    """
    True when new_txt would leave the stored parameter value unchanged,
    comparing Doubles numerically after unit conversion attempts.
    """
    if param is None:
        return True
    ns = unicode(new_txt if new_txt is not None else u'').strip()
    if not param.HasValue:
        return len(ns) == 0

    try:
        st = param.StorageType
    except Exception:
        return False

    try:
        if st == DB.StorageType.String:
            cur = param.AsString() or u''
            return cur.strip() == ns
        if st == DB.StorageType.Integer:
            try:
                cur_i = param.AsInteger()
            except Exception:
                return False
            if not ns:
                return False
            try:
                return int(ns) == cur_i
            except Exception:
                try:
                    return int(float(ns.replace(u',', u'.'))) == cur_i
                except Exception:
                    return (param.AsValueString() or u'').strip() == ns
        if st == DB.StorageType.Double:
            internal_new = user_double_to_internal(param, ns)
            if internal_new is None:
                try:
                    return (param.AsValueString() or u'').strip() == ns
                except Exception:
                    return unicode(param_value_display(param)).strip() == ns
            try:
                cur = param.AsDouble()
                return abs(cur - internal_new) <= max(abs(cur), abs(internal_new), 1.0) * 1e-9
            except Exception:
                return False
        if st == DB.StorageType.ElementId:
            if not ns:
                return not param.HasValue
            try:
                nid = int(ns)
                return get_id_value(param.AsElementId()) == nid
            except Exception:
                return False
    except Exception:
        log_swallowed(_LOG, u'param_edit_is_unchanged')

    try:
        return unicode(param.AsValueString() or u'').strip() == ns
    except Exception:
        return unicode(param_value_display(param)).strip() == ns


def set_param_from_string(param, txt):
    if param is None or param.IsReadOnly:
        return False
    st = param.StorageType
    raw = (txt if txt is not None else u'') or u''
    txtu = unicode(raw)
    try:
        if st == DB.StorageType.String:
            param.Set(txtu)
            return True
        if st == DB.StorageType.Integer:
            if not txtu.strip():
                return False
            param.Set(int(txtu.strip()))
            return True
        if st == DB.StorageType.Double:
            if not txtu.strip():
                return False
            internal = user_double_to_internal(param, txtu)
            if internal is None:
                return False
            param.Set(internal)
            return True
        if st == DB.StorageType.ElementId:
            if not txtu.strip():
                return False
            param.Set(element_id_from_int(txtu.strip()))
            return True
    except Exception:
        return False
    return False


def apply_param_batch(doc, tuples, txn_name=u'NOSA — Parameter edit'):
    """tuples = [(Parameter, unicode value), …]."""
    ok = skipped = failed = 0
    try:
        with nosa_tx.guard(DB.Transaction(doc, txn_name)) as t:
            t.Start()
            for p, val in tuples:
                if val is None or p is None or p.IsReadOnly:
                    skipped += 1
                    continue
                if set_param_from_string(p, val):
                    ok += 1
                else:
                    failed += 1
            t.Commit()
    except Exception:
        raise
    return ok, failed, skipped


def preview_apply_strings(tuples, max_rows=12):
    """List of unicode lines for confirmation dialog."""
    lines = []
    n = len(tuples)
    cap = max_rows if max_rows > 0 else n
    for i in range(min(n, cap)):
        p, val = tuples[i]
        lbl = u'?'
        eid = u'?'
        try:
            el = getattr(p, 'Element', None)
            if el is not None:
                eid = unicode(get_id_value(el.Id))
                try:
                    nm = getattr(el, 'Name', None)
                    if nm is not None:
                        lbl = unicode(nm)
                except Exception:
                    lbl = unicode(type(el).__name__)
        except Exception:
            log_swallowed(_LOG, u'preview_apply_strings')
        try:
            pn = p.Definition.Name if p and p.Definition else u'?'
        except Exception:
            pn = u'?'
        try:
            cur = param_value_display(p)
        except Exception:
            cur = u''
        lines.append(u'{} | {} | {} : {} → {}'.format(eid, lbl, pn, cur, unicode(val)))
    if n > cap:
        lines.append(u'… (+{} more)'.format(n - cap))
    return lines


_param_value_display = param_value_display
