# -*- coding: utf-8 -*-
from __future__ import print_function
import zipfile
import xml.etree.ElementTree as ET
import os
import re

p = r'c:\Users\AntonioCViñas\NOSA\NOSA - Shared Data\1. Projects\23112 - WWTP\2. Incoming\Contractor - ACCIONA\261015 - Clash repports XML\UWWTP-AA-00-BM-RP-00002.xlsm'
print('exists', os.path.exists(p), 'size', os.path.getsize(p) if os.path.exists(p) else 0)

NS = {
    'm': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main',
    'r': 'http://schemas.openxmlformats.org/officeDocument/2006/relationships',
    'rel': 'http://schemas.openxmlformats.org/package/2006/relationships',
}

def col_row(ref):
    m = re.match(r'([A-Z]+)(\d+)', ref)
    return m.group(1), int(m.group(2))

with zipfile.ZipFile(p) as z:
    names = z.namelist()
    print('entries', len(names))
    interesting = [n for n in names if (
        n == 'xl/workbook.xml' or n.startswith('xl/worksheets/')
        or n.startswith('xl/media/') or 'drawing' in n.lower()
        or n.startswith('xl/_rels/') or n == '[Content_Types].xml'
        or n == 'xl/sharedStrings.xml'
    )]
    for n in interesting:
        print(n, z.getinfo(n).file_size)

    wb = ET.fromstring(z.read('xl/workbook.xml'))
    sheets = []
    for sh in wb.findall('m:sheets/m:sheet', NS):
        sheets.append((sh.get('name'), sh.get('{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id')))
    print('SHEETS:')
    for s in sheets:
        print(' ', s)

    rels = ET.fromstring(z.read('xl/_rels/workbook.xml.rels'))
    rid_to_target = {}
    for rel in rels:
        rid_to_target[rel.get('Id')] = rel.get('Target')
    for name, rid in sheets:
        print(name, '->', rid_to_target.get(rid))

    # Probe first few sheets: rows 1-10 of first 3 worksheets
    ss = None
    if 'xl/sharedStrings.xml' in names:
        ss_root = ET.fromstring(z.read('xl/sharedStrings.xml'))
        ss = []
        for si in ss_root.findall('m:si', NS):
            texts = [t.text or '' for t in si.findall('.//m:t', NS)]
            ss.append(''.join(texts))
        print('shared strings', len(ss))

    def cell_val(c):
        t = c.get('t')
        v = c.find('m:v', NS)
        is_el = c.find('m:is', NS)
        if t == 'inlineStr' and is_el is not None:
            return ''.join((x.text or '') for x in is_el.findall('.//m:t', NS))
        if v is None or v.text is None:
            return None
        if t == 's' and ss is not None:
            return ss[int(v.text)]
        return v.text

    for name, rid in sheets:
        target = rid_to_target[rid]
        if not target.startswith('/'):
            path = 'xl/' + target.lstrip('/')
        else:
            path = target.lstrip('/')
        if path.startswith('xl/xl/'):
            path = path[3:]
        print('\n====', name, path, '====')
        root = ET.fromstring(z.read(path))
        rows = {}
        for row in root.findall('m:sheetData/m:row', NS)[:12]:
            ridx = int(row.get('r'))
            cells = {}
            for c in row.findall('m:c', NS):
                ref = c.get('r')
                col, _ = col_row(ref)
                cells[col] = cell_val(c)
            rows[ridx] = cells
            if ridx <= 9:
                # print compact
                items = ['{}={!r}'.format(k, cells[k][:80] if isinstance(cells[k], str) and len(cells[k])>80 else cells[k]) for k in sorted(cells.keys(), key=lambda x: (len(x), x))]
                print('R', ridx, '|'.join(items)[:500])
        # count data rows roughly
        all_rows = root.findall('m:sheetData/m:row', NS)
        print('row count', len(all_rows))
