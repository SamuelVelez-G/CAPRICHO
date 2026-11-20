"""
Análisis experimental de los algoritmos (capricho/algoritmos.py).

Para cada problema y cada variante:
  1. Arma datos REALES del sistema (transacciones, pedidos, ítems, clientes)
     del tamaño n pedido. Si n es más grande que lo que hay en la base, los
     datos se replican con variaciones (otros días, otras sucursales) para
     conservar su forma: la misma distribución de montos, de clientes y de horas.
  2. Mide el tiempo (el mejor de varias repeticiones, con perf_counter) y
     cuenta las operaciones básicas.
  3. Si una variante O(n²) ya se va a demorar demasiado con el siguiente
     tamaño, no se corre: se marca como omitida con su tiempo estimado.
  4. Verifica que TODAS las variantes den el mismo resultado.
  5. Estima la complejidad observada con una regresión lineal sobre
     log(tiempo) contra log(n): la pendiente es el exponente. Pendiente ≈ 1
     es lineal, ≈ 2 es cuadrática, ≈ 0 es constante.
"""

import math
import platform
import random
import time
from datetime import datetime

from .. import algoritmos as alg
from ..tiempo import a_texto, ahora
from .estadistica import regresion_lineal

TAMANOS = {"COMPLETO": [100, 250, 500, 1_000, 2_500, 5_000, 10_000, 25_000, 50_000],
           "RAPIDO": [100, 250, 500, 1_000, 2_000]}
LIMITE_MS = {"COMPLETO": 3_000, "RAPIDO": 350}
EXPONENTE = {"O(1)": 0.1, "O(log n)": 0.2, "O(n)": 1.0, "O(n log n)": 1.15, "O(n²)": 2.0}
BUSQUEDAS = 200          # cuántos IDs se buscan en el problema de búsqueda


# =============================================================================
#  Datos del sistema, escalados al tamaño n
# =============================================================================

class Datos:
    """Lee una sola vez las tablas y genera muestras de cualquier tamaño."""

    def __init__(self, db, semilla=7):
        self.rng = random.Random(semilla)
        self.txns = [tuple(f) for f in db.execute(
            "SELECT id_txn, usuario_id, valor, fecha_txn FROM transacciones ORDER BY fecha_txn")]
        self.clientes_pedidos = [f[0] for f in db.execute("SELECT usuario_id FROM pedidos")]
        self.lineas = [(f[0], f[1]) for f in db.execute("SELECT producto_id, cantidad FROM pedido_items")]
        self.nombres = [f[0] for f in db.execute("SELECT nombre FROM usuarios")] + \
                       [f[0] for f in db.execute("SELECT nombre FROM productos")]
        if not self.txns:                   # base sin transacciones: datos de respaldo con fechas distintas
            from datetime import timedelta
            momento = ahora()
            self.txns = [(f"T{i:04d}", i % 30, 9_000 + 1_000 * (i % 20), a_texto(momento - timedelta(seconds=i * 7.3)))
                         for i in range(500, 0, -1)]
        if not self.clientes_pedidos:
            self.clientes_pedidos = [t[1] for t in self.txns]
        if not self.lineas:
            self.lineas = [(i % 20, 1 + i % 3) for i in range(500)]
        primera = datetime.fromisoformat(self.txns[0][3])
        self.segundos = [(t[1], (datetime.fromisoformat(t[3]) - primera).total_seconds()) for t in self.txns]
        self.duracion = (self.segundos[-1][1] if self.segundos else 0) + 86_400

    def _replica(self, fuente, n):
        """n elementos tomando la fuente en orden y repitiéndola; devuelve (elemento, número de réplica)."""
        return [(fuente[i % len(fuente)], i // len(fuente)) for i in range(n)]

    def registros(self, n):
        return [{"id": f"{t[0]}-{r}" if r else t[0], "valor": t[2]} for t, r in self._replica(self.txns, n)]

    def buscados(self, registros):
        ids = [r["id"] for r in registros]
        return [self.rng.choice(ids) if self.rng.random() < 0.9 else "NO-EXISTE" for _ in range(BUSQUEDAS)]

    def valores(self, n):
        return [t[2] for t, _ in self._replica(self.txns, n)]

    def montos_desordenados(self, n):
        valores = self.valores(n)
        self.rng.shuffle(valores)
        return valores

    def por_fecha(self, n):
        """Transacciones que llegan desordenadas (como en un lote): (fecha, id)."""
        datos = [(t[3].replace(t[3][:4], str(int(t[3][:4]) - r), 1) if r else t[3], t[0])
                 for t, r in self._replica(self.txns, n)]
        self.rng.shuffle(datos)
        return datos

    def clientes(self, n):
        """Más pedidos = más clientes: la réplica r es otra sucursal con otros clientes."""
        fuente = self.clientes_pedidos
        sucursales = max(1, n // (3 * len(set(fuente))))       # unos n/3 clientes distintos
        return [f"{self.rng.choice(fuente)}-{self.rng.randrange(sucursales)}" for _ in range(n)]

    def lineas_venta(self, n):
        return [(f"{p}-{r % 7}" if r else str(p), cantidad) for (p, cantidad), r in self._replica(self.lineas, n)]

    def nombres_sucios(self, n):
        """Nombres reales con las variaciones típicas de captura (mayúsculas, espacios, tildes)."""
        variaciones = [str.lower, str.upper, lambda s: s, lambda s: "  " + s.replace(" ", "  "),
                       lambda s: s.translate(str.maketrans("áéíóúÁÉÍÓÚ", "aeiouAEIOU"))]
        resultado = []
        for i in range(n):
            base = self.nombres[i % len(self.nombres)]
            if i >= len(self.nombres) * 3:
                base = f"{base} {i // (len(self.nombres) * 3)}"
            resultado.append(self.rng.choice(variaciones)(base))
        return resultado

    def flujo(self, n):
        """(usuario, segundo) en orden de llegada, como en el detector."""
        datos = [(f"{u}-{r % 3}", s + r * self.duracion) for (u, s), r in self._replica(self.segundos, n)]
        datos.sort(key=lambda d: d[1])
        return datos


# =============================================================================
#  Definición de los problemas
# =============================================================================

def _problemas():
    """(clave, título, descripción, armar_datos, [(clave, nombre, complejidad, preparar, correr)])"""
    sin_preparar = lambda datos: datos  # noqa: E731
    return [
        ("busqueda", "Búsqueda de una transacción por ID",
         f"Buscar {BUSQUEDAS} idTxn entre n transacciones (10 % no existen).",
         lambda d, n: (lambda r: (r, d.buscados(r)))(d.registros(n)),
         [("lineal", "Búsqueda lineal", "O(n)", sin_preparar, lambda x, c: alg.busqueda_lineal(x[0], x[1], c)),
          ("binaria", "Búsqueda binaria (lista ordenada)", "O(log n)",
           lambda x: (alg.preparar_binaria(x[0]), x[1]), lambda x, c: alg.busqueda_binaria(x[0], x[1], c)),
          ("hash", "Índice hash (diccionario)", "O(1)",
           lambda x: (alg.preparar_indice(x[0]), x[1]), lambda x, c: alg.busqueda_indice(x[0], x[1], c))]),
        ("suma", "Suma de ventas", "Total vendido en n transacciones.",
         lambda d, n: d.valores(n),
         [("bucle", "Bucle for", "O(n)", sin_preparar, lambda x, c: alg.suma_bucle(x, c)),
          ("divide", "Divide y vencerás", "O(n)", sin_preparar, lambda x, c: alg.suma_divide(x, c)),
          ("nativa", "sum() de Python (en C)", "O(n)", sin_preparar, lambda x, c: alg.suma_nativa(x, c))]),
        ("conteo", "Conteo de pedidos por cliente", "Cuántos pedidos hizo cada cliente (n pedidos).",
         lambda d, n: d.clientes(n),
         [("doble", "Doble ciclo", "O(n²)", sin_preparar, lambda x, c: alg.conteo_doble_ciclo(x, c)),
          ("ordenar", "Ordenar y agrupar", "O(n log n)", sin_preparar, lambda x, c: alg.conteo_ordenando(x, c)),
          ("diccionario", "Diccionario", "O(n)", sin_preparar, lambda x, c: alg.conteo_diccionario(x, c))]),
        ("ordenamiento_simple", "Ordenamiento simple", "Ordenar n montos de menor a mayor.",
         lambda d, n: d.montos_desordenados(n),
         [("burbuja", "Burbuja", "O(n²)", sin_preparar, lambda x, c: alg.burbuja(x, c)),
          ("seleccion", "Selección", "O(n²)", sin_preparar, lambda x, c: alg.seleccion(x, c)),
          ("insercion", "Inserción", "O(n²)", sin_preparar, lambda x, c: alg.insercion(x, c))]),
        ("ordenamiento_fecha", "Ordenamiento por fecha", "Ordenar cronológicamente n transacciones que llegan en lote.",
         lambda d, n: d.por_fecha(n),
         [("insercion", "Inserción", "O(n²)", sin_preparar, lambda x, c: alg.insercion(x, c, clave=lambda t: t[0])),
          ("merge", "Merge sort (divide y vencerás)", "O(n log n)", sin_preparar,
           lambda x, c: alg.merge_sort(x, c, clave=lambda t: t[0])),
          ("quick", "Quicksort", "O(n log n)", sin_preparar, lambda x, c: alg.quicksort(x, c, clave=lambda t: t[0])),
          ("heap", "Heapsort", "O(n log n)", sin_preparar, lambda x, c: alg.heapsort(x, c, clave=lambda t: t[0])),
          ("timsort", "Timsort (sorted)", "O(n log n)", sin_preparar,
           lambda x, c: alg.timsort(x, c, clave=lambda t: t[0]))]),
        ("ranking", "Ranking de ítems más vendidos", "Top 10 de productos en n líneas de pedido.",
         lambda d, n: d.lineas_venta(n),
         [("doble", "Doble ciclo", "O(n²)", sin_preparar, lambda x, c: alg.ranking_doble_ciclo(x, c)),
          ("ordenar", "Ordenar y agrupar", "O(n log n)", sin_preparar, lambda x, c: alg.ranking_ordenando(x, c)),
          ("heap", "Diccionario + heap", "O(n)", sin_preparar, lambda x, c: alg.ranking_heap(x, c))]),
        ("normalizacion", "Normalizar y unificar nombres",
         "Cuántos clientes o ítems distintos hay en n nombres mal escritos.",
         lambda d, n: d.nombres_sucios(n),
         [("pares", "Comparar por pares", "O(n²)", sin_preparar, lambda x, c: alg.unificar_por_pares(x, c)),
          ("ordenar", "Ordenar claves", "O(n log n)", sin_preparar, lambda x, c: alg.unificar_ordenando(x, c)),
          ("diccionario", "Conjunto de claves", "O(n)", sin_preparar, lambda x, c: alg.unificar_diccionario(x, c))]),
        ("ventana", "Ventana deslizante (ráfagas)",
         "Transacciones con 5 o más del mismo usuario en menos de 1 s (algoritmo crítico del detector).",
         lambda d, n: d.flujo(n),
         [("doble", "Doble ciclo", "O(n²)", sin_preparar, lambda x, c: alg.rafagas_doble_ciclo(x, c=c)),
          ("punteros", "Ordenar + dos punteros", "O(n log n)", sin_preparar,
           lambda x, c: alg.rafagas_dos_punteros(x, c=c)),
          ("deque", "Deque por usuario (en vivo)", "O(n)", sin_preparar, lambda x, c: alg.rafagas_deque(x, c=c))]),
    ]


# =============================================================================
#  Medición
# =============================================================================

def _medir(correr, entrada):
    """El mejor de varias repeticiones (el resto es ruido del sistema operativo)."""
    inicio = time.perf_counter()
    resultado = correr(entrada, None)
    mejor = time.perf_counter() - inicio
    repeticiones = 4 if mejor < 0.02 else 2 if mejor < 0.2 else 0
    for _ in range(repeticiones):
        inicio = time.perf_counter()
        correr(entrada, None)
        mejor = min(mejor, time.perf_counter() - inicio)
    return mejor * 1000, resultado


def _pendiente(puntos):
    validos = [(math.log10(p["n"]), math.log10(p["ms"])) for p in puntos if p.get("ms") and p["ms"] >= 0.002]
    if len(validos) < 3:
        return None, None
    pendiente, _, r2 = regresion_lineal([v[0] for v in validos], [v[1] for v in validos])
    return round(pendiente, 2), round(r2, 3)


def _clasificar(pendiente):
    if pendiente is None:
        return "sin datos suficientes"
    if pendiente < 0.35:
        return "casi constante: O(1) u O(log n)"
    if pendiente < 1.3:
        return "lineal: O(n) u O(n log n)"
    if pendiente < 1.7:
        return "entre lineal y cuadrático"
    return "cuadrático: O(n²)"


def correr(db, tipo="RAPIDO", tamanos=None, al_avanzar=None):
    """Ejecuta todo el experimento. Devuelve un diccionario listo para JSON."""
    inicio_total = time.perf_counter()
    tamanos = tamanos or TAMANOS[tipo]
    limite = LIMITE_MS[tipo]
    datos = Datos(db)
    problemas = []
    for clave, titulo, descripcion, armar, variantes in _problemas():
        # 1. ¿Todas las variantes dan lo mismo? (con un tamaño pequeño)
        muestra = armar(datos, 300)
        respuestas = [correr_variante(preparar(muestra), None) for _, _, _, preparar, correr_variante in variantes]
        verificado = all(r == respuestas[0] for r in respuestas)

        resultado_variantes = []
        for vclave, nombre, complejidad, preparar, correr_variante in variantes:
            puntos, anterior = [], None
            for n in tamanos:
                if anterior and anterior["ms"] * (n / anterior["n"]) ** EXPONENTE[complejidad] > limite:
                    estimado = anterior["ms"] * (n / anterior["n"]) ** EXPONENTE[complejidad]
                    puntos.append({"n": n, "omitido": True, "estimado_ms": round(estimado, 1)})
                    continue
                entrada = preparar(armar(datos, n))
                ms, _ = _medir(correr_variante, entrada)
                punto = {"n": n, "ms": round(ms, 4)}
                if n <= 2_500 or complejidad != "O(n²)":
                    contador = alg.Contador()
                    correr_variante(preparar(armar(datos, n)), contador)
                    punto["ops"] = contador.ops
                puntos.append(punto)
                anterior = punto
            pendiente, r2 = _pendiente(puntos)
            resultado_variantes.append({"clave": vclave, "nombre": nombre, "complejidad": complejidad,
                                        "puntos": puntos, "pendiente": pendiente, "r2": r2,
                                        "observado": _clasificar(pendiente)})
            if al_avanzar:
                al_avanzar(f"{titulo}: {nombre}")
        problemas.append({"clave": clave, "titulo": titulo, "descripcion": descripcion, "verificado": verificado,
                          "variantes": resultado_variantes, "mejora": _mejora(resultado_variantes)})
    return {
        "tipo": tipo, "tamanos": tamanos, "problemas": problemas,
        "equipo": f"{platform.processor() or platform.machine()} · Python {platform.python_version()} · {platform.system()}",
        "duracion_s": round(time.perf_counter() - inicio_total, 1), "fecha": a_texto(ahora()),
    }


def _mejora(variantes):
    """Cuántas veces más rápida es la mejor variante frente a la peor en el
    tamaño más grande que ambas alcanzaron (o con el tiempo estimado)."""
    def tiempo(v, n):
        punto = next((p for p in v["puntos"] if p["n"] == n), None)
        if punto is None:
            return None, False
        return (punto["estimado_ms"], True) if punto.get("omitido") else (punto["ms"], False)

    n = max(p["n"] for p in variantes[0]["puntos"])
    tiempos = [(v, *tiempo(v, n)) for v in variantes]
    tiempos = [t for t in tiempos if t[1]]
    if len(tiempos) < 2:
        return None
    lenta = max(tiempos, key=lambda t: t[1])
    rapida = min(tiempos, key=lambda t: t[1])
    return {"n": n, "lenta": lenta[0]["nombre"], "lenta_complejidad": lenta[0]["complejidad"],
            "rapida": rapida[0]["nombre"], "rapida_complejidad": rapida[0]["complejidad"],
            "lenta_ms": round(lenta[1], 2), "rapida_ms": round(rapida[1], 3), "estimado": lenta[2],
            "veces": round(lenta[1] / max(rapida[1], 1e-4), 1)}


def guardar(db, resultado):
    import json
    cursor = db.execute(
        "INSERT INTO benchmarks (tipo, duracion_s, equipo, resultados, fecha) VALUES (?, ?, ?, ?, ?)",
        (resultado["tipo"], resultado["duracion_s"], resultado["equipo"], json.dumps(resultado, ensure_ascii=False),
         resultado["fecha"]))
    db.commit()
    return cursor.lastrowid


def ultimo(db, tipo=None):
    import json
    consulta = "SELECT id, resultados FROM benchmarks" + (" WHERE tipo = ?" if tipo else "") + " ORDER BY id DESC LIMIT 1"
    fila = db.execute(consulta, (tipo,) if tipo else ()).fetchone()
    return {**json.loads(fila["resultados"]), "id": fila["id"]} if fila else None
