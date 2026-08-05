# -*- coding: utf-8 -*-
"""
monitor/monitor_engine.py
============================
Motor de monitoreo reusable. Consulta el estado oficial de un proyecto de
ley por su boletín y compara contra el estado guardado en la base de datos.

FUENTE PRIMARIA — Datos Abiertos oficiales de la Cámara de Diputadas y
Diputados (servicio WSLegislativo, método retornarProyectoLey). Es un
servicio HTTP diseñado explícitamente para integraciones de terceros, a
diferencia de leer el HTML público pensado para navegadores.
Ver `consultar_open_data()` / `extraer_desde_open_data()`.

FUENTE DE RESPALDO — scraping del HTML de tramitacion.aspx (la
implementación original de esta etapa, endurecida contra bloqueos 403 en
una revisión anterior). Solo se usa si Datos Abiertos no está disponible o
no entrega un Estado utilizable, y queda registrado en logs y en el campo
"fuente" del resultado cuál de las dos fue la que realmente respondió.
Ver `consultar_fuente_oficial_scraper()` / sección "RESPALDO" más abajo.

LIMITACIÓN DE VERIFICACIÓN (importante, léela antes de tocar el parser de
Open Data): el entorno donde se escribió esta integración no tiene salida
a internet hacia opendata.camara.cl (política de egress del sandbox, no un
bloqueo del sitio), así que no fue posible obtener en vivo un ejemplo real
de la respuesta de retornarProyectoLey. El nombre del método viene
indicado por quien pidió este cambio; el parámetro y los nombres de campo
están basados en la convención documentada de los servicios WSLegislativo/
WSDiputado de la Cámara (prefijo "prm", catálogos con sub-nodo "Valor",
etc.), pero no están 100% confirmados. Por eso `extraer_desde_open_data`
es tolerante a variantes de nombre y registra el XML crudo cuando no
reconoce los campos esperados — al probar contra el servicio real, revisa
los logs si el resultado no es el esperado; puede ser cuestión de agregar
un nombre de campo candidato, no de rehacer la integración.
"""
import datetime
import logging
import re
import time
import xml.etree.ElementTree as ET

import requests

logger = logging.getLogger(__name__)

TIMEOUT = 12
INTENTOS_MAX = 2  # 1 intento inicial + 1 reintento ante error transitorio
ESPERA_ENTRE_INTENTOS = 1.5  # segundos, se multiplica por el número de intento

PRM_ID_CONOCIDOS = {
    # Confirmados en la columna "Link seguimiento" del Excel original de Ambar
    # (SEGUIMIENTO_PROYECTOS_DE_LEY.xlsx) — no son un supuesto, vienen de ahí.
    # Solo se usan para el RESPALDO por scraping (tramitacion.aspx necesita
    # prmID además del boletín); Open Data consulta directo por boletín.
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


# =====================================================================
# FUENTE PRIMARIA: Datos Abiertos oficiales (WSLegislativo.retornarProyectoLey)
# =====================================================================

OPEN_DATA_BASE_URL = "https://opendata.camara.cl/camaradiputados/WServices/WSLegislativo.asmx"
OPEN_DATA_METODO = "retornarProyectoLey"

# Nombres de parámetro candidatos para el número de boletín. Se prueban en
# orden hasta obtener una respuesta HTTP 200 con contenido; no se pudo
# confirmar en vivo cuál es el correcto (ver nota del módulo).
OPEN_DATA_PARAMS_CANDIDATOS = ["prmNumeroBoletin", "prmBoletin", "prmBOLETIN"]

OPEN_DATA_HEADERS = {
    # Cliente honesto: esta es una llamada a un servicio HTTP público
    # pensado para integraciones, no scraping de una página para navegador.
    "User-Agent": "RadarLegislativoCorfo-Observatorio/1.0 (+https://github.com/ambarv-blip/Radar-Legislativo-Corfo-v3)",
    "Accept": "text/xml, application/xml",
}


def _tag_local(elemento):
    """Nombre de la etiqueta sin prefijo de namespace ('{ns}Tag' -> 'Tag')."""
    return elemento.tag.rsplit("}", 1)[-1]


def _buscar_elemento(raiz, *nombres_candidatos):
    """Busca en todo el árbol el primer elemento cuyo nombre local (sin
    namespace) coincida, sin distinguir mayúsculas, con alguno de los
    candidatos. Necesario porque el esquema exacto de Open Data no pudo
    verificarse en vivo (ver nota del módulo)."""
    candidatos = {c.lower() for c in nombres_candidatos}
    for el in raiz.iter():
        if _tag_local(el).lower() in candidatos:
            return el
    return None


def _texto_de(raiz, *nombres_candidatos):
    """Como _buscar_elemento, pero devuelve el texto útil: el propio texto
    del elemento, o si viene vacío, el de un sub-nodo típico de catálogo
    (Valor/Descripcion/Nombre), como usan los servicios de la Cámara para
    representar valores de listas (ej. <EstadoTramitacion><Valor>...))."""
    el = _buscar_elemento(raiz, *nombres_candidatos)
    if el is None:
        return None
    texto = (el.text or "").strip()
    if texto:
        return texto
    for sub in el:
        if _tag_local(sub).lower() in ("valor", "descripcion", "nombre"):
            if sub.text and sub.text.strip():
                return sub.text.strip()
    return None


def consultar_open_data(boletin):
    """Consulta retornarProyectoLey en el servicio oficial WSLegislativo.

    Prueba los nombres de parámetro candidatos en orden hasta obtener un
    HTTP 200 con cuerpo no vacío. No reintenta ante error de red más que
    una vez por candidato (INTENTOS_MAX), igual que el respaldo HTML.
    """
    for nombre_param in OPEN_DATA_PARAMS_CANDIDATOS:
        url = f"{OPEN_DATA_BASE_URL}/{OPEN_DATA_METODO}"
        params = {nombre_param: boletin}
        ultimo_error = None
        ultimo_status = None

        for intento in range(1, INTENTOS_MAX + 1):
            logger.info(
                "Consultando Open Data oficial (%s, param=%s, boletín=%s, intento=%d/%d)",
                OPEN_DATA_METODO, nombre_param, boletin, intento, INTENTOS_MAX,
            )
            try:
                resp = requests.get(url, params=params, headers=OPEN_DATA_HEADERS, timeout=TIMEOUT)
            except requests.Timeout as e:
                ultimo_error = f"Timeout tras {TIMEOUT}s consultando Open Data"
                logger.warning("Timeout consultando Open Data (intento %d/%d): %s", intento, INTENTOS_MAX, e)
            except requests.RequestException as e:
                ultimo_error = f"Error de conexión con Open Data: {str(e)[:300]}"
                logger.warning("Error de conexión consultando Open Data (intento %d/%d): %s", intento, INTENTOS_MAX, e)
            else:
                ultimo_status = resp.status_code
                logger.info("Open Data respondió HTTP %s desde %s", resp.status_code, resp.url)
                if resp.status_code == 200 and resp.content:
                    return {
                        "exito": True, "codigo_http": 200, "url_consultada": resp.url,
                        "contenido": resp.content, "param_usado": nombre_param, "error": None,
                    }
                ultimo_error = f"HTTP {resp.status_code} de Open Data"
                if resp.status_code == 403 and resp.text:
                    logger.warning("Cuerpo del 403 de Open Data (primeros 500 chars): %s", resp.text[:500])
                # 500/400 típicamente significa "nombre de parámetro incorrecto" en ASMX:
                # no tiene sentido reintentar con el mismo, se prueba el siguiente candidato.
                if resp.status_code in (400, 500):
                    break

            if intento < INTENTOS_MAX:
                time.sleep(ESPERA_ENTRE_INTENTOS * intento)

        logger.warning("Candidato de parámetro '%s' no funcionó para Open Data: %s", nombre_param, ultimo_error)

    return {
        "exito": False, "codigo_http": ultimo_status,
        "url_consultada": f"{OPEN_DATA_BASE_URL}/{OPEN_DATA_METODO}",
        "contenido": None, "param_usado": None, "error": ultimo_error,
    }


def extraer_desde_open_data(contenido_xml, boletin):
    """Mapea la respuesta XML de retornarProyectoLey al mismo formato
    interno que produce el respaldo HTML: {estado_oficial, ultima_actuacion}.
    Devuelve None si no logra reconocer ningún campo esperado (ver nota de
    verificación al inicio del módulo)."""
    try:
        raiz = ET.fromstring(contenido_xml)
    except ET.ParseError as e:
        logger.error("XML de Open Data no válido para boletín %s: %s", boletin, e)
        return None

    estado = _texto_de(raiz, "EstadoTramitacion", "SituacionActual", "Estado")

    ultima_actuacion = None
    tramites = [el for el in raiz.iter() if _tag_local(el).lower() in ("tramite", "tramitecamara", "tramitesenado")]
    if tramites:
        ultimo = tramites[-1]
        ultima_actuacion = {
            "fecha": _texto_de(ultimo, "Fecha"),
            "sesion": _texto_de(ultimo, "Sesion", "NumeroSesion"),
            "etapa": _texto_de(ultimo, "Etapa", "EtapaTramitacion") or estado,
            "sub_etapa": _texto_de(ultimo, "Descripcion", "SubEtapa", "Detalle"),
        }

    if estado is None and ultima_actuacion is None:
        logger.warning(
            "Open Data respondió pero no se reconoció ningún campo esperado para boletín %s. "
            "XML crudo (primeros 800 chars) — usar esto para ajustar los nombres candidatos "
            "en extraer_desde_open_data: %s",
            boletin, ET.tostring(raiz, encoding="unicode")[:800],
        )
        return None

    return {"estado_oficial": estado, "ultima_actuacion": ultima_actuacion}


# =====================================================================
# RESPALDO: scraping del HTML público (solo si Open Data no está disponible
# o no entrega un Estado utilizable)
# =====================================================================

TRAMITACION_URL = "https://www.camara.cl/legislacion/ProyectosDeLey/tramitacion.aspx"
LISTADO_URL = "https://www.camara.cl/legislacion/ProyectosDeLey/proyectos_ley.aspx"

SCRAPER_HEADERS = {
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


def _nueva_sesion_scraper():
    """Crea una sesión de requests y la 'calienta' visitando el listado de
    proyectos, igual que un navegador real que llega a la ficha de
    tramitación navegando desde el buscador. Esto entrega cookies de
    sesión/WAF y un Referer legítimo para el siguiente pedido."""
    session = requests.Session()
    session.headers.update(SCRAPER_HEADERS)
    try:
        session.get(LISTADO_URL, timeout=TIMEOUT)
    except requests.RequestException as e:
        # No es fatal: seguimos con la sesión sin cookies previas.
        logger.warning("No se pudo precargar cookies desde %s: %s", LISTADO_URL, e)
    return session


def consultar_fuente_oficial_scraper(boletin, prm_id):
    """Consulta la ficha de tramitación de un boletín en camara.cl (HTML).

    Reintenta ante errores transitorios (timeout, error de conexión, 403 —
    que a veces se resuelve renovando cookies de sesión) hasta
    INTENTOS_MAX veces. No reintenta ante 404, ya que un boletín/prmID
    inválido no se arregla reintentando.
    """
    params = {"prmID": prm_id, "prmBOLETIN": boletin}
    ultimo_error = None
    ultimo_status = None

    for intento in range(1, INTENTOS_MAX + 1):
        session = _nueva_sesion_scraper()
        logger.info(
            "Consultando respaldo HTML (boletín=%s, prmID=%s, intento=%d/%d): %s",
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
            ultimo_error = f"Timeout tras {TIMEOUT}s consultando el respaldo HTML"
            logger.warning("Timeout en intento %d/%d para boletín %s: %s", intento, INTENTOS_MAX, boletin, e)
        except requests.ConnectionError as e:
            ultimo_error = f"Error de conexión con el respaldo HTML: {str(e)[:300]}"
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
                ultimo_error = "HTTP 403 — camara.cl rechazó la solicitud (bloqueo anti-bot/WAF)"
                logger.warning("Bloqueo 403 en intento %d/%d para boletín %s", intento, INTENTOS_MAX, boletin)
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


# =====================================================================
# Orquestación: Open Data primero, respaldo HTML solo si hace falta
# =====================================================================

def _comparar_y_construir(estado_oficial, ultima_actuacion, estado_actual_guardado, url_consultada, fuente):
    if (estado_actual_guardado or "").strip() == (estado_oficial or "").strip():
        resultado = "sin_cambios"
    else:
        resultado = "nuevo_evento"

    logger.info("Monitoreo: resultado=%s estado_oficial=%r fuente=%s", resultado, estado_oficial, fuente)

    return {
        "resultado": resultado,
        "error": None,
        "estado_oficial": estado_oficial,
        "ultima_actuacion": ultima_actuacion,
        "url_consultada": url_consultada,
        "fuente": fuente,
        "fecha_deteccion": datetime.datetime.utcnow().isoformat(),
    }


def ejecutar_monitoreo(boletin, estado_actual_guardado):
    """
    Punto de entrada único usado por el backend.
    Devuelve un dict con: resultado ('sin_cambios'|'nuevo_evento'|'error_tecnico'),
    estado_oficial, ultima_actuacion, url_consultada, fuente, error.

    Intenta primero el servicio oficial de Datos Abiertos (WSLegislativo).
    Si no está disponible, o responde pero no se puede extraer un Estado
    utilizable, cae al respaldo por scraping del HTML público — solo si
    existe un prmID conocido para ese boletín (ver PRM_ID_CONOCIDOS).
    """
    # 1) Fuente oficial preferida: Datos Abiertos
    od = consultar_open_data(boletin)
    if od["exito"]:
        datos = extraer_desde_open_data(od["contenido"], boletin)
        if datos and datos["estado_oficial"]:
            return _comparar_y_construir(
                datos["estado_oficial"], datos["ultima_actuacion"], estado_actual_guardado,
                od["url_consultada"],
                fuente="Datos Abiertos oficiales — Cámara de Diputadas y Diputados (WSLegislativo.retornarProyectoLey)",
            )
        logger.warning(
            "Open Data respondió pero no entregó un Estado utilizable para boletín %s; se prueba el respaldo HTML.",
            boletin,
        )
        error_open_data = "Open Data respondió pero no se pudo interpretar el Estado del proyecto"
    else:
        logger.warning(
            "Open Data no disponible para boletín %s (%s); se prueba el respaldo HTML.", boletin, od["error"],
        )
        error_open_data = od["error"]

    # 2) Respaldo: scraping del HTML público (solo si Open Data falló)
    prm_id = obtener_prm_id(boletin)
    if prm_id is None:
        return {
            "resultado": "error_tecnico",
            "error": f"Datos Abiertos falló ({error_open_data}) y no hay prmID conocido para boletín "
                     f"{boletin} para usar el respaldo HTML.",
            "estado_oficial": None, "ultima_actuacion": None,
            "url_consultada": od["url_consultada"], "fuente": None,
        }

    fuente_scraper = consultar_fuente_oficial_scraper(boletin, prm_id)
    if not fuente_scraper["exito"]:
        return {
            "resultado": "error_tecnico",
            "error": f"Datos Abiertos falló ({error_open_data}) y el respaldo HTML también falló "
                     f"({fuente_scraper['error']}).",
            "estado_oficial": None, "ultima_actuacion": None,
            "url_consultada": fuente_scraper["url_consultada"], "fuente": None,
        }

    estado_oficial = extraer_estado_resumen(fuente_scraper["texto"])
    ultima_actuacion = extraer_ultima_actuacion(fuente_scraper["texto"])

    if estado_oficial is None:
        logger.error(
            "No se pudo extraer 'Estado' del HTML de respaldo para boletín %s (prmID=%s) — "
            "posible cambio de estructura en camara.cl", boletin, prm_id,
        )
        return {
            "resultado": "error_tecnico",
            "error": "Ni Datos Abiertos ni el respaldo HTML entregaron un Estado utilizable "
                     "(posible cambio de estructura en camara.cl).",
            "estado_oficial": None, "ultima_actuacion": None,
            "url_consultada": fuente_scraper["url_consultada"], "fuente": None,
        }

    return _comparar_y_construir(
        estado_oficial, ultima_actuacion, estado_actual_guardado,
        fuente_scraper["url_consultada"],
        fuente="camara.cl (HTML, respaldo — Datos Abiertos no disponible)",
    )
