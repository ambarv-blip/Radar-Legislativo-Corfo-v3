// Por defecto, vacío: las peticiones van a rutas relativas (/api/...) que el propio
// dev server de Vite reenvía a FastAPI (ver server.proxy en vite.config.js), evitando
// llamadas cross-origin desde el navegador. Solo se usa una URL absoluta si se define
// VITE_API_URL explícitamente (por ejemplo, para apuntar a un backend en otro host).
export const BACKEND_URL = import.meta.env.VITE_API_URL || "";
const API_BASE = `${BACKEND_URL}/api`;

async function request(path, options) {
  let res;
  try {
    res = await fetch(`${API_BASE}${path}`, options);
  } catch {
    // fetch lanza TypeError cuando la red/CORS bloquea la petición antes de recibir respuesta
    // (backend caído, URL incorrecta, o el puerto de Codespaces no es realmente accesible).
    throw new Error(`No se pudo alcanzar ${API_BASE} (red/CORS). Verifica que el backend esté corriendo y accesible en esa URL.`);
  }

  const contentType = res.headers.get("content-type") || "";
  if (!contentType.includes("application/json")) {
    // Típico cuando un proxy (p. ej. la página de aviso de puertos de Codespaces) intercepta
    // la petición y devuelve HTML en vez de la respuesta de la API.
    throw new Error(`Respuesta inesperada de ${API_BASE} (no es JSON). Abre esa URL directamente en el navegador para revisar si hay una pantalla intermedia.`);
  }

  const data = await res.json();
  if (!res.ok) {
    throw new Error(data.detail || `Error ${res.status} al consultar ${path}`);
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
