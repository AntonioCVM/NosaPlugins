# -*- coding: utf-8 -*-
"""'Done' marks for clashes, kept in a small JSON file next to the report (shared with the team)."""
import datetime
import io
import json
import os

_SUFFIX = u'.clashreview.json'
_VERSION = 2


def _json_safe(value):
    """IronPython 2.7 returns non-ASCII Windows text (user names, paths) that json cannot encode."""
    try:
        json.dumps(value)
        return value
    except UnicodeDecodeError:
        return value.encode('utf-8')


def _deep_safe(value):
    """Make every string in a loaded structure serialisable again (text re-read from disk breaks IronPython 2.7)."""
    if isinstance(value, dict):
        return dict((_deep_safe(k), _deep_safe(v)) for k, v in value.items())
    if isinstance(value, (list, tuple)):
        return [_deep_safe(v) for v in value]
    if isinstance(value, (type(u''), bytes)):
        return _json_safe(value)
    return value


def _text(value):
    return value if isinstance(value, type(u'')) else value.decode('ascii', 'replace')


class ReviewStore(object):
    """Marks keyed by clash key; every change is merged with what is on disk before saving."""

    def __init__(self, path, fallback_path=None):
        self.path = path
        self.fallback_path = fallback_path
        self.message = u''
        self._marks = {}
        self._notes = {}
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

    def set_many(self, keys, done, user=u''):
        """Mark or unmark several keys with a single save; returns True when it could be saved."""
        self.reload()
        stamp = datetime.datetime.now().strftime('%Y-%m-%d %H:%M')
        for key in keys:
            if done:
                self._marks[key] = {u'by': user or u'', u'at': stamp}
            else:
                self._marks.pop(key, None)
        return self._save()

    def note(self, key):
        """The note text for ``key`` (u'' when there is none)."""
        return (self._notes.get(key) or {}).get(u'text', u'')

    def note_info(self, key):
        return self._notes.get(key)

    def set_note(self, key, text, user=u''):
        """Store (or clear, when empty) the note of ``key``; returns True when it could be saved."""
        self.reload()
        text = (text or u'').strip()
        if text:
            self._notes[key] = {
                u'text': text,
                u'by': user or u'',
                u'at': datetime.datetime.now().strftime('%Y-%m-%d %H:%M'),
            }
        else:
            self._notes.pop(key, None)
        return self._save()

    # ---------------------------------------------------------------- changes

    def set_done(self, key, done, user=u''):
        """Mark or unmark ``key``; returns True when it could be saved."""
        self.reload()
        if done:
            self._marks[key] = {
                u'by': user or u'',
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
                    self._notes = dict(data.get('notes', {}))
                    return
                except (IOError, OSError, ValueError):
                    self.message = u'The review file could not be read: %s' % candidate
        self._marks = {}
        self._notes = {}

    def _write(self, path):
        folder = os.path.dirname(path)
        if folder and not os.path.isdir(folder):
            os.makedirs(folder)
        payload = _deep_safe({u'version': _VERSION, u'done': self._marks, u'notes': self._notes})
        text = json.dumps(payload, indent=1, sort_keys=True)
        tmp = path + u'.tmp'
        with io.open(tmp, 'w', encoding='utf-8') as fh:
            fh.write(_text(text))
        if os.path.isfile(path):
            os.remove(path)
        os.rename(tmp, path)

    def _save(self):
        try:
            self._write(self.path)
            self.message = u''
            return True
        except (IOError, OSError):
            if not self.fallback_path or self.fallback_path == self.path:
                self.message = u'The marks could not be saved.'
                return False
        try:
            self._write(self.fallback_path)
        except (IOError, OSError):
            self.message = u'The marks could not be saved.'
            return False
        self.path = self.fallback_path
        self.message = u'The report folder is read-only: marks are kept on this computer only.'
        return True
