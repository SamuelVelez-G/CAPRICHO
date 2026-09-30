"""GET /api/domicilios/mapa · GET /api/domicilios/cotizar?barrio=Prado"""

from flask import Blueprint, request

from ..errores import ErrorValidacion
from ..servicios import domicilios
from . import ok

bp = Blueprint("api_domicilios", __name__, url_prefix="/api/domicilios")


@bp.get("/mapa")
def mapa():
    return ok(domicilios.mapa())


@bp.get("/cotizar")
def cotizar():
    barrio = request.args.get("barrio", "").strip()
    if barrio not in domicilios.BARRIOS:
        raise ErrorValidacion({"barrio": "Elige un barrio de la lista"})
    return ok({"domicilio": domicilios.cotizar(barrio)})
