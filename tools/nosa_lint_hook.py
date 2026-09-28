# -*- coding: utf-8 -*-
"""Claude Code PostToolUse hook: lint the edited .py/.xaml file with nosa_lint."""
from __future__ import print_function

import io
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import nosa_lint  # noqa: E402

BLOCKING = ('critical', 'high')


def main():
    try:
        payload = json.load(io.TextIOWrapper(sys.stdin.buffer, encoding='utf-8'))
    except Exception:
        return 0
    tool_input = payload.get('tool_input') or {}
    tool_response = payload.get('tool_response') or {}
    path = tool_input.get('file_path') or tool_response.get('filePath')
    if not path or not path.endswith(('.py', '.xaml')) or not os.path.isfile(path):
        return 0
    root = os.path.normcase(nosa_lint.EXT_ROOT)
    if not os.path.normcase(os.path.abspath(path)).startswith(root):
        return 0

    findings = [f for f in nosa_lint.lint_target(os.path.abspath(path)) if f.severity in BLOCKING]
    findings.sort(key=lambda f: f.line)
    if not findings:
        return 0
    lines = ['nosa_lint found %d blocking issue(s) in %s:' % (len(findings), nosa_lint.rel(path))]
    lines += ['  ' + str(f) for f in findings]
    lines.append('Fix them, or suppress a deliberate case with "# nosa-lint: disable=<RULE>" on that line.')
    sys.stderr.write('\n'.join(lines) + '\n')
    return 2


if __name__ == '__main__':
    sys.exit(main())
