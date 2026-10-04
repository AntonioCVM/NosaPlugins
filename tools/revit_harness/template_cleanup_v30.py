# -*- coding: utf-8 -*-
"""
T8.18 — template v30 cleanup approved by the user on 2026-10-04 (list A + dimensions to
NOSA Dimensions 2.0mm + Phase-* materials + copied stair types). One guarded transaction; a Revit
error rolls everything back. Scope: doc, EXT_ROOT, PYREVIT, DRY (bool: roll back at the end).
Result: RESULT.
"""
import sys
import os
import traceback

import clr
clr.AddReference('RevitAPI')
from Autodesk.Revit import DB

for _p in (os.path.join(PYREVIT, 'pyrevitlib'), os.path.join(PYREVIT, 'site-packages'),
           os.path.join(EXT_ROOT, 'lib')):
    if _p not in sys.path:
        sys.path.insert(0, _p)

LINE_PATTERNS = [u'Aligning Line 1/8"', u'Center 1/4"', u'Dash 1/8"', u'Dash Dot 3/16"', u'Demolished 3/16"',
                 u'Dot 1/32"', u'Dot 1/8"', u'Double Dash 3/8"', u'Hidden 1/8"', u'Hidden 3/32"',
                 u'Loose Dash 1/16"', u'Overhead 1/16"',
                 u'Centro', u'Derribado', u'Elevado', u'Línea de alineación',
                 u'Líneas de recubrimiento de armadura', u'Oculto', u'Punto', u'Trazo', u'Trazo doble',
                 u'Trazo holgado', u'Trazo largo', u'Trazo punto', u'Trazo punto punto', u'Trazo triple',
                 u'Long dash']
LINE_RENAME = {u'Dash 1/16"': u'Dash 1.6mm'}
MATERIALS = [u'Cubierta por defecto', u'Muro por defecto', u'Origen de luz por defecto', u'Por defecto',
             u'Vidrio', u'Relleno', u'Material de renderización 0-0-0', u'Material de renderización 255-255-255',
             u'Phase-Demo', u'Phase-Exist', u'Phase-Temp']
FILL_PATTERNS = [u'Diagonal abajo', u'Diagonal arriba', u'Sombreado de líneas cruzadas',
                 u'Sombreado de líneas cruzadas diagonal', u'Diagonal crosshatch']
IMAGES = [u'3D - Antonio-Nosa structure foundation.png',
          u'22041-NOSA-DT-ZZ-D-S-4100-P01-Substructure details - Sheet 1.png', u'NOSA Teams background v2.0.png']
DIM_TO_NOSA = [u'Linear Dimension Style']           # every Linear type of that name -> NOSA Dimensions 2.0mm
DIM_DELETE = [u'Linear Dimension Style', u'Arrow - 2.5mm Arial']
DIM_FONT = [u'Dimensions 1.5mm', u'Diameter Dimension Style']
STAIR_COPIES = [u'50 mm Tread 13 mm Riser (1)', u'Stringer - 50 mm Width (1)', u'Stringer - 50 mm Width (2)',
                u'Stringer - 50 mm Width (3)']
FAKE_GUIDS = [u'11111111-1111-1111-1111-111111111101', u'11111111-1111-1111-1111-111111111102',
              u'11111111-1111-1111-1111-111111111103']
VIEW_RENAME = {u'Simbolos': u'Symbols'}

_log = []


def run():
    from nosa_utils.revit_helpers import element_name, get_id_value
    from nosa_utils import transactions as nosa_tx

    def col(cls):
        return list(DB.FilteredElementCollector(doc).OfClass(cls))

    def by_names(cls, names):
        found = [e for e in col(cls) if element_name(e) in names]
        missing = set(names) - set(element_name(e) for e in found)
        if missing:
            _log.append(u'not found {}: {}'.format(cls.__name__, u', '.join(sorted(missing))))
        return found

    deleted = {}

    def delete(kind, elements):
        n = 0
        for e in elements:
            try:
                doc.Delete(e.Id)
                n += 1
            except Exception as ex:
                _log.append(u'could not delete {} "{}": {}'.format(kind, element_name(e), ex))
        deleted[kind] = deleted.get(kind, 0) + n

    t = DB.Transaction(doc, u'NOSA — Template cleanup (T8.18)')
    collector = nosa_tx.FailureCollector()
    nosa_tx._install(t, collector)
    t.Start()
    try:
        lps = col(DB.LinePatternElement)
        delete(u'line pattern', [e for e in lps if element_name(e).startswith(u'IMPORT-')])
        delete(u'line pattern', by_names(DB.LinePatternElement, LINE_PATTERNS))
        for e in by_names(DB.LinePatternElement, list(LINE_RENAME)):
            e.Name = LINE_RENAME[element_name(e)]
        mats = col(DB.Material)
        delete(u'material', [m for m in mats if element_name(m).startswith(u'Render Material ')])
        delete(u'material', by_names(DB.Material, MATERIALS))
        delete(u'fill pattern', by_names(DB.FillPatternElement, FILL_PATTERNS))
        delete(u'image', by_names(DB.ImageType, IMAGES))

        nosa = [d for d in col(DB.DimensionType) if element_name(d) == u'NOSA Dimensions 2.0mm']
        old = [d for d in col(DB.DimensionType) if element_name(d) in DIM_TO_NOSA and
               d.StyleType == DB.DimensionStyleType.Linear]
        old_ids = set(get_id_value(d.Id) for d in old)
        retyped, kept = 0, {}
        before = len(col(DB.Dimension))

        def nosa_type_for(dim):
            valid = list(dim.GetValidTypes())
            if nosa[0].Id in valid:
                return nosa[0].Id
            for tid in valid:
                if element_name(doc.GetElement(tid)).startswith(u'NOSA'):
                    return tid
            return None
        def view_count(view_id):
            return sum(1 for d in col(DB.Dimension) if d.OwnerViewId == view_id)
        unstable = {}
        pending = [d for d in col(DB.Dimension) if get_id_value(d.GetTypeId()) in old_ids and
                   d.GroupId == DB.ElementId.InvalidElementId]   # group members: edit the group by hand
        counts = {}
        for dim in pending:
            if not dim.IsValidObject:
                continue
            target = nosa_type_for(dim)
            view = doc.GetElement(dim.OwnerViewId)
            if target is None:
                key = (get_id_value(dim.GetTypeId()), element_name(view) if view else u'?')
                kept[key] = kept.get(key, 0) + 1
                continue
            vid, view_id, old_tid = get_id_value(dim.OwnerViewId), dim.OwnerViewId, get_id_value(dim.GetTypeId())
            if vid not in counts:
                counts[vid] = view_count(view_id)
            sub = DB.SubTransaction(doc)
            sub.Start()
            dim.ChangeTypeId(target)
            doc.Regenerate()
            # Revit sometimes rebuilds a legend dimension as new ones in the old type: keep it as it was
            if not dim.IsValidObject or view_count(view_id) != counts[vid]:
                sub.RollBack()
                name = element_name(view) if view else u'?'
                unstable[name] = unstable.get(name, 0) + 1
                key = (old_tid, name)
                kept[key] = kept.get(key, 0) + 1
            else:
                sub.Commit()
                retyped += 1
        for name, n in sorted(unstable.items()):
            _log.append(u'  Revit rebuilds these when retyped, left as they were: "{}" x{}'.format(name, n))
        after = len(col(DB.Dimension))
        _log.append(u'dimensions moved to NOSA types: {} (dimensions in the model before {} after {})'.format(
            retyped, before, after))
        for key, n in sorted(kept.items()):
            _log.append(u'  no NOSA type allowed: type {} in "{}" x{}'.format(key[0], key[1], n))
        in_groups = [d for d in col(DB.Dimension) if get_id_value(d.GetTypeId()) in old_ids and
                     d.GroupId != DB.ElementId.InvalidElementId]
        for d in in_groups:
            g = doc.GetElement(d.GroupId)
            kept[(get_id_value(d.GetTypeId()), u'group ' + element_name(g))] = kept.get(
                (get_id_value(d.GetTypeId()), u'group ' + element_name(g)), 0) + 1
            _log.append(u'  left in group "{}" (view {}): type {}'.format(
                element_name(g), element_name(doc.GetElement(d.OwnerViewId)), get_id_value(d.GetTypeId())))
        still_used = set(k[0] for k in kept)
        delete(u'dimension type', [d for d in col(DB.DimensionType) if element_name(d) in DIM_DELETE and
                                   get_id_value(d.Id) not in still_used])
        for d in by_names(DB.DimensionType, DIM_FONT):
            d.get_Parameter(DB.BuiltInParameter.TEXT_FONT).Set(u'Century Gothic')

        delete(u'stair type', [e for e in DB.FilteredElementCollector(doc).WhereElementIsElementType()
                               if element_name(e) in STAIR_COPIES])

        # parameters: drop the fake-GUID copies; Revit version -> shared copy keeps the values
        shared, project = None, None
        it = doc.ParameterBindings.ForwardIterator()
        fakes = []
        while it.MoveNext():
            el = doc.GetElement(it.Key.Id)
            if isinstance(el, DB.SharedParameterElement) and u'{}'.format(el.GuidValue) in FAKE_GUIDS:
                fakes.append(el)
            if it.Key.Name == u'Revit version':
                if isinstance(el, DB.SharedParameterElement):
                    shared = el
                else:
                    project = el
        copied = 0
        if shared is not None and project is not None:
            for sheet in col(DB.ViewSheet):
                src = [p for p in sheet.GetParameters(u'Revit version') if p.Id == project.Id]
                dst = sheet.get_Parameter(shared.GuidValue)
                if src and dst is not None and src[0].HasValue and src[0].AsString():
                    if not dst.AsString():
                        dst.Set(src[0].AsString())
                    copied += 1
            fakes.append(project)
        _log.append(u'Revit version values copied to the shared parameter: {}'.format(copied))
        delete(u'parameter', fakes)

        for v in col(DB.View):
            if not v.IsTemplate and v.Name in VIEW_RENAME:
                v.Name = VIEW_RENAME[v.Name]
                _log.append(u'view renamed to {}'.format(v.Name))
    except Exception:
        t.RollBack()
        _log.append(u'EXCEPTION, rolled back:\n' + traceback.format_exc())
        return
    _log.append(u'deleted: {}'.format(u', '.join(u'{} {}'.format(n, k) for k, n in sorted(deleted.items()))))
    if DRY:
        t.RollBack()
        _log.append(u'DRY RUN: rolled back')
    else:
        status = t.Commit()
        _log.append(u'commit: {}'.format(status))
    if collector.warnings:
        _log.append(u'warnings cleared: {}'.format(u' | '.join(sorted(set(collector.warnings))[:8])))
    if collector.errors:
        _log.append(u'REVIT ERRORS (rolled back): {}'.format(u' | '.join(collector.errors[:8])))


try:
    run()
except Exception:
    _log.append(traceback.format_exc())
RESULT = u'\n'.join(_log)
