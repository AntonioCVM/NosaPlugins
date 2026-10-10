# -*- coding: utf-8 -*-
"""
nosa_utils.couplers — mechanical couplers (T8.52, IStructE SMDSC 5.5), no Revit: where the bars of a congested
column join end to end instead of lapping, and the 'E' written just before the mark of a bar with a special end
preparation, on the drawings and the schedules.
"""
from __future__ import absolute_import, division, print_function, unicode_literals

JOINT_ABOVE_SLAB_MM = 500.0       # coupled joint above the kicker: clear of the slab bars, easy to make
END_PREP = u'E'
FAMILY = u'NOSA Rebar Coupler'
SIZES_MM = (10, 12, 16, 20, 25, 32, 40)


def type_name(dia_mm):
    """The NOSA Rebar Coupler type for a bar size ('H20'), or None for a size it does not come in."""
    d = int(round(dia_mm))
    return u'H{}'.format(d) if d in SIZES_MM else None


def mark_with_end_prep(mark, prepared):
    """SMDSC 5.5: 'E' just before the mark of a bar with a coupler; the plain mark otherwise."""
    mark = (mark or u'').strip()
    if prepared and mark and not mark.startswith(END_PREP):
        return END_PREP + mark
    if not prepared and mark.startswith(END_PREP):
        return mark[len(END_PREP):]
    return mark


def joints_mm(slab_tops_mm, kicker_mm=0.0, above_mm=JOINT_ABOVE_SLAB_MM):
    """Elevations of the coupled joints of a column, one above each slab top it crosses."""
    return [z + kicker_mm + above_mm for z in slab_tops_mm]


def has_coupler(rebar):
    """A bar (set) with a Revit Rebar Coupler at either end: its mark takes the 'E' (Revit, read-only)."""
    from Autodesk.Revit import DB
    for end in (0, 1):
        try:
            cid = rebar.GetCouplerId(end)
        except Exception:
            return False
        if cid is not None and cid != DB.ElementId.InvalidElementId:
            return True
    return False


def schedule_mark(rebar, mark):
    """The Schedule Mark a bar shows on its tags and bar schedule: its mark, after 'E' when it is coupled."""
    try:
        coupled = has_coupler(rebar)
    except Exception:
        coupled = False
    return mark_with_end_prep(mark, coupled)
