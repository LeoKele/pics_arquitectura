# PICS - Arquitectura Backend (Sistema de Detección Vial)

Este repositorio contiene la arquitectura backend en contenedores para el Proyecto Integrador de Ciencias de Datos (PICS). El sistema se encarga de recibir videos de recorridos viales, encolar el procesamiento y gestionar las detecciones de daños en el asfalto (baches, piel de cocodrilo, calles de tierra) utilizando una arquitectura orientada a microservicios.

## Arquitectura del Sistema

El proyecto utiliza Docker Compose para orquestar los siguientes servicios:
- **API (FastAPI)**: Expone los endpoints RESTful para la carga de datos y consulta de resultados.
- **Worker (Python)**: Proceso en segundo plano que consume tareas de la cola y simula la inferencia del modelo YOLO.
- **Base de Datos (PostgreSQL + PostGIS)**: Almacena el estado de los videos y las coordenadas geográficas de las detecciones.
- **Cola de Mensajes (Redis)**: Gestiona la cola de tareas asíncronas entre la API y el Worker.
- **Almacenamiento de Objetos (MinIO)**: Guarda los archivos crudos (`.mp4` y `.json` de metadata).

## Cómo levantar el entorno 

Para ejecutar este proyecto en una carpeta limpia, asegúrate de tener instalado [Docker](https://www.docker.com/) y `docker-compose`.

1. **Configurar variables de entorno:**
   Copia el archivo de ejemplo para crear tu propio .env local.
   ```bash
   cp .env.example .env

2. **Levantar los contenedores:**
   Ejecuta el siguiente comando para construir las imágenes y levantar toda la infraestructura:
   ```bash
   docker-compose up --build -d
