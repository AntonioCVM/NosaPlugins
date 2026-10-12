# -*- coding: utf-8 -*-
"""
nosa_utils.rule_flags — the bars RebarAutomate adds by a detailing rule rather than from the design (T9.15, user
decision 2026-10-11: generate, but flag them "detailing rule applied — confirm with design"): the rule of each bar
layer the generators write, for NOSA_Rebar_Rule, the QA and the rule-added bars schedule. Design layers have none.
"""
from __future__ import absolute_import, division, print_function, unicode_literals

PARAM = u'NOSA_Rebar_Rule'
CONFIRM = u'detailing rule applied - confirm with design'

RULES = {
    u'end_ubar': u'U-bars at a free edge (SMDSC 4th ed. MD S3 / MD W1)',
    u'corner_ubar': u'U-bars at a free corner (SMDSC 4th ed. MD S3)',
    u'top_ubar': u'U-bars at a free top edge (SMDSC 4th ed. MD W1)',
    u'closure_x': u'U-bars closing a base edge (SMDSC 4th ed. MD PF1)',
    u'closure_y': u'U-bars closing a base edge (SMDSC 4th ed. MD PF1)',
    u'opening_ubar': u'U-bars round an opening (SMDSC 4th ed. MD W4)',
    u'trimmer': u'Trimmer bars round an opening (SMDSC 4th ed. MD OP1 / MD W4)',
    u'trimmer_top': u'Trimmer bars round an opening (SMDSC 4th ed. MD OP1)',
    u'trimmer_bottom': u'Trimmer bars round an opening (SMDSC 4th ed. MD OP1)',
    u'diagonal_top': u'Diagonal bars at an opening corner (SMDSC 4th ed. MD OP1)',
    u'diagonal_bottom': u'Diagonal bars at an opening corner (SMDSC 4th ed. MD OP1)',
    u'side': u'Side / lacer bars against cracking (SMDSC 4th ed. MD B1 / MD PC1)',
    u'spacer': u'Spacer bars between layers (SMDSC 4th ed. MD B1)',
    u'crosstie': u'Cross-ties restraining column bars (EC2 9.5.3(6))',
    u'interior_stirrup': u'Interior links restraining column bars (EC2 9.5.3(6))',
    u'starter_link': u'Links round the starter bars (SMDSC 4th ed. MD C1)',
    u'stair_landing_ubar': u'U-bars at the landing edge (SMDSC 4th ed. MD ST1)',
}


def rule_for(layer):
    """The detailing rule behind a bar layer; '' for a design bar."""
    return RULES.get((layer or u'').strip().lower(), u'')


def flag_text(layer):
    """The QA's and the schedule's text for a rule-added bar; '' for a design bar."""
    rule = rule_for(layer)
    return u'{} - {}'.format(rule, CONFIRM) if rule else u''


def stamp(rebars):
    """Write NOSA_Rebar_Rule from each bar's NOSA_Rebar_Layer (in a transaction). Returns how many changed."""
    n = 0
    for r in rebars:
        lp, rp = r.LookupParameter(u'NOSA_Rebar_Layer'), r.LookupParameter(PARAM)
        if rp is None or rp.IsReadOnly:
            continue
        text = flag_text(lp.AsString() if lp is not None else u'')
        if (rp.AsString() or u'') != text:
            rp.Set(text)
            n += 1
    return n
