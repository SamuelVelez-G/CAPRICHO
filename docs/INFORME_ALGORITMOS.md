# Informe del análisis experimental de algoritmos

Generado por `herramientas/benchmark.py` el 2026-11-20 15:02 en AMD64 Family 25 Model 68 Stepping 1, AuthenticAMD · Python 3.12.10 · Windows (33.6 s).

Cada problema se resolvió de varias formas sobre datos reales de la base de Capricho (replicados para los tamaños grandes). Se midió el mejor de varios intentos con `time.perf_counter`, se contaron las operaciones básicas y se verificó que todas las variantes dieran el mismo resultado. La **pendiente** es el exponente estimado con una regresión lineal de log(tiempo) contra log(n): ≈ 0 es constante, ≈ 1 lineal, ≈ 2 cuadrático.

## Búsqueda de una transacción por ID

Buscar 200 idTxn entre n transacciones (10 % no existen). Todas las variantes dieron el mismo resultado.

| Variante | Teoría | n = 100 | n = 250 | n = 500 | n = 1.000 | n = 2.500 | n = 5.000 | n = 10.000 | n = 25.000 | n = 50.000 | Pendiente | R² |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Búsqueda lineal | O(n) | 321 µs | 805 µs | 1.77 ms | 2.95 ms | 8.17 ms | 16.12 ms | 28.96 ms | 85.56 ms | 166.10 ms | 1.0 | 0.999 |
| Búsqueda binaria (lista ordenada) | O(log n) | 111 µs | 140 µs | 175 µs | 198 µs | 214 µs | 257 µs | 281 µs | 316 µs | 351 µs | 0.18 | 0.977 |
| Índice hash (diccionario) | O(1) | 14 µs | 13 µs | 13 µs | 13 µs | 13 µs | 13 µs | 13 µs | 13 µs | 26 µs | 0.06 | 0.287 |

**Mejora:** con n = 50.000. Índice hash (diccionario) (O(1)) tarda 26 µs y Búsqueda lineal (O(n)) tarda 166.10 ms: **6.488 veces más rápido**.

## Suma de ventas

Total vendido en n transacciones. Todas las variantes dieron el mismo resultado.

| Variante | Teoría | n = 100 | n = 250 | n = 500 | n = 1.000 | n = 2.500 | n = 5.000 | n = 10.000 | n = 25.000 | n = 50.000 | Pendiente | R² |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Bucle for | O(n) | 3 µs | 6 µs | 12 µs | 24 µs | 61 µs | 122 µs | 244 µs | 612 µs | 1.22 ms | 0.98 | 1.0 |
| Divide y vencerás | O(n) | 40 µs | 101 µs | 207 µs | 424 µs | 1.06 ms | 2.15 ms | 4.20 ms | 10.50 ms | 21.48 ms | 1.01 | 1.0 |
| sum() de Python (en C) | O(n) | 1 µs | 2 µs | 4 µs | 7 µs | 17 µs | 34 µs | 69 µs | 170 µs | 338 µs | 0.96 | 1.0 |

**Mejora:** con n = 50.000. sum() de Python (en C) (O(n)) tarda 338 µs y Divide y vencerás (O(n)) tarda 21.48 ms: **64 veces más rápido**.

## Conteo de pedidos por cliente

Cuántos pedidos hizo cada cliente (n pedidos). Todas las variantes dieron el mismo resultado.

| Variante | Teoría | n = 100 | n = 250 | n = 500 | n = 1.000 | n = 2.500 | n = 5.000 | n = 10.000 | n = 25.000 | n = 50.000 | Pendiente | R² |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Doble ciclo | O(n²) | 78 µs | 435 µs | 1.55 ms | 6.88 ms | 44.01 ms | 197.76 ms | 937.51 ms | ~5.86 s* | ~23.44 s* | 2.04 | 0.999 |
| Ordenar y agrupar | O(n log n) | 11 µs | 32 µs | 68 µs | 172 µs | 520 µs | 1.80 ms | 2.62 ms | 9.02 ms | 21.48 ms | 1.23 | 0.997 |
| Diccionario | O(n) | 6 µs | 26 µs | 48 µs | 71 µs | 159 µs | 388 µs | 1.25 ms | 2.19 ms | 5.69 ms | 1.06 | 0.99 |

**Mejora:** con n = 50.000. Diccionario (O(n)) tarda 5.69 ms y Doble ciclo (O(n²)) tardaría 23.44 s: **4.117 veces más rápido**.

## Ordenamiento simple

Ordenar n montos de menor a mayor. Todas las variantes dieron el mismo resultado.

| Variante | Teoría | n = 100 | n = 250 | n = 500 | n = 1.000 | n = 2.500 | n = 5.000 | n = 10.000 | n = 25.000 | n = 50.000 | Pendiente | R² |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Burbuja | O(n²) | 266 µs | 1.85 ms | 7.82 ms | 42.07 ms | 270.67 ms | 1.12 s | ~4.50 s* | ~28.12 s* | ~112.48 s* | 2.15 | 1.0 |
| Selección | O(n²) | 179 µs | 1.09 ms | 4.92 ms | 20.27 ms | 123.57 ms | 544.12 ms | 2.15 s | ~13.45 s* | ~53.79 s* | 2.05 | 1.0 |
| Inserción | O(n²) | 179 µs | 1.33 ms | 4.67 ms | 24.08 ms | 152.91 ms | 649.59 ms | 2.64 s | ~16.51 s* | ~66.05 s* | 2.09 | 1.0 |

**Mejora:** con n = 10.000. Selección (O(n²)) tarda 2.15 s y Burbuja (O(n²)) tardaría 4.50 s: **2 veces más rápido**.

## Ordenamiento por fecha

Ordenar cronológicamente n transacciones que llegan en lote. Todas las variantes dieron el mismo resultado.

| Variante | Teoría | n = 100 | n = 250 | n = 500 | n = 1.000 | n = 2.500 | n = 5.000 | n = 10.000 | n = 25.000 | n = 50.000 | Pendiente | R² |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Inserción | O(n²) | 245 µs | 1.63 ms | 6.00 ms | 31.43 ms | 202.81 ms | 830.81 ms | ~3.32 s* | ~20.77 s* | ~83.08 s* | 2.09 | 0.999 |
| Merge sort (divide y vencerás) | O(n log n) | 248 µs | 648 µs | 871 µs | 1.94 ms | 5.50 ms | 13.32 ms | 26.51 ms | 84.35 ms | 201.02 ms | 1.08 | 0.993 |
| Quicksort | O(n log n) | 95 µs | 313 µs | 638 µs | 1.87 ms | 4.75 ms | 10.37 ms | 19.07 ms | 60.71 ms | 151.81 ms | 1.16 | 0.998 |
| Heapsort | O(n log n) | 28 µs | 79 µs | 174 µs | 550 µs | 1.70 ms | 3.01 ms | 7.08 ms | 33.81 ms | 100.23 ms | 1.3 | 0.995 |
| Timsort (sorted) | O(n log n) | 7 µs | 35 µs | 46 µs | 116 µs | 338 µs | 827 µs | 2.22 ms | 7.53 ms | 15.77 ms | 1.23 | 0.995 |

**Mejora:** con n = 50.000. Timsort (sorted) (O(n log n)) tarda 15.77 ms y Inserción (O(n²)) tardaría 83.08 s: **5.269 veces más rápido**.

## Ranking de ítems más vendidos

Top 10 de productos en n líneas de pedido. Todas las variantes dieron el mismo resultado.

| Variante | Teoría | n = 100 | n = 250 | n = 500 | n = 1.000 | n = 2.500 | n = 5.000 | n = 10.000 | n = 25.000 | n = 50.000 | Pendiente | R² |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Doble ciclo | O(n²) | 360 µs | 2.46 ms | 10.09 ms | 43.43 ms | 305.71 ms | 1.16 s | ~4.63 s* | ~28.93 s* | ~115.71 s* | 2.07 | 1.0 |
| Ordenar y agrupar | O(n log n) | 16 µs | 42 µs | 97 µs | 208 µs | 527 µs | 1.09 ms | 2.17 ms | 8.13 ms | 15.84 ms | 1.11 | 0.999 |
| Diccionario + heap | O(n) | 8 µs | 17 µs | 43 µs | 80 µs | 170 µs | 331 µs | 781 µs | 1.83 ms | 4.39 ms | 1.01 | 0.998 |

**Mejora:** con n = 50.000. Diccionario + heap (O(n)) tarda 4.39 ms y Doble ciclo (O(n²)) tardaría 115.71 s: **26.332 veces más rápido**.

## Normalizar y unificar nombres

Cuántos clientes o ítems distintos hay en n nombres mal escritos. Todas las variantes dieron el mismo resultado.

| Variante | Teoría | n = 100 | n = 250 | n = 500 | n = 1.000 | n = 2.500 | n = 5.000 | n = 10.000 | n = 25.000 | n = 50.000 | Pendiente | R² |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Comparar por pares | O(n²) | 408 µs | 1.40 ms | 4.97 ms | 22.42 ms | 133.52 ms | 604.46 ms | 2.60 s | ~16.23 s* | ~64.91 s* | 1.94 | 0.995 |
| Ordenar claves | O(n log n) | 511 µs | 829 µs | 2.45 ms | 3.78 ms | 11.62 ms | 25.72 ms | 52.43 ms | 145.74 ms | 351.82 ms | 1.07 | 0.995 |
| Conjunto de claves | O(n) | 563 µs | 930 µs | 2.33 ms | 3.95 ms | 12.29 ms | 19.99 ms | 58.13 ms | 144.40 ms | 321.22 ms | 1.05 | 0.994 |

**Mejora:** con n = 50.000. Conjunto de claves (O(n)) tarda 321.22 ms y Comparar por pares (O(n²)) tardaría 64.91 s: **202 veces más rápido**.

## Ventana deslizante (ráfagas)

Transacciones con 5 o más del mismo usuario en menos de 1 s (algoritmo crítico del detector). Todas las variantes dieron el mismo resultado.

| Variante | Teoría | n = 100 | n = 250 | n = 500 | n = 1.000 | n = 2.500 | n = 5.000 | n = 10.000 | n = 25.000 | n = 50.000 | Pendiente | R² |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Doble ciclo | O(n²) | 408 µs | 2.35 ms | 11.99 ms | 39.58 ms | 290.90 ms | 1.07 s | ~4.26 s* | ~26.63 s* | ~106.52 s* | 2.02 | 0.999 |
| Ordenar + dos punteros | O(n log n) | 20 µs | 46 µs | 90 µs | 178 µs | 459 µs | 938 µs | 1.97 ms | 5.03 ms | 11.59 ms | 1.02 | 0.999 |
| Deque por usuario (en vivo) | O(n) | 27 µs | 91 µs | 190 µs | 385 µs | 630 µs | 1.45 ms | 2.99 ms | 8.10 ms | 15.36 ms | 0.99 | 0.995 |

**Mejora:** con n = 50.000. Ordenar + dos punteros (O(n log n)) tarda 11.59 ms y Doble ciclo (O(n²)) tardaría 106.52 s: **9.193 veces más rápido**.

\* Tiempo estimado: con ese tamaño la variante tardaría demasiado y no se corrió; se proyectó con su complejidad.
