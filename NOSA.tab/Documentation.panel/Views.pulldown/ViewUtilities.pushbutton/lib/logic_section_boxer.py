# -*- coding: utf-8 -*-
# Extracted from the original SectionBoxer.pushbutton/script.py (which had no
# lib/ folder — all logic was inline in script.py) as part of the
# ViewUtilities hub consolidation. The Revit API calls, prompts and messages
# below are copied verbatim from that script; only the outer function
# wrapper (create_section_box) and the (doc, uidoc) parameters are new, so
# the hub's "Section Boxer" quick-action button can call straight into it
# instead of running a standalone script.
import os
import sys

_lib = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', '..', 'lib'))
if _lib not in sys.path:
    sys.path.insert(0, _lib)

from nosa_utils import unit_conversion as _uc10

from Autodesk.Revit import DB
from pyrevit import forms


def _get_offset_ft():
    try:
        val = forms.ask_for_string(
            prompt=u'Section box offset (mm):',
            default='500',
            title=u'Section Boxer'
        )
        if val is None:
            return None
        return float(val) * _uc10.MM_TO_FT
    except Exception:
        return None


def _union_bbox(elements, view=None):
    mins = []
    maxs = []
    for el in elements:
        try:
            bb = el.get_BoundingBox(view)
            if bb:
                mins.append(bb.Min)
                maxs.append(bb.Max)
        except Exception:
            pass
    if not mins:
        return None
    min_x = min(p.X for p in mins)
    min_y = min(p.Y for p in mins)
    min_z = min(p.Z for p in mins)
    max_x = max(p.X for p in maxs)
    max_y = max(p.Y for p in maxs)
    max_z = max(p.Z for p in maxs)
    bb = DB.BoundingBoxXYZ()
    bb.Min = DB.XYZ(min_x, min_y, min_z)
    bb.Max = DB.XYZ(max_x, max_y, max_z)
    return bb


def create_section_box(doc, uidoc):
    """
    Create a 3D section box around the current selection with a
    user-supplied offset, and activate that view. Ported unchanged from
    SectionBoxer.pushbutton/script.py.
    """
    sel_ids = list(uidoc.Selection.GetElementIds())
    if not sel_ids:
        forms.alert(u'Select elements first, then run Section Boxer.', title=u'Section Boxer')
        return

    offset = _get_offset_ft()
    if offset is None:
        return

    elements = [doc.GetElement(eid) for eid in sel_ids]
    bb = _union_bbox(elements)
    if bb is None:
        forms.alert(u'Could not compute bounding box for the selection.',
                    title=u'Section Boxer')
        return

    # Create a new 3D view
    view_types = DB.FilteredElementCollector(doc) \
                   .OfClass(DB.ViewFamilyType) \
                   .ToElements()
    vt_3d = next((vt for vt in view_types
                  if vt.ViewFamily == DB.ViewFamily.ThreeDimensional), None)

    if vt_3d is None:
        forms.alert(u'No 3D view type found in this project.', title=u'Section Boxer')
        return

    with DB.Transaction(doc, u'NOSA — Section Box') as t:
        t.Start()
        view3d = DB.View3D.CreateIsometric(doc, vt_3d.Id)
        view3d.Name = u'NOSA — Section Box {}'.format(
            ', '.join(doc.GetElement(eid).Name
                      for eid in sel_ids[:2]
                      if doc.GetElement(eid) is not None))[:60]

        exp_bb = DB.BoundingBoxXYZ()
        exp_bb.Min = DB.XYZ(bb.Min.X - offset, bb.Min.Y - offset, bb.Min.Z - offset)
        exp_bb.Max = DB.XYZ(bb.Max.X + offset, bb.Max.Y + offset, bb.Max.Z + offset)
        view3d.SetSectionBox(exp_bb)
        t.Commit()

    uidoc.ActiveView = view3d
    forms.alert(u'Section box created and view activated.',
                title=u'Section Boxer', warn_icon=False)
