from fastapi import FastAPI, Depends, UploadFile, File, HTTPException, status
from sqlalchemy.orm import Session
from geoalchemy2.functions import ST_AsGeoJSON
from minio import Minio
from minio.error import S3Error
import redis
import os
import json
import time

from database import engine, get_db
import models
import schemas

# Crea las tablas si no existen
for intento in range(10):
    try:
        models.Base.metadata.create_all(bind=engine)
        print("✓ Tablas creadas/verificadas correctamente.")
        break
    except Exception as e:
        print(f"⚠ BD no lista, reintentando en 3s... ({intento+1}/10): {e}")
        time.sleep(3)
else:
    print("✗ No se pudo conectar a la BD después de 10 intentos.")
    raise SystemExit(1)

# Configuración de conexiones externas
REDIS_HOST = os.getenv("REDIS_HOST", "redis_queue")
r = redis.Redis(host=REDIS_HOST, port=6379, decode_responses=True)

minio_client = Minio(
    "almacenamiento-objetos:9000",
    access_key=os.getenv("MINIO_ROOT_USER"),
    secret_key=os.getenv("MINIO_ROOT_PASSWORD"),
    secure=False 
)
BUCKET_NAME = "videos-crudos"

# ===============================================================================================
# ===============================================================================================
# ===============================================================================================

app = FastAPI(title="PICS API", version="1.0.0")

# ===============================================================================================

@app.get("/")
def raiz():
    return {"mensaje": "API PICS v1 funcionando correctamente"}

# ===============================================================================================

@app.post("/api/v1/videos", status_code=status.HTTP_202_ACCEPTED, response_model=schemas.VideoResponse)
def subir_video(
    video: UploadFile = File(...), 
    metadata: UploadFile = File(...), 
    db: Session = Depends(get_db)
):
    # Validación básica para que no rompa por subir cualquier archivo
    if not video.filename.endswith(('.mp4', '.webm')):
        raise HTTPException(status_code=422, detail="El archivo de video debe ser .mp4 o .webm")
    if not metadata.filename.endswith('.json'):
        raise HTTPException(status_code=422, detail="El archivo de metadata debe ser .json")

    try:
        if not minio_client.bucket_exists(BUCKET_NAME):
            minio_client.make_bucket(BUCKET_NAME)

        minio_client.put_object(
            BUCKET_NAME, video.filename, video.file, video.size, content_type=video.content_type
        )
        minio_client.put_object(
            BUCKET_NAME, metadata.filename, metadata.file, metadata.size, content_type=metadata.content_type
        )
    except S3Error as e:
        raise HTTPException(status_code=500, detail=f"Error en MinIO: {str(e)}")
    
    # Registro en la base de datos
    nuevo_video = models.Video(
        nombre_archivo=video.filename,
        nombre_metadata=metadata.filename,
        estado="pendiente"
    )
    db.add(nuevo_video)
    db.commit()
    db.refresh(nuevo_video)
    
    # Enviar tarea a Redis
    try:
        r.rpush("tareas_video", nuevo_video.id)
    except Exception as e:
        # Registramos el error de Redis pero no fallamos la request
        print(f"Error al enviar a Redis: {e}")
    
    return {
        "mensaje": "Video y metadata recibidos correctamente", 
        "video_id": nuevo_video.id,
        "estado": nuevo_video.estado
    }

# ===============================================================================================

@app.get("/api/v1/detecciones", response_model=list[schemas.DeteccionResponse])
def obtener_detecciones(db: Session = Depends(get_db)):
    detecciones = db.query(
        models.Deteccion.id,
        models.Deteccion.video_id,
        models.Deteccion.tipo_dano,
        models.Deteccion.confianza,
        ST_AsGeoJSON(models.Deteccion.geom).label("geometria"),
        models.Deteccion.fecha_deteccion,
        models.Deteccion.frame_minio_path,
        models.Deteccion.estado_auditoria
    ).all()
    
    resultado = []
    for d in detecciones:
        resultado.append({
            "id": d.id,
            "video_id": d.video_id,
            "tipo_dano": d.tipo_dano,
            "confianza": d.confianza,
            "geometria": json.loads(d.geometria),
            "fecha": d.fecha_deteccion,
            "frame_minio_path": d.frame_minio_path,
            "estado_auditoria": d.estado_auditoria
        })
        
    return resultado


# ===============================================================================================
@app.get("/api/v1/videos/{video_id}", response_model=schemas.VideoStatusResponse)
def obtener_estado_video(video_id: int, db: Session = Depends(get_db)):
    # Buscamos el video en la base de datos por su ID
    video = db.query(models.Video).filter(models.Video.id == video_id).first()
    
    # Si alguien pide un ID que no existe (ej. video 999), devolvemos error 404
    if not video:
        raise HTTPException(status_code=404, detail="Video no encontrado")
        
    # Si existe, devolvemos su estado actual
    return {"id": video.id, "estado": video.estado}