"use client";
import { useState, useEffect } from "react";
import { MapContainer, TileLayer, Marker, Popup, Polyline, GeoJSON } from "react-leaflet";
import L from "leaflet";
import "leaflet/dist/leaflet.css";

const iconoBache = new L.DivIcon({
  className: "",
  html: `<div style="width: 22px; height: 22px; background: #0055aa; border: 2px solid black; border-radius: 50%; box-shadow: 0 0 8px rgba(0,85,170,0.9);"></div>`,
  iconSize: [22, 22],
  iconAnchor: [11, 11],
});

export default function MapaVial({ detecciones, trayectorias = {}, onSeleccionarVideo, onSeleccionarFalla }: any) {
  const [limitesMoreno, setLimitesMoreno] = useState<any>(null);

  useEffect(() => {
    const obtenerLimites = async () => {
      try {
        const res = await fetch("https://nominatim.openstreetmap.org/search.php?q=Partido+de+Moreno,+Buenos+Aires,+Argentina&polygon_geojson=1&format=json");
        const data = await res.json();

        if (data && data.length > 0) {
          setLimitesMoreno(data[0].geojson);
        }
      } catch (error) {
        console.error("Error al cargar los límites de Moreno:", error);
      }
    };

    obtenerLimites();
  }, []);

  return (
    <MapContainer
      center={[-34.6441, -58.7894]}
      zoom={12}
      style={{ height: "100%", width: "100%", zIndex: 0 }}
    >
      <TileLayer
        attribution='&copy; OpenStreetMap contributors'
        url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        className="dark-map-tiles"
      />

      {limitesMoreno && (
        <GeoJSON
          data={limitesMoreno}
          style={{
            color: '#00aaff',
            weight: 3,
            opacity: 0.9,
            fillColor: '#00aaff',
            fillOpacity: 0.05,
            dashArray: '5, 10'
          }}
        />
      )}

      {detecciones.map((d: any) => {
        if (!d.geometria || !d.geometria.coordinates) return null;
        const lon = d.geometria.coordinates[0];
        const lat = d.geometria.coordinates[1];

        return (
          <Marker
            key={d.id}
            position={[lat, lon]}
            icon={iconoBache}
            eventHandlers={{
              click: () => {
                onSeleccionarVideo(d.video_id);
                if (onSeleccionarFalla) onSeleccionarFalla(d);
              }
            }}
          >
            <Popup>
              <div className="text-gray-200 text-base w-[150px]">
                <strong><i className="fa-solid fa-road-circle-exclamation text-[#00aaff]"></i> Bache Detectado</strong><br/>
                Confianza: {(d.confianza * 100).toFixed(0)}%<br/>
                Video Origen: #{d.video_id}
              </div>
            </Popup>
          </Marker>
        );
      })}

      {Object.keys(trayectorias).map((vidId) => {
        const puntosDeRuta = trayectorias[vidId] as any[];
        if (puntosDeRuta && puntosDeRuta.length > 1) {
          return (
            <Polyline
              key={`trayecto-${vidId}`}
              positions={puntosDeRuta}
              pathOptions={{
                color: '#33ccff',
                weight: 2,
                opacity: 0.8,
                dashArray: '10, 10',
                lineJoin: 'round'
              }}
            />
          );
        }
        return null;
      })}

    </MapContainer>
  );
}
