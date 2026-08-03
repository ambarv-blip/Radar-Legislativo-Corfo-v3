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
  ai/         → Placeholder de análisis IA (a integrar en un ciclo posterior)
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

## Placeholder de IA

El campo "Último análisis IA" en el detalle de cada proyecto es, por ahora, un texto fijo
(`ai/analysis.py`) que se actualiza cuando se detecta un evento nuevo. En un ciclo
posterior, esta función llamará a la API de Claude para generar el análisis estructurado
real.
