import json
import logging
import traceback
from io import BytesIO

import httpx
import models
import schemas
from configs.config import settings
from database import get_db
from dependencias import minio_client, r, s3_client, s3_public_client
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from minio.error import S3Error
from pydantic import BaseModel
from services.geo_service import obtener_contexto_geografico
from sqlalchemy import text
from sqlalchemy.orm import Session

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

        # El Agente decide si usa la herramienta o responde directo segun convenga
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

            # Ejecución de la herramienta
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

                # Conversión a floats x q si no no funciona bien
                arg_lat = lat
                arg_lng = lng
                try:
                    if "lat" in argumentos and argumentos["lat"] not in [None, ""]:
                        arg_lat = float(argumentos["lat"])
                    if "lng" in argumentos and argumentos["lng"] not in [None, ""]:
                        arg_lng = float(argumentos["lng"])
                except (ValueError, TypeError):
                    logger.warning("La IA Usó las reales de la BD.")
                # -----------------------------------------------------

                # Llamada real a geo_service
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


@router.post(
    "/api/v1/videos/upload/iniciar",
    status_code=status.HTTP_200_OK,
    response_model=schemas.UploadIniciarResponse,
)
def iniciar_upload_multipart(
    payload: schemas.UploadIniciarRequest, db: Session = Depends(get_db)
):
    if not payload.nombre_archivo.endswith((".mp4", ".webm")):
        logger.warning(
            f"Archivo rechazado por extensión inválida: {payload.nombre_archivo}"
        )
        raise HTTPException(
            status_code=422, detail="El archivo de video debe ser .mp4 o .webm"
        )

    nombre_base = payload.nombre_archivo.rsplit(".", 1)[0]
    nombre_json = f"{nombre_base}.json"

    nuevo_video = models.Video(
        nombre_archivo=payload.nombre_archivo,
        nombre_metadata=nombre_json,
        estado="esperando_video",
    )
    db.add(nuevo_video)
    db.commit()
    db.refresh(nuevo_video)
    logger.info(
        f"Video registrado en BD con ID: {nuevo_video.id} (estado: esperando_video)"
    )

    try:
        if not minio_client.bucket_exists(settings.BUCKET_NAME):
            minio_client.make_bucket(settings.BUCKET_NAME)

        # Configurar CORS en el bucket de MinIO para permitir peticiones directas de subida desde el navegador
        try:
            cors_configuration = {
                "CORSRules": [
                    {
                        "AllowedHeaders": ["*"],
                        "AllowedMethods": ["GET", "PUT", "POST", "DELETE", "HEAD"],
                        "AllowedOrigins": ["*"],
                        "ExposeHeaders": ["ETag", "x-amz-request-id"],
                        "MaxAgeSeconds": 3000,
                    }
                ]
            }
            s3_client.put_bucket_cors(
                Bucket=settings.BUCKET_NAME, CORSConfiguration=cors_configuration
            )
            logger.info(
                f"CORS configurado exitosamente para el bucket {settings.BUCKET_NAME}"
            )
        except Exception as cors_err:
            logger.warning(
                f"No se pudo configurar CORS en el bucket de MinIO: {cors_err}"
            )

        json_bytes = json.dumps(payload.gps_metadata).encode("utf-8")
        minio_client.put_object(
            settings.BUCKET_NAME,
            nombre_json,
            BytesIO(json_bytes),
            len(json_bytes),
            content_type="application/json",
        )
        logger.info(f"Metadata GPS guardada en MinIO: {nombre_json}")
    except Exception as e:
        logger.error(f"Error guardando metadata GPS en MinIO: {e}")
        db.delete(nuevo_video)
        db.commit()
        raise HTTPException(
            status_code=500,
            detail=f"Error al inicializar almacenamiento de metadata: {e}",
        )

    try:
        response = s3_client.create_multipart_upload(
            Bucket=settings.BUCKET_NAME,
            Key=payload.nombre_archivo,
            ContentType=(
                "video/webm"
                if payload.nombre_archivo.endswith(".webm")
                else "video/mp4"
            ),
        )
        upload_id = response["UploadId"]
        logger.info(f"Creado multipart upload en MinIO. UploadId: {upload_id}")
    except Exception as e:
        logger.error(f"Error creando multipart upload en S3/MinIO: {e}")
        try:
            minio_client.remove_object(settings.BUCKET_NAME, nombre_json)
        except Exception:
            pass
        db.delete(nuevo_video)
        db.commit()
        raise HTTPException(
            status_code=500,
            detail=f"Error al iniciar carga multipart en almacenamiento: {e}",
        )

    return {
        "video_id": nuevo_video.id,
        "upload_id": upload_id,
        "key": payload.nombre_archivo,
    }


@router.post(
    "/api/v1/videos/upload/firmar-partes",
    status_code=status.HTTP_200_OK,
    response_model=schemas.UploadFirmaResponse,
)
def firmar_partes_upload(payload: schemas.UploadFirmaRequest):
    urls = {}
    try:
        for part_number in payload.part_numbers:
            url = s3_public_client.generate_presigned_url(
                ClientMethod="upload_part",
                Params={
                    "Bucket": settings.BUCKET_NAME,
                    "Key": payload.key,
                    "UploadId": payload.upload_id,
                    "PartNumber": part_number,
                },
                ExpiresIn=3600,
            )
            urls[part_number] = url
        return {"urls": urls}
    except Exception as e:
        logger.error(f"Error generando URLs prefirmadas: {e}")
        raise HTTPException(
            status_code=500, detail=f"Error al generar firmas de carga: {e}"
        )


@router.post(
    "/api/v1/videos/upload/finalizar",
    status_code=status.HTTP_200_OK,
)
def finalizar_upload_multipart(
    payload: schemas.UploadFinalizarRequest, db: Session = Depends(get_db)
):
    video = db.query(models.Video).filter(models.Video.id == payload.video_id).first()
    if not video:
        logger.warning(
            f"Video ID {payload.video_id} no encontrado en base de datos al finalizar"
        )
        raise HTTPException(status_code=404, detail="Registro de video no encontrado")

    try:
        parts_list = []
        for p in payload.partes:
            parts_list.append({"PartNumber": p.PartNumber, "ETag": p.ETag})

        parts_list = sorted(parts_list, key=lambda x: x["PartNumber"])

        s3_client.complete_multipart_upload(
            Bucket=settings.BUCKET_NAME,
            Key=payload.key,
            UploadId=payload.upload_id,
            MultipartUpload={"Parts": parts_list},
        )
        logger.info(f"Completado Multipart Upload en MinIO para key: {payload.key}")
    except Exception as e:
        logger.error(f"Error al completar multipart upload en MinIO: {e}")
        try:
            s3_client.abort_multipart_upload(
                Bucket=settings.BUCKET_NAME, Key=payload.key, UploadId=payload.upload_id
            )
            logger.warning(
                f"Abortado multipart upload {payload.upload_id} debido a error"
            )
        except Exception as abort_err:
            logger.error(f"No se pudo abortar el multipart upload: {abort_err}")

        video.estado = "error"
        db.commit()
        raise HTTPException(
            status_code=500, detail=f"Error al consolidar el archivo de video: {e}"
        )

    video.estado = "pendiente"
    db.commit()
    logger.info(
        f"Video ID {video.id} actualizado a estado 'pendiente' y listo para procesamiento"
    )

    try:
        r.rpush("cola_preprocesamiento", video.id)
        logger.info(f"Tarea encolada en Redis para video ID: {video.id}")
    except Exception as e:
        logger.error(f"Error al enviar tarea a Redis para video ID {video.id}: {e}")

    return {"mensaje": "Video subido y consolidado con éxito. Procesamiento iniciado."}
