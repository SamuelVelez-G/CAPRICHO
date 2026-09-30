"""
CRUD de productos: los cinco métodos HTTP de la diapositiva 3.

    GET    /api/productos        consultar todos
    GET    /api/productos/1      consultar uno
    POST   /api/productos        crear
    PUT    /api/productos/1      reemplazar completo
    PATCH  /api/productos/1      actualizar parcialmente (ej. solo el precio)
    DELETE /api/productos/1      eliminar
"""

from flask import Blueprint, request

from ..db import obtener_db
from ..seguridad import admin_requerido, exigir_csrf, revisar_inyeccion, usuario_actual
from ..servicios import catalogo
from ..validaciones import validar_producto
from . import leer_json, ok

bp = Blueprint("api_productos", __name__, url_prefix="/api/productos")


@bp.get("")
def listar():
    usuario = usuario_actual()
    incluir_inactivos = request.args.get("todos") == "1" and usuario and usuario["rol"] == "ADMIN"
    return ok({
        "productos": catalogo.listar(obtener_db(), incluir_inactivos),
        "sabores": list(catalogo.SABORES),
        "max_adiciones": catalogo.MAX_ADICIONES,
    })


@bp.get("/<int:producto_id>")
def obtener(producto_id):
    return ok({"producto": catalogo.obtener(obtener_db(), producto_id)})


@bp.post("")
@admin_requerido
@exigir_csrf
def crear():
    datos = leer_json()
    revisar_inyeccion(datos)
    producto = catalogo.crear(obtener_db(), validar_producto(datos, catalogo.IMAGENES))
    return ok({"producto": producto}, 201)


@bp.put("/<int:producto_id>")
@admin_requerido
@exigir_csrf
def reemplazar(producto_id):
    datos = leer_json()
    revisar_inyeccion(datos)
    producto = catalogo.reemplazar(obtener_db(), producto_id, validar_producto(datos, catalogo.IMAGENES))
    return ok({"producto": producto})


@bp.patch("/<int:producto_id>")
@admin_requerido
@exigir_csrf
def actualizar(producto_id):
    datos = leer_json()
    revisar_inyeccion(datos)
    cambios = validar_producto(datos, catalogo.IMAGENES, parcial=True)
    return ok({"producto": catalogo.actualizar(obtener_db(), producto_id, cambios)})


@bp.delete("/<int:producto_id>")
@admin_requerido
@exigir_csrf
def eliminar(producto_id):
    catalogo.eliminar(obtener_db(), producto_id)
    return ok({"eliminado": producto_id})
