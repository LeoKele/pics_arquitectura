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

        # Sembrar usuarios por defecto si la tabla está vacía
        import hashlib

        from models import Usuario
        from sqlalchemy.orm import Session

        with Session(engine) as session:
            if session.query(Usuario).count() == 0:
                logger.info("Sembrando usuarios por defecto...")
                admin_hash = hashlib.sha256(b"admin").hexdigest()
                op_hash = hashlib.sha256(b"operador").hexdigest()
                session.add_all(
                    [
                        Usuario(
                            username="admin", password_hash=admin_hash, rol="admin"
                        ),
                        Usuario(
                            username="operador", password_hash=op_hash, rol="operador"
                        ),
                    ]
                )
                session.commit()
                logger.info("Sembrador: Usuarios por defecto creados con éxito.")
        break
    except Exception as e:
        logger.warning(f"BD no lista, reintentando en 3s... ({intento+1}/10): {e}")
        time.sleep(3)
else:
    logger.error("No se pudo conectar a la BD después de 10 intentos.")
    raise SystemExit(1)

app = FastAPI(title="Mapeo Vial Moreno", version="1.1.4")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(sistema.router)
app.include_router(video.router)
app.include_router(deteccion.router)
app.include_router(reporte.router)
