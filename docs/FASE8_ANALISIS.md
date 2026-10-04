# Fase 8 — Análisis de consolidación (2026-10-04)

Base del análisis: inventario de `NOSA.tab` (38 botones visibles, 15 módulos ocultos o vacíos), uso real en
`NOSA_Configs/_usage.json` (aperturas acumuladas, claves actuales + heredadas), escaneo de patrones de riesgo
aprendidos en las fases 5–7 y auditoría en vivo de la plantilla v30 (Revit 2024).

## 1. Hallazgos transversales (afectan a casi todos los plugins)

| # | Hallazgo | Evidencia | Riesgo | Propuesta |
|---|---|---|---|---|
| 1 | **Transacciones sin protección de fallos** | 150 `Transaction(` en ~60 ficheros; solo RebarAutomate (10) instala un `IFailuresPreprocessor`. `nosa_utils.transactions.nosa_transaction` existe pero no lo hace y solo lo usan 2 ficheros | Un error de Revit abre un diálogo modal que bloquea la sesión (vivido 3 veces en la fase 7) | T8.1: `nosa_transaction` con preprocesador (borra avisos, deshace errores y devuelve el texto) y migración de todos los plugins |
| 2 | Sin prueba de humo en Revit por plugin | Los tests son de lógica pura; `ui_smoke.py` solo cubre algunos | Ventanas que no abren en 2025/2026/2027 se descubren en producción | T8.2: abrir cada ventana con el arnés en las 4 versiones |
| 3 | Módulos ocultos ya absorbidos por hubs y carpetas vacías | `.nobutton`: AnnotationBatch, GridBubbleBatch, DrawingProtocolChecker, DrawingIndex, SheetNamer, TemplateGuard, ViewBatchManager, LinkChangeMonitor, RebarAuditor, RebarManager, RebarSchedule; vacíos: ExportSheets, ClashReport, `QA.modules`; `TagAll2.pushbutton.DISABLED` | Código muerto que el lint y las búsquedas siguen leyendo | T8.3: verificar que el hub cubre cada función y borrar |
| 4 | 63 hallazgos del lint y 246 `print()` en RebarAutomate | `tools/nosa_lint.py` | Salida de consola ruidosa; avisos ignorados | T8.4 |
| 5 | RebarAutomate: 30 000 líneas, `ui.py` monolítico | inventario | Cada cambio toca el mismo fichero | T8.5: dividir `ui.py` por tipología |
| 6 | `SelectionChanged` declarado en XAML | 30 casos, casi todos en DataGrid (seguros); los peligrosos (ComboBox/TabControl) solo en módulos ocultos (SheetNamer, ViewBatchManager) | Bajo | Se elimina con T8.3 |

## 2. Plugin a plugin

Uso = aperturas registradas (actual + heredado). Acción: **M** mantener · **F** fusionar · **R** retirar · **N** mejora.

| Panel / plugin | Líneas | Uso | Observaciones | Acción |
|---|---:|---:|---|---|
| Documentation / **Sheet Export Hub** | 3 874 | 310 | La herramienta más usada. Sin comprobación de protocolo ni de contenido antes de exportar | **N** T8.12 comprobador previo a la exportación |
| Reinforcement / **RebarAutomate** | 30 012 | 116 | Fase 7 completa. Deuda: tamaño, `print`, Tag All en plantas | **N** T8.5, T8.15, T8.16 |
| Foundations / **Pile Master** | 2 432 | 107 | Exporta coordenadas de pilotes: duplica *pile setting-out* de Survey Export | **F** T8.8 |
| Documentation / **QR Code** | 1 607 | 96 | Correcto | M |
| Quantities / **Material Manager** | 1 045 | 78 | Correcto | M |
| Foundations / **Create Pilecap** | 1 007 | 64 | Correcto | M |
| Foundations / **Add Piling** | 1 805 | 50 | 2 `print` | M (T8.4) |
| Data / **Project Setup** | 312 | 54 | Correcto; base del generador de notas (T8.13) | M |
| Elements / **Element Join** | 751 | 41 | Correcto | M |
| Data / **Element Comments** | 952 | 36 | Correcto | M |
| NOSA / **Dashboard** | 503 | 32 | Correcto | M |
| Sheets / **Sheet Hub** | 1 158 | 21 | Edición de protocolo y duplicado de hojas | **F** con Sheet Gen (T8.10) |
| Sheets / **Sheet Gen** | 1 961 | 14 | Creación de hojas; 62 `alert` | **F** en Sheet Hub (T8.10) |
| Views / **View Manager** | 1 042 | 18 | | **F** View Hub (T8.9) |
| Views / **View Utilities** | 1 402 | 3 | Uso muy bajo | **F** View Hub |
| Views / **View Overrides** | 817 | 1 | Uso muy bajo | **F** View Hub |
| Views / **Template Manager** | 782 | 1 | Uso muy bajo | **F** View Hub |
| Annotations / **Auto Dimensions** | 1 459 | 17 | | M |
| Annotations / **Tags & Symbols** | 283 | 20 | Tag All (T7.4) | M |
| Annotations / **Text Tools** | 406 | 4 | | M |
| Quantities / **Schedule Pro** | 1 293 | 30 | | M |
| Elements / **Waffle Slab** | 1 168 | 16 | | M |
| Elements / **Structural Types** | 793 | 9 | | M |
| Elements / **Align Element to Column** | 538 | 14 | | M |
| Elements / **Pour Sequence Planner** | 270 | 7 | | M |
| Foundations / **Pilecap Geometry Check** | 776 | 11 | | M |
| Foundations / **Footing Designer** | 716 | 2 | Crea zapatas; RebarAutomate las arma | M |
| Foundations / **Survey Export** | 1 310 | 1 | Duplica parte de Pile Master | **F** T8.8 |
| Foundations / **Site Toolkit** | 339 | 2 | Solo lectura | M |
| Structures / **Model Health Hub** | 3 679 | 2 (+ claves antiguas) | Se solapa con Structural QA | **F** QA Hub (T8.7) |
| Structures / **Structural QA** | 2 752 | 3 | | **F** QA Hub (T8.7) |
| Documentation / **Issue Workflow Hub** | 1 964 | 5 | Contiene el comprobador de protocolo que reutilizará T8.12 | M |
| Data / **Data Tools** | 2 186 | 4 | | M; recibe T8.11 |
| Data / **Parameter Hub** | 1 129 | 5 | | M |
| Data / **Shared Parameters** | 350 | 1 | | **F** Data Tools (T8.11) |
| Data / **Worksharing Audit** | 303 | 2 | | **F** Data Tools (T8.11) |
| Reinforcement / **Rebar Hub** | 567 | 2 | BBS, marcas y agrupación ya están en RebarAutomate | **F** auditoría EC2 a RebarAutomate, retirar (T8.6) |
| Módulos ocultos (11) y vacíos (3) | — | 0–8 | Funciones ya en los hubs | **R** T8.3 |

## 3. Herramientas nuevas propuestas

1. **Comprobador de planos en Sheet Export Hub (T8.12).** Antes de exportar comprueba:
   - el número y los campos del protocolo NOSA v2.2 / ISO 19650 (`sheet_protocol`);
   - el código de revisión (P01/C01) y el estado;
   - la serie del número frente al *functional breakdown*;
   - que el cajetín esté completo;
   - la escala del cajetín frente a la de los viewports;
   - viewports fuera del área de impresión y hojas vacías;
   - vistas sin plantilla;
   - tipos de texto y cota que no sean NOSA, y textos con faltas típicas.

   Genera un informe y puede bloquear la exportación de lo que no cumple.
2. **Generador de notas generales 0900 (T8.13).** Rellena los valores propios de cada proyecto (clase de hormigón, recubrimientos por exposición, viento, fuego, cargas de barandilla, terreno…) desde un diálogo. Regenera la tabla de anclajes y solapes con `nosa_utils.standards`, el mismo motor que RebarAutomate.
3. **Auditoría de estándares del proyecto frente a la plantilla (T8.14).** Detecta tipos, estilos, patrones y materiales ajenos, residuos de DWG, nombres en español y parámetros duplicados.

## 4. Auditoría de la plantilla v30

| Área | Hallazgo | Propuesta |
|---|---|---|
| 0900 General notes | 8 drafting views, 1 leyenda y notas sueltas en la hoja; normas retiradas y erratas | **Hecho 2026-10-04**: un único drafting view, normas al día y erratas corregidas (T8.17 recoge lo pendiente) |
| 0002 File naming protocols | Imagen de `N:\2. Technical\NOSA QA\NOSA File Naming Protocols.pdf` (ruta inaccesible fuera de la red) | Contenido nativo y buscable (T8.23); necesita el PDF |
| Materiales (91) | Restos en español (*Cubierta por defecto*, *Muro por defecto*, *Por defecto*, *Relleno*, *Vidrio*, *Material de renderización…*), 18 *Render Material x-y-z* de DWG, duplicados *Phase - Demo* / *Phase-Demo*, *Metal - Steel - 345 MPa* (EE. UU.) | Depurar (T8.18) |
| Patrones de línea (78) | Duplicados en español (*Centro*, *Oculto*, *Trazo…*), 13 *IMPORT-*, nombres imperiales (1/8", 3/16") | Depurar (T8.18) |
| Cotas | 3 *Linear Dimension Style*, *Arrow - 2.5mm Arial* (otra fuente) | Depurar (T8.18) |
| Parámetros de proyecto | Duplicados: *Manufacturer_ISO*, *Revit version*, *UniclassCode*, *UniclassDescription* | Uno compartido por nombre (T8.19) |
| Revisiones | Solo «1 First issue»; sin secuencias P01/C01 | Secuencias ISO 19650 (T8.20) |
| Perfiles de acero | Vigas en perfiles europeos (HEA/HEB/IPE/IPN/UPE/UPN) y pilares en UK (UKA/UKPFC/UKT); faltan UKB/UKC/PFC como viga; 773 de 781 tipos sin uso | Biblioteca UK BS EN 10365 curada (T8.21) |
| Plantillas de vista (10) | Nomenclatura mezclada (*NOSA GA PLAN* / *NOSA GA plan view*); sin plantilla 3D ni de cimentación; 3 vistas sin plantilla | T8.22 |
| Navegador | Varias organizaciones «all» repetidas | T8.22 |
| Filtros | Restos de pruebas: *Isolate Shape 00/21*, *RC 01*, *Sec 01* | Borrar (T8.18) |
| Imágenes | 6 con rutas rotas (Downloads, OneDrive, N:) | Borrar las no usadas (T8.18) |
| Tablas | Errata «Stairscases»; *BBS* y *Rebar Schedule* se solapan | T8.24 |
| Texto | Notas a 2,0 mm en A1 (BS EN ISO 3098 recomienda ≥ 2,5 mm en A0/A1) | Decisión del usuario (T8.17) |
| Correcto | Unidades en mm, 0 avisos, 0 familias in situ, 0 DWG, Uniclass 2015 presente, nombre del fichero según el protocolo, cajetines NOSA A1–A4 | — |
