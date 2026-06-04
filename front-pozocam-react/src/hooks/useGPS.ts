// src/hooks/useGPS.ts
import { useState, useEffect, useCallback, useRef } from 'react';
import { TelemetryFrame } from '@/types';

export function useGPS() {
  const [gps, setGps] = useState<{
    lat: number;
    lng: number;
    accuracy: number;
    speed: number | null;
  } | null>(null);

  const [gpsError, setGpsError] = useState<string | null>(null);
  const [telemetryData, setTelemetryData] = useState<TelemetryFrame[]>([]);

  const watchIdRef = useRef<number | null>(null);

  // Guardamos en una referencia los datos actuales para poder capturarlos
  // en el intervalo sin forzar re-creaciones de funciones
  const gpsRef = useRef(gps);
  gpsRef.current = gps;

  // Inicializa el GPS
  const startGPS = useCallback(() => {
    if (!navigator.geolocation) {
      setGpsError("GPS no soportado en este navegador");
      return;
    }

    if (watchIdRef.current !== null) return; // Ya está corriendo

    watchIdRef.current = navigator.geolocation.watchPosition(
      (pos) => {
        const coords = {
          lat: pos.coords.latitude,
          lng: pos.coords.longitude,
          accuracy: pos.coords.accuracy,
          speed: pos.coords.speed,
        };
        setGps(coords);
        setGpsError(null);
      },
      (err) => {
        let msg = "Error GPS";
        if (err.code === 1) {
          msg = "Permiso GPS denegado";
        } else if (err.code === 2) {
          msg = "GPS no disponible";
        } else if (err.code === 3) {
          msg = "Timeout GPS";
        }
        console.warn(`[GPS Warning] Código: ${err.code} - ${err.message}`);
        setGpsError(msg);
        setGps(null);
      },
      { enableHighAccuracy: true, maximumAge: 1000, timeout: 5000 }
    );
  }, []);

  // Detiene el tracker de GPS
  const stopGPS = useCallback(() => {
    if (watchIdRef.current !== null) {
      navigator.geolocation.clearWatch(watchIdRef.current);
      watchIdRef.current = null;
    }
  }, []);

  // Captura un frame de telemetría y lo añade al historial
  const captureTelemetry = useCallback((startTime: number) => {
    const now = Date.now();
    const g = gpsRef.current;

    const newFrame: TelemetryFrame = {
      timestamp: new Date(now).toISOString(),
      elapsed_ms: now - startTime,
      lat: g ? g.lat : null,
      lng: g ? g.lng : null,
      acc: g ? g.accuracy : null,
      spd: g ? g.speed : null,
    };

    setTelemetryData((prev) => [...prev, newFrame]);
  }, []);

  const resetTelemetry = useCallback(() => {
    setTelemetryData([]);
  }, []);

  // Limpia el GPS cuando el componente se destruye
  useEffect(() => {
    return () => {
      if (watchIdRef.current !== null) {
        navigator.geolocation.clearWatch(watchIdRef.current);
      }
    };
  }, []);

  // Estado del GPS: OK si tiene precisión menor a 20 metros
  const isGpsOk = gps ? gps.accuracy < 20 : false;
  const gpsText = gpsError
    ? "Error GPS"
    : gps
    ? isGpsOk
      ? "GPS OK"
      : "GPS BAJO"
    : "Buscando...";

  return {
    gps,
    gpsText,
    isGpsOk,
    gpsError,
    telemetryData,
    startGPS,
    stopGPS,
    captureTelemetry,
    resetTelemetry,
  };
}
