"""
Transferencia EN VIVO (observación del profesor después de la exposición).

Alguien hace una transferencia en ese momento (desde la página /transferir,
incluso desde su celular por ngrok) y el monitor (/en-vivo) muestra cómo la
analizó cada parte del sistema con lo que aprendió: reglas, estadística del
cliente, clasificador, monto esperado y autoencoder.

    POST /api/vivo/transferir     hacer la transferencia (la firma el servidor como la pasarela)
    GET  /api/vivo/feed?desde=ID  transacciones nuevas de CUALQUIER origen con su análisis   administrador
    GET  /api/vivo/sugerencias    clientes de la demo para probar (habitual, nuevo...)
"""

import json
import secrets

from flask import Blueprint, current_app

from ..db import obtener_db
from ..errores import ErrorProhibido, ErrorValidacion
from ..seguridad import admin_requerido, exigir_csrf, firmar_transaccion, revisar_inyeccion
from ..servicios import detector
from ..tiempo import a_texto, ahora
from ..validaciones import METODOS_PAGO, exigir_objeto, validar_email
from . import entero_de_consulta, estado_app, ip_cliente, leer_json, ok

bp = Blueprint("api_vivo", __name__, url_prefix="/api/vivo")


@bp.post("/transferir")
@exigir_csrf
def transferir():
    if not current_app.config["MODO_LABORATORIO"]:
        raise ErrorProhibido("El modo laboratorio está apagado")
    datos = exigir_objeto(leer_json())
    revisar_inyeccion(datos)
    errores = {}
    email = datos.get("email")
    if not isinstance(email, str) or validar_email(email.strip().lower()):
        errores["email"] = "Escribe un correo válido (puede ser uno que nunca haya comprado)"
    valor = datos.get("valor")
    if isinstance(valor, bool) or not isinstance(valor, (int, float)) or not 100 <= valor <= 50_000_000:
        errores["valor"] = "Monto entre $100 y $50.000.000"
    metodo = datos.get("metodo")
    if metodo not in METODOS_PAGO:
        errores["metodo"] = f"Uno de: {', '.join(METODOS_PAGO)}"
    repetir = datos.get("repetir", 1)
    if isinstance(repetir, bool) or not isinstance(repetir, int) or not 1 <= repetir <= 6:
        errores["repetir"] = "Entre 1 y 6"
    if errores:
        raise ErrorValidacion(errores)

    estado = estado_app()
    resultados = []
    for _ in range(repetir):              # repetir = 6 simula un bot que manda varias en un segundo
        momento = ahora()
        externo = {"idTxn": f"VIVO-{momento:%H%M%S}-{secrets.token_hex(3).upper()}", "user": email.strip().lower(),
                   "date": a_texto(momento), "value": valor, "paymentMethod": metodo}
        firma = firmar_transaccion(externo, estado.llave_hmac)
        txn = {"id_txn": externo["idTxn"], "email": externo["user"], "fecha": momento, "valor": valor,
               "metodo_pago": metodo, "hash": firma, "hash_valido": True, "firma": "HMAC-SHA256 de la pasarela"}
        if datos.get("alterar_firma"):
            # Alguien cambió el monto en el camino: la firma ya no corresponde.
            txn["valor"] = valor * 10
            txn["hash_valido"], txn["firma"] = False, "no coincide"
        resultados.append(detector.procesar_transaccion(obtener_db(), estado, txn, origen="VIVO", ip=ip_cliente(),
                                                        llegada=momento, canal="EN_VIVO"))
    return ok({"resultados": resultados}, 201)


@bp.get("/feed")
@admin_requerido
def feed():
    desde = entero_de_consulta("desde", 0, 0, 10 ** 9)
    db = obtener_db()
    if desde == 0:
        filas = db.execute(
            """SELECT * FROM (SELECT t.*, u.email, u.nombre FROM transacciones t JOIN usuarios u ON u.id = t.usuario_id
               WHERE t.origen != 'DEMO' ORDER BY t.id DESC LIMIT 6) ORDER BY id""").fetchall()
    else:
        filas = db.execute(
            """SELECT t.*, u.email, u.nombre FROM transacciones t JOIN usuarios u ON u.id = t.usuario_id
               WHERE t.id > ? AND t.origen != 'DEMO' ORDER BY t.id LIMIT 25""", (desde,)).fetchall()
    transacciones = []
    for fila in filas:
        txn = dict(fila)
        txn["analisis"] = json.loads(txn["analisis"]) if txn["analisis"] else None
        txn["anomalias"] = [dict(a) for a in db.execute(
            "SELECT tipo, nivel, detalle FROM anomalias WHERE transaccion_id = ?", (txn["id"],))]
        txn.pop("hash", None)
        transacciones.append(txn)
    ultimo = db.execute("SELECT COALESCE(MAX(id), 0) FROM transacciones").fetchone()[0]
    contadores = dict(db.execute(
        """SELECT COUNT(*) AS total, SUM(estado = 'APROBADA') AS aprobadas, SUM(estado = 'SOSPECHOSA') AS sospechosas,
                  SUM(estado = 'RECHAZADA') AS rechazadas, SUM(clasificacion = 'FRAUDULENTA') AS fraudulentas
           FROM transacciones WHERE origen != 'DEMO'""").fetchone())
    return ok({"transacciones": transacciones, "ultimo": ultimo, "contadores": contadores,
               "modo_ia": detector.cargar_reglas(db).get("ia_modo", "marcar")})


@bp.get("/sugerencias")
def sugerencias():
    """Clientes con historial para probar "compra normal" contra "cuenta tomada"."""
    if not current_app.config["MODO_LABORATORIO"]:
        raise ErrorProhibido("El modo laboratorio está apagado")
    db = obtener_db()
    filas = db.execute(
        """SELECT u.email, u.nombre, COUNT(*) AS compras FROM transacciones t JOIN usuarios u ON u.id = t.usuario_id
           WHERE u.rol = 'CLIENTE' AND u.email != 'consumidor.final@capricho.co' AND t.estado = 'APROBADA'
           GROUP BY u.id HAVING compras >= 15 ORDER BY compras DESC LIMIT 5""").fetchall()
    clientes = []
    for fila in filas:
        habitos = db.execute(
            """SELECT metodo_pago, COUNT(*) AS n FROM transacciones t JOIN usuarios u ON u.id = t.usuario_id
               WHERE u.email = ? AND t.estado = 'APROBADA' GROUP BY metodo_pago ORDER BY n DESC LIMIT 1""",
            (fila["email"],)).fetchone()
        montos = sorted(f[0] for f in db.execute(
            """SELECT t.valor FROM transacciones t JOIN usuarios u ON u.id = t.usuario_id
               WHERE u.email = ? AND t.estado = 'APROBADA' ORDER BY t.fecha_txn DESC LIMIT 40""", (fila["email"],)))
        clientes.append({"email": fila["email"], "nombre": fila["nombre"], "compras": fila["compras"],
                         "metodo": habitos["metodo_pago"], "monto_habitual": montos[len(montos) // 2]})
    return ok({"clientes": clientes, "metodos": list(METODOS_PAGO), "nuevo": f"nuevo.{secrets.token_hex(2)}@correo.co"})
