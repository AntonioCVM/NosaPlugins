# Reglas frente a la SMDSC 4.ª ed. (T9.22, 2026-10-17)

Referencia: IStructE *Standard Method of Detailing Structural Concrete*, 4.ª ed. (2021).

## Qué se ha hecho

1. **Registro** `lib/nosa_utils/smdsc_rules.py`.
   - Recoge cada constante de detallado de `nosa_utils` con su valor, su cláusula de la 4.ª ed. y lo que cambió respecto a la 3.ª.
   - `tests/test_smdsc_rules.py` comprueba que cada valor registrado es el que usa el código. Cambiar una regla sin actualizar el registro rompe el test.
2. **Citas en textos y comentarios** (342 en 52 ficheros).
   - Todas llevan ya la edición.
   - Los detalles modelo se renombran a la nomenclatura de la 4.ª (`MB1` → `MD B1`, `MW4` → `MD W4`, `MCB1` → `MD CB1`…).
   - Las cláusulas y tablas renumeradas se han traducido (tabla abajo).
   - Lo que no existe en la 4.ª queda como `SMDSC 3rd ed. …`.
   - `nibs.py` y `tab_beams.py` no se tocan: usan `'MN1'`/`'MN2'` como datos.
3. **Cambios de la 4.ª ed. aplicados en la oleada D**:

| Regla | 3.ª ed. | 4.ª ed. | Dónde |
|---|---|---|---|
| Barras de piel en vigas | H16 a 250 desde 1000 de canto | Tabla MD B1: número y diámetro por canto × ancho, desde 750 | `links.md_b1_side_bars` |
| Superiores de losa en apoyo interior | 0,3 × luz entre ejes | 0,3 l (50 %) y 0,15 l (100 %) desde la cara, o l_bd si es mayor | `mesh_rules.support_strips_mm`, `md_s1_top_reach_mm` |
| Barras de reparto en losas | — | Tabla de MD S1 (paso por canto y Ø) | QA `distribution_issues` |
| Hanger bars | — | ≥ 20 % del acero de apoyo, H16 recomendado (6.3.2.9) | `links.hanger_issue` |
| Sillas | detalladas | a cargo del contratista salvo encepados multipilar y losas de cimentación (4.2.6, 6.7.2) | notas de montaje |
| Trimmers de losa | 45Ø más allá del hueco | mínimo 450 (anclaje nominal), 6.2.2.12 | se mantiene 45Ø (≥ 450 desde H10) |
| Detalles tipo | — | 4.1.2: plano de detalles tipo | `typical_details`, plano 4900 |

## Renumeraciones aplicadas a las citas

| 3.ª ed. | 4.ª ed. | Tema |
|---|---|---|
| 5.1.6 | 5.1.7 | longitudes y dimensiones de barras |
| 5.1.8 | 5.1.9 | doblados de gran radio |
| 5.1.9 | 5.1.10 | atado estructural (robustez) |
| 5.1.10 | 5.1.11 | mallas electrosoldadas |
| 5.4.3–5.4.5 | 5.4.2 | disposición de solapes |
| 5.4.6 | 5.4.5 | solapes de mallas |
| 5.5 | Apéndice D | acopladores mecánicos (el 5.5 de la 4.ª es soldadura) |
| Tabla 5.2 | Tabla 5.3 | tamaño real de la barra |
| Tabla 5.5 | Tabla 5.8 | deducciones entre caras de hormigón |
| Tabla 5.8 | Tabla 5.10 | solapes de alambres secundarios de malla |
| Fig. 6.9 | Fig. 6.7 | armadura de torsión en esquinas |
| Tabla 6.2 (bandas de losa plana) | 6.2.2.9 / MD S5 | la 4.ª cita «Tabla 6.2», que ahora es otra tabla |
| Tabla 6.10 | Tabla 6.7 | encepados tipo |

## Sin equivalente en la 4.ª ed. (se citan como 3.ª ed.)

- **Tabla 4.3**: planilla de mallas.
- **Capítulo 9** (9.2.1, 9.2.3, Tabla 9.1): estanqueidad.
- **Tablas 6.4 / 6.5 de la 3.ª** (α3 confinado): en la 4.ª esos números son tablas de paso mínimo.
- **MN2**: la 4.ª sólo tiene MD N1.
- **Banda bajo pilar en zapatas, l > 1,5 (c + 3d)** (3.ª ed. 6.7): la 4.ª no lo repite; se mantiene la regla.

## Pendiente de criterio del usuario

- La 4.ª ed. permite trimmers de 450 en losas; seguimos con 45Ø (más conservador). ¿Bajar a max(450, anclaje)?
