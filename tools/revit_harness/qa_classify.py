# -*- coding: utf-8 -*-
"""
CPython: the QA findings of a building run (qa_findings.json, building_test) classified for the user (2026-10-26,
point 9) - by check, by element type and by storey, split into: beam/column joint clashes (point 6), column top
L-bars (point 7), proven false positives, and the rest with their cause. Writes qa_classes.md and .json beside it.
Usage: python qa_classify.py <run folder> [storey height mm, default 3000]
"""
import collections
import io
import json
import os
import re
import sys

POS = re.compile(r'at \((-?\d+), (-?\d+), (-?\d+)\)')


def element_type(host):
    h = host or u''
    if u'/' in h:
        kinds = sorted(set(element_type(part) for part in h.split(u'/')))
        return u' / '.join(kinds)
    if h.strip().startswith(u'450x450') or u'Column' in h:
        return u'column'
    if u'300x600' in h or u'Beam' in h:
        return u'beam'
    if u'Floor' in h or u'Slab' in h:
        return u'slab'
    if u'Wall' in h:
        return u'wall'
    if u'Stair' in h:
        return u'stair'
    if re.match(r'\s*\d+x\d+x\d+', h):
        return u'foundation'
    return u'other'


def storey(z_mm, height):
    if z_mm is None:
        return u'?'
    if z_mm < -1.0:
        return u'foundation'
    return u'storey {}'.format(int(z_mm // height) + 1)


def classify(row, top_storey, height):
    check, kind = row['check'], element_type(row['host'])
    m = POS.search(row['issue'] or u'')
    z = float(m.group(3)) if m else row.get('z_mm')
    row['_z'] = z
    if check in (u'Joint clash', u'Joint congestion'):
        if u'beam' in kind and u'column' in kind:
            return u'point 6: beam/column joint'
        if kind == u'column':
            return u'column/column at a storey joint: lap bars'
        return CAUSES.get((u'joint', kind), u'joint: ' + kind)
    if check == u'Clash' and kind == u'column' and z is not None:
        # inside a top-storey column, in its top 600 mm: where the L-bars' feet turn (point 7)
        if storey(z, height) == top_storey and (z % height) > height - 600.0:
            return u'point 7: column top L-bars'
    return CAUSES.get((check, kind), u'other: {} ({})'.format(check, kind))


# what each remaining class is, read from its findings (2026-10-26, 2 and 4 storeys)
CAUSES = {
    (u'joint', u'column / slab'): u'slab bars through a column cage, not set round its bars',
    (u'joint', u'beam / slab'): u'slab bars on a beam\'s bars at the same level',
    (u'joint', u'beam'): u'beam bars crossing at an interior joint (the secondary\'s 20 mm drop not enough)',
    (u'Clash', u'slab'): u'slab bars on each other (U-bars and main bars at edges and supports)',
    (u'Congestion', u'slab'): u'slab bars closer than s_min (U-bars and main bars at edges and supports)',
    (u'Clash', u'column'): u'a column\'s lap crank on its top link',
    (u'Congestion', u'column'): u'a column\'s bars closer than s_min at a lap',
    (u'Cover', u'column'): u'a column link 1 mm short of its cover at the joint',
    (u'Vibrator gap', u'beam'): u'design: 300 beams with 3H20 leave no 75 mm poker gap (SMDSC MD B1)',
    (u'Pitch', u'slab'): u'design: slab bars at 600 over the 400 allowed (SMDSC 6.2)',
    (u'Distribution pitch', u'slab'): u'design: distribution bars over 450 (SMDSC MD S1)',
    (u'Steel ratio', u'slab'): u'design: steel under the EC2 minimum',
    (u'Steel ratio', u'wall'): u'design: steel under the EC2 minimum',
    (u'Rule-added bars', u'foundation'): u'info: bars a detailing rule added (confirm with design)',
    (u'Rule-added bars', u'wall'): u'info: bars a detailing rule added (confirm with design)',
    (u'Rule-added bars', u'slab'): u'info: bars a detailing rule added (confirm with design)',
}


def main(folder, height=3000.0):
    height = float(height)
    rows = json.load(io.open(os.path.join(folder, 'qa_findings.json'), encoding='utf-8'))
    zs = [float(POS.search(r['issue']).group(3)) for r in rows if POS.search(r['issue'] or u'')]
    top_storey = storey(max(zs) - 1.0, height) if zs else u'?'
    classes = collections.Counter()
    by = collections.defaultdict(collections.Counter)
    examples = {}
    for r in rows:
        c = classify(r, top_storey, height)
        classes[c] += 1
        by[c][(r['severity'], r['check'], element_type(r['host']), storey(r['_z'], height))] += 1
        examples.setdefault(c, (r['host'], r['mark'], r['issue'][:160], r.get('id')))
    lines = [u'# QA: {} hallazgos clasificados'.format(len(rows)), u'',
             u'Carpeta `{}`; plantas de {:.0f} mm; planta superior: {}.'.format(folder, height, top_storey), u'',
             u'| Clase | Hallazgos | Ejemplo |', u'|---|---|---|']
    for c, n in classes.most_common():
        h, mk, issue, eid = examples[c]
        lines.append(u'| {} | {} | {} {} - {} (id {}) |'.format(c, n, h, mk, issue, eid))
    lines += [u'', u'## Por gravedad, comprobación, elemento y planta', u'',
              u'| Clase | Gravedad | Comprobación | Elemento | Planta | Hallazgos |', u'|---|---|---|---|---|---|']
    for c, counter in sorted(by.items(), key=lambda kv: -classes[kv[0]]):
        for (sev, check, kind, st), n in sorted(counter.items(), key=lambda kv: -kv[1]):
            lines.append(u'| {} | {} | {} | {} | {} | {} |'.format(c, sev, check, kind, st, n))
    io.open(os.path.join(folder, 'qa_classes.md'), 'w', encoding='utf-8').write(u'\n'.join(lines) + u'\n')
    json.dump({'classes': dict(classes), 'detail': dict((c, dict((u' | '.join(k), n) for k, n in v.items()))
                                                       for c, v in by.items())},
              io.open(os.path.join(folder, 'qa_classes.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    for c, n in classes.most_common():
        print(u'{:5d}  {}'.format(n, c))


if __name__ == '__main__':
    main(*sys.argv[1:])
