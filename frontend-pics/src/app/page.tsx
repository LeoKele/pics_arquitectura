"use client";
import { useState, useEffect } from "react";
import Login from "@/components/Login";
import Dashboard from "@/components/Dashboard";

export default function Home() {
  // TS: Le decimos que rol puede ser un string o null
  const [rol, setRol] = useState<string | null>(null);
  const [cargando, setCargando] = useState<boolean>(true);

  useEffect(() => {
    const rolGuardado = localStorage.getItem("pics_rol");
    if (rolGuardado) {
      setRol(rolGuardado);
    }
    setCargando(false);
  }, []);

  if (cargando) {
    return <div className="h-screen bg-black flex items-center justify-center text-[#00aaff] text-xl">Cargando sistema...</div>;
  }

  if (!rol) {
    return <Login onLoginSuccess={(nuevoRol) => setRol(nuevoRol)} />;
  }

  return (
    <Dashboard
      rol={rol}
      onLogout={() => {
        localStorage.removeItem("pics_rol");
        localStorage.removeItem("pics_token");
        setRol(null);
      }}
    />
  );
}
