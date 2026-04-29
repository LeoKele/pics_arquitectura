from datetime import datetime

from database import Base
from geoalchemy2 import Geometry
from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, String, Text


class Video(Base):
    __tablename__ = "video"
    id = Column(Integer, primary_key=True, index=True)
    nombre_archivo = Column(String, index=True)
    nombre_metadata = Column(String)
    estado = Column(String, default="pendiente")
    fecha_ingreso = Column(DateTime, default=datetime.utcnow)


class Deteccion(Base):
    __tablename__ = "deteccion"
    id = Column(Integer, primary_key=True, index=True)
    video_id = Column(Integer, ForeignKey("video.id"))
    geom = Column(Geometry(geometry_type="POINT", srid=4326))
    tipo_dano = Column(String)
    confianza = Column(Float)
    frame_minio_path = Column(String, nullable=True)
    estado_auditoria = Column(String, default="pendiente")
    fecha_deteccion = Column(DateTime, default=datetime.utcnow)


# Ollama
class Reporte(Base):
    __tablename__ = "reporte"
    id = Column(Integer, primary_key=True)
    video_id = Column(Integer, ForeignKey("video.id"), nullable=True, unique=True)
    contenido = Column(String)
    fecha_generacion = Column(DateTime, default=datetime.utcnow)
