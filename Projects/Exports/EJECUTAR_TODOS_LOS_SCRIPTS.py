"""
Script maestro para ejecutar todos los scripts de corrección de errores de Revit.
Este script ejecuta automáticamente todos los scripts de corrección en el orden correcto.

INSTRUCCIONES:
1. Abre Revit con el modelo cargado
2. Abre pyRevit
3. Ejecuta este script desde pyRevit
"""

import sys
import os

# Obtener la ruta del directorio actual donde está este script
# Este script está en Projects\Exports
# Si se ejecuta desde el botón, usar la variable global EXPORTS_DIR si está disponible
script_dir = None
try:
    if 'EXPORTS_DIR' in globals():
        exports_dir_path = globals()['EXPORTS_DIR']
        if os.path.exists(exports_dir_path) and os.path.exists(os.path.join(exports_dir_path, 'fix_revit_errors.py')):
            script_dir = exports_dir_path
except:
    pass

if script_dir is None:
    # Intentar obtener la ruta del archivo actual
    try:
        current_file = os.path.abspath(__file__)
        script_dir = os.path.dirname(current_file)
    except:
        # Si __file__ no está disponible, buscar desde el directorio de trabajo actual
        script_dir = os.getcwd()
    
    # Verificar que estamos en la carpeta correcta (Exports)
    # Si no estamos en Exports, buscar la carpeta correcta
    if not os.path.basename(script_dir) == 'Exports':
        # Buscar la carpeta Exports desde la ubicación actual
        current = script_dir
        found = False
        for _ in range(10):  # Buscar hasta 10 niveles arriba
            exports_path = os.path.join(current, 'Exports')
            if os.path.exists(exports_path) and os.path.exists(os.path.join(exports_path, 'fix_revit_errors.py')):
                script_dir = exports_path
                found = True
                break
            parent = os.path.dirname(current)
            if parent == current:
                break
            current = parent
        
        # Si aún no se encontró, buscar desde el directorio de trabajo
        if not found:
            current = os.getcwd()
            for _ in range(10):
                exports_path = os.path.join(current, 'Exports')
                if os.path.exists(exports_path) and os.path.exists(os.path.join(exports_path, 'fix_revit_errors.py')):
                    script_dir = exports_path
                    break
                parent = os.path.dirname(current)
                if parent == current:
                    break
                current = parent

# Rutas de los scripts a ejecutar
scripts = [
    os.path.join(script_dir, 'fix_revit_errors.py'),
    os.path.join(script_dir, 'fix_stair_errors.py'),
    os.path.join(script_dir, 'fix_remaining_errors.py'),
]

print("=" * 70)
print("SCRIPT MAESTRO - CORRECCIÓN DE ERRORES DE REVIT")
print("=" * 70)
print("\nEste script ejecutará automáticamente todos los scripts de corrección.")
print("Asegúrate de tener una copia de seguridad del modelo antes de continuar.\n")

# Preguntar confirmación
try:
    respuesta = input("¿Deseas continuar? (s/n): ").lower().strip()
    if respuesta != 's' and respuesta != 'si' and respuesta != 'yes' and respuesta != 'y':
        print("\nOperación cancelada por el usuario.")
        sys.exit(0)
except:
    # Si no hay input disponible (ejecución automática), continuar
    print("\nContinuando con la ejecución automática...\n")

# Ejecutar cada script
for i, script_path in enumerate(scripts, 1):
    script_name = os.path.basename(script_path)
    
    if not os.path.exists(script_path):
        print("\n" + "=" * 70)
        print("ERROR: No se encontró el script: {}".format(script_path))
        print("=" * 70)
        continue
    
    print("\n" + "=" * 70)
    print("EJECUTANDO SCRIPT {}/{}: {}".format(i, len(scripts), script_name))
    print("=" * 70)
    
    try:
        # Leer y ejecutar el script (compatible con Python 2 y 3)
        # Usar modo universal newlines para manejar automáticamente \r\n
        try:
            # Python 3 - usar 'rU' o 'r' con newline=None
            with open(script_path, 'rU', encoding='utf-8') as f:
                script_content = f.read()
        except (TypeError, ValueError):
            # Python 2 - usar codecs con modo universal
            import codecs
            with codecs.open(script_path, 'rU', encoding='utf-8') as f:
                script_content = f.read()
        except:
            # Fallback: leer en modo binario y decodificar
            with open(script_path, 'rb') as f:
                script_content = f.read().decode('utf-8')
        
        # Normalizar finales de línea (eliminar \r para evitar errores)
        script_content = script_content.replace('\r\n', '\n').replace('\r', '\n')
        
        # Ejecutar el script
        exec(script_content)
        
        print("\n✓ Script {} ejecutado correctamente".format(script_name))
        
    except Exception as e:
        print("\n✗ ERROR al ejecutar {}: {}".format(script_name, str(e)))
        print("Continuando con el siguiente script...")
        continue

print("\n" + "=" * 70)
print("EJECUCIÓN COMPLETADA")
print("=" * 70)
print("\nTodos los scripts han sido ejecutados.")
print("Por favor, revisa el informe de errores de Revit para verificar los resultados.")
print("\nNOTA: Algunos errores pueden requerir ajustes manuales.")
print("Consulta el archivo INSTRUCCIONES.md para más detalles.")
print("=" * 70)

