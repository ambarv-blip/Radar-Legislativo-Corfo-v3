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

Notas sobre el cliente HTTP (revisión posterior — bloqueo 403):
camara.cl rechazaba las consultas con HTTP 403 porque la petición se veía
como tráfico de bot: User-Agent no realista, sin Accept/Accept-Language,
sin Referer ni cookies de sesión. Se usa ahora una requests.Session() que
primero visita la página de listado (como haría un usuario real navegando
al detalle de un proyecto) para obtener cookies, y luego reutiliza esa
sesión — con headers de navegador y Referer — para pedir la ficha de
tramitación.
"""
import datetime
import logging
import re
import time

import requests

logger = logging.getLogger(__name__)

TRAMITACION_URL = "https://www.camara.cl/legislacion/ProyectosDeLey/tramitacion.aspx"
LISTADO_URL = "https://www.camara.cl/legislacion/ProyectosDeLey/proyectos_ley.aspx"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "es-CL,es;q=0.9,en-US;q=0.8,en;q=0.7",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
}

TIMEOUT = 12
INTENTOS_MAX = 2  # 1 intento inicial + 1 reintento ante error transitorio/403
ESPERA_ENTRE_INTENTOS = 1.5  # segundos, se multiplica por el número de intento

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


def _nueva_sesion():
    """Crea una sesión de requests y la 'calienta' visitando el listado de
    proyectos, igual que un navegador real que llega a la ficha de
    tramitación navegando desde el buscador. Esto entrega cookies de
    sesión/WAF y un Referer legítimo para el siguiente pedido."""
    session = requests.Session()
    session.headers.update(HEADERS)
    try:
        session.get(LISTADO_URL, timeout=TIMEOUT)
    except requests.RequestException as e:
        # No es fatal: seguimos con la sesión sin cookies previas.
        logger.warning("No se pudo precargar cookies desde %s: %s", LISTADO_URL, e)
    return session


def consultar_fuente_oficial(boletin, prm_id):
    """Consulta la ficha de tramitación de un boletín en camara.cl.

    Reintenta ante errores transitorios (timeout, error de conexión, 403 —
    que a veces se resuelve renovando cookies de sesión) hasta
    INTENTOS_MAX veces. No reintenta ante 404, ya que un boletín/prmID
    inválido no se arregla reintentando.
    """
    params = {"prmID": prm_id, "prmBOLETIN": boletin}
    ultimo_error = None
    ultimo_status = None

    for intento in range(1, INTENTOS_MAX + 1):
        session = _nueva_sesion()
        logger.info(
            "Consultando fuente oficial (boletín=%s, prmID=%s, intento=%d/%d): %s",
            boletin, prm_id, intento, INTENTOS_MAX, TRAMITACION_URL,
        )
        try:
            resp = session.get(
                TRAMITACION_URL,
                params=params,
                headers={"Referer": LISTADO_URL},
                timeout=TIMEOUT,
                allow_redirects=True,
            )
        except requests.Timeout as e:
            ultimo_error = f"Timeout tras {TIMEOUT}s consultando la fuente oficial"
            logger.warning("Timeout en intento %d/%d para boletín %s: %s", intento, INTENTOS_MAX, boletin, e)
        except requests.ConnectionError as e:
            ultimo_error = f"Error de conexión con la fuente oficial: {str(e)[:300]}"
            logger.warning("Error de conexión en intento %d/%d para boletín %s: %s", intento, INTENTOS_MAX, boletin, e)
        except requests.RequestException as e:
            ultimo_error = f"{type(e).__name__}: {str(e)[:300]}"
            logger.warning("Error de red en intento %d/%d para boletín %s: %s", intento, INTENTOS_MAX, boletin, e)
        else:
            ultimo_status = resp.status_code
            logger.info("Respuesta HTTP %s desde %s", resp.status_code, resp.url)

            if resp.status_code == 200:
                return {
                    "exito": True, "codigo_http": 200, "url_consultada": resp.url,
                    "texto": resp.text, "error": None,
                }
            if resp.status_code == 403:
                ultimo_error = "HTTP 403 — la fuente oficial rechazó la solicitud (bloqueo anti-bot/WAF)"
                logger.warning("Bloqueo 403 en intento %d/%d para boletín %s", intento, INTENTOS_MAX, boletin)
                # Muchos WAF devuelven una pista (referencia, motivo) en el cuerpo del 403;
                # se deja truncado en el log para no inundarlo pero sí poder diagnosticar.
                if resp.text:
                    logger.warning("Cuerpo de la respuesta 403 (primeros 500 chars): %s", resp.text[:500])
            elif resp.status_code == 404:
                ultimo_error = "HTTP 404 — no se encontró la ficha de tramitación (revisar prmID/boletín)"
                logger.warning("404 en intento %d/%d para boletín %s (prmID=%s)", intento, INTENTOS_MAX, boletin, prm_id)
                break  # un 404 no se arregla reintentando
            else:
                ultimo_error = f"HTTP {resp.status_code}"
                logger.warning("Respuesta inesperada %s en intento %d/%d para boletín %s", resp.status_code, intento, INTENTOS_MAX, boletin)

        if intento < INTENTOS_MAX:
            time.sleep(ESPERA_ENTRE_INTENTOS * intento)

    return {
        "exito": False, "codigo_http": ultimo_status, "url_consultada": TRAMITACION_URL,
        "texto": None, "error": ultimo_error,
    }


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
        logger.warning("No hay prmID conocido para el boletín %s", boletin)
        return {"resultado": "error_tecnico", "error": f"No hay prmID conocido para el boletín {boletin}",
                "estado_oficial": None, "ultima_actuacion": None, "url_consultada": None}

    fuente = consultar_fuente_oficial(boletin, prm_id)
    if not fuente["exito"]:
        return {"resultado": "error_tecnico", "error": fuente["error"],
                "estado_oficial": None, "ultima_actuacion": None,
                "url_consultada": fuente["url_consultada"]}

    estado_oficial = extraer_estado_resumen(fuente["texto"])
    ultima_actuacion = extraer_ultima_actuacion(fuente["texto"])

    if estado_oficial is None:
        # HTTP 200 pero no se pudo extraer el Estado: la estructura del HTML
        # cambió, o la página no es la ficha esperada. No se debe pisar el
        # estado guardado con None — se reporta como error técnico explícito.
        logger.error(
            "No se pudo extraer 'Estado' del HTML recibido para boletín %s (prmID=%s) — "
            "posible cambio de estructura en camara.cl", boletin, prm_id,
        )
        return {
            "resultado": "error_tecnico",
            "error": "La fuente oficial respondió, pero no se pudo extraer el Estado del HTML "
                     "(posible cambio de estructura en camara.cl).",
            "estado_oficial": None, "ultima_actuacion": None,
            "url_consultada": fuente["url_consultada"],
        }

    if (estado_actual_guardado or "").strip() == (estado_oficial or "").strip():
        resultado = "sin_cambios"
    else:
        resultado = "nuevo_evento"

    logger.info("Monitoreo boletín %s: resultado=%s estado_oficial=%r", boletin, resultado, estado_oficial)

    return {
        "resultado": resultado,
        "error": None,
        "estado_oficial": estado_oficial,
        "ultima_actuacion": ultima_actuacion,
        "url_consultada": fuente["url_consultada"],
        "fecha_deteccion": datetime.datetime.utcnow().isoformat(),
    }
