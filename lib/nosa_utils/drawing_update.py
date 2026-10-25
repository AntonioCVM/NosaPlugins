# -*- coding: utf-8 -*-
"""
T12.9 (user 2026-10-24): "Update drawings" instead of regenerating them, no Revit. What the plugin drew in a view is
kept in a record (view key, crop, scale, viewport centre, each annotation's fingerprint and its bar's signature);
an update compares the drawing as it now is with it to tell the user's changes from the plugin's own work.
Points are view or sheet mm; tolerances paper mm.
"""
import json
import re

MOVED_PAPER_MM = 0.5
RECORD_VERSION = 1

KEEP = 'keep'               # moved by the user, its bar unchanged: copied into the new view as it stands
RELAY = 'relay'             # the plugin's own, or its bar changed: laid out again by the plugin
GONE = 'gone'               # its bar deleted: not drawn again
GONE_MOVED = 'gone_moved'   # its bar deleted after the user moved it: reported


def view_key(host_ids, kind, title):
    """'1513973|elevation|Elevation': which member's which view, stable across runs."""
    return u'{}|{}|{}'.format(u'-'.join(u'{}'.format(i) for i in sorted(host_ids)), kind or u'', title or u'')


def bar_signature(count, length_mm, shape, bar_type, varying=False):
    """What a bar is, its mark aside (marks follow the bar): positions, total length to 1 mm, shape, type."""
    return u'{}|{}|{}|{}|{}'.format(int(count), int(round(length_mm)), shape or u'', bar_type or u'',
                                    u'V' if varying else u'')


def moved(now, saved, scale, tol_paper_mm=MOVED_PAPER_MM):
    """Any point of a fingerprint off its saved place by more than tol on paper (now, saved: [(x, y)] view mm)."""
    if saved is None or now is None or len(now) != len(saved):
        return now != saved
    tol = tol_paper_mm * max(1, scale or 1)
    return any(abs(a[0] - b[0]) > tol or abs(a[1] - b[1]) > tol for a, b in zip(now, saved))


def tag_action(entry, now_points, signatures, scale):
    """
    What an update does with one of the plugin's annotations. entry: its record {'bars': [id], 'points', 'sig':
    {id: signature}, 'kept'}; now_points: where it stands now (None when the user deleted it); signatures: {bar id:
    signature} of the bars still in the model.
    """
    bars = entry.get('bars') or []
    alive = [b for b in bars if u'{}'.format(b) in signatures]
    user_moved = entry.get('kept') or (now_points is not None and moved(now_points, entry.get('points'), scale))
    if bars and not alive:
        return GONE_MOVED if user_moved else GONE
    if not user_moved or now_points is None:
        return RELAY
    same = all(signatures.get(u'{}'.format(b)) == (entry.get('sig') or {}).get(u'{}'.format(b)) for b in bars)
    return KEEP if same else RELAY


def view_changed(record, crop, scale, tol_mm=1.0):
    """
    The user's own crop or scale on a view: (crop, scale) theirs, against what the plugin set - or kept as theirs
    by an update before (the record says so: once the user's, always the user's).
    """
    if not record:
        return False, False
    saved = record.get('crop')
    crop_moved = bool(saved and crop and any(abs(a - b) > tol_mm for a, b in zip(crop, saved)))
    scale_moved = bool(record.get('scale') and scale and int(scale) != int(record['scale']))
    return crop_moved or bool(record.get('user_crop')), scale_moved or bool(record.get('user_scale'))


def viewport_moved(record, centre, tol_mm=1.0):
    """The user moved the view on its sheet, now or before an update that kept it there."""
    record = record or {}
    if record.get('user_place'):
        return True
    saved = record.get('centre')
    return bool(saved and centre and (abs(centre[0] - saved[0]) > tol_mm or abs(centre[1] - saved[1]) > tol_mm))


def encode(record):
    out = dict(record)
    out['v'] = RECORD_VERSION
    return json.dumps(out, sort_keys=True)


def decode(text):
    """A view's or sheet's record; {} when it has none or it does not read."""
    if not text:
        return {}
    try:
        out = json.loads(text)
    except ValueError:
        return {}
    return out if isinstance(out, dict) and out.get('v') == RECORD_VERSION else {}


class NumberPool(object):
    """Sheet numbers for one drawing: its own old numbers first, then the shared free ones (pop(0) as a list)."""

    def __init__(self, own, shared):
        self.own = list(own)
        self.shared = shared

    def pop(self, index=0):
        if self.own:
            number = self.own.pop(0)
            if number in self.shared:
                self.shared.remove(number)
            return number
        return self.shared.pop(0)

    def __len__(self):
        return len(self.own) + len(self.shared)


def keep_marks(bars):
    """
    Update (T12.9, decision M1): the marks bars already carry stay, new bars get numbers. bars: [(bar id, number,
    identity key)] -> ({identity key: number} kept, [bar id] to number). A number already taken by another kind of
    bar is not kept twice.
    """
    known, taken, todo = {}, {}, []
    for bar, number, key in bars:
        if number <= 0:
            todo.append(bar)
            continue
        if key in known:
            if known[key] != number:
                todo.append(bar)
            continue
        if taken.get(number, key) != key:
            todo.append(bar)
            continue
        known[key] = number
        taken[number] = key
    return known, todo


def issue_date(day):
    """A sheet's issue date as the drawings write it: dd/mm/yy (decision 2026-10-24)."""
    return u'{:02d}/{:02d}/{:02d}'.format(day.day, day.month, day.year % 100)


def from_revit_date(text):
    """
    Revit's own Sheet Issue Date of a new sheet, m/d/yy (10/24/26), as dd/mm/yy; None when it does not read so
    (a date the user wrote is kept as it is).
    """
    m = re.match(u'^\s*(\d{1,2})/(\d{1,2})/(\d{2}|\d{4})\s*$', text or u'')
    if not m:
        return None
    month, day, year = int(m.group(1)), int(m.group(2)), int(m.group(3)) % 100
    if not (1 <= month <= 12 and 1 <= day <= 31):
        return None
    return u'{:02d}/{:02d}/{:02d}'.format(day, month, year)
