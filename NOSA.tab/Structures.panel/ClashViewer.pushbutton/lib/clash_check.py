# -*- coding: utf-8 -*-
"""Indicative geometry re-check: do the two elements of a clash still intersect in the model?"""
import re
from Autodesk.Revit import DB

from nosa_utils import solids as _solids
from nosa_utils.telemetry import log_swallowed

_LOG = u'ClashViewer.check'
STILL, CLEARED, UNKNOWN, JOINED = u'still', u'cleared', u'unknown', u'joined'
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
    joined = _joined_overlap_mm3(first, second)
    if joined is not None:
        if joined >= _MIN_OVERLAP_MM3:
            return CheckResult(JOINED, u'Joined in Revit (Join Geometry): the overlap is cut away. Without the join the '
                                       u'elements overlap by about %.0f cm³, so Navisworks still reports it.'
                               % (joined / 1000.0), joined / 1000.0)
        return CheckResult(CLEARED, u'No longer clashing: no measurable overlap.')
    return CheckResult(CLEARED, u'No longer clashing: no measurable overlap.')


def _joined_overlap_mm3(first, second):
    """Overlap (mm3) the two host elements would have without Join Geometry; None when they are not joined."""
    if first.model is None or second.model is None or first.model.is_link or second.model.is_link:
        return None
    e1, e2 = first.element, second.element
    if e1 is None or e2 is None:
        return None
    doc = e1.Document
    try:
        if not DB.JoinGeometryUtils.AreElementsJoined(doc, e1, e2):
            return None
    except Exception:
        log_swallowed(_LOG, u'joined.test')
        return None
    volume = 0.0
    t = DB.Transaction(doc, u'NOSA — Clash Viewer: check joined geometry')
    try:
        t.Start()
        DB.JoinGeometryUtils.UnjoinGeometry(doc, e1, e2)
        doc.Regenerate()
        a, b = _solids.get_element_solid(e1), _solids.get_element_solid(e2)
        if a is not None and b is not None:
            inter = DB.BooleanOperationsUtils.ExecuteBooleanOperation(a, b, DB.BooleanOperationsType.Intersect)
            volume = inter.Volume if inter is not None else 0.0
    except Exception:
        log_swallowed(_LOG, u'joined.unjoin')
        volume = _MIN_OVERLAP_MM3 / _MM_PER_FT ** 3      # joined, overlap unknown: do not call it cleared
    finally:
        try:
            if t.HasStarted():
                t.RollBack()
        except Exception:
            log_swallowed(_LOG, u'joined.rollback')
    return max(volume, 0.0) * _MM_PER_FT ** 3
