import json
import logging
import os
import time

import httpx
import models
import redis
import schemas
from database import engine, get_db
from fastapi import Depends, FastAPI, File, HTTPException, UploadFile, status
from geoalchemy2.functions import ST_AsGeoJSON
from minio import Minio
from minio.error import S3Error
from sqlalchemy.orm import Session

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
)
logger = logging.getLogger("api")

# Crea las tablas si no existen
for intento in range(10):
    try:
        models.Base.metadata.create_all(bind=engine)
        logger.info("Tablas creadas/verificadas correctamente.")
        break
    except Exception as e:
        logger.warning(f"BD no lista, reintentando en 3s... ({intento+1}/10): {e}")
        time.sleep(3)
else:
    logger.error("No se pudo conectar a la BD después de 10 intentos.")
    raise SystemExit(1)

# Configuración de conexiones externas
REDIS_HOST = os.getenv("REDIS_HOST", "redis_queue")
r = redis.Redis(host=REDIS_HOST, port=6379, decode_responses=True)


minio_client = Minio(
    "almacenamiento-objetos:9000",
    access_key=os.getenv("MINIO_ROOT_USER"),
    secret_key=os.getenv("MINIO_ROOT_PASSWORD"),
    secure=False,
)
BUCKET_NAME = "videos-crudos"

# ===============================================================================================
# ===============================================================================================
# ===============================================================================================

app = FastAPI(title="Mapeo Vial Moreno", version="1.1.3")

# ===============================================================================================


@app.get("/")
def raiz():
    return {"mensaje": "API PICS v1 funcionando correctamente"}


# ===============================================================================================


@app.post(
    "/api/v1/videos",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=schemas.VideoResponse,
)
def subir_video(
    video: UploadFile = File(...),
    metadata: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    # Validación básica para que no rompa por subir cualquier archivo
    if not video.filename.endswith((".mp4", ".webm")):
        logger.warning(f"Archivo rechazado por extensión inválida: {video.filename}")
        raise HTTPException(
            status_code=422, detail="El archivo de video debe ser .mp4 o .webm"
        )
    if not metadata.filename.endswith(".json"):
        logger.warning(
            f"Metadata rechazada por extensión inválida: {metadata.filename}"
        )
        raise HTTPException(
            status_code=422, detail="El archivo de metadata debe ser .json"
        )

    try:
        if not minio_client.bucket_exists(BUCKET_NAME):
            minio_client.make_bucket(BUCKET_NAME)

        minio_client.put_object(
            BUCKET_NAME,
            video.filename,
            video.file,
            video.size,
            content_type=video.content_type,
        )
        minio_client.put_object(
            BUCKET_NAME,
            metadata.filename,
            metadata.file,
            metadata.size,
            content_type=metadata.content_type,
        )
        logger.info(f"Archivos subidos a MinIO: {video.filename}, {metadata.filename}")

    except S3Error as e:
        logger.error(f"Error en MinIO al subir archivos: {e}")
        raise HTTPException(status_code=500, detail=f"Error en MinIO: {str(e)}")

    # Registro en la base de datos
    nuevo_video = models.Video(
        nombre_archivo=video.filename,
        nombre_metadata=metadata.filename,
        estado="pendiente",
    )
    db.add(nuevo_video)
    db.commit()
    db.refresh(nuevo_video)
    logger.info(f"Video registrado en BD con ID: {nuevo_video.id}")

    # Enviar tarea a Redis
    try:
        r.rpush("tareas_video", nuevo_video.id)
        logger.info(f"Tarea encolada en Redis para video ID: {nuevo_video.id}")
    except Exception as e:
        logger.error(
            f"Error al enviar tarea a Redis para video ID {nuevo_video.id}: {e}"
        )

    return {
        "mensaje": "Video y metadata recibidos correctamente",
        "video_id": nuevo_video.id,
        "estado": nuevo_video.estado,
    }


# ===============================================================================================


@app.get("/api/v1/detecciones", response_model=list[schemas.DeteccionResponse])
def obtener_detecciones(db: Session = Depends(get_db)):
    logger.info("Consultando todas las detecciones")

    detecciones = db.query(
        models.Deteccion.id,
        models.Deteccion.video_id,
        models.Deteccion.tipo_dano,
        models.Deteccion.confianza,
        ST_AsGeoJSON(models.Deteccion.geom).label("geometria"),
        models.Deteccion.fecha_deteccion,
        models.Deteccion.frame_minio_path,
        models.Deteccion.estado_auditoria,
    ).all()

    resultado = []
    for d in detecciones:
        resultado.append(
            {
                "id": d.id,
                "video_id": d.video_id,
                "tipo_dano": d.tipo_dano,
                "confianza": d.confianza,
                "geometria": json.loads(d.geometria),
                "fecha": d.fecha_deteccion,
                "frame_minio_path": d.frame_minio_path,
                "estado_auditoria": d.estado_auditoria,
            }
        )

    logger.info(f"Devolviendo {len(resultado)} detecciones")
    return resultado


# ===============================================================================================
@app.get("/api/v1/videos/{video_id}", response_model=schemas.VideoStatusResponse)
def obtener_estado_video(video_id: int, db: Session = Depends(get_db)):
    logger.info(f"Consultando estado del video ID: {video_id}")

    video = db.query(models.Video).filter(models.Video.id == video_id).first()
    if not video:
        logger.warning(f"Video ID {video_id} no encontrado")
        raise HTTPException(status_code=404, detail="Video no encontrado")

    logger.info(f"Video ID {video_id} → estado: {video.estado}")
    return {"id": video.id, "estado": video.estado}


OLLAMA_URL = os.getenv("OLLAMA_URL", "http://ollama:11434")


@app.post("/api/v1/reporte/{video_id}", status_code=status.HTTP_201_CREATED)
def generar_reporte(video_id: int, db: Session = Depends(get_db)):
    try:
        logger.info(f"Generando reporte para video ID: {video_id}")

        # 1. Verificar que el video existe y está procesado
        video = db.query(models.Video).filter(models.Video.id == video_id).first()
        if not video:
            raise HTTPException(status_code=404, detail="Video no encontrado")
        if video.estado != "procesado":
            raise HTTPException(
                status_code=400,
                detail=f"El video aún no fue procesado. Estado actual: {video.estado}",
            )

        # 2. Obtener detecciones
        detecciones = (
            db.query(models.Deteccion)
            .filter(models.Deteccion.video_id == video_id)
            .all()
        )
        cantidad = len(detecciones)
        confianza_promedio = (
            sum(d.confianza for d in detecciones) / cantidad if cantidad > 0 else 0
        )

        # Manejo seguro por si la fecha llega nula desde la BD
        fecha_texto = (
            video.fecha_ingreso.strftime("%d/%m/%Y")
            if video.fecha_ingreso
            else "Desconocida"
        )

        # 3. Armar el prompt
        prompt = f"""Sos un inspector vial municipal del partido de Moreno, provincia de Buenos Aires.
        Basándote en los siguientes datos de una inspección de calles, redactá un informe ejecutivo breve y formal en español.

        Datos de la inspección:
        - Video ID: {video_id}
        - Archivo inspeccionado: {video.nombre_archivo}
        - Fecha de inspección: {fecha_texto}
        - Cantidad de baches detectados: {cantidad}
        - Confianza promedio del modelo: {confianza_promedio:.0%}

        El informe debe tener exactamente 3 párrafos:
        1. Resumen ejecutivo de la inspección
        2. Análisis del estado vial detectado
        3. Recomendación de acción prioritaria

        Sé conciso y profesional."""

        # 4. Llamar a Ollama
        response = httpx.post(
            f"{OLLAMA_URL}/api/generate",
            json={"model": "llama3.2:3b", "prompt": prompt, "stream": False},
            timeout=120.0,
        )

        # Validación específica por si el modelo no está instalado
        if response.status_code == 404:
            raise HTTPException(
                status_code=500,
                detail="Ollama respondió 404. Es probable que no hayas descargado el modelo. Entra a tu terminal y ejecuta: docker exec -it tu_contenedor_ollama ollama run llama3.2:3b",
            )

        response.raise_for_status()
        contenido_reporte = response.json().get(
            "response", "No se pudo extraer el texto del reporte."
        )
        logger.info(f"Reporte generado correctamente para video ID: {video_id}")

        # 5. Guardar en BD
        nuevo_reporte = models.Reporte(video_id=video_id, contenido=contenido_reporte)
        db.add(nuevo_reporte)
        db.commit()
        db.refresh(nuevo_reporte)

        return {
            "reporte_id": nuevo_reporte.id,
            "video_id": video_id,
            "fecha_generacion": nuevo_reporte.fecha_generacion,
            "contenido": contenido_reporte,
        }

    # Atrapamos errores para que siempre devuelvan un JSON legible en Swagger
    except HTTPException:
        raise
    except httpx.TimeoutException:
        logger.error(f"Timeout al llamar a Ollama para video ID: {video_id}")
        raise HTTPException(
            status_code=504, detail="Ollama tardó demasiado en responder (Timeout)."
        )
    except Exception as e:
        logger.error(f"Error interno en generar_reporte: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Crash detectado: {str(e)}")


@app.get("/api/v1/reporte/{video_id}")
def obtener_reporte(video_id: int, db: Session = Depends(get_db)):
    logger.info(f"Consultando reporte para video ID: {video_id}")

    # AQUI CORREGIDO: models.Reporte
    reporte = (
        db.query(models.Reporte)
        .filter(models.Reporte.video_id == video_id)
        .order_by(models.Reporte.fecha_generacion.desc())
        .first()
    )

    if not reporte:
        logger.warning(f"No hay reporte para video ID: {video_id}")
        raise HTTPException(
            status_code=404, detail="No hay reporte generado para este video"
        )

    return {
        "reporte_id": reporte.id,
        "video_id": video_id,
        "fecha_generacion": reporte.fecha_generacion,
        "contenido": reporte.contenido,
    }
