# -*- coding: utf-8 -*-
"""Template/test model: re-render the BS 8666 sketches of the shapes NOSA bars use, reload their
ImageTypes and stamp every NOSA bar (what the plugin's Shape Images tool does, without its UI).
Scope: doc, EXT_ROOT, PYREVIT. Result: RESULT."""
import os
import sys
import traceback

import clr
clr.AddReference('RevitAPI')
from Autodesk.Revit import DB

for _p in (os.path.join(PYREVIT, 'pyrevitlib'), os.path.join(PYREVIT, 'site-packages'),
           os.path.join(EXT_ROOT, 'lib'),
           os.path.join(EXT_ROOT, 'NOSA.tab', 'Reinforcement.panel', 'RebarAutomate.pushbutton', 'lib')):
    if _p not in sys.path:
        sys.path.insert(0, _p)
_log = []
try:
    if u'template' not in doc.Title and u'Rebar test' not in doc.Title:
        raise RuntimeError(u'not a test model: ' + doc.Title)
    from nosa_utils.bootstrap import load_module
    lib = os.path.join(EXT_ROOT, 'NOSA.tab', 'Reinforcement.panel', 'RebarAutomate.pushbutton', 'lib')
    si = load_module('shape_images', os.path.join(lib, 'shape_images.py'))
    rebars = si.nosa_rebars(doc)
    shapes = si.shapes_of(doc, rebars)
    paths = si.render_shapes(doc, shapes)
    t = DB.Transaction(doc, u'NOSA — BS 8666 Shape Images')
    t.Start()
    done = si.stamp_bars(doc, rebars, si.image_types(doc, shapes, paths))
    t.Commit()
    _log.append(u'{} shape sketch(es) rendered, {} bar(s) stamped'.format(len(paths), done))
except Exception:
    _log.append(traceback.format_exc())
RESULT = u'\n'.join(_log)
