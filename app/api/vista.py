"""Vista web de la jornada: una pagina HTML simple, sin dependencias de frontend."""
from datetime import date
from html import escape
from typing import Optional

from fastapi import APIRouter, Depends, Query
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.core.tiempo import hoy_local
from app.db.session import get_db
from app.services import jornada as servicio

router = APIRouter(tags=["vista"])

_ESTILO = """
body{font-family:system-ui,Arial,sans-serif;margin:1.5rem;color:#222;max-width:1100px}
h1{font-size:1.3rem;margin:0 0 .25rem} h2{font-size:1.05rem;margin:1.5rem 0 .4rem}
.nota{color:#555;font-size:.85rem} table{border-collapse:collapse;width:100%;font-size:.9rem}
th,td{border-bottom:1px solid #ddd;padding:.35rem .5rem;text-align:left} th{background:#f2f2f2}
td.n{text-align:right} .tot{display:flex;gap:1rem;flex-wrap:wrap;margin:.8rem 0}
.tot div{border:1px solid #ccc;border-radius:6px;padding:.4rem .8rem}
.COMPLETA{color:#1a7f37}.INCONCLUSA{color:#b35900}.ESTIMADA{color:#6639ba}.EN_CURSO{color:#0969da}
.aviso{background:#fff8e1;border:1px solid #f0d58c;padding:.4rem .7rem;border-radius:6px;font-size:.85rem}
"""

_SECCIONES = (
    ("en_curso", "En curso", "Todavia estan llegando lecturas."),
    ("completas", "Completas", "Recibieron la lectura final del ordeno."),
    ("inconclusas", "Inconclusas",
     "El ordeno se corto sin lectura final. El volumen es lo ultimo que se supo, NO la produccion total."),
    ("estimadas", "Estimadas", "El valor se declaro estimado, no medido."),
)


def _num(valor, decimales=1) -> str:
    return "-" if valor is None else f"{valor:.{decimales}f}"


def _tabla(filas) -> str:
    if not filas:
        return '<p class="nota">Sin registros.</p>'
    cab = ("Sesion", "Estacion", "Animal", "Inicio", "Ultima lectura", "Lecturas", "Volumen (L)", "Duracion (s)",
           "Flujo (L/min)")
    out = ["<table><tr>" + "".join(f"<th>{c}</th>" for c in cab) + "</tr>"]
    for f in filas:
        faltan = f["secuencias_faltantes"]
        lecturas = str(f["n_lecturas"]) + (f" (faltan {', '.join(map(str, faltan))})" if faltan else "")
        vol = _num(f["volumen_l"]) + (" (parcial)" if f["volumen_es_parcial"] else "")
        celdas = [
            escape(f["sesion_id"]), escape(f["estacion_id"]), escape(f["animal_id"] or "sin identificar"),
            escape((f["ts_inicio"] or "-")[11:19]), escape((f["ts_ultima_lectura"] or "-")[11:19]),
            escape(lecturas), escape(vol), escape(_num(f["duracion_s"], 0)), escape(_num(f["flujo_l_min"], 2)),
        ]
        out.append("<tr>" + "".join(f"<td>{c}</td>" for c in celdas) + "</tr>")
    out.append("</table>")
    return "".join(out)


def _pagina(datos: dict) -> str:
    t = datos["totales"]
    tarjetas = "".join(
        f"<div><b>{escape(str(v))}</b><br><span class='nota'>{escape(k)}</span></div>"
        for k, v in (
            ("sesiones", t["sesiones"]), ("completas", t["completas"]), ("inconclusas", t["inconclusas"]),
            ("estimadas", t["estimadas"]), ("en curso", t["en_curso"]),
            ("litros completos", t["volumen_completas_l"]),
        )
    )
    cuerpo = []
    for clave, titulo, nota in _SECCIONES:
        estado = {"en_curso": "EN_CURSO", "completas": "COMPLETA", "inconclusas": "INCONCLUSA",
                  "estimadas": "ESTIMADA"}[clave]
        cuerpo.append(
            f"<h2 class='{estado}'>{titulo} ({len(datos[clave])})</h2><p class='nota'>{escape(nota)}</p>"
            + _tabla(datos[clave])
        )
    aviso = ""
    if t["inconclusas"]:
        aviso = (f"<p class='aviso'>Hay {t['inconclusas']} sesion(es) inconclusa(s): al menos "
                 f"{t['volumen_inconcluso_minimo_l']} L se ordenaron pero no estan en el total de litros completos.</p>")
    return (
        "<!doctype html><html lang='es'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1'>"
        "<meta http-equiv='refresh' content='30'><title>Jornada de ordeno</title>"
        f"<style>{_ESTILO}</style></head><body>"
        f"<h1>Jornada de ordeno &mdash; {escape(datos['fecha'])}</h1>"
        "<p class='nota'>CIC Santa Maria del Puyon. La pagina se actualiza sola cada 30 s.</p>"
        "<form method='get'><label>Dia: <input type='date' name='fecha' "
        f"value='{escape(datos['fecha'])}'></label> <button>Ver</button></form>"
        f"<div class='tot'>{tarjetas}</div>{aviso}{''.join(cuerpo)}</body></html>"
    )


@router.get("/jornada", response_class=HTMLResponse, include_in_schema=False)
def vista_jornada(fecha: Optional[date] = Query(default=None), db: Session = Depends(get_db)):
    return HTMLResponse(_pagina(servicio.jornada(db, fecha or hoy_local())))
