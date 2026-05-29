from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel


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
    bbox: Optional[Dict[str, Any]] = None
    estado_auditoria: str

    class Config:
        from_attributes = True


# Esquemas para Multipart Upload (Direct-to-MinIO)
class UploadIniciarRequest(BaseModel):
    nombre_archivo: str
    nombre_metadata: Optional[str] = None
    gps_metadata: Dict[str, Any]


class UploadIniciarResponse(BaseModel):
    video_id: int
    upload_id: str
    key: str


class UploadFirmaRequest(BaseModel):
    upload_id: str
    key: str
    part_numbers: List[int]


class UploadFirmaResponse(BaseModel):
    urls: Dict[int, str]


class PartETagSchema(BaseModel):
    PartNumber: int
    ETag: str


class UploadFinalizarRequest(BaseModel):
    video_id: int
    upload_id: str
    key: str
    partes: List[PartETagSchema]
