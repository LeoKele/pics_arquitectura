import json
import logging

import models
import schemas
from database import get_db
from fastapi import APIRouter, Depends, HTTPException, status
from geoalchemy2.functions import ST_AsGeoJSON
from sqlalchemy import text
from sqlalchemy.orm import Session
# Importamos el cliente de MinIO que ya tenías configurado
from dependencias import minio_client

router = APIRouter()
logger = logging.getLogger("api.deteccion")


# --- NUEVA FUNCIÓN PARA CONTAR EN MINIO ---
def contar_falsos_positivos_en_minio():
    """
    Cuenta directamente la cantidad de objetos en el bucket de reentrenamiento.
    Esto garantiza que el número de falsos positivos sea siempre exacto en el Dashboard.
    """
    reentrenamiento_bucket = "backgrounds-reentrenamiento"
    try:
        if not minio_client.bucket_exists(reentrenamiento_bucket):
            return 0
        
        # list_objects devuelve un iterador, lo convertimos a lista para contarlo
        objetos = list(minio_client.list_objects(reentrenamiento_bucket, recursive=True))
        return len(objetos)
    except Exception as e:
        logger.error(f"Error al contar objetos en MinIO: {e}")
        return 0
# ----------------------------------------


# --- NUEVO ENDPOINT DE MÉTRICAS ---
@router.get("/api/v1/metricas")
def obtener_metricas(db: Session = Depends(get_db)):
    """
    Devuelve las métricas generales consolidadas para el Dashboard.
    Combina datos de la base de datos (baches activos) con datos físicos (MinIO).
    """
    logger.info("Calculando métricas generales para el Dashboard")

    # 1. Contamos desde PostgreSQL (solo los NO falsos positivos)
    total_baches = db.query(models.Deteccion).filter(
        models.Deteccion.tipo_dano == "D40",
        models.Deteccion.estado_auditoria != "falso_positivo"
    ).count()
    
    total_grietas = db.query(models.Deteccion).filter(
        models.Deteccion.tipo_dano == "D20",
        models.Deteccion.estado_auditoria != "falso_positivo"
    ).count()
    
    total_tierras = db.query(models.Deteccion).filter(
        models.Deteccion.tipo_dano == "calle_tierra",
        models.Deteccion.estado_auditoria != "falso_positivo"
    ).count()

    total_verificados = db.query(models.Deteccion).filter(
        models.Deteccion.estado_auditoria == "verificado"
    ).count()
    
    total_pendientes = db.query(models.Deteccion).filter(
        models.Deteccion.estado_auditoria == "pendiente"
    ).count()

    # 2. Contamos Falsos Positivos directamente desde el almacenamiento físico (MinIO)
    total_falsos_positivos = contar_falsos_positivos_en_minio()

    # 3. El total absoluto es la suma de los reales en DB + los descartados en MinIO
    total_hallazgos = total_baches + total_grietas + total_tierras + total_falsos_positivos

    return {
        "total": total_hallazgos,
        "baches": total_baches,
        "grietas": total_grietas,
        "tierras": total_tierras,
        "verificadas": total_verificados,
        "pendientes": total_pendientes,
        "falsos": total_falsos_positivos
    }
# ----------------------------------------


@router.get("/api/v1/detecciones", response_model=list[schemas.DeteccionResponse])
def obtener_detecciones(db: Session = Depends(get_db)):
    logger.info("Consultando todas las detecciones")

    detecciones = (
        db.query(
            models.Deteccion.id,
            models.Deteccion.video_id,
            models.Deteccion.tipo_dano,
            models.Deteccion.confianza,
            ST_AsGeoJSON(models.Deteccion.geom).label("geometria"),
            models.Deteccion.fecha_deteccion,
            models.Deteccion.frame_minio_path,
            models.Deteccion.bbox,
            models.Deteccion.estado_auditoria,
        )
        # ACÁ ESTABA EL FILTRO. LO DEJAMOS COMO ESTÁ, YA QUE AHORA LAS MÉTRICAS VAN POR OTRO LADO.
        .filter(models.Deteccion.estado_auditoria != "falso_positivo")
        .all()
    )

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
                "bbox": d.bbox,
                "estado_auditoria": d.estado_auditoria,
            }
        )

    logger.info(f"Devolviendo {len(resultado)} detecciones activas")
    return resultado


@router.get("/api/v1/detecciones/agrupadas/{video_id}")
def obtener_detecciones_agrupadas(video_id: int, db: Session = Depends(get_db)):
    query = text("""
        WITH clusters AS (
            SELECT
                tipo_dano,
                confianza,
                -- Agrupa los puntos que estén a menos de ~5 metros de distancia
                ST_ClusterDBSCAN(geom, 0.00005, 1)
                OVER(PARTITION BY tipo_dano) as cluster_id,
                geom
            FROM deteccion
            WHERE video_id = :video_id AND estado_auditoria != 'falso_positivo'
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
                "cantidad_frames": fila.frames_detectados,
                "coordenada_central": json.loads(fila.geometria),
            }
        )

    return {
        "video_id": video_id,
        "total_baches_reales": len(detecciones_limpias),
        "baches": detecciones_limpias,
    }


@router.patch("/api/v1/detecciones/{deteccion_id}", status_code=status.HTTP_200_OK)
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

    if nuevo_estado.lower() == "falso_positivo":
        if deteccion.frame_minio_path:
            from dependencias import minio_client
            from minio.commonconfig import CopySource

            reentrenamiento_bucket = "backgrounds-reentrenamiento"

            try:
                # Asegurar que el bucket de reentrenamiento exista
                if not minio_client.bucket_exists(reentrenamiento_bucket):
                    minio_client.make_bucket(reentrenamiento_bucket)

                source = CopySource("detecciones", deteccion.frame_minio_path)
                minio_client.copy_object(
                    reentrenamiento_bucket, deteccion.frame_minio_path, source
                )
                logger.info(
                    f"Imagen limpia copiada a {reentrenamiento_bucket}/{deteccion.frame_minio_path}"
                )
            except Exception as e_copy:
                logger.error(
                    f"Error al intentar copiar la imagen a backgrounds-reentrenamiento: {e_copy}"
                )

            try:
                # Borrar la imagen del bucket activo de detecciones
                minio_client.remove_object("detecciones", deteccion.frame_minio_path)
                logger.info(
                    f"Imagen activa eliminada de detecciones: {deteccion.frame_minio_path}"
                )
            except Exception as e_remove:
                logger.error(
                    f"Error crítico al intentar eliminar la imagen de detecciones: {e_remove}"
                )

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


@router.get("/api/v1/trayectorias")
def obtener_trayectorias(db: Session = Depends(get_db)):
    puntos = (
        db.query(models.Telemetria)
        .order_by(models.Telemetria.video_id, models.Telemetria.tiempo)
        .all()
    )

    trayectorias = {}
    for p in puntos:
        if p.video_id not in trayectorias:
            trayectorias[p.video_id] = []

        # Extraemos lat y lon de PostGIS
        lon = db.scalar(p.geometria.ST_X())
        lat = db.scalar(p.geometria.ST_Y())

        trayectorias[p.video_id].append([lat, lon])

    return trayectorias  # Devuelve {"video_1": [[lat, lon], [lat, lon]...]}