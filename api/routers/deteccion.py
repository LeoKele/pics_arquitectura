import json
import logging

import models
import schemas
from database import get_db
from fastapi import APIRouter, Depends, HTTPException, status
from geoalchemy2.functions import ST_AsGeoJSON
from sqlalchemy import text
from sqlalchemy.orm import Session

router = APIRouter()
logger = logging.getLogger("api.deteccion")


@router.get("/api/v1/detecciones", response_model=list[schemas.DeteccionResponse])
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
