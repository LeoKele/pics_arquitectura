import logging
import os
import time
import traceback

import cv2
import numpy as np
import redis
from minio import Minio
from sqlalchemy import Column, Integer, String, create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] PRE-WORKER - %(message)s"
)
logger = logging.getLogger("worker-preprocesamiento")

REDIS_HOST = os.getenv("REDIS_HOST", "redis_queue")
DATABASE_URL = os.getenv("DATABASE_URL")

minio_client = Minio(
    "almacenamiento-objetos:9000",
    access_key=os.getenv("MINIO_ROOT_USER", "minioadmin"),
    secret_key=os.getenv("MINIO_ROOT_PASSWORD", "minioadmin"),
    secure=False,
)
BUCKET_NAME = "videos-crudos"

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()


class Video(Base):
    __tablename__ = "video"
    id = Column(Integer, primary_key=True)
    nombre_archivo = Column(String)
    estado = Column(String)


try:
    r = redis.Redis(host=REDIS_HOST, port=6379, db=0)
    r.ping()
    logger.info("Worker de Pre-procesamiento conectado. Esperando videos crudos...")
except Exception as e:
    logger.critical(f"Error conectando a Redis: {e}")
    exit(1)


def es_imagen_borrosa(frame, umbral=30.0):
    """Calcula la varianza del Laplaciano. Si es muy baja, la imagen está movida/borrosa."""
    gris = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    varianza = cv2.Laplacian(gris, cv2.CV_64F).var()
    return varianza < umbral


def es_imagen_oscura(frame, umbral=15.0):
    """Calcula el brillo promedio. Si es muy bajo, es de noche o no se ve nada."""
    gris = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    brillo_promedio = np.mean(gris)
    return brillo_promedio < umbral


while True:
    try:
        resultado = r.blpop("cola_preprocesamiento")
        if not resultado:
            continue

        video_id = int(resultado[1].decode("utf-8"))
        logger.info(f"--- Iniciando pre-procesamiento del video ID: {video_id} ---")

        db = SessionLocal()
        try:
            video = db.query(Video).filter(Video.id == video_id).first()
            if not video:
                continue

            ruta_original = f"/tmp/crudo_{video_id}.mp4"
            logger.info(f"Descargando {video.nombre_archivo} desde MinIO...")
            minio_client.fget_object(BUCKET_NAME, video.nombre_archivo, ruta_original)

            cap = cv2.VideoCapture(ruta_original)
            frame_count = 0
            frames_guardados = 0

            frame_anterior_gris = None

            if not minio_client.bucket_exists("frames-procesados"):
                minio_client.make_bucket("frames-procesados")

            logger.info("Extrayendo frames y enviando a MinIO...")

            width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            es_vertical = height > width
            if es_vertical:
                logger.info(
                    f"Video vertical detectado ({width}x{height}). Se aplicará rotación automática."
                )

            while cap.isOpened():
                ret, frame = cap.read()
                if not ret:
                    break

                if es_vertical:
                    frame = cv2.rotate(frame, cv2.ROTATE_90_COUNTERCLOCKWISE)

                frame_count += 1
                if frame_count % 6 != 0:
                    continue

                gris_actual = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                if frame_anterior_gris is not None:
                    diff = cv2.absdiff(frame_anterior_gris, gris_actual)
                    _, thresh = cv2.threshold(diff, 25, 255, cv2.THRESH_BINARY)
                    porcentaje_cambio = (np.count_nonzero(thresh) / thresh.size) * 100

                    if porcentaje_cambio < 2.0:
                        continue

                frame_anterior_gris = gris_actual

                tiempo_ms = int(cap.get(cv2.CAP_PROP_POS_MSEC))

                nombre_frame = f"frame_{tiempo_ms}.jpg"
                ruta_local = f"/tmp/{nombre_frame}"
                cv2.imwrite(ruta_local, frame)

                minio_client.fput_object(
                    "frames-procesados",
                    f"video_{video_id}/{nombre_frame}",
                    ruta_local,
                    content_type="image/jpeg",
                )
                os.remove(ruta_local)
                frames_guardados += 1

            cap.release()

            logger.info(
                f"Limpieza terminada. De {frame_count} frames originales, quedaron {frames_guardados} frames perfectos."
            )

            r.rpush("cola_inferencia", video_id)
            logger.info(
                f"Video {video_id} enviado a Inferencia. Limpiando archivos temporales..."
            )

            os.remove(ruta_original)

        except Exception as e:
            db.rollback()
            logger.error(f"Error procesando video ID {video_id}: {e}")
            logger.debug(traceback.format_exc())
            if "video" in locals() and video:
                video.estado = "error"
                db.commit()
        finally:
            db.close()

    except Exception:
        time.sleep(2)
