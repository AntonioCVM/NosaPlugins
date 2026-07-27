# -*- coding: utf-8 -*-
"""Structural / host type browser — edit one type-parameter column across ElementTypes."""

import sys
import os

from Autodesk.Revit import DB
# lib = NOSA.extension/lib (StructuralType…/lib is 5 levels below extension root)
_lib = os.path.abspath(
    os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', '..', 'lib'))
if _lib not in sys.path:
    sys.path.insert(0, _lib)

from nosa_utils.revit_helpers import get_id_value
from nosa_utils.worksharing_quick import element_workset_is_open

try:
    unicode
except NameError:
    unicode = str  # CPython 3 compat
from nosa_utils import param_element_ops as pe

_TYPE_CAP = 8000


def bic_from_name(name):
    return getattr(DB.BuiltInCategory, name, None)


def type_family_type_label(el_type):
    """Family symbol or system type readable label."""
    try:
        if isinstance(el_type, DB.FamilySymbol):
            fn = u''
            try:
                if el_type.Family and getattr(el_type.Family, 'Name', None):
                    fn = unicode(el_type.Family.Name)
            except Exception:
                pass
            tn = u''
            try:
                tn = unicode(el_type.Name) if getattr(el_type, 'Name', None) else u''
            except Exception:
                tn = u''
            if fn and tn:
                return u'{} — {}'.format(fn, tn)
            return tn or fn
    except Exception:
        pass
    try:
        fn = getattr(el_type, 'FamilyName', None)
        nm = getattr(el_type, 'Name', None)
        fu = unicode(fn).strip() if fn else u''
        nu = unicode(nm).strip() if nm else u''
        if fu and nu:
            return u'{} — {}'.format(fu, nu)
        return nu or fu
    except Exception:
        pass
    try:
        return unicode(el_type.Name)
    except Exception:
        try:
            return unicode(get_id_value(el_type.Id))
        except Exception:
            return u''


def _selected_type_ids(doc, uidoc):
    ids = set()
    try:
        for rid in uidoc.Selection.GetElementIds():
            el = doc.GetElement(rid)
            if el is None:
                continue
            if isinstance(el, DB.ElementType):
                ids.add(get_id_value(el.Id))
                continue
            try:
                if isinstance(el, DB.FamilyInstance) and el.Symbol:
                    ids.add(get_id_value(el.Symbol.Id))
            except Exception:
                pass
    except Exception:
        pass
    return ids


def gather_element_types(doc, bic_name, family_subs, type_subs,
                         uidoc=None, restrict_selection=False,
                         exclude_non_modifiable=False,
                         only_open_worksets=False):
    """
    Structural / host ElementTypes for bic_name.

    restrict_selection intersects collector with types inferred from Revit selection
    (FamilyInstance.Symbol or selected ElementTypes).
    """
    bic = bic_from_name(bic_name)
    if bic is None:
        return [], u'Unknown category {}'.format(bic_name)
    fam_f = (family_subs or u'').strip().lower()
    typ_f = (type_subs or u'').strip().lower()

    sel_ids = None
    if restrict_selection:
        if uidoc is None:
            return [], u'Needs active UIDocument for selection intersection.'
        sel_ids = _selected_type_ids(doc, uidoc)
        if not sel_ids:
            return [], u'Select instances or types in Revit — no types resolved.'

    types_list = []
    try:
        col = (
            DB.FilteredElementCollector(doc)
            .OfCategory(bic)
            .WhereElementIsElementType())
        for et in col:
            try:
                if sel_ids is not None and get_id_value(et.Id) not in sel_ids:
                    continue
                if exclude_non_modifiable and not et.IsModifiable:
                    continue
                if only_open_worksets and not element_workset_is_open(doc, et):
                    continue
                lbl = type_family_type_label(et).lower()
                if fam_f and fam_f not in lbl:
                    continue
                if typ_f and typ_f not in lbl:
                    continue
            except Exception:
                pass
            types_list.append(et)
            if len(types_list) >= _TYPE_CAP:
                break
    except Exception:
        pass

    hint = u''
    if len(types_list) >= _TYPE_CAP:
        hint = u'(Showing first {:,} types refine filters.)'.format(len(types_list))
    return types_list, hint


def duplicate_type(doc, el_type, new_name):
    """
    Duplicate ElementType/FamilySymbol. Returns (new_element, error_message_unicode).
    """
    if el_type is None:
        return None, u'No type.'
    nn = new_name.strip() if isinstance(new_name, unicode) else unicode(str(new_name or u'')).strip()
    if not nn:
        return None, u'Empty name.'
    try:
        with DB.Transaction(doc, u'NOSA — Duplicate type') as tx:
            tx.Start()
            dup = el_type.Duplicate(nn)
            tx.Commit()
        return dup, None
    except Exception as ex:
        return None, unicode(ex)


def apply_batch(doc, tuples):
    return pe.apply_param_batch(doc, tuples, u'NOSA — Structural Type Manager')


# Thin aliases for scripts / inspectors
lookup_param_named = pe.lookup_param_named
discover_param_names = pe.discover_param_names
discover_param_specs = pe.discover_param_specs
_param_value_display = pe.param_value_display
set_param_from_string = pe.set_param_from_string
preview_apply_strings = pe.preview_apply_strings
param_edit_is_unchanged = pe.param_edit_is_unchanged