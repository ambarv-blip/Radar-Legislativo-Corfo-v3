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

- `extraer_actuaciones_html()`: la tabla de tramitación del HTML trae la
  secuencia COMPLETA de actuaciones oficiales (Fecha, Sesión, Etapa,
  Sub-etapa), no solo la más reciente. Hasta esta revisión, el código
  (entonces extraer_ultima_actuacion()) descartaba todas las filas menos la
  última — causa raíz de que varios proyectos mostraran el historial vacío
  o incompleto pese a que la fuente oficial sí traía su evolución completa.
  ejecutar_monitoreo() ahora reconstruye la secuencia entera de cambios de
  etapa a partir de esta lista, además de (no en reemplazo de) el mecanismo
  existente que compara el "Estado" resumen contra el guardado.

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
import threading
import time
import xml.etree.ElementTree as ET

import requests

logger = logging.getLogger(__name__)

TIMEOUT = 12
INTENTOS_MAX = 2  # 1 intento inicial + 1 reintento ante error transitorio
ESPERA_ENTRE_INTENTOS = 1.5  # segundos, se multiplica por el número de intento

# El prmID que necesita tramitacion.aspx (HTML) —además del boletín— ya no
# vive en un diccionario hardcodeado en este módulo: un proyecto nuevo que
# no se agrega manualmente aquí quedaba con esta fuente permanentemente
# rota, sin ningún aviso. Ahora es Proyecto.prm_id (columna persistente en
# la base de datos, ver backend/app/database.py) y lo entrega el llamador
# (ejecutar_monitoreo recibe prm_id como parámetro) — Open Data no lo
# necesita, consulta directo por boletín.

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


class _ClienteHtmlCamara:
    """Encapsula la sesión HTTP reutilizable hacia camara.cl (HTML).

    Aislado a propósito del resto del adaptador — solo sabe crear,
    entregar e invalidar una sesión "calentada" — para poder evolucionar
    más adelante hacia un gestor de clientes HTTP compartido entre varias
    fuentes (uno por FuenteOficial) sin tener que tocar la lógica de
    consultar_fuente_oficial_scraper(). Por ahora es un singleton simple a
    nivel de módulo (ver `_cliente_html` más abajo), no una variable suelta
    manipulada directamente desde la función de consulta.
    """

    def __init__(self):
        self._session = None
        self._lock = threading.Lock()

    def obtener_sesion(self):
        """Devuelve la sesión activa, creándola (y 'calentándola') si es la
        primera vez o si fue invalidada."""
        with self._lock:
            if self._session is None:
                self._session = self._crear_sesion()
            return self._session

    def invalidar(self):
        """Descarta la sesión actual. La próxima llamada a obtener_sesion()
        crea una nueva desde cero (con su propio calentamiento) — se usa
        cuando el circuito se abre, para no reintentar más adelante con
        cookies posiblemente asociadas al bloqueo."""
        with self._lock:
            self._session = None

    @staticmethod
    def _crear_sesion():
        """'Calienta' la sesión visitando el listado de proyectos, igual
        que un navegador real que llega a la ficha de tramitación
        navegando desde el buscador. Esto entrega cookies de sesión/WAF y
        un Referer legítimo para los pedidos siguientes."""
        session = requests.Session()
        session.headers.update(SCRAPER_HEADERS)
        try:
            session.get(LISTADO_URL, timeout=TIMEOUT)
        except requests.RequestException as e:
            # No es fatal: seguimos con la sesión sin cookies previas.
            logger.warning("No se pudo precargar cookies desde %s: %s", LISTADO_URL, e)
        return session


_cliente_html = _ClienteHtmlCamara()


class EstadoCircuito:
    """Circuit breaker de una fuente. Hoy vive en memoria del proceso
    (se reinicia si se reinicia uvicorn) — los nombres de los campos se
    eligen pensando en que más adelante puedan mapear 1:1 a columnas de
    una futura entidad FuenteOficial (fallos_consecutivos, abierto_desde,
    ultima_consulta_exitosa) para persistir este mismo estado sin cambiar
    la lógica que lo usa, solo el lugar donde vive.
    """

    def __init__(self, nombre_fuente, umbral_fallos=3, cooldown_segundos=900):
        self.nombre_fuente = nombre_fuente
        self.umbral_fallos = umbral_fallos
        self.cooldown_segundos = cooldown_segundos
        self.fallos_consecutivos = 0
        self.abierto_desde = None  # datetime | None
        self.ultima_consulta_exitosa = None  # datetime | None

    def esta_abierto(self):
        if self.abierto_desde is None:
            return False
        transcurrido = (datetime.datetime.utcnow() - self.abierto_desde).total_seconds()
        return transcurrido < self.cooldown_segundos

    def registrar_exito(self):
        if self.fallos_consecutivos or self.abierto_desde:
            logger.info("Circuito de %s: recuperado, circuito cerrado.", self.nombre_fuente)
        self.fallos_consecutivos = 0
        self.abierto_desde = None
        self.ultima_consulta_exitosa = datetime.datetime.utcnow()

    def registrar_fallo(self, razon="desconocida"):
        """Registra cualquier fallo relevante de esta fuente — bloqueo 403,
        pero también timeout o error de conexión: antes solo el 403 abría
        el circuito, así que una caída real de camara.cl (no un bloqueo
        WAF) generaba reintentos completos sin protección alguna en cada
        proyecto de una actualización masiva. Devuelve True si este fallo
        fue el que recién abrió el circuito (para que el llamador pueda,
        por ejemplo, invalidar la sesión asociada en el caso de un 403)."""
        self.fallos_consecutivos += 1
        if self.fallos_consecutivos >= self.umbral_fallos and self.abierto_desde is None:
            self.abierto_desde = datetime.datetime.utcnow()
            logger.error(
                "Circuito de %s ABIERTO tras %d fallo(s) consecutivo(s) (último: %s). "
                "Se omitirá esta fuente por %ds (fuente marcada como degradada).",
                self.nombre_fuente, self.fallos_consecutivos, razon, self.cooldown_segundos,
            )
            return True
        return False


_circuito_html = EstadoCircuito("camara.cl (HTML)", umbral_fallos=3, cooldown_segundos=900)


def consultar_fuente_oficial_scraper(boletin, prm_id):
    """Consulta la ficha de tramitación de un boletín en camara.cl (HTML).

    Reintenta ante errores transitorios (timeout, error de conexión) hasta
    INTENTOS_MAX veces. NO reintenta ante 403 ni 404: un bloqueo tipo WAF
    no se resuelve en los pocos segundos de un reintento inmediato (según
    evidencia real de producción), y un boletín/prmID inválido tampoco se
    arregla reintentando.

    Si el circuito de esta fuente está abierto (varios fallos consecutivos
    recientes — 403, timeout o error de conexión), la consulta se omite
    por completo — la fuente queda marcada como degradada temporalmente,
    pero esta función nunca lanza excepción ni bloquea al llamador: sigue
    devolviendo la misma forma de resultado de siempre con exito=False.
    """
    if prm_id is None:
        mensaje = (
            f"Proyecto sin prm_id configurado (boletín {boletin}) — no se puede consultar "
            "la ficha de tramitación HTML de camara.cl. Revisa Proyecto.prm_id en la base de datos."
        )
        logger.warning(mensaje)
        return {"exito": False, "codigo_http": None, "url_consultada": TRAMITACION_URL,
                "texto": None, "error": mensaje}

    if _circuito_html.esta_abierto():
        logger.warning(
            "camara.cl (HTML) marcado como degradado (circuito abierto) — se omite la "
            "consulta para boletín %s.", boletin,
        )
        return {
            "exito": False, "codigo_http": None, "url_consultada": TRAMITACION_URL,
            "texto": None,
            "error": "camara.cl (HTML) está temporalmente marcado como degradado tras fallos "
                     "consecutivos (bloqueos 403, timeouts o errores de conexión); se omite esta consulta.",
        }

    params = {"prmID": prm_id, "prmBOLETIN": boletin}
    session = _cliente_html.obtener_sesion()
    ultimo_error = None
    ultimo_status = None

    for intento in range(1, INTENTOS_MAX + 1):
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
            if _circuito_html.registrar_fallo("timeout"):
                break  # ya se abrió el circuito: reintentar de inmediato no cambiaría nada
        except requests.ConnectionError as e:
            ultimo_error = f"Error de conexión con camara.cl: {str(e)[:300]}"
            logger.warning("Error de conexión en intento %d/%d para boletín %s: %s", intento, INTENTOS_MAX, boletin, e)
            if _circuito_html.registrar_fallo("error de conexión"):
                break
        except requests.RequestException as e:
            ultimo_error = f"{type(e).__name__}: {str(e)[:300]}"
            logger.warning("Error de red en intento %d/%d para boletín %s: %s", intento, INTENTOS_MAX, boletin, e)
            if _circuito_html.registrar_fallo("error de red"):
                break
        else:
            ultimo_status = resp.status_code
            logger.info("camara.cl respondió HTTP %s desde %s", resp.status_code, resp.url)

            if resp.status_code == 200:
                _circuito_html.registrar_exito()
                return {
                    "exito": True, "codigo_http": 200, "url_consultada": resp.url,
                    "texto": resp.text, "error": None,
                }
            if resp.status_code == 403:
                ultimo_error = "HTTP 403 — camara.cl rechazó la solicitud (bloqueo anti-bot/WAF)"
                logger.warning("Bloqueo 403 en intento %d/%d para boletín %s", intento, INTENTOS_MAX, boletin)
                if resp.text:
                    logger.warning("Cuerpo de la respuesta 403 (primeros 500 chars): %s", resp.text[:500])
                if _circuito_html.registrar_fallo("bloqueo 403"):
                    _cliente_html.invalidar()
                break  # un 403 no se arregla reintentando de inmediato
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


def extraer_actuaciones_html(html):
    """TODAS las filas de la tabla de tramitación del HTML, en el orden en
    que camara.cl las presenta — no solo la última.

    Hallazgo de auditoría (causa raíz de que el historial de varios
    proyectos solo mostrara el ingreso o quedara vacío): esta función antes
    se llamaba extraer_ultima_actuacion() y devolvía únicamente filas[-1],
    descartando el resto de la tabla. La tabla oficial de tramitación ya
    trae la secuencia completa (Fecha, Sesión, Etapa, Sub-etapa) de todas
    las actuaciones del proyecto — se estaba descartando esa información
    en la propia extracción, antes de que le llegara al backend.
    ejecutar_monitoreo() ahora reconstruye la secuencia completa de cambios
    de etapa a partir de esta lista (ver más abajo)."""
    if not html:
        return []
    filas = []
    for fila_html in re.findall(r"<tr[^>]*>(.*?)</tr>", html, re.IGNORECASE | re.DOTALL):
        celdas = re.findall(r"<td[^>]*>(.*?)</td>", fila_html, re.IGNORECASE | re.DOTALL)
        if len(celdas) >= 4:
            limpio = [re.sub("<[^>]+>", "", c).strip() for c in celdas]
            if limpio[0] and re.search(r"\d{4}|\w{3}\.", limpio[0]):
                filas.append({"fecha": limpio[0], "sesion": limpio[1], "etapa": limpio[2],
                               "sub_etapa": limpio[3] if len(limpio) > 3 else None})
    return filas


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


def ejecutar_monitoreo(boletin, prm_id, estado_actual_guardado, ids_externos_existentes=frozenset()):
    """
    Punto de entrada único usado por el backend.

    prm_id: identificador interno que camara.cl usa para la ficha HTML de
    tramitación (Proyecto.prm_id en la base de datos). Ya no se busca en un
    diccionario hardcodeado de este módulo — el llamador lo entrega desde
    el registro persistente del proyecto, así un proyecto nuevo no depende
    de una actualización manual de monitor_engine.py para que funcione la
    fuente HTML. Puede ser None (proyecto sin prm_id configurado): en ese
    caso consultar_fuente_oficial_scraper lo registra con un warning
    explícito y devuelve exito=False — Open Data sigue aportando lo que
    pueda igual, sin bloquearse por la ausencia de la otra fuente.

    ids_externos_existentes: set de Evento.id_externo ya guardados en el
    timeline de este proyecto — se usa para no duplicar votaciones, hitos de
    etapa o cambios de estado ya registrados en actualizaciones anteriores.

    Si la fuente HTML responde con éxito, esta función también reconstruye
    la secuencia COMPLETA de cambios de etapa que trae la tabla oficial de
    tramitación (ver extraer_actuaciones_html) — no solo el estado vigente.
    En un proyecto que nunca se había actualizado, esto puede backfillear de
    una sola vez todo su historial oficial de etapas (Ingreso, Primer
    trámite, Segundo trámite, ...).

    Devuelve dict:
      resultado: 'sin_cambios' | 'nuevo_evento' | 'error_tecnico'
      estado_nuevo: str | None            (solo si el Estado real cambió)
      eventos_nuevos: list[dict]          (0, 1 o más — cada uno listo para
                                            construir un Evento nuevo)
      error: str | None
    """
    html = consultar_fuente_oficial_scraper(boletin, prm_id)
    estado_html = extraer_estado_resumen(html["texto"]) if html["exito"] else None
    actuaciones_html = extraer_actuaciones_html(html["texto"]) if html["exito"] else []
    ultima_actuacion_html = actuaciones_html[-1] if actuaciones_html else None

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

    # 2) Secuencia completa de cambios de etapa (HTML) — reconstruida a
    # partir de TODAS las filas de la tabla de tramitación oficial, no solo
    # la última (ver extraer_actuaciones_html). Cada cambio de "Etapa" entre
    # una fila y la siguiente es un hito real de la fuente oficial: se
    # registra tal cual, con el texto literal que trae la tabla — nunca se
    # reformula ni se infiere. Deduplicado por id_externo propio (namespace
    # "html-etapa-", distinto del "html-estado-" del punto 3) para que
    # actualizaciones futuras no vuelvan a crear los mismos hitos.
    etapa_anterior = None
    for fila in actuaciones_html:
        etapa_actual = (fila.get("etapa") or "").strip()
        if not etapa_actual or etapa_actual == etapa_anterior:
            continue
        id_externo_etapa = f"html-etapa-{boletin}-{fila.get('fecha')}-{etapa_actual}"[:250]
        if id_externo_etapa not in ids_externos_existentes:
            eventos_nuevos.append({
                "id_externo": id_externo_etapa,
                "fecha_evento": fila.get("fecha"),
                "tipo_evento": "Ingreso de proyecto" if etapa_anterior is None
                               else "Cambio de estado (detectado por el Observatorio)",
                "descripcion": fila.get("sub_etapa") or "Sin descripción disponible",
                "estado_anterior": etapa_anterior,
                "estado_nuevo": etapa_actual,
                "fuente": "camara.cl (ficha de tramitación oficial)",
                "enlace": html["url_consultada"],
                "nivel_alerta": "Informativa" if etapa_anterior is None else "Media",
            })
        etapa_anterior = etapa_actual

    # 3) Cambio de Estado (HTML, "Estado" resumen) — la única fuente que
    # sabe con certeza cuál es el estado VIGENTE ahora mismo; sigue
    # decidiendo si se actualiza Proyecto.estado_actual, independiente del
    # punto 2 (que solo reconstruye el historial de eventos).
    estado_cambio = estado_html is not None and estado_html.strip() != (estado_actual_guardado or "").strip()
    if estado_cambio:
        id_externo_estado = f"html-estado-{boletin}-{estado_html}"[:250]
        if id_externo_estado not in ids_externos_existentes:
            ultima = ultima_actuacion_html or {}
            # Si el proyecto nunca tuvo estado_actual guardado Y el estado
            # vigente coincide con la primera etapa de la propia tabla (o
            # sea, todavía no avanzó más allá de su primera etapa), este
            # evento describe exactamente la misma transición que el
            # "Ingreso de proyecto" del punto 2 — se etiqueta igual para que
            # el deduplicador del frontend los reconozca como un solo hito
            # en vez de mostrar dos. En cualquier otro caso (el proyecto ya
            # avanzó más allá de su primera etapa) sigue siendo un cambio de
            # estado real, no un ingreso.
            primera_etapa_html = (
                actuaciones_html[0]["etapa"].strip() if actuaciones_html and actuaciones_html[0].get("etapa") else None
            )
            es_transicion_de_ingreso = (
                not estado_actual_guardado and primera_etapa_html and estado_html.strip() == primera_etapa_html
            )
            eventos_nuevos.append({
                "id_externo": id_externo_estado,
                "fecha_evento": ultima.get("fecha"),
                "tipo_evento": "Ingreso de proyecto" if es_transicion_de_ingreso
                               else "Cambio de estado (detectado por el Observatorio)",
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
