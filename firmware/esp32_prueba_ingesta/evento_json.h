// Construye el JSON del contrato v1.0 (15 campos). Es C++ puro, sin dependencias de Arduino,
// para poder probarlo en el computador contra el esquema real del concentrador
// (ver tests/unit/test_firmware_json.py).
#ifndef EVENTO_JSON_H
#define EVENTO_JSON_H

#include <stdio.h>
#include <string.h>

struct EventoDatos {
  const char* id_evento;            // UUID v4
  const char* estacion_id;          // R1..R5 o L1..L5
  const char* sesion_id;
  const char* animal_id;            // 4 digitos, o nullptr si no hay animal identificado
  const char* animal_id_origen;     // RFID | INFERIDO_POR_POSICION | MANUAL
  float animal_id_confianza;        // 0..1; valor negativo = nulo
  const char* ts_inicio;            // ISO 8601 con zona, p. ej. 2026-10-31T11:45:00-05:00
  const char* ts_lectura;
  int secuencia;                    // >= 1
  float volumen_l;                  // litros ACUMULADOS de la sesion (no incremento)
  long duracion_s;                  // segundos; valor negativo = nulo (punto Waikato)
  const char* estado;               // EN_CURSO | COMPLETA | INCONCLUSA | ESTIMADA
  const char* origen_dato;          // OCR | MANUAL | ESTIMADO
};

// Los textos del contrato son identificadores simples: se rechaza cualquier caracter que
// obligue a escapar (comillas, barra invertida, control) en vez de producir un JSON roto.
static inline bool texto_seguro(const char* s) {
  if (s == nullptr || s[0] == '\0') return false;
  for (; *s; ++s) {
    unsigned char c = (unsigned char)*s;
    if (c < 0x20 || c == '"' || c == '\\' || c >= 0x7F) return false;
  }
  return true;
}

// Escribe el JSON en buf. Devuelve su longitud, o -1 si algun dato no es valido o no cabe.
static inline int construir_evento_json(char* buf, size_t cap, const EventoDatos& d) {
  if (!buf || cap == 0) return -1;
  if (!texto_seguro(d.id_evento) || !texto_seguro(d.estacion_id) || !texto_seguro(d.sesion_id) ||
      !texto_seguro(d.animal_id_origen) || !texto_seguro(d.ts_inicio) || !texto_seguro(d.ts_lectura) ||
      !texto_seguro(d.estado) || !texto_seguro(d.origen_dato)) return -1;
  if (d.animal_id != nullptr && !texto_seguro(d.animal_id)) return -1;
  if (d.secuencia < 1 || d.volumen_l < 0.0f) return -1;

  char animal[24];
  if (d.animal_id) snprintf(animal, sizeof animal, "\"%s\"", d.animal_id);
  else snprintf(animal, sizeof animal, "null");

  char confianza[16];
  if (d.animal_id_confianza >= 0.0f) snprintf(confianza, sizeof confianza, "%.2f", (double)d.animal_id_confianza);
  else snprintf(confianza, sizeof confianza, "null");

  char duracion[16];
  if (d.duracion_s >= 0) snprintf(duracion, sizeof duracion, "%ld", d.duracion_s);
  else snprintf(duracion, sizeof duracion, "null");

  // El separador decimal siempre es '.', porque snprintf de Arduino/ESP32 usa la configuracion "C".
  int n = snprintf(buf, cap,
      "{\"id_evento\":\"%s\",\"version_esquema\":\"1.0\",\"estacion_id\":\"%s\",\"sesion_id\":\"%s\","
      "\"animal_id\":%s,\"animal_id_origen\":\"%s\",\"animal_id_confianza\":%s,"
      "\"ts_inicio\":\"%s\",\"ts_lectura\":\"%s\",\"secuencia\":%d,\"volumen_l\":%.2f,"
      "\"duracion_s\":%s,\"flujo_l_min\":null,\"estado\":\"%s\",\"origen_dato\":\"%s\"}",
      d.id_evento, d.estacion_id, d.sesion_id, animal, d.animal_id_origen, confianza,
      d.ts_inicio, d.ts_lectura, d.secuencia, (double)d.volumen_l, duracion, d.estado, d.origen_dato);
  if (n < 0 || (size_t)n >= cap) return -1;
  return n;
}

#endif
