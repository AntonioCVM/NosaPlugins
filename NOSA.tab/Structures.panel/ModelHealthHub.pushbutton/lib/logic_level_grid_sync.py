# -*- coding: utf-8 -*-
"""Level & Grid Sync — compare host model vs. linked model."""
import sys, os
from Autodesk.Revit import DB
from nosa_utils import unit_conversion as _uc10
from nosa_utils.telemetry import log_swallowed
_LOG = u'ModelHealthHub/level_grid_sync'
_TOL_DEFAULT_MM = 1.0  # default elevation tolerance in mm
_MM_PER_FOOT    = _uc10.FT_TO_MM


def _ft_to_mm(ft):
    return ft * _MM_PER_FOOT


def get_linked_models(doc):
    """Return list of (RevitLinkInstance, display_title) tuples — includes unloaded links."""
    links = []
    col = (DB.FilteredElementCollector(doc)
           .OfClass(DB.RevitLinkInstance)
           .ToElements())
    for link in col:
        try:
            link_doc = link.GetLinkDocument()
            if link_doc is not None:
                title = link_doc.Title or link.Name
            else:
                title = u'{} (not loaded)'.format(link.Name or u'Link')
            links.append((link, title))
        except Exception:
            log_swallowed(_LOG, u'get_linked_models')
    links.sort(key=lambda x: x[1].lower())
    return links


def _collect_levels(doc):
    """Return dict name_lower → elevation_mm."""
    result = {}
    col = (DB.FilteredElementCollector(doc)
           .OfClass(DB.Level)
           .ToElements())
    for lvl in col:
        try:
            result[lvl.Name.strip().lower()] = (_ft_to_mm(lvl.Elevation), lvl.Name)
        except Exception:
            log_swallowed(_LOG, u'_collect_levels')
    return result


def _collect_grids(doc):
    """Return dict name_lower → (name, position_mm) where position is the X or Y midpoint."""
    result = {}
    col = (DB.FilteredElementCollector(doc)
           .OfClass(DB.Grid)
           .ToElements())
    for g in col:
        try:
            curve = g.Curve
            mid   = curve.Evaluate(0.5, True)
            pos   = _ft_to_mm((mid.X + mid.Y) / 2.0)  # simplified midpoint signature
            result[g.Name.strip().lower()] = (g.Name, pos)
        except Exception:
            log_swallowed(_LOG, u'_collect_grids')
    return result


class SyncReport(object):
    def __init__(self):
        self.level_elevation_mismatches = []   # (name, host_mm, link_mm, delta_mm)
        self.levels_only_in_host        = []   # name
        self.levels_only_in_link        = []   # name
        self.grids_only_in_host         = []   # name
        self.grids_only_in_link         = []   # name
        self.link_title                 = ''

    @property
    def has_issues(self):
        return any([
            self.level_elevation_mismatches,
            self.levels_only_in_host,
            self.levels_only_in_link,
            self.grids_only_in_host,
            self.grids_only_in_link,
        ])

    @property
    def issue_count(self):
        return (len(self.level_elevation_mismatches) +
                len(self.levels_only_in_host) +
                len(self.levels_only_in_link) +
                len(self.grids_only_in_host) +
                len(self.grids_only_in_link))


def compare(doc, link_doc, tolerance_mm=_TOL_DEFAULT_MM):
    """
    Compare levels and grids between host doc and link_doc.
    Returns a SyncReport.
    """
    report = SyncReport()
    report.link_title = link_doc.Title

    host_levels = _collect_levels(doc)
    link_levels = _collect_levels(link_doc)

    host_grids  = _collect_grids(doc)
    link_grids  = _collect_grids(link_doc)

    # Levels: elevation mismatch
    for name_lo, (host_elev, display_name) in host_levels.items():
        if name_lo in link_levels:
            link_elev = link_levels[name_lo][0]
            delta = abs(host_elev - link_elev)
            if delta > tolerance_mm:
                report.level_elevation_mismatches.append(
                    (display_name, host_elev, link_elev, delta)
                )

    # Levels only in host / only in link
    host_level_names = set(host_levels.keys())
    link_level_names = set(link_levels.keys())
    report.levels_only_in_host = [host_levels[k][1] for k in (host_level_names - link_level_names)]
    report.levels_only_in_link = [link_levels[k][1] for k in (link_level_names - host_level_names)]

    # Grids only in host / only in link
    host_grid_names = set(host_grids.keys())
    link_grid_names = set(link_grids.keys())
    report.grids_only_in_host = [host_grids[k][0] for k in (host_grid_names - link_grid_names)]
    report.grids_only_in_link = [link_grids[k][0] for k in (link_grid_names - host_grid_names)]

    return report
