# -*- coding: utf-8 -*-
"""joint_apply_probe.py with nothing applied: the same building's QA before the R1 shifts (point 3.2)."""
import os

APPLY = False
execfile(os.path.join(EXT_ROOT, 'tools', 'revit_harness', 'joint_apply_probe.py'), globals())
