# Maquetador de programaciones

App de escritorio (macOS y Windows) que devuelve programaciones didácticas con la maquetación de una programación de referencia, sin cambiar su contenido.

## Uso

1. Elige la programación de referencia (.docx): su maquetación manda.
2. Añade las programaciones a maquetar, con el botón o arrastrando archivos y carpetas. Se comprueban solas.
3. Elige el destino: junto a cada original (con el sufijo « (maquetada)») o en una carpeta. Nunca se sobrescribe nada.
4. Pulsa «Maquetar las que no cumplen» o «Maquetar seleccionadas».

La app busca sola versiones nuevas en GitHub, comprueba la suma del archivo y, en macOS, se sustituye donde está instalada.

## Desarrollo

```bash
PY=~/.venvs/maquetador/bin/python
$PY src/main.py
QT_QPA_PLATFORM=offscreen $PY -m pytest -q
$PY -m ruff check src tests
```

Se compila en GitHub al subir una etiqueta `vX.Y.Z` (macOS con chip Apple en DMG y Windows en .zip portable). Más en `AGENTS.md` y `DESIGN.md`.
