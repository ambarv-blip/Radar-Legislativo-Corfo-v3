const API_BASE = "http://127.0.0.1:8000/api";

export async function listarProyectos() {
  const res = await fetch(`${API_BASE}/proyectos`);
  if (!res.ok) throw new Error("Error al listar proyectos");
  return res.json();
}

export async function verProyecto(id) {
  const res = await fetch(`${API_BASE}/proyectos/${id}`);
  if (!res.ok) throw new Error("Error al obtener el proyecto");
  return res.json();
}

export async function actualizarProyecto(id) {
  const res = await fetch(`${API_BASE}/proyectos/${id}/actualizar`, { method: "POST" });
  if (!res.ok) throw new Error("Error al actualizar el proyecto");
  return res.json();
}
