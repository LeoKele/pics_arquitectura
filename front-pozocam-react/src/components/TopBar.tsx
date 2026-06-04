// src/components/TopBar.tsx
'use client';

import React from 'react';
import { FontAwesomeIcon } from '@fortawesome/react-fontawesome';
import { faGear } from '@fortawesome/free-solid-svg-icons';

interface TopBarProps {
  gpsText: string;
  isGpsOk: boolean;
  recording: boolean;
  videoBlobExists: boolean;
  onOpenSettings: () => void;
}

export default function TopBar({
  gpsText,
  isGpsOk,
  recording,
  videoBlobExists,
  onOpenSettings,
}: TopBarProps) {
  return (
    <header className="absolute top-0 left-0 right-0 z-40 flex items-center justify-between p-4 bg-gradient-to-b from-black/80 to-transparent">
      {/* Logotipo */}
      <div className="flex items-center gap-1.5 select-none">
        <span className="text-2xl font-black tracking-wider text-blue-500">
          POZO<span className="text-white font-medium opacity-60">CAM</span>
        </span>
      </div>

      {/* Badges y Configuración */}
      <div className="flex items-center gap-3">
        <div className="flex items-center gap-1.5">
          {/* Pill GPS */}
          <div
            className={`flex items-center gap-1.5 px-3 py-1 text-[10px] font-bold tracking-wider uppercase rounded-full border transition-all duration-300 bg-black/40 backdrop-blur-md ${
              isGpsOk
                ? 'border-sky-400 text-sky-400 shadow-[0_0_8px_rgba(56,189,248,0.25)]'
                : gpsText === 'Buscando...'
                ? 'border-zinc-700 text-zinc-500'
                : 'border-sky-800 text-sky-600/90 shadow-[0_0_6px_rgba(2,132,199,0.15)]'
            }`}
          >
            <span
              className={`w-2 h-2 rounded-full transition-colors ${
                isGpsOk
                  ? 'bg-sky-400 animate-pulse'
                  : gpsText === 'Buscando...'
                  ? 'bg-zinc-600'
                  : 'bg-sky-700'
              }`}
            />
            {gpsText}
          </div>

          {/* Pill Grabador */}
          <div
            className={`flex items-center gap-1.5 px-3 py-1 text-[10px] font-bold tracking-wider uppercase rounded-full border transition-all duration-300 bg-black/40 backdrop-blur-md ${
              recording
                ? 'border-cyan-400 text-cyan-400 shadow-[0_0_8px_rgba(34,211,238,0.35)] animate-pulse'
                : videoBlobExists
                ? 'border-blue-500 text-blue-400 shadow-[0_0_8px_rgba(59,130,246,0.2)]'
                : 'border-zinc-700 text-zinc-500'
            }`}
          >
            <span
              className={`w-2 h-2 rounded-full ${
                recording
                  ? 'bg-cyan-400 animate-ping'
                  : videoBlobExists
                  ? 'bg-blue-500'
                  : 'bg-zinc-600'
              }`}
            />
            {recording ? 'REC' : videoBlobExists ? 'LISTO' : 'IDLE'}
          </div>
        </div>

        {/* Botón Configuración */}
        <button
          onClick={onOpenSettings}
          className="flex items-center justify-center w-9 h-9 text-zinc-300 hover:text-white bg-black/40 hover:bg-black/60 backdrop-blur-md border border-white/10 hover:border-white/20 rounded-full transition-all duration-200 active:scale-95"
          aria-label="Configuración"
        >
          <FontAwesomeIcon icon={faGear} className="text-sm" />
        </button>
      </div>
    </header>
  );
}
