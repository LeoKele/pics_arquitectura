import logging
import os
from datetime import datetime
import hashlib
import jwt
from datetime import datetime, timedelta
from pydantic import BaseModel
import httpx
import models
from configs.config import settings
from database import get_db
from dependencias import minio_client, r
from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import text
from sqlalchemy.orm import Session
from db.models import Usuario

router = APIRouter()
logger = logging.getLogger("api.sistema")


@router.get("/")
def raiz():
    return {"mensaje": "API PICS v1 funcionando correctamente"}


@router.get("/api/v1/health", tags=["Monitoreo"])
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

    # 2. Chequeo de Redis
    try:
        if r.ping():
            servicios["redis"] = "OK"
    except Exception as e:
        servicios["redis"] = f"ERROR: {str(e)}"
        estado_general = "ROJO"

    # 3. Chequeo de MinIO
    try:
        minio_client.bucket_exists(settings.BUCKET_NAME)
        servicios["minio"] = "OK"
    except Exception as e:
        servicios["minio"] = f"ERROR: {str(e)}"
        estado_general = "ROJO"

    # 4. Chequeo de Ollama
    try:
        url_limpia = settings.OLLAMA_URL.rstrip("/")
        async with httpx.AsyncClient(timeout=3.0) as client:
            res = await client.get(f"{url_limpia}/")
            if res.status_code in [200, 401, 403, 404]:
                servicios["ollama"] = "OK"
            else:
                servicios["ollama"] = f"ERROR: Status {res.status_code}"
                if estado_general == "VERDE":
                    estado_general = "AMARILLO"
    except Exception as e:
        servicios["ollama"] = "ERROR: Desconectado"
        logger.error(f"Error en health check de Ollama: {str(e)}")
        if estado_general == "VERDE":
            estado_general = "AMARILLO"

    if estado_general == "ROJO":
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    return {
        "estado_general": estado_general,
        "timestamp": datetime.utcnow().isoformat(),
        "servicios": servicios,
    }


@router.get("/api/v1/sistema/inventario", tags=["Monitoreo"])
def obtener_inventario_archivos(db: Session = Depends(get_db)):
    """
    Lista el inventario completo cruzando la Base de Datos con los 3 buckets de MinIO.
    """
    try:
        videos_db = db.query(models.Video).all()
        buckets = ["videos-crudos", "frames-procesados", "detecciones"]
        resumen_minio = {}

        for bucket in buckets:
            if minio_client.bucket_exists(bucket):
                objetos = minio_client.list_objects(bucket, recursive=True)
                lista_archivos = []
                for obj in objetos:
                    lista_archivos.append(
                        {
                            "nombre": obj.object_name,
                            "tamaño_kb": round(obj.size / 1024, 2),
                        }
                    )
                resumen_minio[bucket] = {
                    "cantidad": len(lista_archivos),
                    "archivos": lista_archivos,
                }
            else:
                resumen_minio[bucket] = {"cantidad": 0, "error": "Bucket no creado aún"}

        return {
            "estado_db": {
                "total_videos_registrados": len(videos_db),
                "videos": [{"id": v.id, "nombre": v.nombre_archivo} for v in videos_db],
            },
            "almacenamiento_minio": resumen_minio,
            "total_general_archivos": sum(
                b["cantidad"] for b in resumen_minio.values()
            ),
        }
    except Exception as e:
        logger.error(f"Error en inventario: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# --- CONFIGURACIÓN DE SEGURIDAD ---
SECRET_KEY = os.getenv("JWT_SECRET_KEY")
ALGORITHM = "HS256"

class LoginRequest(BaseModel):
    username: str
    password: str

def hashear_password(password: str):
    return hashlib.sha256(password.encode()).hexdigest()

@router.post("/api/v1/login")
def login(req: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(Usuario).filter(Usuario.username == req.username).first()
    
    if not user or user.password_hash != hashear_password(req.password):
        raise HTTPException(status_code=401, detail="Usuario o contraseña incorrectos")
    
    payload = {
        "sub": user.username,
        "rol": user.rol,
        "exp": datetime.utcnow() + timedelta(hours=12) # El token dura 12 horas
    }
    token = jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)
    
    return {
        "access_token": token, 
        "rol": user.rol
    }