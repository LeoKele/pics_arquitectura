"use client";
import { useState, useRef, useEffect } from "react";
import { marked } from "marked";

export default function ChatIA({ videoSeleccionado, onVolverGlobal }) {
  const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
  const [mensajes, setMensajes] = useState([
    { rol: "ai", texto: "¡Hola! Soy tu asistente vial. Podés preguntarme por **todo el municipio de Moreno**, o seleccionar un video específico para enfocar el análisis." }
  ]);
  const [input, setInput] = useState("");
  const [cargando, setCargando] = useState(false);

  const finDelChatRef = useRef(null);

  useEffect(() => {
    finDelChatRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [mensajes]);

  useEffect(() => {
    if (videoSeleccionado) {
      setMensajes(prev => [...prev, { rol: "ai", texto: `*He enfocado mis sensores en el **Video #${videoSeleccionado}**. ¿Qué querés analizar?*` }]);
    }
  }, [videoSeleccionado]);

  const enviarMensaje = async (e) => {
    e.preventDefault();
    if (!input.trim() || cargando) return;

    const textoUsuario = input.trim();
    setInput("");

    setMensajes(prev => [...prev, { rol: "user", texto: textoUsuario }]);
    setCargando(true);

    try {
      const contexto = videoSeleccionado || 0;
      const res = await fetch(`${API_URL}/api/v1/video/${contexto}/preguntar`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ pregunta: textoUsuario })
      });

      if (!res.ok) throw new Error("Fallo en la IA");
      const data = await res.json();
      const respuestaIA = data.respuesta || data.mensaje || JSON.stringify(data);

      setMensajes(prev => [...prev, { rol: "ai", texto: respuestaIA }]);
    } catch (error) {
      setMensajes(prev => [...prev, { rol: "ai", texto: "<i class='fa-solid fa-triangle-exclamation text-[#ff3d3d] mr-1.5'></i> **Error.** Verifica la conexión con el contenedor de la API." }]);
    } finally {
      setCargando(false);
    }
  };

  return (
    <div className="flex flex-col h-full bg-[#0a0a0a] border border-[#222] rounded-xl overflow-hidden shadow-[0_8px_30px_rgb(0,0,0,0.6)] hover:border-[#00aaff]/30 transition-colors">

      {/* HEADER DEL CHAT */}
      <div className="bg-[#121212] p-2.5 border-b border-[#222] flex justify-between items-center drop-shadow-[0_0_5px_rgba(0,170,255,0.2)]">
        <span className="font-bold text-[#00aaff] text-[1.05rem] flex items-center gap-1.5 drop-shadow-[0_0_8px_rgba(0,170,255,0.5)]">
          <i className="fa-solid fa-microchip"></i> Inteligencia Vial - PozoBot
        </span>
        <div className="flex items-center gap-2">
          {videoSeleccionado && (
            <button
              onClick={onVolverGlobal}
              className="bg-[#00aaff] text-black border-none rounded-md px-2.5 py-1 text-[0.8rem] font-bold cursor-pointer hover:bg-white transition-colors shadow-[0_0_8px_rgba(0,170,255,0.3)]"
              title="Desmarcar video y volver al municipio entero"
            >
              <i className="fa-solid fa-earth-americas mr-1"></i> Global
            </button>
          )}
        </div>
      </div>

      {/* ÁREA DE MENSAJES */}
      <div className="flex-1 p-3 overflow-y-auto flex flex-col gap-2.5 custom-scrollbar">
        {mensajes.map((msg, i) => (
          <div key={i} className={`p-3 rounded-xl max-w-[85%] ${
            msg.rol === 'user'
              ? 'bg-[#00aaff]/20 text-[#e0e0e0] border border-[#00aaff]/50 self-end rounded-br-sm shadow-[0_0_10px_rgba(0,170,255,0.1)]'
              : 'bg-[#121212] text-gray-200 self-start rounded-bl-sm border border-[#222] border-l-[3px] border-l-[#00aaff] shadow-md'
          }`}>
            <div dangerouslySetInnerHTML={{ __html: marked.parse(msg.texto) }} className="markdown-chat text-xs sm:text-sm leading-relaxed tracking-wide" />
          </div>
        ))}
        {cargando && (
          <div className="bg-[#121212] text-[#00aaff] self-start rounded-xl rounded-bl-sm border border-[#222] border-l-[3px] border-l-[#00aaff] p-3 text-xs sm:text-sm shadow-md font-semibold animate-pulse">
            <i className="fa-solid fa-circle-notch fa-spin mr-2"></i> Procesando tu consulta...
          </div>
        )}
        <div ref={finDelChatRef} />
      </div>

      {/* INPUT DEL USUARIO */}
      <form onSubmit={enviarMensaje} className="p-2.5 bg-[#121212] border-t border-[#222] flex gap-2">
        <input
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder={videoSeleccionado ? `Preguntá sobre el Video #${videoSeleccionado}...` : "Consultá sobre el estado vial de Moreno..."}
          className="flex-1 px-3 py-1.5 rounded-lg border border-[#333] bg-[#0a0a0a] text-white outline-none focus:border-[#00aaff] focus:shadow-[0_0_10px_rgba(0,170,255,0.2)] text-xs sm:text-sm transition-all"
          disabled={cargando}
        />
        <button
          type="submit"
          disabled={cargando || !input.trim()}
          className="bg-[#00aaff] text-black px-3.5 py-1.5 rounded-lg font-bold text-sm hover:bg-white disabled:bg-[#222] disabled:text-[#555] disabled:cursor-not-allowed transition-all shadow-[0_0_10px_rgba(0,170,255,0.3)]"
        >
          <i className="fa-solid fa-paper-plane text-xs"></i>
        </button>
      </form>
    </div>
  );
}
