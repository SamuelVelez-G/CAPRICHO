from dataclasses import dataclass
from typing import Generic, TypeVar, Optional

T = TypeVar("T")

class Cola(Generic[T]):
    """Cola FIFO: el primero que entra es el primero que sale."""
    def __init__(self):
        self._elementos = []

    def encolar(self, elemento: T):
        self._elementos.append(elemento)

    def desencolar(self) -> Optional[T]:
        if self.esta_vacia():
            return None
        return self._elementos.pop(0)

    def esta_vacia(self) -> bool:
        return len(self._elementos) == 0

    def __len__(self):
        return len(self._elementos)

    def ver(self):
        return self._elementos[0] if self._elementos else None

    def elementos(self):
        return list(self._elementos)


class Pila(Generic[T]):
    """Pila LIFO: el último que entra es el primero que sale."""
    def __init__(self):
        self._elementos = []

    def apilar(self, elemento: T):
        self._elementos.append(elemento)

    def desapilar(self) -> Optional[T]:
        if self.esta_vacia():
            return None
        return self._elementos.pop()

    def esta_vacia(self) -> bool:
        return len(self._elementos) == 0

    def __len__(self):
        return len(self._elementos)

    def cima(self):
        return self._elementos[-1] if self._elementos else None

    def elementos(self):
        return list(reversed(self._elementos))


class Grafo:
    """Grafo ponderado no dirigido y algoritmo de Dijkstra."""
    def __init__(self):
        self.adyacencia = {}

    def agregar_ciudad(self, ciudad):
        if ciudad not in self.adyacencia:
            self.adyacencia[ciudad] = {}

    def agregar_conexion(self, origen, destino, distancia):
        self.agregar_ciudad(origen)
        self.agregar_ciudad(destino)
        self.adyacencia[origen][destino] = distancia
        self.adyacencia[destino][origen] = distancia

    def dijkstra(self, origen, destino):
        if origen not in self.adyacencia or destino not in self.adyacencia:
            return None, float("inf")

        distancias = {ciudad: float("inf") for ciudad in self.adyacencia}
        anteriores = {ciudad: None for ciudad in self.adyacencia}
        pendientes = set(self.adyacencia)

        distancias[origen] = 0

        while pendientes:
            actual = min(pendientes, key=lambda ciudad: distancias[ciudad])
            pendientes.remove(actual)

            if distancias[actual] == float("inf"):
                break

            if actual == destino:
                break

            for vecino, peso in self.adyacencia[actual].items():
                if vecino not in pendientes:
                    continue
                nueva_distancia = distancias[actual] + peso
                if nueva_distancia < distancias[vecino]:
                    distancias[vecino] = nueva_distancia
                    anteriores[vecino] = actual

        if distancias[destino] == float("inf"):
            return None, float("inf")

        ruta = []
        actual = destino
        while actual is not None:
            ruta.append(actual)
            actual = anteriores[actual]

        ruta.reverse()
        return ruta, distancias[destino]
