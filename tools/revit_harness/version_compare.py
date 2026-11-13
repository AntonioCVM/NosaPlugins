# -*- coding: utf-8 -*-
"""
CPython (point 1, user 2026-10-28): one building_test run of a Revit version against the reference run of another
- total time, memory peak, views/sheets/tags, QA findings by check, drawing review incidents, BBS rows and totals,
errors and exceptions - so a version's differences show line by line.
Usage: python version_compare.py <run OUT .txt> <reference OUT .txt>
"""
import collections
import io
import json
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))


def facts(out):
    text = io.open(out, encoding='utf-8', errors='replace').read()
    folder = out[:-4]
    f = collections.OrderedDict()
    m = re.search(r'^total (\d+) s', text, re.M)
    f['total s'] = int(m.group(1)) if m else None
    peaks = [float(x) for x in re.findall(r'^\d\d:\d\d:\d\d\s+([\d.]+)GB', io.open(out + '.progress', encoding='utf-8',
                                                                                     errors='replace').read(), re.M)]
    f['peak GB (progress)'] = max(peaks) if peaks else None
    m = re.search(r'STATUS: (\d+) view\(s\), (\d+) sheet\(s\) and (\d+) tag', text)
    f['views/sheets/tags'] = '/'.join(m.groups()) if m else None
    m = re.search(r'== QA: (\d+) finding', text)
    f['QA findings'] = int(m.group(1)) if m else None
    m = re.search(r'^Drawing review \((\d+) incident', text, re.M)
    f['drawing incidents'] = int(m.group(1)) if m else None
    for cat in ('A3', 'A4', 'A4i', 'A7', 'A9', 'A10', 'A11'):
        m = re.search(r'^  - ' + cat + r' [^:]*: (\d+)', text, re.M)
        f[cat] = int(m.group(1)) if m else 0
    m = re.search(r'beam/column joints: (\d+) R1 applied, (\d+) R3', text)
    f['joints R1/R3'] = '{}/{}'.format(*m.groups()) if m else None
    f['exceptions'] = len(re.findall(r'EXCEPTION|Traceback', text))
    f['pdf'] = len(os.listdir(os.path.join(folder, 'pdf'))) if os.path.isdir(os.path.join(folder, 'pdf')) else 0
    cross = subprocess.run([sys.executable, os.path.join(HERE, 'ra_bbs_crosscheck.py'), folder], capture_output=True,
                           text=True, encoding='utf-8', errors='replace').stdout
    m = re.search(r'rows (\d+) \| unreadable rebars (\S+) \| problems (\d+)', cross)
    f['BBS rows / problems'] = '{} / {}'.format(m.group(1), m.group(3)) if m else None
    f['BBS totals'] = '; '.join(re.findall(r'total (\S+): (\S+) kg', cross) and
                                ['{}={}'.format(k, v) for k, v in re.findall(r'total (\S+): (\S+) kg', cross)])
    qa = os.path.join(folder, 'qa_findings.json')
    checks = collections.Counter(r['check'] for r in json.load(io.open(qa, encoding='utf-8'))) if os.path.exists(qa) \
        else collections.Counter()
    return f, checks


def main(run, ref):
    a, qa_a = facts(run)
    b, qa_b = facts(ref)
    print('| | {} | {} (ref) |'.format(os.path.basename(run), os.path.basename(ref)))
    print('|---|---|---|')
    for k in a:
        flag = '' if a[k] == b[k] or k in ('total s', 'peak GB (progress)') else ' **≠**'
        print('| {} | {}{} | {} |'.format(k, a[k], flag, b[k]))
    diff = [(k, qa_a[k], qa_b[k]) for k in sorted(set(qa_a) | set(qa_b)) if qa_a[k] != qa_b[k]]
    print('\nQA by check, where they differ: {}'.format(diff or 'none'))


if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2])
