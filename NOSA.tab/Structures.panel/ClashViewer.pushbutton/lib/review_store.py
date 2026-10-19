# -*- coding: utf-8 -*-
"""'Done' marks for clashes, kept in a small JSON file next to the report (shared with the team)."""
import datetime
import io
import json
import os

_SUFFIX = u'.clashreview.json'
_VERSION = 1


def _json_safe(value):
    """IronPython 2.7 returns non-ASCII Windows text (user names, paths) that json cannot encode."""
    try:
        json.dumps(value)
        return value
    except UnicodeDecodeError:
        return value.encode('utf-8')


def _text(value):
    return value if isinstance(value, type(u'')) else value.decode('ascii', 'replace')


class ReviewStore(object):
    """Marks keyed by clash key; every change is merged with what is on disk before saving."""

    def __init__(self, path, fallback_path=None):
        self.path = path
        self.fallback_path = fallback_path
        self.note = u''
        self._marks = {}
        self.reload()

    @classmethod
    def for_report(cls, report_path, document_code, local_dir):
        """Sidecar named after the document code (stable across revisions P02, P03…)."""
        beside = os.path.join(os.path.dirname(report_path), document_code + _SUFFIX)
        local = os.path.join(local_dir, u'_clash_review_%s.json' % document_code)
        return cls(beside, local)

    # ---------------------------------------------------------------- queries

    def is_done(self, key):
        return key in self._marks

    def info(self, key):
        return self._marks.get(key)

    @property
    def done_count(self):
        return len(self._marks)

    # ---------------------------------------------------------------- changes

    def set_done(self, key, done, user=u''):
        """Mark or unmark ``key``; returns True when it could be saved."""
        self.reload()
        if done:
            self._marks[key] = {
                u'by': _json_safe(user or u''),
                u'at': datetime.datetime.now().strftime('%Y-%m-%d %H:%M'),
            }
        else:
            self._marks.pop(key, None)
        return self._save()

    # ------------------------------------------------------------------- disk

    def reload(self):
        for candidate in (self.path, self.fallback_path):
            if candidate and os.path.isfile(candidate):
                try:
                    with io.open(candidate, 'r', encoding='utf-8') as fh:
                        data = json.load(fh)
                    self._marks = dict(data.get('done', {}))
                    return
                except (IOError, OSError, ValueError):
                    self.note = u'The review file could not be read: %s' % candidate
        self._marks = {}

    def _write(self, path):
        folder = os.path.dirname(path)
        if folder and not os.path.isdir(folder):
            os.makedirs(folder)
        text = json.dumps({u'version': _VERSION, u'done': self._marks}, indent=1, sort_keys=True)
        tmp = path + u'.tmp'
        with io.open(tmp, 'w', encoding='utf-8') as fh:
            fh.write(_text(text))
        if os.path.isfile(path):
            os.remove(path)
        os.rename(tmp, path)

    def _save(self):
        try:
            self._write(self.path)
            self.note = u''
            return True
        except (IOError, OSError):
            if not self.fallback_path or self.fallback_path == self.path:
                self.note = u'The marks could not be saved.'
                return False
        try:
            self._write(self.fallback_path)
        except (IOError, OSError):
            self.note = u'The marks could not be saved.'
            return False
        self.path = self.fallback_path
        self.note = u'The report folder is read-only: marks are kept on this computer only.'
        return True
