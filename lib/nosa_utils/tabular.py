# -*- coding: utf-8 -*-
"""
nosa_utils.tabular — the tabular (representative) method (T8.54, IStructE SMDSC 4.1.1, 6.4.4, 6.7.4), no Revit:
the calling-up of a member's bars written once per type of member, the members alike grouped with their
references listed together ('A1, A3, A5'), as in the column and base schedules of the SMDSC.
"""
from __future__ import absolute_import, division, print_function, unicode_literals

import re


def bar_text(count, dia_mm, mark, spacing_mm=None):
    """One calling-up: '8H25-03', or with the pitch of links and distributed bars '14H8-07-200'."""
    text = u'{}H{:.0f}-{}'.format(int(count), dia_mm, mark or u'??')
    return u'{}-{:.0f}'.format(text, spacing_mm) if spacing_mm else text


def summarise(sets):
    """
    The bars of one role of a member (e.g. its main bars), sets [(count, dia, mark, spacing or None)]: the sets of
    one mark, size and pitch added up, then joined with ' + ' in mark order.
    """
    total = {}
    for count, dia, mark, spacing in sets:
        key = (mark or u'', round(dia), round(spacing) if spacing else None)
        total[key] = total.get(key, 0) + count
    parts = [bar_text(n, dia, mark, spacing) for (mark, dia, spacing), n in sorted(total.items(), key=lambda kv: (
        natural_key(kv[0][0]), kv[0][1], kv[0][2] or 0))]
    return u' + '.join(parts)


def natural_key(text):
    return [int(t) if t.isdigit() else t.lower() for t in re.split(u'(\\d+)', text or u'')]


def groups(members):
    """
    members [(reference, signature)] -> [(signature, [references])] for the members alike (same signature),
    references in natural order, groups in the order of their first reference.
    """
    out = {}
    for ref, signature in members:
        out.setdefault(signature, []).append(ref)
    rows = [(sig, sorted(refs, key=natural_key)) for sig, refs in out.items()]
    return sorted(rows, key=lambda r: natural_key(r[1][0]))


def references_text(refs):
    """'A1, A3, A5' (SMDSC Table 6.x 'Column reference')."""
    return u', '.join(refs)
