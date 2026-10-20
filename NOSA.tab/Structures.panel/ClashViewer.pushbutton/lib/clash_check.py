# -*- coding: utf-8 -*-
"""Indicative geometry re-check: do the two elements of a clash still intersect in the model?"""
import re
from Autodesk.Revit import DB

from nosa_utils.telemetry import log_swallowed

_LOG = u'ClashViewer.check'
STILL, CLEARED, UNKNOWN = u'still', u'cleared', u'unknown'
_MM_PER_FT = 304.8
_MIN_OVERLAP_MM3 = 1000.0            # 1 cm3: below this the boolean result is treated as touching


class CheckResult(object):
    def __init__(self, verdict, text, overlap_cm3=0.0):
        self.verdict = verdict
        self.text = text
        self.overlap_cm3 = overlap_cm3


def tolerance_mm(test_tolerance):
    """'1mm' / '5 mm' -> 1.0 / 5.0 (1.0 when unreadable)."""
    m = re.search(r'(\d+(?:[.,]\d+)?)', test_tolerance or u'')
    return float(m.group(1).replace(u',', u'.')) if m else 1.0


def _apart(box_a, box_b, tol_ft):
    for axis in ('X', 'Y', 'Z'):
        if getattr(box_a[1], axis) < getattr(box_b[0], axis) - tol_ft:
            return True
        if getattr(box_b[1], axis) < getattr(box_a[0], axis) - tol_ft:
            return True
    return False


def recheck(located, tolerance):
    """Verdict for a LocatedClash: STILL, CLEARED or UNKNOWN (never CLEARED on a failed boolean)."""
    first, second = located.first, located.second
    if not (first.is_shown and second.is_shown):
        return CheckResult(UNKNOWN, u'Cannot check: %s.' % (
            first.text if not first.is_shown else second.text))
    tol_ft = (tolerance or 1.0) / _MM_PER_FT
    if first.bbox and second.bbox and _apart(first.bbox, second.bbox, tol_ft):
        return CheckResult(CLEARED, u'No longer clashing: the elements are apart.')
    try:
        s1, s2 = first.check_solid(), second.check_solid()
    except Exception:
        log_swallowed(_LOG, u'recheck.solids')
        return CheckResult(UNKNOWN, u'Cannot check: the geometry could not be read.')
    if s1 is None or s2 is None:
        return CheckResult(UNKNOWN, u'Cannot check: an element has no solid geometry '
                                    u'(an AutoCAD mesh cannot be intersected).')
    try:
        inter = DB.BooleanOperationsUtils.ExecuteBooleanOperation(
            s1, s2, DB.BooleanOperationsType.Intersect)
        volume_ft3 = inter.Volume if inter is not None else 0.0
    except Exception:
        log_swallowed(_LOG, u'recheck.boolean')
        return CheckResult(UNKNOWN, u'Cannot check: Revit could not intersect these shapes.')
    mm3 = max(volume_ft3, 0.0) * _MM_PER_FT ** 3
    if mm3 >= _MIN_OVERLAP_MM3:
        return CheckResult(STILL, u'Still clashing: overlap of about %.0f cm³.' % (mm3 / 1000.0), mm3 / 1000.0)
    return CheckResult(CLEARED, u'No longer clashing: no measurable overlap.')
