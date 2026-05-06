import logging

import httpx
import models
from configs.config import settings
from database import get_db
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

router = APIRouter()
logger = logging.getLogger("api.reporte")


class GenerarReporteRequest(BaseModel):
    video_ids: list[int] = []


@router.post(
    "/api/v1/reportes/generar",
    status_code=status.HTTP_201_CREATED,
    tags=["Inteligencia Artificial"],
)
def generar_reporte(request: GenerarReporteRequest, db: Session = Depends(get_db)):
    try:
        query_videos = db.query(models.Video).filter(models.Video.estado == "procesado")

        if request.video_ids:
            query_videos = query_videos.filter(models.Video.id.in_(request.video_ids))

        videos = query_videos.all()

        if not videos:
            detalle = "No se encontraron videos procesados"
            if request.video_ids:
                detalle += f" para los IDs: {request.video_ids}"
            raise HTTPException(status_code=404, detail=detalle)

        ids_v = [v.id for v in videos]

        query_global = text("""
            WITH clusters AS (
                SELECT tipo_dano, confianza,
                       ST_ClusterDBSCAN(geom, 0.00005, 1)
                       OVER(PARTITION BY tipo_dano) as cluster_id
                FROM deteccion WHERE video_id IN :ids
            )
            SELECT MAX(confianza) as conf_max
            FROM clusters
            GROUP BY tipo_dano, cluster_id
        """)

        baches_agrupados = db.execute(query_global, {"ids": tuple(ids_v)}).fetchall()

        cantidad_baches = len(baches_agrupados)
        confianza_promedio = (
            sum(r.conf_max for r in baches_agrupados) / cantidad_baches
            if cantidad_baches > 0
            else 0
        )

        es_global = len(request.video_ids) == 0
        contexto_scope = (
            "global de todo el municipio"
            if es_global
            else f"de los videos con IDs: {ids_v}"
        )

        prompt = f"""
        Sos un inspector vial experto del municipio de Moreno, Provincia de Buenos Aires.
        Tu tarea es redactar un informe ejecutivo formal y técnico sobre el estado de la infraestructura vial.

        REGLA ESTRICTA: Actuá 100% como un humano técnico. NO menciones que sos una Inteligencia Artificial, no hables de algoritmos, modelos, ni de cómo se procesaron los datos. Enfocate exclusivamente en el asfalto y las calles.

        Datos oficiales de la inspección {contexto_scope}:
        - Tramos o recorridos analizados: {len(videos)}
        - Cantidad de daños o baches confirmados: {cantidad_baches}
        - Nivel de certeza de la inspección: {confianza_promedio:.0%}

        El informe debe tener exactamente 3 párrafos:
        1. Resumen ejecutivo de la inspección (mencionando los tramos y la certeza general).
        2. Análisis técnico del estado vial y nivel de deterioro basado en los daños encontrados.
        3. Recomendación de mantenimiento, bacheo o acción prioritaria para la municipalidad.

        Sé conciso, profesional y directo."""

        logger.info(
            f"Pidiendo reporte a Ollama para {len(videos)} videos ({contexto_scope})..."
        )

        response = httpx.post(
            f"{settings.OLLAMA_URL}/api/generate",
            json={"model": "llama3.2:3b", "prompt": prompt, "stream": False},
            timeout=120.0,
        )
        response.raise_for_status()
        contenido_reporte = response.json().get("response")

        nuevo_reporte = models.Reporte(contenido=contenido_reporte)
        db.add(nuevo_reporte)
        db.flush()

        for v in videos:
            relacion = models.ReporteVideo(video_id=v.id, reporte_id=nuevo_reporte.id)
            db.add(relacion)

        db.commit()

        return {
            "mensaje": "Reporte generado y vinculado correctamente.",
            "reporte_id": nuevo_reporte.id,
            "videos_incluidos": ids_v,
            "contenido": contenido_reporte,
        }

    except Exception:
        db.rollback()
        logger.error("Error generando reporte")
        raise HTTPException(
            status_code=500, detail="Error interno al generar el reporte"
        )


@router.get("/api/v1/reporte/{video_id}", tags=["Inteligencia Artificial"])
def obtener_reporte(video_id: int, db: Session = Depends(get_db)):
    """
    Busca el reporte más reciente asociado a un video específico.
    Si se pide el ID 0,
    se busca el último reporte que NO esté asociado a un solo video (o el más global).
    """
    if video_id == 0:
        reporte = (
            db.query(models.Reporte)
            .order_by(models.Reporte.fecha_generacion.desc())
            .first()
        )
    else:
        reporte = (
            db.query(models.Reporte)
            .join(models.ReporteVideo)
            .filter(models.ReporteVideo.video_id == video_id)
            .order_by(models.Reporte.fecha_generacion.desc())
            .first()
        )

    if not reporte:
        raise HTTPException(
            status_code=404,
            detail=f"No se encontró ningún reporte para el video ID {video_id}.",
        )

    return {
        "reporte_id": reporte.id,
        "contenido": reporte.contenido,
        "fecha": reporte.fecha_generacion,
    }
