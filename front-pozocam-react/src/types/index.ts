// src/types/index.ts

/**
 * Representa cada cuadro de telemetría (GPS) que capturamos en segundo plano.
 * Este contrato de datos se corresponde exactamente con el esquema de Pydantic del backend.
 */
export interface TelemetryFrame {
  timestamp: string;      // ISO Date String
  elapsed_ms: number;     // Milisegundos transcurridos desde el inicio de la grabación
  lat: number | null;     // Latitud GPS
  lng: number | null;     // Longitud GPS
  acc: number | null;     // Precisión (Accuracy) en metros
  spd: number | null;     // Velocidad (Speed) en m/s
}

/**
 * Estructura de la sesión completa que se guarda de forma local.
 */
export interface RecordingSession {
  sessionId: string;      // Identificador único (timestamp formateado)
  userAgent: string;      // Dispositivo/Navegador que originó la sesión
  totalPoints: number;    // Cantidad de puntos GPS recolectados
  data: TelemetryFrame[]; // Historial completo de coordenadas
}

/**
 * Configuraciones del usuario que guardaremos en LocalStorage.
 */
export interface AppSettings {
  deviceId: string | null;     // ID de la cámara seleccionada
  resolution: string;         // '1920x1080', '1280x720', '1080x1080' o 'full'
  bitrate: number;            // Bitrate de video en bps (ej: 7500000)
  apiUrl: string;             // URL de la API del servidor (FastAPI)
}

/**
 * Representa los estados de la interfaz de subida (Upload Modal).
 * Usado para renderizar condicionalmente los iconos (Spinner, Check, X, etc.)
 */
export type UploadStepStatus = 'idle' | 'run' | 'ok' | 'err' | 'waiting';

export interface UploadProgressState {
  percentage: number;
  statusText: string;
  stepInit: UploadStepStatus;
  stepGps: UploadStepStatus;
  stepVideo: UploadStepStatus;
  stepFinalize: UploadStepStatus;
}
