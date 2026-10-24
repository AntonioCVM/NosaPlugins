# -*- coding: utf-8 -*-
"""T12.8: the review shown after every drawing run - the model's warnings grouped and the drawings' audit."""
from __future__ import absolute_import, division, print_function, unicode_literals

import re

_PER_DRAWING = re.compile(r'^(\d{4})(?: ([A-Z][A-Za-z]+))?: (.+)$')

AUDIT_LABELS = {
    u'A1': u'calling-ups out of line',
    u'A2': u'texts over each other',
    u'A3': u'annotations over the drawing',
    u'A4': u'lines crossing',
    u'A5': u'leaders',
    u'A6': u'texts off the frame',
    u'A7': u'views off the sheet',
    u'A8': u'calling-ups not naming the mark of their bar',
    u'A4i': u'leaders across an indicator line spanning the whole member (unavoidable, for information)',
}


_RANGE = r'((?:\([a-z]+ to [a-z]+\))?)'
_CALLED_MARK = re.compile(r'H\d+-E?(\d+)' + _RANGE)
_MARK_ONLY = re.compile(r'^E?(\d+)' + _RANGE + r'$')


def callout_mismatch(text, mark, suffix=u''):
    """
    A8 (2026-10-24 audit): the mark a label prints ('6H16-06(a to f) B2', '01') against the bar's own mark and
    varying-set range; a text written before the marks changed names another bar. '' when it agrees (or names
    no mark), else what it prints.
    """
    text = (text or u'').strip()
    hit = _CALLED_MARK.search(text)
    if hit is None:
        hit, suffix = _MARK_ONLY.match(text), u''       # a mark alone (sections) gives no range
    if not hit or not mark:
        return u''
    printed = hit.group(1) + hit.group(2)
    return u'' if (hit.group(1) == mark and (not suffix or hit.group(2) == suffix)) else printed


def group_messages(messages):
    """
    The same warning on several drawings as one line naming them: '4501 Columns: X' and '4502 Slabs: X' read
    'X (4501 Columns, 4502 Slabs)'. Other messages are kept as they are, in their order.
    """
    groups, order = {}, []
    for m in messages:
        hit = _PER_DRAWING.match(m or u'')
        key = hit.group(3) if hit else m
        where = u' '.join(t for t in (hit.group(1), hit.group(2)) if t) if hit else u''
        if key not in groups:
            groups[key] = []
            order.append(key)
        if where and where not in groups[key]:
            groups[key].append(where)
    return [u'{} ({})'.format(k, u', '.join(groups[k])) if groups[k] else k for k in order]


def summary(messages, issues, limit=12):
    """
    The text of the review: the grouped model warnings, then the audit's incidents counted by kind with the
    first of each. issues [{'sheet', 'view', 'category', 'element', 'problem'}]. Returns (text, count).
    """
    lines = []
    grouped = group_messages(messages)
    if grouped:
        lines.append(u'Model and notes ({}):'.format(len(grouped)))
        lines.extend(u'  - ' + g for g in grouped[:limit])
        if len(grouped) > limit:
            lines.append(u'  ... and {} more'.format(len(grouped) - limit))
    by_cat = {}
    for i in issues:
        by_cat.setdefault(i.get('category') or u'?', []).append(i)
    # informative kinds (A4i) are listed but not counted as incidents
    real = [i for i in issues if not (i.get('category') or u'').endswith(u'i')]
    if by_cat:
        lines.append(u'Drawing review ({} incident(s)):'.format(len(real)))
        for cat in sorted(by_cat):
            first = by_cat[cat][0]
            lines.append(u'  - {} {}: {} - e.g. {} {}: {}'.format(
                cat, AUDIT_LABELS.get(cat, u''), len(by_cat[cat]), first.get('sheet', u''), first.get('view', u''),
                first.get('problem', u'')))
    else:
        lines.append(u'Drawing review: no incidents.')
    return u'\n'.join(lines), len(grouped) + len(real)
