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
    # Identificador interno que camara.cl usa para la ficha HTML de tramitación (prmID en
    # tramitacion.aspx). Fuente canónica de este dato: si es null, el monitor lo registra con
    # un warning explícito y omite esa fuente para este proyecto (ver monitor/monitor_engine.py).
    prm_id = Column(Integer)
    link_seguimiento = Column(String)
    fecha_ultima_revision = Column(DateTime)
    ultimo_analisis_ia = Column(Text)  # placeholder para el futuro análisis IA
    # Ambos opcionales: solo se completan cuando el proyecto efectivamente terminó siendo
    # ley (la mayoría de los proyectos en trámite nunca llegan a este punto). No se derivan
    # automáticamente del monitor — se cargan/verifican igual que link_seguimiento.
    url_ley_publicada = Column(String)  # ficha de la ley en LeyChile (BCN), ej. leychile.cl/navegar?idNorma=...
    fecha_vigencia = Column(DateTime)   # fecha en que la ley entra en vigencia

    # Ordenado por fecha_deteccion (DateTime real, siempre poblada por el sistema al
    # detectar el evento) y no por fecha_evento (texto libre de formato variable según
    # la fuente: "31 May. 2024", "16 Dic. 2024", ...) — ordenar por ese string hacía una
    # comparación alfabética, no cronológica, y un evento recién detectado podía terminar
    # enterrado entre eventos antiguos en vez de aparecer primero en el historial.
    eventos = relationship("Evento", back_populates="proyecto", order_by="desc(Evento.fecha_deteccion)")


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
    # Clave estable de deduplicación contra la fuente oficial (ej. "od-votacion-42178"
    # usando el <Id> real de una VotacionProyectoLey de Open Data, o una clave compuesta
    # para filas del HTML). Permite que el motor de monitoreo sepa con certeza qué
    # actuaciones ya están en el timeline y cuáles son realmente nuevas, sin comparar
    # texto. Nula para eventos históricos migrados antes de que existiera este campo.
    id_externo = Column(String, index=True)

    proyecto = relationship("Proyecto", back_populates="eventos")


def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    Base.metadata.create_all(bind=engine)
    _migrar_columnas_faltantes()


def _migrar_columnas_faltantes():
    """Migración liviana para bases de datos SQLite creadas antes de agregar
    columnas nuevas al modelo. Base.metadata.create_all() solo crea tablas
    que no existen — no altera tablas ya existentes — así que hace falta
    este paso manual para que las columnas nuevas aparezcan en instalaciones previas."""
    with engine.connect() as conn:
        columnas_eventos = {fila[1] for fila in conn.exec_driver_sql("PRAGMA table_info(eventos)")}
        if "id_externo" not in columnas_eventos:
            conn.exec_driver_sql("ALTER TABLE eventos ADD COLUMN id_externo VARCHAR")
            conn.commit()

        columnas_proyectos = {fila[1] for fila in conn.exec_driver_sql("PRAGMA table_info(proyectos)")}
        if "url_ley_publicada" not in columnas_proyectos:
            conn.exec_driver_sql("ALTER TABLE proyectos ADD COLUMN url_ley_publicada VARCHAR")
            conn.commit()
        if "fecha_vigencia" not in columnas_proyectos:
            conn.exec_driver_sql("ALTER TABLE proyectos ADD COLUMN fecha_vigencia DATETIME")
            conn.commit()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
