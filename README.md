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
│   ├── api/v1/          Endpoints HTTP. Punto de entrada de la ingesta.
│   ├── core/            Configuración, constantes y utilidades transversales.
│   ├── db/              Sesión de base de datos y migraciones.
│   ├── models/          Entidades persistidas: sesión, lectura, animal, estación.
│   ├── schemas/         Modelos de validación del contrato de datos.
│   └── services/        Lógica de dominio: idempotencia, consolidación, estados.
├── docs/
│   └── contrato/        Especificación versionada del contrato de datos.
├── scripts/             Utilidades de desarrollo y carga de datos de prueba.
├── tests/
│   ├── unit/            Pruebas de servicios y validaciones.
│   └── integration/     Pruebas de los casos de falla: corte de luz, sin señal, ID dudoso.
├── .github/workflows/   Integración continua.
├── .gitignore
├── requirements.txt
└── README.md
```

### Separación por capas

El flujo de un evento atraviesa el sistema en este orden:

1. `api/v1` recibe el envío del nodo de captura.
2. `schemas` valida el contrato y rechaza lo malformado con detalle del error.
3. `services` aplica idempotencia, consolida las lecturas parciales de la sesión y decide el estado del registro.
4. `models` y `db` persisten el resultado.

La lógica de dominio vive en `services` y no depende de la capa HTTP, de modo que sea verificable sin levantar el servidor.

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
| API | Python con FastAPI |
| Persistencia local | SQLite en el concentrador |
| Persistencia centralizada | PostgreSQL |
| Empaquetado | Docker |

La ejecución en contenedor permite desarrollar y probar sin depender de la llegada del hardware.

---

## Estado del proyecto

**Sprint 1 — del 10 al 23 de septiembre de 2026.** Demostración el jueves 24.

| Tarea | Descripción | Estado |
|---|---|---|
| G-01 | Contrato de datos acordado y publicado | Cerrado |
| G-05 | Modelo de datos: sesión, lectura parcial, animal, estación | En curso |
| G-02 | Endpoint `POST /v1/eventos` en el concentrador | Pendiente |

Criterio de cierre del sprint: un evento JSON enviado con `curl` queda almacenado en la base local.

### Sprints siguientes

| Sprint | Ventana | Objetivo |
|---|---|---|
| S2 | 24 sep – 7 oct | Ingesta robusta: valida, no duplica, acepta datos incompletos |
| S3 | 8 oct – 21 oct | Concentrador montado y sesiones consolidadas |
| S4 | 22 oct – 1 nov | Consulta de la jornada y medición de desempeño |

---

## Licencia y uso

Proyecto académico desarrollado en el marco de la Modalidad de Grado I de la Universidad de La Salle. Los datos de producción del hato son propiedad del CIC Santa María del Puyón.
