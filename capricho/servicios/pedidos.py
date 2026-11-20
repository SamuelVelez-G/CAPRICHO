"""
Pedidos de todos los canales: web, app, domicilio y presencial (caja).

Tienda web (cliente):
  1. El SERVIDOR calcula el precio con la base de datos (catalogo.cotizar).
  2. Dijkstra calcula la ruta y la tarifa del domicilio.
  3. Si el total del navegador no coincide -> se rechaza (PRECIO_MANIPULADO).
  4. Se revisa el inventario.
  5. El pago pasa por el mismo detector de fraude que las transacciones externas.
  6. Si se aprueba: se descuenta el inventario, se emite la factura, se
     registra el pago y el pedido entra a la COLA (orden de llegada).

Caja (empleado): pedido con varios ítems, canal y descuento opcional. Queda
PENDIENTE_PAGO con su factura EMITIDA hasta que se registre el pago
(servicios/pagos.py), que puede llevar comprobante.
"""

import json

from ..db import fila_a_dict, filas_a_dicts
from ..errores import ErrorConflicto, ErrorNoEncontrado, ErrorPrecioManipulado
from ..registro import logger
from ..tiempo import a_texto, ahora
from . import alertas, catalogo, detector, domicilios, facturacion, pagos, usuarios
from .detector import dinero

CANALES = ("PRESENCIAL", "WEB", "APP", "DOMICILIO")
CONSUMIDOR_FINAL = usuarios.CONSUMIDOR_FINAL
DESCUENTO_ALTO = 30          # % desde el que un descuento genera alerta por sí solo


def cotizar_pedido(db, datos, solo_granizados=True):
    lineas, subtotal, diferencias = catalogo.cotizar(db, datos["items"], solo_granizados)
    entrega = None
    if datos["tipo_entrega"] == "DOMICILIO":
        entrega = domicilios.cotizar(datos["barrio"])
    tarifa = entrega["tarifa"] if entrega else 0
    return lineas, subtotal, tarifa, subtotal + tarifa, diferencias, entrega


def _insertar(db, *, usuario_id, empleado_id, transaccion_id, canal, estado, datos, entrega, lineas, subtotal,
              tarifa, total, momento, demo):
    cursor = db.execute(
        """INSERT INTO pedidos (usuario_id, empleado_id, transaccion_id, canal, estado, tipo_entrega, barrio, direccion,
                                ruta, distancia_km, subtotal, domicilio, total, metodo_pago, demo,
                                fecha_creacion, fecha_actualizacion)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (usuario_id, empleado_id, transaccion_id, canal, estado, datos["tipo_entrega"], datos.get("barrio"),
         datos.get("direccion"), json.dumps(entrega["ruta"], ensure_ascii=False) if entrega else None,
         entrega["distancia_km"] if entrega else 0, subtotal, tarifa, total, datos["metodo_pago"], int(demo),
         a_texto(momento), a_texto(momento)))
    pedido_id = cursor.lastrowid
    db.executemany(
        """INSERT INTO pedido_items (pedido_id, producto_id, nombre, sabor, adiciones, cantidad, precio_unitario, subtotal)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        [(pedido_id, l["producto_id"], l["nombre"], l["sabor"], json.dumps(l["adiciones"], ensure_ascii=False),
          l["cantidad"], l["precio_unitario"], l["subtotal"]) for l in lineas])
    return pedido_id


def crear(db, estado, config, usuario, datos, ip=None, momento=None, canal="WEB", demo=False):
    """Compra en la tienda web (o en la app): pago en línea por la pasarela."""
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

    requeridas = catalogo.necesidades(lineas)
    catalogo.revisar_stock(db, requeridas)
    momento = momento or ahora()
    txn = detector.transaccion_de_tienda(estado, usuario["email"], total, datos["metodo_pago"], momento)

    # El candado cubre el análisis, el pedido y el commit: así la siguiente
    # compra del mismo usuario siempre ve esta en su ventana.
    with estado.candado:
        resultado = detector.procesar_transaccion(db, estado, txn, origen="DEMO" if demo else "TIENDA", ip=ip,
                                                  llegada=momento, canal=canal, confirmar=False)
        estado_pedido = "RECHAZADO" if resultado["estado"] == "RECHAZADA" else "SOLICITADO"
        pedido_id = _insertar(db, usuario_id=usuario["id"], empleado_id=None, transaccion_id=resultado["id"],
                              canal=canal, estado=estado_pedido, datos=datos, entrega=entrega, lineas=lineas,
                              subtotal=subtotal, tarifa=tarifa, total=total, momento=momento, demo=demo)
        factura = None
        if estado_pedido == "SOLICITADO":
            catalogo.descontar(db, requeridas, pedido_id, usuario["id"], momento)
            factura = facturacion.emitir(db, config, pedido_id=pedido_id, usuario_id=usuario["id"], empleado_id=None,
                                         canal=canal, lineas=lineas, subtotal=subtotal, descuento=0,
                                         motivo_descuento=None, domicilio=tarifa, estado="EMITIDA", momento=momento)
            pagos.registrar(db, estado, config, factura["id"], {"metodo": datos["metodo_pago"], "monto": total},
                            momento=momento, resultado=resultado, pasarela=True, demo=demo)
        db.commit()
        if estado_pedido == "SOLICITADO" and not demo:
            estado.cola_pedidos.encolar(pedido_id)
        posicion = len(estado.cola_pedidos)

    logger.info("Pedido #%s de %s por %s -> %s", pedido_id, usuario["email"], dinero(total), estado_pedido)
    pedido = obtener(db, pedido_id)
    pedido["posicion_en_cola"] = posicion if estado_pedido == "SOLICITADO" else None
    pedido["pago"] = resultado
    return pedido


def crear_en_caja(db, estado, config, empleado, datos, momento=None, demo=False):
    """Pedido tomado por un empleado: cualquier canal, varios ítems y descuento.

    datos = {cliente_email?, canal, tipo_entrega, barrio?, direccion?, items, descuento_porcentaje,
             motivo_descuento?, metodo_pago}
    """
    momento = momento or ahora()
    lineas, subtotal, tarifa, _, _, entrega = cotizar_pedido(db, datos, solo_granizados=False)
    requeridas = catalogo.necesidades(lineas)
    catalogo.revisar_stock(db, requeridas)
    porcentaje = datos.get("descuento_porcentaje") or 0
    descuento = round(subtotal * porcentaje / 100 / 100) * 100          # en múltiplos de $100
    email = datos.get("cliente_email") or CONSUMIDOR_FINAL

    with estado.candado:
        usuario_id = usuarios.obtener_o_crear_por_email(db, estado, email, momento)
        pedido_id = _insertar(db, usuario_id=usuario_id, empleado_id=empleado["id"], transaccion_id=None,
                              canal=datos["canal"], estado="PENDIENTE_PAGO", datos=datos, entrega=entrega,
                              lineas=lineas, subtotal=subtotal, tarifa=tarifa, total=subtotal - descuento + tarifa,
                              momento=momento, demo=demo)
        catalogo.descontar(db, requeridas, pedido_id, empleado["id"], momento)
        factura = facturacion.emitir(db, config, pedido_id=pedido_id, usuario_id=usuario_id, empleado_id=empleado["id"],
                                     canal=datos["canal"], lineas=lineas, subtotal=subtotal, descuento=descuento,
                                     motivo_descuento=datos.get("motivo_descuento"), domicilio=tarifa,
                                     estado="EMITIDA", momento=momento)
        if descuento:
            if porcentaje >= DESCUENTO_ALTO:
                alertas.crear(db, "DESCUENTO_ALTO", "MEDIO", "OPERACION",
                              f"{empleado['nombre']} dio {porcentaje} % de descuento ({dinero(descuento)}) en la "
                              f"factura {facturacion.numero_visible(factura['numero'])}. Motivo: "
                              f"{datos.get('motivo_descuento') or 'sin motivo'}",
                              usuario_id=empleado["id"], entidad="FACTURA", entidad_id=factura["id"],
                              datos={"porcentaje": porcentaje, "descuento": descuento}, demo=demo, momento=momento)
            from . import estadistica
            estadistica.revisar_empleado(db, empleado["id"], momento, demo=demo)
        db.commit()

    logger.info("Pedido #%s en caja (%s) por %s, factura %s", pedido_id, datos["canal"], empleado["email"],
                facturacion.numero_visible(factura["numero"]))
    return {"pedido": obtener(db, pedido_id), "factura": facturacion.obtener(db, factura["id"])}


def _armar(pedido, items=None):
    pedido["ruta"] = json.loads(pedido["ruta"]) if pedido.get("ruta") else None
    if pedido.get("factura_numero"):
        pedido["factura"] = facturacion.numero_visible(pedido["factura_numero"])
    if items is not None:
        for item in items:
            item["adiciones"] = json.loads(item["adiciones"])
        pedido["items"] = items
    return pedido


CONSULTA_BASE = """SELECT p.*, u.nombre AS cliente, u.email, t.id_txn, t.estado AS estado_pago,
                          e.nombre AS empleado, f.id AS factura_id, f.numero AS factura_numero
                   FROM pedidos p JOIN usuarios u ON u.id = p.usuario_id
                   LEFT JOIN usuarios e ON e.id = p.empleado_id
                   LEFT JOIN transacciones t ON t.id = p.transaccion_id
                   LEFT JOIN facturas f ON f.pedido_id = p.id"""


def obtener(db, pedido_id):
    pedido = fila_a_dict(db.execute(CONSULTA_BASE + " WHERE p.id = ?", (pedido_id,)).fetchone())
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


def de_usuario(db, usuario_id):
    pedidos = filas_a_dicts(db.execute(CONSULTA_BASE + " WHERE p.usuario_id = ? ORDER BY p.id DESC LIMIT 30",
                                       (usuario_id,)))
    return _con_items(db, pedidos)


def listar(db, canal=None, estado=None, pagina=1, por_pagina=20):
    condiciones, parametros = [], []
    if canal:
        condiciones.append("p.canal = ?")
        parametros.append(canal)
    if estado:
        condiciones.append("p.estado = ?")
        parametros.append(estado)
    donde = (" WHERE " + " AND ".join(condiciones)) if condiciones else ""
    total = db.execute(f"SELECT COUNT(*) FROM pedidos p{donde}", parametros).fetchone()[0]
    pedidos = filas_a_dicts(db.execute(CONSULTA_BASE + donde + " ORDER BY p.id DESC LIMIT ? OFFSET ?",
                                       (*parametros, por_pagina, (pagina - 1) * por_pagina)))
    return {"pedidos": _con_items(db, pedidos), "total": total, "pagina": pagina,
            "paginas": max(1, -(-total // por_pagina))}


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
