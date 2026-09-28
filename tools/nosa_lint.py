# -*- coding: utf-8 -*-
"""Deterministic linter for the NOSA pyRevit extension conventions (CLAUDE.md)."""
from __future__ import print_function

import argparse
import ast
import io
import json
import os
import re
import struct
import sys
import xml.etree.ElementTree as ET

EXT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))

SEVERITIES = ('critical', 'high', 'medium', 'low')
SEV_RANK = dict((s, i) for i, s in enumerate(SEVERITIES))

RULES = {
    'NOSA000': ('critical', 'File cannot be parsed'),
    'NOSA001': ('critical', "Module-level 'from pyrevit import DB' (multi-Revit IOError) - use 'from Autodesk.Revit import DB'"),
    'NOSA002': ('critical', 'Revit API enum accessed at import time (module or class body) - move inside a function'),
    'NOSA003': ('high', "'nosa_utils.loader' can fail silently - use imp.load_source"),
    'NOSA004': ('high', 'Dead sys.path entry (wrong number of ..) - resolves to a directory that does not exist'),
    'NOSA005': ('medium', "Transaction name does not start with 'NOSA'"),
    'NOSA006': ('medium', 'Exception silently swallowed (except: pass) - log it'),
    'NOSA007': ('medium', 'unicode() used without the CPython compat shim'),
    'NOSA008': ('low', "'from pyrevit import DB' inside a function - prefer 'from Autodesk.Revit import DB'"),
    'NOSA009': ('high', 'Spanish text in a user-facing Python string'),
    'NOSA100': ('critical', 'XAML is not well-formed'),
    'NOSA101': ('critical', "'{Binding type}' collides with a Python keyword - rename the attribute"),
    'NOSA102': ('critical', "'{Binding _x}' - underscore-prefixed attributes cannot be bound"),
    'NOSA103': ('critical', 'Selection event fires during LoadComponent (SelectionChanged + initial selection in XAML) - window init crash risk'),
    'NOSA104': ('high', 'Spanish text in XAML'),
    'NOSA105': ('high', 'Window is missing NOSA colour resources'),
    'NOSA106': ('medium', 'SelectedIndex/SelectionChanged set in XAML - convention is to wire it in code after LoadComponent'),
    'NOSA201': ('critical', 'Pushbutton has no script.py'),
    'NOSA202': ('high', 'Pushbutton icon missing or not 32x32'),
    'NOSA203': ('high', 'Window class does not inherit NOSAWindow'),
}

REQUIRED_BRUSHES = ('BgColor', 'PanelColor', 'TextColor', 'AccentColor', 'BorderColor')
REVIT_ENUMS = ('BuiltInCategory', 'BuiltInParameter')
UI_ATTRS = ('Text', 'Content', 'Header', 'Title', 'ToolTip', 'Tag', 'Watermark', 'PlaceholderText')
UI_CALLS = ('alert', 'Show', 'ask_for_string', 'ask_for_one_item', 'SelectFromList', 'LogLine', 'SetLoading')
SPANISH_CHARS = re.compile(u'[áéíóúñ¿¡ÁÉÍÓÚÑ]')
SPANISH_WORDS = re.compile(
    r'\b(Cancelar|Aceptar|Seleccion(?:ar|e)|Guardar|Cerrar|Crear|Borrar|Eliminar|Nombre|Distancia|Longitud|'
    r'Espesor|Ancho|Alto|Todos|Ninguno|Buscar|Exportar|Generar|Aplicar|Hoja|Nivel|Muro|Viga|Pilar|Zapata|'
    r'Armado|Encepado|Pilote|Error al|Sin |Aviso|Advertencia|Listo|Hecho)\b')
SUPPRESS = re.compile(r'nosa-lint:\s*disable=([A-Z0-9, ]+)')
SKIP_DIRS = {'__pycache__', '.git', '.claude', 'node_modules'}


class Finding(object):
    def __init__(self, rule, path, line, detail=''):
        self.rule = rule
        self.severity = RULES[rule][0]
        self.path = path
        self.line = line
        self.detail = detail

    def as_dict(self):
        return {'rule': self.rule, 'severity': self.severity, 'path': rel(self.path),
                'line': self.line, 'message': RULES[self.rule][1], 'detail': self.detail}

    def __str__(self):
        extra = ' [%s]' % self.detail if self.detail else ''
        return '%s:%s: %s %s %s%s' % (rel(self.path), self.line, self.severity.upper(), self.rule,
                                      RULES[self.rule][1], extra)


def rel(path):
    try:
        return os.path.relpath(path, EXT_ROOT).replace('\\', '/')
    except ValueError:
        return path


def read_text(path):
    with io.open(path, encoding='utf-8-sig', errors='replace') as f:
        return f.read()


def looks_spanish(text):
    return bool(SPANISH_CHARS.search(text) or SPANISH_WORDS.search(text))


def suppressed(lines, lineno, rule):
    if 1 <= lineno <= len(lines):
        m = SUPPRESS.search(lines[lineno - 1])
        if m and rule in [r.strip() for r in m.group(1).split(',')]:
            return True
    return False


# --------------------------------------------------------------------------- python

def _str_value(node):
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _call_name(node):
    func = node.func
    if isinstance(func, ast.Attribute):
        return func.attr
    if isinstance(func, ast.Name):
        return func.id
    return None


def _import_time_nodes(tree):
    """Yield nodes executed at import time: module and class bodies, not function bodies."""
    stack = list(tree.body)
    while stack:
        node = stack.pop()
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
            continue
        yield node
        if isinstance(node, ast.ClassDef):
            stack.extend(node.body)
            stack.extend(node.decorator_list)
            continue
        for child in ast.iter_child_nodes(node):
            stack.append(child)



def check_sys_path(path, tree, findings):
    here = os.path.dirname(os.path.abspath(path))
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and _call_name(node) == 'join'):
            continue
        args = node.args
        if len(args) < 2:
            continue
        head = ast.dump(args[0])
        if '__file__' not in head or 'dirname' not in head:
            continue
        parts = [_str_value(a) for a in args[1:]]
        if any(p is None for p in parts) or '..' not in parts:
            continue
        if parts[-1] != 'lib':
            continue
        target = os.path.normpath(os.path.join(here, *parts))
        if not os.path.isdir(target):
            findings.append(Finding('NOSA004', path, node.lineno, rel(target)))


def lint_python(path):
    findings = []
    src = read_text(path)
    lines = src.splitlines()
    try:
        tree = ast.parse(src, filename=path)
    except SyntaxError as exc:
        return [Finding('NOSA000', path, exc.lineno or 1, str(exc.msg))]

    import_time = list(_import_time_nodes(tree))
    import_time_ids = set(id(n) for n in import_time)

    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == 'pyrevit':
            if any(a.name == 'DB' for a in node.names):
                rule = 'NOSA001' if id(node) in import_time_ids else 'NOSA008'
                findings.append(Finding(rule, path, node.lineno))
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            names = [getattr(node, 'module', None) or ''] + [a.name for a in node.names]
            if any('nosa_utils.loader' in n or n == 'load_local_module' for n in names):
                findings.append(Finding('NOSA003', path, node.lineno))

    for node in import_time:
        if isinstance(node, ast.Attribute) and node.attr in REVIT_ENUMS and isinstance(node.ctx, ast.Load):
            findings.append(Finding('NOSA002', path, node.lineno, node.attr))

    check_sys_path(path, tree, findings)

    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            name = _call_name(node)
            if name in ('Transaction', 'TransactionGroup'):
                for arg in list(node.args) + [k.value for k in node.keywords if k.arg == 'name']:
                    text = _str_value(arg)
                    if text is not None and not text.strip().startswith('NOSA'):
                        findings.append(Finding('NOSA005', path, node.lineno, text[:60]))
            if name in UI_CALLS:
                for arg in node.args:
                    text = _str_value(arg)
                    if text and looks_spanish(text):
                        findings.append(Finding('NOSA009', path, node.lineno, text[:60]))
        if isinstance(node, ast.ExceptHandler):
            if len(node.body) == 1 and isinstance(node.body[0], ast.Pass):
                findings.append(Finding('NOSA006', path, node.lineno))

    if re.search(r'(?<![\w.])unicode\(', src) and 'NameError' not in src:
        m = re.search(r'(?<![\w.])unicode\(', src)
        findings.append(Finding('NOSA007', path, src.count('\n', 0, m.start()) + 1))

    return [f for f in findings if not suppressed(lines, f.line, f.rule)]


# --------------------------------------------------------------------------- xaml

def _local(tag):
    return tag.split('}', 1)[-1]


def lint_xaml(path):
    findings = []
    src = read_text(path)
    lines = src.splitlines()

    def line_of(pattern):
        for i, l in enumerate(lines, 1):
            if pattern in l:
                return i
        return 1

    for m in re.finditer(r'\{Binding\s+(?:Path=)?type\b', src):
        findings.append(Finding('NOSA101', path, src.count('\n', 0, m.start()) + 1))
    for m in re.finditer(r'\{Binding\s+(?:Path=)?_\w+', src):
        findings.append(Finding('NOSA102', path, src.count('\n', 0, m.start()) + 1, m.group(0)))

    try:
        root = ET.fromstring(src.encode('utf-8'))
    except ET.ParseError as exc:
        findings.append(Finding('NOSA100', path, exc.position[0] if exc.position else 1, str(exc)))
        return findings

    for el in root.iter():
        tag = _local(el.tag)
        attrs = dict((_local(k), v) for k, v in el.attrib.items())
        if tag in ('ComboBox', 'TabControl', 'ListBox'):
            name = attrs.get('Name', '')
            has_handler = 'SelectionChanged' in attrs
            preselected = ('SelectedIndex' in attrs or 'SelectedItem' in attrs or
                           any(_local(k) == 'IsSelected' and v.lower() == 'true'
                               for child in el for k, v in child.attrib.items()))
            if has_handler and (preselected or tag == 'TabControl'):
                findings.append(Finding('NOSA103', path, line_of(name or 'SelectionChanged'), '%s %s' % (tag, name)))
            elif has_handler or 'SelectedIndex' in attrs:
                findings.append(Finding('NOSA106', path, line_of(name or 'Selected'), '%s %s' % (tag, name)))
        for key in UI_ATTRS:
            val = attrs.get(key)
            if val and not val.startswith('{') and looks_spanish(val):
                findings.append(Finding('NOSA104', path, line_of(val[:30]), val[:60]))
        if el.text and el.text.strip() and looks_spanish(el.text):
            findings.append(Finding('NOSA104', path, line_of(el.text.strip()[:30]), el.text.strip()[:60]))

    if _local(root.tag) == 'Window':
        keys = set()
        for el in root.iter():
            for k, v in el.attrib.items():
                if _local(k) == 'Key':
                    keys.add(v)
        missing = [b for b in REQUIRED_BRUSHES if b not in keys]
        if missing:
            findings.append(Finding('NOSA105', path, 1, ', '.join(missing)))
    return findings


# --------------------------------------------------------------------------- structure

def _png_size(path):
    with open(path, 'rb') as f:
        head = f.read(24)
    if head[:8] != b'\x89PNG\r\n\x1a\n':
        return None
    return struct.unpack('>II', head[16:24])


def lint_pushbutton(folder):
    findings = []
    if not os.path.isfile(os.path.join(folder, 'script.py')):
        findings.append(Finding('NOSA201', folder, 0))
    icon = os.path.join(folder, 'icon.png')
    names = os.listdir(folder)
    if 'icon.png' not in names:
        alt = [f for f in names if f.lower() == 'icon.png']
        findings.append(Finding('NOSA202', folder, 0, 'wrong case: %s' % alt[0] if alt else 'missing'))
    else:
        size = _png_size(icon)
        if size != (32, 32):
            findings.append(Finding('NOSA202', icon, 0, 'size %s' % (size,)))
    lib = os.path.join(folder, 'lib')
    if os.path.isdir(lib):
        for name in os.listdir(lib):
            if not name.endswith('.py'):
                continue
            p = os.path.join(lib, name)
            try:
                tree = ast.parse(read_text(p))
            except SyntaxError:
                continue
            for node in ast.walk(tree):
                if isinstance(node, ast.ClassDef):
                    bases = [ast.dump(b) for b in node.bases]
                    if any('WPFWindow' in b for b in bases) and not any('NOSAWindow' in b for b in bases):
                        findings.append(Finding('NOSA203', p, node.lineno, node.name))
    return findings


# --------------------------------------------------------------------------- driver

def iter_targets(paths, include_hidden):
    for base in paths:
        base = os.path.abspath(base)
        if os.path.isfile(base):
            yield base
            continue
        for root, dirs, files in os.walk(base):
            dirs[:] = [d for d in dirs if d not in SKIP_DIRS
                       and not d.endswith('.DISABLED')
                       and (include_hidden or not d.endswith('.nobutton'))]
            if root.endswith('.pushbutton'):
                yield root
            for f in files:
                if f.endswith(('.py', '.xaml')):
                    yield os.path.join(root, f)


def lint_target(target):
    if os.path.isdir(target):
        return lint_pushbutton(target)
    if target.endswith('.py'):
        return lint_python(target)
    if target.endswith('.xaml'):
        return lint_xaml(target)
    return []


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('paths', nargs='*', help='files or folders (default: NOSA.tab and lib)')
    parser.add_argument('--include-hidden', action='store_true', help='also lint .nobutton folders')
    parser.add_argument('--fail-on', choices=SEVERITIES + ('never',), default='critical',
                        help='exit 1 if a finding of this severity or worse exists (default: critical)')
    parser.add_argument('--min-severity', choices=SEVERITIES, default='low', help='hide less severe findings')
    parser.add_argument('--json', action='store_true', help='machine-readable output')
    parser.add_argument('--summary', action='store_true', help='print only totals per rule')
    args = parser.parse_args(argv)

    paths = args.paths or [os.path.join(EXT_ROOT, 'NOSA.tab'), os.path.join(EXT_ROOT, 'lib')]
    findings = []
    for target in iter_targets(paths, args.include_hidden):
        findings.extend(lint_target(target))
    findings = [f for f in findings if SEV_RANK[f.severity] <= SEV_RANK[args.min_severity]]
    findings.sort(key=lambda f: (SEV_RANK[f.severity], rel(f.path), f.line))

    if args.json:
        print(json.dumps([f.as_dict() for f in findings], indent=2, ensure_ascii=False))
    elif args.summary:
        counts = {}
        for f in findings:
            counts[f.rule] = counts.get(f.rule, 0) + 1
        for rule in sorted(counts, key=lambda r: (SEV_RANK[RULES[r][0]], r)):
            print('%-8s %-8s %5d  %s' % (rule, RULES[rule][0], counts[rule], RULES[rule][1]))
        print('total: %d' % len(findings))
    else:
        for f in findings:
            print(f)
        if findings:
            print('\n%d finding(s)' % len(findings))

    if args.fail_on != 'never':
        limit = SEV_RANK[args.fail_on]
        if any(SEV_RANK[f.severity] <= limit for f in findings):
            return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
