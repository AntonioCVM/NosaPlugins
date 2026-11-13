# Fase 10 — Interfaz de RebarAutomate: más clara, más atractiva, más intuitiva (2026-10-17)

## Punto de partida (estado actual, `ui.xaml` 1786 líneas)

**Estructura actual:**
- 6 pestañas: Footings & Slabs, Columns, Beams, Walls, Stairs y Detailing & Tools.
- 48 casillas, 78 campos de texto, 16 desplegables y 28 botones.

**Problemas de organización:**
- Una pestaña mezcla zapatas y losas, y está llena de etiquetas «(Floors only)» / «(Footings only)».
- «Detailing & Tools» junta cosas sin relación: ajustes del proyecto, lotes, planillas, exportación, QA, vistas y etiquetado.
- Las barras añadidas por regla (U de borde, trimmers, diagonales, piel…) están al mismo nivel que los datos de cálculo.

**Problemas visuales:**
- Pestañas de texto arriba, todo en una columna de formulario y casi ningún uso de las «cards» de `NosaTheme.xaml`.
- El resultado se muestra como texto plano.
- La vista previa es pequeña y no usa los colores de material de los planos.

**Textos:**
- Quedan citas de la 3.ª ed. en el XAML (MC6, MCB1, MB1, MC2, «5.5», «5.1.9», «ch. 9»).

## Principios

1. **Seguir el flujo de trabajo**: proyecto → elemento → generar → revisar (QA) → planos → planillas/exportación.
2. **Separar diseño y regla**: lo que da el cálculo, por un lado; lo que añade el SMDSC, por otro, plegado y marcado.
3. **Mostrar sólo lo que aplica a la selección** en lugar de etiquetas «… only».
4. **Una sola forma de hacer cada cosa**: el botón principal siempre en el mismo sitio y con el mismo texto.
5. **Identidad NOSA**:
   - naranja #FF5F00 y Century Gothic;
   - cards con sombra suave;
   - colores de material de los planos en las vistas previas (naranja claro corte, gris visto);
   - modo oscuro coherente.

## Propuesta de pantalla

```
┌──────────────────────────────────────────────────────────────────────────────┐
│ ▣ REBAR AUTOMATE   Rebar test 2024 · SMDSC 4th ed. · EC2 UK NA     [☾] [?]   │  cabecera
│ Selected: 2 beams (B10, B11) · 1 slab (S10)            [Refresh selection]   │  barra de selección
├────────┬─────────────────────────────────────────────┬───────────────────────┤
│ PROJECT│  BEAMS · B10-B11                            │  PREVIEW              │
│ SLABS  │  ┌ Design reinforcement ─────────────────┐  │  ┌─────────────────┐  │
│ BASES  │  │ Main bars   [H20 ▾]  top [3] bottom [3]│  │  │ sección a escala │  │
│▶BEAMS  │  │ Links       [H8 ▾] @ [200]  zones ☑    │  │  │ naranja = corte  │  │
│ COLUMNS│  │            [SMDSC defaults]           │  │  └─────────────────┘  │
│ WALLS  │  └───────────────────────────────────────┘  │  elevation ▸          │
│ STAIRS │  ▸ Detailing rules (SMDSC 4th ed.)  5 on ⚑  │                       │
│────────│  ▸ Laps, stock lengths, advanced            │  QA  [ A+ ]  0 · 1    │
│DRAWINGS│                                             │                       │
│SCHED.  │                                             │                       │
│CHECK   │                                             │                       │
├────────┴─────────────────────────────────────────────┴───────────────────────┤
│ ✓ 10 bars created in 2 beams · 3 notes          [Create drawings ▸] [GENERATE]│  barra de acción
└──────────────────────────────────────────────────────────────────────────────┘
```

- **Navegación lateral** con iconos vectoriales (`Path`, sin PNG):
  - *Project*;
  - un apartado por elemento: Slabs, Bases (zapatas y encepados), Beams, Columns, Walls, Stairs;
  - *Drawings*, *Schedules & Export* y *Check & Manage*.

  La ventana abre en el apartado del elemento seleccionado.
- **Cada elemento con la misma plantilla**:
  - *Design reinforcement*: siempre visible, con el botón «SMDSC defaults»;
  - *Detailing rules (SMDSC 4th ed.)*: plegado; cada regla con su casilla, la cláusula en el tooltip y la bandera ⚑ «added by rule»;
  - *Advanced*: plegado.
- **Barra de acción fija**: resultado en una línea con icono de estado, lista desplegable de notas en la que se puede pulsar cada una para seleccionarla en el modelo, «Create drawings ▸» como siguiente paso y GENERATE.
- **Vista previa grande** a la derecha:
  - sección y alzado a escala, con el hormigón en sus colores de material y las capas rotuladas (T1/B1…);
  - debajo, el resultado del último QA como insignia A+/A/B/C de color.

## Oleadas

| Oleada | Contenido | Por qué en este orden |
|---|---|---|
| **A — Maqueta y arquitectura** | Maqueta navegable para aprobar antes de tocar código; nueva estructura de navegación; plantilla común de elemento; barra de selección y de acción | Lo demás cuelga de la estructura |
| **B — Aspecto visual** | Cards, iconos vectoriales, insignia QA, vista previa grande con colores de material, modo oscuro revisado, espaciado de 8 pt | Sobre la estructura ya fijada |
| **C — Flujo intuitivo** | SMDSC defaults por tabla, validación en línea, ocultar lo que no aplica, recordar pestaña y valores, resumen antes de generar, notas pulsables, «siguiente paso» | Usa la estructura y el aspecto |
| **D — Textos** | Inglés británico, citas de la 4.ª ed. en todo el XAML, etiquetas cortas, tooltips con cláusula | Revisión final de contenido |
| **E — Validación** | Test de XAML (nombres, sin `SelectedIndex` en XAML), prueba en Revit 2024 y después 2025–2027, capturas antes/después, rama `feature/ra-ui-v2` → `develop` → `main` | Cierre |

Todo en la rama aparte `feature/ra-ui-v2`: la interfaz actual sigue intacta en `develop`/`main` hasta que se apruebe.

## Estado (2026-10-18, rama `feature/ra-ui-v2`)

Hecho en las cinco oleadas:
- **A:** `ui.xaml` reconstruido a partir de las tarjetas actuales (`build_ui_v2.py`, en `%TEMP%
osa_tools`), conservando los 226 controles con nombre; navegación lateral; plantilla común de elemento; barras de selección y de acción. La lógica nueva está en `tab_shell.py` (ShellMixin).
- **B:** iconos vectoriales, cards, vistas previas con colores de material, insignia QA, modo oscuro corregido en `NOSAWindow.ApplyTheme`.
- **C:** GENERATE único que llama al de la pestaña activa; «Create drawings ▸» tras generar; tarjetas ocultas según la selección; validación en línea; «Reset to defaults»; pestaña recordada; doble clic en el registro selecciona el elemento.
- **D:** etiquetas en sentence case; referencias de la 4.ª ed.; depósitos a EC2-3.
- **E:** `tests/test_ui_v2.py`; ventana construida y renderizada en Revit 2024 (claro y oscuro).

Pendiente: SMDSC defaults por tabla (a confirmar), prueba en 2025–2027 y merge a `develop`/`main` tras la aprobación del usuario.
