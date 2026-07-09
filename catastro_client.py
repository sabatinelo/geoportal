import httpx
import xml.etree.ElementTree as ET

WFS_CP = "http://ovc.catastro.meh.es/INSPIRE/wfsCP.aspx"


async def _obtener_gml(refcat: str) -> str:
    params = {
        "service": "WFS",
        "version": "2.0.0",
        "request": "GetFeature",
        "STOREDQUERIE_ID": "GetParcel",
        "REFCAT": refcat[:14],
        "SRSNAME": "EPSG:4326",
    }
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.get(WFS_CP, params=params)
        r.raise_for_status()
        return r.text


def _gml_a_geojson(gml_text: str) -> dict:
    """
    Convierte el GML del WFS de Catastro (cp:CadastralParcel) a un dict
    GeoJSON-like con la geometría en lon/lat (estándar GeoJSON).

    IMPORTANTE: en GML, EPSG:4326 usa orden lat,lon (eje oficial), así que
    hay que invertir cada par para obtener lon,lat.
    """
    root = ET.fromstring(gml_text)

    pos_list_el = None
    for el in root.iter():
        tag = el.tag.split("}")[-1]
        if tag == "posList":
            pos_list_el = el
            break

    if pos_list_el is None or not pos_list_el.text:
        return {"features": []}

    valores = [float(v) for v in pos_list_el.text.split()]
    pares = list(zip(valores[0::2], valores[1::2]))  # (lat, lon)
    coords_lonlat = [[lon, lat] for lat, lon in pares]

    return {
        "features": [
            {
                "type": "Feature",
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [coords_lonlat],
                },
            }
        ]
    }


async def geometria_parcela(refcat: str) -> dict:
    """Devuelve GeoJSON (lon/lat) de la parcela a partir de la RC (14 dígitos)."""
    gml_text = await _obtener_gml(refcat)
    return _gml_a_geojson(gml_text)
