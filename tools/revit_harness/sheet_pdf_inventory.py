# -*- coding: utf-8 -*-
"""
CPython: every sheet the doc audit found (audit.json) against the PDFs of the same run (pdf/), one line each - number,
name, kind (RC drawing, bar schedule, template sheet), its file, and what is missing, extra or duplicated; the PDFs
must be newer than the model state the audit read and older than the audit's end. Writes inventory.md and
inventory.json beside audit.json. Usage: python sheet_pdf_inventory.py <folder> [log of the run]
"""
import glob
import io
import json
import os
import re
import sys


def kind_of(number):
    n = int(re.match(r'\d+', number).group(0)) if re.match(r'\d+', number) else 0
    if 4501 <= n <= 4999:
        return u'RC drawing (made by the run)'
    if n == 5500:
        return u'BBS master sheet (template)'
    if 5501 <= n <= 5999:
        return u'bar schedule (made by the run)'
    return u'template sheet (not made by the run)'


def main(folder, log=None):
    audit = json.load(io.open(os.path.join(folder, 'audit.json'), encoding='utf-8'))
    pdfs = sorted(glob.glob(os.path.join(folder, 'pdf', '*.pdf')))
    by_number = {}
    for p in pdfs:
        number = os.path.basename(p).split(u' - ')[0]
        by_number.setdefault(number, []).append(p)
    audit_time = os.path.getmtime(os.path.join(folder, 'audit.json'))
    rows, problems = [], []
    seen = set()
    for s in sorted(audit['sheets'], key=lambda x: x['number']):
        files = by_number.get(s['number'], [])
        seen.add(s['number'])
        row = {'number': s['number'], 'name': s['name'], 'kind': kind_of(s['number']), 'viewports': len(s['viewports']),
               'schedules': len(s.get('schedules') or []), 'files': [os.path.basename(f) for f in files]}
        if not files:
            problems.append(u'{} {}: no PDF'.format(s['number'], s['name']))
        elif len(files) > 1:
            problems.append(u'{}: {} PDFs (duplicate)'.format(s['number'], len(files)))
        else:
            expected = u'{} - {}.pdf'.format(s['number'], re.sub(u'[\\\\/:*?"<>|]', u'_', s['name']))
            if os.path.basename(files[0]) != expected:
                problems.append(u'{}: file {} does not carry the sheet name ({})'.format(
                    s['number'], os.path.basename(files[0]), expected))
            if os.path.getmtime(files[0]) < audit_time - 3600 * 2:
                problems.append(u'{}: PDF older than the run'.format(s['number']))
        rows.append(row)
    extra = [n for n in by_number if n not in seen]
    for n in extra:
        rows.append({'number': n, 'name': u'(not in the audit)', 'kind': kind_of(n), 'viewports': None,
                     'schedules': None, 'files': [os.path.basename(f) for f in by_number[n]]})
    counts = {}
    for r in rows:
        counts[r['kind']] = counts.get(r['kind'], 0) + 1
    lines = [u'# Inventario de planos y PDF', u'',
             u'Carpeta: `{}`. Hojas en la auditoría: {}. PDF: {}. Sin PDF: {}. PDF sin hoja: {}.'.format(
                 folder, len(audit['sheets']), len(pdfs), sum(1 for r in rows if not r['files']), len(extra)), u'',
             u'| Nº | Nombre | Tipo | Vistas | Planillas | Archivo |', u'|---|---|---|---|---|---|']
    for r in sorted(rows, key=lambda x: x['number']):
        lines.append(u'| {} | {} | {} | {} | {} | {} |'.format(r['number'], r['name'], r['kind'], r['viewports'],
                                                                r['schedules'], u'; '.join(r['files']) or u'**falta**'))
    lines += [u'', u'Por tipo: ' + u'; '.join(u'{} {}'.format(v, k) for k, v in sorted(counts.items())), u'',
              u'Problemas: ' + (u'ninguno' if not problems else u''), u'']
    lines += [u'- ' + p for p in problems]
    io.open(os.path.join(folder, 'inventory.md'), 'w', encoding='utf-8').write(u'\n'.join(lines) + u'\n')
    json.dump({'rows': rows, 'problems': problems, 'counts': counts},
              io.open(os.path.join(folder, 'inventory.json'), 'w', encoding='utf-8'), indent=1, ensure_ascii=False)
    print(u'sheets {} | pdfs {} | problems {} | {}'.format(len(audit['sheets']), len(pdfs), len(problems), counts))
    for p in problems:
        print(u'  ' + p)
    return 1 if problems else 0


if __name__ == '__main__':
    sys.exit(main(*sys.argv[1:]))
