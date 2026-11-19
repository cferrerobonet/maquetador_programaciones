# Maquetador de programaciones — instrucciones para agentes

App de escritorio (macOS y Windows, Python 3.13 + PyQt6) que toma una programación didáctica de referencia (.docx) cuya maquetación manda y devuelve copias de otras programaciones con esa maquetación, sin cambiar el contenido. Sin servidor. Releases en `github.com/cferrerobonet/maquetador_programaciones` (constante `REPO` en `src/maquetador/actualizaciones.py`). Fuente única de instrucciones: `CLAUDE.md` solo la importa.

## Forma de trabajar

- Español, con tuteo. Usuario: **CarlosFB**. Respuestas cortas; sin explicaciones ni código no pedidos.
- **Sin datos, no se implementa**: si falta un dato del que depende algo, se apunta como pendiente y se pide.
- Secretos y datos personales: barrera común (`scripts/comprobar_secretos.sh`, gancho y CI «Secretos»); reglas en la skill de usuario `barrera-secretos`.
- Nunca se sube al repositorio una programación real: las pruebas generan documentos ficticios.
- **No se compila en local**: se compila en GitHub (etiqueta `vX.Y.Z`).
- Todo listado nuevo sigue la norma de CarlosFB: buscador, 10 filas por página (5/10/15/20/50), «Limpiar filtros», cabeceras ordenables, pie «Mostrando 1–10 de N» con primera, anterior, cinco números, siguiente y última (los extremos se desactivan), fila nueva resaltada.
- Leer por rangos (`grep -n`), no releer, no listar `src/` (usar el mapa).

## Mapa

| Qué | Dónde |
| --- | --- |
| Entrada y arranque (prueba de arranque con `MAQUETADOR_PRUEBA_DE_ARRANQUE=1`) | `src/main.py` · `src/maquetador/app.py` |
| Motor: referencia, comprobación y maquetado | `src/maquetador/motor.py` · `paquete.py` |
| Ventana: referencia, listado, destino y acciones | `ui/ventana.py` |
| Tokens, hoja de estilos y tipografías Barlow | `ui/estilo.py` (misma estética que Partes de salida: `DESIGN.md`) |
| Filas, estados y modelo de la tabla · hilos del motor | `modelo.py` · `hilos.py` |
| Archivos añadidos, ruta de salida y paginación (sin interfaz) | `archivos.py` |
| Actualizaciones (GitHub, sha256) · sustitución en macOS · novedades | `actualizaciones.py` · `actualizar_mac.py` · `novedades.py` · `ui/actualizar.py` |
| Ajustes recordados · rutas y recursos | `ajustes.py` · `rutas.py` |
| Compilación | `MaquetadorProgramaciones.spec`, `scripts/build/`, `scripts/build_windows.ps1`, `.github/workflows/` |

`actualizar_mac.py` es el mismo archivo que en Partes de salida: si se corrige, se corrige en los dos.

## Comandos

```bash
PY=~/.venvs/maquetador/bin/python          # fuera de iCloud, obligatorio
$PY src/main.py                            # arrancar en local
QT_QPA_PLATFORM=offscreen $PY -m pytest -q
$PY -m ruff check src tests
QT_QPA_PLATFORM=offscreen $PY scripts/build/generar_icono.py   # rehace el icono
```

## Cada cambio publicado es una versión

SemVer en `pyproject.toml` **y** `src/maquetador/__init__.py`, entrada en `CHANGELOG.md` (es el texto de las novedades y de la release), commit con ficheros concretos, push y etiqueta `vX.Y.Z`.

## Entorno

- Intérprete en `~/.venvs/maquetador`. Dentro de iCloud, Qt deja de arrancar.
- Ajustes de este equipo: `~/Library/Application Support/MaquetadorProgramaciones` (`MAQUETADOR_DATOS` lo cambia en pruebas).
