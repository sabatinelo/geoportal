import asyncio
from pathlib import Path

import uvicorn
import yaml
from apify import Actor
from fastmcp import FastMCP

import catastro_client
import geometry_utils
import wms_client

mcp = FastMCP("geoportal-mapama")
CAPAS_FILE = Path(__file__).parent / "capas.yaml"


def _cargar_capas() -> dict:
    return yaml.safe_load(CAPAS_FILE.read_text())["capas"]


@mcp.tool()
def listar_capas_registradas() -> dict:
    """Lista las capas que tienes configuradas en capas.yaml, con nombre y clave."""
    capas = _cargar_capas()
    return {k: v["nombre"] for k, v in capas.items()}


@mcp.tool()
async def descubrir_layers(servicio_url: str, version: str = "1.1.1") -> list[dict]:
    """
    Consulta el GetCapabilities de un servicio WMS y devuelve todos los
    nombres de capa (Name) disponibles con su título. Úsalo para saber qué
    poner en el campo 'layer' de capas.yaml antes de registrar una capa nueva.
    """
    xml_text = await wms_client.get_capabilities(servicio_url, version)
    return wms_client.listar_layers_desde_xml(xml_text)


@mcp.tool()
async def anadir_capa(
    clave: str,
    nombre: str,
    servicio_url: str,
    layer: str,
    version: str = "1.1.1",
    info_format: str = "application/json",
) -> dict:
    """
    Añade una nueva capa al registro capas.yaml.

    NOTA: en Apify el sistema de archivos es efímero. La capa estará
    disponible mientras la instancia siga viva, pero para hacerla permanente
    hay que añadirla al capas.yaml del repositorio y reconstruir el Actor.
    """
    capas = _cargar_capas()
    capas[clave] = {
        "nombre": nombre,
        "servicio": servicio_url,
        "layer": layer,
        "version": version,
        "info_format": info_format,
    }
    CAPAS_FILE.write_text(yaml.dump({"capas": capas}, allow_unicode=True))
    return {
        "ok": True,
        "clave": clave,
        "aviso": "Capa temporal: para hacerla permanente, añádela a capas.yaml en el repositorio.",
    }


@mcp.tool()
async def parcela_afectada_por_capa(refcat: str, clave_capa: str) -> dict:
    """
    Comprueba si una parcela catastral (por referencia catastral) está
    afectada por una capa registrada en capas.yaml.

    refcat: referencia catastral (14 o 20 dígitos)
    clave_capa: clave definida en capas.yaml (ver listar_capas_registradas)
    """
    capas = _cargar_capas()
    if clave_capa not in capas:
        return {"error": f"Capa '{clave_capa}' no registrada. Usa listar_capas_registradas."}
    capa = capas[clave_capa]

    geo = await catastro_client.geometria_parcela(refcat)
    if not geo.get("features"):
        return {"error": "No se pudo obtener la geometría de la parcela."}
    geometria = geo["features"][0]["geometry"]

    puntos = geometry_utils.puntos_de_muestreo(geometria)
    resultados = []
    for lon, lat in puntos:
        info = await wms_client.get_feature_info(
            capa["servicio"], capa["layer"], lon, lat,
            capa["version"], capa["info_format"],
        )
        resultados.append({"punto": [lon, lat], "resultado": info})

    afectada = geometry_utils.parcela_intersecta(resultados)
    return {
        "refcat": refcat,
        "capa": capa["nombre"],
        "afectada": afectada,
        "puntos_muestreados": len(puntos),
        "detalle": resultados,
    }


@mcp.tool()
async def parcelas_afectadas_por_capa(refcats: list[str], clave_capa: str) -> dict:
    """Igual que parcela_afectada_por_capa pero para una lista de referencias catastrales."""
    out = {}
    for rc in refcats:
        out[rc] = await parcela_afectada_por_capa(rc, clave_capa)
    return out


async def main() -> None:
    async with Actor:
        # Exponemos el servidor MCP sobre Streamable HTTP en el puerto del Actor.
        app = mcp.http_app(transport="streamable-http")
        config = uvicorn.Config(
            app,
            host="0.0.0.0",  # noqa: S104
            port=Actor.configuration.web_server_port,
        )
        web_server = uvicorn.Server(config)
        Actor.log.info(
            f"Servidor MCP disponible en {Actor.configuration.web_server_url}/mcp"
        )
        # Sirve hasta que la plataforma apague el Actor (Standby gestiona el ciclo de vida).
        await web_server.serve()


if __name__ == "__main__":
    asyncio.run(main())
