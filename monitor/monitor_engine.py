# -*- coding: utf-8 -*-
"""
monitor/monitor_engine.py
============================
Motor de monitoreo. Consulta la fuente oficial de un proyecto de ley y
devuelve la lista de eventos NUEVOS (para hacer crecer el historial) más
el estado actual, si cambió.

ARQUITECTURA (revisión post-validación con datos reales): las dos fuentes
disponibles hoy NO son primaria/respaldo — cada una aporta información que
la otra no tiene, y ambas se consultan siempre:

- `consultar_fuente_oficial_scraper()` / `extraer_estado_resumen()` (HTML de
  tramitacion.aspx): ÚNICA fuente confirmada que expone el "Estado" real y
  legible tal como lo muestra camara.cl (ej. "Segundo trámite constitucional
  / Senado"). Usa la sesión endurecida contra bloqueos 403 (headers de
  navegador + cookies de sesión) de una revisión anterior.

- `consultar_open_data()` / `extraer_votaciones_open_data()` (Open Data
  oficial, WSLegislativo.retornarProyectoLey): se comprobó contra una
  respuesta real que este servicio NO expone un "estado actual" — solo
  metadata del proyecto y una lista de votaciones (<Votaciones>
  <VotacionProyectoLey>). Tratar "la votación más reciente" como si fuera
  "el estado actual" (diseño anterior) es lo que causaba estados
  incorrectos: puede haber meses de trámite sin una votación de por medio.
  Ahora cada votación se trata por lo que es — un evento histórico propio,
  deduplicado por su <Id> real del servicio — y se agrega al timeline sin
  pretender representar el estado vigente.

`ejecutar_monitoreo()` combina ambas: el HTML decide si cambió el "Estado";
Open Data aporta votaciones nuevas como eventos independientes. Ninguna de
las dos fuentes bloquea a la otra — si una falla, la otra sigue aportando.

FUENTES INVESTIGADAS Y DESCARTADAS POR FALTA DE EVIDENCIA (no implementadas
por no poder verificarlas en vivo desde este entorno — ver más abajo):
- Métodos hipotéticos retornarTramitaciones / retornarTramites /
  retornarHistoria / retornarEventos / retornarMovimientos: no aparecen
  como operaciones reales de ningún servicio de opendata.camara.cl.
- Datos Abiertos del Senado (tramitacion.senado.cl/datos-abiertos-legislativos):
  confirmado que existe (en operación desde 2012, entrega XML de proyectos
  con movimiento), pero no fue posible obtener su endpoint/esquema exacto
  — este entorno no tiene salida a internet hacia hosts externos (política
  de egress del sandbox). Punto de extensión natural para cuando se pueda
  verificar: un adaptador nuevo con la misma forma que
  extraer_votaciones_open_data() (lista de eventos con id_externo estable),
  sumado en ejecutar_monitoreo() sin tocar el resto del flujo.
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
    # Los necesita tramitacion.aspx (HTML) además del boletín; Open Data
    # consulta directo por boletín, sin prmID.
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
# Fuente A — HTML de camara.cl: única fuente confirmada del "Estado" real
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
    if prm_id is None:
        return {"exito": False, "codigo_http": None, "url_consultada": TRAMITACION_URL,
                "texto": None, "error": f"No hay prmID conocido para boletín {boletin}"}

    params = {"prmID": prm_id, "prmBOLETIN": boletin}
    ultimo_error = None
    ultimo_status = None

    for intento in range(1, INTENTOS_MAX + 1):
        session = _nueva_sesion_scraper()
        logger.info(
            "Consultando estado en camara.cl (boletín=%s, prmID=%s, intento=%d/%d): %s",
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
            ultimo_error = f"Timeout tras {TIMEOUT}s consultando camara.cl"
            logger.warning("Timeout en intento %d/%d para boletín %s: %s", intento, INTENTOS_MAX, boletin, e)
        except requests.ConnectionError as e:
            ultimo_error = f"Error de conexión con camara.cl: {str(e)[:300]}"
            logger.warning("Error de conexión en intento %d/%d para boletín %s: %s", intento, INTENTOS_MAX, boletin, e)
        except requests.RequestException as e:
            ultimo_error = f"{type(e).__name__}: {str(e)[:300]}"
            logger.warning("Error de red en intento %d/%d para boletín %s: %s", intento, INTENTOS_MAX, boletin, e)
        else:
            ultimo_status = resp.status_code
            logger.info("camara.cl respondió HTTP %s desde %s", resp.status_code, resp.url)

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
    """El texto del campo 'Estado' tal como lo muestra camara.cl (ej.
    'Segundo trámite constitucional / Senado'). Es la única fuente
    disponible hoy para el estado real — ver nota del módulo."""
    if not html:
        return None
    m = re.search(r"Estado\s*</[^>]+>\s*(?:<[^>]+>\s*)*([^<]{3,150})<", html, re.IGNORECASE)
    return m.group(1).strip() if m else None


def extraer_ultima_actuacion(html):
    """Última fila de la tabla de tramitación del HTML — se usa solo para
    describir el evento de 'cambio de estado' cuando extraer_estado_resumen
    detecta una diferencia; no se usa para deduplicar (no tiene un id
    estable en el HTML, a diferencia de las votaciones de Open Data)."""
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
# Fuente B — Open Data oficial (WSLegislativo.retornarProyectoLey):
# votaciones estructuradas, cada una un evento propio del timeline
# =====================================================================

OPEN_DATA_BASE_URL = "https://opendata.camara.cl/camaradiputados/WServices/WSLegislativo.asmx"
OPEN_DATA_METODO = "retornarProyectoLey"
OPEN_DATA_PARAM_BOLETIN = "prmNumeroBoletin"  # confirmado contra el servicio real

OPEN_DATA_HEADERS = {
    # Cliente honesto: esta es una llamada a un servicio HTTP público
    # pensado para integraciones, no scraping de una página para navegador.
    "User-Agent": "RadarLegislativoCorfo-Observatorio/1.0 (+https://github.com/ambarv-blip/Radar-Legislativo-Corfo-v3)",
    "Accept": "text/xml, application/xml",
}

MESES_ES = {
    1: "Ene.", 2: "Feb.", 3: "Mar.", 4: "Abr.", 5: "May.", 6: "Jun.",
    7: "Jul.", 8: "Ago.", 9: "Sep.", 10: "Oct.", 11: "Nov.", 12: "Dic.",
}


def _tag_local(elemento):
    """Nombre de la etiqueta sin prefijo de namespace ('{ns}Tag' -> 'Tag').
    El namespace real es http://opendata.camara.cl/camaradiputados/v1, pero
    esto funciona igual sea cual sea el namespace (o si no hay ninguno)."""
    return elemento.tag.rsplit("}", 1)[-1]


def _listar_nodos(raiz):
    vistos = []
    for el in raiz.iter():
        nombre = _tag_local(el)
        if nombre not in vistos:
            vistos.append(nombre)
    return vistos


def _buscar_elemento(raiz, *nombres_candidatos):
    candidatos = {c.lower() for c in nombres_candidatos}
    for el in raiz.iter():
        if _tag_local(el).lower() in candidatos:
            return el
    return None


def _texto_de(raiz, *nombres_candidatos):
    """Texto útil de la forma más tolerante posible: el propio texto del
    elemento (así vienen los campos reales, ej. <Resultado Valor="1">Aprobado
    </Resultado> — "Aprobado" es el texto, Valor="1" es solo un código
    numérico y se ignora); si viene vacío, se prueba un sub-nodo típico de
    catálogo (Valor/Descripcion/Nombre) y, como último recurso, un atributo
    del mismo nombre."""
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
    for attr in ("Valor", "Descripcion", "Nombre"):
        if el.get(attr):
            return el.get(attr)
    return None


def _formatear_fecha(fecha_iso):
    """'2024-12-16T19:08:42' -> '16 Dic. 2024'. Si no se puede interpretar,
    se devuelve el valor original — mejor mostrar algo que perder el dato."""
    if not fecha_iso:
        return None
    try:
        dt = datetime.datetime.fromisoformat(fecha_iso)
    except ValueError:
        return fecha_iso
    return f"{dt.day} {MESES_ES.get(dt.month, dt.strftime('%b'))} {dt.year}"


def consultar_open_data(boletin):
    """Consulta retornarProyectoLey en el servicio oficial WSLegislativo.
    Reintenta ante error transitorio (timeout, conexión, HTTP no-200)."""
    url = f"{OPEN_DATA_BASE_URL}/{OPEN_DATA_METODO}"
    params = {OPEN_DATA_PARAM_BOLETIN: boletin}
    ultimo_error = None
    ultimo_status = None

    for intento in range(1, INTENTOS_MAX + 1):
        logger.info(
            "Consultando Open Data oficial (%s, boletín=%s, intento=%d/%d)",
            OPEN_DATA_METODO, boletin, intento, INTENTOS_MAX,
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
                logger.debug(
                    "Open Data — respuesta 200 boletín=%s — URL: %s — XML: %s",
                    boletin, resp.url, resp.text,
                )
                return {
                    "exito": True, "codigo_http": 200, "url_consultada": resp.url,
                    "contenido": resp.content, "error": None,
                }
            ultimo_error = f"HTTP {resp.status_code} de Open Data"
            if resp.status_code == 403 and resp.text:
                logger.warning("Cuerpo del 403 de Open Data (primeros 500 chars): %s", resp.text[:500])

        if intento < INTENTOS_MAX:
            time.sleep(ESPERA_ENTRE_INTENTOS * intento)

    return {
        "exito": False, "codigo_http": ultimo_status,
        "url_consultada": url, "contenido": None, "error": ultimo_error,
    }


def extraer_votaciones_open_data(contenido_xml, boletin):
    """Devuelve la lista COMPLETA de votaciones del proyecto (no solo la
    última), cada una con un id_externo estable (el <Id> real del servicio,
    ej. "od-votacion-42178") para poder deduplicar contra el historial ya
    guardado. Lista vacía si no hay votaciones o el XML no es interpretable
    — nunca None: la ausencia de votaciones no es un error, es normal para
    proyectos recién ingresados."""
    try:
        raiz = ET.fromstring(contenido_xml)
    except ET.ParseError as e:
        logger.error("XML de Open Data no válido para boletín %s: %s", boletin, e)
        return []

    logger.debug("Open Data — nodos XML encontrados para boletín %s: %s", boletin, _listar_nodos(raiz))

    votaciones_el = [el for el in raiz.iter() if _tag_local(el).lower() == "votacionproyectoley"]
    resultado = []
    for v in votaciones_el:
        id_real = _texto_de(v, "Id")
        if not id_real:
            continue  # sin Id no hay forma de deduplicar de forma confiable; se omite
        fecha_iso = _texto_de(v, "Fecha")
        resultado.append({
            "id_externo": f"od-votacion-{id_real}",
            "fecha": _formatear_fecha(fecha_iso) or fecha_iso,
            "fecha_iso": fecha_iso,
            "resultado": _texto_de(v, "Resultado"),
            "tramite_constitucional": _texto_de(v, "TramiteConstitucional"),
            "tramite_reglamentario": _texto_de(v, "TramiteReglamentario"),
            "total_si": _texto_de(v, "TotalSi"),
            "total_no": _texto_de(v, "TotalNo"),
            "total_abstencion": _texto_de(v, "TotalAbstencion"),
        })

    if votaciones_el and not resultado:
        logger.warning(
            "Open Data trae VotacionProyectoLey para boletín %s pero ninguna con <Id> "
            "reconocible (posible cambio de esquema).", boletin,
        )
    return resultado


# =====================================================================
# Orquestación: ambas fuentes aportan, ninguna bloquea a la otra
# =====================================================================

def _descripcion_votacion(v):
    partes = [p for p in (v["tramite_constitucional"], v["tramite_reglamentario"]) if p]
    base = " — ".join(partes) if partes else "Votación registrada"
    if v["resultado"]:
        base += f": {v['resultado']}"
    if v["total_si"] or v["total_no"]:
        base += f" ({v['total_si'] or '0'} a favor, {v['total_no'] or '0'} en contra, {v['total_abstencion'] or '0'} abstención)"
    return base


def ejecutar_monitoreo(boletin, estado_actual_guardado, ids_externos_existentes=frozenset()):
    """
    Punto de entrada único usado por el backend.

    ids_externos_existentes: set de Evento.id_externo ya guardados en el
    timeline de este proyecto — se usa para no duplicar votaciones ya
    registradas en actualizaciones anteriores.

    Devuelve dict:
      resultado: 'sin_cambios' | 'nuevo_evento' | 'error_tecnico'
      estado_nuevo: str | None            (solo si el Estado real cambió)
      eventos_nuevos: list[dict]          (0, 1 o más — cada uno listo para
                                            construir un Evento nuevo)
      error: str | None
    """
    prm_id = obtener_prm_id(boletin)

    html = consultar_fuente_oficial_scraper(boletin, prm_id)
    estado_html = extraer_estado_resumen(html["texto"]) if html["exito"] else None
    ultima_actuacion_html = extraer_ultima_actuacion(html["texto"]) if html["exito"] else None

    od = consultar_open_data(boletin)
    votaciones = extraer_votaciones_open_data(od["contenido"], boletin) if od["exito"] else []

    if not html["exito"] and not od["exito"]:
        return {
            "resultado": "error_tecnico",
            "error": f"camara.cl (HTML) falló ({html['error']}) y Open Data también falló ({od['error']}).",
            "estado_nuevo": None, "eventos_nuevos": [],
        }
    if html["exito"] and estado_html is None:
        logger.error(
            "camara.cl respondió pero no se pudo extraer 'Estado' para boletín %s "
            "(posible cambio de estructura del HTML).", boletin,
        )

    eventos_nuevos = []

    # 1) Votaciones nuevas (Open Data) — cada una es un evento propio, deduplicado por id_externo real.
    for v in votaciones:
        if v["id_externo"] not in ids_externos_existentes:
            eventos_nuevos.append({
                "id_externo": v["id_externo"],
                "fecha_evento": v["fecha"],
                "tipo_evento": "Votación registrada",
                "descripcion": _descripcion_votacion(v),
                "estado_anterior": None,
                "estado_nuevo": None,  # una votación no implica por sí sola un cambio de Estado
                "fuente": "Datos Abiertos oficiales — Cámara de Diputadas y Diputados (WSLegislativo.retornarProyectoLey)",
                "enlace": od["url_consultada"],
                "nivel_alerta": "Informativa",
            })

    # 2) Cambio de Estado (HTML) — la única fuente que sabe el estado real.
    estado_cambio = estado_html is not None and estado_html.strip() != (estado_actual_guardado or "").strip()
    if estado_cambio:
        id_externo_estado = f"html-estado-{boletin}-{estado_html}"[:250]
        if id_externo_estado not in ids_externos_existentes:
            ultima = ultima_actuacion_html or {}
            eventos_nuevos.append({
                "id_externo": id_externo_estado,
                "fecha_evento": ultima.get("fecha"),
                "tipo_evento": "Cambio de estado (detectado por el Observatorio)",
                "descripcion": ultima.get("sub_etapa") or "Sin descripción disponible",
                "estado_anterior": estado_actual_guardado,
                "estado_nuevo": estado_html,
                "fuente": "camara.cl (ficha de tramitación oficial)",
                "enlace": html["url_consultada"],
                "nivel_alerta": "Media",
            })

    if not eventos_nuevos:
        logger.info("Monitoreo boletín %s: sin cambios.", boletin)
        return {"resultado": "sin_cambios", "estado_nuevo": None, "eventos_nuevos": [], "error": None}

    logger.info(
        "Monitoreo boletín %s: %d evento(s) nuevo(s) detectado(s) (cambio de estado: %s).",
        boletin, len(eventos_nuevos), estado_cambio,
    )
    return {
        "resultado": "nuevo_evento",
        "estado_nuevo": estado_html if estado_cambio else None,
        "eventos_nuevos": eventos_nuevos,
        "error": None,
    }
