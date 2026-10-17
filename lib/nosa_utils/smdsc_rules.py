# -*- coding: utf-8 -*-
"""
nosa_utils.smdsc_rules — the register of the detailing rules in nosa_utils against the IStructE SMDSC 4th edition
(2021) (T9.22): each constant with the edition and clause it follows and what changed from the 3rd edition (2006).
tests/test_smdsc_rules.py keeps every value here equal to the constant the code uses.
"""
from __future__ import absolute_import, division, print_function, unicode_literals

EDITION = u'SMDSC 4th ed. (2021)'

# (module, constant, value, clause in the 4th edition, change from the 3rd edition or '')
REGISTER = (
    # slabs
    (u'mesh_rules', u'TOP_BAR_SPAN_SHARE', 0.3, u'MD S1', u'measured from the support face, or l_bd if greater'),
    (u'mesh_rules', u'MD_S1_ALL_SHARE', 0.15, u'MD S1', u'new: every top bar 0.15 l (or l_bd) past the face'),
    (u'mesh_rules', u'BOTTOM_BAR_SPAN_SHARE', 0.8, u'MD S1', u''),
    (u'mesh_rules', u'EDGE_UBAR_SHARE', 0.5, u'MD S2 / MD S3', u''),
    (u'mesh_rules', u'TORSION_SHARE', 0.75, u'6.2.2.11, Fig. 6.7', u'figure renumbered (was Fig. 6.9)'),
    (u'mesh_rules', u'TORSION_REACH', 0.2, u'6.2.2.11, Fig. 6.7', u'figure renumbered (was Fig. 6.9)'),
    (u'mesh_rules', u'TRIMMER_ANCHOR_PHI', 45.0, u'6.2.2.12',
     u'4th ed. asks for 450 min. (nominal anchorage) past the hole: 45 dia. meets it from H10'),
    (u'mesh_rules', u'FLAT_SLAB_POSITIVE', 0.55, u'6.2.2.9, MD S5', u'table cited as Table 6.2 in the text'),
    (u'mesh_rules', u'TRIMMER_CLEAR_MM', 25.0, u'5.2.5', u''),
    # beams
    (u'links', u'SIDE_BARS_DEPTH_MM', 750.0, u'MD B1 side bar table', u'side bars from 750 deep (was 1000, H16-250)'),
    (u'links', u'MD_B1_EXTRA_EVERY_MM', 300.0, u'MD B1 side bar table', u'new table'),
    (u'links', u'HANGER_SHARE', 0.2, u'6.3.2.9', u''),
    (u'links', u'HANGER_DIA_MM', 16.0, u'6.3.2.9', u''),
    (u'links', u'MAX_PITCH_MM', 300.0, u'MD B1', u''),
    (u'links', u'MAX_BAR_TO_LEG_MM', 150.0, u'6.3.2', u''),
    (u'links', u'MAX_LATERAL_LEG_MM', 600.0, u'6.3.2', u''),
    (u'rebar_qa', u'VIBRATOR_GAP_MM', 75.0, u'MD B1 / 6.3.2.2, Table 6.4', u'Table 6.4 now gives the pitch'),
    # columns
    (u'links', u'COLUMN_REDUCTION', 0.6, u'6.4.2 (EC2 9.5.3(4))', u''),
    (u'links', u'STARTER_LINK_DIA_MM', 10.0, u'MD C1 / MD F1', u'model details renamed (were MC1 / MF1)'),
    (u'links', u'STARTER_LINK_MIN_COUNT', 3, u'MD C1 / MD F1', u''),
    (u'standards', u'FOUNDATION_LEVEL_TOLERANCE_MM', 150.0, u'MD F1 / 6.7.3', u''),
    # walls
    (u'wall_rules', u'KICKER_MM', 75.0, u'6.7.3 (kicker 75 above ground)', u''),
    (u'wall_rules', u'KICKER_BELOW_GROUND_MM', 150.0, u'6.7.3 / MD W1', u''),
    (u'wall_rules', u'MIN_THICKNESS_MM', 150.0, u'6.5.2', u'175 min. where an opening is trimmed (6.5.2)'),
    (u'wall_rules', u'MAX_PITCH_MM', 400.0, u'6.5.2', u''),
    # foundations
    (u'mesh_rules', u'BAND_FACTOR', 1.5, u'3rd ed. 6.7 (not restated in the 4th ed.)', u'kept from the 3rd ed.'),
    (u'pile_caps', u'NOMINAL_DIA_MM', 16.0, u'Table 6.7', u'table renumbered (was Table 6.10)'),
    (u'mesh_rules', u'PILED_BOTTOM_COVER_MM', 100.0, u'6.7.3, MD PC1', u''),
    (u'mesh_rules', u'FOUNDATION_COVER_MM', 75.0, u'6.7.3', u''),
    # general
    (u'rebar_qa', u'REAL_DIA', 1.10, u'5.1.6, Table 5.3', u'table renumbered (was Table 5.2)'),
    (u'rebar_qa', u'MAX_LAYERS', 2, u'4.2.1', u''),
    (u'rebar_qa', u'STOCK_MM', 12000.0, u'Table 5.5', u''),
)


def by_constant():
    return dict(((m, c), (v, clause, change)) for m, c, v, clause, change in REGISTER)


def citation(module, constant):
    """'SMDSC 4th ed. MD S1' for a registered constant; '' when it is not registered."""
    entry = by_constant().get((module, constant))
    if entry is None:
        return u''
    clause = entry[1]
    return clause if clause.startswith(u'3rd ed.') else u'SMDSC 4th ed. {}'.format(clause)


def changes():
    """The rules that changed from the 3rd to the 4th edition: [(module.constant, clause, change)]."""
    return [(u'{}.{}'.format(m, c), clause, change) for m, c, _v, clause, change in REGISTER if change]
