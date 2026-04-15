from fastapi import FastAPI, Depends, UploadFile, File
from sqlalchemy import create_engine, Column, Integer, String, DateTime
from sqlalchemy.orm import declarative_base, sessionmaker, Session
from minio import Minio
from datetime import datetime
import os

# Obtenemos la ruta de conexion desde las variables de entorno
DATABASE_URL = os.getenv("DATABASE_URL")

# Creamos el motor de base de datos que manejara la comunicacion
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base es la clase principal de la que heredaran nuestros modelos
Base = declarative_base()

# Definimos nuestra primera tabla como si fuera un objeto de Python
class Video(Base):
    __tablename__ = "videos_ingresados"

    id = Column(Integer, primary_key=True, index=True)
    nombre_archivo = Column(String, index=True)
    estado = Column(String, default="Pendiente")
    fecha_ingreso = Column(DateTime, default=datetime.utcnow)

# Revisa si las tablas existen y si no, las crea automaticamente
Base.metadata.create_all(bind=engine)

# Configuracion MINIO
minio_client = Minio(
    "almacenamiento-objetos:9000",
    access_key=os.getenv("MINIO_ROOT_USER"),
    secret_key=os.getenv("MINIO_ROOT_PASSWORD"),
    secure=False 
)

# Nombre de la carpeta principal en MinIO
BUCKET_NAME = "videos-crudos"

# Instanciamos nuestra aplicacion web
app = FastAPI()

def obtener_base_datos():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@app.get("/")
def raiz():
    return {"mensaje": "API conectada a PostGIS y MinIO correctamente"}

# Endpoint para recibir archivos fisicos optimizado
@app.post("/videos/")
def subir_video(archivo: UploadFile = File(...), db: Session = Depends(obtener_base_datos)):
    
    # Le decimos a MinIO que si no existe el bucket lo cree
    if not minio_client.bucket_exists(BUCKET_NAME):
        minio_client.make_bucket(BUCKET_NAME)

    # Obtenemos el peso directamente de los metadatos sin cargar el video a la RAM
    longitud = archivo.size 

    # Subimos el archivo fisico a MinIO
    minio_client.put_object(
        bucket_name=BUCKET_NAME,
        object_name=archivo.filename,
        data=archivo.file,
        length=longitud,
        content_type=archivo.content_type
    )
    
    # Si la subida fue exitosa, anotamos el ingreso en PostgreSQL
    nuevo_video = Video(nombre_archivo=archivo.filename)
    db.add(nuevo_video)
    db.commit()
    db.refresh(nuevo_video)
    
    return {
        "mensaje": "Video subido y registrado exitosamente", 
        "video": nuevo_video
    }
    
    
    
# Falta: -Configuracion Redis ; -Endpoints subida(local/red) ; -Containers para cada worker (inferencia,preprocesamiento,reentramiento)
