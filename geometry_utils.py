from shapely.geometry import shape


def puntos_de_muestreo(geojson_geom: dict, n_extra: int = 8) -> list[tuple[float, float]]:
    """Centroide + punto interior garantizado + puntos distribuidos por el contorno."""
    geom = shape(geojson_geom)
    puntos = [geom.centroid.coords[0]]

    # representative_point() garantiza un punto DENTRO del polígono
    puntos.append(geom.representative_point().coords[0])

    coords = list(geom.exterior.coords)
    paso = max(1, len(coords) // n_extra)
    for i in range(0, len(coords), paso):
        puntos.append(coords[i])

    return puntos


def parcela_intersecta(resultados: list[dict]) -> bool:
    """True si algún punto muestreado devolvió features en la capa."""
    for r in resultados:
        features = r.get("resultado", {}).get("features", [])
        if features:
            return True
    return False
