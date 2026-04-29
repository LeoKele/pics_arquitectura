import json
import logging
import os
import time
from datetime import datetime

import httpx
import models
import redis
import schemas
from database import engine, get_db
from fastapi import Depends, FastAPI, File, HTTPException, Response, UploadFile, status
from geoalchemy2.functions import ST_AsGeoJSON
from minio import Minio
from minio.error import S3Error
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session


class PreguntaRequest(BaseModel):
    pregunta: str


class GenerarReporteRequest(BaseModel):
    video_ids: list[int] = (
        []
    )  # Si la lista está vacía, analizará TODOS los videos procesados


# Logging
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
@app.get(
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


OLLAMA_URL = os.getenv("OLLAMA_URL", "http://ollama:11434")


@app.post(
    "/api/v1/reportes/generar",
    status_code=status.HTTP_201_CREATED,
    tags=["Inteligencia Artificial"],
)
def generar_reporte(request: GenerarReporteRequest, db: Session = Depends(get_db)):
    try:
        resultados = []

        # =================================================================
        # CASO A: Lista específica de videos (Ej: [15, 16]) -> Reportes Individuales
        # =================================================================
        if request.video_ids:
            videos = (
                db.query(models.Video)
                .filter(
                    models.Video.id.in_(request.video_ids),
                    models.Video.estado == "procesado",
                )
                .all()
            )

            if not videos:
                raise HTTPException(
                    status_code=404, detail="No se encontraron los videos indicados."
                )

            for video in videos:

                query_clusters = text("""
                    WITH clusters AS (
                        SELECT tipo_dano, confianza,
                               ST_ClusterDBSCAN(geom, 0.00005, 1) OVER(PARTITION BY tipo_dano) as cluster_id
                        FROM deteccion WHERE video_id = :v_id
                    )
                    SELECT MAX(confianza) as conf_max FROM clusters GROUP BY tipo_dano, cluster_id
                """)
                baches_agrupados = db.execute(
                    query_clusters, {"v_id": video.id}
                ).fetchall()

                cantidad_baches = len(baches_agrupados)
                confianza_promedio = (
                    sum(r.conf_max for r in baches_agrupados) / cantidad_baches
                    if cantidad_baches > 0
                    else 0
                )
                # -------------------------------------------------------------

                prompt = f"""Sos un inspector vial municipal de Moreno.
                Redactá un informe ejecutivo breve y formal en español.

                Datos de la inspección:
                - Archivo de origen: {video.nombre_archivo}
                - Cantidad de baches reales detectados: {cantidad_baches}
                - Confianza promedio de la IA: {confianza_promedio:.0%}

                El informe debe tener 3 párrafos exactos:
                1. Resumen ejecutivo.
                2. Análisis del estado vial.
                3. Recomendación de acción prioritaria.
                Sé conciso y profesional."""

                logger.info(f"Pidiendo reporte a Ollama para el video {video.id}...")
                response = httpx.post(
                    f"{OLLAMA_URL}/api/generate",
                    json={"model": "llama3.2:3b", "prompt": prompt, "stream": False},
                    timeout=120.0,
                )
                response.raise_for_status()
                contenido_reporte = response.json().get("response")

                # Guardar en BD
                reporte_db = (
                    db.query(models.Reporte)
                    .filter(models.Reporte.video_id == video.id)
                    .first()
                )
                if reporte_db:
                    reporte_db.contenido = contenido_reporte
                    reporte_db.fecha_generacion = datetime.utcnow()
                else:
                    nuevo_reporte = models.Reporte(
                        video_id=video.id, contenido=contenido_reporte
                    )
                    db.add(nuevo_reporte)

                resultados.append({"video_id": video.id, "reporte": contenido_reporte})

            db.commit()
            return {
                "mensaje": f"Se generaron y guardaron {len(resultados)} reportes individuales.",
                "reportes": resultados,
            }

        # =================================================================
        # CASO B: Lista vacía [] -> Mega Reporte Global (ID 0)
        # =================================================================
        else:
            videos = (
                db.query(models.Video).filter(models.Video.estado == "procesado").all()
            )
            if not videos:
                raise HTTPException(status_code=400, detail="No hay videos procesados.")

            ids_str = ",".join(str(v.id) for v in videos)
            query_global = text(f"""
                WITH clusters AS (
                    SELECT tipo_dano, confianza,
                           ST_ClusterDBSCAN(geom, 0.00005, 1) OVER(PARTITION BY tipo_dano) as cluster_id
                    FROM deteccion WHERE video_id IN ({ids_str})
                )
                SELECT MAX(confianza) as conf_max FROM clusters GROUP BY tipo_dano, cluster_id
            """)
            baches_globales = db.execute(query_global).fetchall()

            cantidad_baches = len(baches_globales)
            confianza_promedio = (
                sum(r.conf_max for r in baches_globales) / cantidad_baches
                if cantidad_baches > 0
                else 0
            )
            # -------------------------------------------------------------

            prompt = f"""Sos un inspector vial municipal de Moreno. Redactá un informe ejecutivo breve y formal en español.

            Datos de la inspección global del municipio:
            - Cantidad de videos analizados: {len(videos)}
            - Cantidad total de baches reales detectados en las calles: {cantidad_baches}
            - Confianza promedio de la IA: {confianza_promedio:.0%}

            El informe debe tener 3 párrafos exactos:
            1. Resumen ejecutivo.
            2. Análisis del estado vial global.
            3. Recomendación de acción prioritaria municipal.
            Sé conciso."""

            logger.info("Pidiendo reporte global a Ollama...")
            response = httpx.post(
                f"{OLLAMA_URL}/api/generate",
                json={"model": "llama3.2:3b", "prompt": prompt, "stream": False},
                timeout=120.0,
            )
            response.raise_for_status()
            contenido_reporte = response.json().get("response")

            reporte_db = (
                db.query(models.Reporte).filter(models.Reporte.video_id == 0).first()
            )
            if reporte_db:
                reporte_db.contenido = contenido_reporte
                reporte_db.fecha_generacion = datetime.utcnow()
            else:
                nuevo_reporte = models.Reporte(
                    video_id=None, contenido=contenido_reporte
                )
                db.add(nuevo_reporte)

            db.commit()
            return {
                "mensaje": "Reporte global generado y guardado",
                "tipo": "global",
                "reporte": contenido_reporte,
            }

    except Exception as e:
        logger.error(f"Error generando reporte: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/reporte/{video_id}", tags=["Inteligencia Artificial"])
def obtener_reporte(video_id: int, db: Session = Depends(get_db)):
    # Si el usuario pide el 0, buscamos el reporte que tiene video_id nulo (Global)
    if video_id == 0:
        reporte = (
            db.query(models.Reporte).filter(models.Reporte.video_id is None).first()
        )
    else:
        reporte = (
            db.query(models.Reporte).filter(models.Reporte.video_id == video_id).first()
        )

    if not reporte:
        raise HTTPException(
            status_code=404,
            detail=f"No hay reporte para el ID {video_id}. Si buscás el total, usá ID 0.",
        )

    return {
        "tipo": "Global" if video_id == 0 else "Individual",
        "video_id": video_id,
        "contenido": reporte.contenido,
        "fecha": reporte.fecha_generacion,
    }


@app.patch("/api/v1/detecciones/{deteccion_id}", status_code=status.HTTP_200_OK)
def auditar_deteccion(
    deteccion_id: int, nuevo_estado: str, db: Session = Depends(get_db)
):
    logger.info(f"Iniciando auditoría para detección ID: {deteccion_id}")

    deteccion = (
        db.query(models.Deteccion).filter(models.Deteccion.id == deteccion_id).first()
    )

    if not deteccion:
        logger.warning(f"Detección ID {deteccion_id} no encontrada para auditar")
        raise HTTPException(status_code=404, detail="Detección no encontrada")

    deteccion.estado_auditoria = nuevo_estado

    db.commit()
    db.refresh(deteccion)

    logger.info(
        f"Detección {deteccion_id} auditada con éxito. Nuevo estado: {nuevo_estado}"
    )

    return {
        "mensaje": "Estado de auditoría actualizado correctamente",
        "id": deteccion.id,
        "estado_actual": deteccion.estado_auditoria,
    }


@app.get("/api/v1/health", tags=["Monitoreo"])
async def health_check(response: Response, db: Session = Depends(get_db)):
    """
    Semáforo de estado de salud de la infraestructura.
    Verifica la conexión con PostgreSQL, Redis, MinIO y Ollama.
    """
    servicios = {
        "postgresql": "DESCONOCIDO",
        "redis": "DESCONOCIDO",
        "minio": "DESCONOCIDO",
        "ollama": "DESCONOCIDO",
    }
    estado_general = "VERDE"

    # 1. Chequeo de PostgreSQL
    try:
        db.execute(text("SELECT 1"))
        servicios["postgresql"] = "OK"
    except Exception as e:
        servicios["postgresql"] = f"ERROR: {str(e)}"
        estado_general = "ROJO"

    # 2. Chequeo de Redis (Usando tu variable 'r')
    try:
        if r.ping():
            servicios["redis"] = "OK"
    except Exception as e:
        servicios["redis"] = f"ERROR: {str(e)}"
        estado_general = "ROJO"

    # 3. Chequeo de MinIO (Usando tus variables 'minio_client' y 'BUCKET_NAME')
    try:
        minio_client.bucket_exists(BUCKET_NAME)
        servicios["minio"] = "OK"
    except Exception as e:
        servicios["minio"] = f"ERROR: {str(e)}"
        estado_general = "ROJO"

    # 4. Chequeo de Ollama (Usando tu variable 'OLLAMA_URL')
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            res = await client.get(f"{OLLAMA_URL}/")
            if res.status_code == 200:
                servicios["ollama"] = "OK"
            else:
                servicios["ollama"] = f"ERROR: Status {res.status_code}"
                if estado_general == "VERDE":
                    estado_general = "AMARILLO"
    except Exception as e:
        servicios["ollama"] = "ERROR: Timeout/Desconectado"
        if estado_general == "VERDE":
            estado_general = "AMARILLO"

    # Modificar el código de estado HTTP de la respuesta si es necesario
    if estado_general == "ROJO":
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    return {
        "estado_general": estado_general,
        "timestamp": datetime.utcnow().isoformat(),
        "servicios": servicios,
    }


@app.post("/api/v1/video/{video_id}/preguntar", tags=["Inteligencia Artificial"])
def preguntar_a_video(
    video_id: int, request: PreguntaRequest, db: Session = Depends(get_db)
):
    """
    Permite hacerle una pregunta en lenguaje natural a la IA sobre los resultados de un video.
    """
    # 1. Validar video
    video = db.query(models.Video).filter(models.Video.id == video_id).first()
    if not video:
        raise HTTPException(status_code=404, detail="Video no encontrado")
    if video.estado != "procesado":
        raise HTTPException(status_code=400, detail="El video aún no fue procesado.")

    # 2. Recopilar contexto
    detecciones = (
        db.query(models.Deteccion).filter(models.Deteccion.video_id == video_id).all()
    )
    cantidad = len(detecciones)
    confianza_promedio = (
        sum(d.confianza for d in detecciones) / cantidad if cantidad > 0 else 0
    )

    # 3. Armar el Prompt con el contexto y la pregunta
    prompt = f"""Sos un asistente técnico de inspección vial.
    A continuación te paso los datos del análisis del video {video_id}:
    - Cantidad total de baches detectados: {cantidad}
    - Nivel de confianza promedio del algoritmo: {confianza_promedio:.2%}

    El usuario te hace la siguiente pregunta sobre esta inspección: "{request.pregunta}"

    Respondé de forma breve, directa y profesional basándote ÚNICAMENTE en los datos provistos. Si la pregunta no tiene relación con calles, baches o inspecciones, indicá amablemente que no podés responder eso."""

    # 4. Consultar a Ollama
    try:
        response = httpx.post(
            f"{OLLAMA_URL}/api/generate",
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


@app.get("/api/v1/detecciones/agrupadas/{video_id}")
def obtener_detecciones_agrupadas(video_id: int, db: Session = Depends(get_db)):
    query = text("""
        WITH clusters AS (
            SELECT
                tipo_dano,
                confianza,
                -- Agrupa los puntos que estén a menos de ~5 metros de distancia
                ST_ClusterDBSCAN(geom, 0.00005, 1) OVER(PARTITION BY tipo_dano) as cluster_id,
                geom
            FROM deteccion
            WHERE video_id = :video_id
        )
        SELECT
            tipo_dano,
            MAX(confianza) as confianza_maxima,
            COUNT(*) as frames_detectados,
            ST_AsGeoJSON(ST_Centroid(ST_Collect(geom))) as geometria
        FROM clusters
        GROUP BY tipo_dano, cluster_id
    """)

    resultados = db.execute(query, {"video_id": video_id}).fetchall()

    detecciones_limpias = []
    for fila in resultados:
        detecciones_limpias.append(
            {
                "tipo_dano": fila.tipo_dano,
                "confianza_maxima": round(fila.confianza_maxima, 2),
                "cantidad_frames": fila.frames_detectados,  # Te dice en cuántas fotos apareció
                "coordenada_central": json.loads(fila.geometria),
            }
        )

    return {
        "video_id": video_id,
        "total_baches_reales": len(detecciones_limpias),
        "baches": detecciones_limpias,
    }


@app.get("/api/v1/sistema/inventario", tags=["Monitoreo"])
def obtener_total_archivos(db: Session = Depends(get_db)):
    """
    Lista todos los videos registrados en la base de datos y
    todos los archivos (videos y jsons) almacenados físicamente en MinIO.
    """
    try:
        # 1. Consultar videos en la Base de Datos
        videos_db = db.query(models.Video).all()
        lista_videos_db = [
            {"id": v.id, "nombre": v.nombre_archivo, "estado": v.estado}
            for v in videos_db
        ]

        # 2. Consultar archivos físicos en MinIO
        # Listamos todos los objetos del bucket
        objetos = minio_client.list_objects(BUCKET_NAME, recursive=True)

        jsons_fisicos = []
        videos_fisicos = []

        for obj in objetos:
            if obj.object_name.endswith(".json"):
                jsons_fisicos.append(
                    {
                        "nombre": obj.object_name,
                        "tamaño_kb": round(obj.size / 1024, 2),
                        "ultima_modificacion": obj.last_modified.isoformat(),
                    }
                )
            else:
                videos_fisicos.append(
                    {
                        "nombre": obj.object_name,
                        "tamaño_mb": round(obj.size / (1024 * 1024), 2),
                    }
                )

        return {
            "conteo": {
                "total_registros_db": len(lista_videos_db),
                "total_jsons_minio": len(jsons_fisicos),
                "total_videos_minio": len(videos_fisicos),
            },
            "base_de_datos": {"videos_registrados": lista_videos_db},
            "almacenamiento_fisico_minio": {
                "jsons": jsons_fisicos,
                "videos": videos_fisicos,
            },
        }
    except Exception as e:
        logger.error(f"Error al obtener inventario: {e}")
        raise HTTPException(
            status_code=500, detail=f"Error al consultar el sistema: {str(e)}"
        )
