"""
Módulos operativos: usuarios con roles, categorías y alertas.

    GET    /api/usuarios            listar (filtros: rol, q, pagina)      administrador
    GET    /api/usuarios/<id>       consultar uno
    POST   /api/usuarios            crear (con rol)
    PUT    /api/usuarios/<id>       reemplazar
    PATCH  /api/usuarios/<id>       actualizar parcialmente
    DELETE /api/usuarios/<id>       eliminar (o desactivar si tiene historial)

    GET    /api/categorias          listar (público)
    POST   /api/categorias ...      crear, PUT, PATCH y DELETE (administrador)

    GET    /api/alertas             alertas de estadística, pagos, integridad y calidad
    PATCH  /api/alertas/<id>        marcar REVISADA o DESCARTADA
"""

from flask import Blueprint, request

from ..db import obtener_db
from ..seguridad import admin_requerido, exigir_csrf, revisar_inyeccion, usuario_actual
from ..servicios import alertas, categorias, usuarios
from ..validaciones import ROLES, exigir_objeto, validar_categoria, validar_usuario
from . import entero_de_consulta, estado_app, leer_json, ok

bp = Blueprint("api_gestion", __name__, url_prefix="/api")


# --- Usuarios ----------------------------------------------------------------

@bp.get("/usuarios")
@admin_requerido
def listar_usuarios():
    rol = request.args.get("rol") or None
    busqueda = (request.args.get("q") or "").strip()[:60] or None
    if busqueda:
        revisar_inyeccion({"q": busqueda})
    return ok(usuarios.listar(obtener_db(), rol if rol in ROLES else None, busqueda,
                              entero_de_consulta("pagina", 1, 1, 10_000)))


@bp.get("/usuarios/<int:usuario_id>")
@admin_requerido
def obtener_usuario(usuario_id):
    return ok({"usuario": usuarios.obtener(obtener_db(), usuario_id)})


@bp.post("/usuarios")
@admin_requerido
@exigir_csrf
def crear_usuario():
    datos = leer_json()
    revisar_inyeccion(datos)
    limpio = validar_usuario(datos)
    return ok({"usuario": usuarios.crear(obtener_db(), estado_app(), limpio)}, 201)


@bp.put("/usuarios/<int:usuario_id>")
@admin_requerido
@exigir_csrf
def reemplazar_usuario(usuario_id):
    datos = leer_json()
    revisar_inyeccion(datos)
    limpio = validar_usuario(datos)
    return ok({"usuario": usuarios.actualizar(obtener_db(), estado_app(), usuario_id, limpio, usuario_actual())})


@bp.patch("/usuarios/<int:usuario_id>")
@admin_requerido
@exigir_csrf
def actualizar_usuario(usuario_id):
    datos = leer_json()
    revisar_inyeccion(datos)
    limpio = validar_usuario(datos, parcial=True)
    return ok({"usuario": usuarios.actualizar(obtener_db(), estado_app(), usuario_id, limpio, usuario_actual())})


@bp.delete("/usuarios/<int:usuario_id>")
@admin_requerido
@exigir_csrf
def eliminar_usuario(usuario_id):
    return ok(usuarios.eliminar(obtener_db(), estado_app(), usuario_id, usuario_actual()))


# --- Categorías ----------------------------------------------------------------

@bp.get("/categorias")
def listar_categorias():
    usuario = usuario_actual()
    todas = request.args.get("todas") == "1" and usuario and usuario["rol"] == "ADMIN"
    return ok({"categorias": categorias.listar(obtener_db(), todas)})


@bp.get("/categorias/<int:categoria_id>")
def obtener_categoria(categoria_id):
    return ok({"categoria": categorias.obtener(obtener_db(), categoria_id)})


@bp.post("/categorias")
@admin_requerido
@exigir_csrf
def crear_categoria():
    datos = leer_json()
    revisar_inyeccion(datos)
    return ok({"categoria": categorias.crear(obtener_db(), validar_categoria(datos))}, 201)


@bp.put("/categorias/<int:categoria_id>")
@admin_requerido
@exigir_csrf
def reemplazar_categoria(categoria_id):
    datos = leer_json()
    revisar_inyeccion(datos)
    return ok({"categoria": categorias.actualizar(obtener_db(), categoria_id, validar_categoria(datos))})


@bp.patch("/categorias/<int:categoria_id>")
@admin_requerido
@exigir_csrf
def actualizar_categoria(categoria_id):
    datos = leer_json()
    revisar_inyeccion(datos)
    return ok({"categoria": categorias.actualizar(obtener_db(), categoria_id, validar_categoria(datos, parcial=True))})


@bp.delete("/categorias/<int:categoria_id>")
@admin_requerido
@exigir_csrf
def eliminar_categoria(categoria_id):
    categorias.eliminar(obtener_db(), categoria_id)
    return ok({"eliminado": categoria_id})


# --- Alertas -------------------------------------------------------------------

@bp.get("/alertas")
@admin_requerido
def listar_alertas():
    origen = request.args.get("origen") or None
    estado = request.args.get("estado") or None
    nivel = request.args.get("nivel") or None
    db = obtener_db()
    return ok({"alertas": alertas.listar(db, origen, estado, nivel, entero_de_consulta("limite", 60, 1, 500)),
               "resumen": alertas.resumen(db)})


@bp.patch("/alertas/<int:alerta_id>")
@admin_requerido
@exigir_csrf
def actualizar_alerta(alerta_id):
    datos = exigir_objeto(leer_json())
    alertas.cambiar_estado(obtener_db(), alerta_id, datos.get("estado"))
    return ok({"id": alerta_id, "estado": datos.get("estado")})
