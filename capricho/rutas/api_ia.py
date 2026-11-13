"""
Detector con IA (Keras).

    GET  /api/ia/estado    cómo se entrenó el modelo y qué tan bien detecta
    POST /api/ia/evaluar   probador: describe una compra y su contexto y
                           devuelve el riesgo 0-100 con la explicación.
                           No guarda nada.
"""

from datetime import datetime, timedelta

from flask import Blueprint

from ..db import obtener_db
from ..errores import ErrorProhibido, ErrorValidacion
from ..ia import caracteristicas
from ..seguridad import admin_requerido, exigir_csrf
from ..tiempo import ahora, desde_texto
from ..validaciones import METODOS_PAGO, exigir_objeto
from . import estado_app, leer_json, ok

bp = Blueprint("api_ia", __name__, url_prefix="/api/ia")

# campo: (mínimo, máximo)
LIMITES = {
    "hora": (0, 23.99), "valor": (100, 50_000_000), "monto_habitual": (100, 50_000_000),
    "proporcion_metodo": (0, 1), "hora_habitual": (0, 23.99), "compras_ultima_hora": (0, 100),
    "horas_desde_anterior": (0, 24 * 365), "compras_previas": (0, 100_000),
}


@bp.get("/estado")
def ver_estado():
    ia = estado_app().ia
    if ia is None:
        return ok({"disponible": False,
                   "motivo": "No hay modelo entrenado o Keras no está instalado. "
                             "Ejecuta: python herramientas/entrenar_ia.py"})
    datos = {k: v for k, v in ia.metadatos.items() if k != "normalizacion"}
    return ok({"disponible": True, "modelo": datos})


@bp.get("/clientes")
@admin_requerido
def listar_clientes():
    """Clientes con historial para el simulador; solo el administrador ve la lista."""
    filas = obtener_db().execute(
        """SELECT u.id, u.nombre, u.email, COUNT(t.id) AS compras, MAX(t.fecha_txn) AS ultima_compra
           FROM usuarios u JOIN transacciones t ON t.usuario_id = u.id
           WHERE u.rol = 'CLIENTE'
           GROUP BY u.id
           ORDER BY compras DESC, u.nombre COLLATE NOCASE
           LIMIT 200"""
    ).fetchall()
    return ok({"clientes": [dict(fila) for fila in filas]})


@bp.post("/evaluar")
@exigir_csrf
def evaluar():
    ia = estado_app().ia
    if ia is None:
        raise ErrorProhibido("La IA no está disponible en este servidor")
    datos = exigir_objeto(leer_json())
    errores, contexto = {}, {}
    for campo, (minimo, maximo) in LIMITES.items():
        valor = datos.get(campo)
        if isinstance(valor, bool) or not isinstance(valor, (int, float)):
            errores[campo] = "Debe ser un número"
        elif not minimo <= valor <= maximo:
            errores[campo] = f"Entre {minimo} y {maximo}"
        else:
            contexto[campo] = float(valor)
    metodo = datos.get("metodo")
    if not isinstance(metodo, str) or not 2 <= len(metodo.strip()) <= 40:
        errores["metodo"] = "Texto de 2 a 40 caracteres"
    if errores:
        raise ErrorValidacion(errores)
    contexto["metodo"] = metodo.strip()
    contexto["compras_previas"] = int(contexto["compras_previas"])
    contexto["compras_ultima_hora"] = int(contexto["compras_ultima_hora"])
    x = caracteristicas.desde_contexto(contexto)
    return ok({"resultado": ia.evaluar(x, contexto),
               "vector": dict(zip(caracteristicas.NOMBRES, [round(v, 4) for v in x]))})


@bp.post("/evaluar-cliente")
@admin_requerido
@exigir_csrf
def evaluar_cliente():
    """Evalúa una compra hipotética usando el historial real de un cliente."""
    ia = estado_app().ia
    if ia is None:
        raise ErrorProhibido("La IA no está disponible en este servidor")
    datos = exigir_objeto(leer_json())
    errores = {}
    usuario_id = datos.get("usuario_id")
    hora = datos.get("hora")
    valor = datos.get("valor")
    metodo = datos.get("metodo")
    if isinstance(usuario_id, bool) or not isinstance(usuario_id, int) or usuario_id < 1:
        errores["usuario_id"] = "Selecciona un cliente de la base de datos"
    if isinstance(hora, bool) or not isinstance(hora, (int, float)) or not 0 <= hora <= 23.99:
        errores["hora"] = "Entre 0 y 23.99"
    if isinstance(valor, bool) or not isinstance(valor, (int, float)) or not 100 <= valor <= 50_000_000:
        errores["valor"] = "Entre 100 y 50000000"
    if not isinstance(metodo, str) or metodo not in METODOS_PAGO:
        errores["metodo"] = "Selecciona un método de pago válido"
    if errores:
        raise ErrorValidacion(errores)

    db = obtener_db()
    cliente = db.execute(
        """SELECT u.id, u.nombre, u.email, MAX(t.fecha_txn) AS ultima_compra
           FROM usuarios u JOIN transacciones t ON t.usuario_id = u.id
           WHERE u.id = ? AND u.rol = 'CLIENTE' GROUP BY u.id""", (usuario_id,),
    ).fetchone()
    if cliente is None:
        raise ErrorValidacion({"usuario_id": "El cliente no existe o no tiene compras"})

    # La compra hipotética queda después del historial disponible, conservando
    # la hora elegida en el formulario para medirla contra los hábitos reales.
    ultima = desde_texto(cliente["ultima_compra"])
    dia = max(ahora().date(), (ultima + timedelta(days=1)).date())
    hora_entera = int(hora)
    minuto = int(round((float(hora) - hora_entera) * 60)) % 60
    fecha = datetime.combine(dia, datetime.min.time()).replace(hour=hora_entera, minute=minuto)
    x, contexto = caracteristicas.desde_historial(db, usuario_id, fecha, float(valor), metodo)
    return ok({
        "cliente": {"id": cliente["id"], "nombre": cliente["nombre"], "email": cliente["email"]},
        "contexto": contexto,
        "resultado": ia.evaluar(x, contexto),
        "vector": dict(zip(caracteristicas.NOMBRES, [round(v, 4) for v in x])),
    })
