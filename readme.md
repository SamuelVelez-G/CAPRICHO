# Capricho — Granizado de café artesanal

Tienda en línea de **Capricho** (Aranjuez, Cra. 50c # 92-84, Medellín) con un
**sistema de detección de fraude** basado en *ventana deslizante*.

Proyecto de Programación Avanzada · Institución Universitaria Pascual Bravo.
Resuelve lo que pide *Técnicas de resolución de problemas* (caso Appresso) y
reúne lo mejor de los dos trabajos anteriores:

| Viene de | Qué se usa aquí |
|---|---|
| Trabajo 1 (complejidad) | **Búsqueda por índice hash O(1)**: usuarios por correo y transacciones por `idTxn` |
| Trabajo 2 (estructuras) | **Cola FIFO** para los pedidos, **Pila LIFO** para los errores y **grafo + Dijkstra** para los domicilios |
| Técnicas de resolución | Métodos HTTP, hash HMAC-SHA256, validación, divide y vencerás, búsqueda eficiente, logs y **ventana deslizante** |

---

## Cómo ejecutarlo

Necesita **Python 3.10 o superior**.

```bash
python -m venv .venv
```

En Windows:

```bash
.venv\Scripts\activate
```

En Mac o Linux:

```bash
source .venv/bin/activate
```

Después:

```bash
pip install -r requirements.txt
```

```bash
python run.py
```

Abre **http://127.0.0.1:5000**. La primera vez se crea la base de datos
(`instancia/capricho.db`) con 9 semanas de datos de demostración.

| Rol | Correo | Contraseña |
|---|---|---|
| Administrador (dashboard y operación) | `admin@capricho.co` | `Capricho2026*` |
| Cliente de prueba | `cliente@capricho.co` | `Cliente2026*` |

Para empezar de cero con 9 semanas de datos de demostración nuevos:

```bash
python run.py --reiniciar
```

Para la **prueba del profesor**: base de datos sin transacciones (solo productos
y cuentas), así el dashboard muestra únicamente lo que él envíe:

```bash
python run.py --reiniciar --limpio
```

Pruebas automáticas (50 pruebas: casos de uso, formatos del generador, seguridad, formularios y métodos HTTP):

```bash
python -m unittest discover -s tests -t .
```

---

## URL pública con ngrok (para la prueba del profesor)

El generador del profesor envía las transacciones desde su equipo, así que el
endpoint necesita una URL pública. Con el servidor corriendo en una terminal:

1. Crear una cuenta gratis en ngrok.com y copiar el *authtoken* del panel.
2. Instalar ngrok (una sola vez): `winget install Ngrok.Ngrok`
3. Registrar el token (una sola vez): `ngrok config add-authtoken TU_TOKEN`
4. En otra terminal: `ngrok http 5000`
5. Copiar la línea `Forwarding https://xxxx.ngrok-free.app` y darle al profesor
   **`https://xxxx.ngrok-free.app/api/transacciones`**.

Mientras corre, **http://127.0.0.1:4040** muestra cada petición que llega por
el túnel con su cuerpo y la respuesta: sirve para ver en vivo qué manda el
generador. La URL cambia cada vez que se reinicia ngrok (salvo que se use el
dominio fijo gratuito del panel). Las dos terminales y el computador deben
quedar encendidos durante la prueba.

Alternativa sin cuenta: `cloudflared tunnel --url http://localhost:5000`.

---

## Páginas

| Ruta | Para qué |
|---|---|
| `/` | Tienda: menú, arma tu granizado, mapa de domicilios |
| `/pagar` | Pago del carrito (necesita sesión) |
| `/laboratorio` | **Para el profesor**: formulario y escenarios para mandar pagos buenos y fraudulentos |
| `/dashboard` | Monitoreo antifraude (administrador) |
| `/operacion` | Cola de pedidos, pila de errores, grafo, búsqueda por índice y CRUD de productos (administrador) |

---

## El detector de fraude

Cada transacción llega a `POST /api/transacciones` con el formato de la diapositiva 40:

```json
{
  "idTxn": 10001,
  "user": "aa@aa.com",
  "date": "2026-09-23T10:30:01.120",
  "value": 50000,
  "paymentMethod": "Tarjeta",
  "hash": "ec37a3a3e8e2566a6ae41d5c807d11db5be922a231d..."
}
```

El algoritmo (diapositiva 41), en `capricho/servicios/detector.py`:

1. ¿El `idTxn` ya existe? → **409** (reenvío / *replay*). Se busca en el índice hash, O(1).
2. ¿El hash coincide? Si no → **RECHAZADA**, anomalía `HASH_INVALIDO` (crítica).
3. Se identifica al usuario (índice hash por correo).
4. Se traen **solo** sus transacciones cercanas con el índice `(usuario_id, fecha_txn)` y se corre la ventana deslizante con dos punteros. Cuentan todas, también las de hash inválido: el intento ocurrió.
5. **5 o más en menos de 1 segundo** → **RECHAZADA**, anomalía `RAFAGA` (crítica). Se cuenta con la fecha de cada transacción; opcionalmente también con la hora de llegada al servidor (apagado por defecto, porque un generador que envía muy rápido produciría ráfagas falsas).
6. **Umbral o más dentro de la ventana** → **SOSPECHOSA**, anomalía `POSIBLE_FRAUDE` (media; alta si supera el umbral).
7. Monto igual o mayor a $300.000 → **SOSPECHOSA**, anomalía `MONTO_ATIPICO` (baja).
8. Se registra la transacción y sus anomalías.

Cada usuario tiene su propia ventana (caso de uso 3). Las transacciones pueden
llegar desordenadas: la ventana revisa vecinas antes y después.

La respuesta es **201** siempre que la transacción quedó registrada, sea normal
o fraudulenta (diapositiva 41: "Anomalía → Registrar"). El resultado va en el cuerpo:

```json
{ "ok": true, "resultado": "ANOMALIA", "estado": "SOSPECHOSA", "anomalias": ["POSIBLE_FRAUDE"],
  "transaccion": { "...": "detalle completo y el análisis de la ventana" } }
```

Solo responde error cuando la petición misma está mal: **422** campos nulos o
con formato inválido, **400** inyección SQL, **409** `idTxn` repetido. El
endpoint también acepta una lista de transacciones (se procesa como lote) y las
rutas alternativas `/transacciones` y `/api/transactions`.

### Reglas configurables (PUT y PATCH en `/api/configuracion` o desde el dashboard)

- **Por franja horaria** (por defecto, diapositiva 38): la ventana depende de la
  hora de la transacción, con el umbral de la diapositiva 39 (3 o más):

  | Franja | Horario | Ventana |
  |---|---|---|
  | Mañana | 05:00:01 a 12:00:00 | 10 s |
  | Tarde-noche | 12:00:01 a 20:00:00 | 6 s |
  | Noche-madrugada | 20:00:01 a 05:00:00 | 3 s |

  La diapositiva dice "venta de 10 / 6 / 3": el profesor confirmó que es "ventana".
- **Regla fija** (diapositiva 39): 3 o más transacciones en 3 segundos a cualquier hora.

Cada franja tiene su ventana y su umbral editables desde el dashboard. La franja
se elige con la hora de la transacción que llega (campo `date`).

### Cómo se verifica el hash

Como no sabemos con qué script firma el generador del profesor, el servidor
acepta las formas que muestran las diapositivas y rechaza todo lo demás:

- **HMAC-SHA256** (diapositiva 19) con la llave propia `capricho_llave_secreta_2026`
  o con la de la diapositiva, `mi_llave_privada_123`. Si el profesor da otra
  llave, en PowerShell: `$env:CAPRICHO_LLAVES_EXTRA = "su_llave"` antes de `python run.py`.
- **SHA-256 sin llave** (diapositivas 15 a 17). Se puede exigir solo HMAC con
  `$env:CAPRICHO_SHA256_SIMPLE = "0"`.
- Sobre los 5 campos de la diapositiva 40 o sobre todos los campos menos `hash`,
  con llaves ordenadas (Python) o en el orden recibido (`JSON.stringify` de JavaScript).

Cualquier dato alterado después de firmar cambia el hash y se detecta. El
dashboard muestra en "Verificación del hash" cómo se validó cada transacción.

### Cómo firmar una transacción (diapositiva 19)

```python
import hashlib, hmac, json

LLAVE = b"capricho_llave_secreta_2026"
txn = {"idTxn": 10001, "user": "aa@aa.com", "date": "2026-09-23T10:30:01.120",
       "value": 50000, "paymentMethod": "Tarjeta"}
datos = json.dumps(txn, sort_keys=True, separators=(",", ":"))
txn["hash"] = hmac.new(LLAVE, datos.encode(), hashlib.sha256).hexdigest()
```

O desde la terminal, con el servidor corriendo:

```bash
python herramientas/enviar_transacciones.py --usuario r@r.com --repetir 5 --intervalo 100
```

---

## Seguridad de los formularios

| Requisito | Cómo se cumple |
|---|---|
| Validación en todo | Las mismas reglas en el navegador (`static/js/validacion.js`) y en el servidor (`capricho/validaciones.py`). La del servidor es la que manda. |
| Nombre de más de 3 letras | Solo letras y espacios, mínimo 4 letras (constante `NOMBRE_MIN_LETRAS`). |
| Ningún campo nulo | Todo campo obligatorio se rechaza si llega `null`, vacío o solo con espacios. También se revisan los tipos (`true` no pasa como número). |
| Inyección SQL | Todas las consultas usan parámetros `?`. Además, una capa detecta patrones (`' OR 1=1`, `--`, `UNION SELECT`, `DROP TABLE`…), bloquea con **400** y lo deja en la pila de errores. |
| Contraseñas con hash | `scrypt` con sal aleatoria de 16 bytes. Nunca se guarda la contraseña. Tras 5 intentos fallidos se bloquea 5 minutos. |
| Precio validado en el servidor | El servidor recalcula cada línea con los precios de la base de datos. Si el total del navegador no coincide, la compra se rechaza (**409**) y queda la anomalía `PRECIO_MANIPULADO`. |
| No cambiar el valor desde el localStorage | El carrito del localStorage es solo para mostrar. Al cargar la página se compara con los precios oficiales y se corrige; al pagar, el servidor rechaza cualquier diferencia. |
| 5 en el mismo segundo | Regla `RAFAGA` del detector (por usuario) y además un límite de peticiones por IP. |

También: token CSRF en toda petición con sesión, cookie `HttpOnly` y `SameSite`,
cabeceras `Content-Security-Policy` sin JavaScript en línea, y todo dato se
pinta con `textContent` (sin `innerHTML`), lo que evita XSS.

---

## API

| Método | Ruta | Descripción |
|---|---|---|
| POST | `/api/transacciones` | Recibe una transacción o una lista (pasarela, generador del profesor, laboratorio) |
| POST | `/api/transacciones/lote` | Lista desordenada: se ordena con merge sort y se analiza |
| GET | `/api/transacciones` | Listado con filtros (admin) |
| GET | `/api/transacciones/<idTxn>` | Búsqueda por índice hash (admin) |
| GET | `/api/productos` · `/api/productos/<id>` | Consultar |
| POST | `/api/productos` | Crear (admin) |
| PUT | `/api/productos/<id>` | Reemplazar completo (admin) |
| PATCH | `/api/productos/<id>` | Actualizar parcialmente, ej. solo el precio (admin) |
| DELETE | `/api/productos/<id>` | Eliminar (admin) |
| POST | `/api/pedidos` | Comprar (cliente con sesión) |
| GET | `/api/pedidos/cola` · POST `/api/pedidos/cola/atender` | Cola FIFO (admin) |
| GET | `/api/domicilios/cotizar?barrio=` | Ruta más corta con Dijkstra y tarifa |
| GET | `/api/dashboard?rango=hoy\|7d\|30d\|90d\|todo` | Estadísticas (admin) |
| GET · PATCH | `/api/anomalias/<id>` | Detalle y cambio de estado (admin) |
| GET · PUT · PATCH | `/api/configuracion` | Reglas del detector |
| GET · POST | `/api/eventos` · `/api/eventos/desapilar` | Pila de errores (admin) |

---

## Estructura

```
capricho/
  config.py            configuración (llaves, límites, cuentas de demo)
  esquema.sql          tablas: usuarios, transacciones, anomalias (diapositiva 45) y las de la tienda
  estructuras.py       Cola, Pila, IndiceHash, Grafo+Dijkstra, merge sort, ventana deslizante
  seguridad.py         scrypt, HMAC, inyección SQL, CSRF, cabeceras
  validaciones.py      reglas de todos los formularios y del JSON de transacciones
  registro.py          logs (qué, cuándo, dónde) y pila de errores
  semilla.py           datos de demostración que pasan por el detector real
  servicios/           detector, pedidos, catálogo, domicilios, estadísticas, anomalías
  rutas/               endpoints de la API y páginas
  templates/ static/   interfaz (HTML, CSS y JavaScript sin librerías externas)
herramientas/          script para enviar transacciones desde la terminal
tests/                 pruebas automáticas
run.py                 arranque
```

El log queda en `logs/capricho.log`, con el formato
`fecha | nivel | módulo.función:línea | mensaje`.

---

## Diseño

Colores tomados del logo, el letrero y el menú: vino `#75383f`, vino oscuro
`#633035` (las rayas), crema `#ffdb94` y caramelo `#96502e`. Títulos en
*Fraunces* (cercana a la letra del logo y del menú) y texto en *Barlow* (como
"GRANIZADO DE CAFÉ ARTESANAL"). Las gráficas del dashboard están hechas en SVG
propio, con una paleta validada para daltonismo, y cada una tiene vista de tabla.
