# PICS - Arquitectura Backend (Sistema de Detección Vial)

Este repositorio contiene la arquitectura backend en contenedores para el Proyecto Integrador de Ciencias de Datos (PICS). El sistema se encarga de recibir videos de recorridos viales, encolar el procesamiento y gestionar las detecciones de daños en el asfalto (baches, piel de cocodrilo, calles de tierra) utilizando una arquitectura orientada a microservicios.

## Arquitectura del Sistema

El proyecto utiliza Docker Compose para orquestar los siguientes servicios:
- **API (FastAPI)**: Expone los endpoints RESTful para la carga de datos y consulta de resultados.
- **Worker (Python)**: Proceso en segundo plano que consume tareas de la cola y simula la inferencia del modelo YOLO.
- **Base de Datos (PostgreSQL + PostGIS)**: Almacena el estado de los videos y las coordenadas geográficas de las detecciones.
- **Cola de Mensajes (Redis)**: Gestiona la cola de tareas asíncronas entre la API y el Worker.
- **Almacenamiento de Objetos (MinIO)**: Guarda los archivos crudos (`.mp4` y `.json` de metadata).
- **Modelo Ollama**: Ejecuta el modelo de lenguaje "llama3.2:3b" de forma local para analizar las detecciones y redactar informes ejecutivos.
- **Observabilidad (Loki + Promtail + Grafana):** Promtail recolecta los logs estructurados de los containers de Docker, Loki los centraliza y Grafana proporciona dashboards interactivos para monitorear el estado y los errores del sistema.

## Desarrollo y calidad

- **Pre-Commit:** Funciona como un pipeline de validacion automatica antes de cada commit en Git. Utiliza herramientas de formateo (Black), orden de dependencias (Isort), linting (Flake8) y escaneo de credenciales (detect-secrets) para asegurar que el codigo sea seguro, limpio y estandarizado.

## Cómo levantar el entorno

Para ejecutar este proyecto en una carpeta limpia, asegúrate de tener instalado [Docker](https://www.docker.com/) y `docker-compose`.

1. **Configurar variables de entorno:**
   Copia el archivo de ejemplo para crear tu propio .env local.
   ```bash
   cp .env.example .env

2. **Configurar Pre-Commit**
   En caso de no haber ejecutado nunca pre-commit correr en la terminal:

   !Es importante tener la carpeta vinculada a un repositorio de Github!
   "
   pip install pre-commit detect-secrets
   detect-secrets scan > .secrets.baseline
   pre-commit install
   "

3. **Levantar los contenedores:**
   Ejecuta el siguiente comando para construir las imágenes y levantar toda la infraestructura:
   ```bash
   docker-compose up --build -d

4. **Descargar el modelo de IA (Ollama)**

   Para poder generar los reportes correctamente, necesitas descargar el modelo de lenguaje en el contenedor de Ollama (esto se hace solo la primera vez y pesa aprox. 2GB).
   Con los contenedores ya corriendo, ejecuta en tu terminal:


   docker exec -it pics_arquitectura-main-ollama-1 ollama run llama3.2:3b
   (Nota: Si el comando falla porque no encuentra el contenedor, revisa el nombre exacto ejecutando docker ps y buscando el contenedor de Ollama).



## Contexto de analisis

- **Pre-Commit:** Su proposito es evitar que se suba codigo roto, inseguro o desprolijo de formato. Sirve para corregir espacios en blanco, organizar imports, evitar subida de contraseñas por error, entre otras. Este Pre-Commit frena el push antes de que ocurra.

   **Estilo uniforme (Black):** Si se escribe una sola linea larga, Black la formatea automaticamente para que quede prolija y legible

   **Ordena importanciones (isort):** Agrupa los import alfabéticamente y por tipos.

   **Buscar errores (flake8):** Lee el código buscando variables definidas sin usar o lineas muy largas.

   **Errores de seguridad (detect-secrets):** Ayuda a que no se permita hacer un commit de .env el cual contiene las credenciales para la base de datos, minIO y Grafana.

   **Limpieza básica:** Elimina espacios en blanco inncesarios al final de las lineas.


   Cuando se hagamos un commit, se ejecutará automáticamente. Pero hay una forma de correrlo manual si queremos verlo antes de hacer Commit, en la terminal ejecutar: "pre-commit run --all-files"


- **Modelo IA (Ollama):** Esta herramienta permite descargar un modelo de lenguaje (IA) y ejecutarlo directamente sin depender de enviar los datos a traves de internet a los servidores de una empresa como OpenAI.

Todo se procesa de forma local, no salen de la infraestructura. Funciona de manera offline.

Ollama se encuentra aislado en un container en Docker. Adentro posee el modelo "llama3.2:3b" (Version optimizada y liviana de Meta AI). Cuando se pide generar un reporte hace lo siguiente:
   1. FastAPI recopila los datos crudos de la bd
   2. FastAPI arma un prompt y se lo envia a Ollama (puerto 11434)
   3. Ollama lee los datos, redacta el parrafo de informe y se lo devuelve a FastAPI
   4. FastAPI guarda ese texto en PostreSQL.



- **Loki + Promtail + Grafana**
"http://localhost:3000/"
**Promtail** Funciona como un recolector que levanta todos los textos y errores de Dcoker. Los etiqueta y los envia

**Loki** Recibe los logs de Promtail y los guarda de forma optimizada. Solo indexa las etiquetas.

**Grafana** Es la interfaz grafica. Se conecta a Loki y te permite ver todos los logs en tiempo real, armar gráficos, filtrar por errores, entre otros.
Ejemplo Grafana para visualizar: '{job="docker"} |= "api" '
Esto mostrara lo logs de la palabra "api", se puede hacer lo mismo con "worker" y demas.
