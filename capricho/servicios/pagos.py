"""
Pagos de facturas con distintos métodos y comprobante adjunto.

    Efectivo / Tarjeta .......... no necesitan comprobante (NO_REQUIERE)
    Nequi / Daviplata / PSE /
    Transferencia ............... en caja exigen comprobante (PDF, PNG o JPG)

Cada pago:
  1. Revisa que no supere el saldo de la factura.
  2. Verifica el comprobante (servicios/comprobantes.py) y que ni el archivo
     ni la referencia se hayan usado antes.
  3. Pasa por el mismo detector de fraude que las transacciones de la API
     (ventana deslizante, reglas e IA), salvo el efectivo.
  4. Se sella con el hash encadenado de pagos.
  5. Si queda aprobado y cubre el total, la factura pasa a PAGADA y el pedido
     entra a la cola de preparación.
"""

import secrets

from ..errores import ErrorConflicto, ErrorValidacion
from ..registro import logger
from ..tiempo import a_texto, ahora
from . import alertas, comprobantes, detector, facturacion, integridad

METODOS = ("Efectivo", "Tarjeta", "Nequi", "Daviplata", "PSE", "Transferencia")
METODOS_CON_COMPROBANTE = ("Nequi", "Daviplata", "PSE", "Transferencia")
RECHAZO = {"FALSO": ("COMPROBANTE_FALSO", "CRITICO"), "NO_COINCIDE": ("COMPROBANTE_NO_COINCIDE", "ALTO"),
           "REUTILIZADO": ("COMPROBANTE_REUTILIZADO", "ALTO")}


def referencia_automatica(metodo, momento):
    return f"{metodo[:3].upper()}-{momento:%Y%m%d%H%M%S}-{secrets.token_hex(2).upper()}"


def _verificar_comprobante(db, config, metodo, monto, referencia, archivo, pasarela=False):
    """Devuelve (verificacion, detalle, sha256, referencia)."""
    if archivo is None:
        if pasarela:
            return "NO_REQUIERE", f"Pago en línea con {metodo}: lo confirmó la pasarela.", None, referencia
        if metodo in METODOS_CON_COMPROBANTE:
            return "SIN_COMPROBANTE", "Pago por transferencia sin comprobante adjunto.", None, referencia
        return "NO_REQUIERE", f"{metodo}: no necesita comprobante.", None, referencia

    contenido, nombre = archivo
    if comprobantes.tipo_archivo(contenido) is None:
        raise ErrorValidacion({"comprobante": "Debe ser un PDF, PNG o JPG (se revisa el contenido, no la extensión)"})
    if len(contenido) > config["COMPROBANTE_MAX_BYTES"]:
        raise ErrorValidacion({"comprobante": "El comprobante supera 2 MB"})
    huella = comprobantes.sha256(contenido)
    verificacion, detalle, datos = comprobantes.verificar(contenido, config["LLAVE_HMAC"], metodo, monto)
    referencia = referencia or (str(datos["referencia"]) if datos and datos.get("referencia") else None)

    repetido = db.execute("SELECT id FROM pagos WHERE comprobante_sha256 = ? LIMIT 1", (huella,)).fetchone()
    if repetido:
        verificacion, detalle = "REUTILIZADO", f"Este mismo archivo ya se usó en el pago #{repetido['id']}."
    elif referencia:
        repetido = db.execute("SELECT id FROM pagos WHERE referencia = ? AND metodo = ? LIMIT 1",
                              (referencia, metodo)).fetchone()
        if repetido:
            verificacion, detalle = "REUTILIZADO", f"La referencia {referencia} ya se usó en el pago #{repetido['id']}."
    comprobantes.guardar(contenido, config["CARPETA_COMPROBANTES"])
    return verificacion, detalle, huella, referencia


def registrar(db, estado_app, config, factura_id, datos, archivo=None, *, quien=None, ip=None, momento=None,
              origen="CAJA", resultado=None, pasarela=False, demo=False):
    """datos = {metodo, monto, referencia?}. archivo = (bytes, nombre) o None.
    resultado: si el pago ya pasó por el detector (compra web), no se analiza otra vez.
    pasarela: el pago se hizo en línea y la pasarela lo confirmó (no hay comprobante que adjuntar)."""
    momento = momento or ahora()
    factura = facturacion.obtener(db, factura_id)
    if factura["estado"] == "ANULADA":
        raise ErrorConflicto(f"La factura {factura['codigo']} está anulada")
    if datos["monto"] > factura["saldo"]:
        raise ErrorValidacion({"monto": f"El saldo de la factura es ${factura['saldo']:,.0f}".replace(",", ".")})

    metodo = datos["metodo"]
    verificacion, detalle, huella, referencia = _verificar_comprobante(
        db, config, metodo, datos["monto"], datos.get("referencia"), archivo, pasarela)
    referencia = referencia or referencia_automatica(metodo, momento)

    with estado_app.candado:
        transaccion_id = resultado["id"] if resultado else None
        if resultado is None and metodo != "Efectivo":
            txn = detector.transaccion_de_tienda(estado_app, factura["email"], datos["monto"], metodo, momento)
            resultado = detector.procesar_transaccion(db, estado_app, txn, origen=origen, ip=ip, llegada=momento,
                                                      canal=factura["canal"], confirmar=False)
            transaccion_id = resultado["id"]

        if verificacion in RECHAZO or (resultado and resultado["estado"] == "RECHAZADA"):
            estado_pago = "RECHAZADO"
        elif verificacion in ("SIN_VERIFICAR", "SIN_COMPROBANTE") or (resultado and resultado["estado"] == "SOSPECHOSA"):
            estado_pago = "PENDIENTE"
        else:
            estado_pago = "APROBADO"

        pago = {"factura_id": factura_id, "metodo": metodo, "monto": datos["monto"], "referencia": referencia,
                "comprobante_sha256": huella, "fecha": a_texto(momento)}
        anterior, sello = integridad.sellar(db, config["LLAVE_INTEGRIDAD"], "pagos", integridad.contenido_pago(pago))
        cursor = db.execute(
            """INSERT INTO pagos (factura_id, transaccion_id, metodo, monto, referencia, comprobante_nombre,
                                  comprobante_tipo, comprobante_sha256, verificacion, detalle_verificacion, estado,
                                  registrado_por, fecha, hash_anterior, hash)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (factura_id, transaccion_id, metodo, datos["monto"], referencia, archivo[1][:120] if archivo else None,
             comprobantes.tipo_archivo(archivo[0])[0] if archivo else None, huella, verificacion, detalle,
             estado_pago, quien["id"] if quien else None, a_texto(momento), anterior, sello))
        pago_id = cursor.lastrowid

        if verificacion in RECHAZO:
            tipo, nivel = RECHAZO[verificacion]
            alertas.crear(db, tipo, nivel, "PAGOS", f"Pago #{pago_id} de la factura {factura['codigo']}: {detalle}",
                          usuario_id=factura["usuario_id"], entidad="PAGO", entidad_id=pago_id,
                          datos={"monto": datos["monto"], "metodo": metodo, "referencia": referencia},
                          demo=demo, momento=momento)

        pagado = factura["pagado"] + (datos["monto"] if estado_pago == "APROBADO" else 0)
        if pagado >= factura["total"]:
            db.execute("UPDATE facturas SET estado = 'PAGADA', fecha_actualizacion = ? WHERE id = ?",
                       (a_texto(momento), factura_id))
            cursor = db.execute("""UPDATE pedidos SET estado = 'SOLICITADO', transaccion_id = COALESCE(transaccion_id, ?),
                                   fecha_actualizacion = ? WHERE id = ? AND estado = 'PENDIENTE_PAGO'""",
                                (transaccion_id, a_texto(momento), factura["pedido_id"]))
            if cursor.rowcount and not demo:
                estado_app.cola_pedidos.encolar(factura["pedido_id"])
        db.commit()

    logger.info("Pago #%s de %s por %s con %s -> %s (%s)", pago_id, factura["codigo"], datos["monto"], metodo,
                estado_pago, verificacion)
    return {"id": pago_id, "estado": estado_pago, "verificacion": verificacion, "detalle": detalle,
            "referencia": referencia, "hash": sello, "transaccion": resultado,
            "factura": facturacion.obtener(db, factura_id)}


def comprobante_de_prueba(config, metodo, monto, pagador, referencia=None, alterar=False):
    """Lo que entregaría la pasarela después de pagar (para el laboratorio y la demo).
    alterar=True simula un comprobante hecho por un falsificador, que no tiene
    la llave de la pasarela: la firma no cuadra."""
    momento = ahora()
    datos = {"referencia": referencia or referencia_automatica(metodo, momento), "metodo": metodo,
             "monto": monto, "fecha": a_texto(momento)[:19], "pagador": pagador}
    llave = b"llave-de-un-falsificador" if alterar else config["LLAVE_HMAC"]
    return comprobantes.generar_pdf(datos, llave), datos["referencia"]
