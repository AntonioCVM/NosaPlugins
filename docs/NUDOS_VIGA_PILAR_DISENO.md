# Resolución de choques en nudos viga–pilar: reglas de decisión (borrador para aprobación)

Estado: **borrador, pendiente de tu aprobación**. La función se desarrolla y se prueba en copias, pero no está conectada a las ejecuciones reales. Cualquier cambio requiere tu confirmación caso a caso.

## 1. Qué se considera choque

En cada extremo de una viga que entra en un pilar se comparan, en la sección del nudo, las posiciones transversales de:
- las barras longitudinales de cada capa de la viga (superior e inferior);
- las barras verticales del pilar en la cara por la que entra la viga.

Una barra de viga **choca** cuando su hueco libre con la barra de pilar más cercana, medido entre caras reales (diámetro × 1,1 por corrugas, `rebar_qa.REAL_DIA`), es menor que el mínimo

`s_min = max(φ_max, d_g + 5, 20 mm)` — EC2 8.2(2) y SMDSC 4.ª ed. 5.2.5 (`rebar_qa.min_clear_mm`).

Es la comprobación que ya hace `joints.bars_between`. La función no cambia este criterio ni la tolerancia de la QA.

## 2. Principios que no se negocian

- **P1. Las barras del pilar no se mueven.** Decisión del usuario de 2026-10-11 (`rebar_qa.joint_advice`): el pilar manda y cede la viga.
- **P2. La posición resistente de la viga no cambia.**
  - No se toca ninguna barra en cota: el canto útil d se conserva.
  - No se cambian número ni diámetro de barras.
  - Una segunda capa (reduce d) o barras más pequeñas son cambios de cálculo: el plugin solo puede proponerlos como "revisión manual".
- **P3. Las barras de esquina de la viga no se mueven.** Deben quedar en las esquinas de los cercos (EC2 9.2.2 y SMDSC 4.ª ed. 6.3); solo se mueven barras intermedias.
- **P4. Ningún cambio sin confirmación.** La propuesta se presenta con qué barra, cuánto y por qué. El usuario la acepta, la rechaza o elige otra alternativa, y se registra la decisión.
- **P5. Choque resuelto significa armado ejecutable**, no ausencia de aviso. Tras aplicar se regeneran el armado, los planos y la BBS afectados, y se pasa la QA existente.

## 3. Reglas, en orden de preferencia

### R1. Desplazamiento lateral de la barra completa (desplazar)

Se desplaza δ en horizontal, dentro de su capa, una barra intermedia de la viga. El desplazamiento abarca toda la barra, de apoyo a apoyo, sin cambio de forma. Se elige el |δ| más pequeño que cumpla **a la vez**:

| Comprobación | Criterio | Referencia |
|---|---|---|
| Recubrimiento | \|y + δ\| ≤ b/2 − c_nom − φ_cerco − φ/2: la barra queda dentro del cerco | EC2 4.4.1 |
| Separación con las barras de su capa | hueco libre ≥ s_min | EC2 8.2(2), SMDSC 5.2.5 |
| Separación con las barras de **todos** los pilares de la línea (los dos extremos y los apoyos intermedios) | hueco libre ≥ s_min | EC2 8.2(2) |
| Hueco para el vibrador (capa superior) | si la capa original lo cumplía, la nueva también: hueco ≥ 75 mm | SMDSC 4.ª ed. 4.2 / MD B1 (`rebar_qa.vibrator_issue`) |
| Barra sujeta por una horquilla interior | no se desplaza (la horquilla tendría que moverse con ella) | SMDSC 6.3 |
| Simetría resistente | \|δ\| ≤ s/2, donde s es la separación entre barras de la capa: la barra no cruza a su vecina ni cambia el orden de la capa | criterio técnico (P2) |

El anclaje, el radio de doblado y la forma de la barra no cambian, porque la geometría solo se traslada. La QA los comprueba igualmente después de aplicar el cambio.

### R2. Acodado local antes del nudo (acodar)

Solo si R1 no encuentra δ. La barra se acoda una excentricidad e para pasar entre las barras del pilar y vuelve a su posición fuera del nudo.

| Comprobación | Criterio | Referencia |
|---|---|---|
| Pendiente | longitud del acodado ≥ 10 · e | SMDSC 4.ª ed. MD C2 (`column_rebar.CRANK_SLOPE`) |
| Excentricidad máxima | e ≤ 75 mm | SMDSC (`column_rebar.MAX_CRANK_OFFSET_MM`) |
| Radio de doblado | mandril ≥ 4φ (φ ≤ 16) / 7φ (φ ≥ 20) | BS 8666 tabla 2 (`standards.standard_mandrel_mm`) |
| Tramo recto entre dobleces | ≥ 5φ | SMDSC tabla B1 / BS 8666 (`standards.min_end_projection_mm`) |
| Dónde | el acodado termina antes de la cara del pilar, sin solaparse con la zona de anclaje requerida | EC2 8.4 |
| Esfuerzo en la barra | **solo barras comprimidas en el nudo**: inferiores en apoyos de vigas continuas. Una barra traccionada acodada empuja el hormigón (fuerza de desvío ≈ T · e / l_acodado) | criterio técnico; EC2 8.3 (fuerzas de desvío) |
| Recubrimiento y separación en la posición acodada | igual que en R1 | EC2 4.4.1, 8.2(2) |

El acodado cambia la forma de la barra en la BBS. La función calcula la nueva forma y la regenera, y la QA la comprueba.

### R3. Revisión manual (señalar)

Cuando ni R1 ni R2 cumplen **todas** las condiciones, el nudo **queda señalado** y no se fuerza ninguna solución. El aviso incluye las alternativas que requieren cálculo:
- pasar la barra a segunda capa (comprobar el nuevo d);
- usar más barras de menor diámetro (por ejemplo 4H25 por 2H32);
- recolocar las barras del pilar, si el proyectista lo acepta (contra P1).

## 4. Casos que deben probarse

| Caso | Situación | Resultado esperado |
|---|---|---|
| A. Nudo de esquina | Viga de 300 mm con 3H20 y pilar de 450 mm con 3H20 por cara: la barra central de la viga coincide con la barra central del pilar | R1: la barra central se desplaza lo justo para dejar s_min a la barra del pilar, dentro del cerco y con la separación a las barras de esquina |
| B. Nudo interior | Dos vigas en cruz y pilar con barras centrales en las cuatro caras | R1 en cada dirección. Las barras superiores de la viga secundaria ya bajan bajo las de la principal (T8.49) |
| C. Viga a canto completo con forjado que corta la viga | La inversión temporal de la unión de este proyecto | R1 igual que en A. El forjado no cambia |
| D. Sin solución | Viga estrecha en la que ningún δ cabe dentro del cerco y la barra está traccionada (sin R2) | R3: nudo señalado con alternativas, sin ningún cambio |
| E. Línea continua | La misma barra pasa por tres pilares con posiciones distintas | R1 solo si un mismo δ vale en los tres pilares; si no, R2 en el apoyo intermedio (barra inferior comprimida) o R3 |

## 5. Comportamiento y registro

1. **Detección**, sin cambiar nada: tabla de choques por nudo (viga, pilar, extremo, capa, barra, hueco libre, s_min).
2. **Propuesta** por choque: regla (R1/R2/R3), barra (id y marca), δ o e en mm, comprobaciones con su valor y su límite, y alternativas.
3. **Confirmación** del usuario por propuesta: aceptar, rechazar o elegir otra alternativa.
4. **Aplicación** solo de lo aceptado. Después se regeneran el armado, los planos y la BBS afectados, se pasa la QA del miembro y se compara antes/después:
   - ninguna barra sale de su posición resistente salvo la corrección;
   - recubrimientos, separaciones, anclajes y doblados siguen en regla.
5. **Registro** JSON por decisión: fecha, nudo (ids de viga y pilar), barras (ids, marcas), causa (hueco y mínimo), regla, valores, estado (propuesta / aplicada / rechazada / pendiente) y resultado de la QA posterior.

## 6. Qué queda fuera de esta fase

- La aplicación automática sin confirmación. Solo se propondrá con todas las reglas probadas, sin falsos positivos atribuibles a la función y sin degradaciones demostradas, y siempre con tu aprobación expresa.
- Cambiar la tolerancia de la QA o desactivar comprobaciones.

## 7. Decisiones que te pido

1. ¿Apruebas el orden R1 → R2 → R3 y que R2 se limite a barras comprimidas en el nudo?
2. ¿Apruebas para R2 la pendiente 1:10 y la excentricidad máxima de 75 mm, tomadas de los acodados de pilares (SMDSC MD C2), o prefieres otro criterio para vigas?
3. En R1, ¿aceptas el límite |δ| ≤ s/2, o prefieres un tope absoluto en mm?
