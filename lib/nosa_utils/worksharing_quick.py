# -*- coding: utf-8 -*-
"""Tiny worksharing probes — avoids hard dependency failures on non-workshared docs."""

from Autodesk.Revit import DB


def element_workset_is_open(doc, el):
    """True if element workset is open, or probe fails (assume editable)."""
    try:
        if doc is None or el is None:
            return True
        if hasattr(doc, 'IsWorkshared') and not doc.IsWorkshared:
            return True
        wt = doc.GetWorksetTable()
        ws = wt.GetWorkset(el.WorksetId)
        if ws is None:
            return True
        return bool(ws.IsOpen)
    except Exception:
        return True
