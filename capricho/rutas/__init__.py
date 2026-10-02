"""Utilidades comunes de las rutas."""

from flask import current_app, jsonify, request

from ..errores import ErrorValidacion


def estado_app():
    return current_app.extensions["capricho"]


def leer_json(forzar=False):
    """El cuerpo debe ser JSON válido. Si no, 422 con un mensaje claro.

    forzar=True lee el cuerpo como JSON aunque el Content-Type no lo diga
    (algunos scripts mandan text/plain); se usa en el endpoint público.
    """
    if not forzar and not request.is_json:
        raise ErrorValidacion({"cuerpo": "El Content-Type debe ser application/json"},
                              "Formato de solicitud inválido")
    datos = request.get_json(silent=True, force=forzar)
    if datos is None:
        raise ErrorValidacion({"cuerpo": "El JSON está mal formado"}, "Formato de solicitud inválido")
    return datos


def ip_cliente():
    return request.remote_addr or "desconocida"


def ok(datos=None, codigo=200):
    return jsonify({"ok": True, **(datos or {})}), codigo


def entero_de_consulta(nombre, defecto=1, minimo=1, maximo=10_000):
    valor = request.args.get(nombre, str(defecto))
    if not valor.isdigit() or not minimo <= int(valor) <= maximo:
        raise ErrorValidacion({nombre: f"Debe ser un entero entre {minimo} y {maximo}"})
    return int(valor)
