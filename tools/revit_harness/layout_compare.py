# -*- coding: utf-8 -*-
"""
CPython: two runs' layout_snapshot.json (and their review issues, BBS CSVs) compared - 'identical' only when every
sheet's viewports, every view's tags, notes, lines, dimensions, regions and bars' shown positions match exactly, the
drawing review lists the same issues and the BBS rows are the same. Usage: python layout_compare.py <run A folder>
<run B folder> [<log A> <log B>]. Exit 0 when identical.
"""
import csv
import glob
import io
import json
import os
import re
import sys


def load(folder):
    with io.open(os.path.join(folder, 'layout_snapshot.json'), encoding='utf-8') as fh:
        return json.load(fh)


def issues(log):
    if not log or not os.path.exists(log):
        return None
    out = []
    for line in io.open(log, encoding='utf-8'):
        if line.startswith(u'ISSUE '):
            # annotation ids differ between runs: compare category, sheet, view and the problem without ids
            parts = [p.strip() for p in line.split(u'|')]
            out.append(u' | '.join([parts[0], parts[1], re.sub(r'\d{5,}', u'#', parts[-1])]))
    return sorted(out)


def bbs(folder):
    rows = []
    for path in sorted(glob.glob(os.path.join(folder, 'BBS*.csv'))):
        with io.open(path, encoding='utf-8-sig') as fh:
            rows.extend([os.path.basename(path)] + r for r in csv.reader(fh))
    return rows


def main(a, b, log_a=None, log_b=None):
    sa, sb = load(a), load(b)
    diffs = []
    for key in sorted(set(sa['sheets']) | set(sb['sheets'])):
        if sa['sheets'].get(key) != sb['sheets'].get(key):
            diffs.append(u'sheet {}: viewports differ'.format(key))
    for key in sorted(set(sa['views']) | set(sb['views'])):
        va, vb = sa['views'].get(key), sb['views'].get(key)
        if va is None or vb is None:
            diffs.append(u'view {}: only in {}'.format(key, 'A' if vb is None else 'B'))
            continue
        for kind in sorted(set(va) | set(vb)):
            la, lb = va.get(kind, []), vb.get(kind, [])
            if la != lb:
                only_a = [x for x in la if x not in lb]
                only_b = [x for x in lb if x not in la]
                diffs.append(u'view {} {}: {} vs {} ({} only in A, {} only in B){}'.format(
                    key, kind, len(la), len(lb), len(only_a), len(only_b),
                    u'\n      A: {}\n      B: {}'.format(json.dumps(only_a[:2])[:300], json.dumps(only_b[:2])[:300])))
    ia, ib = issues(log_a), issues(log_b)
    if ia is not None and ib is not None and ia != ib:
        diffs.append(u'review issues differ: {} vs {} ({} only in A, {} only in B)'.format(
            len(ia), len(ib), len([x for x in ia if x not in ib]), len([x for x in ib if x not in ia])))
    if bbs(a) != bbs(b):
        diffs.append(u'BBS rows differ')
    n_views = len(set(sa['views']) | set(sb['views']))
    print(u'sheets {} | views {} | differences {}'.format(len(sa['sheets']), n_views, len(diffs)))
    for d in diffs[:60]:
        print(u'  ' + d)
    return 1 if diffs else 0


if __name__ == '__main__':
    sys.exit(main(*sys.argv[1:]))
