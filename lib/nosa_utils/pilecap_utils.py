# -*- coding: utf-8 -*-
"""Helpers shared by the pile tools (PileMaster, AddPileToPilecap, CreatePilecapType)."""
import math


# ── 2D polygon helpers (polygon = list of (x, y), any consistent unit) ────────

def point_in_polygon(x, y, polygon):
    """Even-odd ray cast; points exactly on the outline are not guaranteed either way."""
    n = len(polygon)
    if n < 3:
        return False
    inside = False
    j = n - 1
    for i in range(n):
        xi, yi = polygon[i]
        xj, yj = polygon[j]
        if ((yi > y) != (yj > y)) and \
           (x < (xj - xi) * (y - yi) / (yj - yi) + xi):
            inside = not inside
        j = i
    return inside


def distance_to_segment(px, py, ax, ay, bx, by):
    dx, dy = bx - ax, by - ay
    seg2 = dx * dx + dy * dy
    if seg2 <= 0.0:
        return math.sqrt((px - ax) ** 2 + (py - ay) ** 2)
    t = ((px - ax) * dx + (py - ay) * dy) / seg2
    t = max(0.0, min(1.0, t))
    qx, qy = ax + t * dx, ay + t * dy
    return math.sqrt((px - qx) ** 2 + (py - qy) ** 2)


def distance_to_polygon_edge(x, y, polygon):
    """Shortest distance from (x, y) to the closed polygon outline; inf if < 2 points."""
    n = len(polygon)
    if n < 2:
        return float('inf')
    return min(distance_to_segment(x, y,
                                   polygon[i][0], polygon[i][1],
                                   polygon[(i + 1) % n][0], polygon[(i + 1) % n][1])
               for i in range(n))


# ── Model Group round-trip (edit grouped piles/caps in one Transaction) ──────

def ungroup_targets(doc, elements, output=None):
    """Ungroup every Model Group containing *elements*; returns restore data for regroup_restore.

    Must be called inside an open Transaction.
    """
    from Autodesk.Revit import DB
    from nosa_utils.revit_helpers import get_id_value

    seen = set()
    restore = []
    invalid = DB.ElementId.InvalidElementId
    for el in elements:
        gid = el.GroupId
        if gid == invalid:
            continue
        gid_val = get_id_value(gid)
        if gid_val in seen:
            continue
        seen.add(gid_val)
        grp = doc.GetElement(gid)
        if grp is None:
            continue
        try:
            member_ids = list(grp.GetMemberIds())
            grp_type_id = grp.GetTypeId()
            grp.UngroupMembers()
            restore.append((grp_type_id, member_ids))
            if output:
                output.print_md(u'  - Ungrouped: {} members'.format(len(member_ids)))
        except Exception as e:
            if output:
                output.print_md(u'  - WARNING: could not ungroup group {}: {}'.format(gid_val, e))
    return restore


def regroup_restore(doc, restore_data, output=None):
    """Recreate the groups removed by ungroup_targets, inside the same Transaction; returns count."""
    from Autodesk.Revit import DB
    from System.Collections.Generic import List

    n = 0
    for _grp_type_id, member_ids in restore_data:
        try:
            doc.Create.NewGroup(List[DB.ElementId](member_ids))
            n += 1
        except Exception as e:
            if output:
                output.print_md(u'  - WARNING: could not regroup: {}'.format(e))
    if output and n:
        output.print_md(u'  - Regrouped: {} group(s) restored'.format(n))
    return n
