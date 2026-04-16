import time
import redis
import os
import traceback
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

# ---------------------------------------------------------
# Modelos para el Worker

class Video(Base):
    __tablename__ = "video" 
    id = Column(Integer, primary_key=True)
    estado = Column(String)

class Deteccion(Base):
    __tablename__ = "deteccion"
    id = Column(Integer, primary_key=True)
    video_id = Column(Integer, ForeignKey("video.id"))
    geom = Column(Geometry('POINT', srid=4326))
    tipo_dano = Column(String)
    confianza = Column(Float)
    frame_minio_path = Column(String, nullable=True)
    estado_auditoria = Column(String, default="pendiente")
    fecha_deteccion = Column(DateTime, default=datetime.utcnow)

# Conexión a Redis
try:
    r = redis.Redis(host=REDIS_HOST, port=6379, db=0)
    r.ping()
    print("Worker iniciado y conectado a Redis, esperando tareas...")
except Exception as e:
    print(f"Error crítico: No se pudo conectar a Redis. {e}")
    exit(1)

while True:
    try:
        resultado = r.blpop("tareas_video")
        if not resultado:
            continue
            
        mensaje = resultado[1]
        video_id = int(mensaje.decode('utf-8'))
        
        print(f"\n[*] Recibida tarea para Procesar Video ID: {video_id}")
        db = SessionLocal()
        
        try:
            # 1. Buscar video y cambiar estado a 'procesando'
            video = db.query(Video).filter(Video.id == video_id).first()
            if not video:
                print(f"[!] Error: No se encontró el video {video_id} en la BD.")
                continue

            video.estado = "procesando"
            db.commit()
            print(f"    -> Estado actualizado a 'procesando'")

            # 2. Simular tiempo de YOLO (5 segundos)
            print(f"    -> Simulando inferencia de IA (5 seg)...")
            time.sleep(5)

            # 3. Insertar bache falso (Mock) en Moreno
            punto_moreno = Point(-58.79, -34.65) # Coordenadas fake
            nueva_deteccion = Deteccion(
                video_id=video_id,
                geom=from_shape(punto_moreno, srid=4326),
                tipo_dano="bache",
                confianza=0.85,
                frame_minio_path=f"frames/{video_id}/deteccion_1.jpg",
                estado_auditoria="pendiente"
            )
            db.add(nueva_deteccion)

            # 4. Finalizar con éxito
            video.estado = "procesado"
            db.commit()
            print(f"[V] Video {video_id} finalizado con éxito.")

        except Exception as e:
            db.rollback()
            print(f"[X] Error procesando el video {video_id}: {str(e)}")
            traceback.print_exc() 
            
            if 'video' in locals() and video:
                try:
                    video.estado = "error"
                    db.commit()
                except Exception:
                    pass

        finally:
            db.close()

    except Exception as general_error:
        print(f"[X] Error general en el loop del worker: {general_error}")
        time.sleep(2)
