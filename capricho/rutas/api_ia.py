"""
Modelos de IA (Keras): estado, métricas y probadores.

    GET  /api/ia/estado           cómo se entrenó cada modelo y qué tan bien funciona
    GET  /api/ia/clientes         clientes con historial para el probador (administrador)
    POST /api/ia/evaluar          probador del autoencoder con un perfil descrito a mano
    POST /api/ia/evaluar-cliente  probador del autoencoder con el historial real de un cliente (administrador)
    POST /api/ia/clasificar       probador del clasificador (normal o fraudulenta) con
                                  la explicación y cuánto conocimiento general o personal usó
Los probadores no guardan nada.
"""

from datetime import datetime, timedelta

from flask import Blueprint

from ..db import obtener_db
from ..errores import ErrorProhibido, ErrorValidacion
from ..ia import MOTOR, caracteristicas, operaciones
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
