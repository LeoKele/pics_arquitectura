import logging
import os
import time
import traceback
from datetime import datetime

import cv2
import numpy as np
import redis
from minio import Minio
from sqlalchemy import Column, Integer, String, create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

# --- CONFIGURACIÓN Y LOGS ---
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


# --- INICIALIZACIÓN ---
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

            # 1. DESCARGAR VIDEO CRUDO
            ruta_original = f"/tmp/crudo_{video_id}.mp4"
            logger.info(f"Descargando {video.nombre_archivo} desde MinIO...")
            minio_client.fget_object(BUCKET_NAME, video.nombre_archivo, ruta_original)

            # 2. CONFIGURAR OPENCV
            cap = cv2.VideoCapture(ruta_original)
            frame_count = 0
            frames_guardados = 0

            # Asegurarnos de que el bucket exista
            if not minio_client.bucket_exists("frames-procesados"):
                minio_client.make_bucket("frames-procesados")

            logger.info("Extrayendo frames y enviando a MinIO...")
            while cap.isOpened():
                ret, frame = cap.read()
                if not ret:
                    break

                frame_count += 1
                if frame_count % 6 != 0:  # Tomamos 1 de cada 6 frames
                    continue

                # Acá irían tus filtros si los descomentás:
                # frame_recortado = frame[corte_superior:alto, 0:ancho]
                # if es_imagen_borrosa(frame_recortado): continue

                # 1. Obtener el milisegundo exacto
                tiempo_ms = int(cap.get(cv2.CAP_PROP_POS_MSEC))

                # 2. Guardar imagen temporalmente
                nombre_frame = f"frame_{tiempo_ms}.jpg"
                ruta_local = f"/tmp/{nombre_frame}"
                cv2.imwrite(
                    ruta_local, frame
                )  # Usar frame_recortado si aplicás filtros

                # 3. Subir el frame a MinIO
                minio_client.fput_object(
                    "frames-procesados",
                    f"video_{video_id}/{nombre_frame}",
                    ruta_local,
                    content_type="image/jpeg",
                )
                os.remove(ruta_local)  # Limpiamos
                frames_guardados += 1

            cap.release()

            logger.info(
                f"Limpieza terminada. De {frame_count} frames originales, quedaron {frames_guardados} frames perfectos."
            )

            # 3. PASAR EL TESTIGO A YOLO
            r.rpush("cola_inferencia", video_id)
            logger.info(
                f"Video {video_id} enviado a Inferencia. Limpiando archivos temporales..."
            )

            # Limpiar el contenedor local (ya no guardamos el video entero procesado)
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

    except Exception as e:
        time.sleep(2)
