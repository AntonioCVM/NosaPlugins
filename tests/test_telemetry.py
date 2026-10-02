# -*- coding: utf-8 -*-
"""nosa_utils.telemetry writes UTF-8, logs a swallowed error once per site, never needs pyRevit."""
import io
import os
import shutil
import sys
import tempfile
import unittest

_LIB = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'lib'))
if _LIB not in sys.path:
    sys.path.insert(0, _LIB)

from nosa_utils import telemetry  # noqa: E402


class TelemetryTests(unittest.TestCase):

    def setUp(self):
        self.folder = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.folder, True)
        self.saved = (telemetry._LOG_DIR, telemetry._LOG_FILE)
        telemetry._LOG_DIR = self.folder
        telemetry._LOG_FILE = os.path.join(self.folder, 'nosa_errors.log')

    def tearDown(self):
        telemetry._LOG_DIR, telemetry._LOG_FILE = self.saved

    def _log(self):
        with io.open(telemetry._LOG_FILE, encoding='utf-8') as f:
            return f.read()

    def test_non_ascii_messages_are_kept(self):
        telemetry.log_error('Test', u'Sección de muro — Viñas', u'Traceback\n  línea 1')
        telemetry.log_info('Test', u'Cerámica ✓')
        text = self._log()
        for piece in (u'Sección de muro — Viñas', u'línea 1', u'Cerámica ✓'):
            self.assertIn(piece, text)

    def test_swallowed_exception_logged_once_per_site(self):
        for _ in range(3):
            try:
                raise ValueError(u'boom')
            except ValueError:
                telemetry.log_swallowed('Test', u'unit_site_{}'.format(id(self)))
        self.assertEqual(self._log().count(u'swallowed in unit_site_'), 1)

    def test_revit_version_without_revit_does_not_import_pyrevit(self):
        self.assertEqual(telemetry._revit_version(), u'unknown')
        self.assertNotIn('pyrevit', sys.modules.get('nosa_utils.telemetry').__dict__)


if __name__ == '__main__':
    unittest.main()
