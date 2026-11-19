# Diseño: Maquetador de programaciones

Hereda por completo la estética de Partes de salida (`../../PARTES DE SALIDA (python)/PARTES DE SALIDA - CÓDIGO FUENTE/DESIGN.md`): tokens verde EPLA y dorado en claro y oscuro, Barlow y Barlow Condensed, tarjetas redondeadas de 12 px y botón principal verde.

- Fuente de verdad del código: `src/maquetador/ui/estilo.py` (tokens `CLARO` y `OSCURO`, hoja de estilos). Todo color sale de `T[...]`.
- Una sola ventana en tarjetas, en el orden del flujo: referencia → programaciones → destino y acciones. Mínimo 980 × 700.
- Estados con color: Cumple y Maquetada en verde, No cumple en ámbar, Error en rojo, el resto en gris. La fila nueva o actualizada se resalta en dorado unos segundos.
- Listado y paginación: norma de CarlosFB para todo listado (ver `AGENTS.md`).
- Icono: documento con escuadra dorada sobre verde EPLA, generado con QPainter (`scripts/build/generar_icono.py`).
