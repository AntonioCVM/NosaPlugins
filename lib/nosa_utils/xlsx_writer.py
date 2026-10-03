# -*- coding: utf-8 -*-
"""
Minimal .xlsx writer (one sheet, text and numbers, bold wrapped header, thin borders, column
widths, row heights and PNG pictures anchored to cells). Pure Python + zipfile: pyRevit's
IronPython has no openpyxl (T7.5, 2026-10-03).
"""
from __future__ import absolute_import, division, print_function, unicode_literals
import zipfile

try:
    unicode
except NameError:
    unicode = str  # CPython 3 compat

EMU_PER_MM = 36000

_CONTENT_TYPES = u'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
<Default Extension="xml" ContentType="application/xml"/>
<Default Extension="png" ContentType="image/png"/>
<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>
{drawing}</Types>'''

_ROOT_RELS = u'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>
</Relationships>'''

_WORKBOOK = u'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
<sheets><sheet name="{name}" sheetId="1" r:id="rId1"/></sheets>
</workbook>'''

_WORKBOOK_RELS = u'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>
<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>
</Relationships>'''

# style 0: plain; 1: header (bold, wrapped, centred, bordered); 2: body (centred, bordered)
_STYLES = u'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
<fonts count="2"><font><sz val="10"/><name val="Arial"/></font><font><b/><sz val="10"/><name val="Arial"/></font></fonts>
<fills count="2"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill></fills>
<borders count="2"><border><left/><right/><top/><bottom/><diagonal/></border>
<border><left style="thin"/><right style="thin"/><top style="thin"/><bottom style="thin"/><diagonal/></border></borders>
<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>
<cellXfs count="3">
<xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>
<xf numFmtId="0" fontId="1" fillId="0" borderId="1" xfId="0" applyFont="1" applyBorder="1" applyAlignment="1"><alignment horizontal="center" vertical="center" wrapText="1"/></xf>
<xf numFmtId="0" fontId="0" fillId="0" borderId="1" xfId="0" applyBorder="1" applyAlignment="1"><alignment horizontal="center" vertical="center"/></xf>
</cellXfs>
<cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles>
</styleSheet>'''


def _esc(text):
    return (unicode(text).replace(u'&', u'&amp;').replace(u'<', u'&lt;').replace(u'>', u'&gt;')
            .replace(u'"', u'&quot;'))


def column_letter(index):
    """0 -> A, 25 -> Z, 26 -> AA."""
    letters = u''
    index += 1
    while index:
        index, rem = divmod(index - 1, 26)
        letters = u'ABCDEFGHIJKLMNOPQRSTUVWXYZ'[rem] + letters
    return letters


def _cell(ref, value, style):
    if isinstance(value, bool) or value is None or value == u'':
        return u'<c r="{}" s="{}"/>'.format(ref, style)
    if isinstance(value, (int, float)):
        return u'<c r="{}" s="{}"><v>{}</v></c>'.format(ref, style, repr(value) if isinstance(value, float) else value)
    return u'<c r="{}" s="{}" t="inlineStr"><is><t xml:space="preserve">{}</t></is></c>'.format(
        ref, style, _esc(value))


def _sheet_xml(rows, widths, heights, header_rows, has_drawing):
    parts = [u'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
             u'<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
             u'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">']
    if widths:
        parts.append(u'<cols>')
        for i, width in enumerate(widths):
            parts.append(u'<col min="{0}" max="{0}" width="{1}" customWidth="1"/>'.format(i + 1, width))
        parts.append(u'</cols>')
    parts.append(u'<sheetData>')
    for r, row in enumerate(rows):
        attrs = u' ht="{}" customHeight="1"'.format(heights[r]) if r in heights else u''
        parts.append(u'<row r="{}"{}>'.format(r + 1, attrs))
        style = 1 if r in header_rows else 2
        for c, value in enumerate(row):
            parts.append(_cell(u'{}{}'.format(column_letter(c), r + 1), value, style))
        parts.append(u'</row>')
    parts.append(u'</sheetData>')
    if has_drawing:
        parts.append(u'<drawing r:id="rId1"/>')
    parts.append(u'</worksheet>')
    return u''.join(parts)


def _drawing_xml(images):
    parts = [u'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
             u'<xdr:wsDr xmlns:xdr="http://schemas.openxmlformats.org/drawingml/2006/spreadsheetDrawing" '
             u'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
             u'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">']
    for n, image in enumerate(images, start=1):
        parts.append(
            u'<xdr:oneCellAnchor><xdr:from><xdr:col>{col}</xdr:col><xdr:colOff>{dx}</xdr:colOff>'
            u'<xdr:row>{row}</xdr:row><xdr:rowOff>{dy}</xdr:rowOff></xdr:from>'
            u'<xdr:ext cx="{cx}" cy="{cy}"/>'
            u'<xdr:pic><xdr:nvPicPr><xdr:cNvPr id="{n}" name="Picture {n}"/><xdr:cNvPicPr/></xdr:nvPicPr>'
            u'<xdr:blipFill><a:blip r:embed="rId{n}"/><a:stretch><a:fillRect/></a:stretch></xdr:blipFill>'
            u'<xdr:spPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="{cx}" cy="{cy}"/></a:xfrm>'
            u'<a:prstGeom prst="rect"><a:avLst/></a:prstGeom></xdr:spPr></xdr:pic><xdr:clientData/>'
            u'</xdr:oneCellAnchor>'.format(
                n=n, col=image['col'], row=image['row'], dx=int(image.get('offset_mm', (1, 1))[0] * EMU_PER_MM),
                dy=int(image.get('offset_mm', (1, 1))[1] * EMU_PER_MM),
                cx=int(image['size_mm'][0] * EMU_PER_MM), cy=int(image['size_mm'][1] * EMU_PER_MM)))
    parts.append(u'</xdr:wsDr>')
    return u''.join(parts)


def write_xlsx(path, sheet_name, rows, widths=None, heights=None, header_rows=(0,), images=None):
    """
    rows: list of lists (text / numbers); widths: column widths (characters); heights:
    {row index: points}; images: [{'row', 'col' (0-based), 'png' (bytes), 'size_mm': (w, h),
    'offset_mm': (x, y)}].
    """
    images = images or []
    heights = heights or {}
    z = zipfile.ZipFile(path, 'w', zipfile.ZIP_DEFLATED)
    try:
        drawing_type = (u'<Override PartName="/xl/drawings/drawing1.xml" ContentType='
                        u'"application/vnd.openxmlformats-officedocument.drawing+xml"/>\n') if images else u''
        z.writestr('[Content_Types].xml', _CONTENT_TYPES.format(drawing=drawing_type).encode('utf-8'))
        z.writestr('_rels/.rels', _ROOT_RELS.encode('utf-8'))
        z.writestr('xl/workbook.xml', _WORKBOOK.format(name=_esc(sheet_name[:31])).encode('utf-8'))
        z.writestr('xl/_rels/workbook.xml.rels', _WORKBOOK_RELS.encode('utf-8'))
        z.writestr('xl/styles.xml', _STYLES.encode('utf-8'))
        z.writestr('xl/worksheets/sheet1.xml',
                   _sheet_xml(rows, widths, heights, set(header_rows), bool(images)).encode('utf-8'))
        if images:
            z.writestr('xl/worksheets/_rels/sheet1.xml.rels', (
                u'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                u'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                u'<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/'
                u'relationships/drawing" Target="../drawings/drawing1.xml"/></Relationships>').encode('utf-8'))
            z.writestr('xl/drawings/drawing1.xml', _drawing_xml(images).encode('utf-8'))
            rels = [u'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                    u'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">']
            media = {}                      # one file per distinct picture, however many rows show it
            for n, image in enumerate(images, start=1):
                key = image['png']
                if key not in media:
                    media[key] = len(media) + 1
                    z.writestr('xl/media/image{}.png'.format(media[key]), key)
                rels.append(u'<Relationship Id="rId{0}" Type="http://schemas.openxmlformats.org/'
                            u'officeDocument/2006/relationships/image" Target="../media/image{1}.png"/>'.format(
                                n, media[key]))
            rels.append(u'</Relationships>')
            z.writestr('xl/drawings/_rels/drawing1.xml.rels', u''.join(rels).encode('utf-8'))
    finally:
        z.close()
    return path
