# -*- coding: utf-8 -*-
"""
nosa_utils.shared_params
=========================
Writer/binding layer for NOSA's own Revit shared parameters. See
docs/REBARAUTOMATE_BLUEPRINT.md Part 05 for the full parameter tables
and Decision 5.A for the DefinitionFile strategy this module
implements.

F1 rule (c) — same as nosa_utils.revit_compat: this module MUST import
cleanly with no live Revit session present (pytest, CI, any pure
test). Autodesk.Revit / pyrevit / System are imported lazily, inside
the functions that actually need them — never at module scope.

Public API
----------
parse_shared_parameters_txt(path=None)
    Pure Python parser for the .txt file's own PARAM/GROUP rows — no
    Revit dependency at all. Used both by ensure_bound (to validate
    the file before ever touching Revit) and by pure tests (Part 14's
    "40 GUIDs unicos, coinciden con la Parte 05" CI check).

ensure_bound(doc, categories=None, insert_into_user_file=False)
    Idempotent. Binds every parameter in NOSA_SharedParameters.txt to
    `categories` (defaults to the 5 "main" categories from Part 05) —
    see its own docstring for the DefinitionFile swap-and-restore
    mechanism (Decision 5.A).

write(elem, guid_or_name, value)
read(elem, guid_or_name, default=None)
    Robust get/set by GUID (preferred, version-proof) or parameter
    name (fallback).

stamp_provenance(elem, ctx)
    Writes the mandatory provenance fields (Golden Rule #6 / Part 08)
    onto `elem` — Created_By_NOSA, Batch_Id, Generator_Version,
    Standard_Code, Last_Modified. Called from inside the SAME
    Transaction that created `elem` (rebar_batch.py owns this call —
    typology modules never call it directly).
"""
import csv
import datetime
import os

_HERE = os.path.dirname(os.path.abspath(__file__))
_EXTENSION_ROOT = os.path.abspath(os.path.join(_HERE, '..', '..'))
_DEFAULT_TXT_PATH = os.path.join(
    _EXTENSION_ROOT, 'data', 'shared_parameters', 'NOSA_SharedParameters.txt')

# PHASE F1 — the .txt format itself has no Instance/Type column (that
# is a BINDING-time decision, not a parameter-definition property) —
# this table mirrors the "I/T" column from blueprint Part 05's own
# markdown tables. Every parameter not listed here binds as INSTANCE.
_TYPE_PARAM_NAMES = frozenset([
    u'NOSA_Rebar_Steel_Grade',
    u'NOSA_Rebar_Mass_Per_Length',
])

# PHASE F1 — Part 05's "Categorías a las que se enlaza": the 5 "main"
# categories every parameter binds to, by BuiltInCategory NAME (not
# the enum value itself, so this module never imports Autodesk.Revit
# at module scope — resolved lazily inside ensure_bound).
DEFAULT_CATEGORY_NAMES = (
    u'OST_Rebar',
    u'OST_AreaRein',
    u'OST_PathRein',
    u'OST_FabricAreas',
    u'OST_FabricReinforcement',
)

# Tag-related categories, and the small subset of parameters that ALSO
# bind to them when the caller includes them in `categories` — F1
# itself never passes these (RebarBatch doesn't touch tags yet; F6
# does), but ensure_bound supports it correctly from the start rather
# than needing a rewrite later.
_TAG_CATEGORY_NAMES = (u'OST_RebarTags', u'OST_MultiReferenceAnnotations')
_TAG_ELIGIBLE_PARAM_NAMES = frozenset([
    u'NOSA_Rebar_Mark',
    u'NOSA_Rebar_Tag_Offset_X',
    u'NOSA_Rebar_Tag_Offset_Y',
])


def _resolve_txt_path(path=None):
    return path if path is not None else _DEFAULT_TXT_PATH


def parse_shared_parameters_txt(path=None):
    """
    Pure Python parser for NOSA_SharedParameters.txt's own GROUP/PARAM
    rows — tab-separated, Revit's shared-parameter-file format. Never
    touches Revit; safe to call from any pure test or CI check.

    Args:
        path (str or None): defaults to
            data/shared_parameters/NOSA_SharedParameters.txt.

    Returns:
        {
          'groups': {int_id: unicode_name, ...},
          'params': [
            {'guid': str, 'name': unicode, 'datatype': unicode,
             'group_id': int, 'visible': bool, 'description': unicode,
             'usermodifiable': bool, 'hide_when_no_value': bool},
            ...
          ],
        }

    Raises:
        IOError: if `path` doesn't exist.
        ValueError: if a PARAM/GROUP row doesn't have the expected
            column count, or a GUID is malformed (not validated as a
            real UUID here — just non-empty; format validation is the
            CI check's job, not the parser's).
    """
    resolved_path = _resolve_txt_path(path)
    groups = {}
    params = []
    import io
    with io.open(resolved_path, 'r', encoding='utf-8') as f:
        reader = csv.reader(f, delimiter='\t')
        for row in reader:
            if not row or not row[0] or row[0].startswith('#') or row[0].startswith('*'):
                continue
            if row[0] == 'META':
                continue
            if row[0] == 'GROUP':
                if len(row) < 3:
                    raise ValueError(u'Malformed GROUP row: {}'.format(row))
                groups[int(row[1])] = row[2]
                continue
            if row[0] == 'PARAM':
                if len(row) < 9:
                    raise ValueError(u'Malformed PARAM row: {}'.format(row))
                (_tag, guid, name, datatype, _datacategory, group_id,
                 visible, description, usermodifiable) = row[:9]
                hide_when_no_value = row[9] if len(row) > 9 else '0'
                if not guid:
                    raise ValueError(u'PARAM row with an empty GUID: {}'.format(row))
                params.append({
                    'guid': guid,
                    'name': name,
                    'datatype': datatype,
                    'group_id': int(group_id),
                    'visible': visible == '1',
                    'description': description,
                    'usermodifiable': usermodifiable == '1',
                    'hide_when_no_value': hide_when_no_value == '1',
                })
    return {'groups': groups, 'params': params}


def ensure_bound(doc, categories=None, insert_into_user_file=False):
    """
    Idempotent. Called once per document, typically when RebarAutomate
    first opens on it (see ui.py):

      1. Parses NOSA_SharedParameters.txt (pure, validates the file
         BEFORE touching Revit at all — a malformed .txt aborts here
         with a clear error, not a half-applied binding pass).
      2. Saves the project's own CURRENT app.SharedParametersFilename.
      3. Points it at NOSA's own .txt just long enough to open it as a
         DefinitionFile and read its Definitions.
      4. For each Definition not already bound to `categories`, creates
         an InstanceBinding (or TypeBinding for the 2 TYPE parameters —
         see _TYPE_PARAM_NAMES) via doc.ParameterBindings.Insert. NEVER
         re-creates an existing binding (that's a GUID-conflict-inducing
         no-op at best, a corrupt binding at worst).
      5. RESTORES the original app.SharedParametersFilename — this
         function never leaves the project pointed at NOSA's own file.
         The bindings themselves live in the project's own BindingMap
         once created; they do not depend on NOSA's .txt staying "the
         current file" afterward (Decision 5.A).
      6. If insert_into_user_file is True (the user opted in via the
         one-time dialog, saved in rebar_project.json — default False,
         never touches the office's own file uninvited): ALSO creates
         matching Definitions (by GUID) inside the user's OWN
         SharedParametersFilename, so the office's file gains NOSA's
         parameters for direct use outside the plugin too. Best-effort,
         per-definition — a failure on one definition is recorded in
         the report and does not abort the rest.

    Args:
        doc         (DB.Document)
        categories  (list[str] or None): BuiltInCategory NAMES (see
                    DEFAULT_CATEGORY_NAMES) — defaults to the 5 "main"
                    categories. Pass DEFAULT_CATEGORY_NAMES + the tag
                    categories to also bind the tag-eligible subset
                    (F6's own concern, not F1's).
        insert_into_user_file (bool): see step 6.

    Returns:
        {'bound': [names...], 'already': [names...],
         'skipped': [names...], 'errors': [unicode...]}
    """
    from Autodesk.Revit.DB import (
        BuiltInCategory, CategorySet, InstanceBinding, TypeBinding, GroupTypeId, Transaction)

    report = {'bound': [], 'already': [], 'skipped': [], 'errors': []}
    category_names = categories if categories is not None else list(DEFAULT_CATEGORY_NAMES)

    try:
        parsed = parse_shared_parameters_txt()
    except Exception as e:
        report['errors'].append(u'Could not parse NOSA_SharedParameters.txt: {}'.format(e))
        return report

    app = doc.Application
    original_path = None
    try:
        original_path = app.SharedParametersFilename
    except Exception:
        original_path = None

    try:
        app.SharedParametersFilename = _DEFAULT_TXT_PATH
        def_file = app.OpenSharedParameterFile()
        if def_file is None:
            report['errors'].append(
                u'Could not open NOSA_SharedParameters.txt as a DefinitionFile.')
            return report

        category_set = CategorySet()
        for cat_name in category_names:
            try:
                bic = getattr(BuiltInCategory, cat_name)
                category = doc.Settings.Categories.get_Item(bic)
                if category is not None:
                    category_set.Insert(category)
            except Exception as e:
                report['errors'].append(u'Could not resolve category {}: {}'.format(cat_name, e))

        param_names_by_guid = {p['guid']: p['name'] for p in parsed['params']}
        tag_eligible_requested = bool(set(category_names) & set(_TAG_CATEGORY_NAMES))

        # CRITICAL: Bindings MUST be inserted within a Transaction
        t = Transaction(doc, u'NOSA — Bind Shared Parameters')
        t.Start()
        try:
            for group in def_file.Groups:
                for definition in group.Definitions:
                    name = definition.Name
                    # A parameter not present in our own parsed table isn't
                    # one of ours — skip it defensively rather than binding
                    # something unexpected.
                    if str(definition.GUID) not in param_names_by_guid:
                        continue

                    existing = doc.ParameterBindings.get_Item(definition)
                    if existing is not None:
                        report['already'].append(name)
                        continue

                    this_category_set = category_set
                    if tag_eligible_requested and name not in _TAG_ELIGIBLE_PARAM_NAMES:
                        # Only the tag-eligible subset gets the tag
                        # categories mixed in; rebuild a set without them
                        # for everything else.
                        this_category_set = CategorySet()
                        for cat_name in category_names:
                            if cat_name in _TAG_CATEGORY_NAMES:
                                continue
                            try:
                                bic = getattr(BuiltInCategory, cat_name)
                                category = doc.Settings.Categories.get_Item(bic)
                                if category is not None:
                                    this_category_set.Insert(category)
                            except Exception:
                                pass

                    try:
                        if name in _TYPE_PARAM_NAMES:
                            binding = TypeBinding(this_category_set)
                        else:
                            binding = InstanceBinding(this_category_set)
                        ok = doc.ParameterBindings.Insert(definition, binding, GroupTypeId.Data)
                        if ok:
                            report['bound'].append(name)
                        else:
                            report['skipped'].append(name)
                    except Exception as e:
                        report['errors'].append(u'{}: {}'.format(name, e))
            
            t.Commit()
        except Exception as e:
            t.RollBack()
            report['errors'].append(u'Transaction failed: {}'.format(e))

        if insert_into_user_file:
            _insert_definitions_into_user_file(app, original_path, def_file, report)
    finally:
        try:
            if original_path is not None:
                app.SharedParametersFilename = original_path
        except Exception as e:
            report['errors'].append(
                u'Could not restore the original SharedParametersFilename ({}): {}'.format(
                    original_path, e))

    return report


def _insert_definitions_into_user_file(app, user_file_path, nosa_def_file, report):
    """
    Best-effort: copy every NOSA definition into the office's own
    shared-parameter file, so it carries them for direct use outside
    the plugin too (the user opted in — see ensure_bound's own
    docstring, step 6). Per-definition try/except — one failure never
    aborts the rest.
    """
    from Autodesk.Revit.DB import ExternalDefinitionCreationOptions

    if not user_file_path:
        report['errors'].append(
            u'insert_into_user_file was requested but no office shared-parameter '
            u'file is currently configured — nothing to insert into.')
        return

    try:
        app.SharedParametersFilename = user_file_path
        user_def_file = app.OpenSharedParameterFile()
        if user_def_file is None:
            report['errors'].append(
                u'Could not open the office shared-parameter file to insert into.')
            return
    except Exception as e:
        report['errors'].append(u'Could not open the office shared-parameter file: {}'.format(e))
        return

    existing_guids = set()
    for group in user_def_file.Groups:
        for definition in group.Definitions:
            try:
                existing_guids.add(str(definition.GUID))
            except Exception:
                pass

    for nosa_group in nosa_def_file.Groups:
        target_group = None
        for g in user_def_file.Groups:
            if g.Name == nosa_group.Name:
                target_group = g
                break
        if target_group is None:
            try:
                target_group = user_def_file.Groups.Create(nosa_group.Name)
            except Exception as e:
                report['errors'].append(
                    u'Could not create group {} in the office file: {}'.format(
                        nosa_group.Name, e))
                continue

        for definition in nosa_group.Definitions:
            guid = str(definition.GUID)
            if guid in existing_guids:
                continue
            try:
                options = ExternalDefinitionCreationOptions(
                    definition.Name, definition.GetDataType())
                options.GUID = definition.GUID
                target_group.Definitions.Create(options)
            except Exception as e:
                report['errors'].append(
                    u'Could not insert {} into the office file: {}'.format(
                        definition.Name, e))


def _find_parameter(elem, guid_or_name):
    """GUID first (version-proof), falls back to lookup by name."""
    try:
        import System
        guid_obj = System.Guid(guid_or_name)
        param = elem.get_Parameter(guid_obj)
        if param is not None:
            return param
    except Exception:
        pass
    try:
        return elem.LookupParameter(guid_or_name)
    except Exception:
        return None


def write(elem, guid_or_name, value):
    """
    Robust set by GUID or name. Returns True on success, False on any
    failure (parameter not found, read-only, wrong type) — never
    raises, matching this extension's "fail warning, not exploding"
    convention for anything that touches a single element's own
    parameters.
    """
    param = _find_parameter(elem, guid_or_name)
    if param is None:
        return False
    try:
        if isinstance(value, bool):
            param.Set(1 if value else 0)
        elif isinstance(value, int):
            param.Set(value)
        elif isinstance(value, float):
            param.Set(value)
        else:
            param.Set(value if value is not None else u'')
        return True
    except Exception:
        return False


def read(elem, guid_or_name, default=None):
    """Robust get by GUID or name. Returns `default` if the parameter
    doesn't exist or has no value — never raises."""
    param = _find_parameter(elem, guid_or_name)
    if param is None:
        return default
    try:
        if not param.HasValue:
            return default
    except Exception:
        return default
    try:
        from Autodesk.Revit.DB import StorageType
        storage_type = param.StorageType
        if storage_type == StorageType.String:
            return param.AsString()
        if storage_type == StorageType.Integer:
            return param.AsInteger()
        if storage_type == StorageType.Double:
            return param.AsDouble()
        if storage_type == StorageType.ElementId:
            return param.AsElementId()
    except Exception:
        pass
    return default


def _now_iso8601():
    """Pure Python — no Revit dependency. Kept as its own function so
    a test can monkeypatch it for a deterministic timestamp."""
    return datetime.datetime.now().isoformat()


def stamp_provenance(elem, ctx):
    """
    Writes the mandatory provenance fields (Golden Rule #6 / Part 08)
    onto `elem`. Called from INSIDE the same Transaction that created
    `elem` — rebar_batch.py owns this call; typology modules
    (column_rebar.py etc.) never call it directly.

    Args:
        elem (DB.Element): the just-created Rebar (or Rebar Set).
        ctx  (dict): the execution context — see rebar_batch.py's own
             make_ctx(). Required keys: 'batch_id', 'generator_version',
             'standard_code'. 'standard' (the resolved F2 profile) is
             NOT read here — Standard_Code is always a plain string,
             independent of whether F2's standards module has loaded a
             real profile yet (F1 rule: F1 does not depend on F2).

    Returns:
        dict[str, bool] — {param_name: write_succeeded} for every
        field this function writes, so a caller can surface a partial
        failure without aborting the whole stamping pass.
    """
    results = {}
    results['NOSA_Rebar_Created_By_NOSA'] = write(elem, 'NOSA_Rebar_Created_By_NOSA', True)
    results['NOSA_Rebar_Batch_Id'] = write(elem, 'NOSA_Rebar_Batch_Id', ctx.get('batch_id', u''))
    results['NOSA_Rebar_Generator_Version'] = write(
        elem, 'NOSA_Rebar_Generator_Version', ctx.get('generator_version', u''))
    results['NOSA_Rebar_Standard_Code'] = write(
        elem, 'NOSA_Rebar_Standard_Code', ctx.get('standard_code', u''))
    results['NOSA_Rebar_Last_Modified'] = write(elem, 'NOSA_Rebar_Last_Modified', _now_iso8601())
    return results
