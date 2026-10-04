# -*- coding: utf-8 -*-
"""
T8.20 / T8.21 / T8.24 on template v30, approved by the user on 2026-10-04: revision sequences
aligned with the naming protocol, UK steel (Tata/Corus Advance UKB, UKC, UKPFC, CHS) as beams and
columns with every catalogue type, schedule typos, Rebar Schedule removed, Uniclass fields added.
Revit refuses family loads after ~100 types in one external call, so ONLY picks one part per call:
'revisions_schedules' or a family file basename. Scope: doc, EXT_ROOT, PYREVIT, DRY (bool: roll back),
OUT (log file), ONLY. Result: RESULT.
"""
import sys
import os
import io
import traceback

import clr
clr.AddReference('RevitAPI')
from Autodesk.Revit import DB

for _p in (os.path.join(PYREVIT, 'pyrevitlib'), os.path.join(PYREVIT, 'site-packages'),
           os.path.join(EXT_ROOT, 'lib')):
    if _p not in sys.path:
        sys.path.insert(0, _p)

_LIB = r'C:\ProgramData\Autodesk\RVT 2024\Libraries\English\UK'
UK_STEEL = [os.path.join(_LIB, u'Structural Framing', u'Steel', u'Corus Advance', n + u'.rfa')
            for n in (u'UKB-UK Beams', u'UKC-UK Columns', u'UKPFC-Parallel Flange Channels',
                      u'CHS-Circular Hollow Sections')] + \
           [os.path.join(_LIB, u'Structural Columns', u'Steel', u'Corus Advance', n + u'.rfa')
            for n in (u'UKB-UK Beams-Column', u'UKC-UK Columns-Column', u'UKPFC-Parallel Flange Channels-Column',
                      u'CHS-Circular Hollow Sections-Column')]
SCHEDULE_RENAME = {u'Concrete volume estimation - RC Stairscases': u'Concrete volume estimation - RC Staircases'}
PARAM_RENAME = {u'Comlumns estimated rebar': u'Columns estimated rebar'}
SCHEDULE_DELETE = [u'Rebar Schedule']
UNICLASS_SCHEDULES = [u'Foundation types Schedule', u'Individual Foundation Schedule', u'Piling Schedule',
                      u'Structural Column Schedule']
UNICLASS_FIELDS = [u'UniclassCode', u'UniclassDescription']

_log = []


def catalogue_types(rfa):
    txt = os.path.splitext(rfa)[0] + u'.txt'
    if not os.path.exists(txt):
        return []
    with io.open(txt, encoding='utf-16' if open(txt, 'rb').read(2) in (b'\xff\xfe', b'\xfe\xff') else 'utf-8') as f:
        rows = f.read().splitlines()[1:]
    return [r.split(u',')[0].strip() for r in rows if r.strip()]


def run():
    from nosa_utils.revit_helpers import element_name
    from nosa_utils import transactions as nosa_tx

    def col(cls):
        return list(DB.FilteredElementCollector(doc).OfClass(cls))

    group = DB.TransactionGroup(doc, u'NOSA — Template revisions, UK steel and schedules (T8.20/21/24)')
    group.Start()
    collector = nosa_tx.FailureCollector()

    def start(name):
        tx = DB.Transaction(doc, name)
        nosa_tx._install(tx, collector)
        tx.Start()
        return tx
    try:
        only = ONLY
    except NameError:
        only = None
    t = start(u'NOSA — Revision sequences')
    try:
        # T8.20 revision sequences
        sequences = col(DB.RevisionNumberingSequence) if only in (None, u'revisions_schedules') else []
        for s in sequences:
            if s.SequenceName == u'Constractual':
                s.SequenceName = u'Contractual'
                _log.append(u'sequence renamed: Contractual')
            if s.SequenceName == u'Post-contractual' and s.NumberType == DB.RevisionNumberType.Numeric:
                ns = s.GetNumericRevisionSettings()
                ns.MinimumDigits = 2
                s.SetNumericRevisionSettings(ns)
                _log.append(u'Post-contractual now PC{:02d}'.format(ns.StartNumber))

        t.Commit()
        # T8.21 UK steel: one transaction per family (Revit refuses loads after ~100 in one)
        for rfa in UK_STEEL:
            if only is not None and only != os.path.splitext(os.path.basename(rfa))[0]:
                continue
            t = start(u'NOSA — Load ' + os.path.basename(rfa))
            if not os.path.exists(rfa):
                _log.append(u'missing family file: ' + rfa)
                continue
            fam_name = os.path.splitext(os.path.basename(rfa))[0]
            family = [f for f in col(DB.Family) if f.Name == fam_name]
            have = set()
            if family:
                have = set(element_name(doc.GetElement(i)) for i in family[0].GetFamilySymbolIds())
            loaded, failed = 0, []
            for name in catalogue_types(rfa):
                if name in have:
                    continue
                try:
                    if doc.LoadFamilySymbol(rfa, name):
                        loaded += 1
                except Exception as e:
                    failed.append(u'{} ({})'.format(name, e))
            _log.append(u'{}: {} types loaded ({} already there){}'.format(
                fam_name, loaded, len(have), u'; FAILED {}: {}'.format(len(failed), u', '.join(failed[:3])) if failed else u''))
            t.Commit()

        # T8.24 schedules
        t = start(u'NOSA — Schedules')
        if only not in (None, u'revisions_schedules'):
            t.Commit()
            raise StopIteration()
        for s in col(DB.ViewSchedule):
            if s.Name in SCHEDULE_RENAME:
                s.Name = SCHEDULE_RENAME[s.Name]
                _log.append(u'schedule renamed: ' + s.Name)
        placed = set(i.ScheduleId for i in col(DB.ScheduleSheetInstance))
        for s in [s for s in col(DB.ViewSchedule) if s.Name in SCHEDULE_DELETE]:
            if s.Id in placed or not DB.DocumentValidation.CanDeleteElement(doc, s.Id):
                _log.append(u'NOT deleted (placed on a sheet or Revit does not allow it): ' + s.Name)
                continue
            doc.Delete(s.Id)
            _log.append(u'schedule deleted: ' + s.Name)
        for p in col(DB.ParameterElement):
            if p.Name in PARAM_RENAME:
                if isinstance(p, DB.SharedParameterElement):
                    _log.append(u'"{}" is a shared parameter: rename it in the shared file'.format(p.Name))
                else:
                    p.Name = PARAM_RENAME[p.Name]
                    _log.append(u'parameter renamed: ' + p.Name)
        for s in col(DB.ViewSchedule):
            if s.Name not in UNICLASS_SCHEDULES:
                continue
            d = s.Definition
            present = set(d.GetField(i).GetName() for i in range(d.GetFieldCount()))
            added = []
            for sf in d.GetSchedulableFields():
                name = sf.GetName(doc)
                if name in UNICLASS_FIELDS and name not in present:
                    d.AddField(sf)
                    present.add(name)
                    added.append(name)
            _log.append(u'{}: Uniclass fields added {}'.format(s.Name, added or u'none (not schedulable here)'))
        t.Commit()
    except StopIteration:
        pass
    except Exception:
        if t.HasStarted() and not t.HasEnded():
            t.RollBack()
        group.RollBack()
        _log.append(u'EXCEPTION, rolled back:\n' + traceback.format_exc())
        return
    if DRY:
        group.RollBack()
        _log.append(u'DRY RUN: rolled back')
    else:
        _log.append(u'commit: {}'.format(group.Assimilate()))
    if collector.warnings:
        _log.append(u'warnings cleared: {}'.format(u' | '.join(sorted(set(collector.warnings))[:8])))
    if collector.errors:
        _log.append(u'REVIT ERRORS (rolled back): {}'.format(u' | '.join(collector.errors[:8])))


try:
    run()
except Exception:
    _log.append(traceback.format_exc())
RESULT = u'\n'.join(_log)
try:
    with io.open(OUT, 'w', encoding='utf-8') as _f:
        _f.write(RESULT)
except NameError:
    pass
