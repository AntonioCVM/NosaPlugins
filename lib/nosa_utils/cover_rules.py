# -*- coding: utf-8 -*-
"""
T12.5 (user 2026-10-18): covers at the junction of members with different covers. The higher-ranked member
governs: foundation > wall > column > beam > slab.
"""
from __future__ import absolute_import, division, print_function, unicode_literals

RANK = {'foundation': 5, 'wall': 4, 'column': 3, 'beam': 2, 'slab': 1}

_CATEGORY_KINDS = (('OST_StructuralFoundation', 'foundation'), ('OST_Walls', 'wall'),
                   ('OST_StructuralColumns', 'column'), ('OST_StructuralFraming', 'beam'), ('OST_Floors', 'slab'))


def rank(kind):
    """A member kind's rank in the cover hierarchy; 0 for one it does not know."""
    return RANK.get(kind or u'', 0)


def governing_cover(own_kind, own_cover_mm, other_kind, other_cover_mm):
    """
    The cover a bar of an own_kind member keeps where it runs into an other_kind member: the other's when it ranks
    higher (a beam's bars into a column keep the column's cover), its own otherwise.
    """
    if other_cover_mm is not None and rank(other_kind) > rank(own_kind):
        return other_cover_mm
    return own_cover_mm


def kind_of(element):
    """'column', 'beam', ... of a Revit element by its category; None for another."""
    from Autodesk.Revit import DB  # Lazy import
    from nosa_utils.revit_compat import get_id_value
    cat = getattr(element, 'Category', None)
    if cat is None:
        return None
    for name, kind in _CATEGORY_KINDS:
        if get_id_value(cat.Id) == int(getattr(DB.BuiltInCategory, name)):
            return kind
    return None
