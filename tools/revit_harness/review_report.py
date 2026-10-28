# -*- coding: utf-8 -*-
"""
CPython: the technical review list of points 3.1 and 3.2 (review_probe.py's JSON) written for the user in Spanish,
one row per column top and per beam bar, each failed check said once with its value and limit.
Usage: python review_report.py <OUT.review.json> <out.md>
"""
import io
import json
import re
import sys

CHECKS = [
    (r'^clear to the layer \(', u'quedaría a menos de s_min de su barra vecina'),
    (r'^shift within half the pitch', u'desplazamiento necesario {v} mm > límite s/2 = {l} mm'),
    (r'^compression at the joint', u'sin esfuerzos en el modelo: R2 no permitido'),
    (r'^offset <= min', u'acodado necesario {v} mm > min(75, 2φ) = {l} mm'),
    (r'^crank within the clear span', u'el acodado no cabe en la luz libre'),
    (r'^clear along its length of secondary', u'desplazada chocaría con barras paralelas de losa u otra viga'),
    (r'^clear to the column bars at', u'desplazada seguiría tocando las barras del pilar'),
    (r'^clear to secondary beam, slab', u'acodada chocaría con barras de losa u otra viga'),
    (r'^cover: inside the link cage', u'saldría del cerco'),
    (r'^poker gap', u'perdería el hueco de vibrador de 75 mm'),
    (r'^no other beam', u'cruza la otra viga a la misma cota en el nudo'),
]


def spanish(failed):
    out = []
    for f in failed:
        m = re.match(r'^(.*): (.*) \(limit (.*)\)$', f)
        name, value, limit = (m.group(1), m.group(2), m.group(3)) if m else (f, u'', u'')
        for pattern, text in CHECKS:
            if re.match(pattern, name):
                line = text.format(v=value, l=limit)
                if line not in out:
                    out.append(line)
                break
        else:
            if f not in out:
                out.append(f)
    return u'; '.join(out)


def main(src, dst):
    rows = json.load(io.open(src, encoding='utf-8'))
    cols = [r for r in rows if r['element'] == u'column top']
    joints = [r for r in rows if r['element'] != u'column top']
    lines = [u'# Revisión técnica: coronación de pilares (3.1) y nudos viga–pilar (3.2)', u'',
             u'Edificio de prueba de 4 plantas (Revit 2026, copia sin guardar). Pilares 450×450, vigas 300×600, H20. '
             u'Cada elemento lleva su aviso en el resultado del plugin y sus choques siguen en la QA. Posiciones en mm '
             u'(coordenadas del modelo). Las marcas de pilar y viga las asignan los planos, que en esta pasada no se '
             u'generaron: se identifica cada elemento por su id.', u'',
             u'## 3.1 Coronación de pilares de borde ({} pilares)'.format(len(cols)), u'',
             u'| # | Id pilar | Posición | Patillas hacia dentro | Motivo | Propuesta |', u'|---|---|---|---|---|---|']
    for n, r in enumerate(cols, 1):
        lines.append(u'| {} | {} | {} | {} | Las patillas de la cara de borde giran hacia dentro y atraviesan las barras '
                     u'de la cara opuesta. Las horquillas del detalle B no encuentran posición libre de esas barras y de '
                     u'las de las vigas (ver docs/PILARES_BORDE_L_CORONACION.md §5) | Decisión de proyecto: separar las '
                     u'barras de viga de las líneas de barras del pilar, horquillas tumbadas en la losa, o patilla '
                     u'acortada con lb,rqd de cálculo (opción B) |'.format(n, r['id'], r['at_mm'][:2], r['feet_in']))
    lines += [u'', u'## 3.2 Nudos viga–pilar en R3 ({} barras)'.format(len(joints)), u'',
              u'| # | Id viga | Posición (centro de viga) | Capa | Barra (id) | y (mm) | Pilares | Motivo | Propuesta |',
              u'|---|---|---|---|---|---|---|---|---|']
    for n, r in enumerate(joints, 1):
        proposal = (u'Pasar las barras de esa capa a segunda capa, o 2 barras de mayor diámetro en lugar de 3, o '
                    u'mover las barras del pilar fuera del eje de la viga (cambio de diseño)')
        if any(u'secondary beam' in f for f in r['failed']):
            proposal += u'; revisar además la posición de la losa o la viga paralela'
        lines.append(u'| {} | {} | {} | {} | {} {} | {:.0f} | {} | {} | {} |'.format(
            n, r['id'], r['at_mm'][:2], {u'top': u'superior', u'bottom': u'inferior'}.get(r['layer'], r['layer']),
            r['bar_mark'], r['bar_id'], r['y_mm'], u', '.join(r['columns']), spanish(r['failed']), proposal))
    io.open(dst, 'w', encoding='utf-8').write(u'\n'.join(lines) + u'\n')
    print('{} column tops, {} joint bars -> {}'.format(len(cols), len(joints), dst))


if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2])
