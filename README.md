# Plataforma de Ingesta, Datos y Visualización — CIC Santa María del Puyón

Capa de software del sistema de registro de producción individual de leche del CIC Santa María del Puyón (Sopó, Cundinamarca), Universidad de La Salle.

**Autor:** Gabriel Alejandro Sánchez Mora
**Programa:** Ingeniería de Software, Universidad de La Salle
**Modalidad:** Proyecto de investigación — Modalidad de Grado I, 2026-II
**Directores:** Mary Rubiano y Jhon Méndez

---

## Qué resuelve este módulo

En el CIC Santa María del Puyón la medición de litros y tiempo que despliega la unidad Allflex MC201DF permanece en pantalla solo hasta que entra el siguiente animal. El registro se hace a mano, en papel, y se digita una vez por semana en el software de gestión ganadera de la finca.

Este repositorio contiene la capa que recibe, valida, consolida, persiste y expone ese dato. **Empieza donde termina el nodo de captura**, que es un proyecto distinto a cargo de otros integrantes del equipo.

### Alcance de este repositorio

- API de ingesta de eventos de ordeño y validación contra el contrato de datos.
- Control de idempotencia para evitar registros duplicados por reenvío.
- Consolidación de lecturas parciales en sesiones de ordeño.
- Motor de estados del registro: completa, inconclusa o estimada.
- Persistencia local en el concentrador, con operación sin conexión permanente.
- Consulta de la jornada de ordeño.

### Fuera del alcance de este repositorio

- Lectura del display por reconocimiento óptico.
- Identificación del animal por radiofrecuencia.
- Montaje físico, cableado y alimentación eléctrica en la sala de ordeño.
- Sustitución del software de gestión ganadera de la finca, que sigue operando como sistema de análisis del hato.

---

## Contrato de datos

Es la única interfaz entre el nodo de captura y esta plataforma. Versión 1.0, acordada por el equipo el 4 de septiembre de 2026. La especificación completa está en `docs/contrato/`.

```json
{
  "id_evento": "9f2c1e40-3b7a-4c11-9d5e-8a1f0b6d2e77",
  "version_esquema": "1.0",
  "estacion_id": "R1",
  "sesion_id": "SES-20260911-R1-004",
  "animal_id": "2101",
  "animal_id_origen": "RFID",
  "animal_id_confianza": 0.98,
  "ts_inicio": "2026-09-11T06:12:00-05:00",
  "ts_lectura": "2026-09-11T06:16:00-05:00",
  "secuencia": 2,
  "volumen_l": 8.4,
  "duracion_s": 240,
  "flujo_l_min": null,
  "estado": "EN_CURSO",
  "origen_dato": "OCR"
}
```

### Campos

| Campo | Tipo | Obligatorio | Lo genera | Para qué sirve |
|---|---|---|---|---|
| `id_evento` | UUID | Sí | Nodo | Identificador único del envío. Evita duplicados cuando el nodo reintenta tras un corte. |
| `version_esquema` | texto | Sí | Nodo | Permite cambiar el formato sin romper lo ya almacenado. |
| `estacion_id` | texto | Sí | Nodo | Punto de ordeño donde se tomó el dato (R1 a R5, L1 a L5). |
| `sesion_id` | texto | Sí | Nodo | Agrupa las lecturas parciales de una misma vaca en un mismo ordeño. |
| `animal_id` | texto | No | Nodo | Chapeta de cuatro dígitos. Puede venir nulo si la identificación falló. |
| `animal_id_origen` | enum | Sí | Nodo | `RFID`, `INFERIDO_POR_POSICION` o `MANUAL`. |
| `animal_id_confianza` | decimal 0-1 | No | Nodo | Por debajo del umbral, el registro va a revisión. |
| `ts_inicio` | ISO 8601 | Sí | Nodo | Inicio del ordeño del animal, con zona horaria explícita. |
| `ts_lectura` | ISO 8601 | Sí | Nodo | Momento de esta lectura. |
| `secuencia` | entero | Sí | Nodo | Número de lectura parcial dentro de la sesión. |
| `volumen_l` | decimal | Sí | Nodo | Litros acumulados hasta esta lectura. |
| `duracion_s` | entero | No | Nodo | Segundos transcurridos. Nulo en los puntos Waikato. |
| `flujo_l_min` | decimal | No | Plataforma | No se transmite: lo calcula el concentrador. |
| `estado` | enum | Sí | Nodo / Plataforma | `EN_CURSO`, `COMPLETA`, `INCONCLUSA` o `ESTIMADA`. |
| `origen_dato` | enum | Sí | Nodo | `OCR`, `MANUAL` o `ESTIMADO`. Deja trazable de dónde salió el número. |

### Reglas de operación

- Se envía una lectura parcial cada dos minutos durante el ordeño, más una lectura final con estado `COMPLETA`.
- Si la sesión se corta sin lectura final, la plataforma la marca `INCONCLUSA`.
- El nodo nunca descarta un evento: si no hay red local, lo guarda y lo reintenta con el mismo `id_evento`.
- Un `animal_id` nulo o de baja confianza no bloquea el guardado. El dato de producción es irrecuperable; la asignación del animal se corrige después.
- Toda marca de tiempo lleva zona horaria explícita. La finca ordeña de madrugada y una diferencia de zona cambia el día del registro.

---

## Estructura del repositorio

```
.
├── app/
│   ├── api/v1/          Endpoints: ingesta (/v1/eventos), jornada, métricas.
│   ├── api/vista.py     Página HTML de la jornada (/jornada).
│   ├── core/            Configuración, manejo de zona horaria y métricas.
│   ├── db/              Sesión de base de datos (SQLite en modo WAL).
│   ├── models/          Entidades persistidas: sesión, lectura, animal, estación.
│   ├── schemas/         Modelos de validación del contrato de datos.
│   └── services/        Lógica de dominio: ingesta, consolidación, estados, jornada.
├── deploy/              Servicio systemd para arranque automático.
├── docs/
│   ├── contrato/        Contrato de datos, reglas y ejemplos validados por las pruebas.
│   └── ESP32.md         Guía de conexión segura del ESP32.
├── firmware/            Sketch de prueba del ESP32 y su verificación en el computador.
├── scripts/             Simulador del nodo, medición de latencia, arranque.
├── tests/               Unitarias e integración (incluye casos de falla).
├── .github/workflows/   Integración continua.
└── requirements.txt
```

### Separación por capas

El flujo de un evento atraviesa el sistema en este orden:

1. `api/v1` recibe el envío del nodo de captura.
2. `schemas` valida el contrato y rechaza lo malformado con detalle del error.
3. `services/ingesta` aplica idempotencia y guarda la lectura; `services/consolidacion` decide el estado de la sesión.
4. `models` y `db` persisten el resultado; `services/jornada` lo presenta.

La lógica de dominio vive en `services` y no depende de la capa HTTP, de modo que sea verificable sin levantar el servidor.

### Reglas de consolidación y estados

- `volumen_l` es el volumen **acumulado**; el de la sesión es el de la lectura con mayor `secuencia`. Nunca se suman lecturas.
- Precedencia de estados: `COMPLETA` > `ESTIMADA` > `INCONCLUSA` > `EN_CURSO`.
- Una sesión sin lectura final y sin lecturas nuevas durante `SESION_TIMEOUT_SEG` pasa a `INCONCLUSA`. Se mide con la hora de **recepción** en el concentrador, no con el reloj del nodo.
- `INCONCLUSA` es reversible: si llegan las lecturas que el nodo guardó durante un corte, la sesión se reabre o se completa.
- Una sesión `INCONCLUSA` nunca se suma como producción completa: su volumen se informa aparte como **mínimo**.
- Sin duración (puntos Waikato) no se calcula flujo.
- Al arrancar, el concentrador revisa de inmediato las sesiones que quedaron abiertas (por ejemplo tras un corte de energía).

---

## Arranque

Requisitos: Python 3.13.

```bash
python -m venv .venv
.venv\Scripts\activate        # Windows  (Linux/Mac: source .venv/bin/activate)
pip install -r requirements.txt
python -m pytest -q
scripts\iniciar_concentrador.bat   # Linux/Mac: ./scripts/iniciar_concentrador.sh
```

Escucha en `0.0.0.0:8000` para que otros dispositivos de la red local (el ESP32) lleguen a él. Configuración opcional en `.env` (ver `.env.example`). En Linux, `deploy/concentrador.service` lo deja arrancando solo al encender el equipo.

| Ruta | Para qué |
|---|---|
| `POST /v1/eventos` | Ingesta de un evento del contrato. |
| `GET /v1/jornada?fecha=AAAA-MM-DD` | Sesiones del día, agrupadas por estado, con totales. |
| `GET /v1/sesiones/{sesion_id}` | Una sesión con todas sus lecturas. |
| `GET /jornada` | La jornada en una página web (se actualiza sola). |
| `GET/DELETE /v1/metricas` | Tiempos de respuesta del servidor (percentiles) y su reinicio. |
| `GET /health` | Estado del servicio y de la base de datos. |
| `GET /docs` | Documentación interactiva de la API. |

## Probar sin hardware

```bash
python scripts/simular_nodo.py --escenario completo     # emula al ESP32 por HTTP real
python scripts/medir_latencia.py --ingestas 200 --consultas 100
```

`medir_latencia.py` escribe eventos de prueba: úsalo con una base aparte (`DATABASE_URL=sqlite:///./medicion.db`). Las cifras que entregue dependen del equipo y de la red; para un resultado del proyecto hay que medirlas en el concentrador real y en la red de la sala.

## Conectar el ESP32

Ver [`docs/ESP32.md`](docs/ESP32.md): orden de pasos, riesgos de hardware y solución de problemas. El sketch envía datos simulados y no usa ningún pin externo.

---

## Estrategia de ramificación

Se sigue un flujo tipo Gitflow simplificado.

| Rama | Propósito |
|---|---|
| `main` | Código estable. Solo recibe integraciones desde `develop` al cierre de cada sprint. |
| `develop` | Rama de integración. Es la base de todas las ramas de trabajo. |
| `feature/*` | Una rama por tarea del cronograma, nombrada con el identificador de la tarea. |

Convención de nombres: `feature/G-02-endpoint-ingesta`, `feature/G-05-modelo-datos`.

Cada rama de trabajo sale de `develop` y regresa a `develop` mediante pull request. `main` no recibe commits directos.

---

## Stack tecnológico

| Capa | Tecnología |
|---|---|
| API | Python con FastAPI y Pydantic v2 |
| Persistencia local | SQLite (modo WAL, `synchronous=FULL`) vía SQLAlchemy |
| Pruebas | pytest y httpx |

Previsto y **aún no incluido**: persistencia centralizada en PostgreSQL y empaquetado en Docker.

---

## Estado del proyecto

Plan según el cronograma de sprints del proyecto.

| Sprint | Ventana | Objetivo | Tareas |
|---|---|---|---|
| S1 | 10 – 23 sep | Contrato y modelo de datos | G-01, G-05, G-02 |
| S2 | 24 sep – 7 oct | Ingesta robusta: valida, no duplica, acepta datos incompletos | G-03, G-04 y G-07 |
| S3 | 8 – 21 oct | Sesiones consolidadas, estados y persistencia | G-06, G-08, G-13 |
| S4 | 22 oct – 1 nov | Consulta de la jornada y medición de desempeño | G-19, G-22 |

El código de las tareas G-06, G-08, G-13, G-19 y G-22 está en la rama `feature/sprints-3-4-definitiva`.

Pendiente: validar con el nodo de captura real, medir el desempeño en la red de la sala (G-22 se mide con `scripts/medir_latencia.py`) y las tareas de los sprints posteriores (mapa real de medidores, corrección de animal, exportación, entre otras).

---

## Licencia y uso

Proyecto académico desarrollado en el marco de la Modalidad de Grado I de la Universidad de La Salle. Los datos de producción del hato son propiedad del CIC Santa María del Puyón.
