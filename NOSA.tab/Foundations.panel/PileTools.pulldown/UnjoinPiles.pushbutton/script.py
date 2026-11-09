# -*- coding: utf-8 -*-
__title__   = "Unjoin\nPiles"
__version__ = "1.0"
__doc__     = "Unjoins pile caps from their nested piles so the embedment (PILE_Embedment) stays visible."
__author__  = "A. Viñas"

from Autodesk.Revit import DB
from pyrevit import revit, forms

doc = revit.doc


def _is_foundation(el):
    cat = el.Category
    return cat is not None and cat.Id.IntegerValue == int(DB.BuiltInCategory.OST_StructuralFoundation)


def _targets():
    sel = [doc.GetElement(i) for i in revit.uidoc.Selection.GetElementIds()]
    sel = [e for e in sel if isinstance(e, DB.FamilyInstance)]
    if sel:
        return sel
    return list(DB.FilteredElementCollector(doc)
                .OfClass(DB.FamilyInstance)
                .OfCategory(DB.BuiltInCategory.OST_StructuralFoundation))


def run():
    pairs = []
    for cap in _targets():
        try:
            sub_ids = list(cap.GetSubComponentIds())
        except Exception:
            continue
        for sid in sub_ids:
            sub = doc.GetElement(sid)
            if sub is None or not _is_foundation(sub):
                continue
            try:
                if DB.JoinGeometryUtils.AreElementsJoined(doc, cap, sub):
                    pairs.append((cap, sub))
            except Exception:
                pass
    if not pairs:
        forms.alert(u"No joined cap/pile pairs found.", title=u"NOSA — Unjoin Piles")
        return
    done = 0
    with DB.Transaction(doc, u"NOSA — Unjoin Piles") as t:
        t.Start()
        for cap, sub in pairs:
            try:
                DB.JoinGeometryUtils.UnjoinGeometry(doc, cap, sub)
                done += 1
            except Exception:
                pass
        t.Commit()
    forms.alert(u"Unjoined {0} of {1} cap/pile pairs.".format(done, len(pairs)),
                title=u"NOSA — Unjoin Piles")


run()
