import { useEffect, useState } from "react";
import { useParams, Link } from "react-router-dom";
import { verProyecto, actualizarProyecto } from "../api";

function formatearFecha(iso) {
  if (!iso) return "Sin registro";
  const d = new Date(iso);
  return d.toLocaleDateString("es-CL", { day: "2-digit", month: "short", year: "numeric" });
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
          {proyecto.eventos.map((ev) => (
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
