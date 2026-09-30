"""
Motor antifraude con VENTANA DESLIZANTE (diapositivas 29 a 43).

Por cada transacción que llega:

    Recibir transacción
      -> ¿el idTxn ya existe?                  sí -> 409 (reenvío / replay)
      -> ¿el hash HMAC coincide?               no -> RECHAZADA  (HASH_INVALIDO, crítico)
      -> identificar al usuario (índice hash, O(1))
      -> traer SOLO sus transacciones cercanas (índice usuario + fecha)
      -> ventana deslizante:
           ¿5 o más en menos de 1 segundo?     sí -> RECHAZADA  (RAFAGA, crítico)
           ¿umbral o más dentro de la ventana? sí -> SOSPECHOSA (POSIBLE_FRAUDE)
      -> ¿monto por encima del límite?         sí -> SOSPECHOSA (MONTO_ATIPICO)
      -> registrar transacción y anomalías

Cada usuario tiene su propia ventana: nunca se mezclan (caso de uso 3).
"""

import bisect
import copy
import json
import secrets
from datetime import time, timedelta

from ..errores import ErrorReplay, ErrorValidacion
from ..estructuras import max_en_ventana, merge_sort
from ..registro import logger
from ..seguridad import firmar_transaccion, hash_es_valido
from ..tiempo import a_texto, ahora, desde_texto
from ..validaciones import validar_transaccion
from . import usuarios

# Regla principal de la diapositiva 39: 3 o más transacciones en 3 segundos.
# Las franjas de la diapositiva 38 quedan listas para activarse (modo FRANJAS);
# cada franja tiene su propia ventana y su propio umbral.
REGLAS_POR_DEFECTO = {
    "modo": "FIJA",
    "regla_fija": {"ventana_segundos": 3, "umbral": 3},
    "franjas": [
        {"clave": "manana", "nombre": "Mañana", "desde": "05:00:00", "hasta": "12:00:00",
         "ventana_segundos": 10, "umbral": 3},
        {"clave": "tarde", "nombre": "Tarde-noche", "desde": "12:00:00", "hasta": "20:00:00",
         "ventana_segundos": 6, "umbral": 3},
        {"clave": "noche", "nombre": "Noche-madrugada", "desde": "20:00:00", "hasta": "05:00:00",
         "ventana_segundos": 3, "umbral": 3},
    ],
    # "Un usuario no puede hacer 5 transacciones en el mismo segundo."
    "rafaga": {"maximo": 5, "ventana_segundos": 1},
    "monto_atipico": 300_000,
}

TIPOS_ANOMALIA = {
    "POSIBLE_FRAUDE": "Múltiples transacciones dentro de la ventana",
    "RAFAGA": "Ráfaga: demasiadas transacciones en un segundo",
    "HASH_INVALIDO": "Hash inválido: datos alterados o firma falsa",
    "MONTO_ATIPICO": "Monto fuera de lo normal",
    "PRECIO_MANIPULADO": "Precio alterado desde el navegador",
}
NIVELES = ("BAJO", "MEDIO", "ALTO", "CRITICO")


def dinero(valor) -> str:
    return f"${valor:,.0f}".replace(",", ".")


# =============================================================================
#  Reglas configurables
# =============================================================================

def cargar_reglas(db) -> dict:
    fila = db.execute("SELECT valor FROM configuracion WHERE clave = 'reglas'").fetchone()
    return json.loads(fila["valor"]) if fila else copy.deepcopy(REGLAS_POR_DEFECTO)


def guardar_reglas(db, reglas, confirmar=True):
    db.execute(
        """INSERT INTO configuracion (clave, valor, fecha_actualizacion) VALUES ('reglas', ?, ?)
           ON CONFLICT(clave) DO UPDATE SET valor = excluded.valor,
                                            fecha_actualizacion = excluded.fecha_actualizacion""",
        (json.dumps(reglas, ensure_ascii=False), a_texto(ahora())),
    )
    if confirmar:
        db.commit()


def regla_aplicable(reglas, instante) -> dict:
    """Ventana y umbral que aplican a la hora de la transacción.

    Las franjas incluyen el "hasta" y excluyen el "desde":
    mañana = 05:00:01 a 12:00:00, tarde = 12:00:01 a 20:00:00,
    noche  = 20:00:01 a 05:00:00 (cruza la medianoche).
    """
    if reglas["modo"] == "FIJA":
        return {"clave": "fija", "nombre": "Regla principal", **reglas["regla_fija"]}
    hora = instante.time()
    for franja in reglas["franjas"]:
        desde, hasta = time.fromisoformat(franja["desde"]), time.fromisoformat(franja["hasta"])
        if desde < hasta:
            if desde < hora <= hasta:
                return franja
        elif hora > desde or hora <= hasta:
            return franja
    return reglas["franjas"][-1]


# =============================================================================
#  Ventana deslizante sobre la base de datos
# =============================================================================

def contar_en_ventana(db, usuario_id, instante, ventana_segundos) -> int:
    """Cuántas transacciones del usuario caben en una misma ventana junto a
    la nueva.

    1. Búsqueda por índice: se piden SOLO las transacciones del usuario a
       menos de `ventana` segundos (antes o después; en un lote pueden
       llegar desordenadas). El índice (usuario_id, fecha_txn) evita
       recorrer la tabla completa.
    2. Búsqueda binaria (bisect) para ubicar la nueva en su lugar.
    3. Dos punteros para encontrar la ventana más llena que la contenga.
    """
    delta = timedelta(seconds=ventana_segundos)
    filas = db.execute(
        """SELECT fecha_txn FROM transacciones
           WHERE usuario_id = ? AND hash_valido = 1 AND fecha_txn > ? AND fecha_txn < ?
           ORDER BY fecha_txn""",
        (usuario_id, a_texto(instante - delta), a_texto(instante + delta)),
    ).fetchall()
    # Cada vecina se expresa en segundos respecto a la nueva (que queda en 0).
    desfases = [(desde_texto(fila["fecha_txn"]) - instante).total_seconds() for fila in filas]
    bisect.insort(desfases, 0.0)
    return max_en_ventana(desfases, 0.0, ventana_segundos)


def contar_llegadas(db, usuario_id, llegada, ventana_segundos) -> int:
    """Cuántas transacciones del usuario LLEGARON al servidor en el último
    segundo, contando la actual. Protege aunque el cliente mienta en la
    fecha que envía."""
    desde = a_texto(llegada - timedelta(seconds=ventana_segundos))
    previas = db.execute(
        """SELECT COUNT(*) FROM transacciones
           WHERE usuario_id = ? AND hash_valido = 1 AND fecha_creacion > ? AND fecha_creacion <= ?""",
        (usuario_id, desde, a_texto(llegada)),
    ).fetchone()[0]
    return previas + 1


# =============================================================================
#  Procesamiento
# =============================================================================

def _anomalia(tipo, nivel, cantidad, ventana, detalle):
    return {"tipo": tipo, "nivel": nivel, "cantidad_transacciones": cantidad,
            "ventana_segundos": ventana, "detalle": detalle}


def _guardar(db, estado, usuario_id, txn, estado_txn, anomalias, origen, ip, llegada):
    momento = a_texto(llegada)
    cursor = db.execute(
        """INSERT INTO transacciones (id_txn, usuario_id, valor, fecha_txn, estado, hash, hash_valido,
                                      metodo_pago, origen, ip, fecha_creacion, fecha_actualizacion)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (txn["id_txn"], usuario_id, txn["valor"], a_texto(txn["fecha"]), estado_txn, txn["hash"],
         int(txn["hash_valido"]), txn["metodo_pago"], origen, ip, momento, momento),
    )
    transaccion_id = cursor.lastrowid

    for anomalia in anomalias:
        cursor = db.execute(
            """INSERT INTO anomalias (transaccion_id, tipo, nivel, cantidad_transacciones, ventana_segundos,
                                      detalle, fecha_creacion, fecha_actualizacion)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (transaccion_id, anomalia["tipo"], anomalia["nivel"], anomalia["cantidad_transacciones"],
             anomalia["ventana_segundos"], anomalia["detalle"], momento, momento),
        )
        anomalia["id"] = cursor.lastrowid
        db.execute(
            """INSERT INTO anomalias_historial (anomalia_id, estado_anterior, estado_nuevo, nota, responsable, fecha)
               VALUES (?, NULL, 'NUEVA', ?, 'sistema', ?)""",
            (anomalia["id"], f"Detectada automáticamente: {TIPOS_ANOMALIA[anomalia['tipo']]}", momento),
        )

    if any(a["nivel"] in ("ALTO", "CRITICO") for a in anomalias):
        db.execute(
            """UPDATE usuarios SET estado = 'EN_OBSERVACION', fecha_actualizacion = ?
               WHERE id = ? AND estado = 'ACTIVO'""",
            (momento, usuario_id),
        )
    estado.indice_transacciones.agregar(txn["id_txn"], transaccion_id)
    return transaccion_id


def procesar_transaccion(db, estado, txn, *, origen, ip=None, llegada=None,
                         contar_llegada=True, confirmar=True):
    """Analiza y registra una transacción ya validada.

    `txn` = {id_txn, email, fecha, valor, metodo_pago, hash, hash_valido}
    `llegada` = cuándo llegó al servidor (la semilla usa fechas pasadas).
    """
    llegada = llegada or ahora()
    with estado.candado:
        if estado.indice_transacciones.contiene(txn["id_txn"]):
            raise ErrorReplay(
                f"La transacción {txn['id_txn']} ya fue procesada. Un idTxn repetido es un posible reenvío (replay).",
                {"idTxn": "Ya existe"},
            )

        reglas = cargar_reglas(db)
        regla = regla_aplicable(reglas, txn["fecha"])
        usuario_id = usuarios.obtener_o_crear_por_email(db, estado, txn["email"], llegada)
        anomalias = []
        analisis = {
            "hash_valido": bool(txn["hash_valido"]),
            "regla": regla["nombre"],
            "ventana_segundos": regla["ventana_segundos"],
            "umbral": regla["umbral"],
        }

        if not txn["hash_valido"]:
            # Si la firma no cuadra, los datos no son confiables: no se
            # analizan ni cuentan en la ventana del usuario.
            estado_txn = "RECHAZADA"
            anomalias.append(_anomalia(
                "HASH_INVALIDO", "CRITICO", 1, 0,
                "El hash recibido no coincide con el HMAC-SHA256 calculado con la llave compartida: "
                "los datos se alteraron en el camino o la firma es falsa.",
            ))
        else:
            rafaga = reglas["rafaga"]
            por_fecha = contar_en_ventana(db, usuario_id, txn["fecha"], rafaga["ventana_segundos"])
            por_llegada = (contar_llegadas(db, usuario_id, llegada, rafaga["ventana_segundos"])
                           if contar_llegada else 1)
            en_ventana = contar_en_ventana(db, usuario_id, txn["fecha"], regla["ventana_segundos"])
            analisis.update({
                "transacciones_en_ventana": en_ventana,
                "rafaga_maximo": rafaga["maximo"],
                "rafaga_por_fecha": por_fecha,
                "rafaga_por_llegada": por_llegada,
            })

            estado_txn = "APROBADA"
            en_rafaga = max(por_fecha, por_llegada)
            if en_rafaga >= rafaga["maximo"]:
                estado_txn = "RECHAZADA"
                anomalias.append(_anomalia(
                    "RAFAGA", "CRITICO", en_rafaga, rafaga["ventana_segundos"],
                    f"{en_rafaga} transacciones en menos de {rafaga['ventana_segundos']:g} s. "
                    f"Un usuario no puede hacer {rafaga['maximo']} en el mismo segundo: se bloqueó.",
                ))
            elif en_ventana >= regla["umbral"]:
                estado_txn = "SOSPECHOSA"
                nivel = "MEDIO" if en_ventana == regla["umbral"] else "ALTO"
                anomalias.append(_anomalia(
                    "POSIBLE_FRAUDE", nivel, en_ventana, regla["ventana_segundos"],
                    f"{en_ventana} transacciones dentro de {regla['ventana_segundos']:g} s "
                    f"(umbral {regla['umbral']}) · {regla['nombre']}",
                ))

            if txn["valor"] >= reglas["monto_atipico"]:
                anomalias.append(_anomalia(
                    "MONTO_ATIPICO", "BAJO", 1, 0,
                    f"Monto {dinero(txn['valor'])} igual o mayor al límite de {dinero(reglas['monto_atipico'])}",
                ))
                if estado_txn == "APROBADA":
                    estado_txn = "SOSPECHOSA"

        transaccion_id = _guardar(db, estado, usuario_id, txn, estado_txn, anomalias, origen, ip, llegada)
        if confirmar:
            db.commit()

    if anomalias:
        logger.warning("Transacción %s de %s -> %s %s", txn["id_txn"], txn["email"], estado_txn,
                       [f"{a['tipo']}/{a['nivel']}" for a in anomalias])
    else:
        logger.info("Transacción %s de %s -> %s", txn["id_txn"], txn["email"], estado_txn)

    return {
        "id": transaccion_id,
        "idTxn": txn["id_txn"],
        "usuario": txn["email"],
        "fecha": a_texto(txn["fecha"]),
        "valor": txn["valor"],
        "estado": estado_txn,
        "anomalias": anomalias,
        "analisis": analisis,
    }


def procesar_lote(db, estado, lista, llave, ip=None):
    """Recibe transacciones desordenadas, las ordena cronológicamente con
    merge sort (divide y vencerás) y las analiza en ese orden."""
    if not isinstance(lista, list) or not lista:
        raise ErrorValidacion({"cuerpo": "Envía una lista JSON con al menos una transacción"})
    if len(lista) > 500:
        raise ErrorValidacion({"cuerpo": "Máximo 500 transacciones por lote"})

    resultados, validas = [], []
    for posicion, crudo in enumerate(lista):
        try:
            txn = validar_transaccion(crudo)
        except ErrorValidacion as error:
            resultados.append({"posicion": posicion, "estado": "INVALIDA", "errores": error.detalles})
            continue
        txn["hash_valido"] = hash_es_valido(crudo, crudo["hash"], llave)
        txn["posicion"] = posicion
        validas.append(txn)

    ordenadas = merge_sort(validas, clave=lambda t: t["fecha"])
    for txn in ordenadas:
        try:
            resultado = procesar_transaccion(db, estado, txn, origen="LOTE", ip=ip, contar_llegada=False)
        except ErrorReplay as error:
            resultado = {"idTxn": txn["id_txn"], "estado": "DUPLICADA", "error": error.mensaje}
        resultado["posicion"] = txn["posicion"]
        resultados.append(resultado)

    resumen = {}
    for resultado in resultados:
        resumen[resultado["estado"]] = resumen.get(resultado["estado"], 0) + 1
    return {
        "recibidas": len(lista),
        "orden_cronologico": [t["id_txn"] for t in ordenadas],
        "orden_recibido": [t["id_txn"] for t in validas],
        "resumen": resumen,
        "resultados": resultados,
    }


def registrar_precio_manipulado(db, estado, *, email, valor_enviado, valor_real, metodo_pago,
                                diferencias, ip=None):
    """La compra se rechaza, pero el intento queda como transacción RECHAZADA
    con su anomalía, para que el dashboard lo muestre."""
    llegada = ahora()
    txn = {
        "id_txn": f"CAP-{llegada:%Y%m%d%H%M%S}-{secrets.token_hex(3).upper()}",
        "email": email, "fecha": llegada, "valor": max(valor_enviado, 1),
        "metodo_pago": metodo_pago, "hash_valido": True,
    }
    txn["hash"] = firmar_transaccion(_formato_externo(txn), estado.llave_hmac)
    lineas = "; ".join(f"{d['producto']}: enviado {dinero(d['precio_enviado'])}, real {dinero(d['precio_real'])}"
                       for d in diferencias)
    detalle = (f"El navegador envió un total de {dinero(valor_enviado)} y el servidor calculó "
               f"{dinero(valor_real)}. " + (lineas or "Se alteró el total."))
    with estado.candado:
        usuario_id = usuarios.obtener_o_crear_por_email(db, estado, email, llegada)
        anomalia = _anomalia("PRECIO_MANIPULADO", "ALTO", 1, 0, detalle)
        transaccion_id = _guardar(db, estado, usuario_id, txn, "RECHAZADA", [anomalia], "TIENDA", ip, llegada)
        db.commit()
    logger.warning("Precio manipulado por %s: %s", email, detalle)
    return transaccion_id, anomalia


def _formato_externo(txn):
    """Convierte la transacción interna al formato de la diapositiva 40."""
    return {"idTxn": txn["id_txn"], "user": txn["email"], "date": a_texto(txn["fecha"]),
            "value": txn["valor"], "paymentMethod": txn["metodo_pago"]}


def transaccion_de_tienda(estado, email, valor, metodo_pago, momento=None):
    """Arma la transacción de una compra en la tienda y la firma como lo
    haría la pasarela de pagos."""
    momento = momento or ahora()
    txn = {
        "id_txn": f"CAP-{momento:%Y%m%d%H%M%S}-{secrets.token_hex(3).upper()}",
        "email": email, "fecha": momento, "valor": valor, "metodo_pago": metodo_pago,
    }
    txn["hash"] = firmar_transaccion(_formato_externo(txn), estado.llave_hmac)
    txn["hash_valido"] = True
    return txn
