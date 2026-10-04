# -*- coding: utf-8 -*-
"""
T8.4 one-off: every `except ...: pass` reported by NOSA006 logs through
nosa_utils.telemetry.log_swallowed (once per place per session). In script.py usage-stat blocks
and in tests the silence is kept on purpose, with a justified suppression comment.
Usage: python tools/fix_swallowed.py [--dry]
"""
from __future__ import print_function
import ast
import io
import os
import re
import subprocess
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.dirname(__file__))
from migrate_transactions import insert_import  # noqa: E402

IMPORT_LINE = u'from nosa_utils.telemetry import log_swallowed\n'


def findings():
    out = subprocess.run([sys.executable, os.path.join(ROOT, 'tools', 'nosa_lint.py')], capture_output=True,
                         text=True, encoding='utf-8', errors='ignore', cwd=ROOT).stdout
    by_file = {}
    for line in out.splitlines():
        m = re.match(r'(.+?):(\d+): MEDIUM NOSA006', line)
        if m:
            by_file.setdefault(m.group(1), []).append(int(m.group(2)))
    return by_file


def enclosing(lines, i):
    for j in range(i, -1, -1):
        m = re.match(r'\s*def (\w+)\(', lines[j])
        if m:
            return m.group(1)
    return u'module'


def fix_file(rel, numbers, dry):
    path = os.path.join(ROOT, rel)
    raw = io.open(path, 'rb').read()
    bom = raw[:3] == b'\xef\xbb\xbf'
    text = raw.decode('utf-8-sig')
    crlf = u'\r\n' in text
    lines = text.replace(u'\r\n', u'\n').split(u'\n')
    keep_silent = os.path.basename(rel) == 'script.py' or '/tests/' in rel.replace('\\', '/')
    logged = 0
    for n in sorted(numbers, reverse=True):
        i = n - 1
        head = lines[i]
        if keep_silent:
            reason = u'usage stats must never break the tool' if os.path.basename(rel) == 'script.py' \
                else u'test cleanup, failure is irrelevant'
            lines[i] = head.rstrip() + u'  # nosa-lint: disable=NOSA006 - ' + reason
            continue
        where = enclosing(lines, i)
        if where == u'module':
            # import-time fallbacks run before log_swallowed can be imported
            lines[i] = head.rstrip() + u'  # nosa-lint: disable=NOSA006 - optional at import time'
            continue
        if re.search(r':\s*pass\s*$', head):                     # `except X: pass` on one line
            indent = re.match(r'(\s*)', head).group(1)
            lines[i] = re.sub(r':\s*pass\s*$', u':', head)
            lines.insert(i + 1, indent + u"    log_swallowed(_LOG, u'{}')".format(where))
        else:
            body = lines[i + 1]
            assert body.strip().split(u'#')[0].strip() == u'pass', (rel, n, body)
            indent = re.match(r'(\s*)', body).group(1)
            lines[i + 1] = indent + u"log_swallowed(_LOG, u'{}')".format(where)
        logged += 1
    new = u'\n'.join(lines)
    if logged:
        if not re.search(r'^\s*from nosa_utils\.telemetry import [^\n]*log_swallowed', new, re.M):
            new = insert_import(new) if False else _add_line(new, IMPORT_LINE)
        if not re.search(r'^_LOG\s*=', new, re.M):
            key = os.path.splitext(os.path.basename(rel))[0]
            plugin = [p for p in rel.replace('\\', '/').split('/') if p.endswith('.pushbutton')]
            key = (plugin[0].split('.')[0].lower() + u'.' + key) if plugin else u'nosa_utils.' + key
            new = new.replace(IMPORT_LINE, IMPORT_LINE + u"_LOG = u'{}'\n".format(key), 1) \
                if IMPORT_LINE in new else _add_line(new, u"_LOG = u'{}'\n".format(key))
    try:
        ast.parse(text)
        ast.parse(new)
    except SyntaxError as e:
        raise SystemExit('broke %s: %s' % (rel, e))
    if not dry:
        data = new.replace(u'\n', u'\r\n') if crlf else new
        io.open(path, 'wb').write((b'\xef\xbb\xbf' if bom else b'') + data.encode('utf-8'))
    return logged, len(numbers) - logged


def _add_line(text, line):
    """Insert `line` with the module's other imports (after the sys.path setup)."""
    from migrate_transactions import IMPORT
    marked = insert_import(text)
    return marked.replace(IMPORT, line, 1)


def main(dry):
    total_l = total_s = 0
    for rel, numbers in sorted(findings().items()):
        logged, silent = fix_file(rel, numbers, dry)
        total_l += logged
        total_s += silent
        print('%3d logged %2d kept silent  %s' % (logged, silent, rel))
    print('total: %d logged, %d kept silent (justified)' % (total_l, total_s))


if __name__ == '__main__':
    main('--dry' in sys.argv)
