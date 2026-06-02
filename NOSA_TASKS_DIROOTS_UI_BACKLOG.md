# NOSA — DiRoots-style ideas + UI unificada (backlog de tareas)

Fecha de referencia: 2026-05-11  
Extensión: `NOSA.extension` (pyRevit)

---

## 1. Mapa DiRoots → NOSA (qué ya tenéis y qué falta)

| Idea estilo DiRoots | Qué aporta | Estado en NOSA | Notas |
|---------------------|------------|----------------|--------|
| **OneParameter / ProSheets** (pivote: categoría/familia/tipo → tabla plana → un parámetro) | Edición masiva de **un** parámetro sobre **miles** de instancias con vista tipo Excel | **Parcial** | `Data.panel/ParameterInspector`: muchos parámetros sobre **elementos ya seleccionados**; edición masiva posible pero **no** el flujo “elige categoría + un param → carga todo el modelo en grid”. Falta un **Bulk Parameter Editor** con pivote DiRoots. |
| **SheetGen** (tabla externa → una fila por plano + disposición vistas) | Producción de planos desde Excel/CSV sin clonar a mano | **Parcial** | `SheetComposer` ya tiene Import CSV / clone / renumber; **no** equivale aún a “columnas = viewports / layout” como SheetGen. Ampliar Composer o módulo aparte. |
| **View Manager** (rename con patrón, filtros, templates, dependencias) | Operaciones de vistas en bloque + trazabilidad con planos | **Parcial** | `ViewBatchManager` cubre **rename** (find-replace, prefijo/sufijo, preview) y **asignar/quitar plantillas de vista**. Faltan típicamente: **filtro por nivel/plantilla/on-sheet**, **informe dependencias** vista↔plano, quizá alineación con `TemplateGuard`. |
| **FamilyReviser** (editar parámetros de **tipo** sin abrir el editor de familias) | Perfiles acero/hormigón, materiales, rodetes | **Hueco fuerte** | `FamilyAudit` existe; no sustituye editor de **Structural Framing/Column types** en grid. Alto valor: **Section Type Manager** (ver abajo). |
| **TableGen** (multi-categoría + export con formato) | Tablas cruzadas fuera de schedules nativos | **Baja prioridad vs nativo** | `ExportScheduleToExcel` + schedules Revit. Valor NOSA: combinar con **QuantificationQA** / **DrawingIndex** para vistas tipo “cruzado por nivel” (diferenciador). |

### Prioridad recomendada para nuevas piezas

1. **Bulk Parameter Editor** (pivote DiRoots) — complementa naturalmente a `ParameterInspector`.  
2. **Section Type Manager** (familias estructurales / tipos — acero y hormigón) — encaja con Gibraltar / NOSA estructural.  
3. **Ampliar SheetComposer / “SheetGen mode”** — CSV con convención de columnas documentada + opcional layout de viewports (fases).  
4. **ViewBatchManager v2** — filtros avanzados + report dependencias con planos.  
5. **TableGen / cruzados** — solo si un caso de negocio no lo cubre un schedule + export.

---

## 2. Interfaz común (NOSAWindow + tema)

**Patrón objetivo:** ventana WPF con `lib/nosa_utils/base_window.NOSAWindow`, `ThemeManager`, tipografía **Century Gothic**, mismos recursos (`BgColor`, `AccentColor`, etc.).

### Comandos con `lib/ui.xaml` (patrón ya alineado con NOSAWindow o WPF dedicado)

Gran parte de Data / Documentation / Structures / Piling (ver carpetas con `ui.xaml`). Incluye: `DrawingIndex`, `SheetComposer`, `ExportSheets`, `ParameterInspector`, `ViewBatchManager`, `ModelCleanup`, …

### Comandos **sin** ventana NOSA (flujo consola / pyRevit forms / solo diálogos)

Prioridad para **llevar a NOSAWindow** o formulario mínimo estándar:

| Comando | Carpeta aprox. | Acción backlog |
|---------|----------------|----------------|
| Center beam to column | `Structures.panel/.../CenterBeamToColumn` | UI config (checkboxes, límites tolerancia) + resultados en panel |
| Add pile to pilecap | `Piling.panel/.../AddPileToPilecap` | Panel resumen + opciones persistentes (gran script) |
| Waffle slab | `Structures.panel/.../WaffleSlab` | Form parámetros + preview / log en ventana |
| Halftone selection | `Documentation.panel/.../HalftoneSelection` | Opciones apply/remove + scope en NOSAWindow ligero |
| Batch rename / Mayúsc–minúsc (×2) | `Documentation.panel/Text.pulldown` | Form unificado “Text tools” o 3 mini-ventanas mismo estilo |
| Export schedule to Excel | `Data.panel/ExportScheduleToExcel` | Ventana NOSA: selección schedule, formato, ruta |

*(Si en tu copia existe `LevelNavigator`, tratarlo igual: NOSAWindow + lista niveles / crear vistas.)*

### Inconsistencias menores a unificar

| Comando | Nota |
|---------|------|
| **Tag All** | Usa `forms.WPFWindow` + `ThemeManager` manualmente; migrar a **`NOSAWindow`** o extraer estilos compartidos para que coincida 1:1 con el resto. |
| Cualquier herramienta con **loading** / **tabs** | Reutilizar patrones de `ExportSheets` / `SheetComposer` (barra estado, `SetLoading`). |

**Tarea transversal:** Documento interno de 1 página: *“NOSA UI kit”* (plantilla XAML mínima, nombres `LoadingPanel`, sidebar, botones `ActionButton`). *(Opcional según tiempo.)*

---

## 3. Task list (checkbox) — pendientes

### A. Interfaz unificada

- [ ] **A1** Inventariar los 36 pushbuttons y etiquetar: `NOSAWindow` / `WPFWindow` / sin UI.
- [ ] **A2** Migrar **Tag All** a `NOSAWindow` o pack de recursos compartido con `DrawingIndex`.
- [ ] **A3** Añadir ventana NOSA a **CenterBeamToColumn** (config + log).
- [ ] **A4** Añadir ventana NOSA a **WaffleSlab** (parámetros + mensajes).
- [ ] **A5** Añadir ventana NOSA a **HalftoneSelection** (modo halftone + confirmación volumen selección).
- [ ] **A6** Panel unificado **Text tools** (`BatchRename` + mayúsc/minúsc) o tres XAML mismo theme.
- [ ] **A7** **`ExportScheduleToExcel`**: pantalla única tipo Data (schedule, columnas, ruta).
- [ ] **A8** **`AddPileToPilecap`**: barra lateral de opciones + resumen post-ejecución (iterativo por tamaño).

### B. Estilo DiRoots — nuevas capacidades

- [ ] **B1** **Bulk Parameter Editor** — filtro categoría/subcategoría + familia/tipo opcional → elegir **un** parámetro (instancia o tipo) → grid de instancias con valor actual → editar selección → transacciones por lotes + CSV export.
- [ ] **B2** **Section Type Manager** — recopilar tipos relevantes (`Structural Framing`, `Structural Columns`, forjados/paramétricos si aplica); grid comparativo; duplicar tipo; editar parametrización editable **sin abrir familia**; export Excel; filtros por material/familia.
- [ ] **B3** **Sheet Composer — modo SheetGen** — especificación de CSV (columnas: número, nombre, titleblock, parámetros NOSA ya soportados, **opcional**: IDs o nombres de vistas a colocar / patrón de viewport); plantilla README en `NOSA_Configs`; validación pre-import.
- [ ] **B4** **View Batch Manager v2** — filtros: tipo vista, plantilla actual, nivel, “solo colocadas en plano”; vista previa mejorada; pestaña **“Sheet dependencies”** (vista → planos que la usan); integración opcional export CSV.
- [ ] **B5** **Cruce datos / pseudo-TableGen** — export combinado Ej.: volúmenes por nivel desde `QuantificationQA` + hoja CSV unificada; o extensión de `DrawingIndex` con columnas calculadas *(solo tras definir caso de uso)*.

### C. Robustez / coherencia (arrastre trabajo previo)

- [ ] **C1** Revisión global `imp.load_source` vs colisiones de módulos en nuevos comandos (mismo patrón que `ExportSheets` / `PileMaster`).
- [ ] **C2** Unificar uso de **`sheet_protocol`** en cualquier lectura/escritura de metadata de **Form** / cajetín en herramientas futuras que toquen sheets.
- [ ] **C3** QA manual por bloque tras A y B según checklist existente.

### D. Producto / documentación

- [ ] **D1** Actualizar **`NOSA` dashboard** (`NOSA.Panel`) listando herramientas nuevas y enlazo a README corto por comando.
- [ ] **D2** Changelog usuario + versioning extensión al cerrar cada bloque (A / B).

---

## 4. Resumen ejecutivo

- **DiRoots** aporta sobre todo **patrones UX**: pivote filtros ↔ tabla ↔ acción única (OneParameter); datos externos ↔ planos (SheetGen); vistas en masa (View Manager); tipos sin editor (FamilyReviser). En NOSA, **ParameterInspector** + **ViewBatchManager** + **SheetComposer** ya cubren **parte** del mapa; el mayor hueco estratégico es **tipo estructural en grid** y el **Bulk Parameter pivot**.  
- **UI común**: varios comandos siguen sin `NOSAWindow`; conviene cerrar eso antes o en paralelo a nuevas piezas grandes para que no se acumule deuda visual.  

Cuando priorices dentro de cada bloque, suele funcionar bien: **A (UI vacíos) + B1** en paralelo, luego **B2**, después **B3/B4**.
