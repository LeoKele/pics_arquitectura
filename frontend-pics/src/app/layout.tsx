import "./globals.css";
import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Mapeo Vial Moreno",
  description: "Plataforma de Inspección Inteligente",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="es">
      <head>
        <link
          rel="stylesheet"
          href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css"
        />
      </head>
      <body
        className="bg-black text-[#e0e0e0] min-h-screen"
        suppressHydrationWarning
      >
        {children}
      </body>
    </html>
  );
}
