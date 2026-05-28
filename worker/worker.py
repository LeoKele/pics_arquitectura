import json
import logging
import os
import time
import traceback
from datetime import datetime

import cv2
import redis
from anonimizador import anonimizar_frame
from geoalchemy2 import Geometry
from geoalchemy2.shape import from_shape
from minio import Minio
from shapely.geometry import Point
from sqlalchemy import (
    JSON,
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
from ultralytics.utils.plotting import Annotator, colors

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
    bbox = Column(JSON, nullable=True)
    estado_auditoria = Column(String, default="pendiente")
    fecha_deteccion = Column(DateTime, default=datetime.utcnow)


# --- NUEVO MODELO DE TELEMETRÍA CORREGIDO ---
class Telemetria(Base):
    __tablename__ = "telemetria"
    id = Column(Integer, primary_key=True)
    video_id = Column(Integer, ForeignKey("video.id"))
    tiempo = Column(Float)
    geometria = Column(Geometry("POINT", srid=4326)) # ¡Corregido de 'geom' a 'geometria'!


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
        return -34.65, -58.79  

    punto_mas_cercano = min(datos_gps, key=lambda x: abs(x["elapsed_ms"] - tiempo_ms))
    return punto_mas_cercano["lat"], punto_mas_cercano["lng"]


def guardar_y_subir_imagen(frame_original, video_id, tiempo_ms, j):
    frame_anonimo = anonimizar_frame(frame_original)
    nombre_det = f"bache_{tiempo_ms}_box{j}.jpg"
    ruta_det_local = f"/tmp/{nombre_det}"
    cv2.imwrite(ruta_det_local, frame_anonimo)

    ruta_minio_deteccion = f"video_{video_id}/{nombre_det}"
    minio_client.fput_object(
        "detecciones",
        ruta_minio_deteccion,
        ruta_det_local,
        content_type="image/jpeg",
    )

    if os.path.exists(ruta_det_local):
        os.remove(ruta_det_local)

    return ruta_minio_deteccion


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

            # 1. DESCARGAR EL JSON DE COORDENADAS
            nombre_base = video.nombre_archivo.replace("procesado_", "").rsplit(".", 1)[0]
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

                # --- GUARDAR TODA LA TELEMETRÍA ---
                logger.info(f"Guardando la trayectoria completa ({len(datos_gps)} puntos) en PostgreSQL...")
                for punto in datos_gps:
                    lat = punto.get("lat")
                    lng = punto.get("lng")
                    tiempo_ms = punto.get("elapsed_ms", 0.0)
                    
                    if lat is not None and lng is not None:
                        nueva_telemetria = Telemetria(
                            video_id=video_id,
                            tiempo=float(tiempo_ms),
                            geometria=from_shape(Point(lng, lat), srid=4326) # ¡Corregido acá también!
                        )
                        db.add(nueva_telemetria)
                db.commit()
                logger.info("Trayectoria guardada en BD con éxito.")
                # --------------------------------------------------------------

            except Exception as e:
                logger.warning(
                    f"""No se encontró/leyó el JSON. Se usará coordenada por defecto.
                    Detalles: {e}"""
                )

            # 2. PROCESAR FRAMES INDIVIDUALES CON YOLO
            if not minio_client.bucket_exists("detecciones"):
                minio_client.make_bucket("detecciones")

            logger.info(f"Buscando frames del video {video_id} en MinIO...")
            objetos_frames = list(
                minio_client.list_objects(
                    "frames-procesados", prefix=f"video_{video_id}/", recursive=True
                )
            )

            # --- ORDENAR FRAMES CRONOLÓGICAMENTE ---
            def extraer_tiempo(obj):
                try:
                    return int(obj.object_name.split("_")[-1].split(".")[0])
                except ValueError:
                    return 0

            objetos_frames.sort(key=extraer_tiempo)
            
            baches_detectados = 0
            diccionario_tracks = {}  
            ids_procesados = set()  

            total_frames = len(objetos_frames)
            logger.info(f"Procesando {total_frames} frames...")

            for i, obj in enumerate(objetos_frames):
                nombre_archivo_minio = obj.object_name

                if i % 5 == 0:
                    logger.info(f"Progreso: Frame {i}/{total_frames} ({obj.object_name})")

                try:
                    tiempo_ms = int(nombre_archivo_minio.split("_")[-1].split(".")[0])
                except ValueError:
                    continue

                ruta_local_frame = f"/tmp/frame_{tiempo_ms}.jpg"
                minio_client.fget_object(
                    "frames-procesados", nombre_archivo_minio, ruta_local_frame
                )

                frame = cv2.imread(ruta_local_frame)
                resultados = modelo_yolo.track(
                    frame,
                    persist=True,
                    tracker="bytetrack.yaml",
                    conf=0.30,
                    iou=0.4,
                    verbose=False,
                )[0]

                if resultados.boxes.id is not None:
                    track_ids = resultados.boxes.id.int().cpu().tolist()
                else:
                    track_ids = [None] * len(resultados.boxes)

                for j, (box, track_id) in enumerate(zip(resultados.boxes, track_ids)):
                    confianza = float(box.conf[0])
                    clase_id = int(box.cls[0])
                    nombre_clase = modelo_yolo.names[clase_id]

                    if confianza > 0.30:
                        y_centro = float(box.xywh[0][1])
                        alto_imagen = frame.shape[0]
                        if y_centro < (alto_imagen * 0.50):
                            logger.info(f"Omitiendo {nombre_clase} por estar en el horizonte")
                            continue

                        id_log = f"ID:{track_id}" if track_id is not None else "ID:NUEVO"

                        lat, lng = obtener_coordenada(datos_gps, tiempo_ms)
                        punto_wkt = f"SRID=4326;POINT({lng} {lat})"

                        distancias_map = {
                            "d40": 0.00003,  
                            "d20": 0.00010,  
                            "calle_tierra": 0.00030,  
                        }
                        umbral = distancias_map.get(nombre_clase.lower(), 0.00003)

                        duplicado = None

                        if track_id is not None and track_id in diccionario_tracks:
                            id_bd = diccionario_tracks[track_id]
                            duplicado = db.query(Deteccion).filter(Deteccion.id == id_bd).first()

                        if not duplicado:
                            duplicado = (
                                db.query(Deteccion)
                                .filter(
                                    Deteccion.video_id == video_id,
                                    Deteccion.tipo_dano == nombre_clase,
                                    Deteccion.geom.ST_DWithin(punto_wkt, umbral),
                                )
                                .first()
                            )

                            if duplicado and track_id is not None:
                                diccionario_tracks[track_id] = duplicado.id

                        if duplicado:
                            if confianza > duplicado.confianza:
                                logger.info(f"Actualizando {nombre_clase} ({id_log}): {duplicado.confianza:.2f} -> {confianza:.2f}")
                                if duplicado.frame_minio_path:
                                    try:
                                        minio_client.remove_object("detecciones", duplicado.frame_minio_path)
                                    except Exception as e:
                                        pass

                                x1, y1, x2, y2 = map(int, box.xyxy[0])
                                bbox_dict = {"x1": x1, "y1": y1, "x2": x2, "y2": y2}

                                ruta_minio_deteccion = guardar_y_subir_imagen(frame, video_id, tiempo_ms, j)

                                duplicado.confianza = confianza
                                duplicado.frame_minio_path = ruta_minio_deteccion
                                duplicado.bbox = bbox_dict
                                duplicado.geom = from_shape(Point(lng, lat), srid=4326)
                                db.commit()
                            continue

                        baches_detectados += 1
                        logger.info(f"NUEVO bache detectado: {nombre_clase} ({id_log}, Conf: {confianza:.2f})")

                        x1, y1, x2, y2 = map(int, box.xyxy[0])
                        bbox_dict = {"x1": x1, "y1": y1, "x2": x2, "y2": y2}

                        ruta_minio_deteccion = guardar_y_subir_imagen(frame, video_id, tiempo_ms, j)

                        nueva_deteccion = Deteccion(
                            video_id=video_id,
                            geom=from_shape(Point(lng, lat), srid=4326),
                            tipo_dano=nombre_clase,
                            confianza=confianza,
                            frame_minio_path=ruta_minio_deteccion,
                            bbox=bbox_dict,
                            estado_auditoria="pendiente",
                        )
                        db.add(nueva_deteccion)
                        db.commit()
                        db.refresh(nueva_deteccion)

                        if track_id is not None:
                            diccionario_tracks[track_id] = nueva_deteccion.id

                os.remove(ruta_local_frame)

            if os.path.exists(ruta_json_local):
                os.remove(ruta_json_local)

            # --- LIMPIEZA DE MINIO ---
            try:
                logger.info(f"Limpiando frames procesados del video {video_id}...")
                objetos_a_borrar = minio_client.list_objects(
                    "frames-procesados", prefix=f"video_{video_id}/", recursive=True
                )
                for obj in objetos_a_borrar:
                    minio_client.remove_object("frames-procesados", obj.object_name)

                logger.info(f"Limpiando archivos crudos del video {video_id}...")
                minio_client.remove_object(BUCKET_NAME, video.nombre_archivo)
                minio_client.remove_object(BUCKET_NAME, nombre_json)
            except Exception as cleanup_error:
                logger.error(f"Error durante la limpieza de MinIO: {cleanup_error}")

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