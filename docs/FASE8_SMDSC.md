# Fase 8 (T8.25+) — RebarAutomate según el IStructE *Standard Method of Detailing Structural Concrete*

Fuente: IStructE / Concrete Society, *Standard Method of Detailing Structural Concrete* (3.ª ed., EC2 + UK NA,
BS 8666), PDF aportado por el usuario el 2026-10-06. Este documento extrae las reglas que el plugin debe aplicar
y las cruza con lo que hace hoy. Las tareas están en [MASTER_ROADMAP.md](../MASTER_ROADMAP.md) (Fase 8, T8.25–T8.58).

Criterio general del manual (6.1): los *Model Details* son la práctica por defecto; el detallista los sigue salvo
instrucción del proyectista. El plugin debe hacer lo mismo: **regla SMDSC por defecto, editable por el usuario,
y el valor usado visible en el resultado**. Valores con Δcdev = 5 mm (contratista con sistema de calidad).

---

## 1. Representación (cap. 3, 4.2 y 6.x.4)

| Tema | Regla SMDSC | Hoy en el plugin / plantilla | Tarea |
|---|---|---|---|
| Nivel de detalle | Secciones de barra «aproximadamente a escala» (3.10) | Vistas creadas en Medium/según plantilla | **T8.25 hecho** (Fine) |
| Grosores de línea | Contorno de hormigón 0,35; barra principal 0,7; cercos 0,35–0,7; cotas y ejes 0,25 (3.10) | Barras con el grosor de la categoría | T8.26 |
| Escalas | GA 1:100; losas y muros 1:50; alzados de viga y pilar 1:50; secciones de viga y pilar 1:20; detalles 1:10/1:5 (3.15) | `view_plan` elige escala por tamaño | T8.30 |
| Secciones | Solo el plano de corte (sin lo de detrás); vigas mirando a la izquierda, pilares hacia abajo; junto al detalle (3.18) | Secciones con profundidad lejana amplia | T8.29 |
| Alzados | Corte junto al elemento; lo cortado en continuo, lo de detrás discontinuo (3.17) | Alzado con lo que haya | T8.29 |
| Llamada de barras | `Número Tipo+Ø - marca - separación capa`, p. ej. `20H16-63-150 B1`; en vigas y pilares sin separación ni capa; el número de un grupo se escribe una sola vez (4.2.1) | Etiquetas por familia de etiqueta, sin capa | T8.28 |
| Capas | B1/B2 (inferior exterior/segunda), T1/T2, N1/N2 (cara cercana), F1/F2 (cara lejana); con croquis de la notación en cada plano (4.2.1, 6.2.2) | `NOSA_Rebar_Layer` interno (bottom_x, top_y…) | T8.28, T8.31 |
| Barra tipo + línea indicadora | Una barra tipo dibujada a escala, línea indicadora con flechas en la primera y última del grupo, punto grande en la unión; zonas múltiples con cantidades entre paréntesis; «Stg.» para escalonar, «Alt.» para alternar marcas (6.2.2) | MRA de Revit + etiquetas | T8.27 |
| Barras de longitud variable | Misma marca con sufijo **a, b, c…**: `8H20-1(a to h)-150`; la planilla lista 1a, 1b… (4.5.1, 6.2.2) | Sufijo Revit «A, B…» (mayúscula) desde T8 de ayer | T8.28 |
| Barras «en otro plano» | Línea gruesa discontinua + «SEE DRG» | — | T8.27 |
| Barras en alzado | Línea gruesa con marca; primera y última del grupo como punto en sección; barras cortadas con oblicuas de 30° (6.2.2) | Presentación de Revit por defecto | T8.27 |
| Cotas de fijación | Solo las que el ferrallista necesita y no controla el recubrimiento; líneas finas con oblicuas cortas (6.2.2) | Cotas de separación de cercos | T8.29 |
| Notas del plano | Referencias a GA, abreviaturas, clase de hormigón, recubrimientos, referencias de planilla; casilla de planillas sobre el cajetín (3.7) | Cajetín NOSA; sin bloque de notas de armado | T8.32 |
| Método tabular / representativo | Pilares y zapatas tipo con tabla por tipo (4.1.1, 6.4.4, 6.7.4) | Partitions (C1 × 3…) ya agrupan iguales | T8.54 |

## 2. Planillas (4.5, BS 8666)

- Columnas del BBS de la Tabla 4.2: Member, Bar mark, Type and size, No. of mbrs, No. of bars in each, Total no.,
  Length of each bar † (múltiplos de 25), Shape code, A–E/R * (múltiplos de 5), Rev letter. Estado P/T/C.
- Referencia de planilla de 6 caracteres: 3 del número de plano + 2 de número de planilla + 1 letra de revisión
  (p. ej. `04602A`); la marca es única dentro de cada planilla; la etiqueta del atado lleva referencia + marca.
- Marcas sin prefijos de ubicación; barras en orden numérico; agrupadas por elemento y, en edificios, planta por
  planta; cada planilla completa (nada de «as before»); planillas en A4 aparte del plano.
- Hoy: marcas por *member* (C1-01), BBS de la plantilla agrupado por *Partition*. → **T8.33** (sistema de
  referencia), **T8.34** (conformidad BS 8666: redondeos, estado, revisión, orden, A4).

## 3. Técnica (cap. 5)

- **Barras**: tamaños preferentes 8, 10, 12, 16, 20, 25, 32, 40; Ø real máx. ≈ +10 % (Tabla 5.2: 20 → 23, 25 → 29,
  32 → 37); longitud comercial 12 m (≥ 12) y 6 m recomendados para ≤ 10 (4.2.4); barra doblada transportable si
  el lado corto del rectángulo envolvente ≤ 2,75 m (5.1.6).
- **Mandriles** (Tabla B1): radio mínimo de planilla 2d hasta Ø16 y 3,5d desde Ø20 (12/16/20/24/32/70/87/112/140);
  prolongación mínima P (5d recta; cercos < 150° 10d). Redoblado en obra no permitido (5.1.7). Doblados de gran
  radio en pilecaps, ménsulas, nudos muro-losa y muros en voladizo (5.1.8). → **T8.46**
- **Recubrimiento**: nominal = cmin + Δcdev, al elemento más exterior (cercos); recubrimiento a la barra principal
  ≥ Ø (o Ø equivalente de grupo) + Δcdev; ≥ tamaño de árido. → **T8.48**
- **Separación mínima libre**: max(Ø, dg + 5, 20 mm); capas alineadas en vertical con huecos para vibrador
  (5.2.5); en vigas 75 mm (100 en parejas), vertical max(25, Ø). → **T8.48**
- **Tolerancias de doblado** (Tabla 5.4) y deducción de detallado cerrado (Tabla 5.5: cercos 10/15/20 mm según luz
  entre caras 0–1/1–2/> 2 m; barras rectas 40). Longitud de corte redondeada **hacia arriba** a 25 mm. → **T8.47**
- **Anclajes y solapes** (5.4): lbd = α1…α5·lb,rqd ≥ lb,min; l0 = α1 α2 α3 α5 α6 lb,rqd ≥ max(0,3 α6 lb,rqd; 15Ø;
  200); α6 = 1,0 / 1,15 / 1,4 / 1,5 para < 25 / 33 / 50 / > 50 % solapado; armadura transversal en solapes con
  Ø ≥ 20: ΣAst ≥ As de una barra, en los tercios extremos del solape; compresión: una barra fuera de cada extremo a
  ≤ 4Ø; solapes contiguos: libre ≤ max(4Ø, 50) y desfase ≥ 0,3 l0 (Fig. 6.2); Ø > 40 sin solape salvo sección ≥ 1 m;
  grupos de barras (Øn = Ø√nb ≤ 55; nb ≤ 3, 4 en compresión/solape). Tablas típicas por elemento (6.1, 6.4, 6.5,
  6.6, 6.7, 6.9, 6.11). → **T8.45**
- **Manguitos** (5.5): tipos 1–7, notación «E» antes de la marca; Revit tiene `RebarCoupler`. → **T8.52**
- **Mallas** (5.1.10, 4.2.5, 5.4.6): A/B/C/D BS 4483, 4,8 × 2,4 m; solapes de secundarias Tabla 5.8 (150/250/350);
  planilla de mallas Tabla 4.3. Revit tiene `FabricSheet`/`FabricArea`. → **T8.51**
- **Atado (robustez, 5.1.9)**: periférico a ≤ 1,2 m del borde, (20 + 4n0) ≤ 60 kN; interiores en dos direcciones;
  horizontales a pilares y muros de borde; verticales. → **T8.50** (calculadora + comprobación, no automático)

## 4. Elementos (cap. 6)

### 4.1 Losas (6.2, MS1–MS8)
- Recubrimiento interior max(15, Ø) + Δcdev; exterior 35 + Δcdev. Ø preferente mínimo 10.
- Separación: mínima 75 (100 en solapes); máxima principal 3h ≤ 400 (2h ≤ 250 bajo cargas concentradas),
  secundaria 3,5h ≤ 450 (3h ≤ 400).
- As,min = 0,26 fctm/fyk bt d ≥ 0,0013 bt d (C30/37: 0,0015); inferior ≥ 40 % del máximo en vano; superior en
  apoyo ≥ 25 % (15 % en extremo); secundaria ≥ 20 % de la principal.
- Despiece simplificado (MS1): superiores alternadas a 0,3·luz (+ alternancia con la regla a+b / c+d, igualar si
  difieren < 500); inferiores 0,8·luz + 0,5 solape alternadas e invertidas; tabla de separación de reparto por
  canto y Ø. Bordes (MS2/MS3): U de área = mitad de la inferior en centro de vano, patillas 2h; apoyos simples
  con anclaje max(d, 0,3 lb,rqd, 10Ø, 100). Voladizos (MS4): superiores ≥ 2 × voladizo, inferior ≥ 0,5 × superior.
- Esquinas: mallas de torsión de lado ≥ luz corta/5, ¾ del área de vano (½ con un solo borde discontinuo) (Fig. 6.9).
- Huecos (6.2.2): ≤ 150 se ignoran; ≤ 500 desplazar barras a los lados o cortar + zunchos de igual área a 45Ø;
  500–1000 además superiores y diagonales si h > 250; grupos de huecos como uno solo.
- Forjados reticulares y losas planas: bandas de soporte y centrales 75/25 % (negativos) y 55/45 % (positivos);
  2/3 del negativo de banda de soporte en media banda centrada en el pilar; dos barras inferiores a través del
  pilar; punzonamiento: perímetros de cercos a ≤ 0,75d, primero a ≤ 0,5d, tangencial ≤ 1,5d (2d fuera).
- Plugin hoy: mallas por topología con varying sets, U de cierre perimetrales, diagonales en huecos, tresbolillo
  opcional. → **T8.39**

### 4.2 Vigas (6.3, MB1–MB3)
- Recubrimiento interior 30 + Δcdev (35 normal), exterior 35 + Δcdev (40).
- As,min 0,0015 bt d (C30/37); compresión ≥ 0,002 Ac; Ø mínimo 12; cercos Asw/(s bw) ≥ 0,085 %, Ø 8 mínimo.
- Separación horizontal mínima 75 (hueco de vibrador de 75 mm cada 300 mm de ancho), 100 en parejas; vertical
  max(25, Ø); separadores entre capas a 1 m, Ø max(25, Ø barra).
- Cercos: paso mínimo max(100, 50 + 12,5·nº ramas); máximo min(300, 0,75d, 12Ø compresión); ramas a ≤ min(600,
  0,75d) y ninguna barra a > 150 de una rama; sin cercos solapados; abiertos con cerco de cierre si ancho ≥ 450
  (*closers* desde 300); forma de cerco de torsión (Fig. 6.22).
- Laterales: canto ≥ 1000 → Ø16 a ≤ 250 (o H12 a 150 según MB1) dentro de los cercos.
- **Despiece simplificado** (con Qk ≤ Gk, carga repartida, ≥ 3 vanos, luces ±15 %; L = luz libre + d):
  - Montaje: ≥ 20 % del área de apoyo hasta 25 mm de cada apoyo (mínimo 2H16 si canto ≥ 500).
  - Superiores en apoyo interior: ≥ 60 % hasta donde basten las de montaje + solape, o **0,25L** si no hay
    datos; ninguna < max(0,15L, 45Ø).
  - Inferiores de vano: ≥ 30 % (continuas) / 50 % (simplemente apoyadas) hasta 25 mm del apoyo; el resto hasta
    **0,15L** de apoyo interior, **0,1L** de apoyo exterior monolítico y **0,08L** de apoyo simple.
  - Barras de empalme inferiores en apoyo interior ≥ 30 % del área de vano, solape a tracción con las de vano.
  - U en apoyo extremo: área ≥ la de momento de apoyo o 30 % (50 % apoyo simple) del vano; patilla superior
    como las de apoyo interior.
  - al por defecto **1,25d** si el proyectista no da otra cosa (curtailment lbd + al, Fig. 6.14).
  - Fijación parcial en extremos: ≥ 0,15 del máximo momento de vano (9.2.1.2).
  - Voladizos (MB3): ≥ 50 % hasta el extremo; ≥ 50 % ancladas 1,5 × voladizo; ninguna < 0,75 × voladizo.
- **Detallado flexible** (4.2.3, Fig. 4.1/4.5, 6.15): las inferiores de vano y las de montaje NO entran en el
  pilar (paran a 25/50 de la cara); la continuidad la dan las superiores de apoyo y las de empalme inferiores →
  jaulas prefabricables y libertad para esquivar las barras del pilar.
- Anclaje en apoyo estrecho: 12Ø desde el eje sin doblar antes del eje, o 12Ø + d/2 desde la cara.
- Vigas de gran canto (L < 3h): malla ortogonal ≥ max(0,001 Ac, 150 mm²/m) por cara, separación ≤ min(2b, 300).
- Alas: armadura de tracción repartida en el ancho eficaz (Fig. 6.16/6.17).
- Plugin hoy: negativos 0,15l+al / 0,30l+al (Concrete Centre, al = 1,125d) y positivos a 0,08/0,20 desde ayer;
  barras corridas que sí entran en el pilar con patilla. → **T8.35**, **T8.36**, **T8.37**

### 4.3 Pilares (6.4, MC1–MC6)
- Recubrimiento 35 + Δcdev interior / 40 exterior; si > 40, malla superficial ≤ 100 mm, Ø ≥ 4 (fuego).
- As,min max(0,002Ac; 0,10NEd/fyd); As,max 0,04Ac (0,08 en solapes). Ø mínimo 16; ≥ 4 barras (rectangular),
  ≥ 6 (circular).
- Separación mínima 75 (100 para Ø ≥ 40), 100 parejas; máxima 300 en compresión (todas a ≤ 150 de una barra
  sujeta), 175 en tracción.
- Cercos: Ø ≥ max(Ø/4, 8); paso ≤ min(20Ø, menor dimensión, 400), × 0,6 a una distancia = mayor dimensión por
  encima y debajo de vigas/losas y en solapes (≤ min(12Ø, 0,6 × menor dimensión, 240), ≥ 3 cercos); cerco en el
  codo de la patilla; cercos de estallido en solapes con Ø ≥ 20 (ΣAst ≥ As) en los tercios extremos.
- Patillas (MC2): codo en la parte baja del tramo, longitud del codo = 10 × desvío, enano (kicker) 75; esperas
  sobre forjado = solape de compresión + enano. MC3 pilares desplazados con barras de empalme; MC4 coronación:
  detalle A si el canto ≥ 200/250/300 para Ø20/25/32, si no B; MC6 circulares con zuncho helicoidal en tramos de
  12 m solapados.
- Unión viga-pilar de borde: U dentro del canto de la viga mejor que L hacia el pilar; armadura transversal del
  pilar dentro del canto de la viga si no hay viga de borde (Fig. 6.27).
- Plugin hoy: patillas 1:6 con aviso > 75 mm, densificación en nudos, esperas en cimentación. → **T8.38**

### 4.4 Muros (6.5, MW1–MW4) y muros de contención (6.6, MRW1–MRW3)
- **Horizontales por fuera de las verticales** (el recubrimiento se mide a las horizontales) en muros;
  en muros de contención, **verticales por fuera en la cara de tierras** y horizontales por fuera en caras
  expuestas (MRW1). Hoy: `vert_is_outer = True` por defecto. → **T8.40**
- Vertical ≥ 0,002Ac (mitad por cara), Ø ≥ 12; horizontal ≥ max(25 % vertical, 0,001Ac) por cara; separación
  ≤ min(3t, 400); cercos si As,v > 0,02Ac (paso vertical ≤ min(16Ø, 2t), horizontal ≤ 2t, barras libres a ≤ 200).
- Tabla MW1 de armado nominal por espesor (150–800 mm: verticales 12–20 a 200–300, horizontales 10–16 a 150–200).
- Esquinas MW2 (U del mismo Ø y paso que las horizontales; 2 barras dentro del lazo si t ≤ 300, 4 si > 300; splay +
  diagonal si > 1,5 %). Huecos MW4: zunchos un Ø mayor que el vertical (uno solo si t < 250/200), U alrededor,
  anclaje más allá de los zunchos. Coronación con U, arranque con L, enano 75 (150 bajo rasante).
- Contención: tierras 45 + Δcdev (50), exterior 40, interior 25; separación máx. 200; juntas de contracción ≤ 30 m;
  enano 150 integrado con la zapata; esperas del muro con la armadura de la losa base.
- Plugin hoy: mallas, U de extremo y coronación, esperas, tresbolillo opcional. → **T8.40**, **T8.43**

### 4.5 Cimentaciones (6.7, MF1–MF5)
- Recubrimiento 75 (inferior 100 en encepados sobre pilotes); tierras 45 + Δcdev; Ø mínimo 16 (salvo lacers);
  separación por cuantía: ≤ 0,5 % → 300, 0,5–1 % → 225, ≥ 1 % → 175 (mínima 100).
- Zapatas: barras rectas sin cortar; anclaje desde la cara del pilar/muro (patilla si no cabe); si lx > 1,5(cx + 3d),
  ≥ 2/3 de la armadura paralela a ly en una banda cx + 3d centrada en el pilar (y viceversa).
- Encepados: anclaje completo desde el eje del pilote extremo; disposiciones tipo de la Tabla 6.10 por número de
  pilotes (2, 3, 4/6, 5/8/9, 7) con formas 21/12/27/25/15; barras dobladas en ambos extremos; 2 capas de lacers H12.
- Esperas de pilar: patilla horizontal ≥ 450; solape de compresión + 150 de tolerancia de cota; cercos H10-300
  (mínimo 3) dentro de la zapata.
- Vigas riostras: recubrimiento 75 sin encofrado; armadura principal corrida a través del encepado; si atan, rodean
  las esperas y anclan.
- Plugin hoy: mallas por topología, U de cierre, esperas, varying sets en chaflanes. → **T8.41**

### 4.6 Escaleras (6.8, MST1–MST2), ménsulas y medias maderas (6.9), depósitos (cap. 9)
- Escaleras: U de rellano = 50 % de la inferior principal; «A» = max(0,1 luz, anclaje, 500); +10 mm de recubrimiento
  superior sin acabado; rellano apoyando la losa en rebaje. → **T8.42**
- Ménsulas/nervios: Ø ≤ 16 preferente, U horizontales o cercos con doblado amplio, principal hasta la cara exterior.
  → **T8.44** (tipología nueva)
- Depósitos: recubrimiento ≥ 40; tracción ≤ 250, reparto ≤ 150; clases de estanqueidad 0–3 (espesor mínimo
  120/150); juntas dibujadas. → **T8.53** (modo «water-retaining»)

## 5. Comprobación (4.4, 4.6)

Lista del detallista y del comprobador que el plugin puede automatizar (informe por host y por plano):
barras de viga que pasan entre las del pilar; capas de vigas que se cruzan (las del principal por encima); losa
sobre viga con su recubrimiento; solapes en zonas permitidas y dentro de la longitud comercial; congestión
(separación libre mínima con Ø real +10 %); ganchos que chocan; recubrimiento ≥ Ø y ≥ árido; separaciones máximas;
número de barras coherente entre plano y planilla; planilla con referencia y revisión. → **T8.48**, **T8.49**

## 6. Revit 2024–2027 (a verificar en cada versión antes de usarlo)

Capacidades de la API que el plan aprovecha; cada una debe comprobarse en las 4 versiones con una sonda del
harness (T8.55) antes de depender de ella:
- `Rebar.DistributionType = VaryingLength` + restricciones por cara (usado desde ayer en 2024).
- `ReinforcementSettings.NumberVaryingLengthRebarsIndividually` / `RebarVaryingLengthNumberSuffix` (2024 ok).
- Modo de presentación de conjuntos (`SetPresentationMode`: todas / primera-última / central / selección) por vista
  — base de la «barra tipo» del SMDSC.
- Anotación multi-armadura (MRA) con línea de cota/indicadora — base de la línea indicadora.
- Detalles de doblado nativos (`RebarBendingDetail`, versiones recientes) — alternativa a los croquis PNG del BBS.
- `RebarCoupler` (manguitos), `FabricSheet` / `FabricArea` (mallas), `RebarContainer`.
- Terminaciones: 2027 sustituye ganchos por `BarTerminationsData` (ya contemplado en `rebar_from_curves`).
- Defectos conocidos y anotados en la memoria del proyecto: restricciones a caras de elementos unidos, recorte de
  extremos al crear, sets imposibles con normal no perpendicular («internal error»), FreeForm sin forma, tipos de
  imagen a 72 ppp, límite de ~100 cargas de familia por llamada.
