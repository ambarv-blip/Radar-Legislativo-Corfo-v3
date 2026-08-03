# -*- coding: utf-8 -*-
"""Esquemas Pydantic (entrada/salida de la API)."""
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime


class EventoOut(BaseModel):
    id: int
    fecha_evento: Optional[str] = None
    fecha_deteccion: Optional[datetime] = None
    tipo_evento: Optional[str] = None
    descripcion: Optional[str] = None
    estado_anterior: Optional[str] = None
    estado_nuevo: Optional[str] = None
    fuente: Optional[str] = None
    enlace: Optional[str] = None
    nivel_alerta: Optional[str] = None
    estado_revision_humana: Optional[str] = None
    observacion: Optional[str] = None

    class Config:
        from_attributes = True


class ProyectoListOut(BaseModel):
    id: int
    boletin: str
    nombre: str
    anio_ingreso: Optional[int] = None
    estado_actual: Optional[str] = None
    prioridad_monitoreo: Optional[str] = None
    fecha_ultima_revision: Optional[datetime] = None
    link_seguimiento: Optional[str] = None

    class Config:
        from_attributes = True


class ProyectoDetailOut(BaseModel):
    id: int
    boletin: str
    nombre: str
    anio_ingreso: Optional[int] = None
    camara_origen: Optional[str] = None
    estado_actual: Optional[str] = None
    descripcion: Optional[str] = None
    comentario_estrategico: Optional[str] = None
    prioridad_monitoreo: Optional[str] = None
    link_seguimiento: Optional[str] = None
    fecha_ultima_revision: Optional[datetime] = None
    ultimo_analisis_ia: Optional[str] = None
    eventos: List[EventoOut] = []

    class Config:
        from_attributes = True


class ActualizarResultado(BaseModel):
    resultado: str  # "sin_cambios" | "nuevo_evento" | "error_tecnico"
    mensaje: str
    proyecto: Optional[ProyectoDetailOut] = None


class EventoCreate(BaseModel):
    proyecto_id: int
    fecha_evento: Optional[str] = None
    tipo_evento: Optional[str] = None
    descripcion: Optional[str] = None
    estado_anterior: Optional[str] = None
    estado_nuevo: Optional[str] = None
    fuente: Optional[str] = None
    enlace: Optional[str] = None
    nivel_alerta: Optional[str] = None
    observacion: Optional[str] = None
