# -*- coding: utf-8 -*-
"""joint_apply_probe.py with R1 applied past crossing beam bars: the shift's own mechanics checked (point 3.2 test only)."""
import os

CROSSING = False
execfile(os.path.join(EXT_ROOT, 'tools', 'revit_harness', 'joint_apply_probe.py'), globals())
