# -*- coding: utf-8 -*-
"""SheetExportHub file_bundle: Revit file base name, DWG ZIP and removal of the loose files."""
import os
import shutil
import sys
import tempfile
import unittest
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'lib'))
from nosa_utils.bootstrap import load_module  # noqa: E402

fb = load_module('t_sehub_file_bundle', os.path.join(
    ROOT, 'NOSA.tab', 'Documentation.panel', 'SheetExportHub.pushbutton', 'lib', 'file_bundle.py'))


class RevitBaseNameTests(unittest.TestCase):

    def test_local_path_drops_folder_and_extension(self):
        self.assertEqual(fb.revit_base_name(u'C:\\Jobs\\24001\\24001-NOSA-ZZ-XX-M3-S-0001.rvt'),
                         u'24001-NOSA-ZZ-XX-M3-S-0001')

    def test_cloud_path_and_upper_case_extension(self):
        self.assertEqual(fb.revit_base_name(u'Autodesk Docs://Project/Folder/Model Ñ.RVT'), u'Model Ñ')

    def test_unsaved_model_falls_back_to_title(self):
        self.assertEqual(fb.revit_base_name(u'', u'Project1'), u'Project1')
        self.assertEqual(fb.revit_base_name(None, u'Project1.rvt'), u'Project1')


class ZipAndDeleteTests(unittest.TestCase):

    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.dwgs = []
        for i in range(3):
            p = os.path.join(self.dir, u'S-{:04d} Plan ñ.dwg'.format(i))
            with open(p, 'wb') as f:
                f.write(b'AC1032' + os.urandom(2048))
            self.dwgs.append(p)

    def tearDown(self):
        shutil.rmtree(self.dir)

    def test_zip_holds_every_dwg_flat_and_leaves_no_partial_file(self):
        zip_path = os.path.join(self.dir, u'Model.zip')
        zipped = fb.zip_files(self.dwgs + [os.path.join(self.dir, u'missing.dwg')], zip_path)
        self.assertEqual(zipped, self.dwgs)
        with zipfile.ZipFile(zip_path) as zf:
            self.assertEqual(sorted(zf.namelist()), sorted(os.path.basename(p) for p in self.dwgs))
            self.assertIsNone(zf.testzip())
        self.assertEqual(sorted(os.listdir(self.dir)), sorted([u'Model.zip'] + [os.path.basename(p) for p in self.dwgs]))

    def test_zip_replaces_an_old_zip_of_the_same_name(self):
        zip_path = os.path.join(self.dir, u'Model.zip')
        with open(zip_path, 'wb') as f:
            f.write(b'old')
        fb.zip_files(self.dwgs[:1], zip_path)
        with zipfile.ZipFile(zip_path) as zf:
            self.assertEqual(len(zf.namelist()), 1)

    def test_no_files_means_no_zip(self):
        zip_path = os.path.join(self.dir, u'Model.zip')
        self.assertEqual(fb.zip_files([], zip_path), [])
        self.assertFalse(os.path.exists(zip_path))

    def test_zip_then_delete_leaves_only_the_zip(self):
        zip_path = os.path.join(self.dir, u'Model.zip')
        fb.zip_files(self.dwgs, zip_path)
        deleted, failed = fb.delete_files(self.dwgs, keep=[zip_path])
        self.assertEqual((len(deleted), failed), (3, []))
        self.assertEqual(os.listdir(self.dir), [u'Model.zip'])

    def test_delete_never_removes_the_kept_combined_file(self):
        combined = self.dwgs[0]
        deleted, _ = fb.delete_files(self.dwgs, keep=[combined])
        self.assertEqual(len(deleted), 2)
        self.assertTrue(os.path.exists(combined))


if __name__ == '__main__':
    unittest.main()
