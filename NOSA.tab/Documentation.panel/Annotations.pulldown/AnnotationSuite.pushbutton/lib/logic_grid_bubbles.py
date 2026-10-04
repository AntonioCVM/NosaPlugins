# -*- coding: utf-8 -*-
import os
import sys

from Autodesk.Revit import DB

_lib = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', '..', 'lib'))
if _lib not in sys.path:
    sys.path.insert(0, _lib)
from nosa_utils.telemetry import log_swallowed
_LOG = u'annotationsuite.logic_grid_bubbles'


def _grid_cat():
    return DB.BuiltInCategory.OST_Grids


def get_plan_views(doc):
    views = []
    for v in DB.FilteredElementCollector(doc).OfClass(DB.View).ToElements():
        try:
            if isinstance(v, DB.ViewPlan) and not v.IsTemplate:
                views.append(v)
        except Exception:
            log_swallowed(_LOG, u'get_plan_views')
    return sorted(views, key=lambda x: x.Name or u'')


def get_all_grids(doc):
    return list(DB.FilteredElementCollector(doc)
                .OfCategory(_grid_cat())
                .WhereElementIsNotElementType()
                .ToElements())


def _set_bubble(grid, end, view, visible):
    try:
        if visible:
            grid.ShowBubbleInView(end, view)
        else:
            grid.HideBubbleInView(end, view)
        return True
    except Exception:
        return False


def _grid_visible_in_view(grid, view):
    try:
        return not grid.IsHidden(view)
    except Exception:
        return True


def apply_bubble_action(doc, views, action, both_ends=True):
    """
    action: 'show' | 'hide' | 'standardise'
    Returns dict with updated/failed/skipped counts.
    """
    grids = get_all_grids(doc)
    updated = failed = skipped = 0
    ends = [DB.DatumEnds.End0, DB.DatumEnds.End1] if both_ends else [DB.DatumEnds.End0]

    with nosa_tx.guard(DB.Transaction(doc, u'NOSA — Grid Bubble Batch')) as t:
        t.Start()
        for view in views:
            for grid in grids:
                if not _grid_visible_in_view(grid, view):
                    skipped += 1
                    continue
                for end in ends:
                    try:
                        if action == 'show':
                            ok = _set_bubble(grid, end, view, True)
                        elif action == 'hide':
                            ok = _set_bubble(grid, end, view, False)
                        else:
                            ok = _set_bubble(grid, end, view, True)
                        if ok:
                            updated += 1
                        else:
                            failed += 1
                    except Exception:
                        failed += 1
        t.Commit()

    return {'updated': updated, 'failed': failed, 'skipped': skipped, 'views': len(views)}
