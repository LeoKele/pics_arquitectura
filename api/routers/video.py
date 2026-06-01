import json
import logging
import traceback
from typing import Any, Dict, List, Optional

import httpx
import models
import schemas
from configs.config import settings
from database import get_db
from dependencias import minio_client, r, s3_public_client
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from minio.error import S3Error
from pydantic import BaseModel
from services.geo_service import obtener_contexto_geografico
from sqlalchemy import text
from sqlalchemy.orm import Session

router = APIRouter()
logger = logging.getLogger("api.video")
from minio.error import S3Error


class PreguntaRequest(BaseModel):
    pregunta: str


class IniciarUploadRequest(BaseModel):
    filename: str
    content_type: str


class ParteFirmadaRequest(BaseModel):
    filename: str
    upload_id: str
    part_number: int


class FinalizarUploadRequest(BaseModel):
    filename: str
    upload_id: str
    parts: List[Dict[str, Any]]
    telemetria: Optional[List[Dict[str, Any]]] = []


@router.post("/api/v1/videos/manual", status_code=status.HTTP_202_ACCEPTED)
def subir_video_manual(
    video: UploadFile = File(...),
    metadata: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    """Sube un video y su JSON de GPS manualmente desde la interfaz web."""
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
        "mensaje": "Video y metadata recibidos correctamente (Modo Manual)",
        "video_id": nuevo_video.id,
        "estado": nuevo_video.estado,
    }


@router.post("/api/v1/videos/upload/iniciar", tags=["Videos Multipart"])
def iniciar_upload_multipart(request: IniciarUploadRequest):
    """Paso 1: Le avisa a MinIO que vamos a empezar a subir un archivo en partes."""
    try:
        if not minio_client.bucket_exists(settings.BUCKET_NAME):
            minio_client.make_bucket(settings.BUCKET_NAME)

        # Iniciamos el multipart usando el cliente público boto3
        response = s3_public_client.create_multipart_upload(
            Bucket=settings.BUCKET_NAME,
            Key=request.filename,
            ContentType=request.content_type,
        )
        return {"upload_id": response["UploadId"], "key": request.filename}
    except Exception as e:
        logger.error(f"Error iniciando multipart: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/v1/videos/upload/firmar-parte", tags=["Videos Multipart"])
def firmar_parte(request: ParteFirmadaRequest):
    """Paso 2: Genera una URL temporal segura para subir un pedazo (chunk) del video."""
    try:
        presigned_url = s3_public_client.generate_presigned_url(
            ClientMethod="upload_part",
            Params={
                "Bucket": settings.BUCKET_NAME,
                "Key": request.filename,
                "UploadId": request.upload_id,
                "PartNumber": request.part_number,
            },
            ExpiresIn=3600,
        )
        return {"url": presigned_url}
    except Exception as e:
        logger.error(f"Error firmando parte: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post(
    "/api/v1/videos/upload/finalizar",
    status_code=status.HTTP_202_ACCEPTED,
    tags=["Videos Multipart"],
)
def finalizar_upload_multipart(
    request: FinalizarUploadRequest, db: Session = Depends(get_db)
):
    """Paso 3: Ensambla el video en MinIO, guarda el JSON del GPS, lo registra en BD y lo encola."""
    try:
        s3_public_client.complete_multipart_upload(
            Bucket=settings.BUCKET_NAME,
            Key=request.filename,
            UploadId=request.upload_id,
            MultipartUpload={"Parts": request.parts},
        )
        logger.info(f"Video {request.filename} ensamblado exitosamente en MinIO.")

        json_filename = request.filename.replace(".webm", ".json")

        try:
            s3_public_client.put_object(
                Bucket=settings.BUCKET_NAME,
                Key=json_filename,
                Body=json.dumps(
                    request.telemetria
                ),  # Convertimos la lista a texto JSON
                ContentType="application/json",
            )
            logger.info(f"Telemetría guardada en MinIO como {json_filename}")
        except Exception as e:
            logger.error(f"Error guardando telemetría en MinIO: {e}")

        nuevo_video = models.Video(
            nombre_archivo=request.filename,
            nombre_metadata=json_filename,  # <-- Acá le pasamos el nombre exacto
            estado="pendiente",
        )
        db.add(nuevo_video)
        db.commit()
        db.refresh(nuevo_video)
        logger.info(f"Video registrado en BD con ID: {nuevo_video.id}")

        try:
            r.rpush("cola_preprocesamiento", nuevo_video.id)
            logger.info(f"Tarea encolada en Redis para video ID: {nuevo_video.id}")
        except Exception as redis_e:
            logger.error(
                f"Error al enviar tarea a Redis para video ID {nuevo_video.id}: {redis_e}"
            )

        return {
            "mensaje": "Video y telemetría guardados correctamente",
            "video_id": nuevo_video.id,
            "estado": nuevo_video.estado,
        }

    except Exception as e:
        logger.error(f"Error finalizando multipart: {e}")
        raise HTTPException(status_code=500, detail=str(e))


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
async def preguntar_a_video(
    video_id: int, request: PreguntaRequest, db: Session = Depends(get_db)
):
    """
    Agente de IA Híbrido: Utiliza el reporte si existe, pero tiene la capacidad de
    consultar OpenStreetMap en tiempo real de forma autónoma si necesita más datos.
    """

    video = db.query(models.Video).filter(models.Video.id == video_id).first()
    if not video:
        raise HTTPException(status_code=404, detail="Video no encontrado")
    if video.estado != "procesado":
        raise HTTPException(status_code=400, detail="El video aún no fue procesado.")

    try:
        detecciones = (
            db.query(models.Deteccion)
            .filter(
                models.Deteccion.video_id == video_id,
                models.Deteccion.estado_auditoria != "falso_positivo",
            )
            .all()
        )
        cantidad = len(detecciones)
        confianza_promedio = (
            sum(d.confianza for d in detecciones) / cantidad if cantidad > 0 else 0
        )

        # Obtener Reporte (si existe)
        reporte = (
            db.query(models.Reporte)
            .join(models.ReporteVideo)
            .filter(models.ReporteVideo.video_id == video_id)
            .order_by(models.Reporte.fecha_generacion.desc())
            .first()
        )
        reporte_texto = (
            reporte.contenido
            if reporte and reporte.contenido
            else "No hay reporte previo generado para este video."
        )

        # Obtener Coordenadas para la herramienta
        query_centroide = text("""
            SELECT ST_Y(ST_Centroid(ST_Collect(geom))) as lat,
                   ST_X(ST_Centroid(ST_Collect(geom))) as lng
            FROM deteccion WHERE video_id = :v_id AND estado_auditoria != 'falso_positivo'
        """)
        centroide = db.execute(query_centroide, {"v_id": video_id}).fetchone()

        lat = float(centroide[0]) if centroide and centroide[0] else 0.0
        lng = float(centroide[1]) if centroide and centroide[1] else 0.0

        # Tool
        herramientas = [
            {
                "type": "function",
                "function": {
                    "name": "consultar_mapa_osm",
                    "description": "Obtiene las calles y puntos de interés (escuelas, comercios, etc) reales cercanos a unas coordenadas.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "lat": {"type": "number", "description": "Latitud"},
                            "lng": {"type": "number", "description": "Longitud"},
                        },
                        "required": ["lat", "lng"],
                    },
                },
            }
        ]

        # Prompt
        mensajes = [
            {
                "role": "system",
                "content": (
                    f"Sos un sistema de IA especializado ÚNICAMENTE en la inspección vial del video {video_id}.\n"
                    f"- Baches detectados: {cantidad}\n"
                    f"- Confianza promedio: {confianza_promedio:.2%}\n"
                    f"- Coordenadas: Lat: {lat}, Lng: {lng}\n\n"
                    "REGLA DE ORO: Si el usuario pregunta algo que NO sea sobre baches, calles o el video (ej. Python, clima, recetas), NO USES HERRAMIENTAS. Respondé: 'Lo siento, estoy diseñado exclusivamente para asistir en la inspección de baches'.\n\n"
                    "INSTRUCCIONES:\n"
                    "1. SOLO baches e infraestructura vial.\n"
                    "2. HERRAMIENTA DE MAPA: Usala SOLO si preguntan por calles o lugares cercanos a las coordenadas dadas.\n"
                    "3. OBJETIVIDAD: Basate en el reporte o el mapa. No inventes.\n\n"
                    "EJEMPLOS DE COMPORTAMIENTO:\n"
                    "User: ¿Qué versión de Python usás?\n"
                    "IA: Lo siento, estoy diseñado exclusivamente para asistir en la inspección de baches y no puedo responder sobre otros temas.\n"
                    "User: ¿Dónde están los baches?\n"
                    "IA: [Usa la herramienta consultar_mapa_osm]"
                ),
            },
            {"role": "user", "content": request.pregunta},
        ]

        async with httpx.AsyncClient() as client:
            respuesta_fase1 = await client.post(
                f"{settings.OLLAMA_URL}/api/chat",
                json={
                    "model": "llama3.2:3b",
                    "messages": mensajes,
                    "tools": herramientas,
                    "stream": False,
                },
                timeout=60.0,
            )
            respuesta_fase1.raise_for_status()
            mensaje_ia = respuesta_fase1.json().get("message", {})

            if "tool_calls" in mensaje_ia and mensaje_ia["tool_calls"]:
                logger.info("El Agente decidió usar el mapa de OpenStreetMap en vivo.")

                argumentos_crudos = mensaje_ia["tool_calls"][0]["function"].get(
                    "arguments", {}
                )

                if isinstance(argumentos_crudos, str):
                    try:
                        argumentos = json.loads(argumentos_crudos)
                    except json.JSONDecodeError:
                        logger.warning("La IA mando un JSON inválido. Rescatando...")
                        argumentos = {}
                else:
                    argumentos = argumentos_crudos

                if not isinstance(argumentos, dict):
                    argumentos = {}

                arg_lat = lat
                arg_lng = lng
                try:
                    if "lat" in argumentos and argumentos["lat"] not in [None, ""]:
                        arg_lat = float(argumentos["lat"])
                    if "lng" in argumentos and argumentos["lng"] not in [None, ""]:
                        arg_lng = float(argumentos["lng"])
                except (ValueError, TypeError):
                    logger.warning("La IA Usó las reales de la BD.")

                datos_osm = await obtener_contexto_geografico(
                    arg_lat, arg_lng, radio_pois=400
                )
                logger.info(f"Datos obtenidos de OSM: {datos_osm}")

                mensajes.append(mensaje_ia)
                mensajes.append({"role": "tool", "content": json.dumps(datos_osm)})

                respuesta_fase2 = await client.post(
                    f"{settings.OLLAMA_URL}/api/chat",
                    json={
                        "model": "llama3.2:3b",
                        "messages": mensajes,
                        "stream": False,
                    },
                    timeout=60.0,
                )
                respuesta_fase2.raise_for_status()
                texto_final = (
                    respuesta_fase2.json()
                    .get("message", {})
                    .get("content", "Error al procesar.")
                )

            else:
                logger.info(
                    "El Agente respondió directamente usando el reporte/contexto."
                )
                texto_final = mensaje_ia.get("content", "Sin respuesta.")

        return {
            "video_id": video_id,
            "pregunta": request.pregunta,
            "respuesta": texto_final,
        }

    except Exception as e:
        logger.error("=== ERROR EN EL AGENTE ===")
        logger.error(str(e))
        logger.error(traceback.format_exc())
        logger.error("==========================")
        raise HTTPException(
            status_code=500, detail="Error en la Inteligencia Artificial."
        )


@router.delete("/api/v1/sistema/reset", tags=["Mantenimiento"])
def resetear_base_de_datos(db: Session = Depends(get_db)):
    """Botón rojo: Borra todos los videos y detecciones, y resetea los IDs a 1."""
    try:
        db.execute(
            text(
                "TRUNCATE TABLE video, deteccion, reporte, reporte_video, telemetria RESTART IDENTITY CASCADE;"
            )
        )
        db.commit()
        return {
            "mensaje": "¡Sistema reseteado! Los mapas están en blanco y el próximo video será el ID: 1"
        }
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))
