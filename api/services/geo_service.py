import logging

import httpx

logger = logging.getLogger("api.geo_service")

_cache_osm_contexto = {}
_cache_osm_nombres = {}


async def obtener_nombre_calle(lat: float, lng: float):
    clave_nombre = f"{round(lat, 3)}_{round(lng, 3)}"
    if clave_nombre in _cache_osm_nombres:
        return _cache_osm_nombres[clave_nombre]

    headers = {"User-Agent": "PICS-UNLu-Research-Project/1.0 (contacto@unlu.edu.ar)"}

    async with httpx.AsyncClient(timeout=30.0, headers=headers) as client:
        try:
            res = await client.get(
                f"https://photon.komoot.io/reverse?lon={lng}&lat={lat}"
            )
            if res.status_code == 200:
                features = res.json().get("features", [])
                if features:
                    props = features[0].get("properties", {})
                    calle = props.get("name") or props.get("street")
                    if calle:
                        _cache_osm_nombres[clave_nombre] = calle
                        return calle
        except Exception as e:
            logger.warning(f"Photon falló: {e}")

        try:
            res = await client.get(
                f"https://nominatim.openstreetmap.org/reverse?format=json&lat={lat}&lon={lng}"
            )
            if res.status_code == 200:
                data = res.json()
                calle = data.get("address", {}).get("road")
                if calle:
                    _cache_osm_nombres[clave_nombre] = calle
                    return calle
        except Exception:
            pass

    return "Calle sin identificar"


async def obtener_contexto_geografico(lat: float, lng: float, radio_pois: int = 400):
    clave_zona = f"{round(lat, 3)}_{round(lng, 3)}"
    if clave_zona in _cache_osm_contexto:
        return _cache_osm_contexto[clave_zona]

    calle_base = await obtener_nombre_calle(lat, lng)

    query = f"""[out:json][timeout:30];
    (
      nwr(around:{radio_pois}, {lat}, {lng})["amenity"~"hospital|school|fire_station|police|clinic|pharmacy"];
    );
    out center;"""

    headers = {"User-Agent": "PICS-UNLu-Research-Project/1.0 (contacto@unlu.edu.ar)"}
    pois_encontrados = []

    async with httpx.AsyncClient(timeout=30.0, headers=headers) as client:
        try:
            res = await client.post(
                "https://overpass-api.de/api/interpreter", data={"data": query}
            )
            if res.status_code == 200:
                data = res.json()
                for elem in data.get("elements", []):
                    tags = elem.get("tags", {})
                    tipo = tags.get("amenity")
                    nombre = tags.get("name", "")

                    traduccion = {
                        "hospital": "Hospital",
                        "school": "Escuela",
                        "fire_station": "Bomberos",
                        "police": "Policía",
                        "clinic": "Centro de Salud",
                        "pharmacy": "Farmacia",
                    }

                    if tipo in traduccion:
                        label = f"{traduccion[tipo]} {f'({nombre})' if nombre else ''}".strip()
                        if label not in pois_encontrados:
                            pois_encontrados.append(label)
        except Exception as e:
            logger.warning(f"Búsqueda de POIs falló en la nube: {e}")

    contexto = {
        "calle": calle_base,
        "tipo_calle": "Vía urbana",
        "calles_cruzadas": [],
        "pois_cercanos": pois_encontrados[:3],
        "resumen_contexto": calle_base,
    }

    _cache_osm_contexto[clave_zona] = contexto
    return contexto
