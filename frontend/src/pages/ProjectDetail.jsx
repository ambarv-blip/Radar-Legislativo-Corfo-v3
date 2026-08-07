import { useEffect, useRef, useState } from "react";
import { useParams, Link } from "react-router-dom";
import { verProyecto, generarAnalisisIA } from "../api";

function formatearFecha(iso) {
  if (!iso) return "Sin registro";
  const d = new Date(iso);
  return d.toLocaleDateString("es-CL", { day: "2-digit", month: "short", year: "numeric" });
}

const MESES_LARGOS = [
  "enero", "febrero", "marzo", "abril", "mayo", "junio",
  "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
];

// "2027-11-13T00:00:00" -> "Entra en vigencia el 13 de noviembre del 2027". Solo se llama
// cuando proyecto.fecha_vigencia existe (ver render más abajo) — un proyecto en trámite no
// tiene este campo, así que nunca se ve esta alerta para un proyecto que aún no es ley.
function formatearFechaVigencia(iso) {
  if (!iso) return null;
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return null;
  return `Entra en vigencia el ${d.getDate()} de ${MESES_LARGOS[d.getMonth()]} del ${d.getFullYear()}`;
}

// Misma escala de color que la tabla del Dashboard (ver estiloEstado en
// Home.jsx) — se reutilizan las clases .estado-pill ya existentes en
// styles.css para que la cápsula se vea idéntica en ambas vistas.
function estiloEstado(estado) {
  const e = (estado || "").toLowerCase();
  // Estados positivos / de tramitación finalizada ("despachado" no tenía regla propia y
  // caía en "Sin información" pese a ser un estado conocido con certeza).
  if (
    e.includes("ley") ||
    e.includes("promulg") ||
    e.includes("public") ||
    e.includes("terminada") ||
    e.includes("despachado")
  ) {
    return { clase: "estado-pill estado-terminado", texto: estado };
  }
  // "Aprobado por el Congreso" corresponde al mismo trámite real que "Trámite de
  // aprobación presidencial" (ambas cámaras ya aprobaron, el proyecto espera la firma
  // presidencial) — se muestra con esa etiqueta aunque el texto guardado sea otro; el
  // dato crudo en BD/API (proyecto.estado_actual) no se modifica, solo la presentación.
  if (e.includes("aprobación presidencial") || e.includes("aprobado por el congreso")) {
    return { clase: "estado-pill estado-presidencial", texto: "Trámite de aprobación presidencial" };
  }
  if (e.includes("tercer trámite") || e.includes("control de constitucionalidad")) {
    return { clase: "estado-pill estado-avanzado", texto: estado };
  }
  if (e.includes("segundo trámite")) {
    return { clase: "estado-pill estado-intermedio", texto: estado };
  }
  if (e.includes("primer trámite")) {
    return { clase: "estado-pill estado-inicial", texto: estado };
  }
  // Mención genérica a "comisión" sin especificar el trámite (texto libre de Cámara que no
  // calzó ninguna regla anterior más específica) — se trata como en curso, no como
  // "sin información".
  if (e.includes("comisión") || e.includes("comision")) {
    return { clase: "estado-pill estado-intermedio", texto: estado };
  }
  return { clase: "estado-pill estado-sin-info", texto: estado || "Sin información" };
}

const MESES_EVENTO = {
  ene: 0, feb: 1, mar: 2, abr: 3, may: 4, jun: 5,
  jul: 6, ago: 7, sep: 8, oct: 9, nov: 10, dic: 11,
};

// Los eventos guardan su fecha real como texto libre (ej. "9 Jul. 2024"),
// tal como la entrega la fuente oficial — no es un ISO ordenable directamente.
// Se parsea solo para poder ordenar el timeline de más reciente a más
// antiguo; si no calza el formato esperado, se devuelve null y ese evento
// conserva el orden que ya trae el backend (ver ordenarEventosPorFecha).
function parsearFechaEvento(fechaTexto) {
  if (!fechaTexto) return null;
  const m = fechaTexto.match(/(\d{1,2})\s+([a-zA-Záéíóú]{3,})\.?\s+(\d{4})/i);
  if (!m) return null;
  const mesIdx = MESES_EVENTO[m[2].toLowerCase().slice(0, 3)];
  if (mesIdx === undefined) return null;
  return new Date(Number(m[3]), mesIdx, Number(m[1])).getTime();
}

// Ordena de más reciente a más antiguo por la fecha real del evento
// (fecha_evento), no por cuándo el sistema lo detectó. Sort estable: los
// eventos sin fecha parseable no se pierden, quedan en el orden relativo
// que ya traía el backend.
function ordenarEventosPorFecha(eventos) {
  return [...eventos].sort((a, b) => {
    const fa = parsearFechaEvento(a.fecha_evento);
    const fb = parsearFechaEvento(b.fecha_evento);
    if (fa !== null && fb !== null) return fb - fa;
    if (fa !== null) return -1;
    if (fb !== null) return 1;
    return 0;
  });
}

// Deduplica eventos idénticos (misma fecha oficial + mismo tipo + misma
// descripción) — defensivo: el motor de monitoreo ya deduplica votaciones y
// cambios de estado por id_externo antes de insertarlos, pero eventos
// históricos migrados o cargados a mano (POST /api/eventos) no pasan por
// esa protección.
function deduplicarEventos(eventos) {
  const vistos = new Set();
  return eventos.filter((ev) => {
    const clave = `${ev.fecha_evento || ""}|${ev.tipo_evento || ""}|${ev.descripcion || ""}`;
    if (vistos.has(clave)) return false;
    vistos.add(clave);
    return true;
  });
}

// Un evento sin tipo, sin descripción y sin cambio de estado no aporta nada
// a la línea de tiempo — se descarta en vez de mostrar una fila vacía. Con
// los datos reales de hoy esto no ocurre; es una protección para datos
// futuros cargados manualmente o por una fuente nueva.
function esEventoRelevante(evento) {
  return Boolean(evento.tipo_evento || evento.descripcion || evento.estado_nuevo);
}

// Ícono según el tipo de evento — coincide con el vocabulario que ya usan
// tanto los eventos históricos migrados ("Ingreso de proyecto", "Aprobación",
// "Promulgación y Publicación") como el motor de monitoreo en vivo ("Cambio
// de estado (detectado por el Observatorio)") — no requiere tocar
// monitor_engine.py. Las votaciones no tienen ícono propio porque nunca
// llegan a esta función: se filtran antes (ver esHitoDeEtapa).
function iconoEvento(tipoEvento) {
  const t = (tipoEvento || "").toLowerCase();
  if (t.includes("ingreso")) return "📥";
  if (t.includes("promulgaci") || t.includes("publicaci")) return "📜";
  if (t.includes("aprobaci")) return "✅";
  if (t.includes("cambio de estado")) return "🔄";
  return "📌";
}

// El estado "nuevo" que declara un evento, pero solo si realmente es una
// etapa distinta a la anterior. Una votación dentro de la misma etapa (ej.
// AFIDE, 10 Dic. 2025: estado_anterior === estado_nuevo === "Segundo
// trámite constitucional") no es un cambio de etapa.
function estadoNuevoDeclarado(evento) {
  if (!evento.estado_nuevo) return null;
  if (evento.estado_anterior && evento.estado_anterior.trim() === evento.estado_nuevo.trim()) {
    return null;
  }
  return evento.estado_nuevo;
}

// Un hito de etapa es un evento que efectivamente declara una etapa nueva
// (ver estadoNuevoDeclarado). Esto excluye automáticamente votaciones,
// sesiones de comisión y cualquier actuación administrativa que no implique
// un cambio real de trámite — sin necesidad de una lista de tipos "técnicos"
// a mano: cualquier evento que no mueva el trámite de una etapa a otra
// simplemente no es un hito legislativo.
function esHitoDeEtapa(evento) {
  return Boolean(estadoNuevoDeclarado(evento));
}

// Extrae "Ley N° 21.813" de un texto oficial (estado_actual o la
// descripción de un evento de promulgación) — nunca se inventa un número:
// si el texto no lo trae, no se muestra.
function extraerNumeroLey(texto) {
  const m = (texto || "").match(/Ley N°\s*[\d.]+/i);
  return m ? m[0] : null;
}

// Mismo criterio que esLeyVigente() en Home.jsx (no se importa para no
// acoplar ambas páginas — Home.jsx no la exporta — pero es la misma regla:
// "Tramitación terminada" o un estado que ya trae "Ley N°").
function proyectoEsLeyPublicada(estado) {
  const e = (estado || "").toLowerCase();
  return e.includes("tramitación terminada") || e.includes("ley n°");
}

// Bandera de activación del Análisis Ejecutivo IA — EN PAUSA para la versión
// demo. Todo el código (componente, endpoint, prompt, backend) queda intacto
// y listo para reactivarse: basta con volver esta constante a `true`. Con
// `false`: no se renderiza la tarjeta, no se llama al endpoint
// /analisis-ia (ver el efecto en ProjectDetail), y por lo tanto tampoco
// aparece ningún mensaje del análisis (ni el skeleton, ni "No se encontró
// información suficiente...", ni el placeholder de "aún no generado").
const ANALISIS_IA_HABILITADO = false;

// Los 6 bloques del Análisis Ejecutivo IA, en el orden fijo definido para la
// funcionalidad. `lista: true` marca el único bloque que se muestra como
// viñetas (aspectos_principales); `destacado: true` marca el bloque de
// implicancias para Corfo, el más relevante para la decisión ejecutiva.
const BLOQUES_ANALISIS = [
  { clave: "objetivo", icono: "🎯", titulo: "Objetivo del proyecto" },
  { clave: "problema", icono: "⚠️", titulo: "¿Qué problema busca resolver?" },
  { clave: "aspectos_principales", icono: "📌", titulo: "Aspectos principales", lista: true },
  { clave: "implicancias_corfo", icono: "🏛", titulo: "Posibles implicancias para Corfo", destacado: true },
  { clave: "estado_debate", icono: "💬", titulo: "Estado del debate legislativo" },
  { clave: "conclusion", icono: "🧠", titulo: "Conclusión Ejecutiva" },
];

function parrafos(texto) {
  return String(texto || "")
    .split(/\n+/)
    .map((p) => p.trim())
    .filter(Boolean);
}

// Skeleton loader: se muestra mientras el backend genera el análisis por
// primera vez (ver el efecto en ProjectDetail que llama a generarAnalisisIA).
// Reproduce la silueta de los 6 bloques reales para que la tarjeta no salte
// de tamaño cuando el análisis termine de llegar.
function SkeletonAnalisisIA() {
  return (
    <div className="panel panel-analisis-ia">
      <h1 style={{ fontSize: 16 }}>🤖 Análisis Ejecutivo IA</h1>
      <p className="analisis-ia-generando">🤖 Generando análisis ejecutivo...</p>
      <div className="bloques-analisis-ia">
        {BLOQUES_ANALISIS.map((bloque) => (
          <div
            key={bloque.clave}
            className={`bloque-analisis-ia bloque-analisis-ia--skeleton${bloque.destacado ? " bloque-analisis-ia--destacado" : ""}`}
          >
            <div className="skeleton-linea skeleton-linea--titulo" />
            <div className="skeleton-linea" />
            <div className="skeleton-linea" />
            <div className="skeleton-linea skeleton-linea--corta" />
          </div>
        ))}
      </div>
    </div>
  );
}

function AnalisisEjecutivoIA({ ultimoAnalisisIA, generando, errorGeneracion }) {
  if (generando) return <SkeletonAnalisisIA />;

  if (!ultimoAnalisisIA) {
    return (
      <div className="panel panel-analisis-ia">
        <h1 style={{ fontSize: 16 }}>🤖 Análisis Ejecutivo IA</h1>
        <p className="placeholder-ia">
          {errorGeneracion || "No fue posible generar el análisis ejecutivo en este momento."}
        </p>
      </div>
    );
  }

  let analisis;
  try {
    analisis = JSON.parse(ultimoAnalisisIA);
  } catch {
    // Compatibilidad con análisis antiguos guardados como texto plano (placeholder).
    return (
      <div className="panel panel-analisis-ia">
        <h1 style={{ fontSize: 16 }}>🤖 Análisis Ejecutivo IA</h1>
        <p className="placeholder-ia">{ultimoAnalisisIA}</p>
      </div>
    );
  }

  return (
    <div className="panel panel-analisis-ia">
      <h1 style={{ fontSize: 16 }}>🤖 Análisis Ejecutivo IA</h1>

      <div className="disclaimer-ia">
        <span aria-hidden="true">ℹ️</span>
        <p>
          Este análisis fue generado automáticamente mediante inteligencia artificial utilizando
          exclusivamente información oficial disponible en la plataforma del Congreso Nacional. Su
          propósito es apoyar el análisis ejecutivo y no reemplaza la revisión de las fuentes oficiales.
        </p>
      </div>

      <div className="bloques-analisis-ia">
        {BLOQUES_ANALISIS.map((bloque) => {
          const valor = analisis[bloque.clave];
          return (
            <div
              key={bloque.clave}
              className={`bloque-analisis-ia${bloque.destacado ? " bloque-analisis-ia--destacado" : ""}`}
            >
              <h2>
                <span aria-hidden="true">{bloque.icono}</span> {bloque.titulo}
              </h2>
              {bloque.lista ? (
                Array.isArray(valor) && valor.length > 0 ? (
                  <ul>
                    {valor.map((item, i) => (
                      <li key={i}>{item}</li>
                    ))}
                  </ul>
                ) : (
                  <p className="sin-informacion-ia">No se encontró información suficiente para este apartado.</p>
                )
              ) : (
                parrafos(valor).map((p, i) => (
                  <p key={i} className={p === "No se encontró información suficiente para este apartado." ? "sin-informacion-ia" : undefined}>
                    {p}
                  </p>
                ))
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

export default function ProjectDetail() {
  const { id } = useParams();
  const [proyecto, setProyecto] = useState(null);
  const [cargando, setCargando] = useState(true);
  const [error, setError] = useState(null);
  const [analisisGenerando, setAnalisisGenerando] = useState(false);
  const [analisisError, setAnalisisError] = useState(null);
  // Evita disparar la llamada dos veces para el mismo proyecto: React
  // StrictMode (desarrollo) invoca los efectos dos veces al montar, y sin
  // este guard se pedían dos análisis a la vez (dos llamadas reales a la
  // API de Claude) la primera vez que se abre una ficha.
  const analisisSolicitadoParaId = useRef(null);

  function cargar() {
    setCargando(true);
    verProyecto(id)
      .then(setProyecto)
      .catch((e) => setError({ tipo: e.tipo || "conexion", mensaje: e.message }))
      .finally(() => setCargando(false));
  }

  useEffect(() => {
    cargar();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  // El Análisis Ejecutivo IA ya no depende de que se detecte un evento nuevo:
  // se genera la primera vez que se abre la ficha (si el proyecto todavía no
  // tiene uno almacenado) y queda guardado, así que en las siguientes visitas
  // no se vuelve a pedir. Mientras se genera, el panel muestra un skeleton
  // loader en vez del antiguo mensaje "Aún no se ha generado...".
  useEffect(() => {
    if (!ANALISIS_IA_HABILITADO) return;
    if (!proyecto || proyecto.ultimo_analisis_ia) return;
    if (analisisSolicitadoParaId.current === proyecto.id) return;
    analisisSolicitadoParaId.current = proyecto.id;
    let cancelado = false;
    setAnalisisError(null);
    setAnalisisGenerando(true);
    generarAnalisisIA(proyecto.id)
      .then((actualizado) => {
        if (!cancelado) setProyecto(actualizado);
      })
      .catch((e) => {
        if (!cancelado) setAnalisisError(e.message);
      })
      .finally(() => {
        if (!cancelado) setAnalisisGenerando(false);
      });
    return () => {
      cancelado = true;
    };
    // Deps por valor primitivo (id, ultimo_analisis_ia), no por identidad de
    // `proyecto`: `cargar()` puede resolver más de una vez para el mismo
    // proyecto (p. ej. en desarrollo, StrictMode invoca sus efectos dos
    // veces) y cada resolución entrega un objeto `proyecto` distinto aunque
    // representen el mismo estado. Si este efecto dependiera del objeto
    // completo, esa segunda referencia dispararía su cleanup a mitad de la
    // generación, descartando el resultado en curso y dejando el skeleton
    // cargando para siempre.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [proyecto?.id, proyecto?.ultimo_analisis_ia]);

  if (cargando) return <p className="vacio">Cargando proyecto...</p>;
  if (error) {
    // error.mensaje ya viene redactado según su tipo (ver api.js): para
    // "conexion" (backend caído, CORS, timeout) arma su propio mensaje de
    // "no fue posible conectar"; para "api" (404 proyecto no encontrado,
    // 422, etc.) es el mensaje que entregó el backend, mostrado tal cual
    // — el backend sí contestó, así que no correspondería decir "no se
    // pudo conectar".
    return <p className="vacio">{error.mensaje}</p>;
  }
  if (!proyecto) return null;

  const estado = estiloEstado(proyecto.estado_actual);

  // Todos los eventos relevantes, deduplicados y ordenados de más reciente a
  // más antiguo por la fecha real del evento (nunca por orden de inserción).
  // Se usa completo (sin filtrar por hito) para el chequeo de consistencia y
  // para ubicar el evento de promulgación/publicación — una votación, aunque
  // no se muestre como hito propio, sigue siendo el dato más reciente que
  // confirma en qué etapa está el proyecto.
  const eventosOrdenados = ordenarEventosPorFecha(
    deduplicarEventos(proyecto.eventos.filter(esEventoRelevante))
  );

  const ultimoEventoConEstado = eventosOrdenados.find((ev) => ev.estado_nuevo);
  const estadoInconsistente =
    ultimoEventoConEstado &&
    proyecto.estado_actual &&
    ultimoEventoConEstado.estado_nuevo.trim() !== proyecto.estado_actual.trim();

  const esLeyPublicada = proyectoEsLeyPublicada(proyecto.estado_actual);
  const numeroLey =
    extraerNumeroLey(proyecto.estado_actual) ||
    extraerNumeroLey(eventosOrdenados.map((ev) => ev.descripcion).join(" "));
  const eventoPublicacion = eventosOrdenados.find((ev) => /promulgaci|publicaci/i.test(ev.tipo_evento || ""));

  // Solo hitos de etapa (ver esHitoDeEtapa) — sin votaciones ni movimientos
  // administrativos. Si el proyecto ya es ley, el evento de
  // promulgación/publicación no se repite aquí: ya se muestra como la
  // tarjeta "✅ Ley publicada" al inicio de la línea de tiempo.
  const eventosTimeline = eventosOrdenados
    .filter(esHitoDeEtapa)
    .filter((ev) => !(esLeyPublicada && eventoPublicacion && ev.id === eventoPublicacion.id));

  return (
    <>
      <Link to="/" className="volver">← Volver al listado</Link>

      <div className="panel">
        <h1>{proyecto.nombre}</h1>
        <div className="boletin-detalle">Boletín {proyecto.boletin} · {proyecto.camara_origen}</div>

        <div className="fila-detalle">
          <div className="campo">
            <label>Estado actual</label>
            <p><span className={estado.clase}>{estado.texto}</span></p>
          </div>
          <div className="campo">
            <label>Prioridad de monitoreo</label>
            <p>{proyecto.prioridad_monitoreo || "No definida"}</p>
          </div>
          <div className="campo">
            <label>Última revisión</label>
            <p>{formatearFecha(proyecto.fecha_ultima_revision)}</p>
          </div>
        </div>

        <div className="fila-detalle">
          <div className="campo" style={{ flexBasis: "100%" }}>
            <label>Descripción</label>
            <p>{proyecto.descripcion || "Sin descripción disponible."}</p>
          </div>
        </div>

        {proyecto.comentario_estrategico && (
          <div className="fila-detalle">
            <div className="campo" style={{ flexBasis: "100%" }}>
              <label>Comentario estratégico</label>
              <p>{proyecto.comentario_estrategico}</p>
            </div>
          </div>
        )}

        {(proyecto.link_seguimiento || proyecto.url_ley_publicada) && (
          <div className="fila-detalle">
            {proyecto.link_seguimiento && (
              <div className="campo">
                <label>Fuente oficial</label>
                <p>
                  <a href={proyecto.link_seguimiento} target="_blank" rel="noopener noreferrer" className="link-boletin">
                    Ver ficha de tramitación en camara.cl ↗
                  </a>
                </p>
              </div>
            )}
            {proyecto.url_ley_publicada && (
              <div className="campo">
                <label>Ley publicada</label>
                <p>
                  <a href={proyecto.url_ley_publicada} target="_blank" rel="noopener noreferrer" className="link-boletin">
                    Ver Ley publicada en BCN ↗
                  </a>
                </p>
              </div>
            )}
          </div>
        )}

        {proyecto.fecha_vigencia && (
          <div className="alerta-vigencia">
            <strong>{formatearFechaVigencia(proyecto.fecha_vigencia)}</strong>
            {proyecto.url_ley_publicada && (
              <p style={{ marginTop: 4 }}>
                Fuente:{" "}
                <a href={proyecto.url_ley_publicada} target="_blank" rel="noopener noreferrer">
                  {proyecto.url_ley_publicada}
                </a>
              </p>
            )}
          </div>
        )}
      </div>

      {ANALISIS_IA_HABILITADO && (
        <AnalisisEjecutivoIA
          ultimoAnalisisIA={proyecto.ultimo_analisis_ia}
          generando={analisisGenerando}
          errorGeneracion={analisisError}
        />
      )}

      <div className="panel">
        <h1 style={{ fontSize: 16 }}>Historial legislativo</h1>

        {estadoInconsistente && (
          <p className="alerta-inconsistencia">
            ⚠ El estado actual de la ficha (<strong>{proyecto.estado_actual}</strong>) no coincide con el
            último estado registrado en la línea de tiempo (<strong>{ultimoEventoConEstado.estado_nuevo}</strong>).
            Revisa el historial de eventos de este proyecto.
          </p>
        )}

        {eventosTimeline.length === 0 && !esLeyPublicada && (
          <p className="vacio">Aún no hay hitos legislativos registrados para este proyecto.</p>
        )}

        {(eventosTimeline.length > 0 || esLeyPublicada) && (
          <ul className="linea-tiempo">
            {esLeyPublicada && (
              <li className="evento evento-ley-publicada" key="ley-publicada">
                <div className="fecha-evento">
                  <span aria-hidden="true">✅</span>{" "}
                  {eventoPublicacion?.fecha_evento || "Fecha de publicación no disponible"}
                </div>
                <h4>Ley publicada</h4>
                {numeroLey && <p>{numeroLey}</p>}
                {proyecto.url_ley_publicada && (
                  <p>
                    <a
                      href={proyecto.url_ley_publicada}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="link-boletin"
                    >
                      Ver en Ley Chile ↗
                    </a>
                  </p>
                )}
              </li>
            )}

            {eventosTimeline.map((ev) => {
              const estadoNuevo = estadoNuevoDeclarado(ev);
              return (
                <li className="evento" key={ev.id}>
                  <div className="fecha-evento">
                    <span aria-hidden="true">{iconoEvento(ev.tipo_evento)}</span>{" "}
                    {ev.fecha_evento || "Fecha no disponible"}
                  </div>
                  <h4>{ev.tipo_evento || "Evento"}</h4>
                  {ev.descripcion && <p>{ev.descripcion}</p>}
                  {estadoNuevo && (
                    <p className="evento-cambio-etapa">
                      {ev.estado_anterior ? "Cambió de etapa → " : "Etapa: "}
                      <span className={estiloEstado(estadoNuevo).clase}>{estiloEstado(estadoNuevo).texto}</span>
                    </p>
                  )}
                </li>
              );
            })}
          </ul>
        )}
      </div>
    </>
  );
}
