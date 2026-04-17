import logging
import os
import time
import traceback
from datetime import datetime

import redis
from geoalchemy2 import Geometry
from geoalchemy2.shape import from_shape
from shapely.geometry import Point
from sqlalchemy import (
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    create_engine,
)
from sqlalchemy.orm import declarative_base, sessionmaker

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
)
logger = logging.getLogger("worker")


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
    geom = Column(Geometry("POINT", srid=4326))
    tipo_dano = Column(String)
    confianza = Column(Float)
    frame_minio_path = Column(String, nullable=True)
    estado_auditoria = Column(String, default="pendiente")
    fecha_deteccion = Column(DateTime, default=datetime.utcnow)


# Conexión a Redis
try:
    r = redis.Redis(host=REDIS_HOST, port=6379, db=0)
    r.ping()
    logger.info("Worker iniciado y conectado a Redis, esperando tareas...")
except Exception as e:
    logger.critical(f"No se pudo conectar a Redis: {e}")
    exit(1)

while True:
    try:
        resultado = r.blpop("tareas_video")
        if not resultado:
            continue

        mensaje = resultado[1]
        video_id = int(mensaje.decode("utf-8"))
        logger.info(f"Tarea recibida para video ID: {video_id}")

        db = SessionLocal()
        try:
            video = db.query(Video).filter(Video.id == video_id).first()
            if not video:
                logger.warning(
                    f"Video ID {video_id} no encontrado en BD, descartando tarea"
                )
                continue

            video.estado = "procesando"
            db.commit()
            logger.info(f"Video ID {video_id} → estado: procesando")

            logger.info(f"Video ID {video_id} → iniciando inferencia de IA")
            time.sleep(5)

            punto_moreno = Point(-58.79, -34.65)
            nueva_deteccion = Deteccion(
                video_id=video_id,
                geom=from_shape(punto_moreno, srid=4326),
                tipo_dano="bache",
                confianza=0.85,
                frame_minio_path=f"frames/{video_id}/deteccion_1.jpg",
                estado_auditoria="pendiente",
            )
            db.add(nueva_deteccion)

            video.estado = "procesado"
            db.commit()
            logger.info(f"Video ID {video_id} → estado: procesado. Detección guardada.")

        except Exception as e:
            db.rollback()
            logger.error(f"Error procesando video ID {video_id}: {e}")
            logger.debug(traceback.format_exc())

            if "video" in locals() and video:
                try:
                    video.estado = "error"
                    db.commit()
                    logger.warning(f"Video ID {video_id} → estado: error")
                except Exception:
                    pass

        finally:
            db.close()

    except Exception as general_error:
        logger.error(f"Error general en el loop del worker: {general_error}")
        time.sleep(2)
