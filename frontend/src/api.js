// Por defecto, vacío: las peticiones van a rutas relativas (/api/...) que el propio
// dev server de Vite reenvía a FastAPI (ver server.proxy en vite.config.js), evitando
// llamadas cross-origin desde el navegador. Solo se usa una URL absoluta si se define
// VITE_API_URL explícitamente (por ejemplo, para apuntar a un backend en otro host).
export const BACKEND_URL = import.meta.env.VITE_API_URL || "";
const API_BASE = `${BACKEND_URL}/api`;

// error.tipo distingue, para quien consuma la API, entre dos causas muy
// distintas de falla: "conexion" (el backend nunca respondió — caído, CORS,
// timeout, proxy que intercepta la petición) y "api" (el backend sí
// respondió, pero con un error: 404, 422, una regla de negocio). Cada
// página decide con esto qué mensaje mostrar, en vez de asumir siempre que
// cualquier error significa "no se pudo conectar".
function crearError(mensaje, tipo) {
  const error = new Error(mensaje);
  error.tipo = tipo;
  return error;
}

// El "detail" de FastAPI no siempre es un string: en errores de validación
// (422) es un array de objetos ({loc, msg, type}); en un HTTPException
// explícito del backend es un string. Sin este mapeo, un array/objeto
// terminaba como el literal "[object Object]" en pantalla.
function extraerMensajeDetail(detail, fallback) {
  if (!detail) return fallback;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    const mensajes = detail
      .map((item) => (item && typeof item === "object" ? item.msg : item))
      .filter((msg) => typeof msg === "string" && msg.trim());
    return mensajes.length ? mensajes.join("; ") : fallback;
  }
  if (typeof detail === "object") {
    return detail.msg || detail.message || fallback;
  }
  return fallback;
}

async function request(path, options) {
  let res;
  try {
    res = await fetch(`${API_BASE}${path}`, options);
  } catch {
    // fetch lanza TypeError cuando la red/CORS bloquea la petición antes de recibir respuesta
    // (backend caído, URL incorrecta, o el puerto de Codespaces no es realmente accesible).
    throw crearError(
      `No fue posible conectar con el servidor (${API_BASE}). Verifica que el backend esté corriendo y accesible en esa URL.`,
      "conexion"
    );
  }

  const contentType = res.headers.get("content-type") || "";
  if (!contentType.includes("application/json")) {
    // Típico cuando un proxy (p. ej. la página de aviso de puertos de Codespaces) intercepta
    // la petición y devuelve HTML en vez de la respuesta de la API.
    throw crearError(
      `No fue posible conectar con el servidor (${API_BASE}): respuesta inesperada (no es JSON). Abre esa URL directamente en el navegador para revisar si hay una pantalla intermedia.`,
      "conexion"
    );
  }

  const data = await res.json();
  if (!res.ok) {
    throw crearError(extraerMensajeDetail(data.detail, `Error ${res.status} al consultar ${path}`), "api");
  }
  return data;
}

export async function listarProyectos() {
  return request("/proyectos");
}

export async function verProyecto(id) {
  return request(`/proyectos/${id}`);
}

export async function actualizarProyecto(id) {
  return request(`/proyectos/${id}/actualizar`, { method: "POST" });
}
