# Guía para la sustentación — viernes 2 de octubre

## 1. Antes de que empiece la prueba (15 minutos antes)

Tres terminales abiertas en la carpeta del proyecto, con el entorno activado (`.venv\Scripts\activate`).

**Terminal 1 — el servidor, con la base de datos vacía:**

```bash
python run.py --reiniciar --limpio
```

**Terminal 2 — la URL pública:**

```bash
ngrok http 5000
```

Copiar la línea `Forwarding https://xxxx.ngrok-free.app`. La URL que se le da al
profesor es: **`https://xxxx.ngrok-free.app/api/transacciones`**

**Terminal 3 — comprobar que el túnel funciona** (cambiar la URL por la de ngrok):

```bash
python herramientas/enviar_transacciones.py --servidor https://xxxx.ngrok-free.app --usuario prueba@prueba.com
```

Debe responder `201 ... APROBADA`. Si funciona, volver a dejar la base vacía (Ctrl+C
en la terminal 1 y otra vez `python run.py --reiniciar --limpio`). **ngrok no hay
que reiniciarlo**: la URL sigue siendo la misma.

En el navegador:

- `http://127.0.0.1:5000/dashboard` → ingresar con `admin@capricho.co` / `Capricho2026*`.
- `http://127.0.0.1:4040` → el inspector de ngrok: muestra cada petición que llega, con su JSON y la respuesta.

Que el computador no se suspenda y que las terminales no se cierren.

## 2. Durante la generación de transacciones (2,5 a 7 minutos)

El dashboard se actualiza solo cada 5 segundos ("En vivo"). Qué mirar:

| Qué quiere ver el profesor | Dónde está en el dashboard |
|---|---|
| Hoy / semana / mes | Primera fila: transacciones y anomalías por periodo |
| Buenas vs fraudulentas | "Transacciones buenas y fraudulentas": barra de proporción y las últimas de cada lado |
| Si el hash cuadra | "Verificación del hash": cuántas validaron y con qué método, cuántas inválidas |
| La ventana deslizante | "Ventana deslizante en acción": el último caso, animado. Botón "Deslizar otra vez" |
| % con anomalías, usuarios afectados, valor sospechoso, promedio por usuario | Fila de indicadores |
| Nuevas, abiertas, revisadas, descartadas | "Estado de las anomalías" |
| Evolución, picos, tendencias | "Evolución y tendencia" (punto rojo = pico) |
| Horas con más anomalías | Mapa de calor + "Horas con más anomalías" |
| Anomalías por nivel, casos recurrentes, métodos de pago | Las tres gráficas de barras |
| Usuarios recurrentes, múltiples transacciones | Las dos tablas |
| Línea de tiempo de una anomalía | Tabla "Anomalías" → botón **Ver** |
| Cada transacción recibida | "Todas las transacciones" (abajo), con buscador |

**Si "Hoy" se queda en 0 pero sí llegan transacciones:** el generador está usando
fechas de otros días. Cambiar arriba a **"Llegada al servidor"** (cuenta por
la hora en que llegaron) o el rango a **"Todo"**.

**Si casi todo sale "Hash inválido":** el profesor firma con otra llave. Preguntarle
cuál es, detener el servidor (Ctrl+C) y volver a arrancarlo así en PowerShell
(no se pierden datos; no usar `--reiniciar`):

```powershell
$env:CAPRICHO_LLAVES_EXTRA = "la_llave_del_profe"
python run.py
```

## 3. Qué se cumple y dónde (diapositivas 35 a 45)

| Pide | Está en |
|---|---|
| Endpoint POST que recibe la transacción (diap. 37 y 40) | `POST /api/transacciones` → `capricho/rutas/api_transacciones.py` |
| Ordenarlas cronológicamente | Lote: merge sort (`estructuras.merge_sort`). Una a una: la ventana mira vecinas antes y después, así que el orden de llegada no importa |
| Analizar por usuario, cada uno con su ventana (diap. 43) | `detector.contar_en_ventana` filtra por `usuario_id` |
| Ventana de x segundos configurable (diap. 36 a 38) | Dashboard → "Reglas de detección" (regla principal o por franja) |
| Contar y detectar si supera el límite (diap. 39 y 41) | `estructuras.max_en_ventana` (dos punteros) |
| Validar el hash (diap. 14 a 19) | `seguridad.verificar_hash` |
| Registrar anomalías | Tablas `anomalias` y `anomalias_historial` |
| Usuarios recurrentes, estadísticas, dashboard (diap. 44) | `servicios/estadisticas.py` + `/dashboard` |
| Modelo de datos (diap. 45) | `capricho/esquema.sql`: `usuarios`, `transacciones`, `anomalias` con todos sus campos |
| Métodos HTTP (diap. 2 a 13) | Productos: GET, POST, PUT, PATCH, DELETE. Reglas: PUT y PATCH |
| Logs (diap. 27 y 28) | `logs/capricho.log`: fecha, nivel, módulo.función:línea, mensaje |

## 4. Preguntas probables

**¿Qué es la ventana deslizante y por qué la usaron?**
Es mirar solo un pedazo de los datos (los últimos 3 segundos de un usuario) y moverlo. En vez de comparar cada transacción con todas las demás, que sería O(n²), cada vez que llega una se agrega a la ventana, se sacan las que quedaron por fuera y se cuenta. Cada elemento entra y sale una sola vez: O(n).

**¿Dónde está en el código?**
`capricho/estructuras.py`, función `max_en_ventana`. Dos punteros: `der` agrega la nueva, `izq` avanza sacando las viejas mientras la diferencia sea de 3 segundos o más. El conteo es `der - izq + 1`.

**¿Cómo evitan que se mezclen los usuarios?**
La consulta trae solo las transacciones de ese `usuario_id`. Cada usuario tiene su propia ventana (caso de uso 3).

**¿Y si las transacciones llegan desordenadas?**
Se traen las vecinas antes y después de la fecha de la nueva (por índice), se ubica la nueva con búsqueda binaria (`bisect`) y se busca la ventana más llena que la contenga. Si llegan en lote, se ordenan primero con merge sort.

**¿Por qué no recorren toda la tabla en cada transacción?**
Hay un índice compuesto `(usuario_id, fecha_txn)`. La consulta pide solo las de ese usuario entre `fecha - 3 s` y `fecha + 3 s`: SQLite las encuentra sin recorrer la tabla. Por eso aguanta cerca de 500 transacciones por segundo en las pruebas.

**¿Para qué sirve el hash? ¿Un hash solo no basta?**
El hash detecta que los datos cambiaron: si alguien cambia el valor de 50.000 a 60.000, el hash ya no coincide. Pero un SHA-256 solo lo puede recalcular cualquiera (diapositiva 18). Con HMAC hace falta la llave secreta, así que también prueba quién lo envió.

**¿Por qué aceptan también SHA-256 sin llave?**
Porque las diapositivas 15 a 17 lo muestran así y no sabíamos cómo firma el generador. Igual detecta cualquier dato alterado. En producción se apaga con la variable `CAPRICHO_SHA256_SIMPLE=0` y solo se acepta HMAC.

**¿Por qué responden 201 aunque la transacción sea fraude?**
Porque sí se recibió y se registró (diapositiva 41: "Anomalía → Registrar"). El resultado va en el cuerpo (`"resultado": "ANOMALIA"`). Si respondiéramos error, un generador la tomaría como fallida y podría reenviarla.

**¿Qué pasa si llega el mismo idTxn dos veces?**
Responde 409: es un posible reenvío (replay). Se detecta con un diccionario en memoria idTxn → registro: O(1).

**¿Qué pasa con 5 transacciones en el mismo segundo?**
La quinta queda RECHAZADA con anomalía RAFAGA, nivel crítico. Se mide con la fecha de cada transacción. Exactamente 1 segundo de diferencia no cuenta como "el mismo segundo".

**¿Qué niveles hay?**
Bajo: monto atípico. Medio: justo en el umbral (3 en 3 s). Alto: por encima del umbral, o precio manipulado. Crítico: ráfaga, hash inválido.

**¿Una transacción con hash inválido cuenta en la ventana?**
Sí. Los datos no son confiables, pero el intento ocurrió. Queda RECHAZADA por el hash y, si además completa la ventana, también se marca posible fraude.

**La diapositiva 38 dice "venta de 10 / 6 / 3", ¿qué hicieron?**
Lo tomamos como la ventana en segundos por franja horaria. Cada franja tiene ventana y umbral editables en el dashboard, así que si la intención era 10, 6 y 3 transacciones, se cambia sin tocar código. Por defecto dejamos la regla de la diapositiva 39 (3 en 3 s) porque con ella los ejemplos de las diapositivas 39 y 42 dan exactamente lo esperado.

**¿Cómo cambian la configuración? ¿Diferencia entre PUT y PATCH?**
Dashboard → "Reglas de detección". PUT reemplaza toda la configuración: si falta un campo, responde 422. PATCH manda solo lo que cambió.

**¿Cómo evitan la inyección SQL?**
Todas las consultas usan parámetros `?`: SQLite recibe los datos aparte de la instrucción y nunca los ejecuta. Además, una capa detecta patrones como `' OR 1=1` o `DROP TABLE`, responde 400 y lo deja en la pila de errores.

**¿Por qué la pila para los errores y la cola para los pedidos?**
Pedidos: el primero que paga es el primero que se prepara (FIFO). Errores: lo más urgente es lo que acaba de pasar (LIFO).

**¿Qué estructuras de los trabajos anteriores usaron?**
Índice hash O(1) (trabajo 1): usuarios por correo y transacciones por idTxn. Cola, pila y grafo con Dijkstra (trabajo 2): pedidos, errores y domicilios desde Aranjuez.

**¿Dónde se aplica divide y vencerás?**
Merge sort para ordenar lotes cronológicamente, y `mayor_por_division` para encontrar la transacción sospechosa de mayor valor (diapositiva 24).

**¿Cómo guardan las contraseñas?**
Con scrypt y una sal aleatoria de 16 bytes. No con SHA-256 solo, porque es rápido a propósito y permitiría probar millones de claves por segundo.

**¿Qué pasa si alguien cambia el precio en el localStorage?**
El servidor recalcula todo con los precios de la base de datos. Si no coincide, rechaza la compra (409) y la registra como anomalía PRECIO_MANIPULADO.

**¿Por qué Flask y SQLite?**
Todo es local, como pidió el profesor. SQLite no necesita instalar un servidor, y Flask es liviano. En las pruebas de carga aguantó cerca de 500 transacciones por segundo sin perder ninguna.

**¿Cómo saben que funciona?**
50 pruebas automáticas (`python -m unittest discover -s tests -t .`): los casos de uso 1, 2 y 3, ráfaga, hash, replay, formatos del generador, formularios y métodos HTTP.

## 5. Si algo falla

| Problema | Qué hacer |
|---|---|
| ngrok: `ERR_NGROK_4018` o pide autenticación | Falta `ngrok config add-authtoken TU_TOKEN` |
| ngrok: `ERR_NGROK_8012` (no conecta) | El servidor no está corriendo en el puerto 5000: revisar la terminal 1 |
| "Address already in use" al arrancar | Ya hay otro `python run.py` abierto: cerrarlo o usar `--puerto 5001` (y `ngrok http 5001`) |
| El profesor ve una página de aviso de ngrok en el navegador | Es normal en la versión gratuita: clic en "Visit Site". A los scripts no les sale |
| Todo sale "Hash inválido" | Preguntar la llave y usar `CAPRICHO_LLAVES_EXTRA` (sección 2) |
| Llegan transacciones pero no se ven | Rango "Todo" o "Llegada al servidor" en el dashboard |
| Ver exactamente qué mandó el generador | `http://127.0.0.1:4040` (inspector de ngrok) o "Todas las transacciones" |
| Ver errores de formato que rechazamos (422) | Operación → "Pila de errores", o `logs/capricho.log` |
| Ngrok no funciona | Plan B sin cuenta: `cloudflared tunnel --url http://localhost:5000` |
