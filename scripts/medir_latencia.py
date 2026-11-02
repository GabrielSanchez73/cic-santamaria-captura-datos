"""Mide la latencia de ingesta y de consulta del concentrador (G-22) y la guarda en un CSV.

Mide el tiempo que ve el CLIENTE (red local + servidor). El tiempo solo del servidor sale de
GET /v1/metricas y se imprime al final para compararlos.

IMPORTANTE: escribe eventos de prueba en la base. Para no mezclarlos con datos reales, levanta el
concentrador con otra base antes de medir, por ejemplo:
    DATABASE_URL=sqlite:///./medicion.db uvicorn app.main:app --host 0.0.0.0 --port 8000

Uso:
    python scripts/medir_latencia.py --url http://192.168.1.50:8000 --ingestas 200 --consultas 100
"""
import argparse
import csv
import statistics
import sys
import time
import uuid
from datetime import datetime, timedelta, timezone

import httpx

ZONA = timezone(timedelta(hours=-5))


def percentil(ordenados, p):
    k = max(0, -(-len(ordenados) * p // 100) - 1)
    return ordenados[int(k)]


def resumen(nombre, ms):
    o = sorted(ms)
    return {
        "operacion": nombre, "n": len(o), "media_ms": round(statistics.mean(o), 2),
        "p50_ms": round(percentil(o, 50), 2), "p95_ms": round(percentil(o, 95), 2),
        "p99_ms": round(percentil(o, 99), 2), "max_ms": round(o[-1], 2),
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--url", default="http://127.0.0.1:8000")
    ap.add_argument("--ingestas", type=int, default=200)
    ap.add_argument("--consultas", type=int, default=100)
    ap.add_argument("--salida", default="latencia.csv")
    a = ap.parse_args()

    http = httpx.Client(base_url=a.url.rstrip("/"), timeout=10.0)
    try:
        http.get("/health").raise_for_status()
    except httpx.HTTPError as exc:
        print(f"No se pudo conectar con {a.url}: {exc}")
        return 2
    http.delete("/v1/metricas")

    lote = datetime.now(ZONA).strftime("%H%M%S")
    inicio = datetime.now(ZONA)
    filas, ingesta, consulta = [], [], []

    for i in range(a.ingestas):
        sesion = f"MED-{lote}-{i // 6:04d}"          # 6 lecturas por sesion, como un ordeno real
        ev = {
            "id_evento": str(uuid.uuid4()), "version_esquema": "1.0", "estacion_id": f"R{1 + (i // 6) % 5}",
            "sesion_id": sesion, "animal_id": f"{2000 + (i // 6) % 90:04d}", "animal_id_origen": "RFID",
            "animal_id_confianza": 0.97, "ts_inicio": inicio.isoformat(timespec="seconds"),
            "ts_lectura": datetime.now(ZONA).isoformat(timespec="seconds"), "secuencia": i % 6 + 1,
            "volumen_l": round(2.0 * (i % 6 + 1), 1), "duracion_s": 120 * (i % 6 + 1), "flujo_l_min": None,
            "estado": "COMPLETA" if i % 6 == 5 else "EN_CURSO", "origen_dato": "OCR",
        }
        t0 = time.perf_counter()
        r = http.post("/v1/eventos", json=ev)
        ms = (time.perf_counter() - t0) * 1000
        if r.status_code != 201:
            print("ingesta inesperada:", r.status_code, r.text[:200])
        ingesta.append(ms)
        filas.append(["ingesta", i + 1, round(ms, 3), r.status_code])

    for i in range(a.consultas):
        t0 = time.perf_counter()
        r = http.get("/v1/jornada")
        ms = (time.perf_counter() - t0) * 1000
        consulta.append(ms)
        filas.append(["consulta", i + 1, round(ms, 3), r.status_code])

    with open(a.salida, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["operacion", "n", "milisegundos", "http"])
        w.writerows(filas)

    print(f"\nLatencia medida desde el cliente ({a.url}) — detalle en {a.salida}")
    print(f"{'operacion':<10}{'n':>6}{'media':>9}{'p50':>9}{'p95':>9}{'p99':>9}{'max':>9}  (ms)")
    for nombre, datos in (("ingesta", ingesta), ("consulta", consulta)):
        if datos:
            s = resumen(nombre, datos)
            print(f"{nombre:<10}{s['n']:>6}{s['media_ms']:>9}{s['p50_ms']:>9}{s['p95_ms']:>9}{s['p99_ms']:>9}{s['max_ms']:>9}")
    m = http.get("/v1/metricas").json()
    print("\nSolo servidor (GET /v1/metricas):")
    for g in ("ingesta", "consulta"):
        d = m[g]
        if d.get("muestras"):
            print(f"  {g:<9} p50 {d['p50_ms']} ms | p95 {d['p95_ms']} ms | max {d['max_ms']} ms")
    return 0


if __name__ == "__main__":
    sys.exit(main())
