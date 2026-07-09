import ssl
import httpx
import certifi
import xml.etree.ElementTree as ET

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; GeoportalMCP/1.0)"}

# El servidor wms.mapama.gob.es no envía el certificado intermedio
# "AC Componentes Informáticos" (FNMT-RCM) durante el handshake TLS.
# Lo descargamos una vez (por HTTP plano, sin necesidad de verificación
# SSL) y lo añadimos al contexto de confianza junto al bundle de certifi.
_ACCOMP_URL = "http://www.cert.fnmt.es/certs/ACCOMP.crt"


def _build_ssl_context() -> ssl.SSLContext:
    ctx = ssl.create_default_context(cafile=certifi.where())
    try:
        with httpx.Client(timeout=10) as c:
            der_bytes = c.get(_ACCOMP_URL).content
        ctx.load_verify_locations(cadata=der_bytes)
    except Exception:
        # Si falla la descarga del intermedio, seguimos solo con certifi
        # (puede que vuelva a fallar el SSL, pero no bloqueamos el arranque)
        pass
    return ctx


SSL_CONTEXT = _build_ssl_context()


async def get_capabilities(servicio_url: str, version: str = "1.3.0") -> str:
    params = {"service": "WMS", "version": version, "request": "GetCapabilities"}
    async with httpx.AsyncClient(timeout=30, headers=HEADERS, verify=SSL_CONTEXT, follow_redirects=True) as client:
        r = await client.get(servicio_url, params=params)
        r.raise_for_status()
        return r.text


def listar_layers_desde_xml(xml_text: str) -> list[dict]:
    root = ET.fromstring(xml_text)
    layers = []
    for layer in root.iter():
        tag = layer.tag.split("}")[-1]
        if tag == "Layer":
            name_el = layer.find("./{*}Name")
            title_el = layer.find("./{*}Title")
            if name_el is not None:
                layers.append({
                    "name": name_el.text,
                    "title": title_el.text if title_el is not None else None,
                })
    return layers


async def get_feature_info(
    servicio_url: str,
    layer: str,
    lon: float,
    lat: float,
    version: str = "1.3.0",
    info_format: str = "application/json",
    buffer_deg: float = 0.0002,
) -> dict:
    if version == "1.3.0":
        bbox = f"{lat-buffer_deg},{lon-buffer_deg},{lat+buffer_deg},{lon+buffer_deg}"
        crs_param_name = "crs"
        crs_value = "EPSG:4326"
    else:
        bbox = f"{lon-buffer_deg},{lat-buffer_deg},{lon+buffer_deg},{lat+buffer_deg}"
        crs_param_name = "srs"
        crs_value = "EPSG:4326"

    params = {
        "service": "WMS",
        "version": version,
        "request": "GetFeatureInfo",
        "layers": layer,
        "query_layers": layer,
        "styles": "",
        crs_param_name: crs_value,
        "bbox": bbox,
        "width": 101,
        "height": 101,
        "i": 50,
        "j": 50,
        "x": 50,
        "y": 50,
        "info_format": info_format,
        "feature_count": 5,
    }
    async with httpx.AsyncClient(timeout=30, headers=HEADERS, verify=SSL_CONTEXT, follow_redirects=True) as client:
        r = await client.get(servicio_url, params=params)
        r.raise_for_status()
        try:
            return r.json()
        except ValueError:
            return {"raw": r.text, "content_type": r.headers.get("content-type")}
