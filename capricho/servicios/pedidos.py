"""
Pedidos de la tienda.

  1. El SERVIDOR calcula el precio con la base de datos (catalogo.cotizar).
  2. Dijkstra calcula la ruta y la tarifa del domicilio.
  3. Si el total del navegador no coincide -> se rechaza (PRECIO_MANIPULADO).
  4. El pago pasa por el mismo detector de fraude que las transacciones externas.
  5. Si se aprueba, el pedido entra a la COLA y se atiende en orden de llegada.
"""

import json

from ..db import fila_a_dict, filas_a_dicts
from ..errores import ErrorConflicto, ErrorNoEncontrado, ErrorPrecioManipulado
from ..registro import logger
from ..tiempo import a_texto, ahora
from . import catalogo, detector, domicilios
from .detector import dinero


def cotizar_pedido(db, datos):
    lineas, subtotal, diferencias = catalogo.cotizar(db, datos["items"])
    entrega = None
    if datos["tipo_entrega"] == "DOMICILIO":
        entrega = domicilios.cotizar(datos["barrio"])
    tarifa = entrega["tarifa"] if entrega else 0
    return lineas, subtotal, tarifa, subtotal + tarifa, diferencias, entrega


def crear(db, estado, usuario, datos, ip=None):
    lineas, subtotal, tarifa, total, diferencias, entrega = cotizar_pedido(db, datos)

    if diferencias or datos["total"] != total:
        detector.registrar_precio_manipulado(
            db, estado, email=usuario["email"], valor_enviado=datos["total"], valor_real=total,
            metodo_pago=datos["metodo_pago"], diferencias=diferencias, ip=ip,
        )
        raise ErrorPrecioManipulado(
            f"Compra rechazada: el navegador envió {dinero(datos['total'])} pero el precio real es "
            f"{dinero(total)}. Los precios se validan en el servidor; no se pueden cambiar desde "
            "el navegador ni desde el localStorage.",
            {"total_enviado": datos["total"], "total_real": total, "diferencias": diferencias,
             "lineas": lineas, "subtotal": subtotal, "domicilio": tarifa},
        )

    momento = ahora()
    txn = detector.transaccion_de_tienda(estado, usuario["email"], total, datos["metodo_pago"], momento)

    # El candado cubre el análisis, el pedido y el commit: así la siguiente
    # compra del mismo usuario siempre ve esta en su ventana.
    with estado.candado:
        resultado = detector.procesar_transaccion(db, estado, txn, origen="TIENDA", ip=ip,
                                                  llegada=momento, confirmar=False)
        estado_pedido = "RECHAZADO" if resultado["estado"] == "RECHAZADA" else "SOLICITADO"
        cursor = db.execute(
            """INSERT INTO pedidos (usuario_id, transaccion_id, estado, tipo_entrega, barrio, direccion, ruta,
                                    distancia_km, subtotal, domicilio, total, metodo_pago,
                                    fecha_creacion, fecha_actualizacion)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (usuario["id"], resultado["id"], estado_pedido, datos["tipo_entrega"], datos["barrio"],
             datos["direccion"], json.dumps(entrega["ruta"], ensure_ascii=False) if entrega else None,
             entrega["distancia_km"] if entrega else 0, subtotal, tarifa, total, datos["metodo_pago"],
             a_texto(momento), a_texto(momento)),
        )
        pedido_id = cursor.lastrowid
        db.executemany(
            """INSERT INTO pedido_items (pedido_id, producto_id, nombre, sabor, adiciones, cantidad,
                                         precio_unitario, subtotal)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            [(pedido_id, l["producto_id"], l["nombre"], l["sabor"],
              json.dumps(l["adiciones"], ensure_ascii=False), l["cantidad"], l["precio_unitario"], l["subtotal"])
             for l in lineas],
        )
        db.commit()
        if estado_pedido == "SOLICITADO":
            estado.cola_pedidos.encolar(pedido_id)
        posicion = len(estado.cola_pedidos)

    logger.info("Pedido #%s de %s por %s -> %s", pedido_id, usuario["email"], dinero(total), estado_pedido)
    pedido = obtener(db, pedido_id)
    pedido["posicion_en_cola"] = posicion if estado_pedido == "SOLICITADO" else None
    pedido["pago"] = resultado
    return pedido


def _armar(pedido, items=None):
    pedido["ruta"] = json.loads(pedido["ruta"]) if pedido.get("ruta") else None
    if items is not None:
        for item in items:
            item["adiciones"] = json.loads(item["adiciones"])
        pedido["items"] = items
    return pedido


def obtener(db, pedido_id):
    pedido = fila_a_dict(db.execute(
        """SELECT p.*, u.nombre AS cliente, u.email, t.id_txn, t.estado AS estado_pago
           FROM pedidos p JOIN usuarios u ON u.id = p.usuario_id
           LEFT JOIN transacciones t ON t.id = p.transaccion_id
           WHERE p.id = ?""", (pedido_id,)).fetchone())
    if pedido is None:
        raise ErrorNoEncontrado(f"No existe el pedido #{pedido_id}")
    items = filas_a_dicts(db.execute("SELECT * FROM pedido_items WHERE pedido_id = ? ORDER BY id", (pedido_id,)))
    return _armar(pedido, items)


def _con_items(db, pedidos):
    if not pedidos:
        return []
    ids = [p["id"] for p in pedidos]
    marcadores = ",".join("?" for _ in ids)
    items = {}
    for fila in db.execute(f"SELECT * FROM pedido_items WHERE pedido_id IN ({marcadores}) ORDER BY id", ids):
        items.setdefault(fila["pedido_id"], []).append(dict(fila))
    return [_armar(p, items.get(p["id"], [])) for p in pedidos]


CONSULTA_BASE = """SELECT p.*, u.nombre AS cliente, u.email, t.id_txn, t.estado AS estado_pago
                   FROM pedidos p JOIN usuarios u ON u.id = p.usuario_id
                   LEFT JOIN transacciones t ON t.id = p.transaccion_id"""


def de_usuario(db, usuario_id):
    pedidos = filas_a_dicts(db.execute(CONSULTA_BASE + " WHERE p.usuario_id = ? ORDER BY p.id DESC LIMIT 30",
                                       (usuario_id,)))
    return _con_items(db, pedidos)


def cola(db, estado):
    """Los pedidos en el orden exacto de la cola FIFO."""
    with estado.candado:
        ids = estado.cola_pedidos.elementos()
    if not ids:
        return []
    marcadores = ",".join("?" for _ in ids)
    por_id = {p["id"]: p for p in filas_a_dicts(
        db.execute(CONSULTA_BASE + f" WHERE p.id IN ({marcadores})", ids))}
    return _con_items(db, [por_id[i] for i in ids if i in por_id])


def en_proceso(db):
    pedidos = filas_a_dicts(db.execute(CONSULTA_BASE + " WHERE p.estado = 'EN_PROCESO' ORDER BY p.fecha_actualizacion"))
    return _con_items(db, pedidos)


def atender_siguiente(db, estado):
    """Desencola el pedido más antiguo y lo pasa a EN_PROCESO."""
    with estado.candado:
        pedido_id = estado.cola_pedidos.desencolar()
        if pedido_id is None:
            return None
        db.execute("UPDATE pedidos SET estado = 'EN_PROCESO', fecha_actualizacion = ? WHERE id = ?",
                   (a_texto(ahora()), pedido_id))
        db.commit()
    logger.info("Pedido #%s desencolado -> EN_PROCESO", pedido_id)
    return obtener(db, pedido_id)


def entregar(db, pedido_id):
    pedido = obtener(db, pedido_id)
    if pedido["estado"] != "EN_PROCESO":
        raise ErrorConflicto(f"Solo se entrega un pedido EN_PROCESO; el #{pedido_id} está {pedido['estado']}.")
    db.execute("UPDATE pedidos SET estado = 'ENTREGADO', fecha_actualizacion = ? WHERE id = ?",
               (a_texto(ahora()), pedido_id))
    db.commit()
    logger.info("Pedido #%s ENTREGADO", pedido_id)
    return obtener(db, pedido_id)
