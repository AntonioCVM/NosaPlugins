# -*- coding: utf-8 -*-
"""Family Audit Logic — inspect, score and purge Revit families."""
import io, sys, os, csv
from pyrevit import DB

_lib = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', 'lib'))
if _lib not in sys.path:
    sys.path.insert(0, _lib)
from nosa_utils.revit_helpers import get_id_value

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
            pass
        fam_doc.Close(False)
        return round(size_bytes / (1024 * 1024), 3)
    except Exception:
        return 0.0


def _instance_count(doc, family):
    """Count placed instances of all types belonging to this family."""
    try:
        type_ids = family.GetFamilySymbolIds()
        total = 0
        for tid in type_ids:
            col = DB.FilteredElementCollector(doc)\
                    .WhereElementIsNotElementType()\
                    .OfClass(DB.FamilyInstance)
            for inst in col:
                try:
                    if inst.Symbol is not None and inst.Symbol.Id == tid:
                        total += 1
                except Exception:
                    pass
        return total
    except Exception:
        return 0


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
        'id':           ElementId,
        'name':         str,
        'category':     str,
        'type_count':   int,
        'instance_count': int,
        'size_mb':      float,
        'completeness': float,   # 0.0 – 1.0
        'is_editable':  bool,    # False for system/in-place families
      }
    Sorted by (category, name).
    """
    col = DB.FilteredElementCollector(doc)\
          .OfClass(DB.Family)\
          .ToElements()

    rows = []
    for fam in col:
        try:
            cat_name = fam.FamilyCategory.Name if fam.FamilyCategory else '—'
            type_count = len(list(fam.GetFamilySymbolIds()))
            is_editable = fam.IsEditable

            # Instance count: use a simpler collector per family
            inst_count = _fast_instance_count(doc, fam)

            # Parameter completeness (lightweight version, no EditFamily needed)
            completeness = _param_completeness(fam)

            # Size: only attempt if editable (opening in-place families crashes)
            size_mb = 0.0

            rows.append({
                'id':             fam.Id,
                'name':           fam.Name,
                'category':       cat_name,
                'type_count':     type_count,
                'instance_count': inst_count,
                'size_mb':        size_mb,
                'completeness':   completeness,
                'is_editable':    is_editable,
                'family':         fam,
            })
        except Exception:
            pass

    rows.sort(key=lambda r: (r['category'], r['name'].lower()))
    return rows


def _fast_instance_count(doc, family):
    """
    Count FamilyInstance elements whose Symbol belongs to this family.
    Uses a per-family-symbol collector for speed.
    """
    try:
        type_ids = set(get_id_value(tid) for tid in family.GetFamilySymbolIds())
        if not type_ids:
            return 0
        col = DB.FilteredElementCollector(doc)\
                .WhereElementIsNotElementType()\
                .OfClass(DB.FamilyInstance)\
                .ToElements()
        count = 0
        for inst in col:
            try:
                sym = inst.Symbol
                if sym is not None and get_id_value(sym.Id) in type_ids:
                    count += 1
            except Exception:
                pass
        return count
    except Exception:
        return 0


def purge_families(doc, family_ids):
    """
    Delete the given family ElementIds from the document.
    Returns (deleted_count, failed_ids).
    """
    deleted = 0
    failed  = []
    id_set  = DB.ICollection[DB.ElementId](list(family_ids))
    with DB.Transaction(doc, "Family Audit — Purge Families") as t:
        t.Start()
        try:
            doc.Delete(id_set)
            deleted = len(family_ids)
        except Exception:
            # Fall back to deleting one by one
            for fid in family_ids:
                try:
                    doc.Delete(DB.ICollection[DB.ElementId]([fid]))
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
