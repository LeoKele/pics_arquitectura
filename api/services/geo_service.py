import asyncio
import logging
import math

import httpx

logger = logging.getLogger("api.geo_service")

# Lista de instancias de Overpass para fallback
OVERPASS_URLS = [
    "https://overpass-api.de/api/interpreter",        
    "https://lz4.overpass-api.de/api/interpreter",    
    "https://z.overpass-api.de/api/interpreter",      
    "https://maps.mail.ru/osm/tools/overpass/api/interpreter" 
]


def haversine(lat1, lon1, lat2, lon2):
    """Calcula la distancia en metros entre dos puntos."""
    R = 6371000
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = (
        math.sin(dphi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    )
    return 2 * R * math.atan2(math.sqrt(a), math.sqrt(1 - a))


async def obtener_nombre_calle(lat: float, lng: float):
    """
    Versión simplificada que solo busca el nombre de la calle.
    Útil para determinar el rango de un video (inicio/fin).
    """
    query = f"""[out:json][timeout:10];
    way(around:50, {lat}, {lng})[highway];
    out tags;"""

    headers = {"User-Agent": "PICS-App-Moreno/1.1"}
    async with httpx.AsyncClient() as client:
        for url in OVERPASS_URLS:
            try:
                response = await client.post(
                    url, data={"data": query}, headers=headers, timeout=10.0
                )
                if response.status_code == 200:
                    data = response.json()
                    # Buscar la primera vía con nombre
                    for elem in data.get("elements", []):
                        name = elem.get("tags", {}).get("name")
                        if name:
                            return name
                    # Si no hay nombres, devolver el tipo de vía más relevante
                    if data.get("elements"):
                        return (
                            data["elements"][0]
                            .get("tags", {})
                            .get("highway", "Calle desconocida")
                        )
            except Exception:
                continue
    return "Calle desconocida"


async def obtener_contexto_geografico(lat: float, lng: float, radio_pois: int = 400):
    """
    Consulta a OpenStreetMap via Overpass API para obtener:
    1. El nombre y tipo de la calle más cercana (radio 100m).
    2. Puntos de interés cercanos (radio configurable).
    """
    await asyncio.sleep(0.2)

    query = f"""[out:json][timeout:15];
(
  way(around:100, {lat}, {lng})[highway];
  nwr(around:{radio_pois}, {lat}, {lng})["amenity"~"hospital|school|fire_station|police|clinic|pharmacy"];
  nwr(around:{radio_pois}, {lat}, {lng})["public_transport"~"stop|platform"];
);
out center;"""

    headers = {
        "User-Agent": "PICS-App-Moreno/1.1",
        "Accept": "application/json",
    }

    async with httpx.AsyncClient() as client:
        for url in OVERPASS_URLS:
            try:
                response = await client.post(
                    url, data={"data": query}, headers=headers, timeout=15.0
                )
                response.raise_for_status()
                data = response.json()

                elementos = data.get("elements", [])
                if elementos:
                    return parsear_respuesta_osm(data, lat, lng)
            except Exception as e:
                logger.warning(f"OSM Error en {url}: {str(e)}")
                continue

    return error_fallback("Información no disponible")


def error_fallback(mensaje_resumen):
    return {
        "calle": "Ubicación desconocida",
        "tipo_calle": "no especificado",
        "pois_cercanos": [],
        "resumen_contexto": mensaje_resumen,
    }


def parsear_respuesta_osm(data, lat_ref, lng_ref):
    elementos = data.get("elements", [])
    calles_encontradas = []
    pois = []

    highway_map = {
        "motorway": "Autopista",
        "trunk": "Ruta principal",
        "primary": "Avenida principal",
        "secondary": "Avenida secundaria",
        "tertiary": "Calle conectora",
        "residential": "Calle residencial",
        "service": "Calle de servicio",
        "living_street": "Calle de convivencia",
        "pedestrian": "Peatonal",
    }

    categoria_map = {
        "hospital": "Hospital",
        "school": "Escuela",
        "fire_station": "Bomberos",
        "police": "Policía",
        "clinic": "Centro de Salud",
        "pharmacy": "Farmacia",
        "bus_stop": "Parada de Colectivo",
    }

    for elem in elementos:
        tags = elem.get("tags", {})
        e_lat = elem.get("lat") or (
            elem.get("center", {}).get("lat") if elem.get("center") else None
        )
        e_lng = elem.get("lon") or (
            elem.get("center", {}).get("lng") if elem.get("center") else None
        )
        distancia = (
            haversine(lat_ref, lng_ref, e_lat, e_lng) if (e_lat and e_lng) else 9999
        )

        if elem.get("type") == "way" and "highway" in tags:
            nombre = tags.get("name")
            tipo = highway_map.get(tags.get("highway"), tags.get("highway"))
            calles_encontradas.append(
                {
                    "nombre": nombre or "Calle sin nombre",
                    "tipo": tipo,
                    "distancia": distancia,
                    "tiene_nombre": 1 if nombre else 0,
                }
            )

        tipo_poi = (
            tags.get("amenity") or tags.get("shop") or tags.get("public_transport")
        )
        if tipo_poi:
            nombre_poi = tags.get("name")
            label = categoria_map.get(tipo_poi)
            if not label and (tags.get("public_transport") in ["stop", "platform"]):
                label = "Parada de Colectivo"

            if label:
                poi_text = f"{label} {f'({nombre_poi})' if nombre_poi else ''}".strip()
                pois.append({"label": poi_text, "distancia": distancia})

    calles_encontradas.sort(key=lambda x: (-x["tiene_nombre"], x["distancia"]))
    calle_nombre = (
        calles_encontradas[0]["nombre"] if calles_encontradas else "Calle sin nombre"
    )
    tipo_calle = (
        calles_encontradas[0]["tipo"] if calles_encontradas else "no especificado"
    )

    # Identificar calles cruzadas (intersecciones potenciales)
    calles_cruzadas = []
    for c in calles_encontradas:
        if c["nombre"] != calle_nombre and c["nombre"] != "Calle sin nombre":
            if c["nombre"] not in calles_cruzadas:
                calles_cruzadas.append(c["nombre"])

    pois.sort(key=lambda x: x["distancia"])
    pois_labels = []
    vistos = set()
    for p in pois:
        if p["label"] not in vistos:
            pois_labels.append(p["label"])
            vistos.add(p["label"])
            if len(pois_labels) >= 3:
                break

    return {
        "calle": calle_nombre,
        "tipo_calle": tipo_calle,
        "calles_cruzadas": calles_cruzadas[
            :2
        ],  # Solo las 2 más cercanas para "entre calles"
        "pois_cercanos": pois_labels,
        "resumen_contexto": f"{calle_nombre} ({tipo_calle})",
    }
