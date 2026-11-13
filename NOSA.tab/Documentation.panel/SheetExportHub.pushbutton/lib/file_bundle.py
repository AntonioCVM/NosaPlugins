# -*- coding: utf-8 -*-
"""Pure-Python file helpers for the export bundle: Revit file base name, ZIP of the DWGs, removal of the loose files."""
import os
import zipfile

try:
    unicode
except NameError:
    unicode = str  # CPython 3 compat


def revit_base_name(path, title=u''):
    """File name of a Revit model without folder or .rvt ('' when neither path nor title gives one)."""
    name = u''
    if path:
        name = os.path.basename(unicode(path).replace(u'/', u'\\').rstrip(u'\\'))
        if u'\\' in name:
            name = name.split(u'\\')[-1]
    if not name:
        name = unicode(title or u'')
    if name.lower().endswith(u'.rvt'):
        name = name[:-4]
    return name.strip()


def zip_files(paths, zip_path):
    """Write the existing files of paths into zip_path (flat, by base name) and verify it; returns the files zipped."""
    files = [p for p in paths if os.path.isfile(p)]
    if not files:
        return []
    try:
        import zlib  # noqa: F401 - only to know whether ZIP_DEFLATED is available
        method = zipfile.ZIP_DEFLATED
    except ImportError:
        method = zipfile.ZIP_STORED
    tmp = zip_path + u'.partial'
    if os.path.exists(tmp):
        os.remove(tmp)
    zf = zipfile.ZipFile(tmp, 'w', method, allowZip64=True)
    try:
        for p in files:
            zf.write(p, os.path.basename(p))
    finally:
        zf.close()
    check = zipfile.ZipFile(tmp, 'r')
    try:
        bad = check.testzip()
        count = len(check.namelist())
    finally:
        check.close()
    if bad is not None or count != len(files):
        os.remove(tmp)
        raise IOError(u'ZIP verification failed ({})'.format(bad or u'{} of {} files'.format(count, len(files))))
    if os.path.exists(zip_path):
        os.remove(zip_path)
    os.rename(tmp, zip_path)
    return files


def delete_files(paths, keep=()):
    """Delete each existing file of paths except those in keep; returns (deleted, failed[(path, error)])."""
    keep_norm = set(os.path.normcase(os.path.abspath(k)) for k in keep if k)
    deleted, failed = [], []
    for p in paths:
        if not p or os.path.normcase(os.path.abspath(p)) in keep_norm or not os.path.isfile(p):
            continue
        try:
            os.remove(p)
            deleted.append(p)
        except Exception as e:  # nosa-lint: disable=NOSA006 - reported back to the caller, which logs it
            failed.append((p, e))
    return deleted, failed
