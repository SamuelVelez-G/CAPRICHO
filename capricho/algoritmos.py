"""
Algoritmos de la entrega final, cada problema resuelto con varias complejidades.

Todos reciben datos reales del sistema (transacciones, pedidos, ítems,
clientes) y un contador opcional `c` que cuenta las operaciones básicas
(comparaciones y accesos). El benchmark (servicios/benchmark.py) los mide
con tamaños crecientes y verifica que todas las variantes de un problema
den el mismo resultado.

    Problema                          Variantes
    -------------------------------   ------------------------------------------------
    Búsqueda por ID                   lineal O(n) · binaria O(log n) · índice hash O(1)
    Suma de ventas                    bucle O(n) · divide y vencerás O(n) · sum() O(n)
    Conteo de pedidos por cliente     doble ciclo O(n²) · ordenar y agrupar O(n log n) · diccionario O(n)
    Ordenamiento simple               burbuja O(n²) · selección O(n²) · inserción O(n²)
    Ordenamiento por fecha            inserción O(n²) · merge sort · quicksort · heapsort · Timsort O(n log n)
    Ranking de ítems más vendidos     doble ciclo O(n²) · ordenar y agrupar O(n log n) · diccionario + heap O(n)
    Normalizar y unificar nombres     por pares O(n²) · ordenar claves O(n log n) · diccionario O(n)
    Ventana deslizante (ráfagas)      doble ciclo O(n²) · ordenar + dos punteros O(n log n) · deque por usuario O(n)
"""

import heapq
from collections import deque

from .servicios.normalizacion import clave as clave_texto


class Contador:
    """Cuenta operaciones básicas para comparar con n, n·log n y n²."""

    def __init__(self):
        self.ops = 0


# =============================================================================
#  1. Búsqueda de una transacción por ID
# =============================================================================

def busqueda_lineal(registros, buscados, c=None):
    """Recorre la lista hasta encontrarlo: O(n) por búsqueda."""
    encontrados = []
    for objetivo in buscados:
        hallado = None
        for registro in registros:
            if c:
                c.ops += 1
            if registro["id"] == objetivo:
                hallado = registro
                break
        encontrados.append(hallado["id"] if hallado else None)
    return encontrados


def preparar_binaria(registros):
    ordenados = sorted(registros, key=lambda r: r["id"])
    return ordenados, [r["id"] for r in ordenados]


def busqueda_binaria(preparado, buscados, c=None):
    """Parte a la mitad el rango en cada paso: O(log n) por búsqueda (lista ordenada)."""
    ordenados, ids = preparado
    encontrados = []
    for objetivo in buscados:
        izq, der = 0, len(ids) - 1
        hallado = None
        while izq <= der:
            if c:
                c.ops += 1
            mitad = (izq + der) // 2
            if ids[mitad] == objetivo:
                hallado = ordenados[mitad]
                break
            if ids[mitad] < objetivo:
                izq = mitad + 1
            else:
                der = mitad - 1
        encontrados.append(hallado["id"] if hallado else None)
    return encontrados


def preparar_indice(registros):
    return {r["id"]: r for r in registros}


def busqueda_indice(indice, buscados, c=None):
    """Diccionario (tabla hash): un acceso directo, O(1) por búsqueda."""
    encontrados = []
    for objetivo in buscados:
        if c:
            c.ops += 1
        hallado = indice.get(objetivo)
        encontrados.append(hallado["id"] if hallado else None)
    return encontrados


# =============================================================================
#  2. Suma de ventas
# =============================================================================

def suma_bucle(valores, c=None):
    total = 0
    for valor in valores:
        if c:
            c.ops += 1
        total += valor
    return round(total, 2)


def suma_divide(valores, c=None, inicio=0, fin=None):
    """Divide y vencerás: la suma de la mitad izquierda más la de la derecha."""
    if fin is None:
        fin = len(valores)
    if fin - inicio <= 1:
        if c:
            c.ops += 1
        return valores[inicio] if fin > inicio else 0
    mitad = (inicio + fin) // 2
    return round(suma_divide(valores, c, inicio, mitad) + suma_divide(valores, c, mitad, fin), 2)


def suma_nativa(valores, c=None):
    """sum() de Python: también O(n), pero el ciclo corre en C."""
    if c:
        c.ops += len(valores)
    return round(sum(valores), 2)


# =============================================================================
#  3. Conteo de pedidos por cliente
# =============================================================================

def conteo_doble_ciclo(clientes, c=None):
    """Por cada pedido, recorrer todos los pedidos para contar los de su cliente: O(n²)."""
    conteo = {}
    for cliente in clientes:
        if cliente in conteo:
            continue
        cuantos = 0
        for otro in clientes:
            if c:
                c.ops += 1
            if otro == cliente:
                cuantos += 1
        conteo[cliente] = cuantos
    return conteo


def conteo_ordenando(clientes, c=None):
    """Ordenar (O(n log n)) y contar los bloques iguales seguidos (O(n))."""
    ordenados = sorted(clientes)
    if c:
        c.ops += len(ordenados) * max(1, len(ordenados).bit_length())
    conteo = {}
    i = 0
    while i < len(ordenados):
        j = i
        while j < len(ordenados) and ordenados[j] == ordenados[i]:
            if c:
                c.ops += 1
            j += 1
        conteo[ordenados[i]] = j - i
        i = j
    return conteo


def conteo_diccionario(clientes, c=None):
    """Una sola pasada sumando en un diccionario: O(n)."""
    conteo = {}
    for cliente in clientes:
        if c:
            c.ops += 1
        conteo[cliente] = conteo.get(cliente, 0) + 1
    return conteo


# =============================================================================
#  4. Ordenamiento simple (montos) — todos O(n²)
# =============================================================================

def burbuja(valores, c=None):
    """Intercambia vecinos desordenados; si una pasada no cambia nada, ya terminó."""
    a = list(valores)
    n = len(a)
    for i in range(n):
        cambio = False
        for j in range(n - 1 - i):
            if c:
                c.ops += 1
            if a[j] > a[j + 1]:
                a[j], a[j + 1] = a[j + 1], a[j]
                cambio = True
        if not cambio:
            break
    return a


def seleccion(valores, c=None):
    """Busca el menor de lo que falta y lo pone al frente."""
    a = list(valores)
    n = len(a)
    for i in range(n):
        menor = i
        for j in range(i + 1, n):
            if c:
                c.ops += 1
            if a[j] < a[menor]:
                menor = j
        a[i], a[menor] = a[menor], a[i]
    return a


def insercion(valores, c=None, clave=lambda x: x):
    """Inserta cada elemento en su lugar dentro de la parte ya ordenada (como las cartas)."""
    a = list(valores)
    for i in range(1, len(a)):
        actual = a[i]
        k = clave(actual)
        j = i - 1
        while j >= 0 and clave(a[j]) > k:
            if c:
                c.ops += 1
            a[j + 1] = a[j]
            j -= 1
        if c:
            c.ops += 1
        a[j + 1] = actual
    return a


# =============================================================================
#  5. Ordenamiento por fecha — O(n log n)
# =============================================================================

def merge_sort(elementos, c=None, clave=lambda x: x):
    """Divide y vencerás: ordena cada mitad y las mezcla. Estable."""
    if len(elementos) <= 1:
        return list(elementos)
    mitad = len(elementos) // 2
    izquierda = merge_sort(elementos[:mitad], c, clave)
    derecha = merge_sort(elementos[mitad:], c, clave)
    resultado = []
    i = j = 0
    while i < len(izquierda) and j < len(derecha):
        if c:
            c.ops += 1
        if clave(izquierda[i]) <= clave(derecha[j]):
            resultado.append(izquierda[i])
            i += 1
        else:
            resultado.append(derecha[j])
            j += 1
    resultado.extend(izquierda[i:])
    resultado.extend(derecha[j:])
    return resultado


def quicksort(elementos, c=None, clave=lambda x: x):
    """Escoge un pivote y parte en menores, iguales y mayores. O(n log n) en promedio."""
    if len(elementos) <= 1:
        return list(elementos)
    pivote = clave(elementos[len(elementos) // 2])
    menores, iguales, mayores = [], [], []
    for e in elementos:
        if c:
            c.ops += 1
        k = clave(e)
        (menores if k < pivote else mayores if k > pivote else iguales).append(e)
    return quicksort(menores, c, clave) + iguales + quicksort(mayores, c, clave)


def heapsort(elementos, c=None, clave=lambda x: x):
    """Montículo: n inserciones y n extracciones de O(log n)."""
    monticulo = [(clave(e), i, e) for i, e in enumerate(elementos)]
    heapq.heapify(monticulo)
    if c:
        c.ops += len(monticulo) * max(1, len(monticulo).bit_length())
    return [heapq.heappop(monticulo)[2] for _ in range(len(monticulo))]


def timsort(elementos, c=None, clave=lambda x: x):
    """sorted() de Python (Timsort, escrito en C): la referencia."""
    if c:
        c.ops += len(elementos) * max(1, len(elementos).bit_length())
    return sorted(elementos, key=clave)


# =============================================================================
#  6. Ranking de ítems más vendidos (top 10)
# =============================================================================

def ranking_doble_ciclo(lineas, c=None, k=10):
    """Por cada línea, sumar todas las líneas de su producto: O(n²).
    Es la solución ingenua: no recuerda los totales que ya calculó."""
    totales = {}
    for linea in lineas:
        suma = 0
        for otra in lineas:
            if c:
                c.ops += 1
            if otra[0] == linea[0]:
                suma += otra[1]
        totales[linea[0]] = suma
    return sorted(totales.items(), key=lambda par: (-par[1], par[0]))[:k]


def ranking_ordenando(lineas, c=None, k=10):
    """Ordenar las líneas por producto (O(n log n)) y sumar por bloques."""
    ordenadas = sorted(lineas)
    if c:
        c.ops += len(ordenadas) * max(1, len(ordenadas).bit_length())
    totales = []
    i = 0
    while i < len(ordenadas):
        producto, suma = ordenadas[i][0], 0
        while i < len(ordenadas) and ordenadas[i][0] == producto:
            if c:
                c.ops += 1
            suma += ordenadas[i][1]
            i += 1
        totales.append((producto, suma))
    return sorted(totales, key=lambda par: (-par[1], par[0]))[:k]


def ranking_heap(lineas, c=None, k=10):
    """Diccionario (O(n)) y luego un heap de tamaño k para el top (O(p log k))."""
    totales = {}
    for producto, cantidad in lineas:
        if c:
            c.ops += 1
        totales[producto] = totales.get(producto, 0) + cantidad
    return heapq.nsmallest(k, totales.items(), key=lambda par: (-par[1], par[0]))


# =============================================================================
#  7. Normalizar nombres y unificar duplicados
# =============================================================================

def unificar_por_pares(nombres, c=None):
    """Compara cada nombre normalizado con todos los anteriores: O(n²)."""
    claves = [clave_texto(n) for n in nombres]
    grupos = []
    representante = [None] * len(claves)
    for i in range(len(claves)):
        for j in range(i):
            if c:
                c.ops += 1
            if claves[j] == claves[i]:
                representante[i] = representante[j]
                break
        if representante[i] is None:
            representante[i] = len(grupos)
            grupos.append(claves[i])
    return len(grupos)


def unificar_ordenando(nombres, c=None):
    """Ordena las claves (O(n log n)) y cuenta las distintas comparando vecinos."""
    claves = sorted(clave_texto(n) for n in nombres)
    if c:
        c.ops += len(claves) * max(1, len(claves).bit_length())
    distintas = 0
    for i in range(len(claves)):
        if c:
            c.ops += 1
        if i == 0 or claves[i] != claves[i - 1]:
            distintas += 1
    return distintas


def unificar_diccionario(nombres, c=None):
    """Un conjunto de claves normalizadas: O(n)."""
    vistas = set()
    for nombre in nombres:
        if c:
            c.ops += 1
        vistas.add(clave_texto(nombre))
    return len(vistas)


# =============================================================================
#  8. Ventana deslizante: transacciones del mismo usuario en menos de 1 s
# =============================================================================

def rafagas_doble_ciclo(txns, ventana=1.0, maximo=5, c=None):
    """Por cada transacción, recorrer TODAS las demás: O(n²)."""
    sospechosas = 0
    for i, (usuario, t) in enumerate(txns):
        cuantas = 0
        for otro, s in txns:
            if c:
                c.ops += 1
            if otro == usuario and t - ventana < s <= t:
                cuantas += 1
        if cuantas >= maximo:
            sospechosas += 1
    return sospechosas


def rafagas_dos_punteros(txns, ventana=1.0, maximo=5, c=None):
    """Agrupar por usuario, ordenar cada grupo (O(n log n)) y recorrerlo con dos punteros (O(n))."""
    por_usuario = {}
    for usuario, t in txns:
        por_usuario.setdefault(usuario, []).append(t)
    sospechosas = 0
    for tiempos in por_usuario.values():
        tiempos.sort()
        if c:
            c.ops += len(tiempos) * max(1, len(tiempos).bit_length())
        izq = 0
        for der in range(len(tiempos)):
            while tiempos[der] - tiempos[izq] >= ventana:
                if c:
                    c.ops += 1
                izq += 1
            if c:
                c.ops += 1
            if der - izq + 1 >= maximo:
                sospechosas += 1
    return sospechosas


def rafagas_deque(txns, ventana=1.0, maximo=5, c=None):
    """Como el detector en vivo: las transacciones llegan en orden y cada
    usuario tiene una deque con las de su último segundo. O(n) amortizado."""
    ventanas = {}
    sospechosas = 0
    for usuario, t in txns:
        cola = ventanas.setdefault(usuario, deque())
        cola.append(t)
        while t - cola[0] >= ventana:
            if c:
                c.ops += 1
            cola.popleft()
        if c:
            c.ops += 1
        if len(cola) >= maximo:
            sospechosas += 1
    return sospechosas
