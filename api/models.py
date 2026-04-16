from sqlalchemy import Column, Integer, String, DateTime
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
    tipo = Column(String)
    ubicacion = Column(Geometry(geometry_type='POINT', srid=4326))
    fecha_deteccion = Column(DateTime, default=datetime.utcnow)
    video_id = Column(Integer)

