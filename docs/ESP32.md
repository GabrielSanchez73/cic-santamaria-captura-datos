# Conectar el ESP32 sin dañar nada

Esta guía acompaña a `firmware/esp32_prueba_ingesta/`. El objetivo es comprobar que **el ESP32 llega al
concentrador por Wi-Fi y que sus eventos quedan guardados**, sin tocar todavía sensores ni cableado de la sala.

> **Qué se verificó y qué no.** El JSON que arma el firmware se compila y se valida contra el esquema real
> (`tests/unit/test_firmware_json.py`), y el concentrador se probó de punta a punta con `scripts/simular_nodo.py`.
> El sketch `.ino` **no se compiló con las librerías reales de Arduino/ESP32** (no estaban disponibles donde se
> preparó); solo se revisó su sintaxis con sustitutos. Si el IDE marca un error al compilar, es de esa capa y se
> corrige en una línea: copia el mensaje completo.

## Qué puede quemar un ESP32 y qué no

| Riesgo real | Cómo se evita |
|---|---|
| Voltaje externo en un pin GPIO. Los pines trabajan a **3.3 V** y **no toleran 5 V**. | Esta prueba no conecta nada a los pines. Más adelante, cualquier señal de 5 V pasa por divisor de tensión o adaptador de nivel. |
| Alimentar por USB **y** por `VIN`/`5V` a la vez. | Alimenta solo por el cable USB. |
| Cortocircuitar `3V3`, `GND` o `VIN` con un cable suelto o sobre una superficie metálica. | Déjalo sobre una superficie no conductora (la caja o una mesa de madera). |
| Conectar cargas (relés, motores, sensores) directo a un pin. | No aplica en esta prueba. Un GPIO entrega pocos mA. |
| Cargar firmware equivocado | **No quema el chip.** El ESP32 siempre conserva su cargador de arranque en ROM; un firmware malo se reemplaza cargando otro. |

El sketch de esta carpeta solo usa Wi-Fi y el LED azul que ya trae la placa (GPIO2). Con la placa sola, sin nada
conectado a sus pines, no hay forma de que dañe el hardware.

## Orden recomendado (no te saltes pasos)

### 1. Prueba en el computador, sin ESP32

```bash
python -m venv .venv
.venv\Scripts\activate            # Windows   (Linux/Mac: source .venv/bin/activate)
pip install -r requirements.txt
python -m pytest -q               # todo debe pasar
scripts\iniciar_concentrador.bat  # Linux/Mac: ./scripts/iniciar_concentrador.sh
```

En otra terminal:

```bash
python scripts/simular_nodo.py --url http://127.0.0.1:8000 --escenario completo
```

Debe terminar en `TODO COMO SE ESPERABA`. Abre `http://localhost:8000/jornada` y verás las sesiones.
(Las sesiones del escenario `corte` pasan a INCONCLUSA a los 6 minutos: es lo esperado.)

Si esto falla, **no conectes aún el ESP32**: el problema está en tu instalación del concentrador.

### 2. Comprobar que otro dispositivo llega al concentrador

1. Conecta el computador y tu celular **a la misma red Wi-Fi**.
2. Averigua la IP del computador (`ipconfig` en Windows → "IPv4"; `ip addr` en Linux).
3. Con el concentrador encendido (`scripts\iniciar_concentrador.bat`), abre en el celular
   `http://IP-DEL-COMPUTADOR:8000/health`. Debe aparecer `{"status":"ok", ...}`.

Si no carga: casi siempre es el cortafuegos de Windows (acepta el permiso para "redes privadas" cuando lo pida
Python) o una red que aísla a los clientes entre sí (redes universitarias, de invitados, de cafeterías). En ese
caso usa el punto de acceso del celular o un router propio. **Si el celular no llega, el ESP32 tampoco.**

### 3. Cargar el sketch (solo USB)

1. Arduino IDE → *Gestor de placas* → instala **esp32 by Espressif Systems**.
2. Placa: `ESP32 Dev Module`. Puerto: el que aparezca al conectar la placa (si no aparece, instala el
   controlador CP210x o CH340 según el chip de tu placa, y comprueba que el cable sea de **datos**, no solo de carga).
3. Abre `firmware/esp32_prueba_ingesta/esp32_prueba_ingesta.ino`.
4. Copia `secrets.h.example` como `secrets.h` y completa: nombre y clave del Wi-Fi (red de **2.4 GHz**) y
   `CONCENTRADOR_URL` con la IP del paso 2. `secrets.h` no se sube a git.
5. Subir. Si queda en "Connecting......", mantén pulsado el botón **BOOT** hasta que empiece a escribir.
6. Monitor serie a **115200**. Pulsa el botón **EN** (reset) para ver el arranque desde el inicio.

### 4. Resultado esperado en el monitor serie

```
Conectado. IP del ESP32: 192.168.1.37
Hora local (Colombia): 2026-10-31T12:10:03-05:00
Sesion de prueba: ESP-20261031-121003-R1
  seq 1 (EN_CURSO) intento 1 -> HTTP 201 en 38 ms
  ...
  seq 5 (COMPLETA) intento 1 -> HTTP 201 en 35 ms
RESULTADO: 5 enviados, 0 fallidos. TODO BIEN.
```

y en `http://IP-DEL-COMPUTADOR:8000/jornada` una sesión `ESP-…-R1` en *Completas* con 7.7 L.

## Si algo falla

| Síntoma | Causa probable |
|---|---|
| "No se pudo conectar al Wi-Fi" | Nombre/clave mal escritos, o red de 5 GHz. |
| "Sin hora NTP" | La red no tiene salida a internet. |
| `HTTP -1` | El ESP32 no alcanza al concentrador: IP equivocada, cortafuegos, red con aislamiento, o concentrador apagado. Repite el paso 2. |
| `HTTP 422` | Evento inválido; la respuesta nombra el campo. El concentrador también lo registra en su consola (logger `concentrador`). |
| `HTTP 409` | Se reutilizó una secuencia con otro `id_evento` dentro de la misma sesión. |
| La placa se reinicia en bucle | Alimentación insuficiente: usa otro cable/puerto USB (sin concentrador USB pasivo). |

## Límites que debes conocer

- La conexión es **HTTP sin cifrar y sin autenticación**: es para la red local del proyecto. No expongas el
  concentrador a internet tal como está.
- La prueba envía **datos inventados**; no representa lecturas reales de la sala.
- Probar así demuestra la **ruta de red y de datos** del nodo. No sustituye la validación del nodo de captura real
  (lectura del display y RFID), que es otro proyecto, ni las mediciones en la sala de ordeño.
