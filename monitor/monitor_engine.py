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

ESQUEMA REAL CONFIRMADO (boletín 16889-05, vía logs de diagnóstico contra
el servicio real): retornarProyectoLey NO tiene un campo "Estado" directo.
Devuelve un <ProyectoLey> con, entre otros, <Votaciones><VotacionProyectoLey>
(una por cada votación registrada), cada una con <Fecha>, <Resultado>,
<TramiteConstitucional> y <TramiteReglamentario>. El estado legislativo se
infiere a partir de la votación más reciente — no hay otra señal de estado
en la respuesta. Parámetro confirmado: prmNumeroBoletin. Namespace real:
xmlns="http://opendata.camara.cl/camaradiputados/v1" (se ignora igual que
cualquier otro namespace, ver _tag_local). El parser se mantiene tolerante
a variantes de nombre por si el esquema cambia a futuro, pero ya no
depende de suposiciones para los campos usados hoy.
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

# Confirmado contra el servicio real (ver nota del módulo).
OPEN_DATA_PARAM_BOLETIN = "prmNumeroBoletin"

OPEN_DATA_HEADERS = {
    # Cliente honesto: esta es una llamada a un servicio HTTP público
    # pensado para integraciones, no scraping de una página para navegador.
    "User-Agent": "RadarLegislativoCorfo-Observatorio/1.0 (+https://github.com/ambarv-blip/Radar-Legislativo-Corfo-v3)",
    "Accept": "text/xml, application/xml",
}


def _tag_local(elemento):
    """Nombre de la etiqueta sin prefijo de namespace ('{ns}Tag' -> 'Tag')."""
    return elemento.tag.rsplit("}", 1)[-1]


def _listar_nodos(raiz):
    """Lista, sin duplicados y en orden de aparición, los nombres locales de
    todos los nodos del XML — para ver de un vistazo el esquema real que
    devuelve retornarProyectoLey (independiente de namespaces, ver nota de
    extraer_desde_open_data)."""
    vistos = []
    for el in raiz.iter():
        nombre = _tag_local(el)
        if nombre not in vistos:
            vistos.append(nombre)
    return vistos


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
    """Como _buscar_elemento, pero devuelve el texto útil de la forma más
    tolerante posible: el propio texto del elemento (así vienen los campos
    reales de retornarProyectoLey, ej. <Resultado Valor="1">Aprobado</Resultado>
    — "Aprobado" es el texto, Valor="1" es solo el código numérico y se
    ignora); si el texto viene vacío, se prueba un sub-nodo típico de
    catálogo (Valor/Descripcion/Nombre) y, como último recurso, un atributo
    del mismo nombre — por si algún campo futuro solo trae el dato ahí."""
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


# Mapea el texto real de <TramiteConstitucional> (ej. "Primer Trámite") al
# formato ya usado en toda la app y reconocido por el frontend para
# colorear el estado (ver estiloEstado() en frontend/src/pages/Home.jsx,
# que busca substrings como "primer trámite" / "segundo trámite").
# Si algún día aparece un trámite no listado aquí, se usa el texto tal cual
# viene del servicio en vez de fallar (parser tolerante).
TRAMITE_CONSTITUCIONAL_A_ESTADO = {
    "primer trámite": "Primer trámite constitucional",
    "segundo trámite": "Segundo trámite constitucional",
    "tercer trámite": "Tercer trámite constitucional",
}

MESES_ES = {
    1: "Ene.", 2: "Feb.", 3: "Mar.", 4: "Abr.", 5: "May.", 6: "Jun.",
    7: "Jul.", 8: "Ago.", 9: "Sep.", 10: "Oct.", 11: "Nov.", 12: "Dic.",
}


def _formatear_fecha(fecha_iso):
    """'2024-12-16T19:08:42' -> '16 Dic. 2024' (mismo estilo que usaban los
    eventos migrados del scraper). Si no se puede interpretar, se devuelve
    el valor original tal cual — mejor mostrar algo que perder el dato."""
    if not fecha_iso:
        return None
    try:
        dt = datetime.datetime.fromisoformat(fecha_iso)
    except ValueError:
        return fecha_iso
    return f"{dt.day} {MESES_ES.get(dt.month, dt.strftime('%b'))} {dt.year}"


def _normalizar_tramite_constitucional(texto):
    if not texto:
        return None
    return TRAMITE_CONSTITUCIONAL_A_ESTADO.get(texto.strip().lower(), texto.strip())


def consultar_open_data(boletin):
    """Consulta retornarProyectoLey en el servicio oficial WSLegislativo.

    Reintenta ante error transitorio (timeout, error de conexión, HTTP no-200)
    hasta INTENTOS_MAX veces.
    """
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
                # Diagnóstico detallado (XML completo) disponible en DEBUG por si hace
                # falta reabrirlo ante un cambio de esquema futuro; ya no se emite en
                # INFO por defecto, el esquema real quedó confirmado y documentado.
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


def extraer_desde_open_data(contenido_xml, boletin):
    """Mapea la respuesta XML de retornarProyectoLey al mismo formato
    interno que produce el respaldo HTML: {estado_oficial, ultima_actuacion}.

    Esquema real (confirmado, ver nota al inicio del módulo): no existe un
    campo "Estado" directo. <ProyectoLey><Votaciones> trae cero o más
    <VotacionProyectoLey>, cada una con <Fecha>, <Resultado>,
    <TramiteConstitucional> y <TramiteReglamentario>. Se toma la votación
    con la <Fecha> más reciente (comparación de string ISO 8601, que ordena
    igual que la fecha real) como referencia del estado actual, tal como no
    hay otra señal de estado en la respuesta del servicio.

    Devuelve None si el proyecto no tiene votaciones registradas todavía
    (recién ingresado) o si, ante un cambio de esquema futuro, no se logra
    reconocer TramiteConstitucional — en ambos casos el llamador debe caer
    al respaldo en vez de guardar un estado vacío.

    Manejo de namespaces: ElementTree representa un tag con namespace como
    '{http://opendata.camara.cl/camaradiputados/v1}NombreTag' (notación de
    Clark). _tag_local() lo reduce a 'NombreTag' quitando el prefijo
    '{...}', así que toda la búsqueda de nodos es namespace-agnóstica."""
    try:
        raiz = ET.fromstring(contenido_xml)
    except ET.ParseError as e:
        logger.error("XML de Open Data no válido para boletín %s: %s", boletin, e)
        return None

    logger.debug("Open Data — nodos XML encontrados para boletín %s: %s", boletin, _listar_nodos(raiz))

    votaciones = [el for el in raiz.iter() if _tag_local(el).lower() == "votacionproyectoley"]
    if not votaciones:
        logger.warning(
            "Open Data respondió pero el boletín %s no tiene votaciones registradas "
            "(proyecto recién ingresado, sin votación aún, o cambio de esquema).", boletin,
        )
        return None

    ultima_votacion = max(votaciones, key=lambda v: _texto_de(v, "Fecha") or "")

    fecha_iso = _texto_de(ultima_votacion, "Fecha")
    resultado_voto = _texto_de(ultima_votacion, "Resultado")
    tramite_constitucional_raw = _texto_de(ultima_votacion, "TramiteConstitucional")
    tramite_reglamentario = _texto_de(ultima_votacion, "TramiteReglamentario")

    tramite_constitucional = _normalizar_tramite_constitucional(tramite_constitucional_raw)
    if tramite_constitucional is None:
        logger.warning(
            "Open Data respondió con votaciones pero sin TramiteConstitucional reconocible "
            "para boletín %s (cambio de esquema).", boletin,
        )
        return None

    detalle = [p for p in (tramite_reglamentario, resultado_voto) if p]
    estado_oficial = f"{tramite_constitucional} — {' / '.join(detalle)}" if detalle else tramite_constitucional

    ultima_actuacion = {
        "fecha": _formatear_fecha(fecha_iso) or fecha_iso,
        "sesion": None,  # no existe un número de sesión en este esquema
        "etapa": tramite_constitucional,
        "sub_etapa": f"{tramite_reglamentario or 'Trámite reglamentario no informado'}"
                     f" — Resultado: {resultado_voto or 'no informado'}",
        "resultado": resultado_voto,
        "tramite_constitucional": tramite_constitucional_raw,
        "tramite_reglamentario": tramite_reglamentario,
    }

    return {"estado_oficial": estado_oficial, "ultima_actuacion": ultima_actuacion}


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

# El esquema real de Open Data ya está confirmado y el parser ajustado a él
# (ver nota al inicio del módulo), así que el respaldo HTML vuelve a estar
# habilitado como lo que siempre debió ser: un mecanismo de contingencia,
# no la fuente principal. Solo se usa si Datos Abiertos falla de verdad
# (caído, timeout) o responde sin votaciones utilizables.
HABILITAR_RESPALDO_HTML = True


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
        logger.warning("Open Data respondió pero no entregó un Estado utilizable para boletín %s.", boletin)
        error_open_data = "Open Data respondió pero no se pudo interpretar el Estado del proyecto"
    else:
        logger.warning("Open Data no disponible para boletín %s (%s).", boletin, od["error"])
        error_open_data = od["error"]

    if not HABILITAR_RESPALDO_HTML:
        return {
            "resultado": "error_tecnico",
            "error": f"Datos Abiertos falló ({error_open_data}). Respaldo HTML desactivado "
                     f"(HABILITAR_RESPALDO_HTML=False en monitor_engine.py).",
            "estado_oficial": None, "ultima_actuacion": None,
            "url_consultada": od["url_consultada"], "fuente": None,
        }

    logger.warning("Open Data no entregó un resultado utilizable para boletín %s; se usa el respaldo HTML.", boletin)

    # 2) Respaldo: scraping del HTML público (solo si Open Data falló y está habilitado)
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
