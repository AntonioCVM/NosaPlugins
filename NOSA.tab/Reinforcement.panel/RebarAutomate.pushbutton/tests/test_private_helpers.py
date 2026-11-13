# -*- coding: utf-8 -*-
"""Every private helper a module calls (_name(...)) is defined in it: a helper deleted by mistake fails here."""
from __future__ import absolute_import, division, print_function, unicode_literals
import io
import os
import re

_LIB = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'lib'))
_CALL = re.compile(r'(?<![\w.])(_[a-z]\w*)\(')


def _undefined_names_defined(path):
    code = io.open(path, encoding='utf-8').read()
    return re.findall(r'(?m)^(?:def|class)\s+(_\w+)', code) + re.findall(r'(?m)^(_\w+)\s*=', code)


def _undefined(path):
    src = io.open(path, encoding='utf-8').read()
    code = re.sub(r'(?s)("""|\'\'\').*?\1', '', src)
    code = re.sub(r'#[^\n]*', '', code)
    defined = set(re.findall(r'(?m)^\s*(?:def|class)\s+(_\w+)', code))
    defined |= set(re.findall(r'(?m)^\s*(_\w+)\s*=', code))
    defined |= set(re.findall(r'import\s+[\w.]+\s+as\s+(_\w+)', code))
    defined |= set(re.findall(r'(?m)^\s*from\s+[\w.]+\s+import\s+.*?\b(_\w+)', code))
    defined |= set(re.findall(r'(?m)^\s*for\s+(_\w+)', code))
    defined |= set(re.findall(r'lambda[^:]*\b(_\w+)', code))
    defined |= set(re.findall(r'(?m)(?:def\s+\w+\(|,)\s*(_\w+)\s*[,=)]', code))
    return sorted(set(_CALL.findall(code)) - defined)


def test_no_undefined_private_helpers():
    # the tab_* mixins are handed ui.py's names by bind()
    shared = set(_undefined_names_defined(os.path.join(_LIB, 'ui.py')))
    bad = {}
    for name in sorted(os.listdir(_LIB)):
        if name.endswith('.py'):
            missing = _undefined(os.path.join(_LIB, name))
            if name.startswith('tab_'):
                missing = [m for m in missing if m not in shared]
            if missing:
                bad[name] = missing
    assert not bad, bad


if __name__ == '__main__':
    test_no_undefined_private_helpers()
    print('test_private_helpers: OK')
