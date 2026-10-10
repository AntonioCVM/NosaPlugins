# -*- coding: utf-8 -*-
"""
NOSA.RebarAutomate — Create Views in one click (T7.3).

For every reinforced element: the view set of its typology (user decision 2026-10-03), the NOSA
RC templates, a scale from view_plan, its bars shown unobscured and tagged without overlaps, and
an A1 QR sheet of its own numbered in the 4000 series. Each element is built in one transaction
that rolls back on a Revit error instead of opening a dialog.
"""
from __future__ import absolute_import, division, print_function, unicode_literals
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

_FT = 304.8
SECTION_TEMPLATE = u'NOSA RC Section'
PLAN_TEMPLATE = u'NOSA RC PLAN'
TITLEBLOCK = u'NOSA_Titleblock_A1_QR'
_CATEGORIES = (('OST_StructuralColumns', 'column'), ('OST_StructuralFraming', 'beam'),
               ('OST_StructuralFoundation', 'foundation'), ('OST_Floors', 'floor'),
               ('OST_Walls', 'wall'), ('OST_Stairs', 'stairs'))
_TITLES = {'column': u'Column', 'beam': u'Beam', 'foundation': u'Foundation', 'floor': u'Slab',
           'wall': u'Wall', 'stairs': u'Stair'}


def _mm(feet):
    return feet * _FT


def _ft(mm):
    return mm / _FT


def host_kind(element):
    from Autodesk.Revit import DB  # Lazy import
    from nosa_utils.revit_helpers import get_id_value
    if element is None or element.Category is None:
        return None
    value = get_id_value(element.Category.Id)
    for name, kind in _CATEGORIES:
        if value == int(getattr(DB.BuiltInCategory, name)):
            return kind
    return None


def host_rebars(element):
    from Autodesk.Revit.DB.Structure import RebarHostData
    try:
        return list(RebarHostData.GetRebarHostData(element).GetRebarsInHost())
    except Exception:
        return []


def host_label(element):
    """The element's Mark, else the BBS partition of its bars, else its id."""
    from Autodesk.Revit import DB  # Lazy import
    from nosa_utils.revit_helpers import get_id_value
    try:
        mark = (element.get_Parameter(DB.BuiltInParameter.ALL_MODEL_MARK).AsString() or u'').strip()
        if mark:
            return mark
    except Exception:  # nosa-lint: disable=NOSA006 - no Mark parameter: the next source applies
        pass
    for rebar in host_rebars(element):
        try:
            partition = rebar.get_Parameter(DB.BuiltInParameter.NUMBER_PARTITION_PARAM).AsString()
            if partition:
                return partition
        except Exception:
            continue
    return u'{}'.format(get_id_value(element.Id))


def _box(element, re_engine):
    box = None
    try:
        box = re_engine.get_isolated_solid_bbox(element)
    except Exception:
        box = None
    return box or element.get_BoundingBox(None)


def _extent(box, direction):
    """(min, max) of a bounding box along a direction, ft."""
    from Autodesk.Revit import DB  # Lazy import
    values = [DB.XYZ(x, y, z).DotProduct(direction) for x in (box.Min.X, box.Max.X)
              for y in (box.Min.Y, box.Max.Y) for z in (box.Min.Z, box.Max.Z)]
    return min(values), max(values)


def _section(title, kind, origin, right, up, half_w, half_h, near, far):
    return {'title': title, 'kind': kind, 'plan': False, 'origin': origin, 'right': right.Normalize(),
            'up': up.Normalize(), 'half_w': half_w, 'half_h': half_h, 'near': near, 'far': far,
            'size': (2.0 * half_w, 2.0 * half_h)}


def _plan(title, kind, level, box, cut_z, bottom_z, margin=500.0):
    return {'title': title, 'kind': kind, 'plan': True, 'level': level, 'box': box, 'cut_z': cut_z,
            'bottom_z': bottom_z, 'margin': margin,
            'size': (_mm(box.Max.X - box.Min.X) + 2 * margin, _mm(box.Max.Y - box.Min.Y) + 2 * margin)}


def _level_of(doc, element):
    from Autodesk.Revit import DB  # Lazy import
    for getter in (lambda: element.LevelId,
                   lambda: element.get_Parameter(DB.BuiltInParameter.STAIRS_BASE_LEVEL_PARAM).AsElementId(),
                   lambda: element.get_Parameter(DB.BuiltInParameter.FAMILY_BASE_LEVEL_PARAM).AsElementId()):
        try:
            level = doc.GetElement(getter())
            if isinstance(level, DB.Level):
                return level
        except Exception:
            continue
    levels = sorted(DB.FilteredElementCollector(doc).OfClass(DB.Level), key=lambda l: l.Elevation)
    return levels[0] if levels else None


def _local_axes(element):
    from Autodesk.Revit import DB  # Lazy import
    try:
        x = element.HandOrientation
        y = element.FacingOrientation
        if x.GetLength() > 0.5 and y.GetLength() > 0.5:
            return DB.XYZ(x.X, x.Y, 0).Normalize(), DB.XYZ(y.X, y.Y, 0).Normalize()
    except Exception:  # nosa-lint: disable=NOSA006 - not a family instance: global axes
        pass
    return DB.XYZ.BasisX, DB.XYZ.BasisY


def view_specs(doc, hosts, re_engine, beam_rebar=None, stair_host=None):
    """The view set of one element (or one line of beam spans), in view_plan's kinds."""
    from Autodesk.Revit import DB  # Lazy import
    host = hosts[0]
    kind = host_kind(host)
    z_axis = DB.XYZ.BasisZ
    specs = []
    if kind == 'column':
        box = _box(host, re_engine)
        x, y = _local_axes(host)
        if x.CrossProduct(y).Z < 0:
            y = y.Negate()
        centre = (box.Min + box.Max).Multiply(0.5)
        wx = _mm(_extent(box, x)[1] - _extent(box, x)[0])
        wy = _mm(_extent(box, y)[1] - _extent(box, y)[0])
        height = _mm(box.Max.Z - box.Min.Z)
        specs.append(_section(u'Section', 'member_section', centre, x, y, wx / 2 + 150, wy / 2 + 150, 0.0, 60.0))
        specs.append(_section(u'Elevation A', 'column_elevation', centre, x, z_axis, wx / 2 + 300,
                              height / 2 + 700, 1.0, wy / 2 + 60))
        specs.append(_section(u'Elevation B', 'column_elevation', centre, y, z_axis, wy / 2 + 300,
                              height / 2 + 700, 1.0, wx / 2 + 60))
    elif kind == 'beam':
        axes = [beam_rebar._clamp_axis_to_bbox(beam_rebar.get_beam_axis(h), h) for h in hosts]
        d = axes[0].Direction.Normalize()
        w = z_axis.CrossProduct(d).Normalize()
        origin = axes[0].GetEndPoint(0)
        params = [(a.GetEndPoint(i) - origin).DotProduct(d) for a in axes for i in (0, 1)]
        boxes = [_box(h, re_engine) for h in hosts]
        z0 = min(b.Min.Z for b in boxes)
        z1 = max(b.Max.Z for b in boxes)
        lo, hi = min(params), max(params)
        width = _mm(_extent(boxes[0], w)[1] - _extent(boxes[0], w)[0])
        mid = origin + d.Multiply((lo + hi) / 2.0)
        mid = DB.XYZ(mid.X, mid.Y, (z0 + z1) / 2.0)
        depth = _mm(z1 - z0)
        specs.append(_section(u'Elevation', 'elevation', mid, d, z_axis, _mm(hi - lo) / 2 + 600,
                              depth / 2 + 300, 1.0, width / 2 + 60))
        for n, axis in enumerate(axes):
            label = u'' if len(axes) == 1 else u' span {}'.format(n + 1)
            centre = axis.Evaluate(0.5, True)
            centre = DB.XYZ(centre.X, centre.Y, (z0 + z1) / 2.0)
            specs.append(_section(u'Section mid{}'.format(label), 'member_section', centre, w, z_axis,
                                  width / 2 + 150, depth / 2 + 150, 0.0, 60.0))
            near = min(_ft(500.0), axis.Length / 4.0)
            at_support = axis.GetEndPoint(0) + axis.Direction.Multiply(near)
            at_support = DB.XYZ(at_support.X, at_support.Y, (z0 + z1) / 2.0)
            specs.append(_section(u'Section support{}'.format(label), 'member_section', at_support, w,
                                  z_axis, width / 2 + 150, depth / 2 + 150, 0.0, 60.0))
    elif kind in ('foundation', 'floor'):
        box = _box(host, re_engine)
        x, y = _local_axes(host) if kind == 'foundation' else (DB.XYZ.BasisX, DB.XYZ.BasisY)
        centre = (box.Min + box.Max).Multiply(0.5)
        level = _level_of(doc, host)
        section_kind = 'footing_section' if kind == 'foundation' else 'slab_section'
        specs.append(_plan(u'Plan', 'plan', level, box, _mm(box.Max.Z) + 200.0, _mm(box.Min.Z) - 200.0))
        thick = _mm(box.Max.Z - box.Min.Z)
        for name, right, other in ((u'Section A', x, y), (u'Section B', y, x)):
            lo, hi = _extent(box, right)
            olo, ohi = _extent(box, other)
            specs.append(_section(name, section_kind, centre, right, z_axis, _mm(hi - lo) / 2 + 300,
                                  thick / 2 + 300, 1.0, _mm(ohi - olo) / 2 + 60))
    elif kind == 'wall':
        box = _box(host, re_engine)
        line = host.Location.Curve
        d = line.Direction.Normalize()
        n = z_axis.CrossProduct(d).Normalize()
        centre = line.Evaluate(0.5, True)
        centre = DB.XYZ(centre.X, centre.Y, (box.Min.Z + box.Max.Z) / 2.0)
        height = _mm(box.Max.Z - box.Min.Z)
        thick = _mm(host.Width)
        specs.append(_section(u'Elevation', 'elevation', centre, d, z_axis, _mm(line.Length) / 2 + 300,
                              height / 2 + 700, 1.0, thick / 2 + 60))
        specs.append(_section(u'Section', 'member_section', centre, n, z_axis, thick / 2 + 300,
                              height / 2 + 700, 0.0, 60.0))
    elif kind == 'stairs':
        data = stair_host.read_stairs(doc, host)
        box = _box(host, re_engine) if host.get_BoundingBox(None) is not None else None
        for i, run in enumerate(data['runs']):
            frame = run['frame']
            s_lo = run['lower']['s_far'] if run['lower']['kind'] == 'landing' else 0.0
            s_hi = run['upper']['s_far'] if run['upper']['kind'] == 'landing' else run['length']
            v_mid = (run['v_min'] + run['v_max']) / 2.0
            z_lo = run['lower']['bottom'] - 300.0
            z_hi = run['upper']['top']
            origin = frame.xyz((s_lo + s_hi) / 2.0, v_mid, (z_lo + z_hi) / 2.0)
            right = frame.u
            specs.append(_section(u'Flight {} section'.format(i + 1), 'stair_section', origin, right,
                                  z_axis, (s_hi - s_lo) / 2 + 400, (z_hi - z_lo) / 2 + 400, 1.0,
                                  (run['v_max'] - run['v_min']) / 2 + 60))
        if box is not None:
            specs.append(_plan(u'Plan', 'stair_plan', _level_of(doc, host), box,
                               _mm(box.Max.Z) + 200.0, _mm(box.Min.Z) - 200.0, margin=400.0))
    return specs


def _view_family_type(doc, family):
    from Autodesk.Revit import DB  # Lazy import
    for vft in DB.FilteredElementCollector(doc).OfClass(DB.ViewFamilyType):
        if vft.ViewFamily == family:
            return vft
    return None


def _template(doc, name):
    from Autodesk.Revit import DB  # Lazy import
    from nosa_utils.revit_helpers import element_name
    for view in DB.FilteredElementCollector(doc).OfClass(DB.View):
        if view.IsTemplate and element_name(view) == name:
            return view
    return None


def _create_section(doc, vft, spec):
    from Autodesk.Revit import DB  # Lazy import
    transform = DB.Transform.Identity
    transform.Origin = spec['origin']
    transform.BasisX = spec['right']
    transform.BasisY = spec['up']
    transform.BasisZ = spec['right'].CrossProduct(spec['up']).Normalize()
    box = DB.BoundingBoxXYZ()
    box.Transform = transform
    box.Min = DB.XYZ(-_ft(spec['half_w']), -_ft(spec['half_h']), -_ft(spec['far']))
    box.Max = DB.XYZ(_ft(spec['half_w']), _ft(spec['half_h']), _ft(spec['near']))
    return DB.ViewSection.CreateDetail(doc, vft.Id, box)


def _create_plan(doc, vft, spec):
    from Autodesk.Revit import DB  # Lazy import
    level = spec['level']
    view = DB.ViewPlan.Create(doc, vft.Id, level.Id)
    rng = view.GetViewRange()
    level_mm = _mm(level.Elevation)
    cut = spec['cut_z'] - level_mm
    bottom = spec['bottom_z'] - level_mm
    for plane, offset in ((DB.PlanViewPlane.TopClipPlane, cut + 100.0), (DB.PlanViewPlane.CutPlane, cut),
                          (DB.PlanViewPlane.BottomClipPlane, bottom),
                          (DB.PlanViewPlane.ViewDepthPlane, bottom)):
        rng.SetLevelId(plane, level.Id)
        rng.SetOffset(plane, _ft(offset))
    view.SetViewRange(rng)
    box = spec['box']
    crop = DB.BoundingBoxXYZ()
    margin = _ft(spec['margin'])
    crop.Min = DB.XYZ(box.Min.X - margin, box.Min.Y - margin, box.Min.Z)
    crop.Max = DB.XYZ(box.Max.X + margin, box.Max.Y + margin, box.Max.Z)
    view.CropBoxActive = True
    view.CropBox = crop
    return view


def _unique_view_name(doc, wanted):
    from Autodesk.Revit import DB  # Lazy import
    from nosa_utils.revit_helpers import element_name
    taken = set(element_name(v) for v in DB.FilteredElementCollector(doc).OfClass(DB.View))
    name, n = wanted, 2
    while name in taken:
        name = u'{} ({})'.format(wanted, n)
        n += 1
    return name


def hide_section_marks(view):
    """
    No section marks in the elevations and sections of a member (user brief 2026-10-10: Revit puts their
    heads at the ends of the section's crop, right on the calling-up under a beam); each section is told by
    its title. On the RC template when it controls the annotation visibility, else on the view.
    """
    from Autodesk.Revit import DB  # Lazy import
    from nosa_utils.revit_helpers import get_id_value
    doc = view.Document
    cat = DB.ElementId(DB.BuiltInCategory.OST_Sections)
    target = view
    template = doc.GetElement(view.ViewTemplateId) if view.ViewTemplateId != DB.ElementId.InvalidElementId else None
    if template is not None:
        free = set(get_id_value(i) for i in template.GetNonControlledTemplateParameterIds())
        if int(DB.BuiltInParameter.VIS_GRAPHICS_ANNOTATION) not in free:
            target = template
    try:
        if not target.GetCategoryHidden(cat):
            target.SetCategoryHidden(cat, True)
        return True
    except Exception:
        from nosa_utils.telemetry import log_swallowed
        log_swallowed(u'rebarautomate', u'hide_section_marks')
        return False


def ensure_coarse(view):
    """
    Detail level Coarse (user decision 2026-10-10, replacing Fine of 2026-10-06): a bar is one thick line
    and a cut bar a filled dot to scale (IStructE SMDSC 3.10), legible on A1 and reduced to A3. When the
    view template controls the detail level, the RC template itself is set; otherwise the view. In a
    transaction; True when it is Coarse.
    """
    from Autodesk.Revit import DB  # Lazy import
    from nosa_utils.revit_helpers import get_id_value
    doc = view.Document
    template = doc.GetElement(view.ViewTemplateId) if view.ViewTemplateId != DB.ElementId.InvalidElementId else None
    target = view
    if template is not None:
        free = set(get_id_value(i) for i in template.GetNonControlledTemplateParameterIds())
        if int(DB.BuiltInParameter.VIEW_DETAIL_LEVEL) not in free:
            target = template
    try:
        if target.DetailLevel != DB.ViewDetailLevel.Coarse:
            target.DetailLevel = DB.ViewDetailLevel.Coarse
        return True
    except Exception:
        from nosa_utils.telemetry import log_swallowed
        log_swallowed(u'rebarautomate', u'ensure_coarse')
        return False


def _apply_template_and_scale(view, template, scale):
    from Autodesk.Revit import DB  # Lazy import
    if template is not None:
        view.ViewTemplateId = template.Id
    try:
        view.Scale = scale
    except Exception:
        # this template fixes the scale: copy its settings instead of linking it
        view.ViewTemplateId = DB.ElementId.InvalidElementId
        if template is not None:
            view.ApplyViewTemplateParameters(template)
        view.Scale = scale
    ensure_coarse(view)


def _rollback_on_error():
    from Autodesk.Revit import DB  # Lazy import

    class RollbackOnError(DB.IFailuresPreprocessor):
        def __init__(self):
            self.errors = []

        def PreprocessFailures(self, accessor):
            accessor.DeleteAllWarnings()
            errors = [f for f in accessor.GetFailureMessages()
                      if f.GetSeverity() != DB.FailureSeverity.Warning]
            if not errors:
                return DB.FailureProcessingResult.Continue
            self.errors.extend(f.GetDescriptionText() for f in errors)
            return DB.FailureProcessingResult.ProceedWithRollBack
    return RollbackOnError()


def _new_sheet(doc, titleblock, number, name):
    from Autodesk.Revit import DB  # Lazy import
    sheet = DB.ViewSheet.Create(doc, titleblock.Id)
    sheet.SheetNumber = number
    sheet.Name = name
    return sheet


def _place_on_sheets(doc, created, titleblock, sheet_numbers, view_plan, name, retag=None, legends=()):
    """
    Two passes: drop every view on the first sheet, read its real viewport size (tags and the
    view title included), then pack them. One sheet per element (user brief): while the views
    need a second sheet, the largest one that can goes to its next coarser scale (tags re-laid
    out by `retag`); only then does a view move to another sheet. Every sheet gets the legends
    (layer notation, reinforcement notes) in the corner of the drawing area kept for them
    (IStructE SMDSC 3.7, 4.2.1).
    """
    from Autodesk.Revit import DB  # Lazy import
    sheets = [_new_sheet(doc, titleblock, sheet_numbers.pop(0), name)]
    ports = [DB.Viewport.Create(doc, sheets[0].Id, view.Id, DB.XYZ(_ft(400.0), _ft(300.0), 0.0))
             for view, _spec, _scale in created]
    doc.Regenerate()

    def _size(port):
        box = port.GetBoxOutline()
        return _mm(box.MaximumPoint.X - box.MinimumPoint.X), _mm(box.MaximumPoint.Y - box.MinimumPoint.Y)
    sizes = [_size(port) for port in ports]
    reserved = ()
    if legends:
        import rc_legends
        reserved = (rc_legends.LEGEND_BOX,)
    placement = view_plan.layout(sizes, reserved=reserved)
    stuck = set()
    for _attempt in range(12):
        if max(p[0] for p in placement) == 0:
            break
        candidates = [i for i, (view, spec, _s) in enumerate(created)
                      if i not in stuck and view_plan.coarser_scale(spec['kind'], view.Scale)]
        if not candidates:
            break
        i = max(candidates, key=lambda k: sizes[k][0] * sizes[k][1])
        view, spec = created[i][0], created[i][1]
        try:
            view.Scale = view_plan.coarser_scale(spec['kind'], view.Scale)
        except Exception:  # nosa-lint: disable=NOSA006 - its template fixes the scale: leave it
            stuck.add(i)
            continue
        if retag is not None:
            retag(view)
        doc.Regenerate()
        sizes[i] = _size(ports[i])
        placement = view_plan.layout(sizes, reserved=reserved)
    for i, (sheet_index, cx, cy) in enumerate(placement):
        while sheet_index >= len(sheets):
            sheets.append(_new_sheet(doc, titleblock, sheet_numbers.pop(0),
                                     u'{} ({})'.format(name, len(sheets) + 1)))
        centre = DB.XYZ(_ft(cx), _ft(cy), 0.0)
        if sheet_index == 0:
            ports[i].SetBoxCenter(centre)
        else:
            view_id = ports[i].ViewId
            doc.Delete(ports[i].Id)
            ports[i] = DB.Viewport.Create(doc, sheets[sheet_index].Id, view_id, centre)
    if legends:
        import rc_legends
        for sheet in sheets:
            rc_legends.place(doc, sheet, legends)
    return [s.SheetNumber for s in sheets]


def build_element_views(doc, hosts, re_engine, rebar_detailing, view_plan, sheet_numbers,
                        beam_rebar=None, stair_host=None, place_on_sheets=True, tag=True):
    """
    Views (and sheets) of one element / beam line. sheet_numbers: a list the next numbers are
    popped from. Returns {'views': [names], 'sheets': [numbers], 'tags': n, 'errors': [...]}.
    """
    from Autodesk.Revit import DB  # Lazy import
    from nosa_utils.revit_helpers import element_name, get_id_value
    kind = host_kind(hosts[0])
    label = host_label(hosts[0]) if len(hosts) == 1 else u'{}-{}'.format(host_label(hosts[0]),
                                                                         host_label(hosts[-1]))
    report = {'views': [], 'sheets': [], 'tags': 0, 'errors': []}
    specs = view_specs(doc, hosts, re_engine, beam_rebar, stair_host)
    if not specs:
        report['errors'].append(u'{} {}: nothing to draw.'.format(_TITLES.get(kind, u'Element'), label))
        return report
    detail_vft = _view_family_type(doc, DB.ViewFamily.Detail)
    plan_vft = _view_family_type(doc, DB.ViewFamily.StructuralPlan) or \
        _view_family_type(doc, DB.ViewFamily.FloorPlan)
    section_template = _template(doc, SECTION_TEMPLATE)
    plan_template = _template(doc, PLAN_TEMPLATE)
    titleblock = None
    for symbol in DB.FilteredElementCollector(doc).OfClass(DB.FamilySymbol).OfCategory(
            DB.BuiltInCategory.OST_TitleBlocks):
        if titleblock is None or element_name(symbol) == TITLEBLOCK:
            titleblock = symbol
            if element_name(symbol) == TITLEBLOCK:
                break
    rebars = [r for h in hosts for r in host_rebars(h)]

    if tag and rebars:
        try:
            import rebar_presentation
            rebar_presentation.bind(doc)       # the one-calling-up-per-mark parameters (SMDSC 4.2.1)
        except Exception as e:
            report['errors'].append(u'presentation parameters not bound: {}'.format(e))
    guard = _rollback_on_error()
    t = DB.Transaction(doc, u'NOSA — Create Views {} {}'.format(_TITLES.get(kind, u''), label))
    options = t.GetFailureHandlingOptions()
    options.SetFailuresPreprocessor(guard)
    options.SetClearAfterRollback(True)
    options.SetForcedModalHandling(False)
    t.SetFailureHandlingOptions(options)
    t.Start()
    created = []
    try:
        for spec in specs:
            scale = view_plan.choose_scale(spec['kind'], spec['size'][0], spec['size'][1])
            if spec['plan']:
                if plan_vft is None or spec['level'] is None:
                    report['errors'].append(u'{}: no plan view type or level.'.format(spec['title']))
                    continue
                view = _create_plan(doc, plan_vft, spec)
                _apply_template_and_scale(view, plan_template, scale)
            else:
                if detail_vft is None:
                    report['errors'].append(u'No detail view type in this project.')
                    break
                view = _create_section(doc, detail_vft, spec)
                _apply_template_and_scale(view, section_template, scale)
                hide_section_marks(view)
            view.Name = _unique_view_name(doc, u'{} {} - {}'.format(_TITLES.get(kind, u''), label,
                                                                     spec['title']))
            for rebar in rebars:
                try:
                    rebar.SetUnobscuredInView(view, True)
                except Exception:
                    continue
            created.append((view, spec, scale))
        doc.Regenerate()
        if tag and rebars:
            # T8.27, SMDSC 6.2.2 / 3.3: typical bars, indicator lines and marks laid out outside the members,
            # before the sheets so each viewport takes its calling-up in
            import rebar_presentation
            from nosa_utils import tag_engine
            mra_type_id = tag_engine.mra_type_id(doc)
            for view, _spec, _scale in created:
                rebar_presentation.apply(doc, view, rebars, rebar_detailing, mra_type_id, hosts=hosts)
        if place_on_sheets and created and titleblock is not None:
            import rc_legends
            legends = rc_legends.ensure(doc)
            report['sheets'] = _place_on_sheets(doc, created, titleblock, sheet_numbers, view_plan,
                                                u'{} {} reinforcement'.format(_TITLES.get(kind, u''), label),
                                                retag=None, legends=legends)   # the presentation laid the tags out
            if report['sheets']:
                # SMDSC 4.5.1: the member's bar schedules belong to the drawing it is detailed on
                import bar_schedules
                bar_schedules.stamp_drawing(doc, rebars, report['sheets'][0])
        if tag and rebars:
            # T8.27, SMDSC 6.2.2: bars detailed on another drawing, once the views are on their sheets
            own = set(get_id_value(r.Id) for r in rebars)
            for view, _spec, _scale in created:
                others = [r for r in DB.FilteredElementCollector(doc, view.Id).OfClass(DB.Structure.Rebar)
                          if get_id_value(r.Id) not in own]
                rebar_presentation.see_drawing(doc, view, others)
    except Exception as e:
        t.RollBack()
        report['errors'].append(u'{} {}: {}'.format(_TITLES.get(kind, u''), label, e))
        report['views'], report['sheets'], report['tags'] = [], [], 0
        return report
    if t.Commit() != DB.TransactionStatus.Committed or guard.errors:
        report['errors'].append(u'{} {}: rolled back by Revit — {}'.format(
            _TITLES.get(kind, u''), label, u'; '.join(guard.errors)))
        report['views'], report['sheets'], report['tags'] = [], [], 0
        return report
    report['views'] = [element_name(v) for v, _s, _sc in created]
    # Revit drops the tags of bars hidden in a view when the transaction commits: count what stays
    report['tags'] = sum(DB.FilteredElementCollector(doc, v.Id).OfCategory(
        DB.BuiltInCategory.OST_RebarTags).GetElementCount() for v, _s, _sc in created)
    return report
