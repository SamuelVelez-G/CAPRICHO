"""
Pedidos de la tienda y cola de atención.

    POST  /api/pedidos               comprar (cliente con sesión)
    GET   /api/pedidos/mios          historial del cliente
    GET   /api/pedidos/<id>          detalle (dueño o administrador)
    GET   /api/pedidos/cola          cola FIFO + pedidos en proceso (administrador)
    POST  /api/pedidos/cola/atender  desencolar el siguiente (administrador)
    PATCH /api/pedidos/<id>          marcar ENTREGADO (administrador)
"""

from flask import Blueprint

from ..db import obtener_db
from ..errores import ErrorProhibido, ErrorValidacion
from ..seguridad import admin_requerido, exigir_csrf, login_requerido, revisar_inyeccion, usuario_actual
from ..servicios import catalogo, domicilios, pedidos
from ..validaciones import exigir_objeto, validar_pedido
from . import estado_app, ip_cliente, leer_json, ok

bp = Blueprint("api_pedidos", __name__, url_prefix="/api/pedidos")


@bp.post("")
@login_requerido
@exigir_csrf
def crear():
    datos = leer_json()
    revisar_inyeccion(datos)
    limpio = validar_pedido(datos, catalogo.SABORES, tuple(domicilios.BARRIOS), catalogo.MAX_ADICIONES)
    pedido = pedidos.crear(obtener_db(), estado_app(), usuario_actual(), limpio, ip_cliente())
    codigo = 429 if pedido["estado"] == "RECHAZADO" else 201
    return ok({"pedido": pedido}, codigo)


@bp.get("/mios")
@login_requerido
def mios():
    return ok({"pedidos": pedidos.de_usuario(obtener_db(), usuario_actual()["id"])})


@bp.get("/cola")
@admin_requerido
def cola():
    db = obtener_db()
    return ok({"cola": pedidos.cola(db, estado_app()), "en_proceso": pedidos.en_proceso(db)})


@bp.post("/cola/atender")
@admin_requerido
@exigir_csrf
def atender():
    pedido = pedidos.atender_siguiente(obtener_db(), estado_app())
    return ok({"pedido": pedido, "restantes": len(estado_app().cola_pedidos)})


@bp.get("/<int:pedido_id>")
@login_requerido
def obtener(pedido_id):
    pedido = pedidos.obtener(obtener_db(), pedido_id)
    usuario = usuario_actual()
    if usuario["rol"] != "ADMIN" and pedido["usuario_id"] != usuario["id"]:
        raise ErrorProhibido("Ese pedido no es tuyo")
    return ok({"pedido": pedido})


@bp.patch("/<int:pedido_id>")
@admin_requerido
@exigir_csrf
def actualizar(pedido_id):
    datos = exigir_objeto(leer_json())
    if datos != {"estado": "ENTREGADO"}:
        raise ErrorValidacion({"estado": 'Solo se admite {"estado": "ENTREGADO"}'})
    return ok({"pedido": pedidos.entregar(obtener_db(), pedido_id)})
