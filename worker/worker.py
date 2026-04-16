import time
import redis
import os
import json
from datetime import datetime
from sqlalchemy import create_engine, Column, Integer, String, Float, ForeignKey, DateTime
from sqlalchemy.orm import sessionmaker, declarative_base
from geoalchemy2 import Geometry
from geoalchemy2.shape import from_shape
from shapely.geometry import Point

# Configuración
REDIS_HOST = os.getenv("REDIS_HOST", "redis_queue")
DATABASE_URL = os.getenv("DATABASE_URL")

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()

# Definición de tablas para que el worker pueda escribir
class Video(Base):
    __tablename__ = "videos_ingresados"
    id = Column(Integer, primary_key=True)
    estado = Column(String)

class Deteccion(Base):
    __tablename__ = "detecciones"
    id = Column(Integer, primary_key=True)
    video_id = Column(Integer, ForeignKey("videos_ingresados.id"))
    ubicacion = Column(Geometry('POINT', srid=4326))
    tipo = Column(String)
    confianza = Column(Float)
    fecha_deteccion = Column(DateTime, default=datetime.utcnow)

# Conexión a Redis
r = redis.Redis(host=REDIS_HOST, port=6379, db=0)

print("Worker iniciado, esperando tareas...")

while True:
    # BLPOP bloquea hasta que haya un mensaje en la cola 'tareas_video'
    # blpop devuelve una tupla (cola, mensaje)
    resultado = r.blpop("tareas_video")
    if not resultado:
        continue
        
    mensaje = resultado[1]
    video_id = int(mensaje.decode('utf-8'))
    
    print(f"[*] Procesando Video ID: {video_id}")
    db = SessionLocal()
    
    # 1. Cambiar estado a 'procesando'
    video = db.query(Video).filter(Video.id == video_id).first()
    if video:
        video.estado = "procesando"
        db.commit()

        # 2. Simular tiempo de YOLO (5 segundos)
        time.sleep(5)

        # 3. Insertar bache falso (Mock) en Moreno
        punto_moreno = Point(-58.79, -34.65) # Coordenadas fake
        nueva_deteccion = Deteccion(
            video_id=video_id,
            ubicacion=from_shape(punto_moreno, srid=4326),
            tipo="bache",
            confianza=0.85
        )
        db.add(nueva_deteccion)

        # 4. Finalizar
        video.estado = "procesado"
        db.commit()
        print(f"[V] Video {video_id} finalizado.")
    
    db.close()