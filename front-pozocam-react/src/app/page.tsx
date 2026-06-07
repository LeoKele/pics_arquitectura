// src/app/page.tsx
'use client';

import React, { useState, useEffect, useRef } from 'react';
import { useCamera } from '@/hooks/useCamera';
import { useGPS } from '@/hooks/useGPS';
import { useRecorder } from '@/hooks/useRecorder';
import { subirVideoMultipart } from '@/services/uploader';
import { AppSettings, UploadProgressState } from '@/types';

// Componentes
import TopBar from '@/components/TopBar';
import HUD from '@/components/HUD';
import RecControls from '@/components/RecControls';
import SettingsModal from '@/components/SettingsModal';
import UploadModal from '@/components/UploadModal';

export default function PozoCam() {
  // ── ESTADOS DE LA INTERFAZ ──
  const [settings, setSettings] = useState<AppSettings>({
    deviceId: null,
    resolution: '1920x1080',
    bitrate: 7500000,
    apiUrl: process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000', // Servidor de desarrollo/producción
  });
  const [mounted, setMounted] = useState(false);
  const [isSettingsOpen, setIsSettingsOpen] = useState(false);
  const [isUploadOpen, setIsUploadOpen] = useState(false);

  // Estado para el modal de subida multipart
  const [uploadProgress, setUploadProgress] = useState<UploadProgressState>({
    percentage: 0,
    statusText: 'Esperando...',
    stepInit: 'waiting',
    stepGps: 'waiting',
    stepVideo: 'waiting',
    stepFinalize: 'waiting',
  });

  // Estado para las alertas flotantes (Toasts)
  const [toast, setToast] = useState<{
    msg: string;
    type: 'info' | 'ok' | 'err';
  } | null>(null);

  const toastTimeoutRef = useRef<NodeJS.Timeout | null>(null);
  const videoRef = useRef<HTMLVideoElement | null>(null);

  // ── HOOKS DE RECURSOS DEL DISPOSITIVO ──
  const {
    stream,
    devices,
    activeResolution,
    cameraError,
    initCamera,
    stopCamera,
  } = useCamera();

  const {
    gps,
    gpsText,
    isGpsOk,
    telemetryData,
    startGPS,
    stopGPS,
    captureTelemetry,
    resetTelemetry,
  } = useGPS();

  const {
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
  } = useRecorder({
    stream,
    bitrate: settings.bitrate,
    onCaptureTelemetry: captureTelemetry,
    resetTelemetry,
  });

  // Utilidad de Toasts
  const showToast = (msg: string, type: 'info' | 'ok' | 'err' = 'info') => {
    if (toastTimeoutRef.current) clearTimeout(toastTimeoutRef.current);
    setToast({ msg, type });
    toastTimeoutRef.current = setTimeout(() => {
      setToast(null);
    }, 3500);
  };

  // 1. CARGA INICIAL (CLIENT-SIDE)
  useEffect(() => {
    setMounted(true);

    // Cargar configuraciones guardadas en localStorage
    const savedDeviceId = localStorage.getItem('pozocam_deviceId');
    const savedRes = localStorage.getItem('pozocam_res') || '1920x1080';
    const savedBitrate = parseInt(localStorage.getItem('pozocam_bitrate') || '7500000');
    const savedApi = localStorage.getItem('pozocam_apiUrl') || process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

    const loadedSettings: AppSettings = {
      deviceId: savedDeviceId,
      resolution: savedRes,
      bitrate: savedBitrate,
      apiUrl: savedApi,
    };

    setSettings(loadedSettings);

    // Iniciar GPS en segundo plano
    startGPS();

    // Comprobar si hay alguna carga local pendiente
    checkPendingUpload().then((pending) => {
      if (pending) {
        showToast("Tenés un recorrido grabado pendiente de subir localmente", "info");
      }
    });

    return () => {
      stopGPS();
      stopCamera();
    };
  }, [startGPS, stopGPS, stopCamera, checkPendingUpload]);

  // 2. INICIALIZAR CÁMARA CUANDO LOS COMPONENTES ESTÁN LISTOS
  useEffect(() => {
    if (mounted) {
      initCamera(settings.deviceId, settings.resolution);
    }
  }, [mounted, settings.deviceId, settings.resolution, initCamera]);

  // Sincronizar el stream con la etiqueta de video HTML
  useEffect(() => {
    if (videoRef.current && stream) {
      videoRef.current.srcObject = stream;
    }
  }, [stream]);

  // Sincronizar telemetría capturada con localforage para respaldo
  useEffect(() => {
    saveTelemetryToStorage(telemetryData);
  }, [telemetryData, saveTelemetryToStorage]);

  // Manejar errores de cámara
  useEffect(() => {
    if (cameraError) {
      showToast(cameraError, 'err');
    }
  }, [cameraError]);

  // ── MANEJADORES DE EVENTOS ──

  // Guardar configuración
  const handleSaveSettings = (newSettings: AppSettings) => {
    setSettings(newSettings);
    localStorage.setItem('pozocam_deviceId', newSettings.deviceId || '');
    localStorage.setItem('pozocam_res', newSettings.resolution);
    localStorage.setItem('pozocam_bitrate', String(newSettings.bitrate));
    localStorage.setItem('pozocam_apiUrl', newSettings.apiUrl);

    showToast("Configuraciones aplicadas", "ok");
  };

  // Subir video y telemetría a través del servicio multipart
  const handleUpload = async () => {
    // Intentar recuperar los datos activos o los datos guardados en IndexedDB
    let currentBlob = videoBlob;
    let currentGPS = telemetryData;
    let currentSession = sessionId;

    if (!currentBlob || !currentSession) {
      // Intentamos recuperar del localforage (respaldo)
      const pending = await checkPendingUpload();
      if (pending) {
        currentBlob = pending.videoBlob;
        currentGPS = pending.telemetryData;
        currentSession = pending.sessionId;
      }
    }

    if (!currentBlob || !currentSession) {
      showToast("No hay datos de video para subir", "err");
      return;
    }

    // Preparar UI del modal de subida
    setIsUploadOpen(true);
    setUploadProgress({
      percentage: 0,
      statusText: 'Iniciando conexión con el servidor...',
      stepInit: 'run',
      stepGps: 'waiting',
      stepVideo: 'waiting',
      stepFinalize: 'waiting',
    });

    try {
      const fileName = `pozocam_${currentSession}.webm`;

      // Ejecutar la subida Multipart
      await subirVideoMultipart(
        currentBlob,
        fileName,
        currentGPS,
        settings.apiUrl,
        (percentage) => {
          // El paso inicial y de GPS se asumen listos rápido en multipart
          setUploadProgress((prev) => ({
            ...prev,
            percentage,
            statusText: `Subiendo video: ${percentage}%`,
            stepInit: 'ok',
            stepGps: 'ok',
            stepVideo: percentage === 100 ? 'ok' : 'run',
            stepFinalize: percentage === 100 ? 'run' : 'waiting',
          }));
        }
      );

      // Éxito absoluto
      setUploadProgress((prev) => ({
        ...prev,
        percentage: 100,
        statusText: '¡Consolidación exitosa!',
        stepVideo: 'ok',
        stepFinalize: 'ok',
      }));

      showToast("¡Recorrido enviado correctamente!", "ok");

      // Limpiar IndexedDB y reiniciar UI
      await clearPendingUpload();

      setTimeout(async () => {
        setIsUploadOpen(false);
        await resetRecording();
      }, 2000);

    } catch (err: any) {
      console.error(err);
      setUploadProgress((prev) => {
        // Encontrar en qué paso ocurrió el fallo para marcar la X
        const isInitFailed = prev.stepInit === 'run';
        const isVideoFailed = prev.stepVideo === 'run';
        return {
          ...prev,
          statusText: 'Error en la subida. Verifica la red y vuelve a intentar.',
          stepInit: isInitFailed ? 'err' : prev.stepInit,
          stepVideo: isVideoFailed ? 'err' : prev.stepVideo,
          stepFinalize: !isInitFailed && !isVideoFailed ? 'err' : 'waiting',
        };
      });

      showToast("Fallo en la subida al servidor", "err");

      // Dejar el modal abierto unos segundos para lectura del error
      setTimeout(() => {
        setIsUploadOpen(false);
      }, 5000);
    }
  };

  // Si Next.js aún no terminó de hidratar en cliente, renderizamos un spinner
  if (!mounted) {
    return (
      <div className="flex items-center justify-center w-screen h-screen bg-black text-blue-500">
        <div className="animate-spin text-3xl">⌛</div>
      </div>
    );
  }

  return (
    <main className="fixed inset-0 w-full h-[100dvh] bg-black overflow-hidden flex flex-col landscape:flex-row select-none">

      {/* ── CONTENEDOR DE CÁMARA (BACKGROUND) ── */}
      <div className="absolute inset-0 w-full h-full z-0 bg-black overflow-hidden">
        {stream ? (
          <video
            ref={videoRef}
            autoPlay
            playsInline
            muted
            className="w-full h-full object-cover select-none pointer-events-none"
          />
        ) : (
          <div className="flex flex-col items-center justify-center w-full h-full text-zinc-500 gap-2">
            <span className="text-4xl animate-pulse">📷</span>
            <span className="text-xs font-mono">Inicializando stream de cámara...</span>
          </div>
        )}
      </div>

      {/* ── PANEL SUPERIOR (Header) ── */}
      <TopBar
        gpsText={gpsText}
        isGpsOk={isGpsOk}
        recording={recording}
        videoBlobExists={!!videoBlob || hasPending}
        onOpenSettings={() => setIsSettingsOpen(true)}
      />

      {/* ── HUD INDICADORES ── */}
      <HUD
        latitude={gps ? gps.lat : null}
        longitude={gps ? gps.lng : null}
        accuracy={gps ? gps.accuracy : null}
        resolution={activeResolution}
        pointsCount={telemetryData.length}
      />

      {/* ── PANEL DE MANDOS (Controles de grabación y cronómetro) ── */}
      <div className="portrait:absolute portrait:bottom-0 portrait:left-0 portrait:right-0 landscape:absolute landscape:right-6 landscape:top-0 landscape:bottom-0 landscape:w-[220px] landscape:h-full z-30 portrait:bg-gradient-to-t portrait:from-black/95 portrait:via-black/70 portrait:to-transparent flex flex-col justify-end landscape:justify-center p-4 portrait:pb-[calc(1.5rem+env(safe-area-inset-bottom,20px))]">
        <RecControls
          recording={recording}
          timerText={timerText}
          videoBlobExists={!!videoBlob || hasPending}
          onStartRecording={startRecording}
          onStopRecording={stopRecording}
          onUploadToServer={handleUpload}
          onDownloadVideo={downloadVideo}
          onDownloadJSON={() => downloadJSON(telemetryData)}
          onReset={resetRecording}
        />
      </div>

      {/* ── TOAST / ALERTA FLOTANTE ── */}
      {toast && (
        <div className={`fixed top-24 left-1/2 -translate-x-1/2 z-50 flex items-center justify-center px-4 py-2.5 rounded-xl border text-xs font-bold tracking-wide shadow-xl backdrop-blur-md transition-all duration-300 animate-in fade-in slide-in-from-top-4 ${
          toast.type === 'ok'
            ? 'bg-emerald-950/90 border-emerald-500/30 text-emerald-400'
            : toast.type === 'err'
            ? 'bg-rose-950/90 border-rose-500/30 text-rose-400'
            : 'bg-zinc-950/90 border-white/10 text-zinc-200'
        }`}>
          {toast.msg}
        </div>
      )}

      {/* ── MODALES ── */}
      <SettingsModal
        isOpen={isSettingsOpen}
        onClose={() => setIsSettingsOpen(false)}
        devices={devices}
        currentSettings={settings}
        onSaveSettings={handleSaveSettings}
      />

      <UploadModal
        isOpen={isUploadOpen}
        progress={uploadProgress}
      />

    </main>
  );
}
