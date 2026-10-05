# -*- coding: utf-8 -*-
"""nosa_utils.material_groups: material classification for the concrete and steel schedules."""
import os
import sys
import unittest

_LIB = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'lib'))
if _LIB not in sys.path:
    sys.path.insert(0, _LIB)

from nosa_utils import material_groups as mg  # noqa: E402


class MaterialGroupsTests(unittest.TestCase):

    def test_template_materials(self):
        cases = {
            u'Concrete - RC32/40': u'Concrete', u'Precast Concrete': u'Concrete',
            u'Concrete - Cast-in-Place Concrete RC40/50': u'Concrete', u'Concrete - Generic': u'Concrete',
            u'Piling concrete': u'Piling', u'Sand/cement screed /blinding': u'Other',
            u'Structural Steel - S355': u'Structural steel', u'Metal - Steel 43-275': u'Structural steel',
            u'LGSF': u'Structural steel', u'Steel Rebar - B500A, B or C': u'Reinforcement',
            u'Timber': u'Timber', u'Blockwork': u'Masonry', u'Brickwork': u'Masonry',
            u'Glass': u'Other', u'Rigid insulation': u'Other', u'MOT Type 1 well compacted': u'Other',
            u'Default Wall': u'Other', u'Site - Earth': u'Other',
        }
        for name, group in cases.items():
            self.assertEqual(mg.classify(name), group, name)

    def test_class_concrete_without_the_word(self):
        self.assertEqual(mg.classify(u'C32/40 in-situ', u'Concrete'), u'Concrete')
        self.assertEqual(mg.classify(u'Mystery', u''), u'Other')

    def test_groups_are_concrete_plus_the_excluded_ones(self):
        self.assertEqual(mg.GROUPS[0], u'Concrete')
        self.assertNotIn(u'Concrete', mg.NON_CONCRETE)


if __name__ == '__main__':
    unittest.main()
