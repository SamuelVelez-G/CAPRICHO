# Appresso - Python

Proyecto de estructuras de datos basado en el caso Appresso (Tu café, a un tap).

## Incluye

- Cola FIFO para solicitudes/pedidos pendientes.
- Pila LIFO para operaciones recientes.
- Grafo ponderado para representar ciudades y distancias.
- Algoritmo de Dijkstra para encontrar la ruta de menor distancia.
- Cálculo de distancia recorrida.
- Estimación de litros de gasolina.
- Cálculo del costo de gasolina.
- Historial de entregas.
- Menú de consola.

## Requisitos

Python 3.10 o superior.

## Ejecutar

Desde la carpeta del proyecto:

```bash
python main.py
```

## Datos de gasolina

Valores iniciales de demostración:
- Rendimiento: 40 km/L
- Gasolina: $16.000/L

Se pueden modificar desde la opción 8.

## Estructuras usadas

### Cola
Los pedidos se atienden en el orden en que llegan: FIFO.

### Pila
Las operaciones recientes se muestran de la más reciente a la más antigua: LIFO.

### Grafo
Las ciudades son vértices/nodos y las carreteras son aristas con distancia.

### Dijkstra
Se usa para obtener la ruta de menor distancia entre dos ciudades.
