FROM node:20-alpine AS builder

WORKDIR /app

# Instalar dependencias
COPY package*.json ./
RUN npm ci

# Copiar el resto del código y compilar la aplicación
COPY . .

# Argumento de compilación para definir la API de producción
ARG NEXT_PUBLIC_API_URL
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL

# Argumento de compilación para definir la URL pública de MinIO
ARG NEXT_PUBLIC_MINIO_URL
ENV NEXT_PUBLIC_MINIO_URL=$NEXT_PUBLIC_MINIO_URL

# Argumento de compilación para definir la URL pública de Grafana
ARG NEXT_PUBLIC_GRAFANA_URL
ENV NEXT_PUBLIC_GRAFANA_URL=$NEXT_PUBLIC_GRAFANA_URL

ENV NEXT_TELEMETRY_DISABLED=1

RUN npm run build

# Imagen de producción final
FROM node:20-alpine AS runner

WORKDIR /app

ENV NODE_ENV=production
ENV NEXT_TELEMETRY_DISABLED=1

# Copiar dependencias y artefactos compilados
COPY --from=builder /app/package*.json ./
COPY --from=builder /app/.next ./.next
COPY --from=builder /app/public ./public
COPY --from=builder /app/node_modules ./node_modules

# Exponer el puerto 80 para mantener compatibilidad con Nginx previo
EXPOSE 80

# Iniciar Next.js en el puerto 80
CMD ["npx", "next", "start", "-p", "80"]
