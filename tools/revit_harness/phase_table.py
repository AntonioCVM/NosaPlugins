# -*- coding: utf-8 -*-
"""
CPython: building_test runs compared phase by phase - wall and processor seconds (the run's 'memory by phase' table)
and each phase's memory peak (GB private): the highest reading while the phase was open, from the run's progress
file and, when given, the watchdog's samples (nosa_mem_<pid>.log) taken in the same minutes.
Usage: python phase_table.py <new OUT .txt> <old OUT .txt> [--mem new.log] [--mem-old old.log]
"""
import argparse
import io
import re

ROW = re.compile(r'^\s{4}(\S.*?)\s+start\s+([\d.]+) end\s+([\d.]+) grown\s+\S+ ws\s+[\d.]+\s+(\d+) s(?:\s+cpu\s+(\d+) s)?')
LINE = re.compile(r'^(\d\d:\d\d:\d\d)\s+([\d.]+)GB\s+(.*)$')
OPEN = re.compile(r'^\s*> (.*) \(([\d.]+) GB\)$')
CLOSE = re.compile(r'^\s*< (.*) \(([\d.]+) GB,')
STEP = re.compile(r'^-- start (\w+)')
NESTED = re.compile(r'^(\d\d:\d\d:\d\d)()\s+([<>] .*)$')      # a timed function: no memory column
MEM = re.compile(r'^(\d\d:\d\d:\d\d) priv=([\d.]+) GB')


def secs(hms):
    h, m, s = (int(x) for x in hms.split(':'))
    return h * 3600 + m * 60 + s


def table(path):
    out, total = {}, None
    for line in io.open(path, encoding='utf-8', errors='replace'):
        m = ROW.match(line)
        if m:
            out[m.group(1).strip()] = {'wall': int(m.group(4)), 'cpu': int(m.group(5)) if m.group(5) else None}
        if line.startswith('total '):
            total = int(line.split()[1])
    return out, total


def peaks(progress, memlog=None):
    """{phase: peak GB} and the [(t0, t1, name)] intervals of every phase."""
    events, opened, intervals = [], {}, []
    for line in io.open(progress, encoding='utf-8', errors='replace'):
        m = LINE.match(line.rstrip('\n')) or NESTED.match(line.rstrip('\n'))
        if not m:
            continue
        t, rest = secs(m.group(1)), m.group(3)
        gb = float(m.group(2)) if m.group(2) else None
        if gb is None:
            g = re.search(r'\(([\d.]+) GB', rest)
            gb = float(g.group(1)) if g else None
        if gb is not None:
            events.append((t, gb))
        o, c, s = OPEN.match(rest), CLOSE.match(rest), STEP.match(rest)
        if s:                                    # building_test's own steps: 'reinforce <kind>' until the next line
            name = u'reinforce ' + s.group(1)
            opened[name] = t
        elif rest.startswith('== ') and any(k.startswith('reinforce ') for k in opened):
            for k in [k for k in opened if k.startswith('reinforce ')]:
                intervals.append((opened.pop(k), t, k))
        if o:
            opened.setdefault(o.group(1), t)
        if c and c.group(1) in opened:
            intervals.append((opened.pop(c.group(1)), t, c.group(1)))
    if memlog:
        for line in io.open(memlog, encoding='utf-8', errors='replace'):
            m = MEM.match(line)
            if m:
                events.append((secs(m.group(1)), float(m.group(2))))
    out = {}
    for t0, t1, name in intervals:
        inside = [gb for t, gb in events if t0 <= t <= t1]
        if inside:
            out[name] = max(out.get(name, 0.0), max(inside))
    return out, (max(gb for _t, gb in events) if events else None)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('new')
    ap.add_argument('old')
    ap.add_argument('--mem')
    ap.add_argument('--mem-old')
    a = ap.parse_args()
    new, new_total = table(a.new)
    old, old_total = table(a.old)
    pk_new, top_new = peaks(a.new + '.progress', a.mem)
    pk_old, top_old = peaks(a.old + '.progress', a.mem_old)
    print('| Fase | Antes s (CPU) | Ahora s (CPU) | Diferencia s | Pico antes GB | Pico ahora GB |')
    print('|---|---:|---:|---:|---:|---:|')
    for name in list(old) + [n for n in new if n not in old]:
        o, n = old.get(name), new.get(name)
        fmt = lambda r: '-' if r is None else ('{} ({})'.format(r['wall'], r['cpu']) if r['cpu'] is not None
                                               else str(r['wall']))
        diff = '{:+d}'.format(n['wall'] - o['wall']) if o and n else '-'
        po, pn = pk_old.get(name), pk_new.get(name)
        print('| {} | {} | {} | {} | {} | {} |'.format(name, fmt(o), fmt(n), diff,
                                                       '-' if po is None else '{:.2f}'.format(po),
                                                       '-' if pn is None else '{:.2f}'.format(pn)))
    print('| **total** | {} | {} | {} | {} | {} |'.format(
        old_total, new_total, '{:+d}'.format(new_total - old_total) if old_total and new_total else '-',
        '-' if top_old is None else '{:.2f}'.format(top_old), '-' if top_new is None else '{:.2f}'.format(top_new)))


if __name__ == '__main__':
    main()
