# -*- coding: utf-8 -*-
"""
backend/app/main.py
=======================
Observatorio Legislativo Estratégico Corfo — API backend (FastAPI).
"""
import sys
import os
import datetime
import logging

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))  # para importar monitor/ y ai/

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from typing import List

from app.database import init_db, get_db, Proyecto, Evento
from app import schemas
from monitor.monitor_engine import ejecutar_monitoreo
from ai.analysis import generar_analisis_ejecutivo

app = FastAPI(title="Observatorio Legislativo Estratégico Corfo", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    # Para el MVP en desarrollo local se permite cualquier origen: evita que un cambio de
    # puerto en Vite (5173, 5174, ...) rompa la conexión por CORS. Restringir antes de producción.
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def on_startup():
    init_db()


@app.get("/api/proyectos", response_model=List[schemas.ProyectoListOut])
def listar_proyectos(db: Session = Depends(get_db)):
    return db.query(Proyecto).order_by(Proyecto.id).all()


@app.get("/api/proyectos/{proyecto_id}", response_model=schemas.ProyectoDetailOut)
def ver_proyecto(proyecto_id: int, db: Session = Depends(get_db)):
    proyecto = db.query(Proyecto).filter(Proyecto.id == proyecto_id).first()
    if not proyecto:
        raise HTTPException(status_code=404, detail="Proyecto no encontrado")
    return proyecto


@app.post("/api/proyectos/{proyecto_id}/actualizar", response_model=schemas.ActualizarResultado)
def actualizar_proyecto(proyecto_id: int, db: Session = Depends(get_db)):
    proyecto = db.query(Proyecto).filter(Proyecto.id == proyecto_id).first()
    if not proyecto:
        raise HTTPException(status_code=404, detail="Proyecto no encontrado")

    ids_externos_existentes = {ev.id_externo for ev in proyecto.eventos if ev.id_externo}
    resultado = ejecutar_monitoreo(proyecto.boletin, proyecto.prm_id, proyecto.estado_actual, ids_externos_existentes)
    proyecto.fecha_ultima_revision = datetime.datetime.utcnow()

    if resultado["resultado"] == "error_tecnico":
        db.commit()
        return schemas.ActualizarResultado(
            resultado="error_tecnico",
            mensaje=f"Error técnico de conexión con la fuente oficial: {resultado['error']}",
            proyecto=proyecto,
        )

    if resultado["resultado"] == "sin_cambios":
        db.commit()
        return schemas.ActualizarResultado(
            resultado="sin_cambios",
            mensaje="No hubo cambios respecto del estado ya registrado.",
            proyecto=proyecto,
        )

    # nuevo_evento: puede traer uno o varios eventos nuevos (votaciones + cambio de estado)
    eventos_nuevos = resultado["eventos_nuevos"]
    for datos_evento in eventos_nuevos:
        db.add(Evento(
            proyecto_id=proyecto.id,
            fecha_deteccion=datetime.datetime.utcnow(),
            estado_revision_humana="Pendiente",
            observacion="Generado automáticamente al presionar 'Actualizar ahora'.",
            **datos_evento,
        ))

    if resultado["estado_nuevo"]:
        proyecto.estado_actual = resultado["estado_nuevo"]

    db.commit()
    db.refresh(proyecto)

    # Se genera después del commit/refresh para que el historial de eventos
    # que recibe el análisis (proyecto.eventos) incluya los eventos recién
    # detectados, no solo los previos.
    proyecto.ultimo_analisis_ia = generar_analisis_ejecutivo(proyecto)
    db.commit()
    db.refresh(proyecto)

    if resultado["estado_nuevo"]:
        mensaje = (
            f"Se detectaron {len(eventos_nuevos)} evento(s) nuevo(s): el estado cambió a "
            f"\"{resultado['estado_nuevo']}\"."
        )
    else:
        mensaje = f"Se detectaron {len(eventos_nuevos)} evento(s) nuevo(s) en el historial de tramitación."

    return schemas.ActualizarResultado(
        resultado="nuevo_evento",
        mensaje=mensaje,
        proyecto=proyecto,
    )


@app.post("/api/eventos", response_model=schemas.EventoOut)
def registrar_evento(evento: schemas.EventoCreate, db: Session = Depends(get_db)):
    proyecto = db.query(Proyecto).filter(Proyecto.id == evento.proyecto_id).first()
    if not proyecto:
        raise HTTPException(status_code=404, detail="Proyecto no encontrado")
    nuevo = Evento(**evento.dict(), fecha_deteccion=datetime.datetime.utcnow(),
                   estado_revision_humana="Pendiente")
    db.add(nuevo)
    db.commit()
    db.refresh(nuevo)
    return nuevo


@app.get("/api/health")
def health():
    return {"status": "ok"}
