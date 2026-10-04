# -*- coding: utf-8 -*-
"""
T8.1 one-off migration: every plugin transaction goes through nosa_utils.transactions, so Revit
failures never open a dialog. `revit.Transaction(` -> `nosa_tx.revit_transaction(`,
`DB.Transaction(...)` -> `nosa_tx.guard(DB.Transaction(...))`. Transactions that already install
their own failures preprocessor are left alone. Usage: python tools/migrate_transactions.py [--dry]
"""
from __future__ import print_function
import ast
import io
import os
import re
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
IMPORT = u'from nosa_utils import transactions as nosa_tx  # T8.1: no Revit failure dialogs\n'
SKIP = (os.path.join('lib', 'nosa_utils', 'transactions.py'),)


def _close_paren(s, i):
    """Index of the ')' closing the '(' at s[i], skipping strings."""
    depth, j, quote = 0, i, None
    while j < len(s):
        c = s[j]
        if quote:
            if c == '\\':
                j += 2
                continue
            if s.startswith(quote, j):
                j += len(quote)
                quote = None
                continue
        elif c in '\'"':
            quote = s[j:j + 3] if s[j:j + 3] in ('"""', "'''") else c
            j += len(quote)
            continue
        elif c == '#':
            j = s.index('\n', j) if '\n' in s[j:] else len(s)
            continue
        elif c == '(':
            depth += 1
        elif c == ')':
            depth -= 1
            if depth == 0:
                return j
        j += 1
    raise ValueError('unbalanced parenthesis at %d' % i)


def _already_guarded(s, start):
    window = s[start:start + 600]
    return 'SetFailuresPreprocessor' in window or '_rollback_on_error' in window or 'guard' in window[:60]


def migrate_text(s):
    changed = 0
    out, pos = [], 0
    for m in re.finditer(r'(?<![\w.])DB\.Transaction\(', s):
        if m.start() < pos or _already_guarded(s, m.start()):
            continue
        before = s[max(0, m.start() - 15):m.start()]
        if 'guard(' in before:
            continue
        end = _close_paren(s, m.end() - 1)
        out.append(s[pos:m.start()])
        out.append(u'nosa_tx.guard(' + s[m.start():end + 1] + u')')
        pos = end + 1
        changed += 1
    out.append(s[pos:])
    s = u''.join(out)
    s, n = re.subn(r'(?<![\w])(?:pyrevit\.)?revit\.Transaction\(', u'nosa_tx.revit_transaction(', s)
    return s, changed + n


def insert_import(s):
    if IMPORT.strip().split('  #')[0] in s:
        return s
    lines = s.splitlines(True)
    last = None
    i = 0
    while i < len(lines):
        line = lines[i]
        if re.match(r'(def|class) ', line):
            break
        stripped = line.strip()
        top = not line[:1].isspace()
        if top and (stripped.startswith('import ') or stripped.startswith('from ')):
            j = i
            if '(' in line and ')' not in line:
                while ')' not in lines[j]:
                    j += 1
            last = j
            i = j
        elif stripped.startswith('sys.path.insert') or stripped.startswith('sys.path.append'):
            last = i
        i += 1
    at = 0 if last is None else last + 1
    if last is None:
        # after the coding line / module docstring
        while at < len(lines) and (lines[at].startswith('#') or not lines[at].strip()):
            at += 1
        if at < len(lines) and lines[at].lstrip().startswith(('"""', "'''", 'u"""')):
            quote = '"""' if '"""' in lines[at] else "'''"
            if lines[at].count(quote) < 2:
                at += 1
                while at < len(lines) and quote not in lines[at]:
                    at += 1
            at += 1
    lines.insert(at, IMPORT)
    return u''.join(lines)


def main(dry):
    report = []
    for base in ('NOSA.tab', 'lib'):
        for dp, dns, fns in os.walk(os.path.join(ROOT, base)):
            if '__pycache__' in dp or '.DISABLED' in dp:
                continue
            for f in fns:
                if not f.endswith('.py'):
                    continue
                path = os.path.join(dp, f)
                rel = os.path.relpath(path, ROOT)
                if rel in SKIP:
                    continue
                raw = io.open(path, 'rb').read()
                bom = raw[:3] == b'\xef\xbb\xbf'
                text = raw.decode('utf-8-sig')
                crlf = u'\r\n' in text
                text = text.replace(u'\r\n', u'\n')
                new, n = migrate_text(text)
                if not n:
                    continue
                new = insert_import(new)
                try:
                    ast.parse(text)
                    parsed_before = True
                except SyntaxError:
                    parsed_before = False
                if parsed_before:
                    ast.parse(new)   # raises if the migration broke the file
                report.append((rel, n))
                if not dry:
                    data = new.replace(u'\n', u'\r\n') if crlf else new
                    io.open(path, 'wb').write((b'\xef\xbb\xbf' if bom else b'') + data.encode('utf-8'))
    for rel, n in report:
        print('%3d  %s' % (n, rel))
    print('%d file(s), %d transaction(s)' % (len(report), sum(n for _r, n in report)))


if __name__ == '__main__':
    main('--dry' in sys.argv)
