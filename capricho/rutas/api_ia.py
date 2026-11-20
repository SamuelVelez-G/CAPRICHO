"""
Modelos de IA (Keras): estado, métricas y probadores.

    GET  /api/ia/estado      cómo se entrenó cada modelo y qué tan bien funciona
    POST /api/ia/evaluar     probador del autoencoder (rareza para ESE cliente)
    POST /api/ia/clasificar  probador del clasificador (normal o fraudulenta) con
                             la explicación y cuánto conocimiento general o personal usó
Los probadores no guardan nada.
"""

from flask import Blueprint

from ..errores import ErrorProhibido, ErrorValidacion
from ..ia import MOTOR, caracteristicas, operaciones
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
LIMITES_CLASIFICADOR = {
    "hora": (0, 23.99), "dia_semana": (0, 6), "valor": (100, 50_000_000), "historial": (0, 100_000),
    "monto_habitual": (100, 50_000_000), "proporcion_metodo": (0, 1), "hora_habitual": (0, 23.99),
    "compras_1min": (0, 100), "compras_1h": (0, 500), "compras_24h": (0, 2_000), "metodos_24h": (1, 6),
    "horas_desde_anterior": (0, 24 * 365),
}


def _numeros(datos, limites):
    errores, limpio = {}, {}
    for campo, (minimo, maximo) in limites.items():
        valor = datos.get(campo)
        if isinstance(valor, bool) or not isinstance(valor, (int, float)):
            errores[campo] = "Debe ser un número"
        elif not minimo <= valor <= maximo:
            errores[campo] = f"Entre {minimo} y {maximo}"
        else:
            limpio[campo] = float(valor)
    metodo = datos.get("metodo")
    if not isinstance(metodo, str) or not 2 <= len(metodo.strip()) <= 40:
        errores["metodo"] = "Texto de 2 a 40 caracteres"
    if errores:
        raise ErrorValidacion(errores)
    limpio["metodo"] = metodo.strip()
    return limpio


@bp.get("/estado")
def ver_estado():
    estado = estado_app()
    modelos = {}
    if estado.clasificador is not None:
        modelos["clasificador"] = {k: v for k, v in estado.clasificador.metadatos.items() if k != "referencia"}
    if estado.monto is not None:
        modelos["monto"] = estado.monto.metadatos
    if estado.demanda is not None:
        modelos["demanda"] = estado.demanda.metadatos
    if estado.ia is not None:
        modelos["autoencoder"] = {k: v for k, v in estado.ia.metadatos.items() if k != "normalizacion"}
    if not modelos:
        return ok({"disponible": False, "motor": MOTOR,
                   "motivo": "No hay modelos entrenados o Keras no está instalado. "
                             "Ejecuta: python herramientas/entrenar_modelos.py --todo"})
    return ok({"disponible": True, "motor": MOTOR, "modelo": modelos.get("autoencoder"), "modelos": modelos})


@bp.post("/evaluar")
@exigir_csrf
def evaluar():
    ia = estado_app().ia
    if ia is None:
        raise ErrorProhibido("El autoencoder no está disponible en este servidor")
    contexto = _numeros(exigir_objeto(leer_json()), LIMITES)
    contexto["compras_previas"] = int(contexto["compras_previas"])
    contexto["compras_ultima_hora"] = int(contexto["compras_ultima_hora"])
    x = caracteristicas.desde_contexto(contexto)
    return ok({"resultado": ia.evaluar(x, contexto),
               "vector": dict(zip(caracteristicas.NOMBRES, [round(v, 4) for v in x]))})


@bp.post("/clasificar")
@exigir_csrf
def clasificar():
    estado = estado_app()
    if estado.clasificador is None:
        raise ErrorProhibido("El clasificador no está disponible en este servidor")
    datos = exigir_objeto(leer_json())
    resumen = _numeros(datos, LIMITES_CLASIFICADOR)
    if not isinstance(datos.get("firma_valida"), bool):
        raise ErrorValidacion({"firma_valida": "Debe ser true o false"})
    resumen["firma_valida"] = datos["firma_valida"]
    x, contexto = operaciones.desde_resumen(resumen, estado.clasificador.mediana_poblacion)
    respuesta = {"resultado": estado.clasificador.evaluar(x, contexto),
                 "vector": dict(zip(operaciones.NOMBRES, [round(v, 4) for v in x]))}
    if estado.monto is not None:
        respuesta["monto_esperado"] = estado.monto.evaluar(contexto)
    return ok(respuesta)
