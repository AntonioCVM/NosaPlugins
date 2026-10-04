# -*- coding: utf-8 -*-
"""T8.12: NOSA File Naming Protocol V2.2 rules."""
import datetime
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'lib'))

from nosa_utils import protocol_rules as pr  # noqa: E402


def _f(**kw):
    base = {'f1': u'23999', 'f2': u'NOSA', 'f3': u'GA', 'f4': u'RF0', 'f5': u'D', 'f6': u'S', 'f7': u'2200',
            'f8': u'P01'}
    base.update(kw)
    return base


def sev(issues):
    return sorted(set(s for s, _k, _m in issues))


def test_protocol_example_is_clean():
    assert pr.check_fields(_f()) == []


def test_format_errors():
    issues = pr.check_fields(_f(f1=u'2399', f3=u'G', f7=u'22', f8=u'P1'))
    keys = sorted(k for s, k, _m in issues if s == pr.ERROR)
    assert keys == [u'f1', u'f3', u'f7', u'f8']


def test_new_code_with_right_length_is_only_a_warning():
    issues = pr.check_fields(_f(f4=u'QZ7'))
    assert sev(issues) == [pr.WARNING] and issues[0][1] == u'f4'


def test_numeric_levels_are_valid_spatial_codes():
    assert pr.check_fields(_f(f4=u'005')) == []


def test_draft_suffix_warns():
    issues = pr.check_fields(_f(f8=u'C01.02'))
    assert issues and issues[0][0] == pr.WARNING and u'draft' in issues[0][2]


def test_post_contract_revision_is_valid():
    assert pr.check_fields(_f(f8=u'PC01')) == []


def test_series_against_function_and_form():
    issues = pr.check_fields(_f(f3=u'DT', f7=u'2500'))
    assert [k for s, k, _m in issues] == [u'f3']
    issues = pr.check_fields(_f(f3=u'RP', f5=u'D', f7=u'5500'))
    assert [k for s, k, _m in issues] == [u'f5']


def test_template_numbering_is_the_reference():
    assert pr.series(u'5000')[2] == u'Quantity schedules'
    assert pr.series(u'0900')[2].startswith(u'Specifications')


def test_file_names():
    assert pr.file_name(_f(), u'Roof GA') == u'23999-NOSA-GA-RF0-D-S-2200-P01 Roof GA'
    issue = _f(f3=u'RP', f4=u'XXX', f5=u'L', f7=u'5000', f8=u'P07')
    assert pr.file_name(issue, issue_date=datetime.date(2025, 4, 15)) == \
        u'23999-NOSA-RP-XXX-L-S-5000-P07 Issue Sheet (250415)'
