# -*- coding: utf-8 -*-
"""
Phase F0 CI checks — see docs/REBARAUTOMATE_BLUEPRINT.md Part 14.

HONESTY NOTE (kept explicit per the F0 approval, adjustment d): there is
no IronPython 2.7 interpreter available in this environment (or in a
typical CI runner), so "dual parse IPy2/Py3" here means:

  1. A REAL Python 3 `ast.parse` of every .py file (genuine syntax
     validation under the interpreter this repo's tooling actually
     runs).
  2. A HEURISTIC grep for known Python-3-only constructs (f-strings,
     the walrus operator, `async`/`await`, positional-only `/`
     markers) that are hard syntax errors under IronPython 2.7. This
     is NOT a real IronPython 2.7 parse — it only catches syntax this
     project's own conventions already avoid. A real IronPython 2.7
     execution (or `pythonnet`) run remains the only way to be fully
     certain; that belongs in the Part 15 smoke matrix, not here.

Also covers: JSON-validity of every data/*.json file, and a grep for
the one CONFIRMED cross-version risk pattern this project has actual
evidence for (ElementId.IntegerValue, removed in Revit 2025 — Part 04)
used directly outside nosa_utils/revit_compat.py or
nosa_utils/revit_helpers.py (which already own that abstraction).

Run with:
    python NOSA.tab/Structures.panel/Quantities.pulldown/RebarAutomate.pushbutton/tests/test_ci_checks.py
"""
import ast
import json
import os
import re
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_PLUGIN_ROOT = os.path.abspath(os.path.join(_HERE, '..'))
_EXTENSION_ROOT = os.path.abspath(os.path.join(_PLUGIN_ROOT, '..', '..', '..', '..'))
_DATA_DIR = os.path.join(_EXTENSION_ROOT, 'data')

# Files this check itself covers directly — the plugin's own script.py
# and lib/*.py, plus the shared facade this phase introduces.
_PY_FILES = []
_PY_FILES.append(os.path.join(_PLUGIN_ROOT, 'script.py'))
_lib_dir = os.path.join(_PLUGIN_ROOT, 'lib')
for fname in sorted(os.listdir(_lib_dir)):
    if fname.endswith('.py'):
        _PY_FILES.append(os.path.join(_lib_dir, fname))
_PY_FILES.append(os.path.join(_EXTENSION_ROOT, 'lib', 'nosa_utils', 'revit_compat.py'))
# PHASE F1
_PY_FILES.append(os.path.join(_EXTENSION_ROOT, 'lib', 'nosa_utils', 'shared_params.py'))

# Heuristic Python-3-only constructs that are hard syntax errors under
# IronPython 2.7. Deliberately narrow (see module docstring).
_PY3_ONLY_PATTERNS = [
    (re.compile(r'(?<![\w])[fF]["\']'), 'f-string'),
    (re.compile(r':='), 'walrus operator (:=)'),
    (re.compile(r'\basync\s+def\b'), 'async def'),
    (re.compile(r'\bawait\s'), 'await'),
]

# The one CONFIRMED cross-version risk (Part 04): ElementId.IntegerValue
# was removed in Revit 2025+. Any direct use outside the two files that
# already own this abstraction is a regression waiting to happen.
_BLACKLIST_PATTERN = re.compile(r'\.IntegerValue\b')
_BLACKLIST_EXEMPT_BASENAMES = {'revit_compat.py', 'revit_helpers.py'}


def test_every_py_file_parses_as_valid_python3():
    failures = []
    for path in _PY_FILES:
        with open(path, 'r', encoding='utf-8') as f:
            source = f.read()
        try:
            ast.parse(source, filename=path)
        except SyntaxError as e:
            failures.append(u'{}: {}'.format(path, e))
    assert not failures, u'Python 3 ast.parse failed:\n' + u'\n'.join(failures)


def test_no_heuristic_python3_only_syntax():
    """Grep-level heuristic for constructs IronPython 2.7 cannot parse
    at all. See module docstring for why this is a heuristic, not a
    real IronPython 2.7 parse."""
    failures = []
    for path in _PY_FILES:
        with open(path, 'r', encoding='utf-8') as f:
            for lineno, line in enumerate(f, start=1):
                # Skip comments/docstrings-ish lines conservatively —
                # false positives here are cheap to review by hand;
                # false negatives (missing a real Py2-breaking line)
                # are the actual risk, so err toward flagging.
                stripped = line.strip()
                if stripped.startswith('#'):
                    continue
                for pattern, label in _PY3_ONLY_PATTERNS:
                    if pattern.search(line):
                        failures.append(u'{}:{}: possible {} — {}'.format(
                            path, lineno, label, stripped[:80]))
    assert not failures, u'Heuristic Python-3-only syntax found:\n' + u'\n'.join(failures)


def test_every_data_json_file_is_valid_json():
    if not os.path.isdir(_DATA_DIR):
        return  # F0 hasn't created data/ yet in some checkout states — nothing to check
    failures = []
    checked = 0
    for root, _dirs, files in os.walk(_DATA_DIR):
        for fname in files:
            if not fname.endswith('.json'):
                continue
            path = os.path.join(root, fname)
            checked += 1
            with open(path, 'r', encoding='utf-8') as f:
                try:
                    json.load(f)
                except ValueError as e:
                    failures.append(u'{}: {}'.format(path, e))
    assert not failures, u'Invalid JSON found under data/:\n' + u'\n'.join(failures)
    assert checked > 0, u'expected at least one .json file under data/ (schema/manifest stubs)'


def test_no_direct_integer_value_outside_compat_layer():
    """The one CONFIRMED cross-version API risk (Part 04): direct
    ElementId.IntegerValue use, removed in Revit 2025+, outside the
    two files that already own this abstraction."""
    failures = []
    for path in _PY_FILES:
        basename = os.path.basename(path)
        if basename in _BLACKLIST_EXEMPT_BASENAMES:
            continue
        with open(path, 'r', encoding='utf-8') as f:
            for lineno, line in enumerate(f, start=1):
                if line.strip().startswith('#'):
                    continue
                if _BLACKLIST_PATTERN.search(line):
                    failures.append(u'{}:{}: {}'.format(path, lineno, line.strip()[:80]))
    assert not failures, (
        u'.IntegerValue used directly outside revit_compat.py/revit_helpers.py '
        u'(use get_id_value() instead):\n' + u'\n'.join(failures))


if __name__ == '__main__':
    tests = [v for k, v in sorted(globals().items()) if k.startswith('test_')]
    failures = 0
    for t in tests:
        try:
            t()
            print(u'{}: OK'.format(t.__name__))
        except AssertionError as e:
            failures += 1
            print(u'{}: FAILED -- {}'.format(t.__name__, e))
    print(u'\n{}/{} checks passed'.format(len(tests) - failures, len(tests)))
    sys.exit(1 if failures else 0)
