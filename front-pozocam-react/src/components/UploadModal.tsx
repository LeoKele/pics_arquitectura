// src/components/UploadModal.tsx
'use client';

import React from 'react';
import { UploadProgressState, UploadStepStatus } from '@/types';
import { FontAwesomeIcon } from '@fortawesome/react-fontawesome';
import {
  faCircleNotch,
  faCircleCheck,
  faCircleXmark,
  faCloudArrowUp,
  faCircle,
} from '@fortawesome/free-solid-svg-icons';


interface UploadModalProps {
  isOpen: boolean;
  progress: UploadProgressState;
}

export default function UploadModal({ isOpen, progress }: UploadModalProps) {
  if (!isOpen) return null;

  // Renderizar icono de estado según el paso
  const renderStepIcon = (status: UploadStepStatus) => {
    switch (status) {
      case 'run':
        return (
          <FontAwesomeIcon
            icon={faCircleNotch}
            className="text-amber-400 animate-spin text-sm"
          />
        );
      case 'ok':
        return (
          <FontAwesomeIcon
            icon={faCircleCheck}
            className="text-emerald-400 text-sm"
          />
        );
      case 'err':
        return (
          <FontAwesomeIcon
            icon={faCircleXmark}
            className="text-rose-500 text-sm"
          />
        );
      case 'waiting':
      default:
        return (
          <FontAwesomeIcon
            icon={faCircle}
            className="text-zinc-600 text-sm opacity-60"
          />
        );
    }
  };

  // Renderizar clase del texto del paso
  const getStepTextClass = (status: UploadStepStatus) => {
    switch (status) {
      case 'run':
        return 'text-amber-400 font-medium';
      case 'ok':
        return 'text-emerald-400';
      case 'err':
        return 'text-rose-500 font-bold';
      case 'waiting':
      default:
        return 'text-zinc-500 opacity-60';
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      {/* Backdrop estático para impedir interacción de fondo */}
      <div className="absolute inset-0 bg-black/85 backdrop-blur-md" />

      {/* Tarjeta Modal */}
      <div className="relative w-full max-w-sm bg-zinc-950/90 border border-white/10 rounded-3xl p-6 shadow-2xl backdrop-blur-xl text-center select-none animate-in fade-in zoom-in-95 duration-200">

        {/* Cabecera / Título */}
        <div className="flex flex-col items-center gap-2 mb-4">
          <div className="w-12 h-12 bg-blue-500/10 border border-blue-500/20 text-blue-400 flex items-center justify-center rounded-2xl animate-pulse">
            <FontAwesomeIcon icon={faCloudArrowUp} className="text-xl" />
          </div>
          <h2 className="text-md font-black tracking-wider text-blue-400 uppercase mt-2">
            Subiendo Recorrido
          </h2>
          <p className="text-xs text-zinc-300 min-h-[16px] leading-tight">
            {progress.statusText}
          </p>
        </div>

        {/* Barra de progreso Tailwind */}
        <div className="relative w-full h-3 bg-zinc-900 border border-white/5 rounded-full overflow-hidden mb-6">
          <div
            className="h-full bg-gradient-to-r from-blue-600 to-blue-400 shadow-[0_0_8px_rgba(59,130,246,0.3)] rounded-full transition-all duration-300 ease-out"
            style={{ width: `${progress.percentage}%` }}
          />
        </div>

        {/* Pasos de subida */}
        <div className="text-left text-xs text-zinc-300 border-t border-white/5 pt-4 flex flex-col gap-3">
          {/* Paso 1: Iniciar */}
          <div className="flex items-center gap-2.5">
            {renderStepIcon(progress.stepInit)}
            <span className={getStepTextClass(progress.stepInit)}>
              Inicializar subida en servidor
            </span>
          </div>

          {/* Paso 2: GPS */}
          <div className="flex items-center gap-2.5">
            {renderStepIcon(progress.stepGps)}
            <span className={getStepTextClass(progress.stepGps)}>
              Enviar metadata GPS
            </span>
          </div>

          {/* Paso 3: Video Chunks */}
          <div className="flex items-center gap-2.5">
            {renderStepIcon(progress.stepVideo)}
            <span className={getStepTextClass(progress.stepVideo)}>
              Subir video en partes
            </span>
          </div>

          {/* Paso 4: Finalizar */}
          <div className="flex items-center gap-2.5">
            {renderStepIcon(progress.stepFinalize)}
            <span className={getStepTextClass(progress.stepFinalize)}>
              Consolidar y procesar
            </span>
          </div>
        </div>

      </div>
    </div>
  );
}
