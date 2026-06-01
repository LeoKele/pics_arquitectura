1. En primer lugar tenemos que tener una cuenta creada en GCP y crear un nuevo proyecto.

2. Luego, dentro del proyecto, debemos habilitar APIs que haran posible el correcto funcionamiento.
    - Compute Engine API
    - Kubernetes Engine API
    - Cloud SQL Admin API

3. Creamos la BD en Cloud SQL
    - Elegi el motor PostreSQL v17 (ya que era la misma q usaba local, Google ofrece hasta la 18.)
    - se crea una instancia
    - Creamos contraseña y usuario
    - Version ENTERPRISE ya que es mas barata que la version PLUS, te da una maquina mas economica
    - Luego a la izq, en la opcion Bases de Datos. Creamos una BD nueva
    - 2CPU, 8gb RAM, 10GB
    - id: pics-db-moreno
    - En usuarios deben existir los usuarios q necesitamos

4. Buscar en la barra KUBERNETES ENGINE
    - Entramos a Clusters
    - Creamos uno y ponemos STANDARD, es para tener un mejor control que en Autopilot.
    - Elegimos un nombre
    - Ubicacion, us-central1-a. Ya q David mencionó que en US es mas barato que el resto.
    - Ir a NODOS (opcion en la izquierda)
    - Grupo de Nodos -> Default-pool -> Nodos
    - Como tenemos Yolo y Llama3.2 me recomienda usar la maquina "e2-standard-4" la cual tiene 4CPUs, 16GbRAM.
    - La cantidad de Nodos es relativa a lo que necesitemos, para empezar con 2 esta ok

5. Crear repositorio en Artifact Registry
    - Buscamos en la barra de busqueda
    - Creamos un repositorio
    - Formato Docker
    - Ubicacion: us-central1, igual que la anterior (se recomienda usar la misma)
    - Crear

6. Conectar PC a Google Cloud
    - Es necesario tener instalado Google Cloud CLI o SDK. gcloud
    - Iniciamos sesion en Google con "gcloud auth login"
    - Luego le decimos en q proyecto laburamos, "gcloud config set project pics-moreno-cloud"
    - Le das permiso a Docker para subir cosas a Google. "gcloud auth configure-docker us-central1-docker.pkg.dev"


7. Construir y levantar las imagenes a Artifact Registry
    - Ahora hay que tirar comandos. Acordate q la region es us-central1 y el repo se llama pics-repo
    - Para FASTAPI
        "docker build -t us-central1-docker.pkg.dev/pics-moreno-cloud/pics-repo/api-fastapi:v1 ./api"
        "docker push us-central1-docker.pkg.dev/pics-moreno-cloud/pics-repo/api-fastapi:v1"

    - Worker
        "docker build -t us-central1-docker.pkg.dev/pics-moreno-cloud/pics-repo/worker-inferencia:v1 -f ./worker/Dockerfile ./worker"
        "docker push us-central1-docker.pkg.dev/pics-moreno-cloud/pics-repo/worker-inferencia:v1"

    - Worker preprocesamiento
        "docker build -t us-central1-docker.pkg.dev/pics-moreno-cloud/pics-repo/worker-base:v1 -f ./worker/Dockerfile ./worker"
        "docker push us-central1-docker.pkg.dev/pics-moreno-cloud/pics-repo/worker-base:v1"

    - Frontend
        "docker build -t us-central1-docker.pkg.dev/pics-moreno-cloud/pics-repo/frontend:v1 -f ./front/Dockerfile.frontend ./front"
        "docker push us-central1-docker.pkg.dev/pics-moreno-cloud/pics-repo/frontend:v1"


8. Conectar PC al Cluster de Kubernetes
    - Para conectarla tenemos q ejecutar el sig comadndo
    "gcloud container clusters get-credentials pics-cluster --zone us-central1-a --project pics-moreno-cloud"

    - Si te tira un warning de kubectl es q no lo tenes instalado
    Usa este comando: "gcloud components install kubectl"


9. IP Base de Datos y abrir el puerto para permitir conexiones mas faciles (esto quizas no esta del todo bien pero Gemini me dijo q lo haga asi para que sea mas facil y no tener que renegar con redes autorizadas y se pueda conectar cualquiera)
    - Anda a Cloud SQL
    - Toca la isntancia pics-db-moreno
    - Hay una opcion que dice "Conectarse a esta instancia" y Copia la IP Publica
    - Ahora se viene el truco de la ip esta rara
    - Anda a Conexiones - Herramientas para redes - Redes Autorizadas
    - Agregar Red, nombre el q quieras y red: "0.0.0.0/0"
    - Esto permite que el cluster de Kubernetes llegue a la base de datos sin configurar una VPC Peering q es una conexion de red privada entre dos nubes privadas. Yo creeria que no nos va a decir nada por esto igual

10. Creamos todos los archivos .yaml
    - 01.secrets.yaml
    - 02.minio.yaml
    - 03.redis.yaml
    - 04.ollama.yaml
    - 05.api.yaml
    - 06.workers.yaml
    - 07.frontend.yaml

11. Subir todos estos yamls a la nube
    - kubectl apply -f k8s/01-secretos.yaml
    - kubectl apply -f k8s/02-minio.yaml
    - kubectl apply -f k8s/03-redis.yaml
    - kubectl apply -f k8s/04-ollama.yaml
    - kubectl apply -f k8s/05-api.yaml
    - kubectl apply -f k8s/06-workers.yaml
    - kubectl apply -f k8s/07-frontend.yaml

12. Para bajar Ollama corre este comando en la terminal
    - "kubectl exec -it ollama-65fcf759f6-6bzjf -- ollama pull llama3.2:3b"

13. Problema Cluster y Artifact Registry pero no se descargan las imagenes
    - Busca en la barra IAM, es el administrador de permisos
    - Busca la parte de Ver por Roles
    - Otorgar Acceso
    - En el panel lateral dice "Principales Nuevos" y ahi tenes que pegar
    - "788873585485-compute@developer.gserviceaccount.com"
    - Abajo donde dice Asignar Roles tenes que buscar el q diga "Lector de Artifact Registry" y ahi lo guardas
    - Si haces un "kubectl get pods -w" en la terminal de Gcloud deberias ver todos en Running si todo esta ok!

14. Link de Frontend
    - "http://34.46.135.173"

15. Detener todo
    - Entrar a Cloud SQL
    - ir a la instancia y arriba dice DETENER
    - Entrar a Kubernetes Engine
    - ir a Clusters
    - Elegi el cluster, luego ir a nodos.
    - En nodos, editar y poner todos los nodos en 0.

    !! Para iniciar despues es al reves. Primero le pones 1,2,3 nodos y despues inicias en Cloud SQL.


Tu MinIO está en http://35.194.31.183:9001

Tu API (FastAPI) está en http://34.63.158.31:8000/docs#/

Tu Dashboard (Frontend) está en http://34.46.135.173/dashboard.html

Tu PozoCam está en https://pozocam-unlu.netlify.app/

LEVANTAR MAS WORKERS:
1. Multiplicar los que cortan el video:
kubectl scale deploy/worker-preprocesamiento --replicas=3

2. Multiplicar los cerebros de Inteligencia Artificial:
kubectl scale deploy/worker-inferencia --replicas=3

3. Inmediatamente después de tirar esos comandos, tirá un:
kubectl get pods

Cloud, los podés volver a bajar a 1 solo obrero tirando
kubectl scale deploy/worker-preprocesamiento --replicas=1
kubectl scale deploy/worker-inferencia --replicas=1
