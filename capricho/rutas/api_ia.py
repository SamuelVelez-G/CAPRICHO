"""
Detector con IA (Keras).

    GET  /api/ia/estado    cómo se entrenó el modelo y qué tan bien detecta
    POST /api/ia/evaluar   probador: describe una compra y su contexto y
                           devuelve el riesgo 0-100 con la explicación.
                           No guarda nada.
"""

from flask import Blueprint

from ..errores import ErrorProhibido, ErrorValidacion
from ..ia import caracteristicas
from ..seguridad import exigir_csrf
from ..validaciones import exigir_objeto
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
