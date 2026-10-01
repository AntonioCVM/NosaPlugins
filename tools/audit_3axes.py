# -*- coding: utf-8 -*-
"""
Three-axis audit of every active NOSA plugin (MASTER_ROADMAP T6.1): code, XAML appearance, usefulness.

    python tools/audit_3axes.py [--usage PATH] [--out docs/AUDIT_3AXES.md]

Code: nosa_lint findings by severity, lines of code, tests. Appearance: NOSA colour resources,
Century Gothic, dark-mode toggle, loading overlay, 96 px icon with an icon.svg master.
Usefulness: launches recorded in NOSA_Configs/_usage.json (local to the machine that ran it).
"""
from __future__ import print_function

import argparse
import io
import json
import os
import re
import subprocess
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
COLOURS = ('BgColor', 'PanelColor', 'TextColor', 'AccentColor', 'BorderColor')


def norm(name):
    return re.sub(r'[^a-z0-9]', '', name.lower())


def plugins():
    """(panel, folder) of every active pushbutton (not .nobutton / .DISABLED)."""
    out = []
    tab = os.path.join(ROOT, 'NOSA.tab')
    for dirpath, dirnames, _files in os.walk(tab):
        dirnames[:] = [d for d in dirnames if not d.endswith(('.nobutton', '.DISABLED')) and d != '__pycache__']
        for d in list(dirnames):
            if d.endswith('.pushbutton'):
                rel = os.path.relpath(os.path.join(dirpath, d), tab).replace(os.sep, '/')
                out.append((rel.split('/')[0].replace('.panel', ''), os.path.join(dirpath, d)))
                dirnames.remove(d)
    return sorted(out, key=lambda p: p[1])


def lint_findings():
    proc = subprocess.run([sys.executable, os.path.join(ROOT, 'tools', 'nosa_lint.py'), '--json',
                           '--fail-on', 'never', 'NOSA.tab'], cwd=ROOT, capture_output=True, text=True)
    try:
        return json.loads(proc.stdout or '[]')
    except ValueError:
        return []


def usage_counts(path):
    try:
        data = json.load(io.open(path, encoding='utf-8'))
    except (IOError, OSError, ValueError):
        return {}
    counts = {}
    for key, value in data.items():
        if isinstance(value, int):
            counts[norm(key)] = counts.get(norm(key), 0) + value
    return counts


def icon_info(folder):
    path = os.path.join(folder, 'icon.png')
    size = None
    if os.path.isfile(path):
        try:
            from PIL import Image
            size = Image.open(path).size
        except Exception:
            size = None
    return size, os.path.isfile(os.path.join(folder, 'icon.svg'))


def xaml_info(folder):
    text = u''
    for dirpath, _d, files in os.walk(folder):
        for f in files:
            if f.endswith('.xaml'):
                text += io.open(os.path.join(dirpath, f), encoding='utf-8-sig', errors='replace').read()
    if not text:
        return None
    return {
        'colours': all(c in text for c in COLOURS),
        'font': 'Century Gothic' in text,
        'dark': 'ChkDarkMode' in text,
        'loading': 'LoadingPanel' in text,
    }


def code_info(folder):
    loc, has_tests = 0, False
    for dirpath, _d, files in os.walk(folder):
        if '__pycache__' in dirpath:
            continue
        if os.path.basename(dirpath) == 'tests':
            has_tests = has_tests or any(f.startswith('test_') for f in files)
        for f in files:
            if f.endswith('.py'):
                loc += sum(1 for _ in io.open(os.path.join(dirpath, f), encoding='utf-8-sig', errors='replace'))
    return loc, has_tests


def root_tests():
    folder = os.path.join(ROOT, 'tests')
    return [norm(f[5:-3]) for f in os.listdir(folder) if f.startswith('test_') and f.endswith('.py')]


def audit(usage_path):
    findings = lint_findings()
    usage = usage_counts(usage_path)
    shared_tests = root_tests()
    rows = []
    for panel, folder in plugins():
        name = os.path.basename(folder).replace('.pushbutton', '')
        rel = os.path.relpath(folder, ROOT).replace(os.sep, '/')
        sev = {'critical': 0, 'high': 0, 'medium': 0, 'low': 0}
        for f in findings:
            if f['path'].startswith(rel + '/'):
                sev[f['severity']] = sev.get(f['severity'], 0) + 1
        loc, has_tests = code_info(folder)
        has_tests = has_tests or any(t.startswith(norm(name)) for t in shared_tests)
        size, svg = icon_info(folder)
        x = xaml_info(folder)
        flags = []
        if sev['critical'] or sev['high']:
            flags.append('lint')
        if x is not None and not (x['colours'] and x['font']):
            flags.append('style')
        if size != (96, 96) or not svg:
            flags.append('icon')
        if not has_tests:
            flags.append('tests')
        uses = usage.get(norm(name), 0)
        rows.append({'panel': panel, 'name': name, 'uses': uses, 'loc': loc, 'tests': has_tests,
                     'sev': sev, 'xaml': x, 'icon': size, 'svg': svg, 'flags': flags})
    return rows


def yes(v):
    return u'✔' if v else u'–'


def rule_summary(findings):
    counts = {}
    for f in findings:
        if f['path'].startswith('NOSA.tab/') and '.nobutton/' not in f['path']:
            key = (f['severity'], f['rule'], f['message'])
            counts[key] = counts.get(key, 0) + 1
    order = {'critical': 0, 'high': 1, 'medium': 2, 'low': 3}
    lines = [u'## Lint findings by rule', u'', u'| Severity | Rule | Message | Count |', u'|---|---|---|---:|']
    for (sev, rule, msg), n in sorted(counts.items(), key=lambda kv: (order.get(kv[0][0], 9), -kv[1])):
        lines.append(u'| {} | {} | {} | {} |'.format(sev, rule, msg, n))
    return lines


def markdown(rows, usage_path, findings=()):
    lines = [u'# NOSA plugins — three-axis audit', u'',
             u'Generated by `tools/audit_3axes.py` (`/audit-nosa-full`). Usage: `{}`.'.format(
                 u'NOSA_Configs/_usage.json' if os.path.isfile(usage_path) else u'(no usage file)'),
             u'', u'| Panel | Plugin | Uses | LOC | Tests | Lint C/H/M/L | NOSA colours | Font | Dark | Loading | Icon | Flags |',
             u'|---|---|---:|---:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|---|']
    for r in sorted(rows, key=lambda r: (-r['uses'], r['name'])):
        s, x = r['sev'], r['xaml'] or {}
        icon = u'{}×{}{}'.format(r['icon'][0], r['icon'][1], u' +svg' if r['svg'] else u'') if r['icon'] else u'missing'
        lines.append(u'| {} | {} | {} | {} | {} | {}/{}/{}/{} | {} | {} | {} | {} | {} | {} |'.format(
            r['panel'], r['name'], r['uses'], r['loc'], yes(r['tests']), s['critical'], s['high'],
            s['medium'], s['low'], yes(x.get('colours')) if r['xaml'] else u'n/a',
            yes(x.get('font')) if r['xaml'] else u'n/a', yes(x.get('dark')) if r['xaml'] else u'n/a',
            yes(x.get('loading')) if r['xaml'] else u'n/a', icon, u', '.join(r['flags']) or u'OK'))
    total = len(rows)
    count = lambda flag: sum(1 for r in rows if flag in r['flags'])
    lines += [u'', u'**{} active plugins** — lint C/H: {} · style: {} · icon: {} · no tests: {} · OK: {}'.format(
        total, count('lint'), count('style'), count('icon'), count('tests'),
        sum(1 for r in rows if not r['flags'])), u'']
    lines += rule_summary(findings) + [u'']
    return u'\n'.join(lines)


def main():
    ap = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    ap.add_argument('--usage', default=os.path.join(ROOT, 'NOSA_Configs', '_usage.json'))
    ap.add_argument('--out', default=os.path.join(ROOT, 'docs', 'AUDIT_3AXES.md'))
    args = ap.parse_args()
    rows = audit(args.usage)
    io.open(args.out, 'w', encoding='utf-8').write(markdown(rows, args.usage, lint_findings()))
    print(u'{} plugins audited -> {}'.format(len(rows), os.path.relpath(args.out, ROOT)))


if __name__ == '__main__':
    main()
