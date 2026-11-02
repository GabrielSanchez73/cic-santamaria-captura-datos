"""Simulador del nodo de captura: envia al concentrador los mismos eventos que enviara el ESP32.

Sirve para probar TODO el camino real (red, JSON, validacion, base de datos, consulta) antes de
conectar el hardware. Si este simulador funciona y el ESP32 falla, el problema esta en el
ESP32 o en la red, no en la plataforma.

Uso (con el concentrador encendido):
    python scripts/simular_nodo.py --url http://127.0.0.1:8000 --escenario completo
    python scripts/simular_nodo.py --url http://192.168.1.50:8000 --escenario normal --intervalo 120
"""
import argparse
import sys
import time
import uuid
from datetime import datetime, timedelta, timezone

import httpx

ZONA = timezone(timedelta(hours=-5))  # hora de Colombia, con el desfase explicito que exige el contrato


def ahora():
    return datetime.now(ZONA)


def iso(dt):
    return dt.isoformat(timespec="seconds")


def evento(sesion_id, estacion, n, inicio, volumen, duracion, estado="EN_CURSO", animal="2101",
           origen_animal="RFID", confianza=0.98, origen_dato="OCR"):
    """Un evento del contrato v1.0. El flujo no se envia: lo calcula el concentrador."""
    return {
        "id_evento": str(uuid.uuid4()),
        "version_esquema": "1.0",
        "estacion_id": estacion,
        "sesion_id": sesion_id,
        "animal_id": animal,
        "animal_id_origen": origen_animal,
        "animal_id_confianza": confianza,
        "ts_inicio": iso(inicio),
        "ts_lectura": iso(ahora()),
        "secuencia": n,
        "volumen_l": volumen,
        "duracion_s": duracion,
        "flujo_l_min": None,
        "estado": estado,
        "origen_dato": origen_dato,
    }


class Nodo:
    def __init__(self, url, pausa):
        self.http = httpx.Client(base_url=url.rstrip("/"), timeout=10.0)
        self.pausa = pausa
        self.fallos = 0

    def enviar(self, ev, esperado=201, titulo=""):
        t0 = time.perf_counter()
        r = self.http.post("/v1/eventos", json=ev)
        ms = (time.perf_counter() - t0) * 1000
        ok = r.status_code == esperado
        self.fallos += 0 if ok else 1
        marca = "OK " if ok else "ERR"
        print(f"  [{marca}] {titulo or 'seq ' + str(ev['secuencia']):<34} HTTP {r.status_code} (esperado {esperado})  {ms:6.1f} ms")
        if not ok:
            print("        respuesta:", r.text[:300])
        return r

    def dormir(self):
        time.sleep(self.pausa)

    # ---------------------------------------------------------------- escenarios
    def normal(self, lecturas=5, estacion="R1", animal="2101"):
        print(f"\n== Ordeno normal en {estacion}: {lecturas} lecturas parciales + lectura final ==")
        sid = f"SIM-{ahora():%Y%m%d-%H%M%S}-{estacion}"
        inicio = ahora()
        litros = 0.0
        for n in range(1, lecturas + 1):
            litros = round(litros + 2.1, 1)
            self.enviar(evento(sid, estacion, n, inicio, litros, 120 * n, animal=animal), titulo=f"parcial {n}")
            self.dormir()
        litros = round(litros + 1.4, 1)
        r = self.enviar(evento(sid, estacion, lecturas + 1, inicio, litros, 120 * (lecturas + 1),
                               estado="COMPLETA", animal=animal), titulo="lectura final COMPLETA")
        print("  estado de la sesion segun el concentrador:", r.json().get("estado_sesion"))
        return sid

    def waikato(self, estacion="L1"):
        print(f"\n== Punto Waikato {estacion}: sin duracion y sin animal identificado ==")
        sid = f"SIM-{ahora():%Y%m%d-%H%M%S}-{estacion}"
        inicio = ahora()
        kw = dict(animal=None, origen_animal="INFERIDO_POR_POSICION", confianza=None, origen_dato="MANUAL")
        self.enviar(evento(sid, estacion, 1, inicio, 4.0, None, **kw), titulo="parcial 1 (solo volumen)")
        self.dormir()
        self.enviar(evento(sid, estacion, 2, inicio, 9.0, None, estado="COMPLETA", **kw), titulo="final (solo volumen)")
        return sid

    def reenvio(self, estacion="R2"):
        print("\n== Reenvio del mismo evento 3 veces (el nodo reintenta tras un corte de red) ==")
        sid = f"SIM-{ahora():%Y%m%d-%H%M%S}-{estacion}"
        ev = evento(sid, estacion, 1, ahora(), 2.0, 120, animal="2102")
        for i in range(3):
            self.enviar(ev, titulo=f"envio {i + 1} del mismo id_evento")
        return sid

    def invalidos(self, estacion="R3"):
        print("\n== Eventos invalidos: el servicio los rechaza con detalle y sigue funcionando ==")
        sid = f"SIM-{ahora():%Y%m%d-%H%M%S}-{estacion}"
        sin_volumen = evento(sid, estacion, 1, ahora(), 1.0, 60, animal="2103")
        del sin_volumen["volumen_l"]
        r = self.enviar(sin_volumen, esperado=422, titulo="sin volumen_l")
        print("        campo senalado:", [e["loc"][-1] for e in r.json()["detail"]])
        sin_zona = evento(sid, estacion, 1, ahora(), 1.0, 60, animal="2103")
        sin_zona["ts_lectura"] = sin_zona["ts_lectura"][:-6]
        self.enviar(sin_zona, esperado=422, titulo="ts_lectura sin zona horaria")
        ok = evento(sid, estacion, 1, ahora(), 1.0, 60, animal="2103")
        self.enviar(ok, titulo="evento valido")
        choque = evento(sid, estacion, 1, ahora(), 1.0, 60, animal="2103")  # otra id, misma secuencia
        self.enviar(choque, esperado=409, titulo="misma secuencia, otro id_evento")
        self.enviar(evento(sid, estacion, 2, ahora(), 2.0, 120, animal="2103"), titulo="sigue aceptando eventos")
        return sid

    def corte(self, estacion="R4"):
        print("\n== Sesion cortada: lecturas parciales y NUNCA llega la final ==")
        sid = f"SIM-{ahora():%Y%m%d-%H%M%S}-{estacion}"
        inicio = ahora()
        for n in range(1, 4):
            self.enviar(evento(sid, estacion, n, inicio, round(2.0 * n, 1), 120 * n, animal="2104"), titulo=f"parcial {n}")
            self.dormir()
        print("  (no se envia la lectura final). Pasado el tiempo limite el concentrador la marca INCONCLUSA.")
        return sid

    def resumen(self):
        print("\n== Jornada segun el concentrador ==")
        j = self.http.get("/v1/jornada").json()
        t = j["totales"]
        print(f"  fecha {j['fecha']}: {t['sesiones']} sesiones | completas {t['completas']} | inconclusas "
              f"{t['inconclusas']} | en curso {t['en_curso']} | litros completos {t['volumen_completas_l']}")
        m = self.http.get("/v1/metricas").json()
        if m["ingesta"].get("muestras"):
            print(f"  tiempo del servidor por ingesta: p50 {m['ingesta']['p50_ms']} ms, p95 {m['ingesta']['p95_ms']} ms")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--url", default="http://127.0.0.1:8000", help="direccion del concentrador")
    ap.add_argument("--escenario", default="completo",
                    choices=["completo", "normal", "waikato", "reenvio", "invalidos", "corte"])
    ap.add_argument("--intervalo", type=float, default=1.0,
                    help="segundos entre lecturas (en la sala real son 120; aqui 1 para probar rapido)")
    ap.add_argument("--lecturas", type=int, default=5, help="lecturas parciales del ordeno normal")
    a = ap.parse_args()

    nodo = Nodo(a.url, a.intervalo)
    try:
        salud = nodo.http.get("/health").json()
    except httpx.HTTPError as exc:
        print(f"No se pudo conectar con {a.url}: {exc}\n"
              "Revisa que el concentrador este encendido (ver README, seccion 'Arranque') y la direccion.")
        return 2
    print(f"Concentrador {a.url}: {salud['status']} (version {salud['version']})")

    escenarios = {
        "normal": lambda: nodo.normal(a.lecturas),
        "waikato": nodo.waikato,
        "reenvio": nodo.reenvio,
        "invalidos": nodo.invalidos,
        "corte": nodo.corte,
    }
    if a.escenario == "completo":
        for nombre in ("normal", "waikato", "reenvio", "invalidos", "corte"):
            escenarios[nombre]()
    else:
        escenarios[a.escenario]()
    nodo.resumen()
    print("\nRESULTADO:", "TODO COMO SE ESPERABA" if nodo.fallos == 0 else f"{nodo.fallos} respuesta(s) inesperada(s)")
    return 1 if nodo.fallos else 0


if __name__ == "__main__":
    sys.exit(main())
