# -*- coding: utf-8 -*-
import os, sys

from Autodesk.Revit import DB

_lib = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', '..', 'lib'))
if _lib not in sys.path:
    sys.path.insert(0, _lib)

from nosa_utils.revit_helpers import get_id_value, element_name

_CATEGORIES = [
    (u'Walls',             'OST_Walls'),
    (u'Floors',            'OST_Floors'),
    (u'Roofs',             'OST_Roofs'),
    (u'Columns',           'OST_Columns'),
    (u'Structural Columns','OST_StructuralColumns'),
    (u'Structural Framing','OST_StructuralFraming'),
    (u'Structural Foundations', 'OST_StructuralFoundation'),
    (u'Doors',             'OST_Doors'),
    (u'Windows',           'OST_Windows'),
    (u'Generic Models',    'OST_GenericModel'),
    (u'Furniture',         'OST_Furniture'),
    (u'Mechanical Equipment', 'OST_MechanicalEquipment'),
    (u'Electrical Fixtures','OST_ElectricalFixtures'),
    (u'Plumbing Fixtures', 'OST_PlumbingFixtures'),
    (u'Pipe Types',        'OST_PipeRun'),
    (u'Duct Types',        'OST_DuctCurves'),
]


def category_names():
    return [c[0] for c in _CATEGORIES]


def get_types_for_category(doc, category_name):
    bic_name = None
    for label, name in _CATEGORIES:
        if label == category_name:
            bic_name = name
            break
    if bic_name is None:
        return []

    bic = getattr(DB.BuiltInCategory, bic_name, None)
    if bic is None:
        return []

    types = list(
        DB.FilteredElementCollector(doc)
        .OfCategory(bic)
        .WhereElementIsElementType()
        .ToElements()
    )

    result = []
    for t in types:
        try:
            name = t.get_Parameter(DB.BuiltInParameter.SYMBOL_NAME_PARAM)
            display = name.AsString() if name else u''
            if not display:
                display = element_name(t)
            result.append({'id': get_id_value(t.Id), 'name': display, 'element': t})
        except Exception:
            pass
    return sorted(result, key=lambda r: r['name'].lower())


def preview_rename(names, mode, find, replace, prefix, suffix):
    results = []
    for name in names:
        if mode == 'find_replace':
            new_name = name.replace(find, replace) if find else name
        else:
            new_name = u'{}{}{}'.format(prefix, name, suffix)
        results.append((name, new_name))
    return results


def apply_renames(doc, pairs):
    renamed = 0
    failed = 0
    errors = []
    with DB.Transaction(doc, u'NOSA — Rename types') as t:
        t.Start()
        for el, new_name in pairs:
            try:
                el.Name = new_name
                renamed += 1
            except Exception as ex:
                failed += 1
                errors.append(u'{} → {}: {}'.format(element_name(el), new_name, ex))
        t.Commit()
    return renamed, failed, errors
