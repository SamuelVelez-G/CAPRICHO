# Informe del análisis experimental de algoritmos

Generado por `herramientas/benchmark.py` el 2026-11-20 14:52 en AMD64 Family 25 Model 68 Stepping 1, AuthenticAMD · Python 3.12.10 · Windows (29.0 s).

Cada problema se resolvió de varias formas sobre datos reales de la base de Capricho (replicados para los tamaños grandes). Se midió el mejor de varios intentos con `time.perf_counter`, se contaron las operaciones básicas y se verificó que todas las variantes dieran el mismo resultado. La **pendiente** es el exponente estimado con una regresión lineal de log(tiempo) contra log(n): ≈ 0 es constante, ≈ 1 lineal, ≈ 2 cuadrático.

## Búsqueda de una transacción por ID

Buscar 200 idTxn entre n transacciones (10 % no existen). Todas las variantes dieron el mismo resultado.

| Variante | Teoría | n = 100 | n = 250 | n = 500 | n = 1.000 | n = 2.500 | n = 5.000 | n = 10.000 | n = 25.000 | n = 50.000 | Pendiente | R² |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Búsqueda lineal | O(n) | 315 µs | 784 µs | 1.59 ms | 2.93 ms | 8.12 ms | 15.72 ms | 29.61 ms | 80.15 ms | 155.26 ms | 1.0 | 1.0 |
| Búsqueda binaria (lista ordenada) | O(log n) | 107 µs | 143 µs | 171 µs | 189 µs | 227 µs | 246 µs | 274 µs | 294 µs | 343 µs | 0.17 | 0.969 |
| Índice hash (diccionario) | O(1) | 12 µs | 12 µs | 13 µs | 13 µs | 13 µs | 13 µs | 14 µs | 19 µs | 13 µs | 0.04 | 0.335 |

**Mejora:** con n = 50.000. Índice hash (diccionario) (O(1)) tarda 13 µs y Búsqueda lineal (O(n)) tarda 155.26 ms: **12.225 veces más rápido**.

## Suma de ventas

Total vendido en n transacciones. Todas las variantes dieron el mismo resultado.

| Variante | Teoría | n = 100 | n = 250 | n = 500 | n = 1.000 | n = 2.500 | n = 5.000 | n = 10.000 | n = 25.000 | n = 50.000 | Pendiente | R² |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Bucle for | O(n) | 3 µs | 6 µs | 12 µs | 24 µs | 60 µs | 120 µs | 238 µs | 601 µs | 1.20 ms | 0.98 | 1.0 |
| Divide y vencerás | O(n) | 39 µs | 100 µs | 202 µs | 412 µs | 1.04 ms | 2.09 ms | 4.12 ms | 10.31 ms | 20.96 ms | 1.01 | 1.0 |
| sum() de Python (en C) | O(n) | 1 µs | 2 µs | 3 µs | 6 µs | 13 µs | 26 µs | 51 µs | 129 µs | 257 µs | 0.97 | 0.999 |

**Mejora:** con n = 50.000. sum() de Python (en C) (O(n)) tarda 257 µs y Divide y vencerás (O(n)) tarda 20.96 ms: **81 veces más rápido**.

## Conteo de pedidos por cliente

Cuántos pedidos hizo cada cliente (n pedidos). Todas las variantes dieron el mismo resultado.

| Variante | Teoría | n = 100 | n = 250 | n = 500 | n = 1.000 | n = 2.500 | n = 5.000 | n = 10.000 | n = 25.000 | n = 50.000 | Pendiente | R² |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Doble ciclo | O(n²) | 76 µs | 417 µs | 1.56 ms | 6.69 ms | 42.30 ms | 172.26 ms | 705.60 ms | ~4.41 s* | ~17.64 s* | 2.0 | 1.0 |
| Ordenar y agrupar | O(n log n) | 12 µs | 32 µs | 69 µs | 166 µs | 499 µs | 1.07 ms | 2.23 ms | 6.22 ms | 14.41 ms | 1.15 | 1.0 |
| Diccionario | O(n) | 6 µs | 15 µs | 31 µs | 64 µs | 168 µs | 344 µs | 673 µs | 1.78 ms | 3.87 ms | 1.03 | 1.0 |

**Mejora:** con n = 50.000. Diccionario (O(n)) tarda 3.87 ms y Doble ciclo (O(n²)) tardaría 17.64 s: **4.556 veces más rápido**.

## Ordenamiento simple

Ordenar n montos de menor a mayor. Todas las variantes dieron el mismo resultado.

| Variante | Teoría | n = 100 | n = 250 | n = 500 | n = 1.000 | n = 2.500 | n = 5.000 | n = 10.000 | n = 25.000 | n = 50.000 | Pendiente | R² |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Burbuja | O(n²) | 273 µs | 1.84 ms | 7.15 ms | 32.02 ms | 233.75 ms | 932.88 ms | ~3.73 s* | ~23.32 s* | ~93.29 s* | 2.09 | 1.0 |
| Selección | O(n²) | 167 µs | 987 µs | 4.02 ms | 16.37 ms | 99.99 ms | 402.56 ms | 1.59 s | ~9.95 s* | ~39.80 s* | 1.99 | 1.0 |
| Inserción | O(n²) | 199 µs | 1.19 ms | 4.54 ms | 19.82 ms | 123.69 ms | 502.43 ms | 2.02 s | ~12.63 s* | ~50.53 s* | 2.01 | 1.0 |

**Mejora:** con n = 50.000. Selección (O(n²)) tarda 39.80 s y Burbuja (O(n²)) tardaría 93.29 s: **2 veces más rápido**.

## Ordenamiento por fecha

Ordenar cronológicamente n transacciones que llegan en lote. Todas las variantes dieron el mismo resultado.

| Variante | Teoría | n = 100 | n = 250 | n = 500 | n = 1.000 | n = 2.500 | n = 5.000 | n = 10.000 | n = 25.000 | n = 50.000 | Pendiente | R² |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Inserción | O(n²) | 257 µs | 1.61 ms | 6.23 ms | 24.54 ms | 151.94 ms | 618.83 ms | 2.55 s | ~15.94 s* | ~63.77 s* | 1.99 | 1.0 |
| Merge sort (divide y vencerás) | O(n log n) | 134 µs | 385 µs | 820 µs | 1.88 ms | 5.17 ms | 10.98 ms | 24.56 ms | 66.37 ms | 149.48 ms | 1.13 | 1.0 |
| Quicksort | O(n log n) | 96 µs | 248 µs | 620 µs | 1.24 ms | 3.46 ms | 7.81 ms | 17.28 ms | 48.70 ms | 115.67 ms | 1.14 | 1.0 |
| Heapsort | O(n log n) | 29 µs | 78 µs | 180 µs | 395 µs | 1.18 ms | 2.73 ms | 6.18 ms | 19.64 ms | 53.10 ms | 1.2 | 0.999 |
| Timsort (sorted) | O(n log n) | 7 µs | 20 µs | 46 µs | 116 µs | 325 µs | 756 µs | 1.71 ms | 4.77 ms | 12.07 ms | 1.2 | 1.0 |

**Mejora:** con n = 50.000. Timsort (sorted) (O(n log n)) tarda 12.07 ms y Inserción (O(n²)) tardaría 63.77 s: **5.282 veces más rápido**.

## Ranking de ítems más vendidos

Top 10 de productos en n líneas de pedido. Todas las variantes dieron el mismo resultado.

| Variante | Teoría | n = 100 | n = 250 | n = 500 | n = 1.000 | n = 2.500 | n = 5.000 | n = 10.000 | n = 25.000 | n = 50.000 | Pendiente | R² |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Doble ciclo | O(n²) | 398 µs | 2.29 ms | 9.13 ms | 36.32 ms | 236.07 ms | 884.66 ms | ~3.54 s* | ~22.12 s* | ~88.47 s* | 1.98 | 1.0 |
| Ordenar y agrupar | O(n log n) | 16 µs | 41 µs | 87 µs | 185 µs | 475 µs | 1.01 ms | 2.05 ms | 5.25 ms | 11.39 ms | 1.05 | 1.0 |
| Diccionario + heap | O(n) | 8 µs | 18 µs | 34 µs | 65 µs | 173 µs | 336 µs | 676 µs | 1.71 ms | 3.40 ms | 0.98 | 0.999 |

**Mejora:** con n = 50.000. Diccionario + heap (O(n)) tarda 3.40 ms y Doble ciclo (O(n²)) tardaría 88.47 s: **25.992 veces más rápido**.

## Normalizar y unificar nombres

Cuántos clientes o ítems distintos hay en n nombres mal escritos. Todas las variantes dieron el mismo resultado.

| Variante | Teoría | n = 100 | n = 250 | n = 500 | n = 1.000 | n = 2.500 | n = 5.000 | n = 10.000 | n = 25.000 | n = 50.000 | Pendiente | R² |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Comparar por pares | O(n²) | 390 µs | 1.32 ms | 4.55 ms | 16.96 ms | 105.37 ms | 434.81 ms | 1.75 s | ~10.91 s* | ~43.64 s* | 1.86 | 0.996 |
| Ordenar claves | O(n log n) | 317 µs | 814 µs | 1.72 ms | 3.53 ms | 9.08 ms | 18.76 ms | 37.96 ms | 98.25 ms | 193.62 ms | 1.03 | 1.0 |
| Conjunto de claves | O(n) | 306 µs | 781 µs | 1.70 ms | 3.38 ms | 8.75 ms | 18.43 ms | 37.03 ms | 92.57 ms | 200.51 ms | 1.04 | 1.0 |

**Mejora:** con n = 50.000. Ordenar claves (O(n log n)) tarda 193.62 ms y Comparar por pares (O(n²)) tardaría 43.64 s: **225 veces más rápido**.

## Ventana deslizante (ráfagas)

Transacciones con 5 o más del mismo usuario en menos de 1 s (algoritmo crítico del detector). Todas las variantes dieron el mismo resultado.

| Variante | Teoría | n = 100 | n = 250 | n = 500 | n = 1.000 | n = 2.500 | n = 5.000 | n = 10.000 | n = 25.000 | n = 50.000 | Pendiente | R² |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Doble ciclo | O(n²) | 310 µs | 1.97 ms | 7.59 ms | 31.09 ms | 204.13 ms | 780.03 ms | ~3.12 s* | ~19.50 s* | ~78.00 s* | 2.01 | 1.0 |
| Ordenar + dos punteros | O(n log n) | 20 µs | 44 µs | 88 µs | 174 µs | 420 µs | 849 µs | 1.66 ms | 4.29 ms | 9.65 ms | 0.99 | 0.999 |
| Deque por usuario (en vivo) | O(n) | 26 µs | 63 µs | 130 µs | 252 µs | 642 µs | 1.30 ms | 2.60 ms | 6.68 ms | 13.01 ms | 1.0 | 1.0 |

**Mejora:** con n = 50.000. Ordenar + dos punteros (O(n log n)) tarda 9.65 ms y Doble ciclo (O(n²)) tardaría 78.00 s: **8.084 veces más rápido**.

\* Tiempo estimado: con ese tamaño la variante tardaría demasiado y no se corrió; se proyectó con su complejidad.
