# -*- coding: utf-8 -*-
"""
Tag All (T7.4): what to tag in which view, and with which NOSA tag type. Pure, no Revit.

User brief 2026-10-03: every modelled element and the reinforcement, the categories recommended
per view, existing tags re-arranged too.
"""
from __future__ import absolute_import, division, print_function, unicode_literals

# key -> (label, BuiltInCategory name of the elements, how the tag sits: point | line | area | rebar)
CATEGORIES = (
    ('columns', u'Columns', 'OST_StructuralColumns', 'point'),
    ('piles', u'Piles', 'OST_StructuralColumns', 'point'),
    ('framing', u'Beams', 'OST_StructuralFraming', 'line'),
    ('walls', u'Walls', 'OST_Walls', 'line'),
    ('floors', u'Slabs', 'OST_Floors', 'area'),
    ('foundations', u'Foundations', 'OST_StructuralFoundation', 'point'),
    ('stair_landings', u'Stair landings', 'OST_StairsLandings', 'area'),
    ('rebar', u'Reinforcement', 'OST_Rebar', 'rebar'),
)
KEYS = tuple(c[0] for c in CATEGORIES)

PLAN_TYPES = ('FloorPlan', 'EngineeringPlan', 'AreaPlan')
SECTION_TYPES = ('Section', 'Detail', 'Elevation')

# preferred NOSA tag type names (substrings, first match wins) per category and context
TAG_PREFERENCES = {
    ('columns', 'steel'): (u'Steel - Type name / Comment',),
    ('columns', 'concrete'): (u'Type name / Comment / Mark', u'Mark'),
    ('piles', None): (u'Pile N', u'Mark'),
    ('framing', 'steel'): (u'Steel beam tag / comment', u'Mark'),
    ('framing', 'concrete'): (u'R.C Beam tag', u'Mark'),
    ('framing', 'section'): (u'Mark',),
    ('walls', None): (u'Type name / Comment', u'Comment'),
    ('floors', None): (u'Type / Comment', u'Type'),
    ('foundations', 'plan'): (u'Mark', u'Thickness'),
    ('foundations', 'slab'): (u'Thickness / Material / Comment', u'Mark'),
    ('stair_landings', None): (u'Standard',),
    ('rebar', 'plan'): (u'Full label - Dot', u'Full label'),
    ('rebar', 'section'): (u'Mark only - Dot', u'Mark only'),
}


def view_kind(view_type):
    """'plan' | 'section' | None (3D, sheets, schedules, legends, drafting: not tagged)."""
    name = u'{}'.format(view_type).split(u'.')[-1]
    if name in PLAN_TYPES:
        return 'plan'
    if name in SECTION_TYPES:
        return 'section'
    return None


def recommend(view_type, template_name=u'', view_name=u'', rebar_visible=False):
    """Category keys worth tagging in a view: what that kind of drawing normally carries."""
    kind = view_kind(view_type)
    if kind is None:
        return []
    text = u'{} {}'.format(template_name or u'', view_name or u'').lower()
    keys = ['columns', 'framing', 'walls', 'floors', 'foundations']
    if kind == 'plan':
        keys.append('stair_landings')
        if u'pil' in text or u'found' in text or u'substructure' in text:
            keys.append('piles')
    if rebar_visible and (kind == 'section' or u'rc' in text.split() or u'rc ' in text or u'rebar' in text):
        keys.append('rebar')
    return [k for k in KEYS if k in keys]


def tag_preference(key, context=None):
    """Name fragments to look for, most wanted first."""
    return TAG_PREFERENCES.get((key, context)) or TAG_PREFERENCES.get((key, None)) or ()


def pick_tag_type(names, key, context=None):
    """Index into `names` of the preferred tag type for a category in a context, else 0."""
    for wanted in tag_preference(key, context):
        for i, name in enumerate(names):
            if wanted.lower() in (name or u'').lower():
                return i
    return 0


def is_pile(family_name):
    return u'pile' in (family_name or u'').lower()
