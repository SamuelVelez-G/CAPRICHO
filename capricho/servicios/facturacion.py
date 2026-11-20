"""
Facturación: número consecutivo, impuesto, descuentos y anulaciones.

  - El número es consecutivo (FV-000001, FV-000002...) y lo asigna el
    servidor dentro de la misma transacción de SQLite que crea la factura,
    así dos ventas simultáneas nunca reciben el mismo número.
  - Los precios del menú ya incluyen el impuesto al consumo (8 %). La factura
    lo discrimina: base = (subtotal - descuento) / 1,08 e impuesto = el resto.
    El domicilio no lleva impuesto.
  - Cada factura se sella con el hash encadenado (servicios/integridad.py).
  - Anular no borra nada: la factura queda ANULADA con motivo, quién y
    cuándo, y el inventario se devuelve.
"""

from ..db import fila_a_dict, filas_a_dicts
from ..errores import ErrorConflicto, ErrorNoEncontrado
from ..registro import logger
from ..tiempo import a_texto, ahora
from . import alertas, catalogo, integridad


def numero_visible(numero):
    return f"FV-{numero:06d}"


def calcular_totales(subtotal, descuento, domicilio, tasa):
    gravado = subtotal - descuento
    base = round(gravado / (1 + tasa))
    return {"subtotal": subtotal, "descuento": descuento, "domicilio": domicilio, "base": base,
            "impuesto": gravado - base, "total": gravado + domicilio}


def emitir(db, config, *, pedido_id, usuario_id, empleado_id, canal, lineas, subtotal, descuento, motivo_descuento,
           domicilio, estado, momento):
    """Crea la factura del pedido. No hace commit: va en la misma transacción que el pedido."""
    totales = calcular_totales(subtotal, descuento, domicilio, config["TASA_IMPUESTO"])
    numero = db.execute("SELECT COALESCE(MAX(numero), 0) + 1 FROM facturas").fetchone()[0]
    factura = {"numero": numero, "fecha_emision": a_texto(momento), "pedido_id": pedido_id,
               "usuario_id": usuario_id, "empleado_id": empleado_id, "canal": canal, **totales}
    anterior, sello = integridad.sellar(db, config["LLAVE_INTEGRIDAD"], "facturas",
                                        integridad.contenido_factura(factura, lineas))
    cursor = db.execute(
        """INSERT INTO facturas (numero, pedido_id, usuario_id, empleado_id, canal, subtotal, descuento,
                                 motivo_descuento, domicilio, base, tasa_impuesto, impuesto, total, estado,
                                 fecha_emision, hash_anterior, hash, fecha_actualizacion)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (numero, pedido_id, usuario_id, empleado_id, canal, subtotal, descuento, motivo_descuento, domicilio,
         totales["base"], config["TASA_IMPUESTO"], totales["impuesto"], totales["total"], estado,
         a_texto(momento), anterior, sello, a_texto(momento)))
    return {**factura, "id": cursor.lastrowid, "estado": estado, "hash": sello, "hash_anterior": anterior}


CONSULTA = """SELECT f.*, c.nombre AS cliente, c.email, e.nombre AS empleado, a.nombre AS anulador,
                     p.estado AS estado_pedido, p.tipo_entrega,
                     COALESCE((SELECT SUM(monto) FROM pagos WHERE factura_id = f.id AND estado = 'APROBADO'), 0) AS pagado
              FROM facturas f JOIN usuarios c ON c.id = f.usuario_id
              JOIN pedidos p ON p.id = f.pedido_id
              LEFT JOIN usuarios e ON e.id = f.empleado_id
              LEFT JOIN usuarios a ON a.id = f.anulada_por"""


def _armar(factura):
    factura["codigo"] = numero_visible(factura["numero"])
    factura["saldo"] = max(0, factura["total"] - factura["pagado"]) if factura["estado"] != "ANULADA" else 0
    return factura


def obtener(db, factura_id):
    factura = fila_a_dict(db.execute(CONSULTA + " WHERE f.id = ?", (factura_id,)).fetchone())
    if factura is None:
        raise ErrorNoEncontrado(f"No existe la factura {factura_id}")
    factura = _armar(factura)
    factura["items"] = filas_a_dicts(db.execute(
        "SELECT producto_id, nombre, sabor, adiciones, cantidad, precio_unitario, subtotal FROM pedido_items "
        "WHERE pedido_id = ? ORDER BY id", (factura["pedido_id"],)))
    factura["pagos"] = filas_a_dicts(db.execute(
        """SELECT p.id, p.metodo, p.monto, p.referencia, p.comprobante_nombre, p.comprobante_sha256, p.verificacion,
                  p.detalle_verificacion, p.estado, p.fecha, p.hash, t.id_txn, t.prob_fraude, t.clasificacion
           FROM pagos p LEFT JOIN transacciones t ON t.id = p.transaccion_id
           WHERE p.factura_id = ? ORDER BY p.id""", (factura_id,)))
    return factura


def listar(db, estado=None, canal=None, busqueda=None, pagina=1, por_pagina=25):
    condiciones, parametros = [], []
    if estado:
        condiciones.append("f.estado = ?")
        parametros.append(estado)
    if canal:
        condiciones.append("f.canal = ?")
        parametros.append(canal)
    if busqueda:
        if busqueda.upper().startswith("FV-") and busqueda[3:].isdigit():
            condiciones.append("f.numero = ?")
            parametros.append(int(busqueda[3:]))
        else:
            condiciones.append("(c.nombre LIKE ? OR c.email LIKE ?)")
            parametros += [f"%{busqueda}%"] * 2
    donde = (" WHERE " + " AND ".join(condiciones)) if condiciones else ""
    total = db.execute(f"""SELECT COUNT(*) FROM facturas f JOIN usuarios c ON c.id = f.usuario_id{donde}""",
                       parametros).fetchone()[0]
    filas = filas_a_dicts(db.execute(CONSULTA + donde + " ORDER BY f.numero DESC LIMIT ? OFFSET ?",
                                     (*parametros, por_pagina, (pagina - 1) * por_pagina)))
    return {"facturas": [_armar(f) for f in filas], "total": total, "pagina": pagina,
            "paginas": max(1, -(-total // por_pagina))}


def anular(db, estado_app, factura_id, motivo, usuario, momento=None, demo=False):
    """Anula la factura y su pedido, y devuelve el inventario."""
    factura = obtener(db, factura_id)
    if factura["estado"] == "ANULADA":
        raise ErrorConflicto(f"La factura {factura['codigo']} ya estaba anulada")
    momento = momento or ahora()
    with estado_app.candado:
        db.execute("""UPDATE facturas SET estado = 'ANULADA', motivo_anulacion = ?, anulada_por = ?,
                      fecha_anulacion = ?, fecha_actualizacion = ? WHERE id = ?""",
                   (motivo, usuario["id"], a_texto(momento), a_texto(momento), factura_id))
        db.execute("UPDATE pedidos SET estado = 'ANULADO', fecha_actualizacion = ? WHERE id = ?",
                   (a_texto(momento), factura["pedido_id"]))
        devueltos = catalogo.reponer(db, factura["pedido_id"], usuario["id"], momento)
        if factura["estado"] == "PAGADA":
            alertas.crear(db, "ANULACION_DESPUES_DE_PAGO", "MEDIO", "OPERACION",
                          f"{usuario['nombre']} anuló la factura {factura['codigo']} por "
                          f"${factura['total']:,.0f} después de cobrarla. Motivo: {motivo}".replace(",", "."),
                          usuario_id=usuario["id"], entidad="FACTURA", entidad_id=factura_id,
                          datos={"total": factura["total"], "motivo": motivo}, demo=demo, momento=momento)
        from . import estadistica
        estadistica.revisar_empleado(db, usuario["id"], momento, demo=demo)
        db.commit()
        quitar_de_cola(estado_app, factura["pedido_id"])
    logger.info("Factura %s anulada por %s (%s ítems devueltos al inventario)", factura["codigo"],
                usuario["email"], devueltos)
    return obtener(db, factura_id)


def quitar_de_cola(estado_app, pedido_id):
    with estado_app.candado:
        pendientes = [i for i in estado_app.cola_pedidos.elementos() if i != pedido_id]
        if len(pendientes) != len(estado_app.cola_pedidos):
            from ..estructuras import Cola
            estado_app.cola_pedidos = Cola(pendientes)
