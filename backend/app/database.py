# -*- coding: utf-8 -*-
"""Modelos de base de datos del Observatorio Legislativo Estratégico Corfo."""
from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime, ForeignKey
from sqlalchemy.orm import declarative_base, relationship, sessionmaker
import os

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "database", "observatorio.db")
DATABASE_URL = f"sqlite:///{DB_PATH}"

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


class Proyecto(Base):
    __tablename__ = "proyectos"

    id = Column(Integer, primary_key=True, index=True)
    boletin = Column(String, unique=True, index=True, nullable=False)
    nombre = Column(String, nullable=False)
    anio_ingreso = Column(Integer)
    camara_origen = Column(String)
    estado_actual = Column(String)
    descripcion = Column(Text)
    comentario_estrategico = Column(Text)
    prioridad_monitoreo = Column(String)
    prm_id = Column(Integer)  # identificador interno del sitio de la Cámara (temporal, ver monitor/)
    link_seguimiento = Column(String)
    fecha_ultima_revision = Column(DateTime)
    ultimo_analisis_ia = Column(Text)  # placeholder para el futuro análisis IA

    eventos = relationship("Evento", back_populates="proyecto", order_by="desc(Evento.fecha_evento)")


class Evento(Base):
    __tablename__ = "eventos"

    id = Column(Integer, primary_key=True, index=True)
    proyecto_id = Column(Integer, ForeignKey("proyectos.id"), nullable=False)
    fecha_evento = Column(String)  # se guarda como texto (formato variable de la fuente oficial)
    fecha_deteccion = Column(DateTime)
    tipo_evento = Column(String)
    descripcion = Column(Text)
    estado_anterior = Column(String)
    estado_nuevo = Column(String)
    fuente = Column(String)
    enlace = Column(String)
    nivel_alerta = Column(String)
    estado_revision_humana = Column(String, default="Pendiente")
    observacion = Column(Text)

    proyecto = relationship("Proyecto", back_populates="eventos")


def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    Base.metadata.create_all(bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
