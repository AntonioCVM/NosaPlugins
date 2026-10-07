# -*- coding: utf-8 -*-
"""
NOSA.RebarAutomate — legends on every reinforcement drawing (T8.31, T8.32).

IStructE SMDSC 4.2.1: the layer notation (T1/T2, B1/B2, N1/N2, F1/F2) illustrated by a sketch on
the drawings; SMDSC 3.7: notes with the GA references, abbreviations, concrete grade, covers and
schedule references, in panel B above the title block, working down from the top. One legend
view each, shared by every sheet, so the notes are edited in one place.
"""
from __future__ import absolute_import, division, print_function, unicode_literals

NOTATION_LEGEND = u'RC layer notation'
NOTES_LEGEND = u'RC reinforcement notes'
NOTATION_SCALE = 10
NOTES_SCALE = 1
NOTES_WIDTH_MM = 84.0
TEXT_TYPE = u'2.0mm Century gothic - Sheet notes'
LABEL_TYPE = u'2.0mm Century Gothic'
VIEWPORT_TYPE = u'NOSA Manual title /No scale'

# NOSA A1 QR titleblock, panel B: free strip right of the drawing area, above the revisions (mm)
PANEL_B = (740.0, 135.0, 834.0, 588.0)
PANEL_GAP_MM = 8.0

_FT = 304.8


def notes_text(concrete_grade, cover_typical, cover_slabs):
    """SMDSC 3.7 notes block from the project's general-notes values (NOSA_GN_*); unicode."""
    grade = concrete_grade or u'to the general notes'
    covers = u'{} typical'.format(cover_typical) if cover_typical else u'to the general notes'
    if cover_slabs:
        covers += u', {} slabs'.format(cover_slabs)
    lines = [
        u'REINFORCEMENT NOTES',
        u'',
        u'1. Read with the general arrangement drawings and the general notes (0900). '
        u'Do not scale from this drawing.',
        u'2. Concrete grade {} unless noted otherwise.'.format(grade),
        u'3. Reinforcement: high yield ribbed bars B500B to BS 4449, scheduled to BS 8666:2020. '
        u'Bar marks refer to the schedules listed above the title block.',
        u'4. Nominal cover to all reinforcement, links included: {}, unless noted otherwise.'.format(covers),
        u'5. Bar notation: number, type and size, mark, centres, layer, e.g. 20H16-63-150 B1. '
        u'Centres and layer are not given for beams and columns.',
        u'6. Layers: T top, B bottom, N near face, F far face; 1 outer layer, 2 second layer '
        u'(see the layer notation key). EF each face, EW each way, Stg. staggered, Alt. alternate.',
        u'7. Laps and anchorages to the table in the general notes (0900) unless dimensioned.',
    ]
    return u'\r'.join(lines)


def stack_in_panel(sizes, panel=PANEL_B, gap=PANEL_GAP_MM):
    """Centres (x, y) mm that stack boxes (w, h) right-aligned down panel B from its top."""
    x0, y0, x1, y1 = panel
    out, top = [], y1
    for w, h in sizes:
        out.append((x1 - w / 2.0, top - h / 2.0))
        top -= h + gap
    return out


# notation sketch, model mm at NOTATION_SCALE: (kind, data)
#   'rect' (x0, y0, x1, y1) | 'line' (x0, y, x1) | 'dots' (x0, y, x1, step) | 'text' (x, y, text)
_DOT_R = 8.0


def notation_sketch():
    """SMDSC 4.2.1 key: slab section with T1/T2/B1/B2, wall plan section with N1/N2/F1/F2."""
    items = [
        ('text', (0.0, 330.0, u'SLAB / BASE (SECTION)')),
        ('rect', (0.0, 0.0, 500.0, 250.0)),
        ('line', (30.0, 220.0, 470.0)), ('dots', (50.0, 180.0, 450.0, 50.0)),
        ('dots', (50.0, 70.0, 450.0, 50.0)), ('line', (30.0, 30.0, 470.0)),
        ('text', (530.0, 235.0, u'T1')), ('text', (530.0, 195.0, u'T2')),
        ('text', (530.0, 85.0, u'B2')), ('text', (530.0, 45.0, u'B1')),
        ('text', (0.0, -90.0, u'WALL (PLAN SECTION)')),
        ('text', (0.0, -130.0, u'Near face')),
        ('rect', (0.0, -450.0, 500.0, -200.0)),
        ('line', (30.0, -230.0, 470.0)), ('dots', (50.0, -270.0, 450.0, 50.0)),
        ('dots', (50.0, -380.0, 450.0, 50.0)), ('line', (30.0, -420.0, 470.0)),
        ('text', (530.0, -215.0, u'N1')), ('text', (530.0, -255.0, u'N2')),
        ('text', (530.0, -365.0, u'F2')), ('text', (530.0, -405.0, u'F1')),
        ('text', (0.0, -470.0, u'Far face')),
        ('text', (0.0, -550.0, u'1 = outer layer, 2 = second layer')),
    ]
    return items


def _xyz(x_mm, y_mm):
    from Autodesk.Revit import DB  # Lazy import
    return DB.XYZ(x_mm / _FT, y_mm / _FT, 0.0)


def _by_name(doc, cls, name):
    from Autodesk.Revit import DB  # Lazy import
    from nosa_utils.revit_helpers import element_name
    for el in DB.FilteredElementCollector(doc).OfClass(cls):
        if element_name(el) == name:
            return el
    return None


def _text_type_id(doc, name):
    from Autodesk.Revit import DB  # Lazy import
    found = _by_name(doc, DB.TextNoteType, name)
    return found.Id if found is not None else doc.GetDefaultElementTypeId(DB.ElementTypeGroup.TextNoteType)


def _legend(doc, name):
    from Autodesk.Revit import DB  # Lazy import
    from nosa_utils.revit_helpers import element_name
    legends = [v for v in DB.FilteredElementCollector(doc).OfClass(DB.View)
               if not v.IsTemplate and v.ViewType == DB.ViewType.Legend]
    for v in legends:
        if element_name(v) == name:
            return v, False
    # the API cannot create a legend: an emptied copy of any legend of the project
    for v in legends:
        if not v.CanViewBeDuplicated(DB.ViewDuplicateOption.Duplicate):
            continue
        copy = doc.GetElement(v.Duplicate(DB.ViewDuplicateOption.Duplicate))
        ids = [e.Id for e in DB.FilteredElementCollector(doc, copy.Id).WhereElementIsNotElementType()
               if e.Id != copy.Id and e.Category is not None]
        for eid in ids:
            try:
                doc.Delete(eid)
            except Exception:  # nosa-lint: disable=NOSA006 - view-owned items Revit keeps
                pass
        copy.Name = name
        return copy, True
    return None, False


def _solid_fill_type(doc):
    """A solid black filled region type: cut bars are drawn as filled dots (SMDSC 4.2)."""
    from Autodesk.Revit import DB  # Lazy import
    for frt in DB.FilteredElementCollector(doc).OfClass(DB.FilledRegionType):
        pattern = doc.GetElement(frt.ForegroundPatternId)
        colour = frt.ForegroundPatternColor
        try:
            solid = pattern is not None and pattern.GetFillPattern().IsSolidFill
        except Exception:  # nosa-lint: disable=NOSA006 - a type without a readable pattern
            continue
        if solid and colour.Red + colour.Green + colour.Blue == 0:
            return frt
    return None


def _draw_notation(doc, view):
    import math
    from Autodesk.Revit import DB  # Lazy import
    from System.Collections.Generic import List
    view.Scale = NOTATION_SCALE
    label_type = _text_type_id(doc, LABEL_TYPE)
    fill = _solid_fill_type(doc)
    for kind, data in notation_sketch():
        if kind == 'rect':
            x0, y0, x1, y1 = data
            pts = [(x0, y0), (x1, y0), (x1, y1), (x0, y1), (x0, y0)]
            for a, b in zip(pts, pts[1:]):
                doc.Create.NewDetailCurve(view, DB.Line.CreateBound(_xyz(*a), _xyz(*b)))
        elif kind == 'line':
            x0, y, x1 = data
            doc.Create.NewDetailCurve(view, DB.Line.CreateBound(_xyz(x0, y), _xyz(x1, y)))
        elif kind == 'dots':
            x0, y, x1, step = data
            n = int(round((x1 - x0) / step))
            for k in range(n + 1):
                c = _xyz(x0 + k * step, y)
                r = _DOT_R / _FT
                if fill is not None:
                    loop = DB.CurveLoop()
                    loop.Append(DB.Arc.Create(c, r, 0.0, math.pi, DB.XYZ.BasisX, DB.XYZ.BasisY))
                    loop.Append(DB.Arc.Create(c, r, math.pi, 2.0 * math.pi, DB.XYZ.BasisX, DB.XYZ.BasisY))
                    loops = List[DB.CurveLoop]()
                    loops.Add(loop)
                    DB.FilledRegion.Create(doc, fill.Id, view.Id, loops)
                else:
                    doc.Create.NewDetailCurve(view, DB.Arc.Create(
                        c, r, 0.0, 2.0 * math.pi, DB.XYZ.BasisX, DB.XYZ.BasisY))
        elif kind == 'text':
            x, y, text = data
            DB.TextNote.Create(doc, view.Id, _xyz(x, y), text, label_type)


def _project_value(doc, name):
    param = doc.ProjectInformation.LookupParameter(name)
    if param is None:
        return u''
    return param.AsString() or param.AsValueString() or u''


def _write_notes(doc, view):
    from Autodesk.Revit import DB  # Lazy import
    view.Scale = NOTES_SCALE
    text = notes_text(_project_value(doc, u'NOSA_GN_Concrete_Grade'),
                      _project_value(doc, u'NOSA_GN_Cover_Typical'),
                      _project_value(doc, u'NOSA_GN_Cover_Slabs'))
    notes = list(DB.FilteredElementCollector(doc, view.Id).OfClass(DB.TextNote))
    if notes:
        if notes[0].Text.rstrip(u'\r\n') != text:
            notes[0].Text = text
        if abs(notes[0].Width * _FT - NOTES_WIDTH_MM) > 0.5:
            notes[0].Width = NOTES_WIDTH_MM / _FT
        return
    options = DB.TextNoteOptions(_text_type_id(doc, TEXT_TYPE))
    DB.TextNote.Create(doc, view.Id, _xyz(0.0, 0.0), NOTES_WIDTH_MM / _FT, text, options)


def ensure(doc):
    """
    The two legends, created when missing and the notes refreshed from the project values.
    In a transaction; [(legend view)] in panel order, without the ones the project cannot hold.
    """
    out = []
    notation, new = _legend(doc, NOTATION_LEGEND)
    if notation is not None:
        if new:
            _draw_notation(doc, notation)
        out.append(notation)
    notes, _new = _legend(doc, NOTES_LEGEND)
    if notes is not None:
        _write_notes(doc, notes)
        out.append(notes)
    return out


def place(doc, sheet, legends):
    """Viewports of the legends down panel B of the sheet; [viewport]."""
    from Autodesk.Revit import DB  # Lazy import
    doc.Regenerate()   # a legend made in this transaction is not placeable before it
    ports = [DB.Viewport.Create(doc, sheet.Id, v.Id, _xyz(780.0, 300.0)) for v in legends
             if DB.Viewport.CanAddViewToSheet(doc, sheet.Id, v.Id)]
    ports = [p for p in ports if p is not None]
    if not ports:
        return ports
    vp_type = _by_name(doc, DB.ElementType, VIEWPORT_TYPE)
    if vp_type is not None:
        for port in ports:
            if vp_type.Id in port.GetValidTypes():
                port.ChangeTypeId(vp_type.Id)
    doc.Regenerate()
    sizes = []
    for port in ports:
        box = port.GetBoxOutline()
        sizes.append(((box.MaximumPoint.X - box.MinimumPoint.X) * _FT,
                      (box.MaximumPoint.Y - box.MinimumPoint.Y) * _FT))
    for port, (cx, cy) in zip(ports, stack_in_panel(sizes)):
        port.SetBoxCenter(_xyz(cx, cy))
    return ports
