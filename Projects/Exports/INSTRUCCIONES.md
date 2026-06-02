# Instrucciones para Corregir Errores de Revit

Este conjunto de scripts está diseñado para solucionar los errores detectados en el informe de errores de Revit del modelo **22039-NOSA-GM-ZZZ-M-S-6500**.

## Archivos Incluidos

1. **EJECUTAR_TODOS_LOS_SCRIPTS.py** - ⭐ Script maestro que ejecuta todos los scripts automáticamente (RECOMENDADO)

2. **fix_revit_errors.py** - Script principal para corregir:
   - Elementos unidos que no se intersectan
   - Muros adjuntos que no alcanzan objetivos
   - Pisos superpuestos

3. **fix_stair_errors.py** - Script para identificar problemas de escaleras:
   - Escaleras con extremo superior incorrecto
   - Runs con ancho menor al mínimo
   - Profundidad de escalón menor al mínimo
   - Descansos con profundidad menor al ancho

4. **fix_remaining_errors.py** - Script para errores restantes:
   - Vigas ligeramente fuera de eje
   - Líneas ligeramente fuera de eje
   - Líneas de propiedad sin bucle cerrado

## Requisitos Previos

- Revit abierto con el modelo cargado
- pyRevit instalado y funcionando
- Acceso de escritura al modelo

## Cómo Ejecutar los Scripts

### Paso 1: Abrir Revit y el Modelo

1. Abre Revit
2. Carga el modelo **22039-NOSA-GM-ZZZ-M-S-6500**
3. Asegúrate de tener permisos de escritura

### Paso 2: Abrir pyRevit

1. En Revit, abre pyRevit (normalmente desde la pestaña de extensiones)
2. Abre la consola de pyRevit

### Paso 3: Ejecutar los Scripts

Tienes dos opciones para ejecutar los scripts:

#### Opción A: Ejecutar el Script Maestro (RECOMENDADO)

El script maestro ejecuta todos los scripts automáticamente en el orden correcto:

```python
# En pyRevit, ejecuta:
exec(open(r'C:\Users\AntonioCViñas\AppData\Roaming\pyRevit\Extensions\NOSA.extension\Projects\Exports\EJECUTAR_TODOS_LOS_SCRIPTS.py').read())
```

Este script ejecutará automáticamente:
1. fix_revit_errors.py
2. fix_stair_errors.py
3. fix_remaining_errors.py

#### Opción B: Ejecutar Scripts Individualmente

Si prefieres ejecutar los scripts uno por uno:

##### 1. Script Principal (fix_revit_errors.py)

```python
# En pyRevit, ejecuta:
exec(open(r'C:\Users\AntonioCViñas\AppData\Roaming\pyRevit\Extensions\NOSA.extension\Projects\Exports\fix_revit_errors.py').read())
```

Este script:
- Desune elementos que están unidos pero no se intersectan
- Desadjunta muros que están adjuntos pero no alcanzan sus objetivos
- Resuelve pisos superpuestos (desune o elimina duplicados)

##### 2. Script de Escaleras (fix_stair_errors.py)

```python
# En pyRevit, ejecuta:
exec(open(r'C:\Users\AntonioCViñas\AppData\Roaming\pyRevit\Extensions\NOSA.extension\Projects\Exports\fix_stair_errors.py').read())
```

Este script identifica los problemas de escaleras. **Nota**: Muchos errores de escaleras requieren ajustes manuales.

##### 3. Script de Errores Restantes (fix_remaining_errors.py)

```python
# En pyRevit, ejecuta:
exec(open(r'C:\Users\AntonioCViñas\AppData\Roaming\pyRevit\Extensions\NOSA.extension\Projects\Exports\fix_remaining_errors.py').read())
```

Este script identifica los problemas restantes. Estos también pueden requerir ajustes manuales.

## Resumen de Errores Corregidos

### Errores Corregidos Automáticamente

- ✅ **Elementos unidos que no se intersectan**: 24 pares de elementos
- ✅ **Muros adjuntos que no alcanzan objetivos**: 3 muros
- ✅ **Pisos superpuestos**: 103+ pares de pisos (desunidos o duplicados eliminados)

### Errores que Requieren Ajuste Manual

- ⚠️ **Vigas fuera de eje**: 6 vigas (requieren alineación manual)
- ⚠️ **Líneas fuera de eje**: 2 líneas (requieren alineación manual)
- ⚠️ **Línea de propiedad sin bucle cerrado**: 1 línea (requiere cierre manual del bucle)
- ⚠️ **Problemas de escaleras**: 
  - 62 escaleras con extremo superior incorrecto
  - 6 runs con ancho menor al mínimo
  - 2 escaleras con profundidad de escalón menor al mínimo
  - 29 descansos con profundidad menor al ancho

## Verificación Post-Ejecución

Después de ejecutar los scripts:

1. **Revisa el informe de errores** en Revit para verificar que los errores se han corregido
2. **Verifica visualmente** los elementos modificados en el modelo
3. **Revisa las escaleras** manualmente y ajusta según sea necesario
4. **Corrige manualmente** los errores restantes identificados por los scripts

## Notas Importantes

- ⚠️ **Haz una copia de seguridad** del modelo antes de ejecutar los scripts
- ⚠️ Los scripts crean transacciones en Revit, por lo que los cambios se guardan automáticamente
- ⚠️ Algunos errores pueden requerir múltiples ejecuciones si hay dependencias entre elementos
- ⚠️ Los errores de escaleras generalmente requieren ajustes manuales específicos

## Solución de Problemas

### El script no se ejecuta

- Verifica que pyRevit esté correctamente instalado
- Asegúrate de que la ruta del archivo sea correcta
- Verifica que el modelo esté abierto y tengas permisos de escritura

### Algunos errores no se corrigen

- Algunos errores requieren ajustes manuales (especialmente escaleras)
- Verifica que los elementos existan en el modelo
- Revisa los mensajes de error en la consola de pyRevit

### Errores después de ejecutar los scripts

- Algunos elementos pueden tener dependencias que impiden la corrección automática
- Revisa manualmente los elementos problemáticos
- Considera ejecutar el script nuevamente después de corregir manualmente algunos elementos

## Contacto y Soporte

Si encuentras problemas al ejecutar los scripts o necesitas ayuda adicional, revisa:
- Los mensajes de error en la consola de pyRevit
- El informe de errores de Revit para verificar el estado actual
- La documentación de la API de Revit para funciones específicas

