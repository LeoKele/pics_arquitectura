// src/hooks/useCamera.ts
import { useState, useEffect, useCallback, useRef } from 'react';

export function useCamera() {
  const [stream, setStream] = useState<MediaStream | null>(null);
  const [devices, setDevices] = useState<MediaDeviceInfo[]>([]);
  const [activeResolution, setActiveResolution] = useState<string>('—');
  const [error, setError] = useState<string | null>(null);

  const streamRef = useRef<MediaStream | null>(null);

  // Detener la cámara actual de forma limpia
  const stopCamera = useCallback(() => {
    if (streamRef.current) {
      streamRef.current.getTracks().forEach((track) => track.stop());
      setStream(null);
      streamRef.current = null;
      setActiveResolution('—');
    }
  }, []);

  // Enlistar cámaras disponibles en el dispositivo
  const refreshDevices = useCallback(async () => {
    try {
      const allDevices = await navigator.mediaDevices.enumerateDevices();
      const videoDevices = allDevices.filter((d) => d.kind === 'videoinput');
      setDevices(videoDevices);
      return videoDevices;
    } catch (e) {
      console.error("Error al listar cámaras:", e);
      setError("Error al listar cámaras");
      return [];
    }
  }, []);

  // Inicializar la cámara con resolución y dispositivo seleccionados
  const initCamera = useCallback(async (deviceId: string | null, resolution: string) => {
    stopCamera();

    let constraints: any = {
      audio: false,
      video: {
        deviceId: deviceId ? { exact: deviceId } : undefined,
        facingMode: deviceId ? undefined : { ideal: 'environment' }
      }
    };

    if (resolution === 'full') {
      constraints.video.width = { ideal: 4096 };
      constraints.video.height = { ideal: 2160 };
    } else {
      const parts = resolution.split('x').map(Number);
      if (parts.length === 2 && !isNaN(parts[0]) && !isNaN(parts[1])) {
        constraints.video.width = { exact: parts[0] };
        constraints.video.height = { exact: parts[1] };
      }
    }

    try {
      let activeStream: MediaStream;
      try {
        activeStream = await navigator.mediaDevices.getUserMedia(constraints);
      } catch (err) {
        console.warn("Fallo en constraints exactos, intentando fallback...", err);
        // Fallback flexible sin exact
        if (constraints.video.width) {
          const wIdeal = constraints.video.width.exact;
          const hIdeal = constraints.video.height?.exact;
          delete constraints.video.width.exact;
          if (constraints.video.height) delete constraints.video.height.exact;
          constraints.video.width.ideal = wIdeal;
          if (hIdeal) constraints.video.height.ideal = hIdeal;
        }
        activeStream = await navigator.mediaDevices.getUserMedia(constraints);
      }

      const videoTrack = activeStream.getVideoTracks()[0];
      const settings = videoTrack.getSettings();

      setStream(activeStream);
      streamRef.current = activeStream;
      setActiveResolution(`${settings.width}x${settings.height}`);
      setError(null);

      // Volvemos a listar cámaras para obtener las etiquetas (labels) si antes no las teníamos
      await refreshDevices();
    } catch (e: any) {
      console.error("Error inicializando cámara:", e);
      setError("Error cámara: " + e.message);
    }
  }, [stopCamera, refreshDevices]);

  // Listar cámaras al montar el componente
  useEffect(() => {
    refreshDevices();
    return () => {
      stopCamera();
    };
  }, [refreshDevices, stopCamera]);

  return {
    stream,
    devices,
    activeResolution,
    cameraError: error,
    initCamera,
    stopCamera,
    refreshDevices
  };
}
