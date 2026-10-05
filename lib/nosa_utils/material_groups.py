# -*- coding: utf-8 -*-
"""
NOSA_Material_Group: which schedules a material belongs to. Concrete schedules take every material that is
NOT in a non-concrete group (so blank and <By Category> show up and reveal what still needs a material);
Steelwork weight takes "Structural steel". Values are British English.
"""
from __future__ import absolute_import, division, print_function, unicode_literals
import os
import re

PARAM = u'NOSA_Material_Group'
CONCRETE = u'Concrete'
STEEL = u'Structural steel'
NON_CONCRETE = (STEEL, u'Reinforcement', u'Piling', u'Timber', u'Masonry', u'Other')
GROUPS = (CONCRETE,) + NON_CONCRETE

_RULES = [
    (u'Reinforcement', r'rebar|reinforc'),
    (u'Piling', r'piling|\bpile'),
    (u'Other', r'screed|blinding'),            # lean mix under slabs: not counted as concrete (user 2026-10-05)
    (STEEL, r'structural steel|^metal - steel|^steel\b|\bs(235|275|355|420|450|460)\b|lgsf|light gauge'),
    (u'Timber', r'timber|wood|glulam|clt\b|plywood|osb\b'),
    (u'Masonry', r'block|brick|masonry|mortar|stone'),
    (CONCRETE, r'concrete'),
]


def classify(name, material_class=u''):
    """Group of a material from its name and Revit material class (pure)."""
    low = (name or u'').lower()
    for group, pattern in _RULES:
        if re.search(pattern, low):
            return group
    if (material_class or u'').lower() == u'concrete':
        return CONCRETE
    return u'Other'


def params_file():
    return os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'data', 'shared_parameters',
                                        'NOSA_Materials.txt'))


def bind(doc):
    """Bind NOSA_Material_Group to Materials (idempotent). Returns the binding report."""
    from nosa_utils import shared_params
    return shared_params.ensure_bound(doc, ['OST_Materials'], params_file())


def assign(doc, overwrite=False):
    """Fill NOSA_Material_Group on every material (only blanks unless overwrite). Call in a transaction.
    Returns {group: [material names]} of what was written."""
    from Autodesk.Revit import DB
    from nosa_utils.revit_helpers import element_name
    out = {}
    for m in DB.FilteredElementCollector(doc).OfClass(DB.Material):
        p = m.LookupParameter(PARAM)
        if p is None or p.IsReadOnly:
            continue
        if p.AsString() and not overwrite:
            continue
        group = classify(element_name(m), m.MaterialClass)
        p.Set(group)
        out.setdefault(group, []).append(element_name(m))
    return out
