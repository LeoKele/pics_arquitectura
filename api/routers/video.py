import json
import logging
import traceback
from typing import Any, Dict, List, Optional

import models
import schemas
from configs.config import settings
from database import get_db
from dependencias import minio_client, r, s3_internal_client, s3_public_client
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from minio.error import S3Error
from openai import AsyncOpenAI
from pydantic import BaseModel
from services.geo_service import obtener_contexto_geografico
from sqlalchemy import text
from sqlalchemy.orm import Session

router = APIRouter()
logger = logging.getLogger("api.video")

# --- CLIENTE DEL PROFESOR ---
ollama_client = AsyncOpenAI(
    base_url=f"{settings.OLLAMA_URL}/v1", api_key=settings.OLLAMA_TOKEN or "ollama"
)


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

    try:
        r.rpush("cola_preprocesamiento", nuevo_video.id)
    except Exception as e:
        logger.error(f"Error al enviar tarea a Redis: {e}")

    return {
        "mensaje": "Video y metadata recibidos correctamente",
        "video_id": nuevo_video.id,
        "estado": nuevo_video.estado,
    }


@router.post("/api/v1/videos/upload/iniciar", tags=["Videos Multipart"])
def iniciar_upload_multipart(request: IniciarUploadRequest):
    try:
        if not minio_client.bucket_exists(settings.BUCKET_NAME):
            minio_client.make_bucket(settings.BUCKET_NAME)
        response = s3_internal_client.create_multipart_upload(
            Bucket=settings.BUCKET_NAME,
            Key=request.filename,
            ContentType=request.content_type,
        )
        return {"upload_id": response["UploadId"], "key": request.filename}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/v1/videos/upload/firmar-parte", tags=["Videos Multipart"])
def firmar_parte(request: ParteFirmadaRequest):
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
        raise HTTPException(status_code=500, detail=str(e))


@router.post(
    "/api/v1/videos/upload/finalizar",
    status_code=status.HTTP_202_ACCEPTED,
    tags=["Videos Multipart"],
)
def finalizar_upload_multipart(
    request: FinalizarUploadRequest, db: Session = Depends(get_db)
):
    try:
        s3_internal_client.complete_multipart_upload(
            Bucket=settings.BUCKET_NAME,
            Key=request.filename,
            UploadId=request.upload_id,
            MultipartUpload={"Parts": request.parts},
        )
        json_filename = request.filename.replace(".webm", ".json")

        try:
            s3_internal_client.put_object(
                Bucket=settings.BUCKET_NAME,
                Key=json_filename,
                Body=json.dumps(request.telemetria),
                ContentType="application/json",
            )
        except Exception as e:
            logger.error(f"Error guardando telemetría en MinIO: {e}")

        nuevo_video = models.Video(
            nombre_archivo=request.filename,
            nombre_metadata=json_filename,
            estado="pendiente",
        )
        db.add(nuevo_video)
        db.commit()
        db.refresh(nuevo_video)

        try:
            r.rpush("cola_preprocesamiento", nuevo_video.id)
        except Exception as redis_e:
            logger.error(f"Error al enviar tarea a Redis: {redis_e}")

        return {
            "mensaje": "Video y telemetría guardados",
            "video_id": nuevo_video.id,
            "estado": nuevo_video.estado,
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/api/v1/videos/{video_id}",
    response_model=schemas.VideoStatusResponse,
    tags=["Monitoreo"],
)
def obtener_estado_video(video_id: int, db: Session = Depends(get_db)):
    video = db.query(models.Video).filter(models.Video.id == video_id).first()
    if not video:
        raise HTTPException(status_code=404, detail="Video no encontrado")
    return {"id": video.id, "estado": video.estado}


@router.post("/api/v1/video/{video_id}/preguntar", tags=["Inteligencia Artificial"])
async def preguntar_a_video(
    video_id: int, request: PreguntaRequest, db: Session = Depends(get_db)
):
    try:
        if video_id == 0:
            # MODO GLOBAL: Todos los videos
            detecciones = (
                db.query(models.Deteccion)
                .filter(models.Deteccion.estado_auditoria != "falso_positivo")
                .all()
            )
            reporte = (
                db.query(models.Reporte)
                .order_by(models.Reporte.fecha_generacion.desc())
                .first()
            )
            contexto_str = "TODOS los videos y recorridos procesados del municipio"

            query_centroide = text("""
                SELECT ST_Y(ST_Centroid(ST_Collect(geom))) as lat,
                       ST_X(ST_Centroid(ST_Collect(geom))) as lng
                FROM deteccion WHERE estado_auditoria != 'falso_positivo'
            """)
            centroide = db.execute(query_centroide).fetchone()
        else:
            # MODO ESPECÍFICO: Solo un video
            video = db.query(models.Video).filter(models.Video.id == video_id).first()
            if not video:
                raise HTTPException(status_code=404, detail="Video no encontrado")
            if video.estado != "procesado":
                raise HTTPException(
                    status_code=400, detail="El video aún no fue procesado."
                )

            detecciones = (
                db.query(models.Deteccion)
                .filter(
                    models.Deteccion.video_id == video_id,
                    models.Deteccion.estado_auditoria != "falso_positivo",
                )
                .all()
            )
            reporte = (
                db.query(models.Reporte)
                .join(models.ReporteVideo)
                .filter(models.ReporteVideo.video_id == video_id)
                .order_by(models.Reporte.fecha_generacion.desc())
                .first()
            )
            contexto_str = f"el video #{video_id}"

            query_centroide = text("""
                SELECT ST_Y(ST_Centroid(ST_Collect(geom))) as lat,
                       ST_X(ST_Centroid(ST_Collect(geom))) as lng
                FROM deteccion WHERE video_id = :v_id AND estado_auditoria != 'falso_positivo'
            """)
            centroide = db.execute(query_centroide, {"v_id": video_id}).fetchone()

        cantidad = len(detecciones)

        reporte_texto = (
            reporte.contenido[:1500]
            if reporte and reporte.contenido
            else "No hay reportes previos."
        )

        lat = float(centroide[0]) if centroide and centroide[0] else -34.64
        lng = float(centroide[1]) if centroide and centroide[1] else -58.79

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

        mensajes = [
            {
                "role": "system",
                "content": (
                    f"Sos el asistente virtual de infraestructura vial de la Municipalidad de Moreno.\n\n"
                    f"--- DATOS REALES DE {contexto_str.upper()} ---\n"
                    f"Cantidad total de baches detectados: {cantidad}\n"
                    f"Ubicacion: Lat {lat}, Lng {lng}\n"
                    f"Resumen técnico de la zona: {reporte_texto}\n"
                    f"-----------------------------------------\n\n"
                    "REGLAS DE COMPORTAMIENTO (CUMPLIR ESTRICTAMENTE):\n"
                    "1. SI EL USUARIO SALUDA: Responde UNICAMENTE '¡Hola! Soy tu asistente vial de Moreno. ¿Qué necesitás saber sobre nuestras inspecciones?'.\n"
                    "2. PREGUNTAS GENERALES: Si te preguntan cuántos baches hay, respondé con la cantidad total mencionada en los datos.\n"
                    "3. USO DE HERRAMIENTA OBLIGATORIO: Debes usar SIEMPRE la herramienta 'consultar_mapa_osm' antes de responder cualquier cosa sobre un video específico, para saber en qué calle estás.\n"
                    "4. PROHIBIDO INVENTAR: Basate exclusivamente en los datos reales y el resumen técnico provisto.\n"
                ),
            },
            {"role": "user", "content": request.pregunta},
        ]

        respuesta_fase1 = await ollama_client.chat.completions.create(
            model="llama3.2:3b",
            messages=mensajes,
            tools=herramientas,
            tool_choice={"type": "function", "function": {"name": "consultar_mapa_osm"}}, 
            stream=False,
            temperature=0.1,
        )

        mensaje_ia = respuesta_fase1.choices[0].message

        if getattr(mensaje_ia, "tool_calls", None):
            logger.info("El Agente decidió usar el mapa de OpenStreetMap.")

            tool_call = mensaje_ia.tool_calls[0]
            argumentos_crudos = tool_call.function.arguments

            try:
                argumentos = json.loads(argumentos_crudos) if argumentos_crudos else {}
            except Exception:
                argumentos = {}

            arg_lat, arg_lng = lat, lng
            try:
                if "lat" in argumentos and isinstance(
                    argumentos["lat"], (int, float, str)
                ):
                    arg_lat = float(argumentos["lat"])
                if "lng" in argumentos and isinstance(
                    argumentos["lng"], (int, float, str)
                ):
                    arg_lng = float(argumentos["lng"])
            except (ValueError, TypeError):
                pass

            datos_osm = await obtener_contexto_geografico(
                arg_lat, arg_lng, radio_pois=400
            )

            mensajes.append(
                {
                    "role": "assistant",
                    "content": mensaje_ia.content or "",
                    "tool_calls": [
                        {
                            "id": tool_call.id,
                            "type": "function",
                            "function": {
                                "name": tool_call.function.name,
                                "arguments": tool_call.function.arguments,
                            },
                        }
                    ],
                }
            )

            mensajes.append(
                {
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "name": tool_call.function.name,
                    "content": json.dumps(datos_osm),
                }
            )

            respuesta_fase2 = await ollama_client.chat.completions.create(
                model="llama3.2:3b", messages=mensajes, stream=False, temperature=0.1
            )
            texto_final = (
                respuesta_fase2.choices[0].message.content or "Error al procesar."
            )

        else:
            logger.info("El Agente respondió directamente usando el reporte/contexto.")
            texto_final = mensaje_ia.content or "Sin respuesta."

        return {
            "video_id": video_id,
            "pregunta": request.pregunta,
            "respuesta": texto_final,
        }

    except Exception as e:
        logger.error("=== ERROR EN EL AGENTE ===")
        logger.error(str(e))
        logger.error(traceback.format_exc())
        raise HTTPException(
            status_code=500, detail="Error en la Inteligencia Artificial."
        )


@router.delete("/api/v1/sistema/reset", tags=["Mantenimiento"])
def resetear_base_de_datos(db: Session = Depends(get_db)):
    try:
        db.execute(
            text(
                "TRUNCATE TABLE video, deteccion, reporte, reporte_video, telemetria RESTART IDENTITY CASCADE;"
            )
        )
        db.commit()
        return {
            "mensaje": "¡Sistema reseteado! Los mapas están en blanco y el próximo video será el ID: 1."
        }
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))
