import { useEffect, useState } from "react";
import { useParams, Link } from "react-router-dom";
import { verProyecto } from "../api";

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

// Las votaciones individuales (Open Data) se guardan todas en la base de
// datos para trazabilidad, pero inundan el timeline ejecutivo — un
// proyecto con muchas votaciones el mismo día no debe tapar los hitos
// reales de tramitación. El motor de monitoreo las etiqueta siempre con
// este tipo_evento exacto (ver monitor/monitor_engine.py); cualquier otro
// tipo de evento (cambios de estado, hitos históricos migrados) se
// considera un hito legislativo y se muestra.
const TIPO_EVENTO_VOTACION = "Votación registrada";

function esHitoLegislativo(evento) {
  return evento.tipo_evento !== TIPO_EVENTO_VOTACION;
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

// Fallback cuando un proyecto no tiene ningún hito con fecha cierta (caso
// frecuente hoy: el HTML de camara.cl —única fuente que registra el
// momento real de cambio de trámite— sigue bloqueado, y las fechas de
// votación de Open Data NO son un proxy confiable de "cuándo entró a esa
// etapa": una votación puede ocurrir semanas o meses después del cambio
// real de trámite. Por eso NO se deriva ningún hito de trámite a partir
// de votaciones (ni la primera ni la última).
//
// En su lugar se muestra un único elemento honesto: el Estado actual ya
// conocido (mismo texto que la cápsula), fechado con la última
// verificación real del Observatorio — nunca se presenta como "fecha de
// ingreso a la etapa", se deja explícito en la descripción que es una
// verificación. Preferible mostrar un solo hito honesto que varios
// aproximados que puedan inducir a error.
function hitoDeRespaldo(proyecto) {
  if (!proyecto.estado_actual) return [];
  return [{
    id: "respaldo-estado-actual",
    fecha_evento: formatearFecha(proyecto.fecha_ultima_revision),
    tipo_evento: proyecto.estado_actual,
    descripcion:
      "Estado verificado por el Observatorio en esta fecha. Aún no se cuenta con la fecha exacta en que " +
      "el proyecto ingresó a esta etapa — las fuentes oficiales disponibles hoy no la entregan con certeza. " +
      "Para el detalle completo de la tramitación, revisa el enlace oficial de la Cámara.",
    nivel_alerta: null,
  }];
}

// Línea de tiempo ejecutiva — EN PAUSA. Toda la lógica de arriba
// (esHitoLegislativo, ordenarEventosPorFecha, hitoDeRespaldo, etc.) se
// mantiene intacta y lista para reactivarse: cuando el backend incorpore
// una fuente oficial que entregue la fecha real de cada cambio de trámite
// (Cámara sin bloqueo 403, BCN, Senado u otra equivalente), basta con
// volver esta constante a `true` — no hace falta rediseñar nada.
//
// Motivo de la pausa: hoy ninguna fuente disponible entrega con certeza la
// fecha en que un proyecto cambia de etapa legislativa. Mostrar fechas
// derivadas de votaciones (que pueden ocurrir mucho después del cambio
// real de trámite) induce a error, así que se prefiere mostrar un mensaje
// explicativo antes que un timeline con fechas potencialmente engañosas.
const TIMELINE_EJECUTIVO_HABILITADO = false;

export default function ProjectDetail() {
  const { id } = useParams();
  const [proyecto, setProyecto] = useState(null);
  const [cargando, setCargando] = useState(true);
  const [error, setError] = useState(null);

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
  const hitosDetectados = ordenarEventosPorFecha(proyecto.eventos.filter(esHitoLegislativo));
  const hitos = hitosDetectados.length > 0 ? hitosDetectados : hitoDeRespaldo(proyecto);

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

      <div className="panel">
        <h1 style={{ fontSize: 16 }}>Último análisis IA</h1>
        <p className="placeholder-ia">
          {proyecto.ultimo_analisis_ia || "Aún no se ha generado un análisis IA para este proyecto — se generará automáticamente la próxima vez que se detecte un nuevo evento."}
        </p>
      </div>

      <div className="panel">
        <h1 style={{ fontSize: 16 }}>Historial legislativo</h1>
        {TIMELINE_EJECUTIVO_HABILITADO ? (
          <>
            {hitos.length === 0 && <p className="vacio">Aún no hay hitos legislativos registrados.</p>}
            <ul className="linea-tiempo">
              {hitos.map((ev) => (
                <li className="evento" key={ev.id}>
                  <div className="fecha-evento">{ev.fecha_evento || "Fecha no disponible"}</div>
                  <h4>{ev.tipo_evento || "Evento"}</h4>
                  <p>{ev.descripcion}</p>
                  {ev.nivel_alerta && (
                    <p style={{ marginTop: 4 }}>
                      <strong>Nivel de alerta:</strong> {ev.nivel_alerta} · <strong>Revisión:</strong>{" "}
                      {ev.estado_revision_humana}
                    </p>
                  )}
                </li>
              ))}
            </ul>
          </>
        ) : (
          <p className="vacio">
            La visualización ejecutiva del historial legislativo se encuentra temporalmente en desarrollo.
            <br />
            Mientras tanto, puedes consultar la historia legislativa oficial mediante el enlace de la Cámara de
            Diputadas y Diputados disponible en esta ficha.
          </p>
        )}
      </div>
    </>
  );
}
