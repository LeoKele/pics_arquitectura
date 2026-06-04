// src/components/HUD.tsx
'use client';

import React from 'react';
import { FontAwesomeIcon } from '@fortawesome/react-fontawesome';
import { faSatelliteDish } from '@fortawesome/free-solid-svg-icons';

interface HUDProps {
  latitude: number | null;
  longitude: number | null;
  accuracy: number | null;
  resolution: string;
  pointsCount: number;
}

export default function HUD({
  latitude,
  longitude,
  accuracy,
  resolution,
  pointsCount,
}: HUDProps) {
  // Formatear coordenadas
  const latStr = latitude !== null ? latitude.toFixed(6) : 'Buscando...';
  const lngStr = longitude !== null ? longitude.toFixed(6) : '';
  const accuracyStr = accuracy !== null ? `±${Math.round(accuracy)}m` : '—';

  return (
    <div className="absolute z-30 select-none pointer-events-none flex gap-1.5 portrait:top-20 portrait:left-4 portrait:right-4 portrait:bottom-auto portrait:max-w-none portrait:flex-row portrait:flex-wrap portrait:justify-start landscape:left-4 landscape:bottom-6 landscape:max-w-[200px] landscape:flex-col">
      {/* Badge Posición GPS */}
      <div className="px-2 py-1 text-[9px] font-mono font-bold text-zinc-300 bg-black/60 backdrop-blur-md border border-white/10 rounded shadow-md pointer-events-auto flex items-center gap-1.5">
        <FontAwesomeIcon icon={faSatelliteDish} className="text-blue-400 text-[8px]" />
        <span>GPS:</span>
        <span className="text-blue-400 font-black">{latStr}{lngStr ? `, ${lngStr}` : ''}</span>
      </div>

      {/* Badge Resolución */}
      <div className="px-2 py-1 text-[9px] font-mono font-bold text-zinc-300 bg-black/60 backdrop-blur-md border border-white/10 rounded shadow-md pointer-events-auto">
        Res: <span className="text-blue-400 font-black">{resolution}</span>
      </div>

      {/* Badge Puntos */}
      <div className="px-2 py-1 text-[9px] font-mono font-bold text-zinc-300 bg-black/60 backdrop-blur-md border border-white/10 rounded shadow-md pointer-events-auto">
        Pts: <span className="text-blue-400 font-black">{pointsCount}</span>
      </div>

      {/* Badge Precisión */}
      <div className="px-2 py-1 text-[9px] font-mono font-bold text-zinc-300 bg-black/60 backdrop-blur-md border border-white/10 rounded shadow-md pointer-events-auto">
        Acc: <span className="text-blue-400 font-black">{accuracyStr}</span>
      </div>
    </div>
  );
}
