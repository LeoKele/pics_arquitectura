import asyncio
import logging
import re

import models
from configs.config import settings
from database import SessionLocal, get_db
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from openai import AsyncOpenAI
from pydantic import BaseModel
from services.geo_service import obtener_contexto_geografico, obtener_nombre_calle
from sqlalchemy import text
from sqlalchemy.orm import Session

router = APIRouter()
logger = logging.getLogger("api.reporte")

# Configurar el cliente y modelo de forma dinámica según el proveedor
if settings.LLM_PROVIDER == "gemini":
    llm_client = AsyncOpenAI(
        base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
        api_key=settings.GEMINI_API_KEY or "mock-key-for-init",
    )
    llm_model = settings.GEMINI_MODEL
elif settings.LLM_PROVIDER == "openai":
    llm_client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY or "mock-key-for-init")
    llm_model = settings.OPENAI_MODEL
else:
    llm_client = AsyncOpenAI(
        base_url=f"{settings.OLLAMA_URL}/v1", api_key=settings.OLLAMA_TOKEN or "ollama"
    )
    llm_model = settings.OLLAMA_MODEL


class GenerarReporteRequest(BaseModel):
    video_ids: list[int] = []


@router.post(
    "/api/v1/reportes/generar",
    status_code=status.HTTP_201_CREATED,
    tags=["Inteligencia Artificial"],
)
async def generar_reporte(
    request: GenerarReporteRequest, db: Session = Depends(get_db)
):
    try:
        # 💥 BLINDAJE: Evita que si 'video_ids' viene vacío se procese toda la base de datos por error
        if not request.video_ids:
            raise HTTPException(
                status_code=400,
                detail="Debe especificar al menos un ID de video en la lista 'video_ids'."
            )

        query_videos = db.query(models.Video).filter(models.Video.estado == "procesado")
        query_videos = query_videos.filter(models.Video.id.in_(request.video_ids))
        videos = query_videos.all()

        if not videos:
            raise HTTPException(
                status_code=404, detail="No se encontraron videos procesados para los IDs provistos"
            )

        ids_v = [v.id for v in videos]
        logger.info(f"--- INICIO GENERACIÓN REPORTE (Videos: {ids_v}) ---")

        async def generador_ollama():
            # Latido inicial para Netlify
            yield " "

            db_gen = SessionLocal()
            try:
                resumen_recorridos = []
                for v in videos:
                    puntos = db_gen.execute(
                        text("""
                        SELECT ST_Y(geom) as lat, ST_X(geom) as lng
                        FROM deteccion WHERE video_id = :v_id AND estado_auditoria != 'falso_positivo'
                        ORDER BY fecha_deteccion ASC
                    """),
                        {"v_id": v.id},
                    ).fetchall()

                    if puntos:
                        # 🔄 Latido pre-OSM 1
                        yield " "
                        inicio = await obtener_nombre_calle(
                            puntos[0].lat, puntos[0].lng
                        )
                        # 🔄 Latido pre-OSM 2
                        yield " "
                        fin = await obtener_nombre_calle(puntos[-1].lat, puntos[-1].lng)
                        
                        if inicio == fin:
                            resumen_recorridos.append(
                                f"- Recorrido {v.id}: Principalmente en {inicio}"
                            )
                        else:
                            resumen_recorridos.append(
                                f"- Recorrido {v.id}: Desde {inicio} hasta {fin}"
                            )

                recorridos_str = "\n".join(resumen_recorridos)

                query_global = text("""
                    WITH clusters AS (
                        SELECT tipo_dano, geom,
                               -- Agrupamos baches/grietas cercanos con DBSCAN
                               ST_ClusterDBSCAN(geom, 0.0015, 1)
                               OVER(PARTITION BY tipo_dano) as cluster_id
                        FROM deteccion WHERE video_id IN :ids AND estado_auditoria != 'falso_positivo'
                    )
                    SELECT
                        tipo_dano,
                        COUNT(*) as cantidad_baches,
                        ST_Y(ST_Centroid(ST_Collect(geom))) as lat,
                        ST_X(ST_Centroid(ST_Collect(geom))) as lng
                    FROM clusters
                    GROUP BY tipo_dano, cluster_id
                """)

                baches_agrupados = db_gen.execute(
                    query_global, {"ids": tuple(ids_v)}
                ).fetchall()
                agrupacion_calles = {}

                for b in baches_agrupados:
                    try:
                        # 🔄 El latido más importante: mantiene el proxy de Netlify vivo durante el delay de 1.2s
                        yield " "
                        await asyncio.sleep(1.2)

                        contexto = await asyncio.wait_for(
                            obtener_contexto_geografico(b.lat, b.lng), timeout=30.0
                        )
                    except (asyncio.TimeoutError, Exception) as e:
                        logger.error(f"OSM falló para {b.lat}, {b.lng}. Motivo: {e}")
                        contexto = {
                            "calle": f"Zona GPS {b.lat:.4f}, {b.lng:.4f}",
                            "tipo_calle": "Vía sin mapear",
                            "calles_cruzadas": [],
                            "pois_cercanos": [],
                        }

                    calle = contexto["calle"]
                    if calle not in agrupacion_calles:
                        agrupacion_calles[calle] = {
                            "hallazgos": [],
                            "pois": set(),
                            "tipo": contexto["tipo_calle"],
                            "prioridad_score": 0,
                            "segmentos_tierra": [],
                        }

                    if b.tipo_dano == "CALLE_TIERRA":
                        entrecalles = contexto.get("calles_cruzadas", [])
                        if (
                            entrecalles
                            not in agrupacion_calles[calle]["segmentos_tierra"]
                        ):
                            agrupacion_calles[calle]["segmentos_tierra"].append(
                                entrecalles
                            )
                    else:
                        agrupacion_calles[calle]["hallazgos"].extend(
                            [b.tipo_dano] * b.cantidad_baches
                        )

                    for p in contexto["pois_cercanos"]:
                        agrupacion_calles[calle]["pois"].add(p)

                detalles_contexto_vial = []
                for calle, info in agrupacion_calles.items():
                    score = len(info["hallazgos"]) * 2
                    if info["segmentos_tierra"]:
                        score += 3
                    if any(
                        p in str(info["pois"])
                        for p in ["Escuela", "Hospital", "Centro de Salud"]
                    ):
                        score += 5
                    if "Avenida" in info["tipo"] or "Ruta" in info["tipo"]:
                        score *= 1.5

                    info["prioridad_score"] = score
                    hallazgos_list = []
                    tipos_danos = set(info["hallazgos"])
                    if tipos_danos:
                        danos_str = ", ".join(
                            [f"{info['hallazgos'].count(t)} {t}" for t in tipos_danos]
                        )
                        hallazgos_list.append(f"Daños en asfalto: {danos_str}")

                    for segment in info["segmentos_tierra"]:
                        entre_str = " entre " + " y ".join(segment) if segment else ""
                        hallazgos_list.append(f"Calzada de tierra detectada{entre_str}")

                    conteo_str = " | ".join(hallazgos_list)
                    pois_str = (
                        f" (Proximidad: {', '.join(info['pois'])})"
                        if info["pois"]
                        else ""
                    )
                    detalle_linea = f"- {calle} ({info['tipo']}): {conteo_str}{pois_str}. [Score Prioridad: {score:.1f}]"
                    detalles_contexto_vial.append(detalle_linea)

                detalles_limpios = []
                for detalle in detalles_contexto_vial:
                    detalle_sin_score = re.sub(r"\[Score Prioridad:.*?\]", "", detalle)
                    detalle_limpio = detalle_sin_score.replace(
                        "(Vía desconocida)", ""
                    ).strip()
                    detalles_limpios.append(detalle_limpio)

                contexto_hallazgos_str = "\n".join(detalles_limpios)

                prompt = f"""
                Sos un inspector vial experto del municipio de Moreno.
                Tu tarea es redactar un informe ejecutivo formal y técnico.

                OBJETIVO: Evaluar críticamente qué calles deben ser intervenidas, justificando cada acción basándote en el impacto social y estratégico (POIs y jerarquía vial).

                REGLAS DE RAZONAMIENTO OBLIGATORIAS:
                1. JUSTIFICACIÓN POR POI: Si recomendás una obra urgente, debés mencionar el Punto de Interés (Escuela, Hospital, Parada) que justifica esa urgencia.
                Ejemplo: "Se requiere bacheo urgente en Calle X debido a su proximidad con el Hospital Y".
                2. JERARQUÍA VIAL: Las Avenidas y Rutas tienen prioridad natural por volumen de tránsito. Si una calle es residencial pero tiene muchos baches, terminala de priorizar según si conecta con una vía principal.
                3. PAVIMENTACIÓN ESTRATÉGICA: Para las calles de tierra, justificá la obra como una mejora en la conectividad del barrio o acceso a servicios.
                4. USO DEL SCORE (INTERNO): Usá el score para ordenar las calles de mayor a menor importancia, pero NUNCA escribas el número.

                REGLA DE ORO DE FORMATO:
                - PROHIBIDO mencionar "Score", "Puntaje" o números decimales.
                - PROHIBIDO decir "X calle tierra". Usá "tramo de calzada natural/tierra".
                - Sé profesional, directo y usá un lenguaje técnico (ej. "nudo vial", "arteria principal", "seguridad vial").

                DATOS DE LA INSPECCIÓN:
                - Cobertura de los recorridos:
                {recorridos_str}

                - Detalle técnico por ubicación (Hallazgos, POIs y prioridad interna):
                {contexto_hallazgos_str}

                ESTRUCTURA OBLIGATORIA:
                1. Resumen Ejecutivo (Estado general de la zona recorrida).
                2. Análisis de Prioridades de Reparación (Justificá bacheo/repavimentación usando Avenidas y POIs).
                3. Propuesta de Pavimentación e Impacto Social (Justificá obras en calles de tierra según conectividad).
                4. Conclusión Técnica (Resumen de la urgencia general).

                Empezá directo con el título "INFORME TÉCNICO DE INSPECCIÓN VIAL - MORENO"."""

                texto_completo = ""

                stream = await llm_client.chat.completions.create(
                    model=llm_model,
                    messages=[{"role": "user", "content": prompt}],
                    stream=True,
                    temperature=0.1,
                )

                async for chunk in stream:
                    delta = chunk.choices[0].delta.content or ""
                    if delta:
                        texto_completo += delta
                        yield delta

                if texto_completo.strip():
                    nuevo_reporte = models.Reporte(contenido=texto_completo)
                    db_gen.add(nuevo_reporte)
                    db_gen.flush()
                    for v in videos:
                        relacion = models.ReporteVideo(
                            video_id=v.id, reporte_id=nuevo_reporte.id
                        )
                        db_gen.add(relacion)
                    db_gen.commit()

            except Exception as e:
                logger.error(f"Error en stream: {e}")
                yield f"\n\n[Error interno: {str(e)}]"
            finally:
                db_gen.close()

        headers_stream = {
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        }
        return StreamingResponse(
            generador_ollama(), media_type="text/plain", headers=headers_stream
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error general: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


async def obtener_tramos_para_videos(video_ids: list[int], db: Session) -> str:
    tramos = []
    for vid_id in video_ids:
        puntos = db.execute(
            text("""
            SELECT ST_Y(geom) as lat, ST_X(geom) as lng
            FROM deteccion WHERE video_id = :v_id AND estado_auditoria != 'falso_positivo'
            ORDER BY fecha_deteccion ASC
        """),
            {"v_id": vid_id},
        ).fetchall()

        if puntos:
            inicio = await obtener_nombre_calle(puntos[0].lat, puntos[0].lng)
            fin = await obtener_nombre_calle(puntos[-1].lat, puntos[-1].lng)
            if inicio == "Calle sin identificar" and fin == "Calle sin identificar":
                tramos.append(f"Video #{vid_id}")
            elif inicio == fin:
                tramos.append(f"{inicio}")
            else:
                tramos.append(f"{inicio} hasta {fin}")
        else:
            tramos.append(f"Video #{vid_id}")
    return "; ".join(tramos) if tramos else "Sin recorrido identificado"


@router.get("/api/v1/reporte/{video_id}", tags=["Inteligencia Artificial"])
async def obtener_reporte(video_id: int, db: Session = Depends(get_db)):
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
        raise HTTPException(status_code=404, detail="No se encontró ningún reporte.")

    vids = (
        db.query(models.ReporteVideo.video_id)
        .filter(models.ReporteVideo.reporte_id == reporte.id)
        .all()
    )
    video_ids = [v[0] for v in vids if v[0] is not None]

    tramos = await obtener_tramos_para_videos(video_ids, db)

    return {
        "reporte_id": reporte.id,
        "contenido": reporte.contenido,
        "fecha": reporte.fecha_generacion,
        "video_ids": video_ids,
        "tramos": tramos,
    }


@router.get("/api/v1/reportes/historial", tags=["Inteligencia Artificial"])
async def obtener_historial_reportes(db: Session = Depends(get_db)):
    try:
        reportes = (
            db.query(models.Reporte)
            .order_by(models.Reporte.fecha_generacion.desc())
            .all()
        )
        resultado = []
        for r in reportes:
            vids = (
                db.query(models.ReporteVideo.video_id)
                .filter(models.ReporteVideo.reporte_id == r.id)
                .all()
            )
            video_ids = [v[0] for v in vids if v[0] is not None]

            tramos = await obtener_tramos_para_videos(video_ids, db)

            resultado.append(
                {
                    "id": r.id,
                    "contenido": r.contenido,
                    "fecha_generacion": r.fecha_generacion,
                    "video_ids": video_ids,
                    "tramos": tramos,
                }
            )
        return resultado
    except Exception as e:
        logger.error(f"Error al obtener historial de reportes: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/api/v1/reporte/{reporte_id}", tags=["Inteligencia Artificial"])
def eliminar_reporte(reporte_id: int, db: Session = Depends(get_db)):
    try:
        db.query(models.ReporteVideo).filter(
            models.ReporteVideo.reporte_id == reporte_id
        ).delete()
        reporte = (
            db.query(models.Reporte).filter(models.Reporte.id == reporte_id).first()
        )
        if not reporte:
            raise HTTPException(status_code=404, detail="Reporte no encontrado")
        db.delete(reporte)
        db.commit()
        return {"mensaje": "Reporte eliminado"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error al eliminar reporte: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))