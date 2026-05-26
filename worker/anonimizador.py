import logging

import cv2
from ultralytics import YOLO

logger = logging.getLogger("worker-inferencia.anonimizador")

logger.info("Cargando modelos de anonimización...")

try:
    # Modelo para caras
    model_face = YOLO("yolov8s-face-lindevs.pt")
    # Modelo para patentes
    model_plate = YOLO("license-plate-finetune-v1s.pt")
except Exception as e:
    logger.error(f"No se pudo cargar alguno de los modelos anonimizadores: {e}")
    model_face = None
    model_plate = None


def anonimizar_frame(frame, conf_threshold=0.25):
    """
    Recibe un frame de OpenCV, detecta caras y patentes,
    y retorna una copia con las regiones censuradas.
    """
    if model_face is None and model_plate is None:
        logger.warning(
            "Modelos anonimizadores no cargados. Retornando imagen sin censura."
        )
        return frame.copy()

    frame_censurado = frame.copy()
    h, w, _ = frame_censurado.shape

    # 1. Detectar y censurar caras
    if model_face is not None:
        res_faces = model_face(frame_censurado, conf=conf_threshold, verbose=False)[0]
        for box in res_faces.boxes:
            x1, y1, x2, y2 = map(int, box.xyxy[0])
            x1, y1 = max(0, x1), max(0, y1)
            x2, y2 = min(w, x2), min(h, y2)
            roi = frame_censurado[y1:y2, x1:x2]
            if roi.size > 0:
                frame_censurado[y1:y2, x1:x2] = cv2.GaussianBlur(roi, (51, 51), 0)

    # 2. Detectar y censurar patentes
    if model_plate is not None:
        res_plates = model_plate(frame_censurado, conf=conf_threshold, verbose=False)[0]
        for box in res_plates.boxes:
            x1, y1, x2, y2 = map(int, box.xyxy[0])
            x1, y1 = max(0, x1), max(0, y1)
            x2, y2 = min(w, x2), min(h, y2)
            roi = frame_censurado[y1:y2, x1:x2]
            if roi.size > 0:
                frame_censurado[y1:y2, x1:x2] = cv2.GaussianBlur(roi, (51, 51), 0)

    return frame_censurado
