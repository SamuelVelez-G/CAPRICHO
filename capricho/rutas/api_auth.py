"""POST /api/auth/registro · POST /api/auth/login · POST /api/auth/logout · GET /api/auth/yo"""

from flask import Blueprint, session

from ..db import obtener_db
from ..seguridad import exigir_csrf, iniciar_sesion, revisar_inyeccion, token_csrf, usuario_actual
from ..servicios import usuarios
from ..validaciones import validar_login, validar_registro
from . import estado_app, ip_cliente, leer_json, ok

bp = Blueprint("api_auth", __name__, url_prefix="/api/auth")


@bp.post("/registro")
@exigir_csrf
def registro():
    datos = leer_json()
    revisar_inyeccion(datos)
    limpio = validar_registro(datos)
    usuario = usuarios.registrar_cliente(obtener_db(), estado_app(), limpio)
    iniciar_sesion(usuario)
    return ok({"usuario": usuario, "csrf": token_csrf()}, 201)


@bp.post("/login")
@exigir_csrf
def login():
    datos = leer_json()
    revisar_inyeccion(datos)
    limpio = validar_login(datos)
    usuario = usuarios.autenticar(obtener_db(), estado_app(), limpio["email"], limpio["password"], ip_cliente())
    iniciar_sesion(usuario)
    return ok({"usuario": usuario, "csrf": token_csrf()})


@bp.post("/logout")
@exigir_csrf
def logout():
    session.clear()
    return ok({"csrf": token_csrf()})


@bp.get("/yo")
def yo():
    return ok({"usuario": usuario_actual(), "csrf": token_csrf()})
