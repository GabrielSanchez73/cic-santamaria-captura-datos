/*
  Prueba de conexion ESP32 -> Concentrador (contrato JSON v1.0)

  QUE HACE
    1. Se conecta al Wi-Fi.
    2. Sincroniza la hora por internet (NTP) para poner marcas de tiempo correctas.
    3. Envia UNA sesion de ordeno simulada (lecturas parciales + lectura final COMPLETA) con
       POST al concentrador, e imprime cada respuesta por el monitor serie.
    4. Se queda quieto. Para repetir la prueba hay que reiniciar la placa (boton EN).

  QUE NO HACE (a proposito, para no danar nada)
    - NO configura ningun pin externo: no hay pinMode/digitalWrite salvo el LED azul incorporado
      a la placa (GPIO2). Puedes probarlo con la placa SOLA, sin nada conectado a los pines.
    - NO lee sensores, NO maneja reles ni cargas. Los datos son numeros inventados.
    - NO se queda en bucles infinitos de reenvio: maximo REINTENTOS por evento y una sola sesion.

  ANTES DE CARGARLO
    - Copia secrets.h.example como secrets.h y completa Wi-Fi y direccion del concentrador.
    - Alimenta la placa SOLO por el cable USB (nunca USB y 5V/VIN externo a la vez).
    - Herramientas > Placa: "ESP32 Dev Module" (o la que corresponda a tu ESP-32D).
    - Monitor serie a 115200 baudios.
  Guia completa: docs/ESP32.md
*/
#include <WiFi.h>
#include <HTTPClient.h>
#include <time.h>
#include "esp_system.h"      // esp_random()
#include "secrets.h"
#include "evento_json.h"

// ---- Parametros de la prueba (se pueden ajustar) ----------------------------------------------
const int      LECTURAS_PARCIALES   = 4;       // lecturas EN_CURSO antes de la final
const uint32_t PAUSA_ENTRE_LECTURAS = 5000;    // ms (en la sala real son 120 000 = 2 min)
const float    LITROS_POR_LECTURA   = 2.1f;    // el volumen enviado es ACUMULADO
const int      REINTENTOS           = 3;
const uint32_t TIMEOUT_WIFI_MS      = 20000;
const uint32_t TIMEOUT_HTTP_MS      = 8000;
const long     DESFASE_COLOMBIA_S   = -5L * 3600L; // UTC-5, sin horario de verano
const char*    ANIMAL_PRUEBA        = "2101";
const int      PIN_LED              = 2;           // LED azul incorporado; es el unico pin que se usa

char sesionId[48];
char tsInicio[32];

// ---- Utilidades -------------------------------------------------------------------------------
void parpadear(int veces, int ms = 120) {
  for (int i = 0; i < veces; i++) {
    digitalWrite(PIN_LED, HIGH); delay(ms);
    digitalWrite(PIN_LED, LOW);  delay(ms);
  }
}

// UUID versión 4 (aleatorio) con el generador por hardware del ESP32.
void uuid4(char* out /* >= 37 */) {
  uint8_t b[16];
  for (int i = 0; i < 16; i += 4) { uint32_t r = esp_random(); memcpy(b + i, &r, 4); }
  b[6] = (b[6] & 0x0F) | 0x40;   // version 4
  b[8] = (b[8] & 0x3F) | 0x80;   // variante RFC 4122
  snprintf(out, 37, "%02x%02x%02x%02x-%02x%02x-%02x%02x-%02x%02x-%02x%02x%02x%02x%02x%02x",
           b[0], b[1], b[2], b[3], b[4], b[5], b[6], b[7], b[8], b[9], b[10], b[11], b[12], b[13], b[14], b[15]);
}

// Marca de tiempo ISO 8601 con la zona explicita (el contrato exige zona horaria).
bool ahoraIso(char* out, size_t cap) {
  time_t t = time(nullptr) + DESFASE_COLOMBIA_S;
  struct tm tmv;
  gmtime_r(&t, &tmv);
  return strftime(out, cap, "%Y-%m-%dT%H:%M:%S-05:00", &tmv) > 0;
}

bool conectarWifi() {
  Serial.printf("Conectando a la red \"%s\" ...\n", WIFI_SSID);
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  uint32_t t0 = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - t0 < TIMEOUT_WIFI_MS) { delay(300); Serial.print("."); }
  Serial.println();
  if (WiFi.status() != WL_CONNECTED) { Serial.println("ERROR: no se pudo conectar al Wi-Fi (revisa nombre, clave y que sea 2.4 GHz)."); return false; }
  Serial.print("Conectado. IP del ESP32: "); Serial.println(WiFi.localIP());
  return true;
}

bool sincronizarHora() {
  configTime(0, 0, "pool.ntp.org", "time.google.com");   // el ESP32 guarda UTC; el desfase se aplica al formatear
  Serial.print("Sincronizando hora por NTP ");
  uint32_t t0 = millis();
  while (time(nullptr) < 1700000000 && millis() - t0 < 15000) { delay(300); Serial.print("."); }
  Serial.println();
  if (time(nullptr) < 1700000000) { Serial.println("ERROR: sin hora NTP (la red necesita salida a internet)."); return false; }
  char buf[32]; ahoraIso(buf, sizeof buf);
  Serial.print("Hora local (Colombia): "); Serial.println(buf);
  return true;
}

// Envia un evento. Devuelve true si el concentrador lo acepto (201) o ya lo tenia (idempotente).
bool enviar(const EventoDatos& d) {
  char json[640];
  int n = construir_evento_json(json, sizeof json, d);
  if (n < 0) { Serial.println("ERROR: datos del evento invalidos, no se envia."); return false; }

  for (int intento = 1; intento <= REINTENTOS; intento++) {
    HTTPClient http;
    http.setTimeout(TIMEOUT_HTTP_MS);
    http.begin(CONCENTRADOR_URL);
    http.addHeader("Content-Type", "application/json");
    uint32_t t0 = millis();
    int codigo = http.POST((uint8_t*)json, n);
    uint32_t ms = millis() - t0;
    String cuerpo = (codigo > 0) ? http.getString() : http.errorToString(codigo);
    http.end();

    Serial.printf("  seq %d (%s) intento %d -> HTTP %d en %lu ms\n", d.secuencia, d.estado, intento, codigo, (unsigned long)ms);
    if (codigo == 200 || codigo == 201) { parpadear(1, 60); return true; }
    Serial.print("    respuesta: "); Serial.println(cuerpo);
    // 4xx = el evento esta mal o choca con otro: reintentar no lo arregla.
    if (codigo >= 400 && codigo < 500) return false;
    delay(1000 * intento);   // fallo de red o 5xx: se reintenta con el MISMO id_evento (idempotente)
  }
  return false;
}

// ---- Programa ---------------------------------------------------------------------------------
void setup() {
  Serial.begin(115200);
  delay(1500);
  pinMode(PIN_LED, OUTPUT);       // unico pin configurado: LED incorporado
  digitalWrite(PIN_LED, LOW);
  Serial.println("\n=== Prueba ESP32 -> Concentrador (contrato v1.0) ===");
  Serial.println("Esta prueba NO usa ningun pin externo. Los datos son simulados.");

  if (!conectarWifi() || !sincronizarHora()) { parpadear(10, 80); return; }

  // Una sola sesion simulada
  char fecha[24];
  time_t t = time(nullptr) + DESFASE_COLOMBIA_S; struct tm tmv; gmtime_r(&t, &tmv);
  strftime(fecha, sizeof fecha, "%Y%m%d-%H%M%S", &tmv);
  snprintf(sesionId, sizeof sesionId, "ESP-%s-%s", fecha, ESTACION_ID);
  ahoraIso(tsInicio, sizeof tsInicio);
  Serial.printf("Sesion de prueba: %s\n", sesionId);

  int enviados = 0, fallidos = 0;
  float litros = 0;
  for (int n = 1; n <= LECTURAS_PARCIALES + 1; n++) {
    bool esFinal = (n == LECTURAS_PARCIALES + 1);
    litros += esFinal ? 1.4f : LITROS_POR_LECTURA;

    char id[37], tsLectura[32];
    uuid4(id);
    ahoraIso(tsLectura, sizeof tsLectura);

    EventoDatos d;
    d.id_evento = id;
    d.estacion_id = ESTACION_ID;
    d.sesion_id = sesionId;
    d.animal_id = ANIMAL_PRUEBA;
    d.animal_id_origen = "RFID";
    d.animal_id_confianza = 0.98f;
    d.ts_inicio = tsInicio;
    d.ts_lectura = tsLectura;
    d.secuencia = n;
    d.volumen_l = litros;
    d.duracion_s = (long)(PAUSA_ENTRE_LECTURAS / 1000) * n;
    d.estado = esFinal ? "COMPLETA" : "EN_CURSO";
    d.origen_dato = "OCR";

    if (enviar(d)) enviados++; else fallidos++;
    if (!esFinal) delay(PAUSA_ENTRE_LECTURAS);
  }

  Serial.printf("\nRESULTADO: %d enviados, %d fallidos. %s\n", enviados, fallidos,
                fallidos == 0 ? "TODO BIEN. Abre http://<IP-del-concentrador>:8000/jornada para verlo." : "Revisa los mensajes de arriba.");
  parpadear(fallidos == 0 ? 3 : 8, fallidos == 0 ? 300 : 80);
}

void loop() {
  // Intencionalmente vacio: la prueba corre una sola vez por arranque.
  delay(1000);
}
