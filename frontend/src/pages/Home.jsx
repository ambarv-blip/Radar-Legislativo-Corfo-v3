import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { listarProyectos, actualizarProyecto, BACKEND_URL } from "../api";

// Escala de avance del trámite -> color institucional.
// Cuanto más avanzado el trámite, más se acerca al color de acento (dorado Corfo);
// las etapas tempranas usan azules más suaves. Se recalcula cada vez que "Actualizar
// ahora" cambia el Estado de un proyecto, por eso vive en el mismo lugar que la tabla.
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

// Clasificación específica para la tarjeta "Leyes vigentes" del panel de
// indicadores — deliberadamente MÁS ESTRECHA que el bucket "estado-terminado"
// de estiloEstado() (que también agrupa "promulg", "public", "despachado"):
// aquí solo cuenta lo que el pedido definió como ley vigente ("Tramitación
// terminada" o que contenga "Ley N°"). No reutiliza estiloEstado() porque son
// dos preguntas distintas (cómo pintar la cápsula vs. qué cuenta como ley para
// el indicador), pero tampoco se vuelve a escribir en otro lugar del código.
function esLeyVigente(estado) {
  const e = (estado || "").toLowerCase();
  return e.includes("tramitación terminada") || e.includes("ley n°");
}

function formatearFechaHora(fecha) {
  if (!fecha) return "Sin registro";
  return fecha.toLocaleString("es-CL", {
    day: "2-digit", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit",
  });
}

export default function Home() {
  const [proyectos, setProyectos] = useState([]);
  const [cargando, setCargando] = useState(true);
  const [error, setError] = useState(null);
  const [busqueda, setBusqueda] = useState("");
  const [filtroPrioridad, setFiltroPrioridad] = useState("Todas");
  const [actualizando, setActualizando] = useState(false);
  const [estadoActualizacion, setEstadoActualizacion] = useState(null);
  const [progreso, setProgreso] = useState(null); // { actual, total } | null — solo mientras dura el ciclo

  useEffect(() => {
    listarProyectos()
      .then(setProyectos)
      .catch((e) => setError({ tipo: e.tipo || "conexion", mensaje: e.message }))
      .finally(() => setCargando(false));
  }, []);

  // Reutiliza la misma llamada por-proyecto que antes disparaba el botón
  // dentro de la ficha (actualizarProyecto en api.js) — no existe un
  // endpoint de actualización masiva en el backend, así que se consulta la
  // fuente oficial de cada proyecto monitoreado, uno a la vez, y al final
  // se recarga el listado completo desde el backend.
  //
  // El backend responde HTTP 200 incluso cuando la consulta a la fuente
  // oficial falló (resultado === "error_tecnico" — ver
  // backend/app/main.py): actualizarProyecto() no lanza excepción en ese
  // caso, así que un fallo de negocio no se puede detectar solo con
  // try/catch. Hay que revisar el campo `resultado` de cada respuesta.
  async function handleActualizarTodos() {
    setActualizando(true);
    setEstadoActualizacion(null);
    const total = proyectos.length;
    let exitosos = 0;
    let fallidos = 0;
    for (let i = 0; i < proyectos.length; i++) {
      // Progreso real por proyecto: la actualización masiva es secuencial
      // (no hay endpoint bulk en el backend, ver comentario más abajo) y
      // cada consulta a la fuente oficial puede tardar varios segundos —
      // sin esto el botón se queda en "Actualizando..." fijo sin indicar
      // si avanza o está colgado.
      setProgreso({ actual: i + 1, total });
      try {
        const r = await actualizarProyecto(proyectos[i].id);
        if (r.resultado === "error_tecnico") {
          fallidos += 1;
        } else {
          exitosos += 1;
        }
      } catch {
        // Fallo real de conexión/API con ese proyecto puntual (no solo un
        // "error_tecnico" de negocio) — igualmente cuenta como fallido.
        fallidos += 1;
      }
    }
    setProgreso(null);
    try {
      setProyectos(await listarProyectos());
    } catch (e) {
      setEstadoActualizacion({ tipo: "error_tecnico", mensaje: `No se pudo recargar el listado: ${e.message}` });
      setActualizando(false);
      return;
    }

    if (fallidos === 0) {
      setEstadoActualizacion({ tipo: "sin_cambios", mensaje: "Actualización completada correctamente" });
    } else if (exitosos === 0) {
      setEstadoActualizacion({ tipo: "error_tecnico", mensaje: "No fue posible actualizar los proyectos" });
    } else {
      setEstadoActualizacion({
        tipo: "nuevo_evento",
        mensaje: `Actualización completada con errores (${fallidos} proyecto${fallidos === 1 ? "" : "s"} fallaron)`,
      });
    }
    setActualizando(false);
  }

  const filtrados = proyectos.filter((p) => {
    const coincideTexto =
      p.nombre.toLowerCase().includes(busqueda.toLowerCase()) ||
      p.boletin.toLowerCase().includes(busqueda.toLowerCase());
    const coincidePrioridad = filtroPrioridad === "Todas" || p.prioridad_monitoreo === filtroPrioridad;
    return coincideTexto && coincidePrioridad;
  });

  // Panel ejecutivo de indicadores — se calcula a partir de `proyectos`, el mismo
  // estado ya cargado por listarProyectos() para la tabla de abajo; no hay una
  // segunda consulta ni una fuente de datos distinta.
  const totalProyectos = proyectos.length;
  const leyesVigentes = proyectos.filter((p) => esLeyVigente(p.estado_actual)).length;
  const enTramitacion = totalProyectos - leyesVigentes;
  const ultimaActualizacion = proyectos.reduce((masReciente, p) => {
    if (!p.fecha_ultima_revision) return masReciente;
    const fecha = new Date(p.fecha_ultima_revision);
    return !masReciente || fecha > masReciente ? fecha : masReciente;
  }, null);

  return (
    <>
      {!cargando && !error && (
        <div className="panel-indicadores">
          <div className="tarjeta-indicador tarjeta-indicador--total">
            <div className="numero">{totalProyectos}</div>
            <div className="titulo">Total de proyectos</div>
          </div>
          <div className="tarjeta-indicador tarjeta-indicador--vigentes">
            <div className="numero">{leyesVigentes}</div>
            <div className="titulo">Leyes vigentes</div>
          </div>
          <div className="tarjeta-indicador tarjeta-indicador--tramite">
            <div className="numero">{enTramitacion}</div>
            <div className="titulo">En tramitación</div>
          </div>
          <div className="tarjeta-indicador tarjeta-indicador--actualizacion">
            <div className="numero numero--fecha">{formatearFechaHora(ultimaActualizacion)}</div>
            <div className="titulo">Última actualización</div>
          </div>
        </div>
      )}

      <div style={{ marginBottom: 16 }}>
        <button
          className="btn-actualizar"
          onClick={handleActualizarTodos}
          disabled={actualizando || cargando || !!error || proyectos.length === 0}
        >
          {actualizando
            ? progreso
              ? `Actualizando proyecto ${progreso.actual} de ${progreso.total}...`
              : "Actualizando..."
            : "Actualizar ahora"}
        </button>
        {estadoActualizacion && (
          <div className={`resultado-actualizacion ${estadoActualizacion.tipo}`}>
            {estadoActualizacion.tipo === "sin_cambios" && "✓ "}
            {estadoActualizacion.tipo === "nuevo_evento" && "⚠ "}
            {estadoActualizacion.tipo === "error_tecnico" && "❌ "}
            {estadoActualizacion.mensaje}
          </div>
        )}
      </div>

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
          {/* error.mensaje ya viene con la redacción correcta según el tipo (ver api.js:
              "conexion" arma su propio mensaje "No fue posible conectar con el servidor...";
              "api" es el mensaje que entregó el backend) — no hay que re-envolverlo. Solo se
              agrega la sugerencia de diagnóstico cuando el problema es realmente de conexión. */}
          {error.mensaje}
          {error.tipo === "conexion" && (
            <>
              {" "}
              Revisa que <code>uvicorn app.main:app --reload</code> esté corriendo en{" "}
              <code>{BACKEND_URL || "http://127.0.0.1:8000"}</code>.
            </>
          )}
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
