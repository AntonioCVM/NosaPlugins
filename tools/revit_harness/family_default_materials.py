# -*- coding: utf-8 -*-
"""
Template families: default Structural Material so every element lands in the right schedule
(user 2026-10-05): concrete columns, pads and pile caps -> Concrete - RC32/40; concrete piles -> Piling
concrete; steel pipe piles -> Structural Steel - S355; UK library steel 43-275 / 50-355 -> NOSA S275 / S355.
Only blank values or the two UK library materials are changed. GENERIC=True (user 2026-10-05, later
decision): every concrete family -> Concrete - Generic, every steel family -> Structural Steel - Generic,
concrete piles -> Piling concrete, all types overwritten. Scope: doc, EXT_ROOT, PYREVIT, FAMILIES (list of
family names, or empty for every concrete/steel structural family), START/COUNT (batch), GENERIC, OUT.
Result: RESULT.
"""
import io
import os
import sys
import traceback

import clr
clr.AddReference('RevitAPI')
from Autodesk.Revit import DB

for _p in (os.path.join(PYREVIT, 'pyrevitlib'), os.path.join(PYREVIT, 'site-packages'),
           os.path.join(EXT_ROOT, 'lib')):
    if _p not in sys.path:
        sys.path.insert(0, _p)

DEFAULTS = {
    u'Concrete Rectangular': u'Concrete - RC32/40', u'Concrete Round': u'Concrete - RC32/40',
    u'Concrete Square': u'Concrete - RC32/40', u'RC Pad foundation': u'Concrete - RC32/40',
    u'Pile Square piling': u'Piling concrete', u'Pile-Steel Pipe Circular': u'Structural Steel - S355',
}
for _n in range(1, 10):
    DEFAULTS[u'Pile Cap-{} Pile'.format(_n)] = u'Concrete - RC32/40'
CONCRETE_PILES = (u'Pile Square piling',)
UNIFY = {u'Metal - Steel 43-275': u'Structural Steel - S275', u'Metal - Steel 50-355': u'Structural Steel - S355'}
_log = []


def _options():
    class _Load(DB.IFamilyLoadOptions):
        def OnFamilyFound(self, family_in_use, overwrite):
            return True, True

        def OnSharedFamilyFound(self, shared_family, family_in_use, source, overwrite):
            return True, DB.FamilySource.Project, False     # nested piles keep the project's version
    return _Load()


def _material(fam_doc, name):
    for m in DB.FilteredElementCollector(fam_doc).OfClass(DB.Material):
        if m.Name == name:
            return m.Id
    return DB.Material.Create(fam_doc, name)      # the project's material of the same name wins on load


def _generic_target(family):
    if family.Name in CONCRETE_PILES:
        return u'Piling concrete'
    if family.Name in (u'RC Pad foundation',):          # material type "Other" in the family, but concrete
        return u'Concrete - Generic'
    kind = u'{}'.format(family.StructuralMaterialType)
    if kind.endswith(u'Concrete') or kind.endswith(u'PrecastConcrete'):
        return u'Concrete - Generic'
    if kind.endswith(u'Steel'):
        return u'Structural Steel - Generic'
    return None


def fix(family, use_generic=False):
    name = family.Name          # the project Family object is replaced by LoadFamily
    generic = _generic_target(family) if use_generic else None
    if use_generic and generic is None:
        return u'{}: skipped ({})'.format(name, family.StructuralMaterialType)
    fam_doc = doc.EditFamily(family)
    try:
        fm = fam_doc.FamilyManager
        param = fm.get_Parameter(DB.BuiltInParameter.STRUCTURAL_MATERIAL_PARAM)
        if param is None:
            for p in fm.Parameters:
                if p.Definition.Name == u'Structural Material':
                    param = p
        if param is None:
            return u'{}: no Structural Material parameter'.format(name)
        changes = []
        t = DB.Transaction(fam_doc, u'NOSA default material')
        t.Start()
        for ft in list(fm.Types):
            fm.CurrentType = ft
            current = ft.AsElementId(param)
            cur_name = fam_doc.GetElement(current).Name if current and current != DB.ElementId.InvalidElementId \
                and fam_doc.GetElement(current) is not None else u''
            if generic:
                target = generic
            else:
                target = UNIFY.get(cur_name) or (DEFAULTS.get(name) if not cur_name else None)
            if target == cur_name:
                continue
            if target:
                fm.Set(param, _material(fam_doc, target))
                changes.append(u'{}: {} -> {}'.format(ft.Name, cur_name or u'(none)', target))
        if not changes:
            t.RollBack()
            return u'{}: nothing to change'.format(name)
        t.Commit()
        fam_doc.LoadFamily(doc, _options())
        sample = changes[0] if len(changes) == 1 else u'{} ... ({} types)'.format(changes[0], len(changes))
        return u'{}: {}'.format(name, sample)
    finally:
        fam_doc.Close(False)


try:
    try:
        use_generic = bool(GENERIC)
    except NameError:
        use_generic = False
    families = dict((f.Name, f) for f in DB.FilteredElementCollector(doc).OfClass(DB.Family))
    wanted = [n for n in (list(FAMILIES) if FAMILIES else [])]
    if not wanted:
        cats = set(DB.Category.GetCategory(doc, getattr(DB.BuiltInCategory, c)).Id.IntegerValue  # nosa-lint: disable=NOSA002 - harness script runs in Revit
                   for c in ('OST_StructuralFraming', 'OST_StructuralColumns', 'OST_StructuralFoundation'))
        wanted = sorted(n for n, f in families.items()
                        if f.FamilyCategory is not None and f.FamilyCategory.Id.IntegerValue in cats and
                        f.IsEditable)
        try:
            wanted = wanted[START:START + COUNT]
        except NameError:
            pass
    for name in wanted:
        if name not in families:
            _log.append(u'{}: not in the model'.format(name))
            continue
        try:
            _log.append(fix(families[name], use_generic))
        except Exception as e:
            _log.append(u'{}: FAILED {}'.format(name, e))
except Exception:
    _log.append(traceback.format_exc())
RESULT = u'\n'.join(_log)
try:
    with io.open(OUT, 'a', encoding='utf-8') as fh:
        fh.write(RESULT + u'\n')
except NameError:
    pass
