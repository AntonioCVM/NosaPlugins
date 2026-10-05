# -*- coding: utf-8 -*-
"""Read-only: render the BS 8666 sketches of the shapes NOSA bars use into FOLDER (PNG files).
Scope: doc, EXT_ROOT, PYREVIT, FOLDER, ALL (bool: every RebarShape of the model). Result: RESULT."""
import os
import sys
import traceback

import clr
clr.AddReference('RevitAPI')

for _p in (os.path.join(PYREVIT, 'pyrevitlib'), os.path.join(PYREVIT, 'site-packages'),
           os.path.join(EXT_ROOT, 'lib'),
           os.path.join(EXT_ROOT, 'NOSA.tab', 'Reinforcement.panel', 'RebarAutomate.pushbutton', 'lib')):
    if _p not in sys.path:
        sys.path.insert(0, _p)
_log = []
try:
    from nosa_utils.bootstrap import load_module
    from nosa_utils.revit_helpers import element_name
    lib = os.path.join(EXT_ROOT, 'NOSA.tab', 'Reinforcement.panel', 'RebarAutomate.pushbutton', 'lib')
    si = load_module('shape_images', os.path.join(lib, 'shape_images.py'))
    shapes = si.all_shapes(doc) if ALL else si.shapes_of(doc, si.nosa_rebars(doc))
    if not os.path.isdir(FOLDER):
        os.makedirs(FOLDER)
    paths = si.render_shapes(doc, shapes, FOLDER)
    from nosa_utils.revit_helpers import get_id_value
    bars = si.examples(doc, shapes)
    for shape in shapes:
        bar = bars.get(get_id_value(shape.Id))
        direct = None
        if bar is not None:
            try:
                direct = si.sketch_from_bar(doc, shape, bar)
            except Exception:
                direct = traceback.format_exc().splitlines()[-1]
        polylines, labels = si.sketch_of(doc, shape, bar)
        _log.append(u'{}: {} lines, letters {} | from bar: {}'.format(
            element_name(shape), len(polylines), labels,
            direct if not isinstance(direct, tuple) else u'yes ({} lines)'.format(len(direct[0]))))
    _log.append(u'{} PNG(s) in {}'.format(len(paths), FOLDER))
except Exception:
    _log.append(traceback.format_exc())
RESULT = u'\n'.join(_log)
