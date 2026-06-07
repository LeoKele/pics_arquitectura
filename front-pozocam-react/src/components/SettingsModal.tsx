// src/components/SettingsModal.tsx
'use client';

import React, { useState, useEffect } from 'react';
import { AppSettings } from '@/types';
import { FontAwesomeIcon } from '@fortawesome/react-fontawesome';
import { faGear, faTimes } from '@fortawesome/free-solid-svg-icons';

interface SettingsModalProps {
  isOpen: boolean;
  onClose: () => void;
  devices: MediaDeviceInfo[];
  currentSettings: AppSettings;
  onSaveSettings: (settings: AppSettings) => void;
}

export default function SettingsModal({
  isOpen,
  onClose,
  devices,
  currentSettings,
  onSaveSettings,
}: SettingsModalProps) {
  const [deviceId, setDeviceId] = useState<string>('');
  const [resolution, setResolution] = useState<string>('1920x1080');
  const [bitrate, setBitrate] = useState<number>(7500000);
  const [apiUrl, setApiUrl] = useState<string>('http://localhost:8000');

  // Sincronizar estados con settings actuales cuando se abre el modal
  useEffect(() => {
    if (isOpen) {
      setDeviceId(currentSettings.deviceId || (devices[0]?.deviceId || ''));
      setResolution(currentSettings.resolution);
      setBitrate(currentSettings.bitrate);
      setApiUrl(currentSettings.apiUrl);
    }
  }, [isOpen, currentSettings, devices]);

  if (!isOpen) return null;

  const handleSave = () => {
    onSaveSettings({
      deviceId: deviceId || null,
      resolution,
      bitrate: Number(bitrate),
      apiUrl,
    });
    onClose();
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      {/* Backdrop */}
      <div
        onClick={onClose}
        className="absolute inset-0 bg-black/80 backdrop-blur-sm transition-opacity"
      />

      {/* Tarjeta Modal */}
      <div className="relative w-full max-w-md bg-zinc-950/90 border border-white/10 rounded-3xl p-6 shadow-2xl backdrop-blur-xl animate-in fade-in zoom-in-95 duration-200">

        {/* Cabecera */}
        <div className="flex items-center justify-between mb-6 pb-3 border-b border-white/5">
          <div className="flex items-center gap-2 text-blue-400">
            <FontAwesomeIcon icon={faGear} className="text-lg" />
            <h2 className="text-lg font-black tracking-wider text-white uppercase">
              Configuración
            </h2>
          </div>
          <button
            onClick={onClose}
            className="flex items-center justify-center w-7 h-7 text-zinc-400 hover:text-white rounded-full hover:bg-white/5 transition-colors cursor-pointer"
          >
            <FontAwesomeIcon icon={faTimes} />
          </button>
        </div>

        {/* Formulario */}
        <div className="space-y-4 mb-6">
          {/* Selector Cámara */}
          <div className="flex flex-col gap-1.5">
            <label className="text-[10px] font-black uppercase tracking-wider text-zinc-400">
              Cámara
            </label>
            <select
              value={deviceId}
              onChange={(e) => setDeviceId(e.target.value)}
              className="w-full bg-zinc-900 border border-white/10 hover:border-white/20 text-sm text-zinc-100 rounded-xl px-3.5 py-2.5 focus:outline-none focus:ring-1 focus:ring-blue-500 transition-all cursor-pointer"
            >
              {devices.length === 0 ? (
                <option value="">No se encontraron cámaras</option>
              ) : (
                devices.map((device, idx) => (
                  <option key={device.deviceId} value={device.deviceId}>
                    {device.label || `Cámara ${idx + 1} (${device.deviceId.slice(0, 5)})`}
                  </option>
                ))
              )}
            </select>
          </div>

          {/* Selector Resolución */}
          <div className="flex flex-col gap-1.5">
            <label className="text-[10px] font-black uppercase tracking-wider text-zinc-400">
              Resolución / Ratio
            </label>
            <select
              value={resolution}
              onChange={(e) => setResolution(e.target.value)}
              className="w-full bg-zinc-900 border border-white/10 hover:border-white/20 text-sm text-zinc-100 rounded-xl px-3.5 py-2.5 focus:outline-none focus:ring-1 focus:ring-blue-500 transition-all cursor-pointer"
            >
              <option value="1920x1080">Full HD (16:9) - 1080p</option>
              <option value="1280x720">HD (16:9) - 720p</option>
              <option value="1080x1080">Square (1:1) - 1080px</option>
              <option value="full">Pantalla Completa (Auto)</option>
            </select>
          </div>

          {/* Selector Calidad / Bitrate */}
          <div className="flex flex-col gap-1.5">
            <label className="text-[10px] font-black uppercase tracking-wider text-zinc-400">
              Calidad Video (Bitrate)
            </label>
            <select
              value={bitrate}
              onChange={(e) => setBitrate(Number(e.target.value))}
              className="w-full bg-zinc-900 border border-white/10 hover:border-white/20 text-sm text-zinc-100 rounded-xl px-3.5 py-2.5 focus:outline-none focus:ring-1 focus:ring-blue-500 transition-all cursor-pointer"
            >
              <option value={10000000}>Muy Alta (10 Mbps)</option>
              <option value={7500000}>Alta (7.5 Mbps)</option>
              <option value={5000000}>Media (5 Mbps)</option>
              <option value={2500000}>Baja (2.5 Mbps)</option>
            </select>
          </div>

          {/* Servidor API */}
          <div className="flex flex-col gap-1.5">
            <label className="text-[10px] font-black uppercase tracking-wider text-zinc-400">
              Servidor API
            </label>
            <input
              type="text"
              value={apiUrl}
              onChange={(e) => setApiUrl(e.target.value)}
              placeholder="http://localhost:8000"
              className="w-full bg-zinc-900 border border-white/10 hover:border-white/20 text-sm text-zinc-100 rounded-xl px-3.5 py-2.5 focus:outline-none focus:ring-1 focus:ring-blue-500 transition-all"
            />
          </div>
        </div>

        {/* Botones */}
        <div className="flex flex-col gap-2 pt-2">
          <button
            onClick={handleSave}
            className="w-full py-3 text-sm font-black tracking-widest text-zinc-950 bg-gradient-to-r from-sky-400 to-blue-500 hover:from-sky-300 hover:to-blue-400 rounded-2xl shadow-[0_4px_15px_rgba(56,189,248,0.3)] transition-all duration-200 active:scale-98 cursor-pointer uppercase"
          >
            Guardar Cambios
          </button>
          <button
            onClick={onClose}
            className="w-full py-3 text-xs font-bold text-zinc-400 hover:text-zinc-200 rounded-2xl border border-white/5 hover:bg-white/5 transition-all duration-200 active:scale-98 cursor-pointer uppercase"
          >
            Cerrar
          </button>
        </div>

      </div>
    </div>
  );
}
