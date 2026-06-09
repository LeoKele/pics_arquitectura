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
### Frontends (Repositorios Externos)

Las interfaces de usuario del sistema se encuentran alojadas en sus propios repositorios para mantener el desacoplamiento:
- **[pics_frontend_dashboard](https://github.com/LeoKele/pics_frontend_dashboard)**: Panel de control interactivo para visualizar el mapa de detecciones, auditar daños, interactuar con el chatbot de reportes y gestionar el sistema.
- **[pics_frontend_pozocam](https://github.com/LeoKele/pics_frontend_pozocam)**: Aplicación web móvil optimizada para smartphones que realiza la captura de video y registra la telemetría GPS en calle de forma offline.

## Estructura del Repositorio

El código se organiza de la siguiente manera:

- **api/**: Núcleo de la API FastAPI.
    - `configs/`: Variables de entorno y configuraciones globales.
    - `routers/`: Endpoints divididos por dominio (`video.py`, `deteccion.py`, `reporte.py`, `sistema.py`).
    - `models.py` & `schemas.py`: Definición de tablas de base de datos y validación de datos (Pydantic).
    - `dependencias.py`: Conexiones a servicios externos (Redis, MinIO).
- **worker/**: Lógica de procesamiento en segundo plano.
    - `preprocesamiento.py`: Lógica de extracción de frames y sincronización GPS.
    - `inferencia.py`: Orquestador de la inferencia con el modelo YOLO.
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

### 4. Levantar la infraestructura (Docker Compose)
Ejecutá el siguiente comando para construir las imágenes y levantar todos los contenedores de forma automatizada:
```bash
docker-compose up --build -d
```
Este comando levantará la base de datos, el almacenamiento MinIO, Redis, la API FastAPI, los workers de preprocesamiento e inferencia, la observabilidad (Loki, Promtail, Grafana) y Ollama.

*   **API (FastAPI)**: Accesible en `http://localhost:8000/docs`.
*   **Grafana**: Accesible en `http://localhost:3000`.
*   **MinIO Console**: Accesible en `http://localhost:9001`.

> **Conexión a la API y Servicios (Local vs Nube):**
> * **Local (Desarrollo/Demo):** No requiere ninguna configuración especial en el backend. Los frontends externos se conectan automáticamente a los servicios locales (API en `http://localhost:8000`, MinIO en `http://localhost:9000` y Grafana en `http://localhost:3000`).
> * **Nube (Nuestro Despliegue de Referencia):** Para nuestro entorno en Google Cloud, las IPs públicas de producción (API: `http://34.63.158.31:8000`, MinIO: `http://35.194.31.183:9000` y Grafana: `http://34.172.225.250:3000`) se inyectan al compilar la imagen del frontend usando los correspondientes argumentos `--build-arg` (esto se gestiona automáticamente por el flujo de CI/CD del repositorio del frontend en cada push a `main`).

### 5. Descargar el modelo de IA (Ollama)
La primera vez que levantes el proyecto, debés descargar el modelo (aprox. 2GB):
```bash
docker exec -it pics_proyecto-ollama-1 ollama run llama3.2:3b
```
> **Nota**: Si el nombre del contenedor varía, verificalo con `docker ps`.

### 6. Levantar los Frontends (Local)
Las aplicaciones cliente (Dashboard e interfaz de captura PozoCam) no forman parte de este repositorio. Para levantarlas localmente para desarrollo, debés clonar sus repositorios externos y seguir sus instrucciones de instalación:

- **[pics_frontend_dashboard](https://github.com/LeoKele/pics_frontend_dashboard)**:
  ```bash
  git clone https://github.com/LeoKele/pics_frontend_dashboard.git
  cd pics_frontend_dashboard
  npm install
  npm run dev
  ```
  Estará disponible en `http://localhost:3000` o en el puerto alternativo indicado.

- **[pics_frontend_pozocam](https://github.com/LeoKele/pics_frontend_pozocam)**:
  ```bash
  git clone https://github.com/LeoKele/pics_frontend_pozocam.git
  cd pics_frontend_pozocam
  npm install
  npm run dev
  ```
  Estará disponible en `http://localhost:3001` (o similar). En la pestaña de configuración de la app móvil, podés configurar la dirección IP de tu API local (por defecto `http://localhost:8000`).

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
1. **Preprocesamiento**: El `preprocesamiento.py` extrae los frames del video, sincronizándolos con la metadata GPS. Filtra frames duplicados (si el vehículo está detenido) y los sube temporalmente a un bucket en MinIO.
2. **Inferencia**: Al finalizar, envía una señal al `inferencia.py`. Este descarga los frames, los procesa con el modelo **YOLO**, inserta las detecciones en la base de datos y guarda las capturas con las *bounding boxes* en el bucket final de `detecciones`.
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

7. **Anonimización Automática (Rostros y Patentes):** El sistema difumina de forma automática los rostros de peatones y patentes de vehículos en las imágenes finales asociadas a daños viales. Corre de forma secuencial dos modelos YOLO especializados ([`yolov8s-face-lindevs.pt`](https://github.com/lindevs/yolov8-face) y [`license-plate-finetune-v1s.pt`](https://github.com/morsetechlab/Yolov11-License-Plate-Detection/tree/main)) sobre los frames seleccionados antes de dibujar las anotaciones del bache y subirse a MinIO, asegurando privacidad y cumplimiento de normativas de datos sin ralentizar el pipeline de inferencia principal.

8. **Human-in-the-Loop (Auditoría de Detecciones):** Flujo de revisión manual que permite auditar las detecciones del sistema. Si una detección es catalogada como falso positivo, esta se descarta automáticamente de los reportes y consultas dinámicas, y la imagen original sin anotaciones se transfiere a un bucket de reentrenamiento (`backgrounds-reentrenamiento`) en MinIO para mejorar la precisión del modelo en futuras iteraciones.

---

## Despliegue en la Nube (Google Cloud Platform - GCP)

> Los comandos y configuraciones de esta sección contienen identificadores de proyecto (`pics-moreno-cloud`), cuentas de servicio (`788873585485-compute@developer.gserviceaccount.com`) y direcciones IP específicas de **nuestro despliegue de referencia**.
> Si deseas desplegar tu propia instancia de la arquitectura, deberás reemplazar estos valores por los correspondientes a tu proyecto y recursos de Google Cloud.

Esta sección detalla los pasos para realizar el despliegue del sistema en **Google Cloud Platform (GCP)** utilizando **Google Kubernetes Engine (GKE)** para la orquestación y **Cloud SQL** para la base de datos PostgreSQL.

### 1. Configuración de la Infraestructura en GCP

#### A. Habilitar APIs requeridas
En la consola de GCP, habilita los siguientes servicios:
- **Compute Engine API**
- **Kubernetes Engine API**
- **Cloud SQL Admin API**

#### B. Base de Datos en Cloud SQL
1. Crea una instancia de base de datos utilizando **PostgreSQL v17**.
2. **Configuración de Hardware**: Para optimizar costos, selecciona la edición **Enterprise** (máquinas más económicas) con **2 vCPUs**, **8 GB de RAM** y **10 GB de almacenamiento**.
3. Asigna un ID de instancia (ej. `pics-db-moreno`), crea un usuario y contraseña.
4. Crea una nueva base de datos dentro de la instancia para la aplicación.
5. **Conexión simplificada (Desarrollo)**: Para evitar configuraciones complejas de red (VPC Peering), puedes habilitar la IP pública de la instancia y agregar una red autorizada `0.0.0.0/0` en la pestaña de conexiones. *Nota: En entornos de producción reales se debe utilizar Cloud SQL Auth Proxy o VPC Peering.*

#### C. Cluster de Kubernetes (GKE)
1. Dirígete a **Kubernetes Engine > Clusters** y crea un cluster de tipo **Standard** para tener control total de los nodos.
2. Configura la ubicación en `us-central1-a` (región recomendada por eficiencia de costos).
3. **Grupo de nodos (Default Pool)**: Configura máquinas de tipo **e2-standard-4** (4 vCPUs, 16 GB de RAM), necesarias para la ejecución eficiente del modelo YOLO y Ollama (Llama 3.2).
4. Define el tamaño inicial en **2 nodos**.

#### D. Repositorio en Artifact Registry
1. Busca **Artifact Registry** en la consola de GCP y crea un nuevo repositorio.
2. Selecciona formato **Docker**.
3. Elige la región `us-central1` (para estar en la misma ubicación del cluster y reducir latencias/costos de transferencia).

---

### 2. Preparación y Subida de Imágenes

#### A. Autenticación Local
Asegúrate de tener instalado el [Google Cloud CLI](https://cloud.google.com/sdk/docs/install). Luego ejecuta:

```bash
# Iniciar sesión en tu cuenta de Google Cloud
gcloud auth login

# Configurar el proyecto de trabajo actual
gcloud config set project pics-moreno-cloud

# Configurar credenciales de Docker para la región us-central1
gcloud auth configure-docker us-central1-docker.pkg.dev
```

#### B. Construcción y Push de Imágenes Docker
Ejecuta los siguientes comandos en la raíz del proyecto para compilar y subir las imágenes a Artifact Registry:

```bash
# 1. API (FastAPI)
docker build -t us-central1-docker.pkg.dev/pics-moreno-cloud/pics-repo/api-fastapi:v1 ./api
docker push us-central1-docker.pkg.dev/pics-moreno-cloud/pics-repo/api-fastapi:v1

# 2. Worker Base (Utilizado tanto para Inferencia como para Preprocesamiento)
docker build -t us-central1-docker.pkg.dev/pics-moreno-cloud/pics-repo/worker-base:v1 -f ./worker/Dockerfile ./worker
docker push us-central1-docker.pkg.dev/pics-moreno-cloud/pics-repo/worker-base:v1
```

---

### 3. Despliegue en Kubernetes (GKE)

#### A. Conectar kubectl al Cluster
Ejecuta el siguiente comando para descargar las credenciales de conexión del cluster de GKE:

```bash
gcloud container clusters get-credentials pics-cluster --zone us-central1-a --project pics-moreno-cloud
```
> Si no tienes la herramienta `kubectl` instalada localmente, puedes agregarla con: `gcloud components install kubectl`.

#### B. Permisos de Descarga de Imágenes (Service Account)
Para que el cluster de GKE pueda descargar las imágenes desde Artifact Registry, debes otorgar el rol de **Lector de Artifact Registry** a la cuenta de servicio por defecto de Compute Engine:
1. Dirígete a **IAM & Admin > IAM**.
2. Busca la cuenta de servicio por defecto (ej. `788873585485-compute@developer.gserviceaccount.com`).
3. Edita sus permisos y agrégale el rol **Lector de Artifact Registry** (Artifact Registry Reader).

#### C. Aplicar Manifiestos de Kubernetes
Aplica los archivos de configuración YAML en el siguiente orden secuencial:

```bash
kubectl apply -f k8s/01-secretos.yaml
kubectl apply -f k8s/02-minio.yaml
kubectl apply -f k8s/03-redis.yaml
kubectl apply -f k8s/04-ollama.yaml
kubectl apply -f k8s/05-api.yaml
kubectl apply -f k8s/06-workers.yaml
kubectl apply -f k8s/07-frontend.yaml   # (Opcional - No requerido si usas Netlify)
```

Puedes verificar que todos los Pods inicien correctamente ejecutando:
```bash
kubectl get pods -w
```

#### D. Inicializar Modelo de Lenguaje en Ollama
Una vez que el pod de Ollama esté en estado `Running`, inicializa el modelo Llama 3.2 ejecutando:

```bash
kubectl exec -it deploy/ollama -- ollama pull llama3.2:3b
```

---

### 4. Operación y Escalado del Cluster

#### Escalado Dinámico de Workers
El diseño desacoplado del sistema permite escalar los workers según la demanda de procesamiento de manera independiente:

```bash
# Escalar los workers de preprocesamiento (extracción de frames)
kubectl scale deploy/worker-preprocesamiento --replicas=3

# Escalar los workers de inferencia (procesamiento YOLO)
kubectl scale deploy/worker-inferencia --replicas=3
```

Para volver a la configuración base de 1 réplica por worker:
```bash
kubectl scale deploy/worker-preprocesamiento --replicas=1
kubectl scale deploy/worker-inferencia --replicas=1
```

#### Pausar Infraestructura (Ahorro de Costos)
Para evitar consumos de créditos cuando el sistema no está en uso:
1. Detén la instancia de **Cloud SQL** desde la consola web.
2. Reduce la cantidad de nodos del cluster de **GKE** a `0` (en la configuración del grupo de nodos en la consola de GCP).
3. Para volver a levantar el sistema, primero escala el grupo de nodos a su tamaño habitual (ej. 2 nodos) y luego inicia la instancia de Cloud SQL.
