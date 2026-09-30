"""
Ayuda del laboratorio de pruebas.

POST /api/laboratorio/firmar hace lo que haría la pasarela de pagos: firma
una transacción con la llave compartida. Así el profesor puede armar
transacciones válidas desde el navegador sin que la llave salga del
servidor. En producción se apaga con CAPRICHO_LABORATORIO=0.
"""

from flask import Blueprint, current_app

from ..errores import ErrorProhibido, ErrorValidacion
from ..seguridad import CAMPOS_FIRMADOS, exigir_csrf, firmar_transaccion, llave_hmac, serializar_para_firma
from ..validaciones import exigir_objeto
from . import leer_json, ok

bp = Blueprint("api_laboratorio", __name__, url_prefix="/api/laboratorio")


@bp.post("/firmar")
@exigir_csrf
def firmar():
    if not current_app.config["MODO_LABORATORIO"]:
        raise ErrorProhibido("El laboratorio está desactivado en este servidor")
    datos = exigir_objeto(leer_json())
    faltan = [campo for campo in CAMPOS_FIRMADOS if campo not in datos]
    if faltan:
        raise ErrorValidacion({campo: "Se necesita para firmar" for campo in faltan})
    return ok({"hash": firmar_transaccion(datos, llave_hmac()), "mensaje_firmado": serializar_para_firma(datos)})
