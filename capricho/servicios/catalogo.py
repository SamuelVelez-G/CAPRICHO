"""
Catálogo de productos y cálculo del precio EN EL SERVIDOR.

El navegador muestra precios, pero nunca los decide. Al comprar, el
servidor vuelve a calcular todo desde la base de datos; si el total que
mandó el navegador no coincide (alguien editó el localStorage o el HTML),
la compra se rechaza y queda registrada como anomalía.
"""

from ..db import fila_a_dict, filas_a_dicts
from ..errores import ErrorConflicto, ErrorNoEncontrado, ErrorValidacion
from ..registro import logger
from ..tiempo import a_texto, ahora

SABORES = ("Café artesanal", "Capuchino")
MAX_ADICIONES = 3
IMAGENES = ("menu.jpg", "capuchino.jpg", "cargador.jpg")


def _publico(producto: dict) -> dict:
    producto = dict(producto)
    producto["activo"] = bool(producto["activo"])
    return producto


def listar(db, incluir_inactivos=False):
    consulta = "SELECT * FROM productos"
    if not incluir_inactivos:
        consulta += " WHERE activo = 1"
    consulta += " ORDER BY categoria DESC, precio, nombre"
    return [_publico(p) for p in filas_a_dicts(db.execute(consulta))]


def obtener(db, producto_id):
    producto = fila_a_dict(db.execute("SELECT * FROM productos WHERE id = ?", (producto_id,)).fetchone())
    if producto is None:
        raise ErrorNoEncontrado(f"No existe el producto {producto_id}")
    return _publico(producto)


def _revisar_coherencia(datos):
    if datos["categoria"] == "GRANIZADO" and not datos.get("onzas"):
        raise ErrorValidacion({"onzas": "Un granizado debe indicar sus onzas"})
    if datos["categoria"] == "ADICION" and datos.get("onzas"):
        raise ErrorValidacion({"onzas": "Una adición no lleva onzas (usa null)"})


def _nombre_libre(db, nombre, excepto_id=None):
    fila = db.execute("SELECT id FROM productos WHERE nombre = ? AND id != ?",
                      (nombre, excepto_id or 0)).fetchone()
    if fila:
        raise ErrorConflicto("Ya existe un producto con ese nombre", {"nombre": "Nombre repetido"})


def crear(db, datos):
    _revisar_coherencia(datos)
    _nombre_libre(db, datos["nombre"])
    momento = a_texto(ahora())
    cursor = db.execute(
        """INSERT INTO productos (nombre, descripcion, categoria, precio, onzas, imagen, activo,
                                  fecha_creacion, fecha_actualizacion)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (datos["nombre"], datos["descripcion"], datos["categoria"], datos["precio"],
         datos["onzas"], datos["imagen"], int(datos["activo"]), momento, momento),
    )
    db.commit()
    logger.info("POST producto #%s %s", cursor.lastrowid, datos["nombre"])
    return obtener(db, cursor.lastrowid)


def reemplazar(db, producto_id, datos):
    """PUT: se reemplazan TODOS los campos."""
    obtener(db, producto_id)
    _revisar_coherencia(datos)
    _nombre_libre(db, datos["nombre"], producto_id)
    db.execute(
        """UPDATE productos SET nombre = ?, descripcion = ?, categoria = ?, precio = ?, onzas = ?,
                                imagen = ?, activo = ?, fecha_actualizacion = ?
           WHERE id = ?""",
        (datos["nombre"], datos["descripcion"], datos["categoria"], datos["precio"], datos["onzas"],
         datos["imagen"], int(datos["activo"]), a_texto(ahora()), producto_id),
    )
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
    _revisar_coherencia(fusion)
    if "nombre" in cambios:
        _nombre_libre(db, cambios["nombre"], producto_id)
    columnas = ", ".join(f"{campo} = ?" for campo in cambios)
    valores = [int(v) if isinstance(v, bool) else v for v in cambios.values()]
    db.execute(f"UPDATE productos SET {columnas}, fecha_actualizacion = ? WHERE id = ?",
               (*valores, a_texto(ahora()), producto_id))
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
    db.execute("DELETE FROM productos WHERE id = ?", (producto_id,))
    db.commit()
    logger.info("DELETE producto #%s", producto_id)


def cotizar(db, items):
    """Calcula cada línea con los precios de la base de datos.

    Devuelve (lineas, subtotal, diferencias). `diferencias` lista las
    líneas donde el precio que mandó el navegador no coincide.
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
        if granizado is None or granizado["categoria"] != "GRANIZADO":
            errores[f"items[{posicion}].producto_id"] = "El granizado no existe o no está disponible"
            continue
        adiciones = []
        for adicion_id in item["adiciones"]:
            adicion = productos.get(adicion_id)
            if adicion is None or adicion["categoria"] != "ADICION":
                errores[f"items[{posicion}].adiciones"] = f"La adición {adicion_id} no existe"
                break
            adiciones.append({"id": adicion["id"], "nombre": adicion["nombre"], "precio": adicion["precio"]})
        precio_unitario = granizado["precio"] + sum(a["precio"] for a in adiciones)
        total_linea = precio_unitario * item["cantidad"]
        subtotal += total_linea
        lineas.append({
            "producto_id": granizado["id"], "nombre": granizado["nombre"], "sabor": item["sabor"],
            "adiciones": adiciones, "cantidad": item["cantidad"],
            "precio_unitario": precio_unitario, "subtotal": total_linea,
        })
        if item["precio_unitario"] != precio_unitario:
            diferencias.append({
                "linea": posicion, "producto": granizado["nombre"],
                "precio_enviado": item["precio_unitario"], "precio_real": precio_unitario,
            })
    if errores:
        raise ErrorValidacion(errores)
    return lineas, subtotal, diferencias
