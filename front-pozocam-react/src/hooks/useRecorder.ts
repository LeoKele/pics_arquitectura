// src/hooks/useRecorder.ts
import { useState, useEffect, useCallback, useRef } from 'react';
import localforage from 'localforage';
import { TelemetryFrame } from '@/types';

// Configurar localforage
localforage.config({
  name: 'PozoCamReact',
  storeName: 'pending_uploads',
});

interface UseRecorderProps {
  stream: MediaStream | null;
  bitrate: number;
  onCaptureTelemetry: (startTime: number) => void;
  resetTelemetry: () => void;
}

export function useRecorder({
  stream,
  bitrate,
  onCaptureTelemetry,
  resetTelemetry,
}: UseRecorderProps) {
  const [recording, setRecording] = useState(false);
  const [timerText, setTimerText] = useState('00:00:00');
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [videoBlob, setVideoBlob] = useState<Blob | null>(null);
  const [hasPending, setHasPending] = useState(false);

  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const recordedChunksRef = useRef<Blob[]>([]);
  const startTimeRef = useRef<number | null>(null);
  const timerRafRef = useRef<number | null>(null);
  const gpsIntervalIdRef = useRef<NodeJS.Timeout | null>(null);

  // Formatea los segundos transcurridos a formato HH:MM:SS
  const formatTime = (elapsedSeconds: number) => {
    const h = String(Math.floor(elapsedSeconds / 3600)).padStart(2, '0');
    const m = String(Math.floor((elapsedSeconds % 3600) / 60)).padStart(2, '0');
    const s = String(elapsedSeconds % 60).padStart(2, '0');
    return `${h}:${m}:${s}`;
  };

  // Bucle de animación para actualizar el timer de forma fluida
  const tick = useCallback(() => {
    if (!startTimeRef.current) return;
    const elapsed = Math.floor((Date.now() - startTimeRef.current) / 1000);
    setTimerText(formatTime(elapsed));
    timerRafRef.current = requestAnimationFrame(tick);
  }, []);

  // Limpiar timers activos
  const clearTimers = useCallback(() => {
    if (gpsIntervalIdRef.current) {
      clearInterval(gpsIntervalIdRef.current);
      gpsIntervalIdRef.current = null;
    }
    if (timerRafRef.current) {
      cancelAnimationFrame(timerRafRef.current);
      timerRafRef.current = null;
    }
  }, []);

  // Iniciar la grabación
  const startRecording = useCallback(() => {
    if (!stream) {
      console.error("No hay stream de cámara disponible para grabar");
      return;
    }

    resetTelemetry();
    recordedChunksRef.current = [];
    setVideoBlob(null);
    const start = Date.now();
    startTimeRef.current = start;

    // Generar sessionId único
    const sessId = new Date().toISOString().replace(/[:.]/g, '-').slice(0, 19);
    setSessionId(sessId);

    let options = {
      mimeType: 'video/webm;codecs=vp8',
      videoBitsPerSecond: bitrate,
    };

    if (!MediaRecorder.isTypeSupported(options.mimeType)) {
      options = { mimeType: 'video/webm', videoBitsPerSecond: bitrate };
    }

    try {
      const recorder = new MediaRecorder(stream, options);

      recorder.ondataavailable = (e) => {
        if (e.data.size > 0) {
          recordedChunksRef.current.push(e.data);
        }
      };

      recorder.onstop = async () => {
        const finalBlob = new Blob(recordedChunksRef.current, { type: 'video/webm' });
        setVideoBlob(finalBlob);

        // Failsafe localforage: Guardamos en IndexedDB
        try {
          await localforage.setItem('pozocam_pending_video', finalBlob);
          await localforage.setItem('pozocam_pending_session_id', sessId);
          setHasPending(true);
        } catch (err) {
          console.error("Error guardando video en localforage:", err);
        }
      };

      mediaRecorderRef.current = recorder;

      // Graba en partes de 5 segundos para seguridad
      recorder.start(5000);
      setRecording(true);

      // Inicia captura de telemetría GPS cada 500ms
      gpsIntervalIdRef.current = setInterval(() => {
        onCaptureTelemetry(start);
      }, 500);

      // Inicia animación del cronómetro
      timerRafRef.current = requestAnimationFrame(tick);
    } catch (e) {
      console.error("Error al iniciar grabadora:", e);
    }
  }, [stream, bitrate, onCaptureTelemetry, resetTelemetry, tick]);

  // Detener la grabación
  const stopRecording = useCallback(async () => {
    setRecording(false);
    clearTimers();

    if (mediaRecorderRef.current && mediaRecorderRef.current.state !== 'inactive') {
      mediaRecorderRef.current.stop();
    }
  }, [clearTimers]);

  // Limpiar estados locales y almacenamiento temporal
  const resetRecording = useCallback(async () => {
    clearTimers();
    setTimerText('00:00:00');
    setSessionId(null);
    setVideoBlob(null);
    recordedChunksRef.current = [];
    startTimeRef.current = null;
    resetTelemetry();

    try {
      await localforage.removeItem('pozocam_pending_video');
      await localforage.removeItem('pozocam_pending_metadata');
      await localforage.removeItem('pozocam_pending_session_id');
      setHasPending(false);
    } catch (err) {
      console.error("Error al limpiar localforage:", err);
    }
  }, [clearTimers, resetTelemetry]);

  // Guardar metadata en localforage cuando se actualiza la telemetría
  const saveTelemetryToStorage = useCallback(async (data: TelemetryFrame[]) => {
    if (recording && sessionId) {
      try {
        await localforage.setItem('pozocam_pending_metadata', JSON.stringify(data));
      } catch (err) {
        console.error("Error guardando telemetría en localforage:", err);
      }
    }
  }, [recording, sessionId]);

  // Descargar el video de forma local
  const downloadVideo = useCallback(() => {
    if (!videoBlob) return;
    const url = URL.createObjectURL(videoBlob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `pozocam_${sessionId}.webm`;
    a.click();
    URL.revokeObjectURL(url);
  }, [videoBlob, sessionId]);

  // Descargar la telemetría en un archivo JSON local
  const downloadJSON = useCallback((telemetryData: TelemetryFrame[]) => {
    if (!sessionId || telemetryData.length === 0) return;
    const data = JSON.stringify({
      session_id: sessionId,
      device: navigator.userAgent,
      total_points: telemetryData.length,
      data: telemetryData
    }, null, 2);
    const blob = new Blob([data], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `pozocam_${sessionId}.json`;
    a.click();
    URL.revokeObjectURL(url);
  }, [sessionId]);

  // Recupera datos pendientes del almacenamiento local
  const checkPendingUpload = useCallback(async () => {
    try {
      const vBlob = await localforage.getItem<Blob>('pozocam_pending_video');
      const metaStr = await localforage.getItem<string>('pozocam_pending_metadata');
      const sessId = await localforage.getItem<string>('pozocam_pending_session_id');

      if (vBlob && sessId) {
        const metadata = metaStr ? JSON.parse(metaStr) : [];
        setHasPending(true);
        return {
          sessionId: sessId,
          videoBlob: vBlob,
          telemetryData: metadata,
        };
      }
    } catch (err) {
      console.error("Error comprobando cargas pendientes:", err);
    }
    setHasPending(false);
    return null;
  }, []);

  const clearPendingUpload = useCallback(async () => {
    try {
      await localforage.removeItem('pozocam_pending_video');
      await localforage.removeItem('pozocam_pending_metadata');
      await localforage.removeItem('pozocam_pending_session_id');
      setHasPending(false);
    } catch (e) {
      console.error(e);
    }
  }, []);

  // Asegura la limpieza en desmontaje
  useEffect(() => {
    return () => {
      clearTimers();
    };
  }, [clearTimers]);

  return {
    recording,
    timerText,
    sessionId,
    videoBlob,
    hasPending,
    startRecording,
    stopRecording,
    resetRecording,
    downloadVideo,
    downloadJSON,
    checkPendingUpload,
    clearPendingUpload,
    saveTelemetryToStorage,
  };
}
