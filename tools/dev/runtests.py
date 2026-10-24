# -*- coding: utf-8 -*-
"""Run every tests/test_*.py of the current folder in ONE process (the files share Revit stubs)."""
import glob
import os
import runpy
import sys
import traceback

ok = fail = 0
here = os.getcwd()
sys.path.insert(0, os.path.join(here, 'tests'))
for path in sorted(glob.glob(os.path.join(here, 'tests', 'test_*.py'))):
    name = os.path.basename(path)
    try:
        ns = runpy.run_path(path, run_name='nosa_test_module')
    except Exception:
        traceback.print_exc()
        print('IMPORT FAIL', name)
        fail += 1
        continue
    tests = [k for k, v in ns.items() if k.startswith('test_') and callable(v)]
    if not tests:
        ok += 1
        continue
    for k in sorted(tests):
        try:
            ns[k]()
            ok += 1
        except Exception:
            traceback.print_exc()
            print('FAIL', name, k)
            fail += 1
print('ok', ok, 'fail', fail)
