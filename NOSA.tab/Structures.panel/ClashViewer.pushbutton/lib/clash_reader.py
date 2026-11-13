# -*- coding: utf-8 -*-
"""Clash report (.xlsm) reader - stdlib only, runs on IronPython 2.7 and CPython 3."""
import io
import re
import zipfile
import posixpath
import collections
import xml.etree.ElementTree as ET

_NS_MAIN = '{http://schemas.openxmlformats.org/spreadsheetml/2006/main}'
_NS_REL = '{http://schemas.openxmlformats.org/officeDocument/2006/relationships}'
_NS_PKG = '{http://schemas.openxmlformats.org/package/2006/relationships}'
_NS_XDR = '{http://schemas.openxmlformats.org/drawingml/2006/spreadsheetDrawing}'
_NS_A = '{http://schemas.openxmlformats.org/drawingml/2006/main}'

STATUSES = ('New', 'Active', 'Reviewed', 'Approved', 'Resolved')

_RE_POINT = re.compile(
    r'x\s*:\s*(-?\d+(?:\.\d+)?)\s*,\s*y\s*:\s*(-?\d+(?:\.\d+)?)\s*,\s*z\s*:\s*(-?\d+(?:\.\d+)?)',
    re.I)
_RE_WS = re.compile(r'\s+')
_RE_CLASH_NAME =re.compile(r'^clash\s*\d+$', re.I)
_RE_DOC_CODE = re.compile(r'^[A-Z0-9]+-[A-Z0-9]+-\d\d-[A-Z]+-[A-Z]+-\d+$')
_RE_DATE = re.compile(r'(\d{4})\s*[/-]\s*(\d{1,2})\s*[/-]\s*(\d{1,2})(?:\s+(\d{1,2}):(\d{2}))?')
_RE_SPLIT_ASSIGNEES = re.compile(r'\s*(?:&|;|/|\+)\s*')

# Item header (lower case, spaces collapsed) -> ClashItem attribute.
_ITEM_FIELDS = {
    u'path': 'path',
    u'element category': 'category',
    u'element family': 'family',
    u'element id': 'element_id_raw',
    u'autocad class': 'acad_class',
    u'autocad size': 'acad_size',
    u'autocad tag': 'acad_tag',
    u'autocad pnpguid': 'pnp_guid',
}

_BASE_FIELDS = {
    u'image': 'image',
    u'clash group': 'group',
    u'clash name': 'name',
    u'status': 'status',
    u'assigned to': 'assigned',
    u'date approved': 'date_raw',
    u'clash point': 'point_raw',
}


class ClashReaderError(Exception):
    """Raised with a user-readable message when a report cannot be read."""


def _norm(value):
    if value is None:
        return u''
    text = value if isinstance(value, type(u'')) else value.decode('utf-8', 'replace') \
        if isinstance(value, bytes) else u'%s' % (value,)
    return _RE_WS.sub(u' ', text.replace(u'\xa0', u' ')).strip()


def _key(value):
    return _norm(value).lower()


def _to_int(value):
    text = _norm(value)
    if not text:
        return None
    if re.match(r'^-?\d+$', text):
        return int(text)
    try:
        return int(float(text))
    except ValueError:
        return None


def _col_index(letters):
    n = 0
    for ch in letters.upper():
        n = n * 26 + (ord(ch) - 64)
    return n


def _split_ref(ref):
    m = re.match(r'^([A-Za-z]+)(\d+)$', ref or '')
    if not m:
        return None, None
    return _col_index(m.group(1)), int(m.group(2))


def _read_file_bytes(path):
    try:
        with open(path, 'rb') as fh:
            return fh.read()
    except (IOError, OSError) as first:
        try:
            import clr  # noqa: F401  (IronPython / pythonnet only)
            from System.IO import FileStream, FileMode, FileAccess, FileShare, MemoryStream
            stream = FileStream(path, FileMode.Open, FileAccess.Read, FileShare.ReadWrite)
            try:
                buf = MemoryStream()
                stream.CopyTo(buf)
                return bytes(bytearray(buf.ToArray()))
            finally:
                stream.Close()
        except Exception:
            raise ClashReaderError(
                u'The report could not be opened. If it is open in Excel, close it '
                u'and try again.\n\n%s' % (first,))


def _buffer(data):
    """Seekable in-memory file: IronPython 2.7's zipfile rejects io.BytesIO, wants cStringIO."""
    try:
        from cStringIO import StringIO
        return StringIO(data)
    except ImportError:
        return io.BytesIO(data)


class _Package(object):
    """In-memory OOXML package (the whole file is read once, so Excel never stays locked)."""

    def __init__(self, data):
        try:
            self.zf = zipfile.ZipFile(_buffer(data))
        except zipfile.BadZipfile:
            raise ClashReaderError(u'The file is not a valid Excel workbook (.xlsx / .xlsm).')
        self.names = set(self.zf.namelist())

    def has(self, name):
        return name in self.names

    def read(self, name):
        return self.zf.read(name)

    def xml(self, name):
        return ET.fromstring(self.zf.read(name))


class ClashItem(object):
    """One side (Item 1 / Item 2) of a clash."""

    def __init__(self):
        self.path = u''
        self.category = u''
        self.family = u''
        self.element_id_raw = u''
        self.unique_id = u''
        self.acad_class = u''
        self.acad_size = u''
        self.acad_tag = u''
        self.pnp_guid = u''
        self.extra = {}

    @property
    def element_id(self):
        return _to_int(self.element_id_raw)

    @property
    def model_base(self):
        base = self.path.replace('\\', '/').split('/')[-1]
        return re.sub(r'\.(nwc|nwd|rvt)$', u'', base, flags=re.I)

    def _code_parts(self):
        return self.model_base.split('-')

    @property
    def author(self):
        parts = self._code_parts()
        return parts[1] if len(parts) >= 6 else u''

    @property
    def discipline(self):
        parts = self._code_parts()
        return parts[3] if len(parts) >= 6 else u''

    @property
    def is_plant(self):
        return bool(self.acad_class or self.acad_tag or self.pnp_guid)

    @property
    def is_revit(self):
        return self.element_id is not None or bool(self.unique_id)

    @property
    def is_empty(self):
        return not (self.path or self.category or self.element_id_raw or self.unique_id
                    or self.is_plant)

    @property
    def label(self):
        if self.is_plant:
            return u' '.join(x for x in (self.acad_class, self.acad_tag) if x) or u'AutoCAD item'
        return u' / '.join(x for x in (self.category, self.family) if x) or u'-'


class Clash(object):
    def __init__(self, test):
        self.test = test
        self.row = 0
        self.group = u''
        self.name = u''
        self.status = u''
        self.assigned = u''
        self.date_raw = u''
        self.point_raw = u''
        self.item1 = ClashItem()
        self.item2 = ClashItem()
        self.extra = {}

    @property
    def image_member(self):
        return self.test.image_for_row(self.row)

    @property
    def key(self):
        return u'%s|%s' % (self.test.sheet_name, self.name)

    @property
    def assignees(self):
        return [p for p in _RE_SPLIT_ASSIGNEES.split(self.assigned) if p]

    @property
    def date_approved(self):
        m = _RE_DATE.search(self.date_raw)
        if not m:
            return self.date_raw
        y, mo, d, hh, mm = m.groups()
        out = u'%04d-%02d-%02d' % (int(y), int(mo), int(d))
        if hh is not None:
            out += u' %02d:%s' % (int(hh), mm)
        return out

    @property
    def point_mm(self):
        m = _RE_POINT.search(self.point_raw or u'')
        if not m:
            return None
        return (float(m.group(1)), float(m.group(2)), float(m.group(3)))

    @property
    def items(self):
        return (self.item1, self.item2)


class ClashTest(object):
    """One test (sheet) of the report."""

    def __init__(self, sheet_name):
        self.sheet_name = sheet_name
        self.name = sheet_name
        self.tolerance = u''
        self.test_type = u''
        self.test_status = u''
        self.declared = {}
        self.clashes = []
        self.groups = collections.OrderedDict()
        self.warnings = []
        self._pkg = None
        self._member = None
        self._images = None

    def image_for_row(self, row):
        """Media member of the thumbnail anchored at ``row``; the drawing is parsed on first use."""
        if self._images is None:
            self._images = _sheet_images(self._pkg, self._member) if self._pkg else {}
        return self._images.get(row)

    def add_group(self, name):
        if name not in self.groups:
            self.groups[name] = []
        return self.groups[name]

    def counts(self):
        out = collections.OrderedDict((s, 0) for s in STATUSES)
        for c in self.clashes:
            out[c.status] = out.get(c.status, 0) + 1
        return out

    @property
    def pct_closed(self):
        total = len(self.clashes)
        if not total:
            return 0.0
        counts = self.counts()
        return float(counts.get('Approved', 0) + counts.get('Resolved', 0)) / total


class ClashReport(object):
    """A loaded .xlsm report."""

    def __init__(self, path):
        self.path = path
        self.document_code = u''
        self.revision = u''
        self.revision_date = u''
        self.tests = []
        self.summary = []
        self.warnings = []
        self._pkg = None

    @property
    def total(self):
        return sum(len(t.clashes) for t in self.tests)

    def all_clashes(self):
        for t in self.tests:
            for c in t.clashes:
                yield c

    def get_image_bytes(self, clash):
        """Raw bytes of the clash thumbnail, or None when the report has none."""
        if self._pkg is None or not clash.image_member:
            return None
        try:
            return self._pkg.read(clash.image_member)
        except KeyError:
            return None


def load_report(path):
    """Parse the report at ``path`` and return a ClashReport."""
    pkg = _Package(_read_file_bytes(path))
    report = ClashReport(path)
    report._pkg = pkg
    shared = _read_shared_strings(pkg)
    for name, member in _list_sheets(pkg):
        rows = _read_rows(pkg.xml(member), shared)
        if _find_header_row(rows) is not None:
            test = _parse_test_sheet(name, member, rows, pkg)
            report.tests.append(test)
            report.warnings.extend(u'%s: %s' % (name, w) for w in test.warnings)
        elif _key(name) == u'clash summary':
            report.summary = _parse_summary(rows)
        elif report.revision == u'':
            _parse_cover(report, rows)
    if not report.tests:
        raise ClashReaderError(
            u'No clash sheets were found. A clash sheet has a "Clash Name" column header.')
    if not report.document_code:
        report.document_code = re.sub(r'\.[^.]+$', u'', re.split(r'[\\/]', path)[-1])
    return report


# ---------------------------------------------------------------- package level

def _read_shared_strings(pkg):
    out = []
    if not pkg.has('xl/sharedStrings.xml'):
        return out
    for si in pkg.xml('xl/sharedStrings.xml').findall(_NS_MAIN + 'si'):
        t = si.find(_NS_MAIN + 't')
        if t is not None:
            out.append(t.text or u'')
        else:
            out.append(u''.join((r.find(_NS_MAIN + 't').text or u'')
                                for r in si.findall(_NS_MAIN + 'r')
                                if r.find(_NS_MAIN + 't') is not None))
    return out


def _resolve(base_dir, target):
    if target.startswith('/'):
        return target.lstrip('/')
    return posixpath.normpath(posixpath.join(base_dir, target))


def _list_sheets(pkg):
    wb = pkg.xml('xl/workbook.xml')
    rels = dict((r.get('Id'), r.get('Target'))
                for r in pkg.xml('xl/_rels/workbook.xml.rels'))
    sheets = wb.find(_NS_MAIN + 'sheets')
    out = []
    for s in sheets:
        target = rels.get(s.get(_NS_REL + 'id'))
        if target and s.get('state') not in ('hidden', 'veryHidden'):
            out.append((s.get('name'), _resolve('xl', target)))
    return out


_COL_CACHE = {}


def _read_rows(root, shared):
    """Sheet XML -> {row: {col: text}} (empty cells omitted)."""
    rows = {}
    seq_row = 0
    tag_v, tag_is, tag_t = _NS_MAIN + 'v', _NS_MAIN + 'is', _NS_MAIN + 't'
    n_shared = len(shared)
    for row in root.iter(_NS_MAIN + 'row'):
        seq_row += 1
        r_idx = int(row.get('r') or seq_row)
        cells = {}
        seq_col = 0
        for c in row:
            seq_col += 1
            if not len(c):                       # styled empty cell: no value to read
                continue
            ref = c.get('r')
            if ref:
                letters = ref.rstrip(u'0123456789')
                col = _COL_CACHE.get(letters)
                if col is None:
                    col = _COL_CACHE[letters] = _col_index(letters)
                seq_col = col
            else:
                col = seq_col
            kind = c.get('t')
            if kind == 'inlineStr':
                is_el = c.find(tag_is)
                text = (u''.join(t.text or u'' for t in is_el.iter(tag_t))
                        if is_el is not None else u'')
            else:
                v = c.find(tag_v)
                if v is None or v.text is None or kind == 'e':
                    continue
                if kind == 's':
                    idx = int(v.text)
                    text = shared[idx] if idx < n_shared else u''
                else:
                    text = v.text
            text = _norm(text)
            if text:
                cells[col] = text
        if cells:
            rows[r_idx] = cells
    return rows


def _find_header_row(rows):
    for r in sorted(rows)[:25]:
        if any(_key(v) == u'clash name' for v in rows[r].values()):
            return r
    return None


# ---------------------------------------------------------------- sheets

def _parse_cover(report, rows):
    best = None
    for r in sorted(rows):
        cells = rows[r]
        joined = u''.join(cells[c] for c in sorted(cells))
        if _RE_DOC_CODE.match(joined) and not report.document_code:
            report.document_code = joined
        rev = cells.get(2, u'')
        if re.match(r'^[A-Z]\d{2,}$', rev):
            serial = _to_int(cells.get(3, u''))
            if serial and (best is None or serial >= best[1]):
                best = (rev, serial)
    if best:
        report.revision = best[0]
        # Excel serial date (1900 system) -> ISO date
        import datetime
        report.revision_date = (datetime.date(1899, 12, 30)
                                + datetime.timedelta(days=best[1])).isoformat()


def _parse_summary(rows):
    out = []
    header = None
    for r in sorted(rows):
        cells = rows[r]
        if header is None:
            if _key(cells.get(1, u'')) == u'test name':
                header = dict((c, _key(v)) for c, v in cells.items())
            continue
        rec = collections.OrderedDict()
        for c in sorted(cells):
            rec[header.get(c, u'col%d' % c)] = cells[c]
        if rec:
            out.append(rec)
    return out


def _item_starts(rows, header_row):
    """Columns where the Item 1 / Item 2 blocks begin, from the row above the headers."""
    starts = {}
    above = rows.get(header_row - 1, {})
    for col, val in above.items():
        m = re.match(r'^item\s*(\d)$', _key(val))
        if m:
            starts[int(m.group(1))] = col
    if 1 in starts and 2 in starts:
        return starts
    path_cols = sorted(c for c, v in rows[header_row].items() if _key(v) == u'path')
    if len(path_cols) >= 2:
        return {1: path_cols[0], 2: path_cols[1]}
    raise ClashReaderError(u'The Item 1 / Item 2 columns could not be located.')


def _map_columns(rows, header_row):
    starts = _item_starts(rows, header_row)
    item2_start = starts[2]
    item1_start = starts[1]
    base, items = {}, {1: {}, 2: {}}
    for col, text in rows[header_row].items():
        key = _key(text)
        if col >= item2_start:
            side = 2
        elif col >= item1_start:
            side = 1
        else:
            side = 0
        if side == 0:
            base[col] = (_BASE_FIELDS.get(key), text)
        else:
            attr = _ITEM_FIELDS.get(key)
            if attr is None and u'uniqueid' in key:
                attr = 'unique_id'
            items[side][col] = (attr, text)
    return base, items


def _parse_test_sheet(name, member, rows, pkg):
    header_row = _find_header_row(rows)
    test = ClashTest(name)
    _read_test_header(test, rows, header_row)
    base, items = _map_columns(rows, header_row)
    test._pkg, test._member = pkg, member

    for r in sorted(k for k in rows if k > header_row):
        cells = rows[r]
        rec = {}
        for col, (attr, title) in base.items():
            if col in cells:
                rec[attr or title] = cells[col]
        group, cname = rec.get('group', u''), rec.get('name', u'')
        if not cname:
            continue
        if not group and not _RE_CLASH_NAME.match(cname):
            test.add_group(cname)          # group header row, not a clash
            continue
        clash = Clash(test)
        clash.row = r
        clash.group = group or u'(no group)'
        clash.name = cname
        clash.status = rec.get('status', u'')
        clash.assigned = rec.get('assigned', u'')
        clash.date_raw = rec.get('date_raw', u'')
        clash.point_raw = rec.get('point_raw', u'')
        for attr, val in rec.items():
            if attr not in ('image', 'group', 'name', 'status', 'assigned', 'date_raw', 'point_raw'):
                clash.extra[attr] = val
        for side, item in ((1, clash.item1), (2, clash.item2)):
            for col, (attr, title) in items[side].items():
                if col not in cells:
                    continue
                if attr:
                    setattr(item, attr, cells[col])
                else:
                    item.extra[title] = cells[col]
        test.add_group(clash.group).append(clash)
        test.clashes.append(clash)

    _check_counts(test)
    return test


def _read_test_header(test, rows, header_row):
    """Test name, tolerance, type and declared counters (rows above the table)."""
    for r in sorted(k for k in rows if k < header_row):
        cells = rows[r]
        titles = dict((c, _key(v)) for c, v in cells.items())
        if u'tolerance' not in titles.values():
            continue
        if cells.get(1):
            test.name = cells[1]
        values = rows.get(r + 1, {})
        for col, title in titles.items():
            val = values.get(col, u'')
            if title == u'tolerance':
                test.tolerance = val
            elif title == u'type':
                test.test_type = val
            elif title == u'status':
                test.test_status = val
            elif title == u'clashes':
                test.declared['Total'] = _to_int(val)
            elif val and title.capitalize() in STATUSES:
                test.declared[title.capitalize()] = _to_int(val)
        return


def _check_counts(test):
    declared_total = test.declared.get('Total')
    if declared_total is not None and declared_total != len(test.clashes):
        test.warnings.append(u'the sheet declares %d clashes but %d were read'
                             % (declared_total, len(test.clashes)))
    counts = test.counts()
    for status in STATUSES:
        want = test.declared.get(status)
        if want is not None and want != counts.get(status, 0):
            test.warnings.append(u'status %s: declared %d, read %d'
                                 % (status, want, counts.get(status, 0)))


def _sheet_images(pkg, sheet_member):
    """{row: media member} from the sheet drawing; empty when there are no images."""
    folder, fname = posixpath.split(sheet_member)
    rels_name = posixpath.join(folder, '_rels', fname + '.rels')
    if not pkg.has(rels_name):
        return {}
    drawing = None
    for rel in pkg.xml(rels_name):
        if rel.get('Type', '').endswith('/drawing'):
            drawing = _resolve(folder, rel.get('Target'))
    if not drawing or not pkg.has(drawing):
        return {}
    dfolder, dname = posixpath.split(drawing)
    drels = posixpath.join(dfolder, '_rels', dname + '.rels')
    targets = {}
    if pkg.has(drels):
        for rel in pkg.xml(drels):
            targets[rel.get('Id')] = _resolve(dfolder, rel.get('Target'))
    out = {}
    for anchor in pkg.xml(drawing):
        frm = anchor.find(_NS_XDR + 'from')
        blip = anchor.find('.//' + _NS_A + 'blip')
        if frm is None or blip is None:
            continue
        member = targets.get(blip.get(_NS_REL + 'embed'))
        if member and pkg.has(member):
            out[int(frm.find(_NS_XDR + 'row').text) + 1] = member
    return out
