"use client";
import { useState, useEffect } from "react";
import dynamic from "next/dynamic";
import { Falla } from "../types";
import FotoDeteccion from "./FotoDeteccion";
import ChatIA from "./ChatIA";
import ModalReporte from "./ModalReporte";
import Link from "next/link";

const MapaVial = dynamic(() => import("./MapaVial"), {
  ssr: false,
  loading: () => <div className="flex justify-center items-center h-full text-[#00aaff]"><i className="fa-solid fa-circle-notch fa-spin text-4xl"></i></div>
});

interface DashboardProps {
  rol: string;
  onLogout: () => void;
}

export default function Dashboard({ rol, onLogout }: DashboardProps) {
  const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
  const GRAFANA_URL = process.env.NEXT_PUBLIC_GRAFANA_URL || "http://localhost:3000";

  const [stats, setStats] = useState({ baches: 0, videos: 0 });
  const [listaVideos, setListaVideos] = useState<any[]>([]);
  const [videoSeleccionado, setVideoSeleccionado] = useState<number | null>(null);
  const [deteccionesTotales, setDeteccionesTotales] = useState<Falla[]>([]);
  const [fallaSeleccionada, setFallaSeleccionada] = useState<Falla | null>(null);
  const [modalAbierto, setModalAbierto] = useState(false);
  const [metodoModal, setMetodoModal] = useState("GET");
  const [trayectorias, setTrayectorias] = useState({});
  const [estadoSistema, setEstadoSistema] = useState("LOADING");

  const volverGlobal = () => {
    setVideoSeleccionado(null);
    setFallaSeleccionada(null);
  };

  const cargarDatos = async () => {
    try {
      const res = await fetch(`${API_URL}/api/v1/detecciones?v=${new Date().getTime()}`);
      if (!res.ok) return;
      const detecciones = await res.json();

      setDeteccionesTotales(detecciones);
      try {
        const resTrayectos = await fetch(`${API_URL}/api/v1/trayectorias?v=${new Date().getTime()}`);
        if (resTrayectos.ok) {
          const trayectoriasReales = await resTrayectos.json();
          setTrayectorias(trayectoriasReales);
        }
      } catch (errTrayectos) {
        console.warn("No se pudo cargar la telemetría:", errTrayectos);
      }

      try {
        const resHealth = await fetch(`${API_URL}/api/v1/health?v=${new Date().getTime()}`);
        if (resHealth.ok) {
          const dataHealth = await resHealth.json();
          setEstadoSistema(dataHealth.estado_general);
        } else {
          setEstadoSistema("ROJO");
        }
      } catch (errHealth) {
        setEstadoSistema("ROJO");
      }

      const idsUnicos = [...new Set(detecciones.filter((d: any) => d.video_id).map((d: any) => d.video_id))];

      setStats({ baches: detecciones.length, videos: idsUnicos.length });

      const videosActualizados = await Promise.all(
        idsUnicos.map(async (id) => {
          try {
            const vRes = await fetch(`${API_URL}/api/v1/videos/${id}`);
            const vData = await vRes.json();
            return { id, estado: vData.estado ? vData.estado.toUpperCase() : "DESCONOCIDO" };
          } catch {
            return { id, estado: "ERROR" };
          }
        })
      );

      setListaVideos(videosActualizados);
    } catch (error) {
      console.error("Error conectando a la API:", error);
    }
  };

  useEffect(() => {
    cargarDatos();
    const intervalo = setInterval(cargarDatos, 15000);
    return () => clearInterval(intervalo);
  }, []);

  return (
    <div className="flex flex-col h-screen overflow-hidden bg-black text-[#e0e0e0] font-sans">

      {/* HEADER */}
      <header className="bg-[#0a0a0a]/90 backdrop-blur-md px-6 flex justify-between items-center border-b border-[#222] h-[70px] shadow-[0_4px_20px_rgba(0,170,255,0.05)] z-10">
        <h1 className="text-2xl text-white flex items-center gap-3 font-bold tracking-wide">
          <i className="fa-solid fa-map-location-dot text-[#00aaff] drop-shadow-[0_0_8px_rgba(0,170,255,0.6)]"></i> PICS Moreno
        </h1>

        <div className="flex items-center gap-4">
          {rol === 'admin' && (
            <a
              href={GRAFANA_URL}
              target="_blank"
              rel="noopener noreferrer"
              className="bg-[#121212] text-[#e0e0e0] border border-[#333] rounded-full px-5 py-2 text-[1.05rem] font-semibold flex items-center gap-2 hover:bg-[#1a1a1a] hover:border-[#00aaff]/50 hover:text-white transition-all no-underline shadow-[0_0_10px_rgba(0,0,0,0.5)]"
            >
              <i className="fa-solid fa-terminal text-[#00aaff] drop-shadow-[0_0_5px_rgba(0,170,255,0.4)]"></i> Ver Logs
            </a>
          )}

          {rol === 'admin' && (
            <Link
              href="/status"
              className="bg-[#121212] px-5 py-2 rounded-full border border-[#333] flex items-center gap-2 text-[1.05rem] font-bold cursor-pointer hover:bg-[#1a1a1a] hover:border-[#00aaff]/50 transition-all no-underline text-white shadow-[0_0_10px_rgba(0,0,0,0.5)]"
            >
              <div className={`w-3.5 h-3.5 rounded-full bg-[#00aaff] shadow-[0_0_8px_#00aaff] ${estadoSistema === 'LOADING' ? 'animate-pulse' : ''}`}></div>
              <span>
                {estadoSistema === 'VERDE' ? 'Sistemas OK' :
                 estadoSistema === 'AMARILLO' ? 'Advertencia' :
                 estadoSistema === 'ROJO' ? 'Falla Crítica' : 'Consultando...'}
              </span>
            </Link>
          )}

          <div className="bg-[#121212] px-5 py-2 rounded-full border border-[#333] flex items-center gap-2 text-[1.05rem] shadow-[0_0_10px_rgba(0,0,0,0.5)]">
            <i className="fa-solid fa-user-tie text-[#00aaff]"></i>
            <span>{rol === 'admin' ? 'Administrador' : 'Operador'}</span>
            <button onClick={onLogout} className="text-gray-400 hover:text-[#ff3d3d] ml-3 transition-colors text-lg" title="Cerrar Sesión">
              <i className="fa-solid fa-right-from-bracket"></i>
            </button>
          </div>
        </div>
      </header>

      {/* LAYOUT PRINCIPAL */}
      <div className="flex flex-1 overflow-hidden relative z-0">

        <aside className="w-[300px] bg-[#0a0a0a]/95 backdrop-blur-md p-5 border-r border-[#222] flex flex-col gap-5 overflow-y-auto z-10 shadow-[4px_0_15px_rgba(0,0,0,0.5)]">

          <div className="bg-[#121212] rounded-xl p-4 text-center border border-[#222] hover:border-[#00aaff]/30 transition-colors">
            <div className="text-4xl font-bold text-[#00aaff] drop-shadow-[0_0_10px_rgba(0,170,255,0.6)]">{stats.baches}</div>
            <div className="text-base text-gray-400 uppercase tracking-widest mt-2 font-semibold">Baches detectados</div>
          </div>
          <div className="bg-[#121212] rounded-xl p-4 text-center border border-[#222] hover:border-[#00aaff]/30 transition-colors">
            <div className="text-4xl font-bold text-[#00aaff] drop-shadow-[0_0_10px_rgba(0,170,255,0.6)]">{stats.videos}</div>
            <div className="text-base text-gray-400 uppercase tracking-widest mt-2 font-semibold">Videos Subidos</div>
          </div>

          <h3 className="text-lg text-[#00aaff] mt-2 uppercase tracking-wide font-bold flex items-center drop-shadow-[0_0_5px_rgba(0,170,255,0.4)]">
            <i className="fa-solid fa-clock-rotate-left mr-2"></i> Historial
          </h3>

          <div className="flex-1 overflow-y-auto flex flex-col gap-3 custom-scrollbar pr-1">
            {listaVideos.length === 0 ? (
              <p className="text-gray-500 text-base italic">Sistema en espera...</p>
            ) : (
              listaVideos.map((vid) => (
                <div
                  key={vid.id}
                  onClick={() => {
                    setVideoSeleccionado(vid.id);
                    setFallaSeleccionada(null);}}
                  className={`bg-[#121212] rounded-lg p-3 border-l-[5px] cursor-pointer transition-all duration-200 text-[1.05rem] flex flex-col gap-1.5 shadow-sm
                    ${videoSeleccionado === vid.id ? 'border-[#00aaff] bg-[#1a1a1a] shadow-[0_0_10px_rgba(0,170,255,0.15)]' : 'border-transparent hover:border-[#00aaff]/50 hover:bg-[#1a1a1a]'}`}
                >
                  <div className="font-bold text-gray-200"><i className="fa-solid fa-film text-[#00aaff] opacity-80 mr-2"></i> Video #{vid.id}</div>
                  <div className={`text-[0.9rem] font-bold w-fit px-3 py-1 rounded-full
                    ${vid.estado === 'PROCESADO' ? 'bg-[#003366]/40 text-[#66ccff] border border-[#0055aa]' :
                      vid.estado === 'PENDIENTE' ? 'bg-[#665000]/40 text-[#ffcc00] border border-[#aa8800]' :
                      'bg-[#004d1a]/40 text-[#3dff7a] border border-[#008833]'}`}>
                    {vid.estado === 'PENDIENTE' ? <i className="fa-solid fa-clock mr-1"></i> : <i className="fa-solid fa-check mr-1"></i>} {vid.estado}
                  </div>
                </div>
              ))
            )}
          </div>

          <div className="mt-auto flex flex-col gap-3 pt-4">
            <button
              onClick={() => { setMetodoModal("GET"); setModalAbierto(true); }}
              disabled={!videoSeleccionado}
              className={`w-full p-4 rounded-xl font-bold text-lg flex justify-center items-center gap-2 transition-all duration-300 ${
                videoSeleccionado
                  ? 'bg-gradient-to-r from-[#00aaff] to-[#0077cc] text-white shadow-[0_0_15px_rgba(0,170,255,0.4)] hover:shadow-[0_0_25px_rgba(0,170,255,0.6)] border-none cursor-pointer'
                  : 'bg-[#121212] text-gray-600 border border-[#222] cursor-not-allowed'
              }`}
            >
              <i className="fa-solid fa-file-lines"></i> Ver Reporte
            </button>

            <button
              onClick={() => { setMetodoModal("POST"); setModalAbierto(true); }}
              disabled={!videoSeleccionado}
              className={`w-full border p-4 rounded-xl font-bold text-lg flex justify-center items-center gap-2 transition-all duration-300 ${
                videoSeleccionado
                  ? 'bg-[#0a0a0a] border-[#00aaff] text-[#00aaff] shadow-[0_0_10px_rgba(0,170,255,0.2)] hover:bg-[#121212] hover:shadow-[0_0_20px_rgba(0,170,255,0.4)] cursor-pointer'
                  : 'bg-[#0a0a0a] border-[#222] text-gray-600 cursor-not-allowed'
              }`}
            >
              <i className="fa-solid fa-robot"></i> Generar Reporte IA
            </button>
          </div>
        </aside>

        {/* CONTENIDO CENTRAL */}
        <main className="flex-1 grid grid-cols-3 grid-rows-3 gap-5 p-5 bg-black">

           {/* MAPA */}
           <div className="col-span-2 row-span-2 bg-[#0a0a0a] border border-[#222] hover:border-[#00aaff]/30 transition-colors rounded-xl flex items-center justify-center flex-col relative overflow-hidden shadow-[0_8px_30px_rgb(0,0,0,0.6)]">
             <MapaVial
               detecciones={deteccionesTotales}
               trayectorias={trayectorias}
               onSeleccionarVideo={setVideoSeleccionado}
               onSeleccionarFalla={setFallaSeleccionada}
             />
           </div>

           {/* FOTO */}
           <div className="col-span-1 row-span-2 bg-[#0a0a0a] border border-[#222] hover:border-[#00aaff]/30 transition-colors rounded-xl p-5 flex flex-col text-gray-300 overflow-hidden shadow-[0_8px_30px_rgb(0,0,0,0.6)]">
             <div className="font-bold text-[#00aaff] border-b border-[#222] text-2xl pb-4 mb-5 flex justify-between items-center drop-shadow-[0_0_5px_rgba(0,170,255,0.3)]">
                <span><i className="fa-solid fa-magnifying-glass-location mr-2"></i> Inspección Técnica</span>
                {videoSeleccionado && <span className="bg-[#121212] text-white text-base px-3 py-1.5 rounded-lg border border-[#333]">Video #{videoSeleccionado}</span>}
             </div>

             <FotoDeteccion
               videoSeleccionado={videoSeleccionado}
               falla={fallaSeleccionada}
               onAuditoriaCompletada={() => {
                 cargarDatos();
                 setFallaSeleccionada(null);
               }}
             />
           </div>

           {/* KEDA */}
           <div className="col-span-2 row-span-1 bg-[#0a0a0a] border border-[#222] hover:border-[#00aaff]/30 transition-colors rounded-xl p-5 flex flex-col text-gray-300 overflow-y-auto shadow-[0_8px_30px_rgb(0,0,0,0.6)] custom-scrollbar">
             <div className="font-bold text-[#00aaff] border-b border-[#222] text-xl pb-3 mb-4 flex items-center gap-2 drop-shadow-[0_0_5px_rgba(0,170,255,0.3)]">
                <i className="fa-solid fa-stopwatch mr-1"></i> Estado del Sistema KEDA
             </div>
             <div className="flex flex-col gap-3">
                {listaVideos.length === 0 ? <p className="text-[1.05rem] italic text-gray-600">En espera de procesamiento de video...</p> : (
                  listaVideos.map(vid => (
                    <div key={`cola-${vid.id}`} className="bg-[#121212] p-3.5 rounded-lg border border-[#222] flex justify-between items-center text-[1.05rem] shadow-sm hover:bg-[#1a1a1a] transition-colors">
                      <strong className="text-gray-300"><i className="fa-solid fa-film text-[#00aaff]/70 mr-3"></i>Video #{vid.id}</strong>
                      <span className={`font-bold tracking-wide ${vid.estado === 'PROCESADO' ? 'text-[#00aaff] drop-shadow-[0_0_5px_rgba(0,170,255,0.5)]' : 'text-[#ffcc00] drop-shadow-[0_0_5px_rgba(255,204,0,0.5)]'}`}>
                        {vid.estado}
                      </span>
                    </div>
                  ))
                )}
             </div>
           </div>

           {/* CHAT */}
           <div className="col-span-1 row-span-1 shadow-[0_8px_30px_rgb(0,0,0,0.6)] rounded-xl transition-colors hover:border-[#00aaff]/30">
             <ChatIA
                videoSeleccionado={videoSeleccionado}
                onVolverGlobal={volverGlobal}
             />
           </div>

        </main>
      </div>

      <ModalReporte
        isOpen={modalAbierto}
        onClose={() => setModalAbierto(false)}
        videoSeleccionado={videoSeleccionado}
        metodo={metodoModal}
      />
    </div>
  );
}
