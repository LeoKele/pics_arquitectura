// src/components/RecControls.tsx
'use client';

import React from 'react';
import { FontAwesomeIcon } from '@fortawesome/react-fontawesome';
import {
  faCircle,
  faStop,
  faCloudArrowUp,
  faVideo,
  faFileCode,
  faRotateLeft,
} from '@fortawesome/free-solid-svg-icons';

interface RecControlsProps {
  recording: boolean;
  timerText: string;
  videoBlobExists: boolean;
  onStartRecording: () => void;
  onStopRecording: () => void;
  onUploadToServer: () => void;
  onDownloadVideo: () => void;
  onDownloadJSON: () => void;
  onReset: () => void;
}

export default function RecControls({
  recording,
  timerText,
  videoBlobExists,
  onStartRecording,
  onStopRecording,
  onUploadToServer,
  onDownloadVideo,
  onDownloadJSON,
  onReset,
}: RecControlsProps) {
  return (
    <div className="flex flex-col items-center justify-center w-full gap-4 select-none">
      {/* Temporizador con cápsula protectora translúcida para legibilidad (tamaño compacto) */}
      <div className="bg-black/40 backdrop-blur-md border border-white/5 px-4 py-2 rounded-xl shadow-[0_4px_12px_rgba(0,0,0,0.6)]">
        <div
          className={`text-sm portrait:text-base font-black font-mono tracking-wider transition-colors duration-300 ${
            recording ? 'text-cyan-400 drop-shadow-[0_0_12px_rgba(34,211,238,0.4)]' : 'text-zinc-100'
          }`}
        >
          {timerText}
        </div>
      </div>

      {/* Rejilla de Botones de Control */}
      <div className="w-full max-w-sm">
        {recording ? (
          /* Botón detener */
          <button
            onClick={onStopRecording}
            className="w-full flex items-center justify-center gap-2 py-4 text-sm font-black tracking-widest text-zinc-950 bg-white hover:bg-zinc-100 rounded-2xl shadow-[0_4px_20px_rgba(255,255,255,0.15)] transition-all duration-200 active:scale-98 cursor-pointer uppercase"
          >
            <FontAwesomeIcon icon={faStop} className="text-zinc-950 w-4 h-4" />
            Detener
          </button>
        ) : videoBlobExists ? (
          /* Opciones después de grabar */
          <div className="flex flex-col gap-2">
            {/* Subir al Servidor */}
            <button
              onClick={onUploadToServer}
              className="w-full flex items-center justify-center gap-2 py-4 text-xs portrait:text-sm font-black tracking-wider text-zinc-950 bg-gradient-to-r from-sky-400 to-blue-500 hover:from-sky-300 hover:to-blue-400 rounded-2xl shadow-[0_4px_25px_rgba(56,189,248,0.45)] transition-all duration-200 active:scale-98 cursor-pointer uppercase whitespace-nowrap"
            >
              <FontAwesomeIcon icon={faCloudArrowUp} className="text-zinc-950/70 w-4 h-4 flex-shrink-0" />
              Subir Recorrido
            </button>

            {/* Descargas (Video y Datos) */}
            <div className="grid grid-cols-2 gap-2">
              <button
                onClick={onDownloadVideo}
                className="flex items-center justify-center gap-2 py-3 text-xs font-bold text-zinc-300 hover:text-white bg-zinc-900/80 hover:bg-zinc-800/80 backdrop-blur-md border border-white/10 hover:border-white/20 rounded-xl transition-all duration-200 active:scale-95 cursor-pointer uppercase"
              >
                <FontAwesomeIcon icon={faVideo} className="text-sky-400 w-3.5 h-3.5" />
                Video
              </button>
              <button
                onClick={onDownloadJSON}
                className="flex items-center justify-center gap-2 py-3 text-xs font-bold text-zinc-300 hover:text-white bg-zinc-900/80 hover:bg-zinc-800/80 backdrop-blur-md border border-white/10 hover:border-white/20 rounded-xl transition-all duration-200 active:scale-95 cursor-pointer uppercase"
              >
                <FontAwesomeIcon icon={faFileCode} className="text-sky-400 w-3.5 h-3.5" />
                Datos
              </button>
            </div>

            {/* Iniciar Grabación Nueva */}
            <button
              onClick={onReset}
              className="w-full flex items-center justify-center gap-2 py-3 text-xs font-bold text-zinc-300 hover:text-white bg-zinc-900/80 hover:bg-zinc-800/80 backdrop-blur-md border border-white/10 hover:border-white/20 rounded-xl transition-all duration-200 active:scale-95 cursor-pointer uppercase"
            >
              <FontAwesomeIcon icon={faRotateLeft} className="text-zinc-400 w-3.5 h-3.5" />
              Nuevo Recorrido
            </button>
          </div>
        ) : (
          /* Botón Iniciar Grabación */
          <button
            onClick={onStartRecording}
            className="w-full flex items-center justify-center gap-2 py-4 text-sm font-black tracking-widest text-zinc-950 bg-gradient-to-r from-sky-400 to-blue-500 hover:from-sky-300 hover:to-blue-400 rounded-2xl shadow-[0_4px_25px_rgba(56,189,248,0.45)] transition-all duration-200 active:scale-98 cursor-pointer uppercase"
          >
            <FontAwesomeIcon icon={faCircle} className="text-zinc-950/70 animate-pulse w-3 h-3" />
            Grabar
          </button>
        )}
      </div>
    </div>
  );
}
