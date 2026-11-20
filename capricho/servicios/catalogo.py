"""
Catálogo de ítems, inventario y cálculo del precio EN EL SERVIDOR.

El navegador muestra precios, pero nunca los decide. Al comprar, el
servidor vuelve a calcular todo desde la base de datos; si el total que
mandó el navegador no coincide (alguien editó el localStorage o el HTML),
la compra se rechaza y queda registrada como anomalía.

Cada venta descuenta inventario y cada anulación lo devuelve; los dos
quedan en movimientos_inventario para poder auditar el stock.
"""

from ..db import fila_a_dict, filas_a_dicts
from ..errores import ErrorConflicto, ErrorNoEncontrado, ErrorValidacion
from . import categorias
from ..registro import logger
from ..tiempo import a_texto, ahora

SABORES = ("Café artesanal", "Capuchino")
MAX_ADICIONES = 3
IMAGENES = ("menu.jpg", "capuchino.jpg", "cargador.jpg")


def _publico(producto: dict) -> dict:
    producto = dict(producto)
    producto["activo"] = bool(producto["activo"])
    return producto


CONSULTA = """SELECT p.*, c.nombre AS categoria, p.stock <= p.stock_minimo AS stock_bajo
              FROM productos p JOIN categorias c ON c.id = p.categoria_id"""


def listar(db, incluir_inactivos=False):
    consulta = CONSULTA
    if not incluir_inactivos:
        consulta += " WHERE p.activo = 1"
    consulta += " ORDER BY p.tipo DESC, c.nombre, p.precio, p.nombre"
    productos = [_publico(p) for p in filas_a_dicts(db.execute(consulta))]
    for producto in productos:
        producto["stock_bajo"] = bool(producto["stock_bajo"])
    return productos


def obtener(db, producto_id):
    producto = fila_a_dict(db.execute(CONSULTA + " WHERE p.id = ?", (producto_id,)).fetchone())
    if producto is None:
        raise ErrorNoEncontrado(f"No existe el producto {producto_id}")
    producto = _publico(producto)
    producto["stock_bajo"] = bool(producto["stock_bajo"])
    return producto


def _revisar_coherencia(db, datos):
    if datos["tipo"] == "GRANIZADO" and not datos.get("onzas"):
        raise ErrorValidacion({"onzas": "Un granizado debe indicar sus onzas"})
    if datos["tipo"] != "GRANIZADO" and datos.get("onzas"):
        raise ErrorValidacion({"onzas": "Solo los granizados llevan onzas (usa null)"})
    try:
        categorias.obtener(db, datos["categoria_id"])
    except ErrorNoEncontrado:
        raise ErrorValidacion({"categoria_id": "La categoría no existe"}) from None


def _nombre_libre(db, nombre, excepto_id=None):
    fila = db.execute("SELECT id FROM productos WHERE nombre = ? AND id != ?",
                      (nombre, excepto_id or 0)).fetchone()
    if fila:
        raise ErrorConflicto("Ya existe un producto con ese nombre", {"nombre": "Nombre repetido"})


def crear(db, datos):
    _revisar_coherencia(db, datos)
    _nombre_libre(db, datos["nombre"])
    momento = a_texto(ahora())
    cursor = db.execute(
        """INSERT INTO productos (nombre, descripcion, categoria_id, tipo, precio, onzas, imagen, stock,
                                  stock_minimo, activo, fecha_creacion, fecha_actualizacion)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (datos["nombre"], datos["descripcion"], datos["categoria_id"], datos["tipo"], datos["precio"],
         datos["onzas"], datos["imagen"], datos["stock"], datos["stock_minimo"], int(datos["activo"]),
         momento, momento),
    )
    if datos["stock"]:
        _movimiento(db, cursor.lastrowid, datos["stock"], "ENTRADA", None, None, momento)
    db.commit()
    logger.info("POST producto #%s %s", cursor.lastrowid, datos["nombre"])
    return obtener(db, cursor.lastrowid)


def reemplazar(db, producto_id, datos):
    """PUT: se reemplazan TODOS los campos."""
    actual = obtener(db, producto_id)
    _revisar_coherencia(db, datos)
    _nombre_libre(db, datos["nombre"], producto_id)
    momento = a_texto(ahora())
    db.execute(
        """UPDATE productos SET nombre = ?, descripcion = ?, categoria_id = ?, tipo = ?, precio = ?, onzas = ?,
                                imagen = ?, stock = ?, stock_minimo = ?, activo = ?, fecha_actualizacion = ?
           WHERE id = ?""",
        (datos["nombre"], datos["descripcion"], datos["categoria_id"], datos["tipo"], datos["precio"],
         datos["onzas"], datos["imagen"], datos["stock"], datos["stock_minimo"], int(datos["activo"]),
         momento, producto_id),
    )
    if datos["stock"] != actual["stock"]:
        _movimiento(db, producto_id, datos["stock"] - actual["stock"], "AJUSTE", None, None, momento)
    db.commit()
    logger.info("PUT producto #%s", producto_id)
    return obtener(db, producto_id)


def actualizar(db, producto_id, cambios):
    """PATCH: solo cambian los campos enviados.

    Los nombres de columna salen de una lista fija (CAMPOS_PRODUCTO, ya
    validada), nunca de lo que escribió el usuario; los valores van como
    parámetros.
    """
    actual = obtener(db, producto_id)
    fusion = {**actual, **cambios}
    _revisar_coherencia(db, fusion)
    if "nombre" in cambios:
        _nombre_libre(db, cambios["nombre"], producto_id)
    momento = a_texto(ahora())
    columnas = ", ".join(f"{campo} = ?" for campo in cambios)
    valores = [int(v) if isinstance(v, bool) else v for v in cambios.values()]
    db.execute(f"UPDATE productos SET {columnas}, fecha_actualizacion = ? WHERE id = ?",
               (*valores, momento, producto_id))
    if "stock" in cambios and cambios["stock"] != actual["stock"]:
        _movimiento(db, producto_id, cambios["stock"] - actual["stock"], "AJUSTE", None, None, momento)
    db.commit()
    logger.info("PATCH producto #%s campos=%s", producto_id, list(cambios))
    return obtener(db, producto_id)


def eliminar(db, producto_id):
    obtener(db, producto_id)
    usado = db.execute("SELECT COUNT(*) FROM pedido_items WHERE producto_id = ?", (producto_id,)).fetchone()[0]
    if usado:
        raise ErrorConflicto(
            f"El producto aparece en {usado} pedidos y no se puede borrar sin perder el historial. "
            "Desactívalo con PATCH {\"activo\": false}."
        )
    db.execute("DELETE FROM movimientos_inventario WHERE producto_id = ?", (producto_id,))
    db.execute("DELETE FROM productos WHERE id = ?", (producto_id,))
    db.commit()
    logger.info("DELETE producto #%s", producto_id)


def cotizar(db, items, solo_granizados=True):
    """Calcula cada línea con los precios de la base de datos.

    Devuelve (lineas, subtotal, diferencias). `diferencias` lista las
    líneas donde el precio que mandó el navegador no coincide.
    La tienda web solo vende granizados con adiciones; la caja vende
    cualquier ítem (solo_granizados=False) y en ese caso no hay precio del
    navegador que comparar.
    """
    ids = {item["producto_id"] for item in items}
    for item in items:
        ids.update(item["adiciones"])
    marcadores = ",".join("?" for _ in ids)
    productos = {
        fila["id"]: dict(fila)
        for fila in db.execute(f"SELECT * FROM productos WHERE id IN ({marcadores}) AND activo = 1", tuple(ids))
    }

    errores = {}
    lineas, diferencias = [], []
    subtotal = 0
    for posicion, item in enumerate(items):
        granizado = productos.get(item["producto_id"])
        if granizado is None or (solo_granizados and granizado["tipo"] != "GRANIZADO"):
            errores[f"items[{posicion}].producto_id"] = "El producto no existe o no está disponible"
            continue
        if item["adiciones"] and granizado["tipo"] != "GRANIZADO":
            errores[f"items[{posicion}].adiciones"] = "Solo los granizados llevan adiciones"
            continue
        adiciones = []
        for adicion_id in item["adiciones"]:
            adicion = productos.get(adicion_id)
            if adicion is None or adicion["tipo"] != "ADICION":
                errores[f"items[{posicion}].adiciones"] = f"La adición {adicion_id} no existe"
                break
            adiciones.append({"id": adicion["id"], "nombre": adicion["nombre"], "precio": adicion["precio"]})
        precio_unitario = granizado["precio"] + sum(a["precio"] for a in adiciones)
        total_linea = precio_unitario * item["cantidad"]
        subtotal += total_linea
        lineas.append({
            "producto_id": granizado["id"], "nombre": granizado["nombre"],
            "sabor": item.get("sabor") if granizado["tipo"] == "GRANIZADO" else None,
            "adiciones": adiciones, "cantidad": item["cantidad"],
            "precio_unitario": precio_unitario, "subtotal": total_linea,
        })
        if item.get("precio_unitario") is not None and item["precio_unitario"] != precio_unitario:
            diferencias.append({
                "linea": posicion, "producto": granizado["nombre"],
                "precio_enviado": item["precio_unitario"], "precio_real": precio_unitario,
            })
    if errores:
        raise ErrorValidacion(errores)
    return lineas, subtotal, diferencias


# =============================================================================
#  Inventario
# =============================================================================

def necesidades(lineas) -> dict:
    """Cuántas unidades de cada ítem consume un pedido (el granizado y sus adiciones)."""
    total = {}
    for linea in lineas:
        total[linea["producto_id"]] = total.get(linea["producto_id"], 0) + linea["cantidad"]
        for adicion in linea["adiciones"]:
            total[adicion["id"]] = total.get(adicion["id"], 0) + linea["cantidad"]
    return total


def revisar_stock(db, requeridas: dict):
    if not requeridas:
        return
    marcadores = ",".join("?" for _ in requeridas)
    faltantes = {}
    for fila in db.execute(f"SELECT id, nombre, stock FROM productos WHERE id IN ({marcadores})", tuple(requeridas)):
        if fila["stock"] < requeridas[fila["id"]]:
            faltantes[fila["nombre"]] = f"quedan {fila['stock']}, se piden {requeridas[fila['id']]}"
    if faltantes:
        raise ErrorConflicto("No hay inventario suficiente: " + "; ".join(f"{n} ({d})" for n, d in faltantes.items()),
                             {"inventario": faltantes})


def _movimiento(db, producto_id, cantidad, motivo, pedido_id, usuario_id, momento):
    db.execute("""INSERT INTO movimientos_inventario (producto_id, cantidad, motivo, pedido_id, usuario_id, fecha)
                  VALUES (?, ?, ?, ?, ?, ?)""", (producto_id, cantidad, motivo, pedido_id, usuario_id, momento))


def descontar(db, requeridas: dict, pedido_id, usuario_id, momento):
    """Saca del inventario lo que consume un pedido. La condición stock >= ?
    en el UPDATE evita quedar en negativo aunque dos ventas lleguen a la vez."""
    for producto_id, cantidad in requeridas.items():
        cursor = db.execute("UPDATE productos SET stock = stock - ? WHERE id = ? AND stock >= ?",
                            (cantidad, producto_id, cantidad))
        if cursor.rowcount == 0:
            raise ErrorConflicto(f"El ítem {producto_id} se quedó sin inventario mientras se procesaba el pedido")
        _movimiento(db, producto_id, -cantidad, "VENTA", pedido_id, usuario_id, momento)


def reponer(db, pedido_id, usuario_id, momento):
    """Devuelve al inventario lo que se descontó en un pedido anulado."""
    filas = db.execute("""SELECT producto_id, -SUM(cantidad) AS cantidad FROM movimientos_inventario
                          WHERE pedido_id = ? GROUP BY producto_id HAVING SUM(cantidad) < 0""", (pedido_id,)).fetchall()
    for fila in filas:
        db.execute("UPDATE productos SET stock = stock + ? WHERE id = ?", (fila["cantidad"], fila["producto_id"]))
        _movimiento(db, fila["producto_id"], fila["cantidad"], "ANULACION", pedido_id, usuario_id, momento)
    return len(filas)


def movimientos(db, producto_id, limite=30):
    return filas_a_dicts(db.execute(
        """SELECT m.*, u.nombre AS usuario FROM movimientos_inventario m LEFT JOIN usuarios u ON u.id = m.usuario_id
           WHERE m.producto_id = ? ORDER BY m.id DESC LIMIT ?""", (producto_id, limite)))
