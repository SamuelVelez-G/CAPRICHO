"""
Monitoreo: dashboard, anomalías, reglas y pila de errores.

    GET   /api/dashboard?rango=30d       estadísticas agregadas
    GET   /api/anomalias                 listado con filtros
    GET   /api/anomalias/<id>            detalle + línea de tiempo + ventana
    PATCH /api/anomalias/<id>            cambiar estado (abrir, revisar, descartar)
    GET   /api/configuracion             reglas activas (público: el laboratorio las muestra)
    PUT   /api/configuracion             reemplazar TODAS las reglas
    PATCH /api/configuracion             cambiar solo algunas
    GET   /api/eventos                   pila de errores (LIFO)
    POST  /api/eventos/desapilar         atender el error más reciente
"""

from flask import Blueprint, request

from ..db import obtener_db
from ..errores import ErrorValidacion
from ..registro import logger
from ..seguridad import admin_requerido, exigir_csrf, revisar_inyeccion, usuario_actual
from ..servicios import anomalias, detector, estadisticas
from ..validaciones import exigir_objeto, validar_reglas
from . import entero_de_consulta, estado_app, leer_json, ok

bp = Blueprint("api_admin", __name__, url_prefix="/api")


@bp.get("/dashboard")
@admin_requerido
def dashboard():
    rango = request.args.get("rango", "30d")
    if rango not in estadisticas.RANGOS:
        raise ErrorValidacion({"rango": f"Debe ser uno de: {', '.join(estadisticas.RANGOS)}"})
    return ok({"dashboard": estadisticas.resumen(obtener_db(), estado_app(), rango)})


@bp.get("/anomalias")
@admin_requerido
def listar_anomalias():
    return ok(anomalias.listar(
        obtener_db(),
        estado=request.args.get("estado") or None,
        nivel=request.args.get("nivel") or None,
        tipo=request.args.get("tipo") or None,
        pagina=entero_de_consulta("pagina"),
    ))


@bp.get("/anomalias/<int:anomalia_id>")
@admin_requerido
def detalle_anomalia(anomalia_id):
    return ok(anomalias.detalle(obtener_db(), anomalia_id))


@bp.patch("/anomalias/<int:anomalia_id>")
@admin_requerido
@exigir_csrf
def cambiar_estado(anomalia_id):
    datos = exigir_objeto(leer_json())
    revisar_inyeccion(datos)
    errores = {}
    nuevo = datos.get("estado")
    if nuevo not in anomalias.ESTADOS:
        errores["estado"] = f"Debe ser uno de: {', '.join(anomalias.ESTADOS)}"
    nota = datos.get("nota")
    if not isinstance(nota, str) or not 5 <= len(nota.strip()) <= 200:
        errores["nota"] = "Escribe una nota de 5 a 200 caracteres"
    if errores:
        raise ErrorValidacion(errores)
    return ok(anomalias.cambiar_estado(obtener_db(), anomalia_id, nuevo, nota.strip(), usuario_actual()["email"]))


@bp.get("/configuracion")
def ver_configuracion():
    return ok({"reglas": detector.cargar_reglas(obtener_db()), "tipos": detector.TIPOS_ANOMALIA})


def _guardar_reglas(parcial):
    db = obtener_db()
    reglas = validar_reglas(leer_json(), detector.cargar_reglas(db), parcial=parcial)
    detector.guardar_reglas(db, reglas)
    logger.warning("Reglas del detector actualizadas (%s) por %s", "PATCH" if parcial else "PUT",
                   usuario_actual()["email"])
    return ok({"reglas": reglas})


@bp.put("/configuracion")
@admin_requerido
@exigir_csrf
def reemplazar_configuracion():
    return _guardar_reglas(parcial=False)


@bp.patch("/configuracion")
@admin_requerido
@exigir_csrf
def actualizar_configuracion():
    return _guardar_reglas(parcial=True)


@bp.get("/eventos")
@admin_requerido
def eventos():
    estado = estado_app()
    with estado.candado:
        pila = estado.pila_errores.elementos()
    return ok({"eventos": pila[:50], "total": len(pila)})


@bp.post("/eventos/desapilar")
@admin_requerido
@exigir_csrf
def desapilar():
    estado = estado_app()
    db = obtener_db()
    with estado.candado:
        evento = estado.pila_errores.desapilar()
        if evento:
            db.execute("UPDATE eventos SET atendido = 1 WHERE id = ?", (evento["id"],))
            db.commit()
    return ok({"evento": evento, "restantes": len(estado.pila_errores)})
