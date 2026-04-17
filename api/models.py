from sqlalchemy import Column, Integer, String, DateTime, Float, ForeignKey
from geoalchemy2 import Geometry
from datetime import datetime
from database import Base

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
    geom = Column(Geometry(geometry_type='POINT', srid=4326))
    tipo_dano = Column(String)
    confianza = Column(Float)
    frame_minio_path = Column(String, nullable=True)
    estado_auditoria = Column(String, default="pendiente")
    fecha_deteccion = Column(DateTime, default=datetime.utcnow)

# Ollama ----------------------

class Reporte(Base):
    __tablename__ = "reportes"
    id = Column(Integer, primary_key=True, index=True)
    video_id = Column(Integer, index=True)
    contenido = Column(String)
    fecha_generacion = Column(DateTime, default=datetime.utcnow)

