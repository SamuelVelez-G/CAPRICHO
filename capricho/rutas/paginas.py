"""Páginas HTML. Solo entregan la estructura; los datos llegan por la API."""

from flask import Blueprint, redirect, render_template, request, url_for

from ..seguridad import admin_requerido, login_requerido, usuario_actual

bp = Blueprint("paginas", __name__)


def _siguiente_seguro():
    """Solo se redirige a rutas internas: evita que un enlace malicioso
    use el login para mandar al usuario a otro sitio (open redirect)."""
    destino = request.args.get("siguiente", "")
    if destino.startswith("/") and not destino.startswith(("//", "/\\")):
        return destino
    return url_for("paginas.inicio")


@bp.get("/")
def inicio():
    return render_template("inicio.html")


@bp.get("/pagar")
def pagar():
    return render_template("pagar.html")


@bp.get("/mis-pedidos")
@login_requerido
def mis_pedidos():
    return render_template("mis_pedidos.html")


@bp.get("/ingresar")
def ingresar():
    if usuario_actual():
        return redirect(_siguiente_seguro())
    return render_template("ingresar.html", siguiente=_siguiente_seguro())


@bp.get("/registro")
def registro():
    if usuario_actual():
        return redirect(_siguiente_seguro())
    return render_template("registro.html", siguiente=_siguiente_seguro())


@bp.get("/laboratorio")
def laboratorio():
    return render_template("laboratorio.html")


@bp.get("/dashboard")
@admin_requerido
def dashboard():
    return render_template("dashboard.html")


@bp.get("/operacion")
@admin_requerido
def operacion():
    return render_template("operacion.html")
