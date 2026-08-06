import { useEffect, useState } from "react";
import { useParams, Link } from "react-router-dom";
import { verProyecto, actualizarProyecto } from "../api";

function formatearFecha(iso) {
  if (!iso) return "Sin registro";
  const d = new Date(iso);
  return d.toLocaleDateString("es-CL", { day: "2-digit", month: "short", year: "numeric" });
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

export default function ProjectDetail() {
  const { id } = useParams();
  const [proyecto, setProyecto] = useState(null);
  const [cargando, setCargando] = useState(true);
  const [error, setError] = useState(null);
  const [actualizando, setActualizando] = useState(false);
  const [resultado, setResultado] = useState(null);

  function cargar() {
    setCargando(true);
    verProyecto(id)
      .then(setProyecto)
      .catch((e) => setError(e.message))
      .finally(() => setCargando(false));
  }

  useEffect(() => {
    cargar();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  async function handleActualizar() {
    setActualizando(true);
    setResultado(null);
    try {
      const r = await actualizarProyecto(id);
      setResultado(r);
      setProyecto(r.proyecto);
    } catch (e) {
      setResultado({ resultado: "error_tecnico", mensaje: e.message });
    } finally {
      setActualizando(false);
    }
  }

  if (cargando) return <p className="vacio">Cargando proyecto...</p>;
  if (error) return <p className="vacio">No se pudo conectar con el backend: {error}</p>;
  if (!proyecto) return null;

  return (
    <>
      <Link to="/" className="volver">← Volver al listado</Link>

      <div className="panel">
        <h1>{proyecto.nombre}</h1>
        <div className="boletin-detalle">Boletín {proyecto.boletin} · {proyecto.camara_origen}</div>

        <div className="fila-detalle">
          <div className="campo">
            <label>Estado actual</label>
            <p>{proyecto.estado_actual || "No disponible"}</p>
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

        {proyecto.link_seguimiento && (
          <div className="fila-detalle">
            <div className="campo">
              <label>Fuente oficial</label>
              <p>
                <a href={proyecto.link_seguimiento} target="_blank" rel="noopener noreferrer" className="link-boletin">
                  Ver ficha de tramitación en camara.cl ↗
                </a>
              </p>
            </div>
          </div>
        )}

        <div style={{ marginTop: 20 }}>
          <button className="btn-actualizar" onClick={handleActualizar} disabled={actualizando}>
            {actualizando ? "Consultando fuente oficial..." : "Actualizar ahora"}
          </button>
        </div>

        {resultado && (
          <div className={`resultado-actualizacion ${resultado.resultado}`}>
            {resultado.resultado === "sin_cambios" && "✓ "}
            {resultado.resultado === "nuevo_evento" && "🔔 "}
            {resultado.resultado === "error_tecnico" && "⚠ "}
            {resultado.mensaje}
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
        <h1 style={{ fontSize: 16 }}>Historial de eventos</h1>
        {proyecto.eventos.length === 0 && <p className="vacio">Aún no hay eventos registrados.</p>}
        <ul className="linea-tiempo">
          {ordenarEventosPorFecha(proyecto.eventos).map((ev) => (
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
      </div>
    </>
  );
}
