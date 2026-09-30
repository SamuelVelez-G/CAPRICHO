"""
Estructuras de datos y algoritmos de Capricho.

Aquí se reúne lo mejor de los dos trabajos anteriores y las técnicas nuevas:

  Trabajo 1 (complejidad)   IndiceHash ........ búsqueda por índice, O(1)
  Trabajo 2 (estructuras)   Cola .............. pedidos en orden de llegada (FIFO)
                            Pila .............. errores, el más reciente primero (LIFO)
                            Grafo + Dijkstra .. ruta más corta para los domicilios
  Técnicas de resolución    merge_sort ........ divide y vencerás, ordena cronológicamente
                            mayor_por_division  divide y vencerás, el mayor de una lista
                            max_en_ventana .... ventana deslizante con dos punteros
                            LimitadorVentana .. ventana deslizante por clave (solicitudes/segundo)
"""

import heapq
from collections import deque
from time import monotonic


# =============================================================================
#  COLA (FIFO) — el primero que entra es el primero que sale
# =============================================================================

class Cola:
    """Cola de pedidos. Se atiende en el mismo orden en que se pagó.

    En el trabajo anterior se usaba list.pop(0), que es O(n) porque corre
    todos los elementos una posición. deque saca por la izquierda en O(1).
    """

    def __init__(self, elementos=None):
        self._elementos = deque(elementos or [])

    def encolar(self, elemento):
        self._elementos.append(elemento)

    def desencolar(self):
        return self._elementos.popleft() if self._elementos else None

    def frente(self):
        return self._elementos[0] if self._elementos else None

    def esta_vacia(self) -> bool:
        return not self._elementos

    def elementos(self) -> list:
        return list(self._elementos)

    def __len__(self):
        return len(self._elementos)


# =============================================================================
#  PILA (LIFO) — el último que entra es el primero que sale
# =============================================================================

class Pila:
    """Pila de errores y eventos de seguridad.

    Lo más urgente de revisar es lo que acaba de pasar, por eso el error más
    reciente queda en la cima.
    """

    def __init__(self, elementos=None):
        self._elementos = list(elementos or [])

    def apilar(self, elemento):
        self._elementos.append(elemento)

    def desapilar(self):
        return self._elementos.pop() if self._elementos else None

    def cima(self):
        return self._elementos[-1] if self._elementos else None

    def esta_vacia(self) -> bool:
        return not self._elementos

    def elementos(self) -> list:
        """De la cima hacia el fondo."""
        return list(reversed(self._elementos))

    def __len__(self):
        return len(self._elementos)


# =============================================================================
#  ÍNDICE HASH — búsqueda por clave en O(1)
# =============================================================================

class IndiceHash:
    """Diccionario clave -> valor.

    Construirlo cuesta O(n) una sola vez al arrancar; después cada búsqueda
    es un acceso directo, sin importar cuántos registros haya. Es la
    conclusión del primer trabajo: se paga memoria para ganar tiempo.
    """

    def __init__(self, pares=None):
        self._datos = dict(pares or {})

    def agregar(self, clave, valor):
        self._datos[clave] = valor

    def quitar(self, clave):
        self._datos.pop(clave, None)

    def buscar(self, clave):
        """Devuelve (valor, operaciones). Siempre es 1 operación."""
        return self._datos.get(clave), 1

    def contiene(self, clave) -> bool:
        return clave in self._datos

    def __len__(self):
        return len(self._datos)


# =============================================================================
#  GRAFO PONDERADO + DIJKSTRA — ruta más corta de los domicilios
# =============================================================================

class Grafo:
    """Grafo no dirigido: los barrios son nodos y las vías son aristas con km."""

    def __init__(self):
        self._adyacencia = {}

    def agregar_nodo(self, nodo):
        self._adyacencia.setdefault(nodo, {})

    def agregar_arista(self, origen, destino, peso):
        self.agregar_nodo(origen)
        self.agregar_nodo(destino)
        self._adyacencia[origen][destino] = peso
        self._adyacencia[destino][origen] = peso

    def nodos(self) -> list:
        return list(self._adyacencia)

    def aristas(self) -> list:
        vistas = set()
        resultado = []
        for origen, vecinos in self._adyacencia.items():
            for destino, peso in vecinos.items():
                par = tuple(sorted((origen, destino)))
                if par not in vistas:
                    vistas.add(par)
                    resultado.append((origen, destino, peso))
        return resultado

    def contiene(self, nodo) -> bool:
        return nodo in self._adyacencia

    def dijkstra(self, origen, destino):
        """Devuelve (ruta, distancia, nodos_visitados).

        Usa un heap (montículo) para sacar siempre el nodo más cercano en
        O(log V). El trabajo anterior lo buscaba con min() sobre un
        conjunto, que es O(V) en cada paso.
        Complejidad: O((V + E) log V).
        """
        if origen not in self._adyacencia or destino not in self._adyacencia:
            return None, float("inf"), 0

        distancias = {origen: 0.0}
        anterior = {origen: None}
        visitados = set()
        monticulo = [(0.0, origen)]

        while monticulo:
            distancia, nodo = heapq.heappop(monticulo)
            if nodo in visitados:
                continue
            visitados.add(nodo)
            if nodo == destino:
                break
            for vecino, peso in self._adyacencia[nodo].items():
                nueva = distancia + peso
                if nueva < distancias.get(vecino, float("inf")):
                    distancias[vecino] = nueva
                    anterior[vecino] = nodo
                    heapq.heappush(monticulo, (nueva, vecino))

        if destino not in distancias:
            return None, float("inf"), len(visitados)

        ruta = []
        nodo = destino
        while nodo is not None:
            ruta.append(nodo)
            nodo = anterior[nodo]
        ruta.reverse()
        return ruta, round(distancias[destino], 2), len(visitados)


# =============================================================================
#  DIVIDE Y VENCERÁS
# =============================================================================

def merge_sort(elementos, clave=lambda x: x):
    """Ordena dividiendo la lista en mitades, ordenando cada mitad y
    mezclándolas (divide, resuelve, combina).

    Se usa para ordenar cronológicamente las transacciones que llegan en
    lote y desordenadas. Es estable: si dos transacciones tienen la misma
    fecha conservan el orden en que llegaron.
    Complejidad: O(n log n).
    """
    if len(elementos) <= 1:                       # caso base
        return list(elementos)

    mitad = len(elementos) // 2                   # divide
    izquierda = merge_sort(elementos[:mitad], clave)   # resuelve
    derecha = merge_sort(elementos[mitad:], clave)

    resultado = []                                # combina
    i = j = 0
    while i < len(izquierda) and j < len(derecha):
        if clave(izquierda[i]) <= clave(derecha[j]):
            resultado.append(izquierda[i])
            i += 1
        else:
            resultado.append(derecha[j])
            j += 1
    resultado.extend(izquierda[i:])
    resultado.extend(derecha[j:])
    return resultado


def mayor_por_division(elementos, clave=lambda x: x, inicio=0, fin=None):
    """El mayor de una lista partiéndola en mitades (diapositiva 24).

    Trabaja con posiciones en vez de cortar la lista, para no copiarla en
    cada llamada. Complejidad: O(n) en tiempo, O(log n) en pila de llamadas.
    """
    if not elementos:
        return None
    if fin is None:
        fin = len(elementos) - 1
    if inicio == fin:                             # caso base: un solo elemento
        return elementos[inicio]
    mitad = (inicio + fin) // 2
    izquierda = mayor_por_division(elementos, clave, inicio, mitad)
    derecha = mayor_por_division(elementos, clave, mitad + 1, fin)
    return izquierda if clave(izquierda) >= clave(derecha) else derecha


# =============================================================================
#  VENTANA DESLIZANTE
# =============================================================================

def max_en_ventana(instantes, objetivo, ventana_segundos):
    """Mayor cantidad de eventos que caben en una ventana de `ventana_segundos`
    que contenga al evento `objetivo`.

    `instantes` es una lista ORDENADA de segundos que ya incluye a `objetivo`.
    Dos eventos están en la misma ventana si los separa MENOS de
    `ventana_segundos` (10:00:01.000 y 10:00:02.000 no están "en el mismo
    segundo").

    Dos punteros: `der` agrega un elemento nuevo y `izq` saca los que ya
    quedaron fuera. Nunca se vuelve a recorrer lo que ya se contó.
    Complejidad: O(k), siendo k el número de vecinos.
    """
    mejor = 0
    izq = 0
    for der in range(len(instantes)):
        while instantes[der] - instantes[izq] >= ventana_segundos:
            izq += 1                              # SALE el más viejo
        if instantes[izq] <= objetivo <= instantes[der]:
            mejor = max(mejor, der - izq + 1)     # ENTRA el nuevo y se cuenta
    return mejor


class LimitadorVentana:
    """Cuenta eventos por clave (una IP, un correo) dentro de los últimos
    `ventana_segundos`, con una deque por clave.

    Es exactamente el algoritmo de la diapositiva 41: agregar el evento,
    eliminar los que quedaron fuera de la ventana y contar.
    """

    def __init__(self, maximo, ventana_segundos):
        self.maximo = maximo
        self.ventana = ventana_segundos
        self._ventanas = {}

    def registrar(self, clave, instante=None):
        """Registra un evento. Devuelve (permitido, cantidad_en_ventana)."""
        instante = monotonic() if instante is None else instante
        ventana = self._ventanas.setdefault(clave, deque())
        ventana.append(instante)
        while ventana and instante - ventana[0] >= self.ventana:
            ventana.popleft()
        return len(ventana) <= self.maximo, len(ventana)

    def cantidad(self, clave, instante=None):
        instante = monotonic() if instante is None else instante
        ventana = self._ventanas.get(clave)
        if not ventana:
            return 0
        while ventana and instante - ventana[0] >= self.ventana:
            ventana.popleft()
        return len(ventana)

    def limpiar(self, clave):
        self._ventanas.pop(clave, None)
