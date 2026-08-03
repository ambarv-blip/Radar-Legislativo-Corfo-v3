import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { listarProyectos, BACKEND_URL } from "../api";

// Escala de avance del trámite -> color institucional.
// Cuanto más avanzado el trámite, más se acerca al color de acento (dorado Corfo);
// las etapas tempranas usan azules más suaves. Se recalcula cada vez que "Actualizar
// ahora" cambia el Estado de un proyecto, por eso vive en el mismo lugar que la tabla.
function estiloEstado(estado) {
  const e = (estado || "").toLowerCase();
  if (e.includes("ley") || e.includes("promulg") || e.includes("public") || e.includes("terminada")) {
    return { clase: "estado-pill estado-terminado", texto: estado };
  }
  if (e.includes("aprobación presidencial")) {
    return { clase: "estado-pill estado-presidencial", texto: estado };
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
  return { clase: "estado-pill estado-sin-info", texto: estado || "Sin información" };
}

export default function Home() {
  const [proyectos, setProyectos] = useState([]);
  const [cargando, setCargando] = useState(true);
  const [error, setError] = useState(null);
  const [busqueda, setBusqueda] = useState("");
  const [filtroPrioridad, setFiltroPrioridad] = useState("Todas");

  useEffect(() => {
    listarProyectos()
      .then(setProyectos)
      .catch((e) => setError(e.message))
      .finally(() => setCargando(false));
  }, []);

  const filtrados = proyectos.filter((p) => {
    const coincideTexto =
      p.nombre.toLowerCase().includes(busqueda.toLowerCase()) ||
      p.boletin.toLowerCase().includes(busqueda.toLowerCase());
    const coincidePrioridad = filtroPrioridad === "Todas" || p.prioridad_monitoreo === filtroPrioridad;
    return coincideTexto && coincidePrioridad;
  });

  return (
    <>
      <div className="buscador">
        <input
          type="text"
          placeholder="Buscar por nombre o boletín..."
          value={busqueda}
          onChange={(e) => setBusqueda(e.target.value)}
        />
        <select value={filtroPrioridad} onChange={(e) => setFiltroPrioridad(e.target.value)}>
          <option>Todas</option>
          <option>Crítica</option>
          <option>Alta</option>
          <option>Media</option>
          <option>Baja</option>
        </select>
      </div>

      {cargando && <p className="vacio">Cargando proyectos...</p>}
      {error && (
        <p className="vacio">
          No se pudo conectar con el backend ({error}). Revisa que <code>uvicorn app.main:app --reload</code> esté
          corriendo en <code>{BACKEND_URL}</code>.
        </p>
      )}

      {!cargando && !error && (
        <table className="tabla-proyectos">
          <thead>
            <tr>
              <th>Nombre Proyecto</th>
              <th>Código Boletín</th>
              <th>Año de ingreso</th>
              <th>Estado</th>
            </tr>
          </thead>
          <tbody>
            {filtrados.length === 0 && (
              <tr>
                <td colSpan={4} className="vacio">No hay proyectos que coincidan con la búsqueda.</td>
              </tr>
            )}
            {filtrados.map((p) => {
              const estado = estiloEstado(p.estado_actual);
              return (
                <tr key={p.id}>
                  <td>
                    <Link to={`/proyectos/${p.id}`} className="link-proyecto">{p.nombre}</Link>
                  </td>
                  <td className="boletin-celda">
                    {p.link_seguimiento ? (
                      <a
                        href={p.link_seguimiento}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="link-boletin"
                        title="Ver ficha de tramitación oficial (Cámara de Diputados)"
                      >
                        {p.boletin} ↗
                      </a>
                    ) : (
                      p.boletin
                    )}
                  </td>
                  <td>{p.anio_ingreso || "—"}</td>
                  <td>
                    <span className={estado.clase}>{estado.texto}</span>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      )}
    </>
  );
}
