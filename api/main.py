import logging
import time

import models
from database import engine
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from routers import deteccion, reporte, sistema, video

# Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
)
logger = logging.getLogger("api")

for intento in range(10):
    try:
        models.Base.metadata.create_all(bind=engine)
        logger.info("Tablas creadas/verificadas correctamente.")
        break
    except Exception as e:
        logger.warning(f"BD no lista, reintentando en 3s... ({intento+1}/10): {e}")
        time.sleep(3)
else:
    logger.error("No se pudo conectar a la BD después de 10 intentos.")
    raise SystemExit(1)

app = FastAPI(title="Mapeo Vial Moreno", version="1.1.4")

app.include_router(sistema.router)
app.include_router(video.router)
app.include_router(deteccion.router)
app.include_router(reporte.router)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
