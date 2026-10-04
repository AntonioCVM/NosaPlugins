# -*- coding: utf-8 -*-
import os, sys

from Autodesk.Revit import DB

_lib = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', '..', 'lib'))
if _lib not in sys.path:
    sys.path.insert(0, _lib)

from nosa_utils.revit_helpers import get_id_value
from nosa_utils.telemetry import log_swallowed
from nosa_utils import unit_conversion as _uc10
_LOG = u'ModelHealthHub/cover_compliance'

_FT_TO_MM = _uc10.FT_TO_MM

_EC2_LIMITS = {
    u'XC1 (dry/permanently wet)':   20.0,
    u'XC2 (wet, rarely dry)':       25.0,
    u'XC3 (moderate humidity)':     25.0,
    u'XC4 (cyclic wet/dry)':        30.0,
    u'XD1 (moderate chloride)':     35.0,
    u'XD2 (wet chloride)':          40.0,
    u'XS1 (airborne salt)':         35.0,
    u'XS2 (submerged)':             40.0,
    u'XS3 (tidal/splash)':          45.0,
}


def ec2_exposure_classes():
    return list(_EC2_LIMITS.keys())


def min_cover_for_class(exposure_class):
    return _EC2_LIMITS.get(exposure_class, 25.0)


def _rebar_cover_mm(rebar_el):
    bip = getattr(DB.BuiltInParameter, 'COVER_TYPE_BOTTOM_COVER', None)
    if bip is None:
        bip = getattr(DB.BuiltInParameter, 'REBAR_ELEM_COVER_OF_CONCRETE_COVER', None)
    if bip is not None:
        p = rebar_el.get_Parameter(bip)
        if p is not None:
            return p.AsDouble() * _FT_TO_MM
    bip2 = getattr(DB.BuiltInParameter, 'COVER_TYPE_COVER', None)
    if bip2 is not None:
        p = rebar_el.get_Parameter(bip2)
        if p is not None:
            return p.AsDouble() * _FT_TO_MM
    return None


def _host_name(doc, rebar_el):
    try:
        host = rebar_el.Host
        if host is not None:
            return host.Name or u'Unknown'
    except Exception:
        log_swallowed(_LOG, u'_host_name')
    try:
        host_id = rebar_el.HostId
        host = doc.GetElement(host_id)
        if host is not None:
            return host.Name or u'Unknown'
    except Exception:
        log_swallowed(_LOG, u'_host_name#2')
    return u'Unknown'


def _host_category(doc, rebar_el):
    try:
        host = rebar_el.Host
        if host is not None and host.Category is not None:
            return host.Category.Name
    except Exception:
        log_swallowed(_LOG, u'_host_category')
    return u'Structural'


def collect_rebar(doc):
    try:
        rebar_class = DB.Structure.Rebar
    except AttributeError:
        try:
            from Autodesk.Revit.DB.Structure import Rebar as rebar_class
        except ImportError:
            return []

    return list(
        DB.FilteredElementCollector(doc)
        .OfClass(rebar_class)
        .ToElements()
    )


def analyse(doc, min_cover_mm):
    rebars = collect_rebar(doc)
    results = []
    for rb in rebars:
        try:
            cover = _rebar_cover_mm(rb)
            if cover is None:
                continue
            status = u'OK' if cover >= min_cover_mm else u'FAIL'
            results.append({
                'id':       get_id_value(rb.Id),
                'host':     _host_name(doc, rb),
                'category': _host_category(doc, rb),
                'cover_mm': round(cover, 1),
                'min_mm':   min_cover_mm,
                'status':   status,
                'element':  rb,
            })
        except Exception:
            log_swallowed(_LOG, u'analyse')
    return results


def summarise(results):
    total = len(results)
    fail  = sum(1 for r in results if r['status'] == u'FAIL')
    ok    = total - fail
    return total, ok, fail
