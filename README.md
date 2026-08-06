# Observatorio Legislativo Estratégico Corfo — MVP

Aplicación web (backend + frontend + base de datos propia) para monitorear estratégicamente
proyectos de ley relevantes para Corfo. Este MVP incluye 3 proyectos reales de prueba:
**AFIDE (16889-05)**, **Transferencia Tecnológica (16686-19)** y **Desalinización (11608-09)**.

El Excel ya no es la base de datos del sistema — solo se usó para cargar la información
inicial (`scripts/seed_db.py`). Toda la información vive ahora en `database/observatorio.db`
(SQLite).

## Estructura del proyecto

```
observatorio-legislativo/
  backend/    → API FastAPI (modelos, endpoints)
  frontend/   → Interfaz web (React + Vite)
  database/   → Base de datos SQLite (se genera sola)
  monitor/    → Motor de monitoreo (consulta camara.cl, compara estado)
  ai/         → Análisis Ejecutivo IA (llamada real a la API de Claude/Anthropic)
  scripts/    → Script de carga inicial de datos
```

## Cómo ejecutarlo

### 1. Backend

```bash
cd backend
pip install -r requirements.txt
```

Cargar los datos iniciales (solo la primera vez):

```bash
cd ..
python scripts/seed_db.py
```

Levantar la API:

```bash
cd backend
uvicorn app.main:app --reload
```

La API queda disponible en `http://127.0.0.1:8000` (documentación interactiva en
`http://127.0.0.1:8000/docs`).

### 2. Frontend

En otra terminal:

```bash
cd frontend
npm install
npm run dev
```

Abrir en el navegador: **http://localhost:5173**

## Qué vas a poder hacer

1. Ver el listado de los 3 proyectos, con buscador y filtro por prioridad.
2. Entrar al detalle de cualquiera (estado, descripción, comentario estratégico).
3. Ver su línea de tiempo de eventos históricos.
4. Presionar **"Actualizar ahora"** — esto ejecuta el motor de monitoreo real contra
   `camara.cl` para ese boletín, y muestra uno de tres resultados:
   - **Sin cambios**
   - **Nuevo evento detectado** (y se agrega automáticamente a la línea de tiempo)
   - **Error técnico de conexión** (si la fuente oficial no responde)

## Nota importante sobre "Actualizar ahora"

El motor (`monitor/monitor_engine.py`) usa un `prmID` fijo por boletín (documentado en el
propio archivo) mientras se resuelve la obtención 100% automática de ese identificador
(ver investigación de la etapa anterior). Si ejecutas la app desde un entorno sin acceso
normal a internet, el botón mostrará "Error técnico de conexión" — es el comportamiento
esperado y correcto, no un bug: el sistema nunca debe fingir un resultado que no pudo
verificar.

## Análisis Ejecutivo IA

Al abrir la ficha de un proyecto, si todavía no tiene un análisis generado, el backend
llama en vivo a la API de Claude (`ai/analysis.py`) para generar el "🤖 Análisis Ejecutivo
IA": 6 bloques breves (objetivo, problema que busca resolver, aspectos principales,
implicancias para Corfo, estado del debate legislativo, conclusión ejecutiva), construidos
**exclusivamente** a partir de la información oficial que el propio Observatorio ya
recopiló (descripción, estado actual, historial de eventos) — nunca de fuentes externas ni
del conocimiento general del modelo. Una vez generado queda almacenado y no se vuelve a
pedir; se regenera solo cuando `actualizar_proyecto()` detecta un cambio de estado o un
evento nuevo.

### Configurar la API key (requerido para que funcione)

El backend lee la key **únicamente** desde la variable de entorno `ANTHROPIC_API_KEY` — no
existe ningún valor hardcodeado en el código ni se lee desde ningún archivo versionado.
Si la variable no está configurada, el análisis no falla ni inventa contenido: cada bloque
muestra "No se encontró información suficiente para este apartado.".

**En GitHub Codespaces** (recomendado, la key nunca queda en el repo ni en el filesystem del
Codespace):

1. En GitHub, ve a **Settings → Secrets and variables → Codespaces** del repositorio (o a
   tu configuración personal de Codespaces si prefieres que aplique a todos tus repos).
2. **New repository secret** → nombre exacto `ANTHROPIC_API_KEY` → pega tu key de
   [console.anthropic.com](https://console.anthropic.com/) → **Add secret**.
3. Si el Codespace ya estaba abierto, hay que reconstruirlo o reiniciarlo (**Codespaces →
   ⋯ → Rebuild Container**, o simplemente detenerlo y volver a abrirlo) para que la variable
   quede disponible en el entorno.

**En local**, expórtala en la terminal antes de levantar el backend:

```bash
export ANTHROPIC_API_KEY=tu_key_aqui
```

Ver también `.env.example` en la raíz del proyecto (documentación de referencia; el backend
no carga archivos `.env` automáticamente).
