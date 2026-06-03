import asyncio
import json
import logging
import re
import models
from configs.config import settings
from database import get_db
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from openai import AsyncOpenAI
from pydantic import BaseModel
from services.geo_service import obtener_contexto_geografico, obtener_nombre_calle
from sqlalchemy import text
from sqlalchemy.orm import Session

router = APIRouter()
logger = logging.getLogger("api.reporte")

# --- CLIENTE DEL PROFESOR ---
ollama_client = AsyncOpenAI(
    base_url=f"{settings.OLLAMA_URL}/v1", api_key=settings.OLLAMA_TOKEN
)


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
        query_videos = db.query(models.Video).filter(models.Video.estado == "procesado")

        if request.video_ids:
            query_videos = query_videos.filter(models.Video.id.in_(request.video_ids))

        videos = query_videos.all()

        if not videos:
            raise HTTPException(
                status_code=404, detail="No se encontraron videos procesados"
            )

        ids_v = [v.id for v in videos]
        logger.info(f"--- INICIO GENERACIÓN REPORTE (Videos: {ids_v}) ---")

        async def generador_ollama():
            yield " "

            try:
                resumen_recorridos = []
                for v in videos:
                    puntos = db.execute(
                        text("""
                        SELECT ST_Y(geom) as lat, ST_X(geom) as lng
                        FROM deteccion WHERE video_id = :v_id AND estado_auditoria != 'falso_positivo'
                        ORDER BY fecha_deteccion ASC
                    """),
                        {"v_id": v.id},
                    ).fetchall()

                    if puntos:
                        inicio = await obtener_nombre_calle(
                            puntos[0].lat, puntos[0].lng
                        )
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
                        SELECT tipo_dano, confianza, geom,
                               ST_ClusterDBSCAN(geom, 0.00005, 1)
                               OVER(PARTITION BY tipo_dano) as cluster_id
                        FROM deteccion WHERE video_id IN :ids AND estado_auditoria != 'falso_positivo'
                    )
                    SELECT
                        tipo_dano,
                        MAX(confianza) as conf_max,
                        ST_Y(ST_Centroid(ST_Collect(geom))) as lat,
                        ST_X(ST_Centroid(ST_Collect(geom))) as lng
                    FROM clusters
                    GROUP BY tipo_dano, cluster_id
                """)

                baches_agrupados = db.execute(
                    query_global, {"ids": tuple(ids_v)}
                ).fetchall()
                agrupacion_calles = {}

                for b in baches_agrupados:
                    try:
                        # --- EL FRENO MÁGICO PARA QUE OSM NO NOS BLOQUEE ---
                        await asyncio.sleep(1.2)
                        
                        contexto = await asyncio.wait_for(
                            obtener_contexto_geografico(b.lat, b.lng), timeout=10.0
                        )
                    except (asyncio.TimeoutError, Exception) as e:
                        # Ahora si falla, lo vemos en la consola
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
                        agrupacion_calles[calle]["hallazgos"].append(b.tipo_dano)

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
                    # Borra "[Score Prioridad: X.X]"
                    detalle_sin_score = re.sub(r'\[Score Prioridad:.*?\]', '', detalle)
                    # Borra "(Vía desconocida)"
                    detalle_limpio = detalle_sin_score.replace('(Vía desconocida)', '').strip()
                    detalles_limpios.append(detalle_limpio)

                contexto_hallazgos_str = "\n".join(detalles_limpios)

                prompt = f"""
                Sos un inspector vial experto del municipio de Moreno.
                Tu tarea es redactar un informe ejecutivo formal y técnico.

                OBJETIVO: Evaluar críticamente qué calles deben ser intervenidas, justificando cada acción basándote en el impacto social y estratégico (POIs y jerarquía vial).

                REGLAS DE RAZONAMIENTO OBLIGATORIAS:
                1. JUSTIFICACIÓN POR POI: Si recomendás una obra urgente, debés mencionar el Punto de Interés (Escuela, Hospital, Parada) que justifica esa urgencia.
                2. JERARQUÍA VIAL: Las Avenidas y Rutas tienen prioridad natural por volumen de tránsito. Si una calle es residencial pero tiene muchos baches, terminala de priorizar según si conecta con una vía principal.
                3. PAVIMENTACIÓN ESTRATÉGICA: Para las calles de tierra, justificá la obra como una mejora en la conectividad del barrio o acceso a servicios.
                4. ORDEN DE URGENCIA: Los datos provistos ya están ordenados desde lo más urgente a lo menos urgente. Respetá esa prioridad al redactar.

                REGLA DE ORO DE FORMATO:
                - PROHIBIDO decir "X calle tierra". Usá "tramo de calzada natural/tierra".
                - Sé profesional, directo y usá un lenguaje técnico (ej. "nudo vial", "arteria principal", "seguridad vial").

                DATOS DE LA INSPECCIÓN:
                - Cobertura de los recorridos:
                {recorridos_str}

                - Detalle técnico por ubicación (Ordenado por urgencia):
                {contexto_hallazgos_str}

                ESTRUCTURA OBLIGATORIA:
                1. Resumen Ejecutivo (Estado general de la zona recorrida).
                2. Análisis de Prioridades de Reparación (Justificá bacheo/repavimentación usando Avenidas y POIs).
                3. Propuesta de Pavimentación e Impacto Social (Justificá obras en calles de tierra según conectividad).
                4. Conclusión Técnica (Resumen de la urgencia general).

                Empezá directo con el título "INFORME TÉCNICO DE INSPECCIÓN VIAL - MORENO"."""

                texto_completo = ""

                # Streaming con la SDK asíncrona de OpenAI apuntando al Cloudflare Tunnel
                stream = await ollama_client.chat.completions.create(
                    model="llama3.2:3b",
                    messages=[{"role": "user", "content": prompt}],
                    stream=True,
                    temperature=0.1,
                )

                async for chunk in stream:
                    delta = chunk.choices[0].delta.content or ""
                    if delta:
                        texto_completo += delta
                        yield delta

                # GUARDAR EN BD AL FINALIZAR
                if texto_completo.strip():
                    nuevo_reporte = models.Reporte(contenido=texto_completo)
                    db.add(nuevo_reporte)
                    db.flush()
                    for v in videos:
                        relacion = models.ReporteVideo(
                            video_id=v.id, reporte_id=nuevo_reporte.id
                        )
                        db.add(relacion)
                    db.commit()

            except Exception as e:
                logger.error(f"Error en stream: {e}")
                yield f"\n\n[Error interno: {str(e)}]"

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


@router.get("/api/v1/reporte/{video_id}", tags=["Inteligencia Artificial"])
def obtener_reporte(video_id: int, db: Session = Depends(get_db)):
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
        raise HTTPException(status_code=404, detail=f"No se encontró ningún reporte.")
    return {
        "reporte_id": reporte.id,
        "contenido": reporte.contenido,
        "fecha": reporte.fecha_generacion,
    }
