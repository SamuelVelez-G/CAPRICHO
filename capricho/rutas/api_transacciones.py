"""
Endpoint que recibe las transacciones (diapositiva 37).

    POST /api/transacciones        una transacción (formato de la diapositiva 40)
    POST /api/transacciones/lote   varias, desordenadas: se ordenan con merge sort
    GET  /api/transacciones        listado con filtros (administrador)
    GET  /api/transacciones/<id>   búsqueda por idTxn con el índice hash (administrador)

No usa sesión ni CSRF: quien llama es la pasarela de pagos, y se
autentica con la firma HMAC de cada transacción.

Códigos de respuesta:
    201  APROBADA o SOSPECHOSA (quedó registrada; si es sospechosa trae sus anomalías)
    401  RECHAZADA por hash inválido
    409  idTxn repetido (replay)
    422  campos nulos, vacíos o con formato inválido
    429  RECHAZADA por ráfaga (5 en el mismo segundo)
    400  inyección SQL detectada
"""

from flask import Blueprint, request

from ..db import obtener_db
from ..errores import ErrorNoEncontrado, ErrorValidacion
from ..seguridad import admin_requerido, hash_es_valido, llave_hmac, revisar_inyeccion
from ..servicios import detector, estadisticas
from ..tiempo import ahora
from ..validaciones import validar_transaccion
from . import entero_de_consulta, estado_app, ip_cliente, leer_json, ok

bp = Blueprint("api_transacciones", __name__, url_prefix="/api/transacciones")


def _codigo(resultado):
    if resultado["estado"] != "RECHAZADA":
        return 201
    tipos = {a["tipo"] for a in resultado["anomalias"]}
    return 401 if "HASH_INVALIDO" in tipos else 429


@bp.post("")
def recibir():
    llegada = ahora()
    datos = leer_json()
    revisar_inyeccion(datos)
    txn = validar_transaccion(datos)
    txn["hash_valido"] = hash_es_valido(datos, datos["hash"], llave_hmac())
    resultado = detector.procesar_transaccion(obtener_db(), estado_app(), txn, origen="API",
                                              ip=ip_cliente(), llegada=llegada)
    return ok({"transaccion": resultado}, _codigo(resultado))


@bp.post("/lote")
def recibir_lote():
    datos = leer_json()
    revisar_inyeccion(datos)
    resultado = detector.procesar_lote(obtener_db(), estado_app(), datos, llave_hmac(), ip_cliente())
    return ok({"lote": resultado}, 201)


@bp.get("")
@admin_requerido
def listar():
    estado = request.args.get("estado") or None
    if estado and estado not in ("APROBADA", "SOSPECHOSA", "RECHAZADA"):
        raise ErrorValidacion({"estado": "Debe ser APROBADA, SOSPECHOSA o RECHAZADA"})
    busqueda = (request.args.get("q") or "").strip() or None
    if busqueda:
        if len(busqueda) > 60:
            raise ErrorValidacion({"q": "Máximo 60 caracteres"})
        revisar_inyeccion({"q": busqueda})
    return ok(estadisticas.listar_transacciones(obtener_db(), estado, busqueda, entero_de_consulta("pagina")))


@bp.get("/<id_txn>")
@admin_requerido
def buscar(id_txn):
    """Búsqueda por índice: el diccionario en memoria responde en 1 operación."""
    revisar_inyeccion({"idTxn": id_txn})
    interno, operaciones = estado_app().indice_transacciones.buscar(id_txn)
    if interno is None:
        raise ErrorNoEncontrado(f"No existe la transacción {id_txn}")
    db = obtener_db()
    fila = db.execute(
        """SELECT t.*, u.email, u.nombre,
                  (SELECT COUNT(*) FROM transacciones WHERE id <= t.id) AS posicion
           FROM transacciones t JOIN usuarios u ON u.id = t.usuario_id WHERE t.id = ?""", (interno,)).fetchone()
    anomalias = [dict(a) for a in db.execute(
        "SELECT id, tipo, nivel, estado, detalle FROM anomalias WHERE transaccion_id = ?", (interno,))]
    transaccion = dict(fila)
    return ok({
        "transaccion": transaccion,
        "anomalias": anomalias,
        "busqueda": {
            "metodo": "Índice hash (diccionario)",
            "operaciones": operaciones,
            "busqueda_lineal_habria_revisado": transaccion.pop("posicion"),
            "registros_indexados": len(estado_app().indice_transacciones),
        },
    })
