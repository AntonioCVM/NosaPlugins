# -*- coding: utf-8 -*-
"""Family Audit Logic — inspect, score and purge Revit families."""
import io, sys, os, csv
from Autodesk.Revit import DB
from System.Collections.Generic import List
_lib = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', '..', 'lib'))
if _lib not in sys.path:
    sys.path.insert(0, _lib)
from nosa_utils.revit_helpers import get_id_value
from nosa_utils.telemetry import log_swallowed
_LOG = u'StructuralQA/family_audit'

# StorageType.None is a reserved Python keyword — use getattr to access it
_STORAGETYPE_NONE = getattr(DB.StorageType, 'None', None)


def _size_mb(family):
    """Estimate family file size via ExtractPart if available, else 0."""
    try:
        doc = family.Document
        fam_doc = doc.EditFamily(family)
        size_bytes = 0
        try:
            # Use the family document's file size if accessible
            path = fam_doc.PathName
            if path and os.path.isfile(path):
                size_bytes = os.path.getsize(path)
        except Exception:
            log_swallowed(_LOG, u'_size_mb')
        fam_doc.Close(False)
        return round(size_bytes / (1024 * 1024), 3)
    except Exception:
        return 0.0


def _build_instance_index(doc):
    """
    Single-pass index: type ElementId value → instance count.
    O(I) where I = total FamilyInstance count in the model.
    Called once in collect_families, shared across all family rows.
    """
    idx = {}
    col = (DB.FilteredElementCollector(doc)
           .WhereElementIsNotElementType()
           .OfClass(DB.FamilyInstance))
    for inst in col:
        try:
            sym = inst.Symbol
            if sym is not None:
                k = get_id_value(sym.Id)
                idx[k] = idx.get(k, 0) + 1
        except Exception:
            log_swallowed(_LOG, u'_build_instance_index')
    return idx


def _param_completeness(family):
    """
    Average fill-rate of shared/project parameters across all types.
    Returns float 0.0–1.0.
    """
    try:
        symbols = list(family.GetFamilySymbolIds())
        if not symbols:
            return 1.0
        doc = family.Document
        scores = []
        for sid in symbols:
            sym = doc.GetElement(sid)
            if sym is None:
                continue
            params = [p for p in sym.Parameters
                      if not p.IsReadOnly and p.StorageType != _STORAGETYPE_NONE]
            if not params:
                scores.append(1.0)
                continue
            filled = sum(1 for p in params if p.HasValue)
            scores.append(filled / len(params))
        return round(sum(scores) / len(scores), 2) if scores else 1.0
    except Exception:
        return 0.0


def collect_families(doc):
    """
    Collect all loaded families and return audit rows.

    Returns list of dicts:
      {
        'id':             ElementId,
        'name':           str,
        'category':       str,
        'type_count':     int,
        'instance_count': int,
        'size_mb':        float,
        'completeness':   float,   # 0.0 – 1.0
        'is_editable':    bool,
      }
    Sorted by (category, name).
    """
    # Build instance index once — O(I) single pass over all FamilyInstances
    instance_index = _build_instance_index(doc)

    col = DB.FilteredElementCollector(doc)\
          .OfClass(DB.Family)\
          .ToElements()

    rows = []
    for fam in col:
        try:
            cat_name   = fam.FamilyCategory.Name if fam.FamilyCategory else u'—'
            type_ids   = set(get_id_value(tid) for tid in fam.GetFamilySymbolIds())
            type_count = len(type_ids)
            is_editable = fam.IsEditable

            # O(T) per family using the pre-built index — total O(F*T) = O(n)
            inst_count  = sum(instance_index.get(tid, 0) for tid in type_ids)
            completeness = _param_completeness(fam)

            rows.append({
                'id':             fam.Id,
                'name':           fam.Name,
                'category':       cat_name,
                'type_count':     type_count,
                'instance_count': inst_count,
                'size_mb':        0.0,
                'completeness':   completeness,
                'is_editable':    is_editable,
                'family':         fam,
            })
        except Exception:
            log_swallowed(_LOG, u'collect_families')

    rows.sort(key=lambda r: (r['category'], r['name'].lower()))
    return rows


def purge_families(doc, family_ids):
    """
    Delete the given family ElementIds from the document.
    Returns (deleted_count, failed_ids).
    """
    deleted = 0
    failed  = []
    id_set  = List[DB.ElementId](list(family_ids))
    with DB.Transaction(doc, u"NOSA — Family Audit — Purge Families") as t:
        t.Start()
        try:
            doc.Delete(id_set)
            deleted = len(family_ids)
        except Exception:
            # Fall back to deleting one by one
            for fid in family_ids:
                try:
                    doc.Delete(List[DB.ElementId]([fid]))
                    deleted += 1
                except Exception:
                    failed.append(fid)
        t.Commit()
    return deleted, failed


def export_to_csv(rows, path):
    """Write audit rows to a CSV file."""
    with io.open(path, 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.writer(f)
        w.writerow(['Category', 'Family Name', 'Types', 'Instances',
                    'Size (MB)', 'Param Fill %', 'Editable'])
        for r in rows:
            w.writerow([
                r['category'], r['name'], r['type_count'],
                r['instance_count'],
                '{:.3f}'.format(r['size_mb']),
                '{:.0%}'.format(r['completeness']),
                'Yes' if r['is_editable'] else 'No',
            ])
