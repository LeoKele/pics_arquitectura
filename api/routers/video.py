import logging

import httpx
import models
import schemas
from configs.config import settings
from database import get_db
from dependencias import minio_client, r
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from minio.error import S3Error
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import text
from services.geo_service import obtener_contexto_geografico


router = APIRouter()
logger = logging.getLogger("api.video")


class PreguntaRequest(BaseModel):
    pregunta: str


@router.post(
    "/api/v1/videos",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=schemas.VideoResponse,
)
def subir_video(
    video: UploadFile = File(...),
    metadata: UploadFile = File(...),
    db: Session = Depends(get_db),
):
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
        if not minio_client.bucket_exists(settings.BUCKET_NAME):
            minio_client.make_bucket(settings.BUCKET_NAME)

        minio_client.put_object(
            settings.BUCKET_NAME,
            video.filename,
            video.file,
            video.size,
            content_type=video.content_type,
        )
        minio_client.put_object(
            settings.BUCKET_NAME,
            metadata.filename,
            metadata.file,
            metadata.size,
            content_type=metadata.content_type,
        )
        logger.info(f"Archivos subidos a MinIO: {video.filename}, {metadata.filename}")

    except S3Error as e:
        logger.error(f"Error en MinIO al subir archivos: {e}")
        raise HTTPException(status_code=500, detail=f"Error en MinIO: {str(e)}")

    nuevo_video = models.Video(
        nombre_archivo=video.filename,
        nombre_metadata=metadata.filename,
        estado="pendiente",
    )
    db.add(nuevo_video)
    db.commit()
    db.refresh(nuevo_video)
    logger.info(f"Video registrado en BD con ID: {nuevo_video.id}")

    try:
        r.rpush("cola_preprocesamiento", nuevo_video.id)
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


@router.get(
    "/api/v1/videos/{video_id}",
    response_model=schemas.VideoStatusResponse,
    tags=["Monitoreo"],
)
def obtener_estado_video(video_id: int, db: Session = Depends(get_db)):
    logger.info(f"Consultando estado del video ID: {video_id}")

    video = db.query(models.Video).filter(models.Video.id == video_id).first()
    if not video:
        logger.warning(f"Video ID {video_id} no encontrado")
        raise HTTPException(status_code=404, detail="Video no encontrado")

    logger.info(f"Video ID {video_id} → estado: {video.estado}")
    return {"id": video.id, "estado": video.estado}


@router.post("/api/v1/video/{video_id}/preguntar", tags=["Inteligencia Artificial"])
def preguntar_a_video(
    video_id: int, request: PreguntaRequest, db: Session = Depends(get_db)
):
    """
    Permite hacerle una pregunta en lenguaje natural a la
    IA sobre los resultados de un video.
    """
    video = db.query(models.Video).filter(models.Video.id == video_id).first()
    if not video:
        raise HTTPException(status_code=404, detail="Video no encontrado")
    if video.estado != "procesado":
        raise HTTPException(status_code=400, detail="El video aún no fue procesado.")

    detecciones = (
        db.query(models.Deteccion).filter(models.Deteccion.video_id == video_id).all()
    )
    cantidad = len(detecciones)
    confianza_promedio = (
        sum(d.confianza for d in detecciones) / cantidad if cantidad > 0 else 0
    )

    # Buscar el Reporte generado previamente (que contiene los datos de OSM)
    reporte = (
        db.query(models.Reporte)
        .join(models.ReporteVideo)
        .filter(models.ReporteVideo.video_id == video_id)
        .order_by(models.Reporte.fecha_generacion.desc())
        .first()
    )


    prompt = "Sos un asistente técnico de inspección vial del municipio.\n\n"
    prompt += f"DATOS BÁSICOS DEL VIDEO {video_id}:\n"
    prompt += f"- Baches detectados: {cantidad}\n"
    prompt += f"- Confianza promedio: {confianza_promedio:.2%}\n\n"
    
    prompt += "CONTEXTO GEOGRÁFICO Y COMERCIOS CERCANOS:\n"
    if reporte and reporte.contenido:
        prompt += reporte.contenido + "\n\n"
    else:
        prompt += "No hay datos de comercios cercanos o reporte geográfico en el sistema para este video.\n\n"
        
    prompt += f'PREGUNTA DEL USUARIO: "{request.pregunta}"\n\n'
    prompt += "Respondé de forma breve y profesional usando la información geográfica provista arriba.\n"
    prompt += "REGLAS IMPORTANTES:\n"
    prompt += "1. Sé flexible con los nombres: si el usuario pregunta por 'Julio Asseff' y en el texto figura 'Intendente Doctor Julio Asseff', asumí que es la misma calle.\n"
    prompt += "2. Si el usuario pregunta por un tipo de lugar (ej. 'una escuela' o 'un hospital'), y en el texto hay uno específico (ej. 'Escuela Lakohmi'), usá esa información.\n"
    prompt += "3. Si la información solicitada definitivamente NO figura en el texto, indicá claramente que no tenés esa información."
    
    try:
        response = httpx.post(
            f"{settings.OLLAMA_URL}/api/generate",
            json={"model": "llama3.2:3b", "prompt": prompt, "stream": False},
            timeout=60.0,
        )
        response.raise_for_status()
        respuesta_ia = response.json().get("response", "No se pudo generar respuesta.")

        return {
            "video_id": video_id,
            "pregunta": request.pregunta,
            "respuesta": respuesta_ia,
        }
    except Exception as e:
        logger.error(f"Error en Q&A con Ollama: {e}")
        raise HTTPException(
            status_code=500, detail="Error al comunicarse con la IA local."
        )