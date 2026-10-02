# -*- coding: utf-8 -*-
"""
Shared Parameter Manager — Logic

Reads the project's shared parameter file (app.OpenSharedParameterFile()),
cross-references every definition against doc.ParameterBindings, and flags
anomalies: definitions bound in the model but no longer present in the
file (orphaned bindings), and same-name/different-GUID mismatches (GUID
conflicts) — usually the result of the .txt file being swapped or a
parameter being re-created instead of re-used.
"""
from Autodesk.Revit import DB
from nosa_utils.telemetry import log_swallowed
_LOG = u'sharedparammanager'

_EMPTY_GUID = u'00000000-0000-0000-0000-000000000000'


def get_shared_parameter_file_path(app):
    """Currently configured shared-parameter .txt path (Manage > Shared
    Parameters), or '' if none is set."""
    try:
        return app.SharedParametersFilename or u''
    except Exception:
        return u''


def set_shared_parameter_file(app, path):
    """Point Revit at a different shared-parameter file and return the
    opened DefinitionFile."""
    app.SharedParametersFilename = path
    return get_shared_parameter_file(app)


def get_shared_parameter_file(app):
    """Return the DefinitionFile for the currently configured shared
    parameter file, or None if none is set / it can't be opened."""
    try:
        return app.OpenSharedParameterFile()
    except Exception:
        return None


def _param_type_label(defn):
    """Data type label, compatible across Revit versions: GetDataType()
    (2022+, ForgeTypeId) with a LabelUtils lookup, falling back to the
    pre-2022 ParameterType enum."""
    try:
        dt = defn.GetDataType()
        try:
            return DB.LabelUtils.GetLabelForSpec(dt)
        except Exception:
            return dt.TypeId.rsplit(u':', 1)[-1].split(u'-')[0]
    except Exception:
        log_swallowed(_LOG, u'_param_type_label')
    try:
        return str(defn.ParameterType)
    except Exception:
        return u'—'


def read_file_definitions(def_file):
    """Every definition in the shared parameter file, across all groups."""
    out = []
    if def_file is None:
        return out
    for group in def_file.Groups:
        for defn in group.Definitions:
            try:
                guid = str(defn.GUID)
            except Exception:
                guid = u''
            out.append({
                'name': defn.Name,
                'guid': guid,
                'group': group.Name,
                'data_type': _param_type_label(defn),
            })
    return out


def get_bound_definitions(doc):
    """Every parameter currently bound in the project. GUID is '' for a
    plain project parameter (not shared) — only shared-parameter bindings
    carry a real GUID here."""
    out = []
    it = doc.ParameterBindings.ForwardIterator()
    it.Reset()
    while it.MoveNext():
        definition = it.Key
        binding = it.Current
        try:
            guid = str(definition.GUID)
            if guid == _EMPTY_GUID:
                guid = u''
        except Exception:
            guid = u''
        try:
            cat_names = u', '.join(sorted(c.Name for c in binding.Categories))
        except Exception:
            cat_names = u''
        try:
            is_instance = isinstance(binding, DB.InstanceBinding)
        except Exception:
            is_instance = True
        out.append({
            'name': definition.Name,
            'guid': guid,
            'categories': cat_names,
            'binding_type': u'Instance' if is_instance else u'Type',
        })
    return out


def audit(app, doc):
    """
    Cross-reference the shared parameter file against the project's
    current bindings.

    Returns:
        {
          'rows':      [{name, guid, group, data_type, bound, status,
                         categories}, ...],
          'file_path': str,
          'orphans':   int,   # bound in model, GUID not found in the file
          'conflicts': int,   # same name, different GUID (subset of orphans)
          'error':     str or None,
        }
    """
    def_file  = get_shared_parameter_file(app)
    file_path = get_shared_parameter_file_path(app)

    if def_file is None:
        return {'rows': [], 'file_path': file_path, 'orphans': 0,
                'conflicts': 0,
                'error': u'No shared parameter file is set (or it could '
                         u'not be opened). Use "Load Shared Parameter '
                         u'File..." to pick one.'}

    file_defs = read_file_definitions(def_file)
    file_by_name = {}
    for d in file_defs:
        file_by_name.setdefault(d['name'], []).append(d)

    bound_defs    = get_bound_definitions(doc)
    bound_by_guid = {d['guid']: d for d in bound_defs if d['guid']}

    rows = []
    seen_guids = set()

    # File definitions first, cross-referenced against the model's bindings.
    for d in file_defs:
        bound = bound_by_guid.get(d['guid'])
        rows.append({
            'name': d['name'], 'guid': d['guid'], 'group': d['group'],
            'data_type': d['data_type'],
            'categories': bound['categories'] if bound else u'',
            'bound': bool(bound),
            'status': u'Bound' if bound else u'Not bound',
        })
        seen_guids.add(d['guid'])

    # Bound in the model but absent from the file -> orphaned binding.
    # Same name present in the file under a different GUID -> GUID conflict
    # (a stricter subset of "orphaned" — usually a swapped/recreated param).
    orphans = 0
    conflicts = 0
    for d in bound_defs:
        if not d['guid'] or d['guid'] in seen_guids:
            continue
        orphans += 1
        is_conflict = bool(file_by_name.get(d['name']))
        if is_conflict:
            conflicts += 1
        rows.append({
            'name': d['name'], 'guid': d['guid'], 'group': u'—',
            'data_type': u'—', 'categories': d['categories'],
            'bound': True,
            'status': u'GUID conflict' if is_conflict else u'Orphaned binding',
        })

    rows.sort(key=lambda r: (r['status'] == u'Bound' and 0 or 1, r['name'].lower()))
    return {'rows': rows, 'file_path': file_path, 'orphans': orphans,
            'conflicts': conflicts, 'error': None}
