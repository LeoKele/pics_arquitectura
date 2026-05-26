# PICS - Arquitectura Backend (Sistema de Detección Vial)

Este repositorio contiene la arquitectura backend en contenedores para el Proyecto Integrador de Ciencias de Datos (PICS). El sistema se encarga de recibir videos de recorridos viales, encolar el procesamiento y gestionar las detecciones de daños en el asfalto (baches, piel de cocodrilo, calles de tierra) utilizando una arquitectura orientada a microservicios.

## Arquitectura del Sistema

El proyecto utiliza Docker Compose para orquestar los siguientes servicios:

- **API (FastAPI)**: Expone los endpoints RESTful para la carga de datos y consulta de resultados.
- **Worker Preprocesamiento (Python)**: Extrae frames de los videos y sincroniza la metadata GPS.
- **Worker Inferencia (Python)**: Consume tareas de la cola y ejecuta el modelo YOLO para detectar daños.
- **Base de Datos (PostgreSQL + PostGIS)**: Almacena el estado de los videos y las coordenadas geográficas de las detecciones.
- **Cola de Mensajes (Redis)**: Gestiona la comunicación asíncrona entre la API y los Workers.
- **Almacenamiento de Objetos (MinIO)**: Guarda archivos crudos (`.mp4`, `.json`) y las capturas de las detecciones.
- **Modelo Ollama**: Ejecuta el modelo de lenguaje "llama3.2:3b" localmente para generar informes ejecutivos.
- **Observabilidad (Loki + Promtail + Grafana)**: Centralización de logs y monitoreo en tiempo real.

## Estructura del Repositorio

El código se organiza de la siguiente manera:

- **api/**: Núcleo de la API FastAPI.
    - `configs/`: Variables de entorno y configuraciones globales.
    - `routers/`: Endpoints divididos por dominio (`video.py`, `deteccion.py`, `reporte.py`, `sistema.py`).
    - `models.py` & `schemas.py`: Definición de tablas de base de datos y validación de datos (Pydantic).
    - `dependencias.py`: Conexiones a servicios externos (Redis, MinIO).
- **worker/**: Lógica de procesamiento en segundo plano.
    - `worker_preprocesamiento.py`: Lógica de extracción de frames y sincronización GPS.
    - `worker.py`: Orquestador de la inferencia con el modelo YOLO.
    - `anonimizador.py`: Módulo que gestiona la difuminación de rostros y patentes.
    - `best.pt`: Pesos del modelo YOLO entrenado para detección de daños.
    - `yolov8s-face-lindevs.pt` y `license-plate-finetune-v1s.pt`: Pesos de los modelos de censura
- **observabilidad/**: Archivos de configuración para el stack de monitoreo (Promtail).
- **docker-compose.yml**: Definición de toda la infraestructura como código.

---

## Cómo levantar el entorno

### 1. Requisitos previos
Asegúrate de tener instalado [Docker](https://www.docker.com/) y `docker-compose`.

### 2. Configurar variables de entorno
Copia el archivo de ejemplo y completa los valores necesarios en tu nuevo `.env`:
```bash
cp .env.example .env
```

### 3. Configurar Pre-Commit (Opcional - Para desarrollo)
Para asegurar la calidad del código, instalá las herramientas de validación:
```bash
pip install pre-commit detect-secrets
detect-secrets scan > .secrets.baseline
pre-commit install
```

### 4. Levantar la infraestructura
Ejecutá el siguiente comando para construir las imágenes y levantar los contenedores:
```bash
docker-compose up --build -d
```

### 5. Descargar el modelo de IA (Ollama)
La primera vez que levantes el proyecto, debés descargar el modelo (aprox. 2GB):
```bash
docker exec -it pics_proyecto-ollama-1 ollama run llama3.2:3b
```
> **Nota**: Si el nombre del contenedor varía, verificalo con `docker ps`.

---

## Ejemplo de uso (Paso a paso)

Para testear el estado actual del sistema y el flujo del modelo, seguí estos pasos:

### 1. Carga de video y metadata
- Entrá a la documentación interactiva: `http://localhost:8000/docs`.
- Buscá el endpoint `POST /api/v1/videos`.
- Hacé clic en **"Try it out"**.
- Subí un archivo de video (`.mp4`) y su correspondiente `.json` de metadata (puedes encontrar un ejemplo para descargar [aquí](https://drive.google.com/drive/folders/1t2k5_rADlHczpZWwmvewc2pNdZBFs21v?usp=sharing) ).
- Al ejecutar, recibirás un `video_id`.

### 2. Flujo de Procesamiento
Una vez subido el video, el sistema inicia una cadena de tareas asíncronas:
1. **Preprocesamiento**: El `worker_preprocesamiento.py` extrae los frames del video, sincronizándolos con la metadata GPS. Filtra frames duplicados (si el vehículo está detenido) y los sube temporalmente a un bucket en MinIO.
2. **Inferencia**: Al finalizar, envía una señal al `worker.py`. Este descarga los frames, los procesa con el modelo **YOLO**, inserta las detecciones en la base de datos y guarda las capturas con las *bounding boxes* en el bucket final de `detecciones`.
3. **Limpieza**: Una vez procesado con éxito, el sistema elimina automáticamente el video original, su JSON de metadata y los frames temporales para optimizar el almacenamiento, dejando solo los resultados finales.

### 3. Verificación de resultados
- **MinIO**: Accedé a `http://localhost:9001` (User/Pass en tu `.env`). Verificá el bucket `detecciones` para ver las imágenes procesadas.
- **Base de Datos**: Podés usar DBeaver o pgAdmin en el puerto `5433` para auditar las tablas `video` y `deteccion`.

### 4. Generación de Reporte con IA
- En `http://localhost:8000/docs`, usá el endpoint `POST /api/v1/reporte/generar`.
- Ingresá el `video_id` obtenido.
- **Nota**: El sistema permite ingresar una lista de IDs (`[1, 2, n]`) para generar un informe consolidado de varios recorridos. Si se envía la lista vacía, la IA generará un reporte basado en **todas** las detecciones históricas del sistema.
- Ollama analizará los datos y redactará un informe ejecutivo narrativo.

### 5. Consulta interactiva
- Usá el endpoint `POST /api/v1/video/{video_id}/preguntar` para hacerle preguntas específicas a la IA sobre los daños encontrados en ese recorrido.

---

### Calidad de Código (Pre-Commit)
El proyecto utiliza hooks de pre-commit para mantener un estándar profesional:
- **Black**: Formateo automático de código.
- **isort**: Orden lógico de importaciones.
- **flake8**: Detección de errores de sintaxis y estilo.
- **detect-secrets**: Prevención de subida de credenciales sensibles.

Para correr las validaciones manualmente:
```bash
pre-commit run --all-files
```

### Modelo de IA (Ollama)
El sistema utiliza **llama3.2:3b** ejecutándose localmente. Esto garantiza la privacidad de los datos. El flujo es:
1. La API recopila detecciones de la base de datos.
2. Se envía un prompt estructurado a Ollama.
3. Ollama devuelve un análisis narrativo que se guarda en PostgreSQL.

### Sistema de Observabilidad
- **Promtail**: Recolecta logs de todos los contenedores Docker.
- **Loki**: Indexa y almacena los logs de forma eficiente.
- **Grafana**: Interfaz visual para consultas.
  - **URL**: `http://localhost:3000/`
  - **Consulta de ejemplo**: `{job="docker"} |= "api"` (Muestra logs que contienen la palabra "api").

### Validaciones durante el procesamiento

1. **Rotación Automática:** Corrección dinámica de la orientación del video (de vertical a horizontal) para estandarizar la perspectiva de los *frames* antes de que ingresen al modelo de inferencia.

2. **Memoria Híbrida (Tracking Visual + Espacial):** El sistema fusiona el motor *ByteTrack* de YOLO con validaciones geoespaciales en PostGIS. Esto permite mantener la identidad de un daño continuo (ej. una calle de tierra prolongada) a medida que el vehículo avanza, evitando la fragmentación de registros y la duplicación de datos.

3. **Filtro de Umbral Dinámico:** Previene la generación de múltiples registros para un mismo daño físico cuando se pierde el tracking visual. El algoritmo agrupa las detecciones utilizando umbrales de distancia geoespacial que varían según la dimensión típica de la anomalía (*D40: 3m, D20: 10m, calle_tierra: 30m*).

4. **Lógica del Fotograma Óptimo y Garbage Collection:** Durante el seguimiento continuo de un daño, el sistema compara las detecciones. Si re-detecta un bache, actualiza las coordenadas en la base de datos **solo si** el nuevo fotograma presenta un mayor índice de confianza. Al hacerlo, ejecuta un proceso de limpieza que elimina automáticamente la imagen anterior de MinIO, garantizando que solo se almacene la captura de mayor calidad y optimizando el uso del disco.

5. **Renderizado Aislado:** El sistema sobreescribe la función de dibujo por defecto de la IA. En lugar de renderizar todas las cajas candidatas superpuestas, aísla y dibuja exclusivamente el recuadro (*bounding box*) del daño que superó estrictamente todos los filtros geográficos y de confianza, generando un respaldo visual limpio.

6. **Filtro de Horizonte (ROI):** Delimita el área de interés exclusivamente a la superficie de rodamiento, descartando automáticamente elementos irrelevantes o falsos positivos ubicados en la mitad superior de la imagen (cielo, árboles, cableado).

7. **Anonimización Automática (Rostros y Patentes):** El sistema difumina de forma automática los rostros de peatones y patentes de vehículos en las imágenes finales asociadas a daños viales. Corre de forma secuencial dos modelos YOLO especializados (`yolov8s-face-lindevs.pt` y `license-plate-finetune-v1s.pt`) sobre los frames seleccionados antes de dibujar las anotaciones del bache y subirse a MinIO, asegurando privacidad y cumplimiento de normativas de datos sin ralentizar el pipeline de inferencia principal.
