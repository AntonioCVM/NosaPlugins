# -*- coding: utf-8 -*-
import os
import re
import sys
import json
import numbers
from nosa_utils.telemetry import log_swallowed
_LOG = u'nosa_utils.usage'

_CONFIGS_DIR = os.path.join(
    os.getenv('APPDATA', ''),
    'pyRevit', 'Extensions', 'NOSA.extension', 'NOSA_Configs'
)
_USAGE_FILE = os.path.join(_CONFIGS_DIR, '_usage.json')

# Counts folded into their canonical key are kept here, per legacy key, so
# the original numbers are never lost.
_LEGACY_BUCKET = '_legacy_keys'

_BUNDLE_SUFFIXES = ('.pushbutton', '.nobutton')

# Legacy usage key -> canonical key (snake_case of the bundle folder name).
# Legacy keys come from old NOSAWindow plugin_keys and lowercased folder names.
_KEY_ALIASES = {
    'addpiletopilecap': 'add_pile_to_pilecap',
    'alignviewtitles': 'align_view_titles',
    'analytical_health': 'analytical_health_check',
    'analyticalhealthcheck': 'analytical_health_check',
    'annotationbatch': 'annotation_batch',
    'annotationhub': 'annotation_hub',
    'annotationsuite': 'annotation_suite',
    'batchrename': 'batch_rename',
    'baysections': 'bay_sections',
    'caseconverter': 'case_converter',
    'centerbeamtocolumn': 'center_beam_to_column',
    'clashreport': 'clash_report',
    'colourbyparam': 'colour_by_param',
    'connectionchecker': 'connection_checker',
    'copyviewtemplates': 'copy_view_templates',
    'covercompliance': 'cover_compliance',
    'create_pilecap': 'create_pilecap_type',
    'createpilecaptype': 'create_pilecap_type',
    'cuadroreplanteo': 'cuadro_replanteo',
    'datatoolshub': 'data_tools_hub',
    'dimensionwalls': 'dimension_walls',
    'drawingchecker': 'drawing_checker',
    'drawingindex': 'drawing_index',
    'drawingprotocolchecker': 'drawing_protocol_checker',
    'elementcommentshub': 'element_comments_hub',
    'elementjoin': 'element_join',
    'excelsync': 'excel_sync',
    'export_sheets': 'sheet_export_hub',
    'exportsheets': 'sheet_export_hub',
    'familyaudit': 'family_audit',
    'footingdesigner': 'footing_designer',
    'foundation_loads': 'foundation_load_extractor',
    'foundationloadextractor': 'foundation_load_extractor',
    'ga_auto_dim': 'ga_auto_dimension',
    'gaautodimension': 'ga_auto_dimension',
    'gridbubblebatch': 'grid_bubble_batch',
    'halftoneselection': 'halftone_selection',
    'healthscore': 'health_score',
    'ifcstructuralexportqa': 'ifc_structural_export_qa',
    'issuegate': 'issue_gate',
    'issueworkflowhub': 'issue_workflow_hub',
    'levelgridsync': 'level_grid_sync',
    'levelnavigator': 'level_navigator',
    'linkchangemonitor': 'link_change_monitor',
    'linkmanager': 'link_manager',
    'materialmanager': 'material_manager',
    'model_sync': 'model_sync_checker',
    'modelcleanup': 'model_cleanup',
    'modelhealthhub': 'model_health_hub',
    'modelsyncchecker': 'model_sync_checker',
    'nosa_dashboard': 'nosa',
    'padfootings': 'pad_footings',
    'parameterdriftmonitor': 'parameter_drift_monitor',
    'parameterhub': 'parameter_hub',
    'pile_survey': 'pile_survey_export',
    'pilecaploadchecker': 'pilecap_load_checker',
    'pilemaster': 'pile_master',
    'pilesurveyexport': 'pile_survey_export',
    'poursequenceplanner': 'pour_sequence_planner',
    'project_setup': 'project_setup_wizard',
    'projectsetupwizard': 'project_setup_wizard',
    'qrcode': 'qr_code',
    'quantificationqa': 'quantification_qa',
    'rebarauditor': 'rebar_auditor',
    'rebarautomate': 'rebar_automate',
    'rebarcoverage': 'rebar_coverage',
    'rebarhub': 'rebar_hub',
    'rebarmanager': 'rebar_manager',
    'rebarschedule': 'rebar_schedule',
    'revisionpackagediff': 'revision_package_diff',
    'revisiontracker': 'revision_tracker',
    'schedule_pro': 'structural_schedule_pro',
    'scheduleimpact': 'schedule_impact',
    'sectionboxer': 'section_boxer',
    'sharedparammanager': 'shared_param_manager',
    'sheet_composer': 'sheet_gen',
    'sheetcomposer': 'sheet_gen',
    'sheetexporthub': 'sheet_export_hub',
    'sheetgen': 'sheet_gen',
    'sheethub': 'sheet_hub',
    'sheetissuemanager': 'sheet_issue_manager',
    'sheetnamer': 'sheet_namer',
    'sitetoolkit': 'site_toolkit',
    'smartjoin_pro': 'element_join',
    'structural_qa_hub': 'structural_qa',
    'structuralbom': 'structural_bom',
    'structuralqa': 'structural_qa',
    'structuralschedulepro': 'structural_schedule_pro',
    'structuraltypemanager': 'structural_type_manager',
    'surveyexport': 'survey_export',
    'tagall': 'tag_all',
    'templateguard': 'template_guard',
    'texttools': 'text_tools',
    'typerenamer': 'type_renamer',
    'viewbatchmanager': 'view_batch_manager',
    'viewdependencyexplorer': 'view_dependency_explorer',
    'viewfilter_batch': 'view_filter_batch',
    'viewfilterbatch': 'view_filter_batch',
    'viewhub': 'view_hub',
    'viewmanager': 'view_manager',
    'vieworganiser': 'view_organiser',
    'viewoverrides': 'view_overrides',
    'viewtemplatemanager': 'view_template_manager',
    'viewutilities': 'view_utilities',
    'waffleslab': 'waffle_slab',
    'wallfootings': 'wall_footings',
    'warningstriage': 'warnings_triage',
    'worksethealth': 'workset_health',
    'worksharingaudit': 'worksharing_audit',
}


def _is_count(value):
    return isinstance(value, numbers.Number) and not isinstance(value, bool)


def to_snake_case(name):
    """'SheetExportHub' -> 'sheet_export_hub', 'QRCode' -> 'qr_code'."""
    s = re.sub(r'(.)([A-Z][a-z]+)', r'\1_\2', name)
    s = re.sub(r'([a-z0-9])([A-Z])', r'\1_\2', s)
    return re.sub(r'[^0-9a-zA-Z]+', '_', s).strip('_').lower()


def canonical_key(key):
    return _KEY_ALIASES.get(key, key)


def bundle_key_from_path(path):
    """Usage key of the nearest .pushbutton/.nobutton folder containing path."""
    if not path:
        return None
    parts = re.split(r'[\\/]+', os.path.abspath(path))
    for part in reversed(parts):
        for suffix in _BUNDLE_SUFFIXES:
            if part.endswith(suffix):
                return canonical_key(to_snake_case(part[:-len(suffix)]))
    return None


def resolve_launch_key(window_class, fallback=None):
    """Stable usage key for a launched window: its bundle folder, else fallback."""
    try:
        mod = sys.modules.get(getattr(window_class, '__module__', None))
        key = bundle_key_from_path(getattr(mod, '__file__', None))
        if key:
            return key
    except Exception:
        log_swallowed(_LOG, u'resolve_launch_key')
    try:
        from pyrevit import EXEC_PARAMS
        key = bundle_key_from_path(EXEC_PARAMS.command_path)
        if key:
            return key
    except Exception:
        log_swallowed(_LOG, u'resolve_launch_key')
    return canonical_key(fallback) if fallback else fallback


def migrate(data):
    """Fold legacy alias keys into canonical keys. Idempotent; returns (data, changed)."""
    if not isinstance(data, dict):
        return {}, True
    changed = False
    for old in list(data.keys()):
        new = _KEY_ALIASES.get(old)
        if new is None or not _is_count(data[old]):
            continue
        count = data.pop(old)
        data[new] = data.get(new, 0) + count
        legacy = data.get(_LEGACY_BUCKET)
        if not isinstance(legacy, dict):
            legacy = {}
            data[_LEGACY_BUCKET] = legacy
        legacy[old] = legacy.get(old, 0) + count
        changed = True
    return data, changed


def _read_raw():
    try:
        with open(_USAGE_FILE, 'r') as f:
            return json.load(f)
    except Exception:
        return {}


def _load():
    data, changed = migrate(_read_raw())
    if changed:
        _save(data)
    return data


def _save(data):
    try:
        if not os.path.isdir(_CONFIGS_DIR):
            os.makedirs(_CONFIGS_DIR)
        with open(_USAGE_FILE, 'w') as f:
            json.dump(data, f, indent=2, sort_keys=True)
    except Exception:
        log_swallowed(_LOG, u'_save')


def _counts(data):
    return dict((k, v) for k, v in data.items()
                if not k.startswith('_') and _is_count(v))


def record(plugin_key):
    """Increment the launch count for plugin_key (legacy keys are canonicalised)."""
    if not plugin_key:
        return
    key = canonical_key(plugin_key)
    data = _load()
    data[key] = data.get(key, 0) + 1
    _save(data)


def get_all():
    """Return dict of {plugin_key: count}."""
    return _counts(_load())


def get_top(n=10):
    """Return list of (plugin_key, count) sorted by count desc."""
    return sorted(_counts(_load()).items(), key=lambda kv: kv[1], reverse=True)[:n]


def reset(plugin_key=None):
    """Reset count for one plugin, or all if plugin_key is None."""
    if plugin_key is None:
        _save({})
    else:
        data = _load()
        data.pop(canonical_key(plugin_key), None)
        _save(data)
