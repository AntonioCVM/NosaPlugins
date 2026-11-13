# -*- coding: utf-8 -*-
from __future__ import print_function
import zipfile, re, xml.etree.ElementTree as ET

p = r'c:\Users\AntonioCViñas\NOSA\NOSA - Shared Data\1. Projects\23112 - WWTP\2. Incoming\Contractor - ACCIONA\261015 - Clash repports XML\UWWTP-AA-00-BM-RP-00002.xlsm'
NS = {'m': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main',
      'xdr': 'http://schemas.openxmlformats.org/drawingml/2006/spreadsheetDrawing',
      'a': 'http://schemas.openxmlformats.org/drawingml/2006/main',
      'r': 'http://schemas.openxmlformats.org/officeDocument/2006/relationships',
      'rel': 'http://schemas.openxmlformats.org/package/2006/relationships'}

def col_row(ref):
    m = re.match(r'([A-Z]+)(\d+)', ref)
    return m.group(1), int(m.group(2))

with zipfile.ZipFile(p) as z:
    ss_root = ET.fromstring(z.read('xl/sharedStrings.xml'))
    ss = []
    for si in ss_root.findall('m:si', NS):
        ss.append(''.join((t.text or '') for t in si.findall('.//m:t', NS)))

    def cell_val(c):
        t = c.get('t')
        v = c.find('m:v', NS)
        is_el = c.find('m:is', NS)
        if t == 'inlineStr' and is_el is not None:
            return ''.join((x.text or '') for x in is_el.findall('.//m:t', NS))
        if v is None or v.text is None:
            return None
        if t == 's':
            return ss[int(v.text)]
        return v.text

    # Cover sheet all non-empty
    root = ET.fromstring(z.read('xl/worksheets/sheet1.xml'))
    print('=== COVER non-empty ===')
    for row in root.findall('m:sheetData/m:row', NS):
        for c in row.findall('m:c', NS):
            val = cell_val(c)
            if val not in (None, ''):
                print(c.get('r'), repr(val)[:120])

    # Count clash vs group on sheet3
    root = ET.fromstring(z.read('xl/worksheets/sheet3.xml'))
    clash_re = re.compile(r'^Clash\s*\d+', re.I)
    groups = clashes = empty = other = 0
    names = []
    for row in root.findall('m:sheetData/m:row', NS):
        ridx = int(row.get('r'))
        if ridx < 9:
            continue
        cells = {}
        for c in row.findall('m:c', NS):
            col, _ = col_row(c.get('r'))
            cells[col] = cell_val(c)
        cval = (cells.get('C') or '').strip() if cells.get('C') else ''
        eval_ = (cells.get('E') or '').strip() if cells.get('E') else ''
        if not cval and not eval_:
            empty += 1
            continue
        if clash_re.match(eval_):
            clashes += 1
            if len(names) < 5:
                names.append((ridx, cval, eval_))
        elif not cval and eval_:
            groups += 1
            print('GROUP', ridx, eval_, 'status', cells.get('G'))
        else:
            other += 1
            print('OTHER', ridx, cval, eval_)
    print('sheet3 groups', groups, 'clashes', clashes, 'empty', empty, 'other', other, 'samples', names)

    # drawing2 (sheet3 likely drawing2 - sheet1=drawing1?)
    print('\n=== drawing2 first 8 anchors ===')
    d = ET.fromstring(z.read('xl/drawings/drawing2.xml'))
    # namespaces might need wildcard
    anchors = d.findall('.//{http://schemas.openxmlformats.org/drawingml/2006/spreadsheetDrawing}twoCellAnchor')
    print('twoCellAnchor', len(anchors))
    for a in anchors[:8]:
        frm = a.find('{http://schemas.openxmlformats.org/drawingml/2006/spreadsheetDrawing}from')
        row = frm.find('{http://schemas.openxmlformats.org/drawingml/2006/spreadsheetDrawing}row')
        col = frm.find('{http://schemas.openxmlformats.org/drawingml/2006/spreadsheetDrawing}col')
        blip = a.find('.//{http://schemas.openxmlformats.org/drawingml/2006/main}blip')
        embed = blip.get('{http://schemas.openxmlformats.org/officeDocument/2006/relationships}embed') if blip is not None else None
        print('row', row.text if row is not None else None, 'col', col.text if col is not None else None, 'embed', embed)

    rels = ET.fromstring(z.read('xl/drawings/_rels/drawing2.xml.rels'))
    for rel in list(rels)[:5]:
        print('rel', rel.get('Id'), rel.get('Target'))
