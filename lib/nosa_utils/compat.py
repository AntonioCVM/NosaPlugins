# -*- coding: utf-8 -*-
"""
nosa_utils.compat
=================
IronPython 2.7 / CPython 3 shims.

Import from here instead of using the Python 2 text builtins, basestring or xrange directly.
"""
import sys

PY3 = sys.version_info[0] >= 3

if PY3:
    text_type    = str
    binary_type  = bytes
    string_types = (str,)
    integer_types = (int,)

    def _range(*args):
        return range(*args)

    def iteritems(d):
        return d.items()

    def itervalues(d):
        return d.values()

    def ensure_text(s, encoding='utf-8'):
        if isinstance(s, bytes):
            return s.decode(encoding)
        return str(s)

    def ensure_bytes(s, encoding='utf-8'):
        if isinstance(s, str):
            return s.encode(encoding)
        return s

else:
    text_type     = unicode      # noqa: F821
    binary_type   = str
    string_types  = (str, unicode)  # noqa: F821
    integer_types = (int, long)     # noqa: F821

    def _range(*args):
        return xrange(*args)  # noqa: F821

    def iteritems(d):
        return d.iteritems()

    def itervalues(d):
        return d.itervalues()

    def ensure_text(s, encoding='utf-8'):
        if isinstance(s, unicode):  # noqa: F821
            return s
        if isinstance(s, str):
            return s.decode(encoding)
        return unicode(s)  # noqa: F821

    def ensure_bytes(s, encoding='utf-8'):
        if isinstance(s, unicode):  # noqa: F821
            return s.encode(encoding)
        return s
