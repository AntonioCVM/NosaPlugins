# -*- coding: utf-8 -*-
"""
Pure tests for Phase F1: the shared-parameter .txt parser + its GUID
fixture (blueprint Part 14's own CI requirement), nosa_utils.shared_params
(stamp_provenance, outside Revit), nosa_utils.rebar_batch (new_batch_id,
make_ctx — the Revit-touching parts of RebarBatch.run/select_batch/
delete_batch/list_batches are NOT covered here; those need a live
Revit session per the smoke matrix, Part 15), and rebar_project.py.

Runs OUTSIDE Revit — no Autodesk.Revit / pyrevit required.
"""
import os
import re
import sys
import tempfile

_HERE = os.path.dirname(os.path.abspath(__file__))
_LIB = os.path.abspath(os.path.join(_HERE, '..', '..', '..', '..', '..', 'lib'))
if _LIB not in sys.path:
    sys.path.insert(0, _LIB)
_PLUGIN_LIB = os.path.abspath(os.path.join(_HERE, '..', 'lib'))
if _PLUGIN_LIB not in sys.path:
    sys.path.insert(0, _PLUGIN_LIB)

from nosa_utils import shared_params  # noqa: E402
import rebar_batch  # noqa: E402
import rebar_project  # noqa: E402


# ══════════════════════════════════════════════════════════════════════════
# Fixture — the 40 parameters as specified in
# docs/REBARAUTOMATE_BLUEPRINT.md Part 05. This is the canonical source
# of truth this test cross-checks the .txt file against — if a GUID
# ever needs to change here AND in the .txt, that is a blueprint
# amendment, not a routine edit.
# ══════════════════════════════════════════════════════════════════════════

_FIXTURE_GUIDS_BY_NAME = {
    # NOSA_Rebar_Identity
    u'NOSA_Rebar_Mark': u'b0a7083b-fab5-43da-a8d6-be2dbba2b310',
    u'NOSA_Rebar_Mark_Number': u'f743bc96-c90e-419b-a1fd-978eeb07fa78',
    u'NOSA_Rebar_Mark_Prefix': u'bdf4e7c4-427a-4ba1-ac7a-d8311b40da70',
    u'NOSA_Rebar_Mark_Suffix': u'0dc98d97-3440-4275-a91b-68f26dc4fe2b',
    u'NOSA_Rebar_Host_Mark': u'b924bef3-194e-4cab-adbf-17d45483fa25',
    u'NOSA_Rebar_Host_Id': u'6dfa3bff-84ce-4b33-b549-64e28ece316e',
    u'NOSA_Rebar_Layer': u'd06c7f54-06e1-43b2-b577-af951d3c0e85',
    u'NOSA_Rebar_Group': u'924457d4-36b3-4cfa-9e43-ecd50bba68d5',
    u'NOSA_Rebar_Assembly': u'574f41d2-9fcd-4b87-8e15-f020f4f7e7b6',
    u'NOSA_Rebar_Position_In_Host': u'da6d9efa-635d-49f1-a18c-c1f4d5d90c30',
    # NOSA_Rebar_Shape
    u'NOSA_Rebar_Shape_Code': u'3af513b3-360f-4184-ac71-15352196e0e8',
    u'NOSA_Rebar_Shape_Catalog': u'93e114b7-61e3-4b55-9999-123047a052cc',
    u'NOSA_Rebar_Shape_Params': u'9d6f4403-dfec-4e42-8874-f08a0a1a6254',
    u'NOSA_Rebar_Bend_Diameter': u'834af015-5907-4db6-a9ce-49aae7157710',
    u'NOSA_Rebar_Hook_Start': u'e6296fa2-4b65-4255-9408-88f1039def22',
    u'NOSA_Rebar_Hook_End': u'2650ae68-68b6-4e08-88cf-8ab318fa8d17',
    u'NOSA_Rebar_Is_Variable': u'd84c3a95-a9d3-4ebf-b30f-77bd21c89e64',
    u'NOSA_Rebar_Segment_Count': u'24fb1e29-fef1-46da-841f-f5fdcc8ab8d5',
    # NOSA_Rebar_Status
    u'NOSA_Rebar_Created_By_NOSA': u'7fcd3b49-56f5-4687-8095-67f153ee2d02',
    u'NOSA_Rebar_Batch_Id': u'0233dc14-11d9-44e1-95b7-e82662da4759',
    u'NOSA_Rebar_Generator_Version': u'9cfdaebb-465e-4c95-b342-c81484917a4e',
    u'NOSA_Rebar_Standard_Code': u'5711215e-99dd-4fcc-a4d6-2f1ab4a27516',
    u'NOSA_Rebar_Finalized': u'4a687ef1-4e0a-4f62-8a80-6e2c98b11e9c',
    u'NOSA_Rebar_Revision': u'77bab632-d23d-4a91-ae17-03eed8c4412b',
    u'NOSA_Rebar_Issue_Status': u'7e9822da-b3b4-406c-8d59-77b1c79af1df',
    u'NOSA_Rebar_Last_Modified': u'cca44491-979b-4d1d-b12d-5f41a8e151ec',
    # NOSA_Rebar_Fabrication
    u'NOSA_Rebar_Steel_Grade': u'49266137-bb93-48bb-8473-1cd1b14bef3a',
    u'NOSA_Rebar_Mass_Per_Length': u'e8842236-4817-44c4-a658-bfb3cbee40e4',
    u'NOSA_Rebar_Total_Length': u'5091b739-01c2-48e0-a212-4f181cfb85e4',
    u'NOSA_Rebar_Cut_Length': u'bafe48b8-787a-4bf8-90f4-ab0a5c39224d',
    u'NOSA_Rebar_Coupler_Start': u'c82adfee-18de-4d2d-ac96-7f45124fa11c',
    u'NOSA_Rebar_Coupler_End': u'490f6e0f-fe07-44b7-9828-a674e211c799',
    u'NOSA_Rebar_EndTreatment_Start': u'caca5c09-7644-443e-bab1-07d48a4e701d',
    u'NOSA_Rebar_EndTreatment_End': u'c4fb884e-26f8-40e8-aada-888d59d95603',
    u'NOSA_Rebar_Export_Id': u'4669bb75-74d7-456b-87d0-791cd3c4382d',
    u'NOSA_Rebar_BVBS_Line': u'f2fb2f85-aa1c-40b1-bf29-ab1fc59357b2',
    # NOSA_Rebar_Detailing
    u'NOSA_Rebar_Tag_Offset_X': u'1fa47447-1b45-4516-8a07-a6590a69b83b',
    u'NOSA_Rebar_Tag_Offset_Y': u'245b5c8c-1813-4935-8c27-8d89df2d48f3',
    u'NOSA_Rebar_Detail_Section_Id': u'2abdcbaa-8f6b-48e1-8607-26d6efc679d0',
    u'NOSA_Rebar_Show_In_Schedule': u'ff5b23e1-7668-48ad-b600-71b754a212bb',
}


# ══════════════════════════════════════════════════════════════════════════
# .txt parser + CI fixture check
# ══════════════════════════════════════════════════════════════════════════

def test_txt_file_has_exactly_40_params():
    parsed = shared_params.parse_shared_parameters_txt()
    assert len(parsed['params']) == 40, len(parsed['params'])


def test_txt_file_guids_are_unique():
    parsed = shared_params.parse_shared_parameters_txt()
    guids = [p['guid'] for p in parsed['params']]
    assert len(guids) == len(set(guids)), 'duplicate GUID found in NOSA_SharedParameters.txt'


def test_txt_file_names_are_unique():
    parsed = shared_params.parse_shared_parameters_txt()
    names = [p['name'] for p in parsed['params']]
    assert len(names) == len(set(names)), 'duplicate parameter name found'


def test_txt_file_matches_the_part05_fixture_exactly():
    """The actual CI requirement (Part 14): every GUID in the .txt
    matches this fixture, derived from the blueprint's own Part 05
    tables — name-for-name, GUID-for-GUID, nothing missing, nothing
    extra."""
    parsed = shared_params.parse_shared_parameters_txt()
    txt_guids_by_name = {p['name']: p['guid'] for p in parsed['params']}

    assert set(txt_guids_by_name.keys()) == set(_FIXTURE_GUIDS_BY_NAME.keys()), (
        u'parameter set mismatch:\n  only in .txt: {}\n  only in fixture: {}'.format(
            set(txt_guids_by_name) - set(_FIXTURE_GUIDS_BY_NAME),
            set(_FIXTURE_GUIDS_BY_NAME) - set(txt_guids_by_name)))

    mismatches = []
    for name, expected_guid in _FIXTURE_GUIDS_BY_NAME.items():
        actual_guid = txt_guids_by_name[name]
        if actual_guid.lower() != expected_guid.lower():
            mismatches.append(u'{}: txt={} fixture={}'.format(name, actual_guid, expected_guid))
    assert not mismatches, u'GUID mismatch(es):\n' + u'\n'.join(mismatches)


def test_guid_format_is_a_valid_uuid():
    uuid_pattern = re.compile(
        r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$', re.IGNORECASE)
    parsed = shared_params.parse_shared_parameters_txt()
    for p in parsed['params']:
        assert uuid_pattern.match(p['guid']), u'not a valid UUID: {} ({})'.format(
            p['guid'], p['name'])


def test_groups_match_the_5_expected_names():
    parsed = shared_params.parse_shared_parameters_txt()
    assert parsed['groups'] == {
        1: u'NOSA_Rebar_Identity',
        2: u'NOSA_Rebar_Shape',
        3: u'NOSA_Rebar_Status',
        4: u'NOSA_Rebar_Fabrication',
        5: u'NOSA_Rebar_Detailing',
    }


def test_every_param_belongs_to_a_declared_group():
    parsed = shared_params.parse_shared_parameters_txt()
    group_ids = set(parsed['groups'].keys())
    for p in parsed['params']:
        assert p['group_id'] in group_ids, u'{} references undeclared group {}'.format(
            p['name'], p['group_id'])


def test_finalized_is_the_one_status_flag_marked_user_modifiable():
    """The one deliberate exception documented in the .txt's own
    header: NOSA_Rebar_Finalized MUST be user-modifiable (it's the
    "do not regenerate" flag the user sets), unlike every other
    Status-group bookkeeping field."""
    parsed = shared_params.parse_shared_parameters_txt()
    by_name = {p['name']: p for p in parsed['params']}
    assert by_name[u'NOSA_Rebar_Finalized']['usermodifiable'] is True
    assert by_name[u'NOSA_Rebar_Created_By_NOSA']['usermodifiable'] is False
    assert by_name[u'NOSA_Rebar_Batch_Id']['usermodifiable'] is False


# ══════════════════════════════════════════════════════════════════════════
# stamp_provenance (pure — a fake element, no Revit)
# ══════════════════════════════════════════════════════════════════════════

class _FakeParam(object):
    def __init__(self):
        self.value = None

    def Set(self, v):
        self.value = v


class _FakeElement(object):
    def __init__(self):
        self._params = {}

    def LookupParameter(self, name):
        return self._params.setdefault(name, _FakeParam())

    def get_Parameter(self, guid):
        raise Exception(u'System.Guid is not available outside Revit')


def test_stamp_provenance_writes_exactly_the_5_mandatory_fields():
    elem = _FakeElement()
    ctx = {'batch_id': u'RA-20260827-153012-a1b2', 'generator_version': u'1.0.0-dev',
           'standard_code': u'EHE-08'}
    results = shared_params.stamp_provenance(elem, ctx)
    assert set(results.keys()) == {
        u'NOSA_Rebar_Created_By_NOSA', u'NOSA_Rebar_Batch_Id',
        u'NOSA_Rebar_Generator_Version', u'NOSA_Rebar_Standard_Code',
        u'NOSA_Rebar_Last_Modified'}
    assert all(results.values()), u'a provenance field failed to write: {}'.format(results)


def test_stamp_provenance_values_are_correct():
    elem = _FakeElement()
    ctx = {'batch_id': u'RA-20260827-153012-a1b2', 'generator_version': u'1.0.0-dev',
           'standard_code': u'EHE-08'}
    shared_params.stamp_provenance(elem, ctx)
    assert elem._params[u'NOSA_Rebar_Created_By_NOSA'].value == 1  # bool True -> Set(1)
    assert elem._params[u'NOSA_Rebar_Batch_Id'].value == u'RA-20260827-153012-a1b2'
    assert elem._params[u'NOSA_Rebar_Generator_Version'].value == u'1.0.0-dev'
    assert elem._params[u'NOSA_Rebar_Standard_Code'].value == u'EHE-08'
    assert isinstance(elem._params[u'NOSA_Rebar_Last_Modified'].value, str)
    assert elem._params[u'NOSA_Rebar_Last_Modified'].value  # non-empty


def test_stamp_provenance_missing_ctx_keys_default_to_empty_not_a_crash():
    elem = _FakeElement()
    shared_params.stamp_provenance(elem, {})  # no batch_id/generator_version/standard_code at all
    assert elem._params[u'NOSA_Rebar_Batch_Id'].value == u''
    assert elem._params[u'NOSA_Rebar_Generator_Version'].value == u''
    assert elem._params[u'NOSA_Rebar_Standard_Code'].value == u''


def test_write_returns_false_when_parameter_not_found():
    class _NoParamsElement(object):
        def LookupParameter(self, name):
            return None
        def get_Parameter(self, guid):
            raise Exception('no System.Guid outside Revit')
    assert shared_params.write(_NoParamsElement(), 'NOSA_Rebar_Mark', u'Z12-01') is False


def test_read_returns_default_when_parameter_not_found():
    class _NoParamsElement(object):
        def LookupParameter(self, name):
            return None
        def get_Parameter(self, guid):
            raise Exception('no System.Guid outside Revit')
    assert shared_params.read(_NoParamsElement(), 'NOSA_Rebar_Mark', default=u'N/A') == u'N/A'


# ══════════════════════════════════════════════════════════════════════════
# rebar_batch.new_batch_id / make_ctx (pure, no Revit)
# ══════════════════════════════════════════════════════════════════════════

_BATCH_ID_PATTERN = re.compile(r'^RA-\d{8}-\d{6}-\d{6}-[0-9a-f]{8}$')


def test_new_batch_id_matches_the_documented_format():
    batch_id = rebar_batch.new_batch_id()
    assert _BATCH_ID_PATTERN.match(batch_id), batch_id


def test_new_batch_id_is_unique_across_many_calls():
    ids = [rebar_batch.new_batch_id() for _ in range(200)]
    assert len(ids) == len(set(ids)), 'collision found in 200 generated batch ids'


def test_make_ctx_default_standard_code_is_ehe08():
    ctx = rebar_batch.make_ctx(doc=None, standard=None, generator_version=u'1.0.0-dev')
    assert ctx['standard_code'] == u'EHE-08'
    assert ctx['standard'] is None  # F1 does not depend on F2
    assert ctx['generator_version'] == u'1.0.0-dev'
    assert _BATCH_ID_PATTERN.match(ctx['batch_id'])


def test_make_ctx_accepts_an_explicit_standard_code():
    ctx = rebar_batch.make_ctx(
        doc=None, standard=None, generator_version=u'1.0.0-dev', standard_code=u'BS-8666-2020')
    assert ctx['standard_code'] == u'BS-8666-2020'


def test_batch_result_container_holds_its_fields():
    result = rebar_batch.BatchResult(
        batch_id=u'RA-x', created=[1, 2, 3], skipped=[], errors=[u'oops'], summary={'created': 3})
    assert result.batch_id == u'RA-x'
    assert result.created == [1, 2, 3]
    assert result.errors == [u'oops']
    assert result.summary == {'created': 3}


# ══════════════════════════════════════════════════════════════════════════
# rebar_project.py (pure — a fake doc with .PathName/.Title only)
# ══════════════════════════════════════════════════════════════════════════

class _FakeDoc(object):
    def __init__(self, path_name=u'', title=u'Untitled'):
        self.PathName = path_name
        self.Title = title


def test_rebar_project_load_returns_defaults_when_nothing_saved():
    doc = _FakeDoc(path_name=u'C:\\nonexistent\\test_project_{}.rvt'.format(os.getpid()))
    data = rebar_project.load(doc)
    assert data['standard_code'] == u'EHE-08'
    assert data['insert_shared_params_into_user_file'] is False


def test_rebar_project_exists_is_false_before_first_save():
    doc = _FakeDoc(path_name=u'C:\\nonexistent\\test_project_exists_{}.rvt'.format(os.getpid()))
    assert not rebar_project.exists(doc)


def test_rebar_project_save_then_load_roundtrips():
    doc = _FakeDoc(path_name=u'C:\\nonexistent\\test_project_roundtrip_{}.rvt'.format(os.getpid()))
    try:
        assert not rebar_project.exists(doc)
        rebar_project.save(doc, {'project_number': u'1234', 'insert_shared_params_into_user_file': True})
        assert rebar_project.exists(doc)
        reloaded = rebar_project.load(doc)
        assert reloaded['project_number'] == u'1234'
        assert reloaded['insert_shared_params_into_user_file'] is True
        assert reloaded['standard_code'] == u'EHE-08'  # untouched default survives a partial save
    finally:
        try:
            os.remove(rebar_project.config_path(doc))
        except Exception:
            pass


def test_rebar_project_doc_key_falls_back_to_title_when_no_path():
    doc = _FakeDoc(path_name=u'', title=u'MyUnsavedProject')
    key = rebar_project.doc_key(doc)
    assert key  # non-empty, deterministic
    assert key == rebar_project.doc_key(_FakeDoc(path_name=u'', title=u'MyUnsavedProject'))


if __name__ == '__main__':
    tests = [v for k, v in sorted(globals().items()) if k.startswith('test_')]
    failures = 0
    for t in tests:
        try:
            t()
            print(u'{}: OK'.format(t.__name__))
        except Exception as e:
            failures += 1
            print(u'{}: FAILED -- {}'.format(t.__name__, e))
    print(u'\n{}/{} tests passed'.format(len(tests) - failures, len(tests)))
    sys.exit(1 if failures else 0)
