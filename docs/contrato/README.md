# Contrato de datos

Especificación versionada de la interfaz entre el nodo de captura y la plataforma.

- `v1.0` — acordada por el equipo el 4 de septiembre de 2026.

Cualquier cambio en el esquema exige subir `version_esquema` y avisar al equipo del nodo
de captura antes de desplegar, porque los dos proyectos dependen de este archivo.

## Ejemplos

En `ejemplos/` hay eventos reales del contrato. `tests/unit/test_contrato_ejemplos.py` los valida contra
el esquema vigente en cada ejecución de las pruebas, de modo que no quedan desactualizados sin que nadie lo note.

- `ordeno_allflex_completo.json`: una sesión con dos lecturas parciales y una final `COMPLETA`.
- `ordeno_waikato_sin_animal.json`: punto Waikato, sin duración y sin animal identificado.

## Reglas que conviene recordar al integrar el nodo

| Tema | Regla |
|---|---|
| `volumen_l` | Litros **acumulados** de la sesión hasta esa lectura. El concentrador toma el de la mayor `secuencia`; nunca suma lecturas. |
| `secuencia` | Empieza en 1 y crece de uno en uno dentro de la sesión. Un mismo `(sesion_id, secuencia)` con otro `id_evento` responde 409. |
| Reenvío | El mismo `id_evento` enviado otra vez responde 201 y **no** duplica la lectura. El nodo debe reintentar con el mismo `id_evento`. |
| Zona horaria | `ts_inicio` y `ts_lectura` con desfase explícito (`-05:00`). Sin zona responde 422. `ts_lectura` no puede ser anterior a `ts_inicio`. |
| `flujo_l_min` | Lo calcula el concentrador; el nodo envía `null`. |
| Campo desconocido | Un campo que no esté en el contrato responde 422 (`extra="forbid"`): así se detecta un nombre mal escrito. |
| Corte | Sin lectura final `COMPLETA`, la sesión pasa a `INCONCLUSA` tras `SESION_TIMEOUT_SEG` sin recibir lecturas. Si luego llegan lecturas guardadas por el nodo durante el corte, se reabre o se completa. |

## Respuestas de `POST /v1/eventos`

| HTTP | Significado | Qué hace el nodo |
|---|---|---|
| 201 | Aceptado (o ya recibido antes) | Borra el evento de su cola |
| 409 | Conflicto de secuencia con otro evento | No reintentar: es un error de numeración |
| 422 | Evento inválido; el cuerpo indica el campo | No reintentar: corregir el evento |
| 5xx / sin respuesta | Falla del concentrador o de la red | Conservar y reintentar con el mismo `id_evento` |
