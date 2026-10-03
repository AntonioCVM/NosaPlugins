# -*- coding: utf-8 -*-
"""rebar_content: packaged family versions against loaded ones (T4.3)."""
from __future__ import absolute_import, print_function, unicode_literals
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'lib'))
import rebar_content as rc  # noqa: E402


def test_manifest_lists_the_tag_family():
    families = rc.load_manifest()
    assert [f['name'] for f in families] == [u'NOSA Rebar Tag']
    assert rc.parse_version(families[0]['version']) == (1, 0, 0)
    assert families[0]['file'].startswith(u'content/')


def test_family_status():
    assert rc.family_status(u'1.0.0', None) == rc.MISSING
    assert rc.family_status(u'1.0.0', u'') == rc.UNVERSIONED
    assert rc.family_status(u'1.2.0', u'1.1.9') == rc.OUTDATED
    assert rc.family_status(u'1.2.0', u'1.10.0') == rc.OK   # numeric, not text, comparison
    assert rc.family_status(u'1.0.0', u'1.0.0') == rc.OK


def test_status_lines_only_for_families_needing_attention():
    report = [{'name': u'A', 'version': u'1.0.0', 'loaded': u'1.0.0', 'status': rc.OK},
              {'name': u'B', 'version': u'1.1.0', 'loaded': u'1.0.0', 'status': rc.OUTDATED},
              {'name': u'C', 'version': u'1.0.0', 'loaded': None, 'status': rc.MISSING}]
    lines = rc.status_lines(report)
    assert len(lines) == 2 and u'B 1.0.0 is older than the packaged 1.1.0' in lines[0]
    assert lines[1].startswith(u'C is not loaded')


if __name__ == '__main__':
    for name, fn in sorted(globals().items()):
        if name.startswith('test_'):
            fn()
            print(name, 'OK')
