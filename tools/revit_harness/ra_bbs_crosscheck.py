# -*- coding: utf-8 -*-
"""
CPython: the BBS exported by ra_doc_audit.py checked against the model's rebars (audit.json in the same folder):
every row traced to its bars (diameter, shape, quantity, BS 8666 length rounded up to 25), every scheduled bar in a
row, no mark naming two bars on one drawing, sheet names and view names clean, each sheet's notes naming its BBS.
Usage: python ra_bbs_crosscheck.py <folder with audit.json and BBS_*.csv>
"""
import collections
import csv
import glob
import html
import json
import math
import os
import re
import sys


def main(folder):
    r = json.load(open(os.path.join(folder, 'audit.json')))
    rebars = dict((k, v) for k, v in r['rebars'].items() if 'error' not in v)
    unreadable = [k for k, v in r['rebars'].items() if 'error' in v]
    model = collections.defaultdict(lambda: {'n': 0, 'len': set(), 'dia': set(), 'shape': set()})
    for v in rebars.values():
        if v['key']:
            m = model[(v['key'], v['partition'], v['mark'])]
            m['n'] += v['qty']
            m['len'].add(v['bar_length'])
            m['dia'].add(int(v['dia']))
            m['shape'].add(v['shape'])
    rows, problems = 0, []
    for f in sorted(glob.glob(os.path.join(folder, 'BBS_45*.csv'))):
        key = os.path.basename(f)[4:-4]
        seen = set()
        for row in csv.reader(open(f, encoding='utf-8-sig'), delimiter=';'):
            if row[0] == 'Member' or not row[1]:
                if row[0].startswith('Grand') and u'Grand total:' in row[0]:
                    problems.append(('grand total counts elements', key, row[0]))
                continue
            rows += 1
            member, mark, typ, mbrs, _each, total, length, shape = row[:8]
            base = re.match(r'(\d+)', mark).group(1)
            k = (key, member, base)
            m = model.get(k)
            if m is None:
                problems.append(('row not traced to the model', k))
                continue
            seen.add(k)
            if {int(typ[1:])} != m['dia'] or shape not in m['shape']:
                problems.append(('diameter/shape', k, typ, shape, m['dia'], m['shape']))
            if mark == base and int(total) != m['n'] * int(mbrs):
                problems.append(('quantity', k, total, m['n'], mbrs))
            if mark == base and len(m['len']) == 1 and int(length) != int(math.ceil(list(m['len'])[0] / 25.0) * 25):
                problems.append(('length', k, length, m['len']))
        problems += [('scheduled bar in no row', k) for k in model if k[0] == key and k not in seen]
    by = collections.defaultdict(set)
    for v in rebars.values():
        by[(v['drawing'], v['mark'])].add((v['dia'], v['shape'], v['bar_length'], v['varying']))
    problems += [('mark names two bars on one drawing', k) for k, s in by.items() if len(s) > 1]
    for s in r['sheets']:
        if re.search(r'\(\d+\)', s['name']):
            problems.append(('sheet name numbered', s['number'], s['name']))
        for vp in s['viewports']:
            if re.search(r'\(\d+\)$', vp['view']):
                problems.append(('view name numbered', s['number'], vp['view']))
        notes = u' '.join(html.unescape(n) for n in s['notes'])
        if s['number'] < '5500' and notes:
            refs = sorted(set(v['key'] for v in rebars.values() if v['drawing'] == s['number'] and v['key']))
            listed = re.search(r'Bar schedules: ([^.]*)\.', notes)
            listed = sorted(x.strip() for x in listed.group(1).split(',')) if listed else []
            if refs != listed:
                problems.append(('notes list other schedules', s['number'], listed, refs))
            if u'Buildability check' in notes and u'0 error(s)' not in notes:
                problems.append(('failed QA printed', s['number']))
    print('rows {} | unreadable rebars {} | problems {}'.format(rows, unreadable, len(problems)))
    for p in problems:
        print(' ', p)
    return 1 if problems else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1]))
