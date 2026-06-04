// src/services/uploader.ts
import { TelemetryFrame } from '@/types';

interface PartETag {
  PartNumber: number;
  ETag: string;
}

/**
 * Motor de subida de video segmentado (S3 Multipart Upload) directo a MinIO/S3
 * con reporte de telemetría GPS integrado en el cierre de subida.
 */
export async function subirVideoMultipart(
  file: Blob,
  fileName: string,
  datosGPS: TelemetryFrame[],
  apiUrl: string,
  onProgress?: (percentage: number) => void
): Promise<any> {
  const CHUNK_SIZE = 5 * 1024 * 1024; // 5MB por fragmento
  const totalChunks = Math.ceil(file.size / CHUNK_SIZE);
  const cleanApiUrl = apiUrl.replace(/\/$/, ''); // Quitar barra final si existe

  try {
    // 1. Inicializar la subida en el servidor FastAPI
    const resInit = await fetch(`${cleanApiUrl}/api/v1/videos/upload/iniciar`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        filename: fileName,
        content_type: file.type || 'video/webm',
      }),
    });

    if (!resInit.ok) {
      throw new Error(`Error al iniciar subida: ${resInit.statusText}`);
    }

    const { upload_id, key } = await resInit.json();

    const parts: PartETag[] = [];

    // 2. Subir cada fragmento de 5MB secuencialmente
    for (let i = 0; i < totalChunks; i++) {
      const partNumber = i + 1;
      const start = i * CHUNK_SIZE;
      const end = Math.min(start + CHUNK_SIZE, file.size);
      const chunk = file.slice(start, end);

      // A. Firmar la parte actual
      const resSign = await fetch(`${cleanApiUrl}/api/v1/videos/upload/firmar-parte`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          filename: key,
          upload_id,
          part_number: partNumber,
        }),
      });

      if (!resSign.ok) {
        throw new Error(`Error al firmar la parte ${partNumber}: ${resSign.statusText}`);
      }

      const { url } = await resSign.json();

      // B. Reemplazar la URL para pasar por el proxy /minio para evitar errores de CORS
      // (si estamos en producción o entorno local con proxy de Next.js)
      let urlSegura = url;
      if (url.includes("35.194.31.183:9000")) {
        urlSegura = url.replace("http://35.194.31.183:9000", "/minio");
      } else if (url.includes("localhost:9000")) {
        urlSegura = url.replace("http://localhost:9000", "/minio");
      }

      // C. Subida binaria del fragmento (PUT)
      const uploadRes = await fetch(urlSegura, {
        method: 'PUT',
        body: chunk,
      });

      if (!uploadRes.ok) {
        throw new Error(`Fallo al subir la parte ${partNumber}`);
      }

      const etag = uploadRes.headers.get("ETag");
      if (!etag) {
        throw new Error(`No se recibió el ETag para la parte ${partNumber}`);
      }

      parts.push({
        PartNumber: partNumber,
        ETag: etag.replace(/"/g, ''), // Limpiar comillas del ETag si vienen
      });

      // D. Reportar progreso de subida
      if (onProgress) {
        const percentage = Math.round(((i + 1) / totalChunks) * 100);
        onProgress(percentage);
      }
    }

    // 3. Finalizar la subida y consolidar con el GPS
    const resFinal = await fetch(`${cleanApiUrl}/api/v1/videos/upload/finalizar`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        filename: key,
        upload_id,
        parts,
        telemetria: datosGPS, // Enviamos el JSON crudo del GPS
      }),
    });

    if (!resFinal.ok) {
      throw new Error(`Error al consolidar la subida en el servidor: ${resFinal.statusText}`);
    }

    return await resFinal.json();
  } catch (error) {
    console.error("Error detallado en subirVideoMultipart:", error);
    throw error;
  }
}
