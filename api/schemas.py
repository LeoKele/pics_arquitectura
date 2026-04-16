from pydantic import BaseModel
from datetime import datetime
from typing import Any, Dict, Optional

# Esquemas para Videos
class VideoBase(BaseModel):
    nombre_archivo: str
    nombre_metadata: str

class VideoResponse(BaseModel):
    mensaje: str
    video_id: int
    estado: str

    class Config:
        from_attributes = True

class VideoStatusResponse(BaseModel):
    id: int
    estado: str

# Esquemas para Detecciones
class DeteccionResponse(BaseModel):
    id: int
    video_id: int
    tipo_dano: str
    confianza: float
    geometria: Dict[str, Any]
    fecha: datetime
    frame_minio_path: Optional[str] = None
    estado_auditoria: str

    class Config:
        from_attributes = True
