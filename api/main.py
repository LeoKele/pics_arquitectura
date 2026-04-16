from fastapi import FastAPI, Depends, UploadFile, File, HTTPException, status
from sqlalchemy import create_engine, Column, Integer, String, DateTime, func
from sqlalchemy.orm import declarative_base, sessionmaker, Session
from geoalchemy2 import Geometry
from geoalchemy2.functions import ST_AsGeoJSON
from minio import Minio
import redis
from datetime import datetime
import os
import json

# Obtenemos la ruta de conexion desde las variables de entorno
DATABASE_URL = os.getenv("DATABASE_URL")
REDIS_HOST = os.getenv("REDIS_HOST", "redis_queue")

# Creamos el motor de base de datos
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# Conexion a Redis
r = redis.Redis(host=REDIS_HOST, port=6379, decode_responses=True)

# Modelo para la tabla de videos
class Video(Base):
    __tablename__ = "videos_ingresados"
    id = Column(Integer, primary_key=True, index=True)
    nombre_archivo = Column(String, index=True)
    nombre_metadata = Column(String)
    estado = Column(String, default="pendiente")
    fecha_ingreso = Column(DateTime, default=datetime.utcnow)

# Modelo para la tabla de detecciones (PostGIS)
class Deteccion(Base):
    __tablename__ = "detecciones"
    id = Column(Integer, primary_key=True, index=True)
    tipo = Column(String) # Ejemplo: "bache"
    ubicacion = Column(Geometry(geometry_type='POINT', srid=4326))
    fecha_deteccion = Column(DateTime, default=datetime.utcnow)
    video_id = Column(Integer)

# Crea las tablas si no existen
Base.metadata.create_all(bind=engine)

# Configuracion MINIO
minio_client = Minio(
    "almacenamiento-objetos:9000",
    access_key=os.getenv("MINIO_ROOT_USER"),
    secret_key=os.getenv("MINIO_ROOT_PASSWORD"),
    secure=False 
)
BUCKET_NAME = "videos-crudos"

app = FastAPI(title="PICS API", version="1.0.0")

def obtener_base_datos():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@app.get("/")
def raiz():
    return {"mensaje": "API PICS v1 funcionando correctamente"}

# POST /api/v1/videos
@app.post("/api/v1/videos", status_code=status.HTTP_202_ACCEPTED)
def subir_video(
    video: UploadFile = File(...), 
    metadata: UploadFile = File(...), 
    db: Session = Depends(obtener_base_datos)
):
    if not minio_client.bucket_exists(BUCKET_NAME):
        minio_client.make_bucket(BUCKET_NAME)

    # Subir video .mp4 a MinIO
    minio_client.put_object(
        BUCKET_NAME, video.filename, video.file, video.size, content_type=video.content_type
    )

    # Subir metadata .json a MinIO
    minio_client.put_object(
        BUCKET_NAME, metadata.filename, metadata.file, metadata.size, content_type=metadata.content_type
    )
    
    # Registro en PostgreSQL
    nuevo_video = Video(
        nombre_archivo=video.filename,
        nombre_metadata=metadata.filename,
        estado="pendiente"
    )
    db.add(nuevo_video)
    db.commit()
    db.refresh(nuevo_video)
    
    # Enviar tarea a Redis
    r.rpush("tareas_video", nuevo_video.id)
    
    return {
        "mensaje": "Video y metadata recibidos correctamente", 
        "video_id": nuevo_video.id,
        "estado": nuevo_video.estado
    }

# GET /api/v1/detecciones
@app.get("/api/v1/detecciones")
def obtener_detecciones(db: Session = Depends(obtener_base_datos)):
    # Consultamos las detecciones y convertimos la geometría a GeoJSON usando PostGIS
    detecciones = db.query(
        Deteccion.id,
        Deteccion.tipo,
        ST_AsGeoJSON(Deteccion.ubicacion).label("geometria"),
        Deteccion.fecha_deteccion
    ).all()
    
    resultado = []
    for d in detecciones:
        resultado.append({
            "id": d.id,
            "tipo": d.tipo,
            "geometria": json.loads(d.geometria),
            "fecha": d.fecha_deteccion
        })
        
    return resultado
