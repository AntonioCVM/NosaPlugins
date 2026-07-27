# -*- coding: utf-8 -*-
"""Parameter Inspector Logic — collect and edit element parameters."""
import sys, os
from Autodesk.Revit import DB
_lib = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', 'lib'))
if _lib not in sys.path:
    sys.path.insert(0, _lib)
from nosa_utils.revit_helpers import get_id_value


_STORAGE_LABELS = {
    DB.StorageType.String:    'Text',
    DB.StorageType.Integer:   'Integer',
    DB.StorageType.Double:    'Double',
    DB.StorageType.ElementId: 'ElementId',
}
# StorageType.None is a reserved word in Python 2 — use getattr to access it
_none_st = getattr(DB.StorageType, 'None', None)
if _none_st is not None:
    _STORAGE_LABELS[_none_st] = u'—'


def _is_builtin(param):
    """True if param is a built-in Revit parameter (not user-created)."""
    try:
        bip = param.Definition.BuiltInParameter
        return bip != DB.BuiltInParameter.INVALID
    except Exception:
        pass
    try:
        return isinstance(param.Definition, DB.InternalDefinition)
    except Exception:
        return not param.IsShared


def _param_value_str(param):
    """Return a human-readable string for a parameter's current value."""
    if param is None or not param.HasValue:
        return ''
    st = param.StorageType
    try:
        if st == DB.StorageType.String:
            return param.AsString() or ''
        if st == DB.StorageType.Integer:
            return str(param.AsInteger())
        if st == DB.StorageType.Double:
            return '{:.4f}'.format(param.AsDouble())
        if st == DB.StorageType.ElementId:
            eid = param.AsElementId()
            return str(get_id_value(eid))
    except Exception:
        pass
    return param.AsValueString() or ''


def collect_params(doc, elements):
    """
    Collect parameters for a list of elements.

    Returns:
        list of dicts:
          {
            'name': str,
            'group': str,           # param group display name
            'storage': str,         # 'Text' | 'Integer' | 'Double' | 'ElementId'
            'builtin': bool,
            'shared': bool,
            'readonly': bool,
            'values': [str, ...],   # one per element
            'consistent': bool,     # all values identical
            'params': [Param, ...], # raw param objects for editing
          }
    """
    if not elements:
        return []

    # Build a union of all parameter names across elements
    param_map = {}  # name -> {'group', 'storage', 'builtin', 'shared', 'readonly', 'by_elem_idx': []}

    for elem_idx, el in enumerate(elements):
        try:
            for param in el.Parameters:
                try:
                    name = param.Definition.Name
                    if name not in param_map:
                        try:
                            group_label = str(param.Definition.ParameterGroup).split('.')[-1]
                        except Exception:
                            group_label = ''
                        param_map[name] = {
                            'group':    group_label,
                            'storage':  _STORAGE_LABELS.get(param.StorageType, '?'),
                            'builtin':  _is_builtin(param),
                            'shared':   param.IsShared,
                            'readonly': param.IsReadOnly,
                            'by_elem':  [None] * len(elements),
                        }
                    param_map[name]['by_elem'][elem_idx] = param
                except Exception:
                    pass
        except Exception:
            pass

    rows = []
    for name, info in sorted(param_map.items(), key=lambda x: (x[1]['group'], x[0])):
        values = [_param_value_str(p) for p in info['by_elem']]
        consistent = len(set(v for v in values if v is not None)) <= 1
        rows.append({
            'name':       name,
            'group':      info['group'],
            'storage':    info['storage'],
            'builtin':    info['builtin'],
            'shared':     info['shared'],
            'readonly':   info['readonly'],
            'values':     values,
            'consistent': consistent,
            'params':     info['by_elem'],
        })
    return rows


def set_param_value(doc, params, new_value_str):
    """
    Set the same string value to all writable params in the list.

    Returns (success_count, fail_count).
    """
    ok = fail = 0
    with DB.Transaction(doc, u"NOSA — Parameter Inspector — Bulk Edit") as t:
        t.Start()
        for param in params:
            if param is None or param.IsReadOnly:
                continue
            try:
                st = param.StorageType
                if st == DB.StorageType.String:
                    param.Set(new_value_str)
                elif st == DB.StorageType.Integer:
                    param.Set(int(new_value_str))
                elif st == DB.StorageType.Double:
                    param.Set(float(new_value_str))
                elif st == DB.StorageType.ElementId:
                    param.Set(DB.ElementId(int(new_value_str)))
                ok += 1
            except Exception:
                fail += 1
        t.Commit()
    return ok, fail


def copy_params_from_source(doc, source_elem, target_elems):
    """
    Copy all writable parameter values from source_elem to each target element
    where the parameter exists and is writable.
    Returns (copied, skipped).
    """
    copied = skipped = 0
    with DB.Transaction(doc, u"NOSA — Parameter Inspector — Copy From Source") as t:
        t.Start()
        for param in source_elem.Parameters:
            try:
                if param.IsReadOnly or not param.HasValue:
                    continue
                name = param.Definition.Name
                st   = param.StorageType
                for target in target_elems:
                    if target.Id == source_elem.Id:
                        continue
                    tp = target.LookupParameter(name)
                    if tp is None or tp.IsReadOnly or tp.StorageType != st:
                        skipped += 1
                        continue
                    try:
                        if st == DB.StorageType.String:
                            tp.Set(param.AsString() or '')
                        elif st == DB.StorageType.Integer:
                            tp.Set(param.AsInteger())
                        elif st == DB.StorageType.Double:
                            tp.Set(param.AsDouble())
                        elif st == DB.StorageType.ElementId:
                            tp.Set(param.AsElementId())
                        copied += 1
                    except Exception:
                        skipped += 1
            except Exception:
                pass
        t.Commit()
    return copied, skipped
