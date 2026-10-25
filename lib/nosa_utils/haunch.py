# -*- coding: utf-8 -*-
"""
T8.58 (2026-10-25): links of a haunched beam, no Revit. Under a haunch each link reaches down to the soffit at its
own position, so the links there differ one from the next; the runs of equal depth still make one set.
"""

STEP_MM = 5.0       # soffit drops are rounded to this; smaller ones are taken as none


def depth_runs(positions, drops_mm):
    """Link positions split into runs of one soffit drop (mm, 0 = the beam's own depth): [(positions, drop)]."""
    runs = []
    for d, drop in zip(positions, drops_mm):
        drop = round(drop / STEP_MM) * STEP_MM if drop >= STEP_MM else 0.0
        if runs and runs[-1][1] == drop:
            runs[-1][0].append(d)
        else:
            runs.append(([d], drop))
    return runs
