# -*- coding: utf-8 -*-
"""
NOSA.RebarAutomate — legends on every reinforcement drawing (T8.31, T8.32).

IStructE SMDSC 4th ed. 4.2.1: the layer notation (T1/T2, B1/B2, N1/N2, F1/F2) illustrated by a sketch on
the drawings; SMDSC 4th ed. 3.7: notes with the GA references, abbreviations, concrete grade, covers and
schedule references. They stand right-aligned in the bottom right corner of the drawing area,
inside its frame, just above the title block; panel B is left for the project's own notes (user,
2026-10-10). One legend view each, shared by every sheet, so the notes are edited in one place.
"""
from __future__ import absolute_import, division, print_function, unicode_literals

import re

NOTATION_LEGEND = u'RC layer notation'
NOTES_LEGEND = u'RC reinforcement notes'
NOTATION_SCALE = 10
NOTES_SCALE = 1
NOTES_WIDTH_MM = 105.0     # the legend corner's full width: the notes stay inside the frame
TEXT_TYPE = u'2.0mm Century gothic - Sheet notes'
LABEL_TYPE = u'2.0mm Century Gothic'
VIEWPORT_TYPE = u'NOSA Manual title /No scale'

# NOSA A1 QR titleblock: the legends' corner of the drawing area (mm), kept free of views
LEGEND_BOX = (610.0, 25.0, 715.0, 215.0)
PANEL_GAP_MM = 8.0

_FT = 304.8


def notes_text(concrete_grade, cover_typical, cover_slabs):
    """SMDSC 4th ed. 3.7 notes block from the project's general-notes values (NOSA_GN_*); unicode."""
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
        u'(see the layer notation key). EF each face, EW each way, ES each side, STG staggered, ALT alternate, '
        u'ABR alternate bar reversed, UB U-bars (SMDSC 4th ed. Appendix I).',
        u'7. Laps and anchorages to the table in the general notes (0900) unless dimensioned.',
    ]
    return u'\r'.join(lines)


_GRADE = re.compile(u'C\\d{2,3}/\\d{2,3}')


def grade_of(material_name, fallback=u''):
    """'C32/40' from a material name such as 'Concrete C32/40', else the fallback."""
    m = _GRADE.search(material_name or u'')
    return m.group(0) if m else fallback


def _mm(value):
    try:
        return float(u'{}'.format(value).lower().replace(u'mm', u'').strip())
    except (TypeError, ValueError):
        return None


FIXING = {
    u'Beams': u'Beams: links tied to every corner bar and to alternate bars elsewhere; top bars carried on the links, '
              u'bottom bars on spacers to BS 7973 at 1.0 m centres max. Cages may be prefabricated, lifting points '
              u'by the contractor.',
    u'Columns': u'Columns: starter bars fixed to a template before the base is cast, 75 mm kicker; links tied to '
                u'every bar they restrain. Cages may be prefabricated.',
    u'Slabs': u'Slabs: bottom mat on spacers, top mat on chairs to BS 7973 chosen by the contractor (SMDSC 4th ed. 4.2.6); '
              u'bars tied at alternate intersections, at every one along edges and round openings.',
    u'Walls': u'Walls: the two faces held apart by spacers or links at 1.0 m centres max; horizontal bars outside '
              u'the vertical bars unless shown otherwise.',
    u'Foundations': u'Foundations: bottom mat on 50 mm spacers on the blinding; starter bars fixed to a template; '
                    u'lacers tied to every bent-up leg. Multi-column bases and rafts: top mat on chairs and edge '
                    u'U-bars to BS 7973, sized for the pour sequence (SMDSC 4th ed. 6.7.2).',
    u'Stairs': u'Stairs: bars carried on spacers at 1.0 m centres max; landing bars lapped as dimensioned.',
}


def fixing_notes(kinds):
    """SMDSC 4th ed. 4.2.3 (T9.11): the fixing notes of the element kinds on a drawing, in the order given."""
    return [FIXING[k] for k in kinds if k in FIXING]


def drawing_notes(drawing, grades, covers, project_grade=u'', project_cover=u'', deviation=u'', aggregate=u'',
                  schedule_refs=(), ga_refs=u'', buildability=None, details=(), details_drawing=u''):
    """
    SMDSC 4th ed. 3.7 / 4th ed. 6.x.3 (T9.6): the notes of one reinforcement drawing from what is on it, so they never
    disagree with the model. grades {element kind: grade or ''}; covers {element kind: (top, bottom, sides) mm};
    project values are the general notes' (NOSA_GN_*). details: [(key, model detail)] of the NOSA typical
    details the drawing calls for, on details_drawing (T9.21). Returns (text, [warnings]).
    """
    warnings = []
    kinds = sorted(set(grades) | set(covers))
    grade_bits = []
    for kind in kinds:
        g = grades.get(kind) or u''
        if not g:
            g = project_grade
            if project_grade:
                warnings.append(u'{} {}: concrete grade not in the material, the general notes\' {} '
                                u'used.'.format(drawing, kind, project_grade))
            else:
                warnings.append(u'{} {}: no concrete grade in the material or the general notes.'.format(
                    drawing, kind))
        grade_bits.append(u'{} {}'.format(kind.lower(), g or u'(to be confirmed)'))
    cover_bits = []
    typical = _mm(project_cover)
    for kind in kinds:
        c = covers.get(kind)
        if not c:
            continue
        values = sorted(set(int(round(v)) for v in c if v))
        text = u'{}'.format(values[0]) if len(values) == 1 else \
            u'{} top, {} bottom, {} sides'.format(*[int(round(v)) for v in c])
        cover_bits.append(u'{} {}'.format(kind.lower(), text))
        if typical and any(abs(v - typical) > 0.5 for v in c if v) and len(values) == 1:
            warnings.append(u'{} {}: modelled cover {} mm differs from the general notes\' {} — the drawing '
                            u'states the modelled value; check which is right.'.format(drawing, kind, values[0],
                                                                                        project_cover))
    dev = _mm(deviation)
    if dev is None:
        warnings.append(u'{}: no cover deviation set (NOSA_GN_Cover_Deviation): c_nom is stated as '
                        u'modelled.'.format(drawing))
    agg = _mm(aggregate)
    if agg is None:
        warnings.append(u'{}: no maximum aggregate size set (NOSA_GN_Aggregate_Max): the SMDSC standard '
                        u'20 mm is stated, to be confirmed.'.format(drawing))
    refs = u', '.join(schedule_refs)
    if not refs:
        warnings.append(u'{}: no bar schedules issued yet for this drawing.'.format(drawing))
    lines = [
        u'REINFORCEMENT NOTES',
        u'',
        u'1. Read with the general arrangement drawings{} and the general notes (0900). Do not scale from '
        u'this drawing.'.format(u' ' + ga_refs if ga_refs else u''),
        u'2. Concrete: {}.'.format(u'; '.join(grade_bits) or u'to the general notes'),
        u'3. Reinforcement: high yield ribbed bars B500B to BS 4449, scheduled to BS 8666:2020. Bar '
        u'schedules: {}.'.format(refs or u'to be issued (refs {}-01 ...)'.format(drawing)),
        u'4. Nominal cover c_nom to all reinforcement, links included{}: {}.'.format(
            u' (includes delta c_dev = {:.0f})'.format(dev) if dev is not None else u'',
            u'; '.join(cover_bits) or u'to the general notes'),
        u'5. Maximum aggregate size {:.0f} mm.'.format(agg if agg is not None else 20.0),
        u'6. Bar notation: number, type and size, mark, centres, layer, e.g. 20H16-63-150 B1; centres and '
        u'layer not given for beams and columns. Link zones (13@100): 13 links at 100 centres.',
        u'7. Layers: T top, B bottom, N near face, F far face; 1 outer layer, 2 second layer (see the layer '
        u'notation key). EF each face, EW each way, ES each side, STG staggered, ALT alternate, ABR alternate '
        u'bar reversed, UB U-bars (SMDSC 4th ed. Appendix I).',
        u'8. Laps and anchorages to the table in the general notes (0900) unless dimensioned; laps of adjacent '
        u'bars staggered unless shown otherwise.',
        # good practice notes for every RC drawing (user 2026-10-17: IStructE)
        u'9. Bars bent cold to BS 8666; none heated, welded or rebent on site without approval.',
        u'10. Construction joints, holes and cast-in items only as shown or agreed.',
        u'11. Reinforcement inspected before concreting; no bar substituted without approval.',
    ]
    number = 12
    fixing = fixing_notes(kinds)
    if fixing:
        lines.append(u'{}. Fixing: '.format(number) + u' '.join(fixing))
        number += 1
    if buildability is not None:
        score, grade, errors, warns = buildability
        # T9.12: the drawing's buildability, from the reinforcement QA of its members
        lines.append(u'{}. Buildability check: {} ({:.0f}/100; {} error(s), {} warning(s)) - see the RC QA '
                     u'report.'.format(number, grade, score, errors, warns))
        number += 1
    if details:
        lines.append(u'{}. Typical details: {}{} (after the SMDSC 4th ed. model details; confirm with '
                     u'design).'.format(number, u', '.join(u'TD {} ({})'.format(k, md.replace(u'SMDSC 4th ed. ', u''))
                                                       for k, md in details),
                                        u' on drawing{} {}'.format(u's' if u',' in details_drawing else u'', details_drawing)
                                        if details_drawing else u''))
    return u'\r'.join(lines), warnings


def stack_in_panel(sizes, panel=LEGEND_BOX, gap=PANEL_GAP_MM):
    """
    Centres (x, y) mm that stack boxes (w, h) down the legend box from its top, their left edges in one
    line and the widest against the box's right edge.
    """
    x0, y0, x1, y1 = panel
    left = x1 - max([w for w, _h in sizes] or [0.0])
    out, top = [], y1
    for w, h in sizes:
        out.append((left + w / 2.0, top - h / 2.0))
        top -= h + gap
    return out


# notation sketch, model mm at NOTATION_SCALE: (kind, data)
#   'rect' (x0, y0, x1, y1) | 'line' (x0, y, x1) | 'dots' (x0, y, x1, step) | 'text' (x, y, text)
_DOT_R = 8.0


def notation_sketch():
    """SMDSC 4th ed. 4.2.1 key: slab section with T1/T2/B1/B2, wall plan section with N1/N2/F1/F2."""
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
    """A solid black filled region type: cut bars are drawn as filled dots (SMDSC 4th ed. 4.2)."""
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
    # the notes are now each drawing's own (sheet_notes, T9.6): the shared notes legend is no longer placed
    return out


_KINDS = (('OST_StructuralFraming', u'Beams'), ('OST_StructuralColumns', u'Columns'), ('OST_Floors', u'Slabs'),
          ('OST_Walls', u'Walls'), ('OST_StructuralFoundation', u'Foundations'), ('OST_Stairs', u'Stairs'))


def _kind(host):
    from Autodesk.Revit import DB  # Lazy import
    from nosa_utils.revit_helpers import get_id_value
    cat = host.Category
    if cat is None:
        return u'Members'
    for name, label in _KINDS:
        if get_id_value(cat.Id) == int(getattr(DB.BuiltInCategory, name)):
            return label
    return u'Members'


def _material_name(doc, host):
    from Autodesk.Revit import DB  # Lazy import
    for getter in (lambda: host.get_Parameter(DB.BuiltInParameter.STRUCTURAL_MATERIAL_PARAM).AsElementId(),
                   lambda: doc.GetElement(host.GetTypeId()).get_Parameter(
                       DB.BuiltInParameter.STRUCTURAL_MATERIAL_PARAM).AsElementId(),
                   lambda: (lambda cs: cs.GetMaterialId(cs.StructuralMaterialIndex))(
                       doc.GetElement(host.GetTypeId()).GetCompoundStructure())):
        try:
            m = doc.GetElement(getter())
            if m is not None:
                return m.Name
        except Exception:
            continue
    return u''


def _covers(doc, host):
    from Autodesk.Revit import DB  # Lazy import
    out = []
    for bip in (DB.BuiltInParameter.CLEAR_COVER_TOP, DB.BuiltInParameter.CLEAR_COVER_BOTTOM,
                DB.BuiltInParameter.CLEAR_COVER_OTHER):
        try:
            out.append(doc.GetElement(host.get_Parameter(bip).AsElementId()).CoverDistance * _FT)
        except Exception:
            out.append(None)
    return tuple(out) if any(out) else None


def sheet_notes(doc, sheet, hosts, rebars, buildability=None, typical=(), typical_drawing=u''):
    """
    The drawing's own notes block (T9.6) on the sheet, under the layer notation key in the legend box.
    Returns the warnings about data the model or the general notes do not give.
    """
    from Autodesk.Revit import DB  # Lazy import
    grades, covers = {}, {}
    project_grade = _project_value(doc, u'NOSA_GN_Concrete_Grade')
    for host in hosts:
        kind = _kind(host)
        grades[kind] = grades.get(kind) or grade_of(_material_name(doc, host))
        c = _covers(doc, host)
        if c:
            covers[kind] = c
    refs = sorted(set(r.LookupParameter(u'NOSA_Rebar_Assembly').AsString()
                      for r in rebars if r.LookupParameter(u'NOSA_Rebar_Assembly') is not None
                      and r.LookupParameter(u'NOSA_Rebar_Assembly').AsString()))
    text, warnings = drawing_notes(
        sheet.SheetNumber, grades, covers, project_grade, _project_value(doc, u'NOSA_GN_Cover_Typical'),
        _project_value(doc, u'NOSA_GN_Cover_Deviation'), _project_value(doc, u'NOSA_GN_Aggregate_Max'), refs,
        _project_value(doc, u'NOSA_GN_GA_Drawings'), buildability, typical, typical_drawing)
    top = LEGEND_BOX[3]
    for port in [doc.GetElement(i) for i in sheet.GetAllViewports()]:
        view = doc.GetElement(port.ViewId)
        if view is not None and view.Name == NOTATION_LEGEND:
            top = port.GetBoxOutline().MinimumPoint.Y * _FT - PANEL_GAP_MM
    options = DB.TextNoteOptions(_text_type_id(doc, TEXT_TYPE))
    DB.TextNote.Create(doc, sheet.Id, _xyz(LEGEND_BOX[2] - NOTES_WIDTH_MM, top), NOTES_WIDTH_MM / _FT, text,
                       options)
    return warnings


def place(doc, sheet, legends):
    """Viewports of the legends down the legend box of the sheet; [viewport]."""
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


TYPICAL_SHEET_NAME = u'RC typical details'
TYPICAL_AREA = (40.0, 40.0, 710.0, 560.0)   # sheet mm the details fill, clear of the titleblock strip
TYPICAL_PER_ROW = 3
TYPICAL_ROW_MM = 250.0


def _empty(doc, view):
    """Delete what a legend view holds (to draw it again)."""
    from Autodesk.Revit import DB  # Lazy import
    for eid in [e.Id for e in DB.FilteredElementCollector(doc, view.Id).WhereElementIsNotElementType()
                if e.Id != view.Id and e.Category is not None]:
        try:
            doc.Delete(eid)
        except Exception:  # nosa-lint: disable=NOSA006 - view-owned items Revit keeps
            pass


def typical_views(doc, keys, redraw=False):
    """
    The legends of the typical details `keys`, drawn when missing (or again with redraw); legends still under their
    old 'NOSA TD' names renamed. In a transaction. [view] in the order of keys.
    """
    from Autodesk.Revit import DB  # Lazy import
    from nosa_utils import typical_details as td
    from nosa_utils.revit_helpers import element_name
    legends = dict((element_name(v), v) for v in DB.FilteredElementCollector(doc).OfClass(DB.View)
                   if not v.IsTemplate and v.ViewType == DB.ViewType.Legend)
    views = []
    for key in keys:
        old = legends.get(td.view_name(key, td.OLD_PREFIX))
        if old is not None and td.view_name(key) not in legends:
            old.Name = td.view_name(key)
            legends[td.view_name(key)] = old
        view, new = _legend(doc, td.view_name(key))
        if view is None:
            continue
        if redraw and not new:
            _empty(doc, view)
        if new or redraw:
            td.draw(doc, view, key, _text_type_id(doc, LABEL_TYPE))
        views.append(view)
    return views


def untitled(doc, ports):
    """Viewports of legends that carry their own title: the NOSA no-title viewport type."""
    from Autodesk.Revit import DB  # Lazy import
    vp_type = _by_name(doc, DB.ElementType, VIEWPORT_TYPE)
    if vp_type is None:
        return
    for port in ports:
        try:
            if vp_type.Id in port.GetValidTypes():
                port.ChangeTypeId(vp_type.Id)
        except Exception:
            continue


def typical_details(doc, keys, titleblock=None, redraw=False, number=None):
    """
    T9.21: the typical details `keys` as legends (drawn when missing, or again with redraw) on the project's
    typical details drawing, made with `titleblock` when missing; legends still under their old 'NOSA TD' names
    are renamed. number: a callable giving the drawing's number when it has to be made (the caller's reserved
    numbers), else the next free RC number. In a transaction. Returns (the numbers of the drawings they are on,
    '' if none, [(key, model detail)]).
    """
    from Autodesk.Revit import DB  # Lazy import
    from nosa_utils import typical_details as td
    if not keys:
        return u'', []
    views = typical_views(doc, keys, redraw)
    import view_plan
    from nosa_utils.revit_helpers import get_id_value
    # found by their names - 'RC typical details', '... (2)'...: each takes the next free RC number when first
    # made, among the drawings (user 2026-10-17); six details to a sheet
    pages = sorted([s for s in DB.FilteredElementCollector(doc).OfClass(DB.ViewSheet)
                    if s.Name == TYPICAL_SHEET_NAME or s.Name.startswith(TYPICAL_SHEET_NAME + u' (')],
                   key=lambda s: s.SheetNumber)
    where = {}                                     # view id -> sheet number
    for sheet in pages:
        for i in sheet.GetAllViewports():
            where[get_id_value(doc.GetElement(i).ViewId)] = sheet.SheetNumber
    cell = (TYPICAL_AREA[2] - TYPICAL_AREA[0]) / TYPICAL_PER_ROW
    per_sheet = TYPICAL_PER_ROW * int((TYPICAL_AREA[3] - TYPICAL_AREA[1]) // TYPICAL_ROW_MM)
    for view in views:
        if get_id_value(view.Id) in where:
            continue
        sheet = next((s for s in pages if len(s.GetAllViewports()) < per_sheet), None)
        if sheet is None:
            if titleblock is None:
                break
            try:
                existing = [s.SheetNumber for s in DB.FilteredElementCollector(doc).OfClass(DB.ViewSheet)]
                sheet = DB.ViewSheet.Create(doc, titleblock.Id)
                sheet.SheetNumber = number() if number is not None else \
                    view_plan.next_sheet_numbers(existing, 1)[0]
                sheet.Name = TYPICAL_SHEET_NAME if not pages else u'{} ({})'.format(TYPICAL_SHEET_NAME,
                                                                                    len(pages) + 1)
                pages.append(sheet)
                doc.Regenerate()
            except Exception:
                break
        placed = len(sheet.GetAllViewports())
        col, row = placed % TYPICAL_PER_ROW, placed // TYPICAL_PER_ROW
        try:
            port = DB.Viewport.Create(doc, sheet.Id, view.Id, _xyz(TYPICAL_AREA[0] + cell * (col + 0.5),
                                                                   TYPICAL_AREA[3] - TYPICAL_ROW_MM * (row + 0.5)))
        except Exception:
            continue
        if port is None:
            continue
        doc.Regenerate()
        # its top left at the cell's top left, whatever the detail's size
        box = port.GetBoxOutline()
        w = (box.MaximumPoint.X - box.MinimumPoint.X) * _FT
        h = (box.MaximumPoint.Y - box.MinimumPoint.Y) * _FT
        port.SetBoxCenter(_xyz(TYPICAL_AREA[0] + cell * col + w / 2.0, TYPICAL_AREA[3] - TYPICAL_ROW_MM * row - h / 2.0))
        where[get_id_value(view.Id)] = sheet.SheetNumber
    numbers = sorted(set(where.get(get_id_value(v.Id)) for v in views) - set([None]))
    return u', '.join(numbers), [(k, td.by_key()[k][1]) for k in keys]
