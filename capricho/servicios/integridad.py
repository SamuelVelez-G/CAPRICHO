"""
Integridad de facturas y pagos con HASH ENCADENADO.

Cada factura guarda dos hashes:

    hash_anterior = el hash de la factura anterior (la primera usa 64 ceros)
    hash          = HMAC-SHA256(llave, hash_anterior | contenido de la factura)

Así cada registro queda "amarrado" al anterior, como los bloques de una
cadena de bloques:

  - Si alguien cambia el total de una factura, su hash ya no coincide con
    el que se recalcula sobre el contenido    -> CONTENIDO_ALTERADO
  - Si alguien borra o mete una factura en el medio, la siguiente ya no
    apunta al hash de la anterior             -> ENLACE_ROTO
  - Como es HMAC y no un SHA-256 simple, quien tenga acceso a la base de
    datos pero no a la llave no puede recalcular la cadena para taparlo.

Los pagos llevan su propia cadena, y además el SHA-256 del comprobante
adjunto: si se reemplaza el archivo, el hash del archivo ya no coincide.

El estado (EMITIDA, PAGADA, ANULADA) no entra en el hash porque cambia
legítimamente; lo que nunca puede cambiar es lo que se facturó y lo que se pagó.
"""

import hashlib
import hmac
import json
import time
from pathlib import Path

GENESIS = "0" * 64


def _canonico(datos) -> bytes:
    """Siempre el mismo texto para los mismos datos (llaves ordenadas, sin espacios)."""
    return json.dumps(datos, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def calcular_hash(llave: bytes, hash_anterior: str, contenido: dict) -> str:
    return hmac.new(llave, hash_anterior.encode("ascii") + b"|" + _canonico(contenido), hashlib.sha256).hexdigest()


def contenido_factura(factura: dict, items) -> dict:
    return {
        "numero": factura["numero"], "fecha_emision": factura["fecha_emision"],
        "pedido_id": factura["pedido_id"], "usuario_id": factura["usuario_id"],
        "empleado_id": factura["empleado_id"], "canal": factura["canal"],
        "items": [[i["producto_id"], i["cantidad"], i["precio_unitario"], i["subtotal"]] for i in items],
        "subtotal": factura["subtotal"], "descuento": factura["descuento"], "domicilio": factura["domicilio"],
        "base": factura["base"], "impuesto": factura["impuesto"], "total": factura["total"],
    }


def contenido_pago(pago: dict) -> dict:
    return {
        "factura_id": pago["factura_id"], "metodo": pago["metodo"], "monto": pago["monto"],
        "referencia": pago["referencia"], "comprobante_sha256": pago["comprobante_sha256"],
        "fecha": pago["fecha"],
    }


def ultimo_hash(db, tabla: str) -> str:
    orden = "numero" if tabla == "facturas" else "id"
    fila = db.execute(f"SELECT hash FROM {tabla} ORDER BY {orden} DESC LIMIT 1").fetchone()   # tabla fija, no del usuario
    return fila["hash"] if fila else GENESIS


def sellar(db, llave: bytes, tabla: str, contenido: dict):
    """Devuelve (hash_anterior, hash) para el registro que se va a insertar."""
    anterior = ultimo_hash(db, tabla)
    return anterior, calcular_hash(llave, anterior, contenido)


def sha256_archivo(ruta) -> str:
    return hashlib.sha256(Path(ruta).read_bytes()).hexdigest()


# =============================================================================
#  Verificación: recorre la cadena completa, O(n)
# =============================================================================

def _recorrer(filas, llave, contenido_de, etiqueta_de):
    esperado = GENESIS
    problemas = []
    for fila in filas:
        recalculado = calcular_hash(llave, fila["hash_anterior"], contenido_de(fila))
        if fila["hash_anterior"] != esperado:
            problemas.append({"id": fila["id"], "registro": etiqueta_de(fila), "tipo": "ENLACE_ROTO",
                              "detalle": "No apunta al hash del registro anterior: se borró, insertó o "
                                         "reordenó un registro antes de este."})
        if not hmac.compare_digest(recalculado, fila["hash"]):
            problemas.append({"id": fila["id"], "registro": etiqueta_de(fila), "tipo": "CONTENIDO_ALTERADO",
                              "detalle": "El hash guardado no coincide con el que se calcula sobre el "
                                         "contenido: alguien cambió los datos después de emitirlo.",
                              "hash_guardado": fila["hash"][:16], "hash_calculado": recalculado[:16]})
        esperado = fila["hash"]
    return problemas


def verificar_facturas(db, llave: bytes) -> dict:
    inicio = time.perf_counter()
    facturas = [dict(f) for f in db.execute("SELECT * FROM facturas ORDER BY numero")]
    # Todos los ítems en una sola consulta (no una por factura): O(n) y no O(n) consultas.
    items = {}
    for fila in db.execute("SELECT pedido_id, producto_id, cantidad, precio_unitario, subtotal "
                           "FROM pedido_items ORDER BY pedido_id, id"):
        items.setdefault(fila["pedido_id"], []).append(dict(fila))
    problemas = _recorrer(facturas, llave, lambda f: contenido_factura(f, items.get(f["pedido_id"], [])),
                          lambda f: f"FV-{f['numero']:06d}")
    return _resumen("facturas", len(facturas), problemas, inicio, facturas[-1]["hash"] if facturas else GENESIS)


def verificar_pagos(db, llave: bytes, carpeta_comprobantes=None) -> dict:
    inicio = time.perf_counter()
    pagos = [dict(p) for p in db.execute("SELECT * FROM pagos ORDER BY id")]
    problemas = _recorrer(pagos, llave, contenido_pago, lambda p: f"Pago #{p['id']}")
    if carpeta_comprobantes:
        carpeta = Path(carpeta_comprobantes)
        for pago in pagos:
            if not pago["comprobante_sha256"]:
                continue
            archivo = next(carpeta.glob(f"{pago['comprobante_sha256']}.*"), None)
            if archivo is None:
                problemas.append({"id": pago["id"], "registro": f"Pago #{pago['id']}", "tipo": "COMPROBANTE_FALTANTE",
                                  "detalle": "El archivo del comprobante ya no existe."})
            elif sha256_archivo(archivo) != pago["comprobante_sha256"]:
                problemas.append({"id": pago["id"], "registro": f"Pago #{pago['id']}", "tipo": "COMPROBANTE_ALTERADO",
                                  "detalle": "El archivo del comprobante fue reemplazado: su SHA-256 ya no es "
                                             "el que se guardó al registrar el pago."})
    return _resumen("pagos", len(pagos), problemas, inicio, pagos[-1]["hash"] if pagos else GENESIS)


def _resumen(tabla, total, problemas, inicio, ultimo):
    afectados = {p["id"] for p in problemas}
    return {
        "tabla": tabla, "total": total, "integros": total - len(afectados), "integra": not problemas,
        "problemas": problemas[:200], "cantidad_problemas": len(problemas),
        "ultimo_hash": ultimo, "milisegundos": round((time.perf_counter() - inicio) * 1000, 1),
    }


def verificar_todo(db, llave: bytes, carpeta_comprobantes=None) -> dict:
    facturas = verificar_facturas(db, llave)
    pagos = verificar_pagos(db, llave, carpeta_comprobantes)
    return {"integra": facturas["integra"] and pagos["integra"], "facturas": facturas, "pagos": pagos}


# =============================================================================
#  Laboratorio: simular a alguien que altera la base de datos a escondidas
# =============================================================================

def alterar_factura(db, numero: int, nuevo_total: int) -> dict:
    """Cambia el total directamente en SQLite, como haría alguien con acceso a
    la base de datos. Guarda el valor original para poder restaurarlo."""
    fila = db.execute("SELECT id, numero, total FROM facturas WHERE numero = ?", (numero,)).fetchone()
    if fila is None:
        return None
    db.execute("INSERT OR IGNORE INTO configuracion (clave, valor, fecha_actualizacion) VALUES (?, ?, datetime('now'))",
               (f"manipulacion_factura_{numero}", json.dumps({"total": fila["total"]})))
    db.execute("UPDATE facturas SET total = ? WHERE numero = ?", (nuevo_total, numero))
    db.commit()
    return {"numero": numero, "total_original": fila["total"], "total_nuevo": nuevo_total}


def restaurar_manipulaciones(db) -> int:
    filas = db.execute("SELECT clave, valor FROM configuracion WHERE clave LIKE 'manipulacion_factura_%'").fetchall()
    for fila in filas:
        numero = int(fila["clave"].rsplit("_", 1)[1])
        db.execute("UPDATE facturas SET total = ? WHERE numero = ?", (json.loads(fila["valor"])["total"], numero))
    db.execute("DELETE FROM configuracion WHERE clave LIKE 'manipulacion_factura_%'")
    db.commit()
    return len(filas)
