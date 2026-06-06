"use client";
import { useState } from "react";

// NUEVO: Definimos qué propiedades espera recibir este componente
interface LoginProps {
  onLoginSuccess: (rol: string) => void;
}

export default function Login({ onLoginSuccess }: LoginProps) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState(false);

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();

    const userLimpio = username.trim().toLowerCase();
    const passLimpia = password.trim();

    try {
      const res = await fetch("http://34.63.158.31:8000/api/v1/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username: userLimpio, password: passLimpia }),
      });

      if (!res.ok) throw new Error("Credenciales inválidas");
      const data = await res.json();

      localStorage.setItem("pics_token", data.access_token);
      localStorage.setItem("pics_rol", data.rol);

      onLoginSuccess(data.rol);
    } catch (err) {
      console.error("Error en login:", err);
      setError(true);
    }
  };

  return (
    <div className="fixed inset-0 bg-black z-50 flex flex-col justify-center items-center">
      <form
        onSubmit={handleLogin}
        className="bg-[#0a0a0a] p-10 rounded-xl border border-[#00aaff] w-[350px] text-center shadow-[0_10px_30px_rgba(0,170,255,0.15)]"
      >
        <h2 className="text-[#00aaff] mb-5 text-2xl font-bold">
          <i className="fa-solid fa-map-location-dot mr-2"></i> PICS Moreno
        </h2>

        <input
          type="text"
          placeholder="Usuario"
          value={username}
          onChange={(e) => setUsername(e.target.value)}
          className="w-full p-3 mb-4 rounded-lg border border-[#222] bg-[#121212] text-white outline-none focus:border-[#00aaff]"
        />

        <input
          type="password"
          placeholder="Contraseña"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          className="w-full p-3 mb-4 rounded-lg border border-[#222] bg-[#121212] text-white outline-none focus:border-[#00aaff]"
        />

        <button
          type="submit"
          className="w-full p-3 rounded-lg border-none bg-[#00aaff] text-white font-bold cursor-pointer text-base transition-colors duration-200 hover:bg-[#0088cc]"
        >
          Ingresar
        </button>

        {error && (
          <div className="text-[#ff3d3d] text-base mt-3">
            <i className="fa-solid fa-triangle-exclamation mr-1"></i> Usuario o contraseña incorrectos.
          </div>
        )}
      </form>
    </div>
  );
}
