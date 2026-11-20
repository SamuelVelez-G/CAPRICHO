# Capricho — Informe de la entrega final

Programación Avanzada · Institución Universitaria Pascual Bravo · noviembre de 2026

## 1. Contexto y problema

Capricho (granizado de café artesanal, Aranjuez, Medellín) vende por la caja,
la web, la app y domicilios. Como cualquier negocio, sus datos se generan en
muchos canales y tienen los problemas del enunciado:

| Problema del enunciado | Cómo aparece en Capricho | Qué lo resuelve |
|---|---|---|
| Calidad de datos | Clientes registrados dos veces con el correo en mayúsculas, celulares con +57 o guiones, un ítem repetido, un precio con un cero de más | Limpieza y calidad (`/calidad`) |
| Errores y fraude | Comprobantes falsos o reutilizados, descuentos abusados y anulaciones de facturas ya cobradas (un empleado), ráfagas, cuentas tomadas | Integridad, estadística por usuario, reglas e IA |
| Volumen | Miles de operaciones que hay que buscar, ordenar, contar y analizar | Algoritmos medidos hasta 50.000 datos |
| Control | ¿Se modificó una factura? ¿El pago corresponde a su comprobante? ¿El usuario se comporta raro? | Hash encadenado, comprobantes firmados, alertas |

**Objetivo general cumplido:** una plataforma que recibe, valida, procesa,
analiza, clasifica y predice las operaciones (pedidos, facturas, pagos y
transacciones) con algoritmos de distintas complejidades, análisis de datos,
IA sin LLM y mecanismos de integridad y seguridad.

## 2. Arquitectura

```
Navegador (HTML + JS)  ──►  Flask (rutas/)  ──►  servicios/  ──►  SQLite (esquema.sql)
     │                                    │
     │  Simple Statistics (vendor/)       └──►  ia/  (Keras + TensorFlow, inferencia en NumPy)
     │
POST /api/transacciones (profesor, ngrok) ─► detector: firma → reglas → estadística → clasificador → monto → autoencoder
```

- **Backend:** Python 3.12, Flask 3.1, SQLite en modo WAL con consultas parametrizadas.
- **IA:** Keras 3.15 sobre TensorFlow 2.21 para entrenar; NumPy para evaluar en vivo.
- **Frontend:** HTML y JavaScript propios (gráficas SVG hechas a mano) y la librería Simple Statistics 7.8.8.
- **Seguridad (primera entrega):** contraseñas con scrypt, CSRF, CSP sin JavaScript en línea, detección de inyección SQL, validación en el servidor de todo lo que llega y límite de peticiones por IP con ventana deslizante.

## 3. Base de datos (5 %)

`capricho/esquema.sql` define 16 tablas con llaves foráneas, restricciones
CHECK, índices compuestos y versión de esquema (`PRAGMA user_version = 2`; una
base anterior se respalda sola al arrancar).

| Grupo | Tablas |
|---|---|
| Operación | `usuarios` (roles), `categorias`, `productos` (ítems con stock), `pedidos`, `pedido_items`, `facturas`, `pagos`, `movimientos_inventario` |
| Antifraude | `transacciones` (con la probabilidad de la red y el análisis completo), `anomalias`, `anomalias_historial`, `alertas` |
| Análisis | `calidad_reportes`, `benchmarks` |
| Soporte | `eventos` (pila de errores), `configuracion` |

## 4. Módulos operativos (15 %)

Página `/gestion` y API REST con GET, POST, PUT, PATCH y DELETE:

| Requisito | Implementación |
|---|---|
| CRUD de usuarios con roles | `/api/usuarios`: administrador, empleado (caja) y cliente. Contraseña con scrypt. Quien tiene historial no se borra: se desactiva. Nadie puede quitarse su propio rol de administrador ni dejar el sistema sin administradores |
| CRUD de categorías | `/api/categorias`: la unicidad se revisa con el nombre normalizado ("Granizados" = "granizado ") |
| CRUD de ítems | `/api/productos`: categoría, tipo de venta, precio, stock y stock mínimo; cada cambio de stock queda en `movimientos_inventario` |
| Pedidos con varios ítems, canal y estado, que descuentan inventario | `/api/caja/pedidos` (caja, app, domicilio, web) y la tienda web. El inventario se revisa antes y se descuenta con `UPDATE ... WHERE stock >= ?` para no quedar en negativo aunque lleguen dos ventas a la vez. Anular devuelve el inventario |
| Facturas con impuestos, descuentos y número consecutivo | `servicios/facturacion.py`: consecutivo FV-000001 asignado dentro de la misma transacción de SQLite; impuesto nacional al consumo del 8 % incluido en el precio (base + impuesto = total); descuento con motivo obligatorio |
| Pagos con distintos métodos y comprobante | `servicios/pagos.py`: efectivo, tarjeta, Nequi, Daviplata, PSE y transferencia. Los de transferencia exigen comprobante (PDF, PNG o JPG, revisado por su contenido y no por la extensión) |

## 5. Algoritmos y análisis experimental (30 %)

`capricho/algoritmos.py` resuelve cada problema del enunciado de varias formas;
`servicios/benchmark.py` las mide con **datos del sistema** (transacciones,
pedidos, ítems y clientes reales, replicados para los tamaños grandes),
cuenta las operaciones, **verifica que todas den el mismo resultado** y estima
la complejidad observada con una regresión lineal de log(tiempo) contra log(n).

| Problema | Variantes | Pendiente medida | Mejora con n = 50.000 |
|---|---|---|---|
| Búsqueda de una transacción por ID | lineal O(n) · binaria O(log n) · índice hash O(1) | 1,0 · 0,17 · 0,04 | 6.488× (166 ms → 26 µs) |
| Suma de ventas | bucle · divide y vencerás · `sum()` en C, todas O(n) | ≈ 1,0 las tres | 64× (misma complejidad, otra constante) |
| Conteo de pedidos por cliente | doble ciclo O(n²) · ordenar y agrupar O(n log n) · diccionario O(n) | 2,0 · 1,15 · 1,03 | 4.117× |
| Ordenamiento simple | burbuja, selección, inserción, todas O(n²) | 2,09 · 1,99 · 2,01 | 2× (solo cambia la constante) |
| Ordenamiento por fecha | inserción O(n²) · merge sort · quicksort · heapsort · Timsort O(n log n) | 1,99 · 1,13 · 1,14 · 1,2 · 1,2 | 5.269× |
| Ranking de ítems más vendidos | doble ciclo O(n²) · ordenar y agrupar O(n log n) · diccionario + heap O(n) | 1,98 · 1,05 · 0,98 | 26.332× |
| Normalizar y unificar nombres | por pares O(n²) · ordenar claves O(n log n) · conjunto O(n) | 1,86 · 1,03 · 1,04 | 202× |
| Ventana deslizante (ráfagas) | doble ciclo O(n²) · ordenar + dos punteros · deque por usuario O(n) | 2,01 · 0,99 · 1,0 | 9.193× |

Las tablas completas (cada tamaño, cada variante, R² y operaciones contadas)
están en [docs/INFORME_ALGORITMOS.md](docs/INFORME_ALGORITMOS.md) y en la
página `/algoritmos` con gráficas log-log. Lo que se concluye:

- La teoría se cumple en los datos: pendiente ≈ 2 para O(n²), ≈ 1 para O(n) y
  O(n log n) (el log n sube la pendiente a 1,1-1,2), ≈ 0 para O(1) y O(log n).
- Misma complejidad no es mismo tiempo: `sum()` está escrita en C y es 64 veces
  más rápida que la versión recursiva, aunque las dos sean O(n).
- Las variantes O(n²) no se corrieron con 50.000 datos: tardarían minutos. Su
  tiempo se proyectó con su complejidad a partir del último tamaño medido.

**Optimización de los algoritmos críticos (documentada):**

1. **Ventana deslizante del detector:** de comparar con todas las
   transacciones (O(n²)) a pedir solo las del usuario cerca de la fecha con el
   índice compuesto `(usuario_id, fecha_txn)` y contarlas con dos punteros:
   9.193 veces más rápido con 50.000 transacciones.
2. **Búsqueda por ID:** índice hash en memoria (diccionario) reconstruido al
   arrancar: O(1) en vez de O(n).
3. **Inferencia de las redes en vivo:** llamar a Keras para una sola operación
   toma unos 4 ms; copiar los pesos a NumPy y hacer la misma cuenta toma 0,03 ms
   (unas 140 veces más rápido, con diferencias menores a una millonésima). El
   análisis completo de una transacción (reglas, estadística, tres redes) toma
   entre 1 y 3 ms.
4. **Verificación de la cadena de facturas:** todos los ítems en una sola
   consulta (no una por factura): 2.300 facturas en unos 40 ms.

## 6. Limpieza y calidad de datos (10 %)

`servicios/normalizacion.py` y `servicios/calidad.py`, página `/calidad`.

- **Normalización:** espacios, mayúsculas, tildes y plurales (`clave()`),
  nombres propios, correos, celulares colombianos (+57, guiones, paréntesis),
  métodos de pago escritos distinto ("NEQUI ", "tarjeta de crédito") y precios
  escritos de cualquier forma ("$12.000", "12,000", "6,5 mil").
- **Auditoría de lo que ya está guardado:** clientes duplicados (por correo,
  celular o nombre normalizados, con un diccionario: una pasada, O(n)), formatos
  sin normalizar, ítems repetidos, precios sospechosos (cinco veces la mediana
  de su categoría: un cero de más), categorías parecidas, facturas que no
  cuadran y métodos no estándar. Puntaje de calidad con cuatro dimensiones:
  completitud, validez, unicidad y consistencia. La corrección automática
  arregla los formatos y desactiva los duplicados evidentes (en la demo el
  puntaje sube de 96,5 a 98,3); lo que necesita criterio humano queda listado.
- **Importación con validación de esquema:** CSV o JSON de clientes o ítems
  (`datos/clientes_sucios.csv`, `datos/items_sucios.json`). Cada registro
  queda VÁLIDO, CORREGIDO, DUPLICADO o DESCARTADO, con el motivo. Ejemplo: de
  30 clientes sucios, 16 válidos, 4 corregidos, 4 duplicados y 6 descartados;
  de 20 ítems, el precio de $85.000 de un postre se corrige a $8.500 y
  "Bebidaz" se unifica con "Bebidas". Cada importación deja su reporte.

## 7. Integridad (10 %)

`servicios/integridad.py`, `servicios/comprobantes.py`, página `/integridad`.

- **Hash encadenado de facturas y pagos:** `hash = HMAC-SHA256(llave,
  hash_anterior | contenido)`. Cambiar una factura rompe su hash
  (CONTENIDO_ALTERADO); borrar o insertar una rompe el enlace de la siguiente
  (ENLACE_ROTO). Al ser HMAC, quien tenga la base de datos pero no la llave no
  puede recalcular la cadena para tapar el cambio. La página tiene un
  laboratorio que altera una factura directamente en SQLite y la verificación
  la encuentra.
- **¿El pago corresponde a su comprobante?** La pasarela simulada entrega un PDF
  con los datos del pago firmados. Al adjuntarlo se detecta: FALSO (firma que
  no cuadra), REUTILIZADO (mismo archivo o misma referencia en otro pago),
  NO_COINCIDE (otro monto u otro método) o SIN_VERIFICAR (una foto: revisión
  humana). El SHA-256 del archivo queda en la cadena de pagos: si alguien lo
  reemplaza, la verificación lo detecta.
- **Transacciones de la API:** firma HMAC-SHA256 por transacción e idTxn único
  contra reenvíos (primera entrega).

## 8. Modelos de IA (30 %)

Cuatro redes neuronales de Keras (sin LLM), entrenadas con
`herramientas/entrenar_modelos.py` y guardadas en `capricho/ia/artefactos/`.

### 8.1 Clasificador de operaciones (normal o fraudulenta)

- **Entrada:** 23 variables de la operación, el usuario, la fecha, el monto,
  el método de pago, la firma y la frecuencia (`ia/operaciones.py`). Las
  **generales** sirven con cualquier cliente; las **personales** comparan con
  su historial y quedan neutras si es nuevo.
- **Red:** Normalización → Dense 64 (ReLU) → Dropout 20 % → Dense 32 (ReLU) →
  Dropout 10 % → Dense 1 (sigmoide). 3.696 pesos.
- **Datos:** 90 días de una población simulada de 800 clientes con los
  hábitos de Capricho y 7 tipos de fraude etiquetados (cuenta tomada, cuenta
  nueva con monto alto, prueba de tarjeta, mula, ráfaga, firma inválida, monto
  extremo), más casos legítimos difíciles (clientes nuevos, pedidos grandes,
  cambios de hábito, volver a comprar el mismo día). División temporal: días
  0-62 entrenamiento, 63-75 validación, 76-89 prueba.
- **TensorFlow:** `keras.layers.Normalization` para preparar los datos,
  `tf.data` para mezclar 75/25 y **aumentar** los fraudes con ruido gaussiano,
  parada temprana sobre el AUC-PR de validación, y guardar/cargar el modelo.
  El aumento sube el F1 de 0,929 a 0,943 (recall de 87,8 % a 89,2 % y precisión
  de 98,5 % a 100 %).
- **Salida:** probabilidad de fraude, clasificación NORMAL o FRAUDULENTA
  (umbral con el mejor F1 en validación) y explicación por variables.

Resultados en los días de prueba (que ningún modelo vio):

| Detector | Detecta (todos) | Detecta (clientes nuevos) | Precisión | Falsas alarmas | F1 |
|---|---|---|---|---|---|
| Reglas de la primera entrega | 52,7 % | 55,6 % | 100 % | 0 % | 0,69 |
| Autoencoder de la exposición | 77,0 % | 88,9 % | 22,0 % | 2,64 % | 0,34 |
| **Clasificador** | **89,2 %** | **81,5 %** | **100 %** | **0 %** | **0,94** |

En pedidos grandes legítimos (una familia, una oficina) el autoencoder da falsa
alarma en el 44 % de los casos y el clasificador en ninguno: aprendió de toda
la población que un pedido grande de día y con el método habitual es normal.

**Respuesta a la observación del profesor:** el clasificador aprende de toda
la población, así que un cliente nuevo también se evalúa con lo aprendido de
todos: detecta el 81,5 % de los fraudes de cuentas nuevas sin ninguna falsa
alarma, contra 56 % de las reglas. El autoencoder detecta algo más en ese
segmento (88,9 %), pero marca el 5,6 % de los clientes nuevos legítimos y solo
el 73 % de lo que marca es fraude (F1 0,80 contra 0,90 del clasificador).
Cada decisión informa cuánto conocimiento **general** y cuánto **personal**
usó (con un cliente nuevo es 100 % general), midiendo el efecto de cada grupo
de variables en log-odds.

### 8.2 Regresión del monto esperado

Predice cuánto debería pagar un cliente según la hora, el día, el método y su
historial (la red aprende, por ejemplo, que los fines de semana se pide más).
Pérdida de error absoluto. Error típico de 45,9 % contra 48,7 % de usar la
mediana del cliente (con clientes nuevos, 95,8 % contra 100,1 %). En vivo dice
"esta operación es 16,6 veces lo esperado".

### 8.3 Predicción de demanda

Ventas del día siguiente a partir del día de la semana, ayer, la semana pasada
y el promedio de 7 días (escalados por el nivel del negocio), con aumento de
datos en `tf.data`. En 4 semanas de prueba: error promedio por día de $87.261,
contra $103.512 de la regresión lineal simple y $101.750 de "igual que la
semana pasada" (venta promedio: $702.707). El panel muestra las dos predicciones
de los próximos 7 días.

### 8.4 Anomalías por usuario con estadística simple (Simple Statistics)

- **Clientes:** cuartiles, IQR, cercas de Tukey (Q3 + 1,5·IQR) y puntaje z
  del monto frente a sus propias compras (o a la población si tiene menos de 5).
- **Empleados:** tasa diaria de descuentos y de anulaciones frente a todos
  los días de todos los empleados. En la demo solo salta Kevin Arias, el caso
  sembrado: por ejemplo, "3 anulaciones en 6 facturas hoy (50 %); lo normal está
  entre 0 % y 0 %; z = 6,8".
- **Demanda:** regresión lineal simple de las ventas diarias.
- **Dos implementaciones que coinciden:** el servidor lo calcula en Python en
  cada operación; la página `/estadistica` lo recalcula en el navegador con la
  librería Simple Statistics (mismo método de cuartiles, `quantileSorted`) y
  muestra que los resultados son idénticos.

### 8.5 El autoencoder de la exposición

Se mantiene como detector de rareza personal (¿se parece a los hábitos de
ESTE cliente?), reentrenado con TensorFlow.

## 9. Transferencia en vivo (observación del profesor)

En `/transferir` cualquiera (también desde un celular con la URL pública de
ngrok) hace una transferencia; el servidor la firma como la pasarela y la manda
al mismo detector del endpoint. En `/en-vivo` aparece en el momento, paso a
paso: validación, firma, ventana deslizante, cuartiles del cliente,
clasificador (probabilidad, factores y conocimiento general/personal), monto
esperado, autoencoder y la decisión con el tiempo que tomó. También muestra lo
que llegue por la API (el generador del profesor).

## 10. Panel (requisito funcional)

`/panel`: ventas de 30 días con su variación, ventas por día con la tendencia
lineal y las dos predicciones, ventas por canal, por hora y por día de la
semana, ranking de ítems, inventario por agotarse, alertas recientes,
puntaje de calidad, métricas de los modelos y resumen del benchmark.

## 11. Limitaciones y uso responsable

- Los modelos se entrenaron con datos simulados con los hábitos de Capricho,
  no con clientes reales: con datos reales hay que reentrenar y volver a medir.
- Aprenden lo que se les muestra. Ejemplo real del proyecto: cuando el
  simulador no tenía clientes que compraran dos veces en una hora, la red marcó
  como fraude el 19 % de las compras normales de la demo; se corrigió agregando
  ese comportamiento legítimo.
- La IA no bloquea: marca para revisión humana. Las reglas siguen bloqueando
  ráfagas y firmas falsas. Con montos de otros negocios se usa el modo "solo
  observar".
- Los comprobantes que no vienen de la pasarela (fotos) no se pueden verificar
  solos.
- La estadística por empleado necesita al menos 20 días-empleado de historia.

## 12. Cómo ejecutarlo y verificarlo

```bash
.venv\Scripts\activate
python run.py --reiniciar                       # base nueva con 9 semanas de operación
python -m unittest discover -s tests -t .       # 86 pruebas
python herramientas/entrenar_modelos.py --todo  # reentrenar las 4 redes (~2 min)
python herramientas/benchmark.py                # benchmark completo (~30 s)
```

Cuentas: `admin@capricho.co` / `Capricho2026*`, `caja@capricho.co` /
`Caja2026*`, `cliente@capricho.co` / `Cliente2026*`.
Demo estática: https://samuelvelez-g.github.io/CAPRICHO/
