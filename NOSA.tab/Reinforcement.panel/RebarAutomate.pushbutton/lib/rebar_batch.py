# -*- coding: utf-8 -*-
"""
NOSA.RebarAutomate — Batch Orchestration (Phase F1)
============================================================================

RebarBatch wraps ONE user-triggered generation run (footing, column —
whichever the caller's own `generate_fn` produces) in a single
TransactionGroup, and adds the ONE thing F1 introduces on top of the
EXISTING, unchanged geometry pipeline: stamping the mandatory
provenance fields (nosa_utils.shared_params.stamp_provenance) on every
Rebar element created.

F1 NON-NEGOTIABLE (per the F1 approval): this module NEVER changes
what geometry gets generated. `generate_fn` is whatever ui.py already
calls today (_run_reinforcement / _run_column_reinforcement,
unchanged) — RebarBatch only wraps it. If a footing/column comes out
different after F1, that is a regression in THIS file, not an
intentional change.

Architecture: this module never imports ui.py or a typology module
(column_rebar.py, footing_rebar.py, ...) — it only knows the SHAPE its
caller's `generate_fn` callable returns: (created_rebars, summary).
This keeps rebar_batch.py fully decoupled, matching the blueprint's
own "los modulos de tipologia nunca importan ui; ui nunca es
importada por un modulo mas bajo" principle.

F1 rule (c) — same as nosa_utils.revit_compat / shared_params: this
module must import cleanly with no live Revit session present.
Autodesk.Revit / pyrevit are imported lazily, inside the functions
that actually need them.
"""
import datetime
import os
import sys
import uuid
from nosa_utils.telemetry import log_swallowed
_LOG = u'rebarautomate'

_HERE = os.path.dirname(os.path.abspath(__file__))
_LIB = os.path.abspath(os.path.join(_HERE, '..', '..', '..', '..', 'lib'))
if _LIB not in sys.path:
    sys.path.insert(0, _LIB)

from nosa_utils import shared_params  # noqa: E402
from nosa_utils.revit_compat import get_id_value  # noqa: E402 -- lazy-safe, not revit_helpers
from nosa_utils import transactions as nosa_tx  # T8.1: no Revit failure dialogs
from nosa_utils.telemetry import log_info as _log_info

_OST_REBAR_LIKE_CATEGORY_NAMES = (
    u'OST_Rebar',
    u'OST_AreaRein',
    u'OST_PathRein',
)


# IStructE / BS 8666 bar location shown on the bar label (read from Comments).
LOCATION_CODES = {u'bottom_x': u'B1', u'bottom_y': u'B2', u'top_x': u'T1', u'top_y': u'T2'}
# near face = towards the slab, far face = outside the building; 1 = outer layer (SMDSC 4.2.1)
WALL_FACE_CODES = (u'N1', u'N2', u'F1', u'F2')
_LEGACY_FACE_CODES = (u'NF', u'FF')   # before 2026-10-07: replaced on the next generation


def location_code(layer):
    """Label location code (B1, B2, T1, T2) for a NOSA_Rebar_Layer, or '' when it has none."""
    return LOCATION_CODES.get(layer or u'', u'')


def stamp_location(elem, layer, code=None):
    """Write the location code (given, or from the layer) to Comments, never over a user's text."""
    from Autodesk.Revit import DB
    code = code or location_code(layer)
    if not code:
        return True
    param = elem.get_Parameter(DB.BuiltInParameter.ALL_MODEL_INSTANCE_COMMENTS)
    if param is None or param.IsReadOnly:
        return False
    current = param.AsString() or u''
    known = set(LOCATION_CODES.values()) | set(WALL_FACE_CODES) | set(_LEGACY_FACE_CODES)
    if current and current not in known:
        return True
    return bool(param.Set(code))


def default_schedule_flag(elem):
    """NOSA_Rebar_Show_In_Schedule = Yes when never written: the BBS filter is 'equals Yes'."""
    param = elem.LookupParameter(u'NOSA_Rebar_Show_In_Schedule')
    if param is None or param.IsReadOnly:
        return True
    try:
        return True if param.HasValue else bool(param.Set(1))
    except Exception:
        return False


def default_members(elem):
    """BBS 'No. of mbrs' (template project parameter): 1 when empty, never over a typed value."""
    param = elem.LookupParameter(u'Number of Members')
    if param is None or param.IsReadOnly:
        return True
    try:
        if param.HasValue and param.AsDouble() > 0:
            return True
        return bool(param.Set(1.0))
    except Exception:
        return False


def new_batch_id():
    """
    Format: "RA-{YYYYMMDD}-{HHMMSS}-{6-digit microseconds}-{8 hex chars}"
    — e.g. "RA-20260827-153012-004271-a1b2c3d4". Pure Python, no Revit
    dependency. The date/time prefix keeps batch ids sorting
    chronologically (see list_batches); the microsecond field plus an
    8-hex-char random suffix (2**32 space) keep them unique even when
    hundreds are minted in the same second inside a scripted/test
    context.
    """
    now = datetime.datetime.now()
    suffix = uuid.uuid4().hex[:8]
    return u'RA-{}-{:06d}-{}'.format(
        now.strftime('%Y%m%d-%H%M%S'), now.microsecond, suffix)


def make_ctx(doc, standard, generator_version, standard_code=u'BS-8666-2020'):
    """
    Builds the execution context every generation run carries — see
    blueprint Part 03's own `ctx` contract.

    Args:
        doc               (DB.Document)
        standard          (dict or None): the resolved F2 standards
                          profile. F1 does NOT depend on F2 — this is
                          None (or a stub) until F2 exists; nothing in
                          F1 reads ctx['standard'] itself.
        generator_version (str): from lib/_version.py's RA_VERSION.
        standard_code     (str): plain string, independent of whether
                          ctx['standard'] is resolved — this is what
                          NOSA_Rebar_Standard_Code actually stores.
                          Defaults to "BS-8666-2020" (NOSA, 2026-10-01; was EHE-08)
                          (rebar_project.json's own default once F1's
                          UI reads/writes it).

    Returns:
        dict — {'doc', 'standard', 'standard_code', 'batch_id',
                'generator_version'}
    """
    return {
        'doc': doc,
        'standard': standard,
        'standard_code': standard_code,
        'batch_id': new_batch_id(),
        'generator_version': generator_version,
    }


class BatchResult(object):
    """Plain result container (no dataclasses — IronPython 2.7 doesn't
    have the module)."""

    def __init__(self, batch_id, created, skipped, errors, summary):
        self.batch_id = batch_id
        self.created = created    # list[int] -- ElementId values (get_id_value), not DB.ElementId
        self.skipped = skipped    # list[unicode]
        self.errors = errors      # list[unicode] -- generation errors + any stamping failures
        self.summary = summary    # the raw dict generate_fn() returned, untouched


# lower-case sub-marks 1a, 1b ... (IStructE SMDSC 4.5.1, decision D8 2026-10-07)
SUBMARK_SUFFIX = u'a'


def ensure_varying_submarks(doc):
    """
    Varying rebar sets numbered as a whole, bars suffixed a, b, c ... (SMDSC 4.5.1): the BBS then
    lists every bar of a set cut by a chamfer as its own sub-mark (01a, 01b) with its real
    dimensions. In a transaction; True when the project setting had to change.
    """
    from Autodesk.Revit.DB import Structure as DBS
    try:
        settings = DBS.ReinforcementSettings.GetReinforcementSettings(doc)
        changed = False
        if settings.NumberVaryingLengthRebarsIndividually:
            settings.NumberVaryingLengthRebarsIndividually = False
            changed = True
        if settings.RebarVaryingLengthNumberSuffix != SUBMARK_SUFFIX:
            settings.RebarVaryingLengthNumberSuffix = SUBMARK_SUFFIX
            changed = True
        return changed
    except Exception:
        log_swallowed(_LOG, u'ensure_varying_submarks')
        return False


class RebarBatch(object):
    """One user-triggered generation run. See module docstring."""

    def __init__(self, doc, standard, generator_version, standard_code=u'BS-8666-2020', layers=None, locations=None,
                 mark_prefix=u''):
        self.ctx = make_ctx(doc, standard, generator_version, standard_code)
        self.ctx['mark_prefix'] = mark_prefix or u''
        # {element id value: layer code} recorded by the generators; written
        # here, inside a transaction, because they create each bar in a
        # transaction of its own that is already closed when they learn it.
        # Keep the caller's dict itself (even while still empty): the
        # generators fill it during run(), after this batch is built.
        self.layers = layers if layers is not None else {}
        self.locations = locations if locations is not None else {}

    def run(self, generate_fn):
        """
        Args:
            generate_fn (callable() -> (created_rebars, summary)):
                exactly ui.py's existing _run_reinforcement /
                _run_column_reinforcement return shape — a list of the
                DB.Element objects just created, and the summary dict
                those methods already build ({'created', 'tags',
                'sections', 'errors', ...}). ui.py supplies this as a
                closure/lambda over its own already-validated hosts
                and values — RebarBatch never sees those directly.

        Returns:
            BatchResult. On a catastrophic failure (the TransactionGroup
            itself has to roll back), `created` is empty and the
            failure is recorded in `errors` — this function never lets
            an exception escape to the caller, matching this
            extension's "fail warning, not exploding" convention for
            anything UI-facing.
        """
        from pyrevit import revit
        from Autodesk.Revit.DB import TransactionGroup

        doc = self.ctx['doc']
        created_rebars = []
        summary = {}
        stamp_errors = []

        transaction_group = TransactionGroup(
            doc, u'NOSA RebarAutomate — {}'.format(self.ctx['batch_id']))
        transaction_group.Start()
        try:
            created_rebars, summary = generate_fn()

            if created_rebars:
                with nosa_tx.revit_transaction(u'NOSA RebarAutomate — Stamp Provenance'):
                    ensure_varying_submarks(doc)
                    for elem in created_rebars:
                        results = shared_params.stamp_provenance(elem, self.ctx)
                        layer = self.layers.get(get_id_value(elem.Id))
                        if layer:
                            results['NOSA_Rebar_Layer'] = shared_params.write(
                                elem, u'NOSA_Rebar_Layer', layer)
                            results['Comments'] = stamp_location(
                                elem, layer, self.locations.get(get_id_value(elem.Id)))
                        results['Number of Members'] = default_members(elem)
                        results['NOSA_Rebar_Show_In_Schedule'] = default_schedule_flag(elem)
                        failed_fields = [name for name, ok in results.items() if not ok]
                        if failed_fields:
                            stamp_errors.append(
                                u'Element {}: failed to stamp {}'.format(
                                    get_id_value(elem.Id), u', '.join(sorted(failed_fields))))

                # F4: Clasificación de formas
                with nosa_tx.revit_transaction(u'NOSA RebarAutomate — Shape Classification'):
                    try:
                        from nosa_utils.bootstrap import load_module
                        rebar_shape_classifier = load_module('rebar_shape_classifier',
                            os.path.join(os.path.dirname(__file__), 'rebar_shape_classifier.py'))
                        all_created_ids = [e.Id for e in created_rebars]
                        # The shape catalogue is named by the standard profile ("EHE-08" ->
                        # en_iso_3766); looking it up by the standard's own code found no
                        # catalogue for EHE-08 and stamped every bar as shape 99.
                        standard = self.ctx.get('standard') or {}
                        standard_code = standard.get('shape_catalog') or self.ctx.get('standard_code', 'en_iso_3766')
                        shape_summary = rebar_shape_classifier.batch_classify(doc, all_created_ids, standard_code)
                        _log_info(u'rebarautomate', u'[RebarBatch] Shape classification: {} classified, {} failed'.format(
                            shape_summary['classified'], shape_summary['failed']))
                        if shape_summary['shapes']:
                            shapes_str = u', '.join(u'{}×{}'.format(code, count) 
                                                    for code, count in sorted(shape_summary['shapes'].items()))
                            _log_info(u'rebarautomate', u'  Shapes: {}'.format(shapes_str))
                        # BS 8666 shape 00: A is the cut length, rounded like it (25 mm up)
                        import rebar_engine
                        for elem in created_rebars:
                            if shared_params.read(elem, u'NOSA_Rebar_Shape_Code', u'') == u'00':
                                rebar_engine.round_straight_like_total(elem)
                    except Exception as shape_err:
                        stamp_errors.append(u'Shape classification failed: {}'.format(shape_err))

                # F3: Numeración y marcado
                with nosa_tx.revit_transaction(u'NOSA RebarAutomate — Marking {}'.format(self.ctx['batch_id'])):
                    try:
                        rebar_marking = load_module('rebar_marking',
                            os.path.join(os.path.dirname(__file__), 'rebar_marking.py'))
                        all_created_ids = [e.Id for e in created_rebars]
                        mark_summary = rebar_marking.deduplicate_and_mark(doc, all_created_ids, self.ctx)
                        rebar_marking.assign_layers_and_lengths(doc, all_created_ids, self.ctx)
                        _log_info(u'rebarautomate', u'[RebarBatch] Marking: {} positions, {} bars'.format(
                            mark_summary['total_positions'], mark_summary['total_bars']))
                    except Exception as mark_err:
                        stamp_errors.append(u'Marking failed: {}'.format(mark_err))

                # T7.5: BS 8666 sketch of each bar's shape for the BBS 'Shape' column
                try:
                    shape_images = load_module('shape_images',
                        os.path.join(os.path.dirname(__file__), 'shape_images.py'))
                    shapes = shape_images.shapes_of(doc, created_rebars)
                    paths = shape_images.render_shapes(doc, shapes)
                    with nosa_tx.revit_transaction(u'NOSA RebarAutomate — BS 8666 Sketches'):
                        shape_images.stamp_bars(doc, created_rebars,
                                                shape_images.image_types(doc, shapes, paths))
                except Exception as sketch_err:
                    stamp_errors.append(u'BS 8666 sketches not stamped: {}'.format(sketch_err))

                # BBS members without a manual step (2026-10-05): every reinforced host gets its
                # partition, identical hosts share one ("No. of Mbrs" = N on one of them, the others
                # left out of the BBS) and each partition is renumbered 01 upwards.
                try:
                    rebar_partitions = load_module('rebar_partitions',
                        os.path.join(os.path.dirname(__file__), 'rebar_partitions.py'))
                    hosts = rebar_partitions.collect_hosts(doc)
                    with nosa_tx.revit_transaction(u'NOSA RebarAutomate — BBS Members'):
                        members = rebar_partitions.apply(
                            doc, hosts, rebar_partitions.keep_names(hosts, rebar_partitions.plan(hosts)), self.ctx)
                    summary['members'] = members
                except Exception as member_err:
                    stamp_errors.append(u'BBS members not assigned: {}'.format(member_err))

            transaction_group.Assimilate()
        except Exception as e:
            try:
                transaction_group.RollBack()
            except Exception:
                log_swallowed(_LOG, u'RebarBatch.run')
            return BatchResult(
                batch_id=self.ctx['batch_id'], created=[], skipped=[],
                errors=[u'Batch aborted and rolled back: {}'.format(e)], summary={})

        all_errors = list(summary.get('errors', [])) + stamp_errors
        return BatchResult(
            batch_id=self.ctx['batch_id'],
            created=[get_id_value(e.Id) for e in created_rebars],
            skipped=[],
            errors=all_errors,
            summary=summary)

    # ── batch-level queries / lifecycle (static — no per-instance state) ────

    @staticmethod
    def select_batch(doc, batch_id):
        """
        Every element this plugin created with this batch_id, across
        every rebar-like category currently in use (OST_Rebar today;
        OST_AreaRein/OST_PathRein once those typologies exist — see
        _OST_REBAR_LIKE_CATEGORY_NAMES).

        Returns:
            list[DB.ElementId]
        """
        from Autodesk.Revit.DB import BuiltInCategory, FilteredElementCollector

        matches = []
        for cat_name in _OST_REBAR_LIKE_CATEGORY_NAMES:
            try:
                bic = getattr(BuiltInCategory, cat_name)
            except AttributeError:
                continue
            collector = FilteredElementCollector(doc).OfCategory(
                bic).WhereElementIsNotElementType()
            for elem in collector:
                if shared_params.read(elem, 'NOSA_Rebar_Batch_Id') == batch_id:
                    matches.append(elem.Id)
        return matches

    @staticmethod
    def delete_batch(doc, batch_id):
        """
        Deletes every element in `batch_id` EXCEPT those with
        NOSA_Rebar_Finalized = 1 (the user's own "do not touch" flag —
        respected unconditionally, never overridden here). Per-element
        try/except — one failed delete never aborts the rest, matching
        this extension's plural-function convention.

        Returns:
            {'deleted': [DB.ElementId,...], 'protected': [DB.ElementId,...],
             'errors': [unicode,...]}
        """
        from pyrevit import revit

        ids = RebarBatch.select_batch(doc, batch_id)
        protected_ids = []
        to_delete_ids = []
        for element_id in ids:
            elem = doc.GetElement(element_id)
            if elem is None:
                continue
            if shared_params.read(elem, 'NOSA_Rebar_Finalized') == 1:
                protected_ids.append(element_id)
            else:
                to_delete_ids.append(element_id)

        deleted_ids = []
        errors = []
        if to_delete_ids:
            with nosa_tx.revit_transaction(u'NOSA RebarAutomate — Delete Batch {}'.format(batch_id)):
                for element_id in to_delete_ids:
                    try:
                        doc.Delete(element_id)
                        deleted_ids.append(element_id)
                    except Exception as e:
                        errors.append(u'{}: {}'.format(get_id_value(element_id), e))

        return {'deleted': deleted_ids, 'protected': protected_ids, 'errors': errors}

    @staticmethod
    def list_batches(doc):
        """
        One entry per distinct batch_id found among this plugin's own
        elements, for the UI's batch manager (Detailing & Tools tab).

        Returns:
            list[dict] — {'batch_id', 'count', 'generator_version',
            'standard_code'}, sorted by batch_id (which sorts
            chronologically — see new_batch_id's own format).
        """
        from Autodesk.Revit.DB import BuiltInCategory, FilteredElementCollector

        batches = {}
        for cat_name in _OST_REBAR_LIKE_CATEGORY_NAMES:
            try:
                bic = getattr(BuiltInCategory, cat_name)
            except AttributeError:
                continue
            collector = FilteredElementCollector(doc).OfCategory(
                bic).WhereElementIsNotElementType()
            for elem in collector:
                if shared_params.read(elem, 'NOSA_Rebar_Created_By_NOSA') != 1:
                    continue
                batch_id = shared_params.read(elem, 'NOSA_Rebar_Batch_Id')
                if not batch_id:
                    continue
                entry = batches.setdefault(batch_id, {
                    'batch_id': batch_id,
                    'count': 0,
                    'generator_version': shared_params.read(elem, 'NOSA_Rebar_Generator_Version'),
                    'standard_code': shared_params.read(elem, 'NOSA_Rebar_Standard_Code'),
                })
                entry['count'] += 1

        return sorted(batches.values(), key=lambda b: b['batch_id'])
