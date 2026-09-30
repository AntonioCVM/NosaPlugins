# -*- coding: utf-8 -*-
"""Tests for nosa_lint rule NOSA011 (.Name read on a Revit type)."""
import os
import sys
import tempfile
import textwrap
import unittest

_TOOLS = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'tools'))
if _TOOLS not in sys.path:
    sys.path.insert(0, _TOOLS)

import nosa_lint  # noqa: E402


def _lines(src):
    fd, path = tempfile.mkstemp(suffix='.py')
    os.close(fd)
    try:
        with open(path, 'w') as f:
            f.write(textwrap.dedent(src))
        return sorted(f.line for f in nosa_lint.lint_python(path) if f.rule == 'NOSA011')
    finally:
        os.remove(path)


class TypeNameRuleTests(unittest.TestCase):

    def test_flags_type_from_get_type_id(self):
        self.assertEqual(_lines('''
            def f(doc, el):
                t = doc.GetElement(el.GetTypeId())
                return t.Name
        '''), [4])

    def test_flags_symbol_and_getattr(self):
        self.assertEqual(_lines('''
            def f(el):
                a = el.Symbol.Name
                b = getattr(el.Symbol, 'Name', None)
        '''), [3, 4])

    def test_flags_type_collector_loop(self):
        self.assertEqual(_lines('''
            def f(doc):
                syms = FilteredElementCollector(doc).OfClass(DB.FamilySymbol).ToElements()
                for s in syms:
                    print(s.Name)
                for t in FilteredElementCollector(doc).WhereElementIsElementType():
                    print(t.Name)
        '''), [5, 7])

    def test_ignores_instances_views_and_setters(self):
        self.assertEqual(_lines('''
            def f(doc, view, el, sym):
                a = view.Name
                b = el.Name
                c = el.Symbol.Family.Name
                sym.Name = u'new'
                for v in FilteredElementCollector(doc).OfClass(DB.View):
                    print(v.Name)
        '''), [])


if __name__ == '__main__':
    unittest.main()
