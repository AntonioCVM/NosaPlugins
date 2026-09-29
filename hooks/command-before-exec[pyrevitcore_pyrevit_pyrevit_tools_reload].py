# -*- coding: utf-8 -*-
"""Unregister every NOSA DMU before pyRevit tears down the IronPython session."""
import os
import sys

_ext_lib = os.path.abspath(
    os.path.join(os.path.dirname(__file__), '..', 'lib')
)
if _ext_lib not in sys.path:
    sys.path.insert(0, _ext_lib)

try:
    from nosa_utils.dmu_lifecycle import unregister_all
    unregister_all(__revit__.Application)  # noqa: F821
except Exception:
    pass
