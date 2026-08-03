# -*- coding: utf-8 -*-
"""
monitor/monitor_engine.py
============================
Motor de monitoreo reusable. Consulta la fuente oficial (camara.cl),
extrae Estado y última actuación, y compara contra el estado guardado.

Hereda directamente la lógica validada en prototipo_afide.py (etapa
anterior), generalizada para cualquier boletín con su prmID conocido.

LIMITACIÓN DOCUMENTADA: el prmID sigue siendo un valor fijo por boletín
(ver PRM_ID_CONOCIDOS) hasta que se confirme un método automático para
obtenerlo (ver Informe_Obtencion_prmID.md de la etapa anterior).
"""
import requests
import re
import datetime

HEADERS = {"User-Agent": "Mozilla/5.0 (observatorio-legislativo-corfo)"}
TIMEOUT = 12

PRM_ID_CONOCIDOS = {
    # Confirmados en la columna "Link seguimiento" del Excel original de Ambar
    # (SEGUIMIENTO_PROYECTOS_DE_LEY.xlsx) — no son un supuesto, vienen de ahí.
    "16889-05": 17500,
    "16441-19": 17011,
    "16686-19": 17258,
    "17064-08": 17680,
    "16799-05": 17413,
    "16817-05": 17428,
    "17169-04": 17792,
    "11608-09": 12126,
    "16182-12": 16745,
    "17777-05": 18426,
}


def obtener_prm_id(boletin):
    return PRM_ID_CONOCIDOS.get(boletin)


def consultar_fuente_oficial(boletin, prm_id):
    url = "https://www.camara.cl/legislacion/ProyectosDeLey/tramitacion.aspx"
    params = {"prmID": prm_id, "prmBOLETIN": boletin}
    try:
        resp = requests.get(url, params=params, headers=HEADERS, timeout=TIMEOUT)
        return {
            "exito": resp.status_code == 200,
            "codigo_http": resp.status_code,
            "url_consultada": resp.url,
            "texto": resp.text if resp.status_code == 200 else None,
            "error": None if resp.status_code == 200 else f"HTTP {resp.status_code}",
        }
    except Exception as e:
        return {"exito": False, "codigo_http": None, "url_consultada": url,
                "texto": None, "error": f"{type(e).__name__} — {str(e)[:300]}"}


def extraer_estado_resumen(html):
    if not html:
        return None
    m = re.search(r"Estado\s*</[^>]+>\s*(?:<[^>]+>\s*)*([^<]{3,150})<", html, re.IGNORECASE)
    return m.group(1).strip() if m else None


def extraer_ultima_actuacion(html):
    if not html:
        return None
    filas = []
    for fila_html in re.findall(r"<tr[^>]*>(.*?)</tr>", html, re.IGNORECASE | re.DOTALL):
        celdas = re.findall(r"<td[^>]*>(.*?)</td>", fila_html, re.IGNORECASE | re.DOTALL)
        if len(celdas) >= 4:
            limpio = [re.sub("<[^>]+>", "", c).strip() for c in celdas]
            if limpio[0] and re.search(r"\d{4}|\w{3}\.", limpio[0]):
                filas.append({"fecha": limpio[0], "sesion": limpio[1], "etapa": limpio[2],
                               "sub_etapa": limpio[3] if len(limpio) > 3 else None})
    return filas[-1] if filas else None


def ejecutar_monitoreo(boletin, estado_actual_guardado):
    """
    Punto de entrada único usado por el backend.
    Devuelve un dict con: resultado ('sin_cambios'|'nuevo_evento'|'error_tecnico'),
    estado_oficial, ultima_actuacion, url_consultada, error.
    """
    prm_id = obtener_prm_id(boletin)
    if prm_id is None:
        return {"resultado": "error_tecnico", "error": f"No hay prmID conocido para el boletín {boletin}",
                "estado_oficial": None, "ultima_actuacion": None, "url_consultada": None}

    fuente = consultar_fuente_oficial(boletin, prm_id)
    if not fuente["exito"]:
        return {"resultado": "error_tecnico", "error": fuente["error"],
                "estado_oficial": None, "ultima_actuacion": None,
                "url_consultada": fuente["url_consultada"]}

    estado_oficial = extraer_estado_resumen(fuente["texto"])
    ultima_actuacion = extraer_ultima_actuacion(fuente["texto"])

    if (estado_actual_guardado or "").strip() == (estado_oficial or "").strip():
        resultado = "sin_cambios"
    else:
        resultado = "nuevo_evento"

    return {
        "resultado": resultado,
        "error": None,
        "estado_oficial": estado_oficial,
        "ultima_actuacion": ultima_actuacion,
        "url_consultada": fuente["url_consultada"],
        "fecha_deteccion": datetime.datetime.utcnow().isoformat(),
    }
