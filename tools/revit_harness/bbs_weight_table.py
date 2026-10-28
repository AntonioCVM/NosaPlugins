# -*- coding: utf-8 -*-
"""
CPython (3.3 / I1, user 2026-10-28): every BBS row's weight against BS 4449's tabulated nominal mass - total bars x
printed length x mass, to 0.1 kg - and, for each row that differs, whether the template's density formula
(pi d^2 / 4 x 7850 kg/m3) explains it (a difference of criterion) or only the rounding of lengths or weights does.
Usage: python bbs_weight_table.py <run folder> [...]  (reads bbs_crosscheck.json, written by ra_bbs_crosscheck.py)
"""
import json
import math
import os
import sys

MASS_KG_M = {6: 0.222, 8: 0.395, 10: 0.617, 12: 0.888, 16: 1.579, 20: 2.466, 25: 3.854, 32: 6.313, 40: 9.864}  # BS 4449


def density_mass(dia):
    return math.pi * (dia / 1000.0) ** 2 / 4.0 * 7850.0


def main(folders):
    print('| Modelo | BBS | Miembro | Marca | Barras | Diámetro | Longitud (mm) | Masa BS 4449 (kg/m) | Esperado (kg) |'
          ' Mostrado (kg) | Diferencia | Causa |')
    print('|---|---|---|---|---:|---|---:|---:|---:|---:|---:|---|')
    totals = {}
    for folder in folders:
        rows = json.load(open(os.path.join(folder, 'bbs_crosscheck.json'), encoding='utf-8'))['rows']
        n = bad = 0
        for r in rows:
            if not (r['weight'] and r['total'].isdigit() and r['length'].isdigit()):
                continue
            dia = int(r['type'][1:])
            if dia not in MASS_KG_M:
                continue
            n += 1
            qty, length, shown = int(r['total']), int(r['length']), float(r['weight'])
            expected = round(qty * length / 1000.0 * MASS_KG_M[dia], 1)
            if abs(shown - expected) < 0.05:
                continue
            bad += 1
            by_density = round(qty * length / 1000.0 * density_mass(dia), 1)
            cause = (u'criterio: fórmula de densidad ({:.5f} kg/m)'.format(density_mass(dia))
                     if abs(shown - by_density) < 0.05 else u'redondeo u otra causa: revisar')
            print(u'| {} | {} | {} | {} | {} | H{} | {} | {} | {:.1f} | {:.1f} | {:+.1f} | {} |'.format(
                os.path.basename(folder.rstrip('\\/')), r['schedule'], r['member'], r['mark'], qty, dia, length,
                MASS_KG_M[dia], expected, shown, shown - expected, cause))
        totals[os.path.basename(folder.rstrip('\\/'))] = (n, bad)
    print()
    for k, (n, bad) in totals.items():
        print(u'- {}: {} filas comprobadas, {} con diferencia'.format(k, n, bad))


if __name__ == '__main__':
    main(sys.argv[1:])
