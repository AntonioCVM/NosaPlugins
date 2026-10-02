# -*- coding: utf-8 -*-
"""Bulk Parameter Editor — one parameter across filtered instances."""
import sys, os
from Autodesk.Revit import DB
from nosa_utils.telemetry import log_swallowed
_LOG = u'parameterhub'
_lib = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', 'lib'))
if _lib not in sys.path:
    sys.path.insert(0, _lib)

from nosa_utils.revit_helpers import get_id_value, element_name
from nosa_utils.worksharing_quick import element_workset_is_open
from nosa_utils import param_element_ops as pe
from nosa_utils.compat import ensure_text


_ELEM_CAP = 15000


def bic_from_name(name):
    return getattr(DB.BuiltInCategory, name, None)


def _fam_type_label(el):
    try:
        if isinstance(el, DB.FamilyInstance):
            sym = el.Symbol
            if sym:
                fn = ''
                try:
                    if hasattr(sym.Family, 'Name'):
                        fn = sym.Family.Name or u''
                except Exception:
                    log_swallowed(_LOG, u'_fam_type_label')
                sn = ''
                try:
                    sp = sym.get_Parameter(DB.BuiltInParameter.SYMBOL_NAME_PARAM)
                    if sp:
                        sn = sp.AsString() or u''
                except Exception:
                    log_swallowed(_LOG, u'_fam_type_label')
                tn = element_name(sym)
                lbl = u'{} — {}'.format(fn, tn or sn) if fn else (tn or sn or u'')
                return lbl or fn
    except Exception:
        log_swallowed(_LOG, u'_fam_type_label')
    try:
        if el.Category:
            cn = ensure_text(el.Category.Name)
        else:
            cn = u''
        en = ensure_text(getattr(el, 'Name', None) or u'')
        return en or cn
    except Exception:
        return u''


def _display_name(el):
    try:
        if isinstance(el, DB.FamilyInstance) and el.Symbol:
            return ensure_text(element_name(el.Symbol))
    except Exception:
        log_swallowed(_LOG, u'_display_name')
    try:
        return ensure_text(getattr(el, 'Name', None) or u'')
    except Exception:
        return u''


def gather_instances(doc, bic_name, family_subs, type_subs,
                     uidoc=None, restrict_selection=False,
                     exclude_non_modifiable=False,
                     only_open_worksets=False):
    """
    Instances of category bic_name after optional substring filters.

    Args:
      restrict_selection — intersect with current Revit selection (needs uidoc).
      exclude_non_modifiable — skips !IsModifiable (worksets / borrowing).
      only_open_worksets — skips elements assigned to closed worksets.
    """
    bic = bic_from_name(bic_name)
    if bic is None:
        return [], u'Unknown category {}'.format(bic_name)
    fam_f = (family_subs or u'').strip().lower()
    typ_f = (type_subs or u'').strip().lower()

    sel_ids = None
    if restrict_selection:
        if uidoc is None:
            return [], u'Needs active UIDocument for «current selection» filter.'
        try:
            s = uidoc.Selection.GetElementIds()
            sel_ids = set(get_id_value(x) for x in s)
        except Exception:
            sel_ids = set()
        if not sel_ids:
            return [], u'Nothing selected — pick instances in Revit first.'

    elems = []
    for el in (DB.FilteredElementCollector(doc)
               .OfCategory(bic).WhereElementIsNotElementType().ToElements()):
        try:
            if sel_ids is not None:
                try:
                    if get_id_value(el.Id) not in sel_ids:
                        continue
                except Exception:
                    continue
            if exclude_non_modifiable and not el.IsModifiable:
                continue
            if only_open_worksets and not element_workset_is_open(doc, el):
                continue
            if fam_f or typ_f:
                lbl = (_fam_type_label(el) or u'').lower()
                tn = (_display_name(el) or u'').lower()
                if fam_f and fam_f not in lbl:
                    continue
                if typ_f and typ_f not in tn and typ_f not in lbl:
                    continue
        except Exception:
            log_swallowed(_LOG, u'gather_instances')
        elems.append(el)
        if len(elems) >= _ELEM_CAP:
            break

    hint = ''
    if len(elems) >= _ELEM_CAP:
        hint = (
            u'(First {:,} instances — refine filters or raise cap if needed)'
            ).format(len(elems))
    return elems, hint


_param_value_display = pe.param_value_display
discover_param_names = pe.discover_param_names
discover_param_specs = pe.discover_param_specs
preview_apply_strings = pe.preview_apply_strings
param_edit_is_unchanged = pe.param_edit_is_unchanged
lookup_param_named = pe.lookup_param_named
set_param_from_string = pe.set_param_from_string


def apply_batch(doc, tuples):
    return pe.apply_param_batch(doc, tuples, u'NOSA — Bulk Parameter Edit')
