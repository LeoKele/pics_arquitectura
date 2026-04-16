from pydantic import BaseModel
from datetime import datetime
from typing import Any, Dict

# Lo que devolvemos al subir un video
class VideoResponse(BaseModel):
    mensaje: str
    video_id: int
    estado: str

# Lo que devolvemos al pedir las detecciones
class DeteccionResponse(BaseModel):
    id: int
    tipo: str
    geometria: Dict[str, Any]
    fecha: datetime