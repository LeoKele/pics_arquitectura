"use client";
import { useState, useEffect } from "react";
import { Falla } from "../types";
import React from "react";

interface Props {
  falla: Falla | null;
  videoSeleccionado: number | null;
  onAuditoriaCompletada: () => void;
}

export default function FotoDeteccion({ falla, videoSeleccionado, onAuditoriaCompletada }: Props) {
  const [imgDims, setImgDims] = useState({ w: 0, h: 0 });
  const [ubicacion, setUbicacion] = useState<string>("Consultando GPS...");
  const [zoomOrigin, setZoomOrigin] = useState("50% 50%");
  const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

  useEffect(() => {
    setImgDims({ w: 0, h: 0 });
  }, [falla]);

  useEffect(() => {
    if (falla && falla.geometria && falla.geometria.coordinates) {
      const [lon, lat] = falla.geometria.coordinates;
      const buscarCalle = async () => {
        try {
          const resGeo = await fetch(`https://nominatim.openstreetmap.org/reverse?format=json&lat=${lat}&lon=${lon}`);
          const geoData = await resGeo.json();
          setUbicacion(geoData.address?.road || "Ubicación desconocida");
        } catch {
          setUbicacion(`Lat: ${lat.toFixed(4)}, Lng: ${lon.toFixed(4)}`);
        }
      };
      buscarCalle();
    }
  }, [falla]);

  const handleAuditoria = async (nuevoEstado: string) => {
    const accionTexto = nuevoEstado === 'falso_positivo' ? 'descartar esta detección (Falso Positivo)' : 'marcar esta detección como Verificada';
    if (!window.confirm(`¿Estás seguro de que querés ${accionTexto}?`)) return;

    try {
      const res = await fetch(`${API_URL}/api/v1/detecciones/${falla?.id}?nuevo_estado=${nuevoEstado}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' }
      });

      if (!res.ok) throw new Error("Fallo en la API al auditar la detección.");

      if (onAuditoriaCompletada) onAuditoriaCompletada();

    } catch (err) {
      console.error(err);
      alert("Ocurrió un error al auditar la detección. Revisá los logs en Grafana.");
    }
  };

  if (!videoSeleccionado && !falla) {
    return (
      <div className="flex-1 flex justify-center items-center text-center text-base px-4 text-gray-500">
        Seleccioná un Video en la barra lateral o un pin en el mapa para activar el análisis.
      </div>
    );
  }

  if (!falla) {
    return (
      <div className="flex flex-col items-center justify-center h-full min-h-[200px] text-[#00aaff] drop-shadow-[0_0_5px_rgba(0,170,255,0.4)] text-center text-xl font-semibold p-4">
        <span>Video #{videoSeleccionado} activado.</span>
        <span>Tocá un pin en el mapa para ver la foto específica.</span>
      </div>
    );
  }

  let bboxStyle: React.CSSProperties = { display: 'none' };
  try {
    if (falla.bbox && imgDims.w > 0 && imgDims.h > 0) {
      const caja = typeof falla.bbox === 'string' ? JSON.parse(falla.bbox) : falla.bbox;
      let x1 = caja.x_min ?? caja.xmin ?? caja.x1;
      let y1 = caja.y_min ?? caja.ymin ?? caja.y1;
      let x2 = caja.x_max ?? caja.xmax ?? caja.x2;
      let y2 = caja.y_max ?? caja.ymax ?? caja.y2;

      if (x2 <= 2 && y2 <= 2) {
        x1 *= imgDims.w; x2 *= imgDims.w;
        y1 *= imgDims.h; y2 *= imgDims.h;
      }

      const MARGEN = 4;
      let leftPct = (x1 / imgDims.w) * 100;
      let topPct = (y1 / imgDims.h) * 100;
      let widthPct = ((x2 - x1) / imgDims.w) * 100;
      let heightPct = ((y2 - y1) / imgDims.h) * 100;

      leftPct = Math.max(0, leftPct - MARGEN);
      topPct = Math.max(0, topPct - MARGEN);
      widthPct = Math.min(100 - leftPct, widthPct + (MARGEN * 2));
      heightPct = Math.min(100 - topPct, heightPct + (MARGEN * 2));

      bboxStyle = {
        display: 'block',
        left: `${leftPct}%`,
        top: `${topPct}%`,
        width: `${widthPct}%`,
        height: `${heightPct}%`
      };
    }
  } catch (e) { console.warn("Error calculando BBox", e); }
  const handleMouseMove = (e: React.MouseEvent<HTMLDivElement>) => {
    if (!e.currentTarget) return;
    const { left, top, width, height } = e.currentTarget.getBoundingClientRect();
    const x = ((e.clientX - left) / width) * 100;
    const y = ((e.clientY - top) / height) * 100;
    setZoomOrigin(`${x}% ${y}%`);
  };
  const urlImagen = `http://35.194.31.183:9000/detecciones/${falla.frame_minio_path}`;

  return (
    <div className="flex flex-col h-full overflow-y-auto pr-2 custom-scrollbar">
      {/* IMAGEN CON CAJA Y EFECTO LUPA INTELIGENTE */}
      <div
        className="relative w-full rounded-lg overflow-hidden border border-[#222] bg-black mb-5 shadow-[0_4px_15px_rgba(0,0,0,0.5)] group cursor-crosshair"
        onMouseMove={handleMouseMove}
        onMouseLeave={() => setZoomOrigin("50% 50%")}
      >

        {/* EL CONTENEDOR QUE HACE ZOOM HACIA EL PUNTERO */}
        <div
          className="relative w-full transition-transform duration-200 ease-out group-hover:scale-[2.2]"
          style={{ transformOrigin: zoomOrigin }}
        >
          {/* IMAGEN MÁS GRANDE*/}
          <img
            src={urlImagen}
            alt="Detección"
            className="w-full h-auto max-h-[320px] block object-contain"
            crossOrigin="anonymous"
            onLoad={(e) => {
              const img = e.target as HTMLImageElement;
              setImgDims({ w: img.naturalWidth, h: img.naturalHeight });
            }}
            onError={(e) => {
              const img = e.target as HTMLImageElement;
              img.style.display = 'none';
            }}
          />
          {/* RECTÁNGULO TURQUESA */}
          <div
            className="absolute border-[2px] border-[#00aaff] bg-[rgba(0,170,255,0.05)] pointer-events-none shadow-[0_0_10px_rgba(0,170,255,0.4)]"
            style={bboxStyle}
          >
            <span className="absolute -top-6 -left-[2px] bg-[#00aaff] text-black text-[0.7rem] px-2 py-0.5 rounded-t-md font-bold uppercase whitespace-nowrap shadow-[0_0_5px_rgba(0,170,255,0.6)]">
              {falla.tipo_dano || 'FALLA'}
            </span>
          </div>
        </div>

      </div>

      {/* METADATOS */}
      <div className="bg-[#121212] p-4 rounded-lg border border-[#222] text-[1.05rem] flex flex-col gap-3 shadow-inner">
        <div className="flex items-center gap-2">
          <i className="fa-solid fa-tag text-gray-500 w-5 text-center"></i>
          <strong className="text-gray-400">Tipo:</strong>
          <span className="text-[#00aaff] font-bold uppercase drop-shadow-[0_0_5px_rgba(0,170,255,0.5)] ml-1">
            {falla.tipo_dano || 'Bache'}
          </span>
        </div>
        <div className="flex items-center gap-2">
          <i className="fa-solid fa-percent text-gray-500 w-5 text-center"></i>
          <strong className="text-gray-400">Confianza:</strong>
          <span className="text-gray-200">{(falla.confianza * 100).toFixed(0)}%</span>
        </div>
        <div className="flex items-center gap-2">
          <i className="fa-solid fa-location-dot text-gray-500 w-5 text-center"></i>
          <strong className="text-gray-400">Ubicación:</strong>
          <span className="text-gray-200">{ubicacion}</span>
        </div>
        <div className="flex items-center gap-2">
          <i className="fa-solid fa-calendar text-gray-500 w-5 text-center"></i>
          <strong className="text-gray-400">Fecha:</strong>
          <span className="text-gray-200">{new Date(falla.fecha).toLocaleDateString('es-AR')}</span>
        </div>
      </div>

      {/* BOTONES AUDITORIA */}
      {falla.estado_auditoria === 'verificado' ? (
        <div className="mt-4 p-3 bg-[#00aaff]/10 backdrop-blur-md border border-[#00aaff]/50 shadow-[0_0_15px_rgba(0,170,255,0.2)] rounded-lg text-[#00aaff] text-center font-bold w-full text-[0.95rem]">
          <i className="fa-solid fa-shield-halved mr-2"></i> Falla Verificada
        </div>
      ) : (
        <div className="flex gap-3 mt-4">
          <button
            onClick={() => handleAuditoria('verificado')}
            className="flex-1 bg-[#00aaff]/10 backdrop-blur-md border border-[#00aaff]/50 text-[#00aaff] py-2.5 rounded-lg font-bold flex justify-center items-center gap-2 hover:bg-[#00aaff]/30 hover:shadow-[0_0_15px_rgba(0,170,255,0.4)] transition-all duration-300"
          >
            <i className="fa-solid fa-check-double"></i> Verificar
          </button>

          <button
            onClick={() => handleAuditoria('falso_positivo')}
            className="flex-1 bg-[#0055aa]/10 backdrop-blur-md border border-[#0055aa]/50 text-[#33ccff] py-2.5 rounded-lg font-bold flex justify-center items-center gap-2 hover:bg-[#0055aa]/40 hover:shadow-[0_0_15px_rgba(0,85,170,0.5)] transition-all duration-300"
          >
            <i className="fa-solid fa-trash-can"></i> Falso Pos.
          </button>
        </div>
      )}
    </div>
  );
}
