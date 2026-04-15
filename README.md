# PICS Proyecto

Este proyecto es una API construida con FastAPI para el registro y almacenamiento de videos, utilizando PostgreSQL (PostGIS) para metadatos y MinIO para el almacenamiento de archivos.

## 📋 Requisitos Previos

- [Docker](https://www.docker.com/get-started) instalado.
- [Docker Compose](https://docs.docker.com/compose/install/) instalado.

## ⚙️ Configuración

Antes de iniciar, debes configurar las variables de entorno:

1. Copia el archivo de ejemplo:
   ```bash
   cp .env.example .env
   ```
2. Abre el archivo `.env` y ajusta las credenciales si es necesario (por defecto ya vienen configuradas para desarrollo local).

## 🚀 Puesta en Marcha

Para levantar todos los servicios (Base de Datos, MinIO y API), ejecuta:

```bash
docker-compose up --build
```

Esto iniciará:
- **API FastAPI:** `http://localhost:8000`
- **Panel de MinIO (Consola):** `http://localhost:9001` (User/Password en `.env`)
- **PostgreSQL/PostGIS:** Puerto `5432`

## 🛠️ Cómo Probar la API

Una vez que los contenedores estén corriendo, puedes interactuar con la API directamente desde el navegador:

1. Ve a: **[http://localhost:8000/docs](http://localhost:8000/docs)**
2. Verás la interfaz de Swagger UI.
3. Puedes probar el endpoint `POST /videos/` cargando un archivo de video pequeño para verificar que se guarde en MinIO y se registre en la base de datos.

## 📁 Estructura del Proyecto

- `/api`: Código fuente de la aplicación Python/FastAPI.
- `docker-compose.yml`: Definición de los servicios de infraestructura.
- `.env`: Archivo de credenciales (ignorado por Git).
