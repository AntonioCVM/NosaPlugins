# -*- coding: utf-8 -*-
"""
NOSA.RebarAutomate — BS 8666 shape images (T7.5): the sketch of every RebarShape (Revit's own
shape-browser geometry, its dimension letters beside each segment) drawn to a PNG, stored on each
bar's NOSA_Rebar_Shape_Image (an Image parameter the BBS schedule shows) and reused by the Excel
export. Revit keeps a RebarShape's own 'Shape Image' read-only for the API (system shapes have no
family to edit), hence the bar parameter (2026-10-03).
Drawn in pure Python: System.Drawing from IronPython crashed Revit 2024 (2026-10-03).
"""
from __future__ import absolute_import, division, print_function, unicode_literals
import os
import re
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import shape_sketch

_FT = 304.8
IMAGE_PREFIX = u'NOSA_BS8666_'
SHAPE_IMAGE_FIELD = u'NOSA_Rebar_Shape_Image'


def image_folder():
    base = os.path.join(os.environ.get('APPDATA', _HERE), 'pyRevit', 'Extensions', 'NOSA.extension',
                        'NOSA_Configs', 'shape_sketches')
    if not os.path.isdir(base):
        os.makedirs(base)
    return base


def file_name(shape_name):
    return IMAGE_PREFIX + re.sub(r'[^A-Za-z0-9_-]+', u'_', shape_name or u'shape') + u'.png'


def _param_name(doc, param_id):
    from nosa_utils.revit_helpers import element_name
    element = doc.GetElement(param_id)
    return element_name(element) if element is not None else u''


def sketch_of(doc, shape):
    """(polylines in mm, one letter per polyline) from the shape's browser curves."""
    from Autodesk.Revit import DB  # Lazy import
    from Autodesk.Revit.DB import Structure as DBS
    polylines, kinds = [], []
    for curve in shape.GetCurvesForBrowser():
        pts = [(p.X * _FT, p.Y * _FT) for p in curve.Tessellate()]
        polylines.append(pts)
        kinds.append('arc' if not isinstance(curve, DB.Line) else 'line')
    definition = shape.GetRebarShapeDefinition()
    labels = [u''] * len(polylines)
    if isinstance(definition, DBS.RebarShapeDefinitionBySegments):
        names = []
        for i in range(definition.NumberOfSegments):
            name = u''
            for constraint in definition.GetSegment(i).GetConstraints():
                if isinstance(constraint, DBS.RebarShapeConstraintSegmentLength):
                    name = _param_name(doc, constraint.GetParamId())
                    break
            names.append(name)
        if len(names) == len(polylines):
            labels = names
        else:                                 # extra bend arcs in the sketch: letters on the straights
            straight = [i for i, k in enumerate(kinds) if k == 'line']
            for i, name in zip(straight, names):
                labels[i] = name
    elif polylines:
        # arc shapes (BS 8666 67, 75, 77): the definition lists every shape parameter of the
        # family, so only the arc's own dimension letter is written
        labels[0] = u'A'
    return polylines, labels


def render_png(path, polylines, labels):
    """Draw the sketch and its letters to a 300 dpi PNG (pure Python: png_sketch)."""
    import png_sketch
    pixel_lines, _to_px = shape_sketch.fit(polylines)
    canvas = png_sketch.draw_sketch(pixel_lines, shape_sketch.label_positions(pixel_lines, labels),
                                    shape_sketch.WIDTH, shape_sketch.HEIGHT)
    with open(path, 'wb') as f:
        f.write(canvas.png())
    return path


def render_shapes(doc, shapes, folder=None):
    """{shape id value: png path} for the given RebarShapes."""
    from nosa_utils.revit_helpers import element_name, get_id_value
    folder = folder or image_folder()
    out = {}
    for shape in shapes:
        try:
            polylines, labels = sketch_of(doc, shape)
            if not polylines:
                continue
            out[get_id_value(shape.Id)] = render_png(
                os.path.join(folder, file_name(element_name(shape))), polylines, labels)
        except Exception:
            continue
    return out


def all_shapes(doc):
    from Autodesk.Revit import DB  # Lazy import
    from Autodesk.Revit.DB import Structure as DBS
    return list(DB.FilteredElementCollector(doc).OfClass(DBS.RebarShape))


def _image_file(image):
    try:
        return os.path.basename(image.Path or u'')
    except Exception:
        return u''


def image_types(doc, shapes, paths):
    """
    {shape id value: ImageType id}, one ImageType per PNG (reloaded when it exists). In a transaction.
    The ImageType is named by the bare shape code ("21"): a BBS schedule view lists the image by
    name, so it reads like the shape code column; the sheet shows the sketch itself.
    """
    from Autodesk.Revit import DB  # Lazy import
    from nosa_utils.revit_helpers import element_name, get_id_value
    images = {}
    for i in DB.FilteredElementCollector(doc).OfClass(DB.ImageType):
        images[_image_file(i) or element_name(i)] = i
    out = {}
    for shape in shapes:
        path = paths.get(get_id_value(shape.Id))
        if not path:
            continue
        options = DB.ImageTypeOptions(path, False, DB.ImageTypeSource.Import)
        image = images.get(os.path.basename(path))
        if image is None:
            image = DB.ImageType.Create(doc, options)
            images[os.path.basename(path)] = image
        else:
            image.ReloadFrom(options)
        code = (element_name(shape) or u'').strip()
        if code and element_name(image) != code:
            try:
                image.Name = code
            except Exception:  # nosa-lint: disable=NOSA006 - name taken: the file name stays
                pass
        out[get_id_value(shape.Id)] = image.Id
    return out


def _shape_id(rebar):
    """The bar's RebarShape id, or None for a FreeForm bundle of several shapes (no single sketch)."""
    try:
        return rebar.GetShapeId()
    except Exception:  # nosa-lint: disable=NOSA006 - "matched with multiple shapes": no sketch
        return None


def stamp_bars(doc, rebars, image_ids):
    """Point every bar's NOSA_Rebar_Shape_Image at the sketch of its shape. In a transaction."""
    from nosa_utils.revit_helpers import get_id_value
    done = 0
    for rebar in rebars:
        shape_id = _shape_id(rebar)
        image_id = image_ids.get(get_id_value(shape_id)) if shape_id is not None else None
        param = rebar.LookupParameter(SHAPE_IMAGE_FIELD)
        if image_id is None or param is None or param.IsReadOnly:
            continue
        if param.Set(image_id):
            done += 1
    return done


def nosa_rebars(doc):
    from Autodesk.Revit import DB  # Lazy import
    from nosa_utils import shared_params
    return [r for r in DB.FilteredElementCollector(doc).OfCategory(DB.BuiltInCategory.OST_Rebar)
            .WhereElementIsNotElementType() if shared_params.read(r, u'NOSA_Rebar_Batch_Id')]


def shapes_of(doc, rebars):
    seen, out = set(), []
    for rebar in rebars:
        shape_id = _shape_id(rebar)
        shape = doc.GetElement(shape_id) if shape_id is not None else None
        if shape is not None and shape.Id not in seen:
            seen.add(shape.Id)
            out.append(shape)
    return out


def add_shape_image_column(doc, schedule, after=u'Shape'):
    """Add the 'Shape Image' field to a rebar schedule, after its shape code; False if already there."""
    definition = schedule.Definition
    for i in range(definition.GetFieldCount()):
        if definition.GetField(i).GetName() == SHAPE_IMAGE_FIELD:
            return False
    field_def = None
    for schedulable in definition.GetSchedulableFields():
        if schedulable.GetName(doc) == SHAPE_IMAGE_FIELD:
            field_def = schedulable
            break
    if field_def is None:
        return False
    index = definition.GetFieldCount()
    for i in range(definition.GetFieldCount()):
        if definition.GetField(i).GetName() == after:
            index = i + 1
            break
    field = definition.InsertField(field_def, index)
    field.ColumnHeading = u'Shape'
    return True
