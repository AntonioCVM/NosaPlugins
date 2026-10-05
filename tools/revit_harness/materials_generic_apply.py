# -*- coding: utf-8 -*-
"""
Template v30, user 2026-10-05: generic materials everywhere (the grade is chosen per project).
Concrete -> "Concrete - Generic", structural steel -> "Structural Steel - Generic" (created from S275),
rebar bar types -> "Steel Rebar - B500A, B or C"; concrete piles keep "Piling concrete"; blinding and
other layers untouched. Concrete materials get an EC2 Table 3.1 physical asset. Families are done by
family_default_materials.py. Scope: doc, EXT_ROOT, PYREVIT, DRY. Result: RESULT.
"""
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

CONCRETE_GENERIC = u'Concrete - Generic'
STEEL_GENERIC = u'Structural Steel - Generic'
REBAR = u'Steel Rebar - B500A, B or C'
# EC2 Table 3.1: fck, Ecm (GPa)
EC2 = {u'C25/30': (25, 31), u'C28/35': (28, 32), u'C32/40': (32, 33), u'C35/45': (35, 34), u'C40/50': (40, 35)}
ASSET_CLASS = {u'Concrete - RC25/30': u'C25/30', u'Concrete - RC28/35': u'C28/35', u'Concrete - RC32/40': u'C32/40',
               u'Concrete - RC35/45': u'C35/45', u'Concrete - RC40/50': u'C40/50',
               u'Concrete - Cast-in-Place Concrete RC35/45': u'C35/45',
               u'Concrete - Cast-in-Place Concrete RC40/50': u'C40/50', u'Precast Concrete': u'C40/50',
               u'Concrete - Generic': u'C32/40', u'Piling concrete': u'C32/40'}
STRAY_COLUMN = 1367401
_log = []


def run():
    from nosa_utils import material_groups as mg
    from nosa_utils import transactions as nosa_tx
    from nosa_utils.revit_helpers import element_name, element_id_from_int

    def mats():
        return dict((element_name(m), m) for m in DB.FilteredElementCollector(doc).OfClass(DB.Material))

    def group_of(mat_id):
        m = doc.GetElement(mat_id) if mat_id is not None else None
        if m is None or not isinstance(m, DB.Material):
            return None
        p = m.LookupParameter(mg.PARAM)
        return p.AsString() if p is not None and p.AsString() else mg.classify(element_name(m), m.MaterialClass)

    t = DB.Transaction(doc, u'NOSA — Generic materials (concrete, steel, rebar)')
    collector = nosa_tx.FailureCollector()
    nosa_tx._install(t, collector)
    t.Start()
    try:
        stray = doc.GetElement(element_id_from_int(STRAY_COLUMN))
        if stray is not None:
            doc.Delete(stray.Id)
            _log.append(u'stray template column deleted')
        m = mats()
        if STEEL_GENERIC not in m:
            new = m[u'Structural Steel - S275'].Duplicate(STEEL_GENERIC)
            _log.append(u'created {} (from S275)'.format(STEEL_GENERIC))
            m = mats()
        for name in (STEEL_GENERIC,):
            p = m[name].LookupParameter(mg.PARAM)
            if p is not None:
                p.Set(mg.STEEL)
        # EC2 physical assets for concrete materials without one
        u = DB.UnitUtils
        added = []
        template_asset = None
        for pse in DB.FilteredElementCollector(doc).OfClass(DB.PropertySetElement):
            try:
                a = pse.GetStructuralAsset()
            except Exception:
                a = None
            if a is not None and a.StructuralAssetClass == DB.StructuralAssetClass.Concrete:
                template_asset = pse
                break
        for name, cls in sorted(ASSET_CLASS.items()):
            mat = m.get(name)
            if mat is None or doc.GetElement(mat.StructuralAssetId) is not None or template_asset is None:
                continue
            fck, ecm = EC2[cls]
            pse = template_asset.Duplicate(doc, u'NOSA physical - {}'.format(name))   # must differ from the asset name
            asset = pse.GetStructuralAsset()
            asset.Name = u'NOSA {} (EC2) - {}'.format(cls, name)     # a duplicate name makes Revit refuse the asset
            asset.ConcreteCompression = u.ConvertToInternalUnits(fck, DB.UnitTypeId.Megapascals)
            asset.SetYoungModulus(u.ConvertToInternalUnits(ecm * 1000.0, DB.UnitTypeId.Megapascals))
            asset.SetPoissonRatio(0.2)
            asset.SetShearModulus(u.ConvertToInternalUnits(ecm * 1000.0 / 2.4, DB.UnitTypeId.Megapascals))
            asset.Density = u.ConvertToInternalUnits(2500.0, DB.UnitTypeId.KilogramsPerCubicMeter)
            try:
                pse.SetStructuralAsset(asset)
            except Exception as e:
                _log.append(u'  asset for {} refused: {} (name "{}")'.format(name, e, asset.Name))
                doc.Delete(pse.Id)
                continue
            mat.SetMaterialAspectByPropertySet(DB.MaterialAspect.Structural, pse.Id)
            added.append(u'{} ({})'.format(name, cls))
        _log.append(u'physical assets: {}'.format(u', '.join(added) or u'none needed'))

        concrete = m[CONCRETE_GENERIC].Id
        changed = []
        for cls in (DB.WallType, DB.FloorType, DB.RoofType, DB.CeilingType):
            for typ in DB.FilteredElementCollector(doc).OfClass(cls):
                try:
                    cs = typ.GetCompoundStructure()
                except Exception:
                    cs = None
                if cs is None:
                    continue
                hit = False
                for i in range(cs.LayerCount):
                    if group_of(cs.GetMaterialId(i)) == mg.CONCRETE and cs.GetMaterialId(i) != concrete:
                        cs.SetMaterialId(i, concrete)
                        hit = True
                if hit:
                    typ.SetCompoundStructure(cs)
                    changed.append(element_name(typ))
        for typ in DB.FilteredElementCollector(doc).WhereElementIsElementType():
            for pname in (u'Structural Material', u'Monolithic Material', u'Tread Material', u'Riser Material',
                          u'Landing Material'):
                p = typ.LookupParameter(pname)
                if p is None or p.IsReadOnly or p.StorageType != DB.StorageType.ElementId:
                    continue
                g = group_of(p.AsElementId())
                if g == mg.CONCRETE and p.AsElementId() != concrete:
                    p.Set(concrete)
                    changed.append(u'{} ({})'.format(element_name(typ), pname))
                elif g == mg.STEEL and p.AsElementId() != m[STEEL_GENERIC].Id:
                    p.Set(m[STEEL_GENERIC].Id)
                    changed.append(u'{} ({} steel)'.format(element_name(typ), pname))
        _log.append(u'types -> generic ({}): {}'.format(len(changed), u', '.join(changed)))
        rebar = []
        for bt in DB.FilteredElementCollector(doc).OfClass(DB.Structure.RebarBarType):
            p = bt.get_Parameter(DB.BuiltInParameter.MATERIAL_ID_PARAM)
            if p is not None and not p.IsReadOnly and p.AsElementId() != m[REBAR].Id:
                p.Set(m[REBAR].Id)
                rebar.append(element_name(bt))
        _log.append(u'rebar bar types -> {} ({}): {}'.format(REBAR, len(rebar), u', '.join(rebar)))
    except Exception:
        t.RollBack()
        _log.append(u'EXCEPTION, rolled back:\n' + traceback.format_exc())
        return
    if DRY:
        t.RollBack()
        _log.append(u'DRY RUN: rolled back')
    else:
        _log.append(u'commit: {}'.format(t.Commit()))
    if collector.errors:
        _log.append(u'REVIT ERRORS: ' + u' | '.join(collector.errors))


try:
    run()
except Exception:
    _log.append(traceback.format_exc())
RESULT = u'\n'.join(_log)
