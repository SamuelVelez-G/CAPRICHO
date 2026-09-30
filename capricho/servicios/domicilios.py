"""
Domicilios con grafos (trabajo 2, ahora aplicado a Capricho).

La tienda está en Aranjuez (Cra. 50c # 92-84, Medellín). Cada barrio es un
nodo y cada vía una arista con su distancia aproximada en km. Dijkstra
encuentra la ruta más corta y con ella se calcula la tarifa del domicilio.

Las distancias son aproximadas para la demostración.
"""

import math

from ..estructuras import Grafo

TIENDA = "Aranjuez"

# Posición en el mapa esquemático (x, y en una caja de 1000 x 700).
BARRIOS = {
    "Bello":            (330, 40),
    "Santa Cruz":       (560, 120),
    "Popular":          (760, 90),
    "Castilla":         (250, 200),
    "Aranjuez":         (560, 250),
    "Manrique":         (760, 250),
    "Moravia":          (420, 290),
    "Campo Valdés":     (650, 330),
    "Robledo":          (90, 330),
    "Prado":            (560, 400),
    "Villa Hermosa":    (800, 400),
    "Estadio":          (260, 430),
    "La Candelaria":    (500, 490),
    "Boston":           (660, 470),
    "Laureles":         (220, 540),
    "Buenos Aires":     (760, 540),
    "Belén":            (230, 650),
    "El Poblado":       (620, 640),
}

VIAS = [
    ("Aranjuez", "Santa Cruz", 2.1), ("Aranjuez", "Manrique", 1.6),
    ("Aranjuez", "Campo Valdés", 1.3), ("Aranjuez", "Moravia", 1.9),
    ("Santa Cruz", "Popular", 1.5), ("Santa Cruz", "Bello", 4.6),
    ("Popular", "Manrique", 2.2), ("Manrique", "Villa Hermosa", 2.8),
    ("Manrique", "Campo Valdés", 1.4), ("Campo Valdés", "Moravia", 1.2),
    ("Campo Valdés", "Prado", 1.6), ("Moravia", "Castilla", 2.4),
    ("Moravia", "Prado", 2.3), ("Castilla", "Bello", 4.2),
    ("Castilla", "Robledo", 3.5), ("Castilla", "Estadio", 3.9),
    ("Prado", "La Candelaria", 1.5), ("Prado", "Boston", 1.8),
    ("Villa Hermosa", "Boston", 1.9), ("Villa Hermosa", "Buenos Aires", 2.0),
    ("Boston", "La Candelaria", 1.2), ("Boston", "Buenos Aires", 1.6),
    ("La Candelaria", "Estadio", 3.2), ("La Candelaria", "El Poblado", 4.2),
    ("Estadio", "Laureles", 1.5), ("Robledo", "Laureles", 3.0),
    ("Laureles", "Belén", 3.0), ("Buenos Aires", "El Poblado", 4.8),
    ("Belén", "El Poblado", 5.2),
]

TARIFA_BASE = 2_000          # pesos
TARIFA_POR_KM = 700          # pesos por km de la ruta
RENDIMIENTO_KM_GALON = 100   # moto de domicilios
PRECIO_GALON = 16_000        # pesos

grafo = Grafo()
for _nombre in BARRIOS:
    grafo.agregar_nodo(_nombre)
for _origen, _destino, _km in VIAS:
    grafo.agregar_arista(_origen, _destino, _km)


def tarifa_para(km: float) -> int:
    """Tarifa base + valor por km, redondeada a la centena de arriba."""
    # El round evita que un error de coma flotante (4100.0000001) suba otra centena.
    return int(math.ceil(round((TARIFA_BASE + TARIFA_POR_KM * km) / 100, 6)) * 100)


def cotizar(barrio: str) -> dict | None:
    ruta, km, visitados = grafo.dijkstra(TIENDA, barrio)
    if ruta is None:
        return None
    ida_y_vuelta = km * 2
    galones = ida_y_vuelta / RENDIMIENTO_KM_GALON
    return {
        "barrio": barrio,
        "ruta": ruta,
        "distancia_km": km,
        "tarifa": tarifa_para(km),
        "nodos_visitados": visitados,
        "galones_ida_y_vuelta": round(galones, 3),
        "costo_gasolina": round(galones * PRECIO_GALON),
    }


def mapa() -> dict:
    nodos = []
    for nombre, (x, y) in BARRIOS.items():
        cotizacion = cotizar(nombre)
        nodos.append({"nombre": nombre, "x": x, "y": y, "tarifa": cotizacion["tarifa"],
                      "distancia_km": cotizacion["distancia_km"]})
    return {
        "tienda": TIENDA,
        "nodos": nodos,
        "aristas": [{"origen": a, "destino": b, "km": km} for a, b, km in grafo.aristas()],
        "tarifa_base": TARIFA_BASE,
        "tarifa_por_km": TARIFA_POR_KM,
    }
