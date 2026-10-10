# -*- coding: utf-8 -*-
"""
NOSA.RebarAutomate — welded fabric to BS 4483 on a floor (T8.51, IStructE SMDSC 4.2.5 / 5.4.6), the rules in
nosa_utils.fabric: the designated sheet types (4.8 x 2.4 m, their wires) made on first use, one Fabric Area over
the floor in its bottom or top face with the main wires along X or Y and the laps of SMDSC 5.4.6 / Table 5.8.
In a transaction.
"""
from Autodesk.Revit import DB
from Autodesk.Revit.DB import Structure as DBS

from nosa_utils import fabric
from nosa_utils.revit_helpers import element_name

_MM_PER_FT = 304.8


def _ft(mm):
    return mm / _MM_PER_FT


def _wire_type(doc, dia_mm):
    name = u'{:g} mm'.format(dia_mm)
    for w in DB.FilteredElementCollector(doc).OfClass(DBS.FabricWireType):
        if element_name(w) == name:
            return w.Id
    wid = DBS.FabricWireType.CreateDefaultFabricWireType(doc)
    wire = doc.GetElement(wid)
    wire.Name = name
    wire.WireDiameter = _ft(dia_mm)
    return wid


def sheet_type(doc, ref):
    """The BS 4483 sheet type `ref` (e.g. 'A193'): main (major) wires along the 4.8 m sheet, made on first use."""
    for t in DB.FilteredElementCollector(doc).OfClass(DBS.FabricSheetType):
        if element_name(t) == ref:
            return t.Id
    main, mp, cross, cp = fabric.FABRICS[ref]
    sid = DBS.FabricSheetType.CreateDefaultFabricSheetType(doc)
    st = doc.GetElement(sid)
    st.Name = ref
    st.MajorDirectionWireType = _wire_type(doc, main)
    st.MinorDirectionWireType = _wire_type(doc, cross)
    # main wires spread across the 2.4 m width, cross wires along the 4.8 m length; half a pitch over at the edges
    st.SetMajorLayoutAsMaximumSpacing(_ft(fabric.SHEET_WIDTH_MM), _ft(mp / 2.0), _ft(mp / 2.0), _ft(mp))
    st.SetMinorLayoutAsMaximumSpacing(_ft(fabric.SHEET_LENGTH_MM), _ft(cp / 2.0), _ft(cp / 2.0), _ft(cp))
    try:
        st.SheetMass = fabric.sheet_mass_kg(ref)        # the schedule's mass (no material density on the type)
    except Exception:
        pass
    return sid


def _area_type(doc):
    found = DB.FilteredElementCollector(doc).OfClass(DBS.FabricAreaType).FirstElementId()
    return found if found != DB.ElementId.InvalidElementId else DBS.FabricAreaType.CreateDefaultFabricAreaType(doc)


def place(doc, floor, ref, face=u'bottom', main_along=u'x', fck_mpa=30.0):
    """
    One Fabric Area of `ref` over the floor (its own boundary and openings), in its bottom or top face, the main
    wires along X or Y, laps of SMDSC 5.4.6 (main: a tension lap, alpha3 = 1.0) and Table 5.8 (secondary).
    Returns (FabricArea, [notes]).
    """
    sid = sheet_type(doc, ref)
    direction = DB.XYZ.BasisX if main_along == u'x' else DB.XYZ.BasisY
    area = DBS.FabricArea.Create(doc, floor, direction, _area_type(doc), sid)
    area.FabricLocation = DBS.FabricLocation.TopOrExternal if face == u'top' else DBS.FabricLocation.BottomOrInternal
    main_lap, cross_lap = fabric.laps_mm(ref, fck_mpa, good_bond=face != u'top')
    area.MajorLapSpliceLength = _ft(main_lap)
    area.MinorLapSpliceLength = _ft(cross_lap)
    doc.Regenerate()
    n = area.GetFabricSheetElementIds().Count
    notes = [u'{} fabric, {} face, main wires along {}: {} sheet(s) of 4.8 x 2.4 m, laps {:.0f} main / {:.0f} '
             u'secondary (SMDSC 5.4.6, Table 5.8).'.format(ref, face, main_along.upper(), n, main_lap, cross_lap)]
    return area, notes


SCHEDULE_NAME = u'NOSA Fabric Schedule'
SCHEDULE_FIELDS = (u'Type', u'Host Mark', u'Cut Overall Length', u'Cut Overall Width', u'Sheet Mass', u'Count')


def ensure_schedule(doc):
    """
    The fabric schedule (SMDSC Table 4.3): one row per fabric type and size of sheet, its count and mass; made on
    first use. Returns the ViewSchedule.
    """
    for v in DB.FilteredElementCollector(doc).OfClass(DB.ViewSchedule):
        if element_name(v) == SCHEDULE_NAME:
            return v
    schedule = DB.ViewSchedule.CreateSchedule(doc, DB.ElementId(DB.BuiltInCategory.OST_FabricReinforcement))
    schedule.Name = SCHEDULE_NAME
    definition = schedule.Definition
    by_name = {}
    for sf in definition.GetSchedulableFields():
        by_name.setdefault(sf.GetName(doc), sf)
    added = {}
    for name in SCHEDULE_FIELDS:
        sf = by_name.get(name)
        if sf is not None:
            added[name] = definition.AddField(sf)
    for name in (u'Type', u'Cut Overall Length', u'Cut Overall Width'):
        if name in added:
            definition.AddSortGroupField(DB.ScheduleSortGroupField(added[name].FieldId))
    definition.IsItemized = False
    definition.ShowGrandTotal = True
    definition.ShowGrandTotalCount = True
    return schedule
