"use client";
import { useState, useEffect, useRef } from "react";
import { marked } from "marked";

export default function ModalReporte({ isOpen, onClose, videoSeleccionado, metodo }) {
  const [contenido, setContenido] = useState("");
  const [estado, setEstado] = useState("idle");
  const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
  const abortControllerRef = useRef(null);
  const scrollRef = useRef(null);

  useEffect(() => {
    if (!isOpen || !videoSeleccionado) return;

    setContenido("");
    setEstado("loading");

    abortControllerRef.current = new AbortController();

    const buscarGenerarReporte = async () => {
      try {
        let url = "";
        let opciones: any = { signal: abortControllerRef.current.signal };

        if (metodo === "POST") {
          url = `${API_URL}/api/v1/reportes/generar`;
          opciones.method = "POST";
          opciones.headers = { "Content-Type": "application/json" };
          opciones.body = JSON.stringify({ video_ids: [videoSeleccionado] });
          setEstado("stream");
        } else {
          url = `${API_URL}/api/v1/reporte/${videoSeleccionado}`;
          opciones.method = "GET";
        }

        const res = await fetch(url, opciones);

        if (res.status === 404 && metodo === "GET") {
          setEstado("notfound");
          return;
        }

        if (!res.ok) throw new Error("Error en servidor");

        if (metodo === "POST") {
          const reader = res.body.getReader();
          const decoder = new TextDecoder("utf-8");
          let textoAcumulado = "";

          while (true) {
            const { done, value } = await reader.read();
            if (done) break;

            textoAcumulado += decoder.decode(value, { stream: true });
            setContenido((marked.parse(textoAcumulado) as string) + '<span class="text-[#00aaff] animate-pulse"> █</span>');

            if (scrollRef.current) scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
          }

          setContenido(marked.parse(textoAcumulado) as string);
          setEstado("done");
        }
        else {
          const data = await res.json();
          const textoCrudo = data.contenido || data.reporte || data.texto || data.respuesta || JSON.stringify(data);
          setContenido(marked.parse(textoCrudo) as string);
          setEstado("done");
        }

      } catch (error) {
        if (error.name !== "AbortError") {
          console.error(error);
          setEstado("error");
        }
      }
    };

    buscarGenerarReporte();

    return () => {
      if (abortControllerRef.current) {
        abortControllerRef.current.abort();
      }
    };
  }, [isOpen, videoSeleccionado, metodo]);

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 bg-black/85 backdrop-blur-sm z-[2000] flex justify-center items-center">
      <style>{`
        @keyframes ia-loading { 0% { left: -30%; width: 30%; } 50% { width: 60%; } 100% { left: 100%; width: 30%; } }

        /* ESTILOS DE LETRA AJUSTADOS Y MÁS COMPACTOS */
        .markdown-report h1 { color: #00aaff; font-size: 1.4rem; border-bottom: 1px solid #333; padding-bottom: 6px; margin: 18px 0 12px 0; text-shadow: 0 0 8px rgba(0,170,255,0.3); font-weight: bold; }
        .markdown-report h2 { color: #00aaff; font-size: 1.15rem; margin: 18px 0 8px 0; font-weight: bold; }
        .markdown-report h3 { color: #00aaff; font-size: 1.05rem; margin: 14px 0 6px 0; font-weight: bold; }
        .markdown-report p { margin-bottom: 12px; font-size: 0.9rem; line-height: 1.6; }
        .markdown-report ul { margin-left: 20px; margin-bottom: 12px; list-style-type: disc; font-size: 0.9rem; line-height: 1.6; }
        .markdown-report li { margin-bottom: 6px; }
        .markdown-report strong { color: #ffffff; font-weight: 700; letter-spacing: 0.2px; }
      `}</style>

      <div className="bg-[#0a0a0a] border border-[#00aaff] rounded-xl w-[65%] max-w-[800px] max-h-[80vh] flex flex-col shadow-[0_10px_40px_rgba(0,170,255,0.15)]">

        {/* HEADER MODAL */}
        <div className="py-2.5 px-4 border-b border-[#222] flex justify-between items-center bg-[#121212] rounded-t-xl drop-shadow-[0_0_5px_rgba(0,170,255,0.2)]">
          <h2 className="text-base font-bold text-[#00aaff] flex items-center gap-2 drop-shadow-[0_0_8px_rgba(0,170,255,0.5)]">
            <i className="fa-solid fa-robot text-[1.1rem]"></i> Reporte de Inspección Inteligente
          </h2>
          <button onClick={onClose} className="text-[#ff3d3d] text-2xl leading-none hover:text-[#ff6b6b] hover:scale-110 transition-all">&times;</button>
        </div>

        {/* BARRA DE PROGRESO */}
        {estado === "stream" && (
          <div className="w-full h-1 bg-[#333] relative overflow-hidden">
            <div className="absolute h-full bg-[#00aaff] shadow-[0_0_10px_#00aaff]" style={{ animation: 'ia-loading 1.5s infinite ease-in-out' }}></div>
          </div>
        )}
        {estado === "done" && metodo === "POST" && (
          <div className="w-full h-1 bg-[#198754] shadow-[0_0_10px_#198754]"></div>
        )}

        <div ref={scrollRef} className="p-6 overflow-y-auto text-[#e0e0e0] text-sm leading-relaxed custom-scrollbar">

          {estado === "loading" && (
            <div className="text-center py-10">
              <div className="text-[#00aaff] text-3xl mb-4 drop-shadow-[0_0_8px_rgba(0,170,255,0.6)]"><i className="fa-solid fa-circle-notch fa-spin"></i></div>
              <div className="text-gray-300 text-sm font-semibold">Buscando el reporte guardado...</div>
            </div>
          )}

          {estado === "stream" && contenido === "" && (
             <div className="text-[#00aaff] text-sm italic text-center py-8"><i className="fa-solid fa-plug fa-fade mr-2"></i> Analizando datos geográficos e inicializando Llama 3.2...</div>
          )}

          {estado === "notfound" && (
            <div className="text-center py-10">
              <div className="text-[#ffb86c] text-4xl mb-4"><i className="fa-solid fa-folder-open"></i></div>
              <strong className="text-white text-lg block mb-2">No hay ningún reporte guardado.</strong>
              <span className="text-gray-400 text-sm">Usá el botón "Generar Nuevo Reporte" en la barra lateral para que la IA lo redacte.</span>
            </div>
          )}

          {estado === "error" && (
            <div className="text-center py-10">
              <div className="text-[#ff3d3d] text-4xl mb-4 drop-shadow-[0_0_8px_rgba(255,61,61,0.5)]"><i className="fa-solid fa-triangle-exclamation"></i></div>
              <strong className="text-[#ff3d3d] text-lg block mb-2">Error de conexión con la IA</strong>
              <span className="text-gray-400 text-sm">Verificá los logs del servidor con Grafana.</span>
            </div>
          )}

          {(estado === "stream" || estado === "done") && (
            <div className="markdown-report" dangerouslySetInnerHTML={{ __html: contenido }} />
          )}

        </div>
      </div>
    </div>
  );
}
