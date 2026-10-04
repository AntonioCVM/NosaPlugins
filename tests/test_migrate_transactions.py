# -*- coding: utf-8 -*-
"""T8.1 migration: transactions wrapped without breaking calls, strings or imports."""
import ast
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'tools'))

import migrate_transactions as mt  # noqa: E402


def test_db_transaction_is_wrapped_with_nested_calls_and_strings():
    src = u"with DB.Transaction(doc, u'NOSA — ({})'.format(name)) as t:\n    t.Start()\n"
    out, n = mt.migrate_text(src)
    assert n == 1
    assert out.startswith(u"with nosa_tx.guard(DB.Transaction(doc, u'NOSA — ({})'.format(name))) as t:")
    ast.parse(out)


def test_pyrevit_transaction_is_replaced():
    out, n = mt.migrate_text(u"with revit.Transaction(u'NOSA — X'):\n    pass\n")
    assert n == 1 and u'nosa_tx.revit_transaction(' in out


def test_transactions_with_their_own_preprocessor_are_left_alone():
    src = (u"t = DB.Transaction(doc, u'x')\n"
           u"options = t.GetFailureHandlingOptions()\n"
           u"options.SetFailuresPreprocessor(guard)\n")
    out, n = mt.migrate_text(src)
    assert n == 0 and out == src


def test_import_goes_after_the_sys_path_setup():
    src = (u"# -*- coding: utf-8 -*-\nimport os, sys\n_lib = 'x'\nif _lib not in sys.path:\n"
           u"    sys.path.insert(0, _lib)\nfrom nosa_utils import y\n\ndef f():\n    pass\n")
    out = mt.insert_import(src)
    lines = out.splitlines()
    assert lines.index(mt.IMPORT.strip()) == lines.index(u'from nosa_utils import y') + 1
    ast.parse(out)
