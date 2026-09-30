"""
Capricho — Granizado de café artesanal.

Tienda en línea + sistema antifraude con ventana deslizante.
Proyecto de Programación Avanzada, I.U. Pascual Bravo.
"""

import logging
import time

from flask import Flask, g, jsonify, render_template, request
from werkzeug.exceptions import HTTPException

from . import db
from .config import Configuracion
from .errores import ErrorApi, ErrorLimite
from .estado import EstadoMemoria
from .registro import configurar_logs, logger, registrar_evento
from .seguridad import agregar_cabeceras, token_csrf, usuario_actual


def create_app(config=None):
    app = Flask(__name__)
    app.config.from_object(Configuracion)
    app.config["SEMBRAR"] = "completo"          # completo | base | no
    if config:
        app.config.update(config)
    app.json.ensure_ascii = False
    app.json.sort_keys = False

    configurar_logs(app.config["CARPETA_LOGS"])
    db.init_app(app)

    estado = EstadoMemoria(app.config["LLAVE_HMAC"], app.config["LIMITE_PETICIONES_POR_SEGUNDO"])
    _preparar_base_de_datos(app, estado)
    app.extensions["capricho"] = estado

    _registrar_hooks(app, estado)
    _registrar_errores(app, estado)
    _registrar_rutas(app)
    return app


def _preparar_base_de_datos(app, estado):
    from .semilla import sembrar, sembrar_base

    conexion = db.conectar(app.config["BASE_DATOS"])
    try:
        db.crear_esquema(conexion)
        if db.esta_vacia(conexion) and app.config["SEMBRAR"] != "no":
            inicio = time.perf_counter()
            nivel = logger.level
            logger.setLevel(logging.ERROR)       # la semilla genera cientos de avisos esperados
            try:
                if app.config["SEMBRAR"] == "completo":
                    sembrar(conexion, estado, app.config)
                else:
                    sembrar_base(conexion, app.config)
            finally:
                logger.setLevel(nivel)
            logger.warning("Base de datos creada con datos de demostración en %.1f s",
                           time.perf_counter() - inicio)
        estado.reconstruir(conexion)
    finally:
        conexion.close()


def _registrar_rutas(app):
    from .rutas import (api_admin, api_auth, api_domicilios, api_laboratorio, api_pedidos,
                        api_productos, api_transacciones, paginas)

    for modulo in (paginas, api_auth, api_productos, api_domicilios, api_transacciones,
                   api_pedidos, api_admin, api_laboratorio):
        app.register_blueprint(modulo.bp)

    @app.context_processor
    def variables_de_plantilla():
        return {"usuario": usuario_actual(), "csrf_token": token_csrf,
                "modo_laboratorio": app.config["MODO_LABORATORIO"]}


def _registrar_hooks(app, estado):
    ultimos_avisos = {}

    @app.before_request
    def antes():
        g.inicio = time.perf_counter()
        if not request.path.startswith("/api/"):
            return None
        # Ventana deslizante por IP: más de N peticiones en 1 s -> 429.
        ip = request.remote_addr or "desconocida"
        permitido, cantidad = estado.limitador_ip.registrar(ip)
        if not permitido:
            error = ErrorLimite(f"Demasiadas peticiones: {cantidad} en 1 segundo desde tu IP")
            # En un ataque llegan cientos por segundo: se deja un solo evento cada 10 s.
            ahora = time.monotonic()
            error.registrar = ahora - ultimos_avisos.get(ip, 0) > 10
            if error.registrar:
                ultimos_avisos[ip] = ahora
            raise error
        return None

    @app.after_request
    def despues(respuesta):
        if request.path.startswith("/api/"):
            duracion = (time.perf_counter() - g.get("inicio", time.perf_counter())) * 1000
            logger.info("%s %s -> %s (%.1f ms) ip=%s", request.method, request.path,
                        respuesta.status_code, duracion, request.remote_addr)
        return agregar_cabeceras(respuesta)


def _es_api():
    return request.path.startswith("/api/")


def _email_de_la_peticion():
    """Para la bitácora: el usuario con sesión, o el correo que venía en el cuerpo."""
    usuario = usuario_actual()
    if usuario:
        return usuario["email"]
    cuerpo = request.get_json(silent=True) if request.is_json else None
    if isinstance(cuerpo, dict):
        for campo in ("user", "email"):
            if isinstance(cuerpo.get(campo), str):
                return cuerpo[campo][:120]
    return None


def _registrar_errores(app, estado):
    @app.errorhandler(ErrorApi)
    def error_api(error):
        if error.tipo_evento and getattr(error, "registrar", True):
            conexion = db.obtener_db()
            conexion.rollback()
            detalle = getattr(error, "extracto", None) or error.mensaje
            if error.detalles and not hasattr(error, "extracto"):
                detalle += " · " + "; ".join(f"{c}: {m}" for c, m in list(error.detalles.items())[:6])
            registrar_evento(conexion, estado, error.tipo_evento, error.nivel_evento, detalle,
                             ruta=request.path, metodo=request.method, ip=request.remote_addr,
                             email=_email_de_la_peticion())
        return jsonify(error.cuerpo()), error.codigo

    @app.errorhandler(HTTPException)
    def error_http(error):
        if _es_api():
            mensajes = {404: "Ruta no encontrada", 405: "Método HTTP no permitido en esta ruta",
                        413: "La solicitud es demasiado grande"}
            return jsonify({"ok": False, "error": mensajes.get(error.code, error.name)}), error.code
        return render_template("error.html", codigo=error.code, mensaje=error.name), error.code

    @app.errorhandler(Exception)
    def error_inesperado(error):
        logger.exception("Error inesperado en %s %s", request.method, request.path)
        try:
            conexion = db.obtener_db()
            conexion.rollback()
            registrar_evento(conexion, estado, "ERROR_INTERNO", "ALTO", f"{type(error).__name__}: {error}",
                             ruta=request.path, metodo=request.method, ip=request.remote_addr)
        except Exception:          # si la base de datos es la que falló, al menos queda el log
            logger.exception("No se pudo registrar el evento del error")
        if _es_api():
            return jsonify({"ok": False, "error": "Error interno del servidor. Quedó registrado en el log."}), 500
        return render_template("error.html", codigo=500, mensaje="Error interno"), 500
