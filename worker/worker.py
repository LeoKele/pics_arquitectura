import json
import logging
import os
import traceback
from datetime import datetime
import time
import cv2
import redis
from geoalchemy2 import Geometry
from geoalchemy2.shape import from_shape
from minio import Minio
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
from ultralytics import YOLO

# Logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s - %(message)s"
)
logger = logging.getLogger("worker-inferencia")

# Configuración
REDIS_HOST = os.getenv("REDIS_HOST", "redis_queue")
DATABASE_URL = os.getenv("DATABASE_URL")

# --- CONEXIÓN A MINIO ---
minio_client = Minio(
    "almacenamiento-objetos:9000",
    access_key=os.getenv("MINIO_ROOT_USER", "minioadmin"),
    secret_key=os.getenv("MINIO_ROOT_PASSWORD", "minioadmin"),
    secure=False,
)
BUCKET_NAME = "videos-crudos"

# Base de datos
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()


class Video(Base):
    __tablename__ = "video"
    id = Column(Integer, primary_key=True)
    nombre_archivo = Column(String)
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


# CARGAR EL MODELO YOLO
logger.info("Cargando modelo YOLO en memoria...")
modelo_yolo = YOLO("best.pt")

try:
    r = redis.Redis(host=REDIS_HOST, port=6379, db=0)
    r.ping()
    logger.info("Worker de Inferencia conectado a Redis, esperando videos...")
except Exception as e:
    logger.critical(f"No se pudo conectar a Redis: {e}")
    exit(1)


# Función para buscar la coordenada correcta
def obtener_coordenada(datos_gps, tiempo_ms):
    if not datos_gps:
        # Si no hay JSON, devolvemos la falsa por defecto para que no explote
        return -34.65, -58.79  # Se puede cambiar a 0.0

    # Busca en la lista el GPS cuyo "elapsed_ms" esté más cerca del tiempo del video
    punto_mas_cercano = min(datos_gps, key=lambda x: abs(x["elapsed_ms"] - tiempo_ms))
    return punto_mas_cercano["lat"], punto_mas_cercano["lng"]


while True:
    try:
        resultado = r.blpop("cola_inferencia")
        if not resultado:
            continue

        video_id = int(resultado[1].decode("utf-8"))
        logger.info(f"Iniciando inferencia real para video ID: {video_id}")

        db = SessionLocal()
        try:
            video = db.query(Video).filter(Video.id == video_id).first()
            if not video:
                continue

            video.estado = "procesando"
            db.commit()

            # 1. DESCARGAR VIDEO PROCESADO
            ruta_video_local = f"/tmp/video_{video_id}.mp4"
            minio_client.fget_object(
                BUCKET_NAME, video.nombre_archivo, ruta_video_local
            )

            # DESCARGAR EL JSON DE COORDENADAS
            nombre_base = video.nombre_archivo.replace("procesado_", "").rsplit(".", 1)[
                0
            ]
            nombre_json = f"{nombre_base}.json"
            ruta_json_local = f"/tmp/{nombre_json}"

            datos_gps = []
            try:
                logger.info(f"Buscando archivo GPS asociado: {nombre_json}")
                minio_client.fget_object(BUCKET_NAME, nombre_json, ruta_json_local)
                with open(ruta_json_local, "r") as f:
                    json_completo = json.load(f)
                    datos_gps = json_completo.get("data", [])
                logger.info(f"Éxito: Se cargaron {len(datos_gps)} puntos de GPS.")
            except Exception as e:
                logger.warning(
                    f"No se encontró/leyó el JSON. Se usará coordenada por defecto. Detalles: {e}"
                )

            # 2. PROCESAR CON OPENCV Y YOLO
            logger.info("Procesando frames con YOLO...")
            cap = cv2.VideoCapture(ruta_video_local)

            baches_detectados = 0

            while cap.isOpened():
                ret, frame = cap.read()
                if not ret:
                    break

                tiempo_actual_ms = cap.get(cv2.CAP_PROP_POS_MSEC)

                # Procesamos todos los frames que llegaron
                resultados = modelo_yolo(frame, verbose=False)[0]

                for box in resultados.boxes:
                    confianza = float(box.conf[0])
                    clase_id = int(box.cls[0])
                    nombre_clase = modelo_yolo.names[clase_id]

                    if confianza > 0.10:
                        baches_detectados += 1

                        lat, lng = obtener_coordenada(datos_gps, tiempo_actual_ms)

                        # Shapely (Point) siempre recibe (Longitud, Latitud) en ese orden
                        punto_real = Point(lng, lat)

                        nueva_deteccion = Deteccion(
                            video_id=video_id,
                            geom=from_shape(punto_real, srid=4326),
                            tipo_dano=nombre_clase,
                            confianza=confianza,
                            estado_auditoria="pendiente",
                        )
                        db.add(nueva_deteccion)

            cap.release()
            os.remove(ruta_video_local)
            if os.path.exists(ruta_json_local):
                os.remove(ruta_json_local)

            video.estado = "procesado"
            db.commit()
            logger.info(
                f"Video {video_id} terminado. Se encontraron {baches_detectados} baches reales."
            )

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
