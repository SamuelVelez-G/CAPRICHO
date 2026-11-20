"""
Anomalías por usuario con estadística simple.

Es lo que hace la librería Simple Statistics (simplestatistics.org), escrito
en Python para poder clasificar cada operación en el servidor en el momento
en que llega. El panel vuelve a calcular lo mismo en el navegador con la
librería original y muestra que los dos resultados coinciden.

    Perfil del usuario   media, desviación, mediana, cuartiles Q1 y Q3, rango
                         intercuartílico (IQR = Q3 - Q1)
    Valores atípicos     cercas de Tukey: Q1 - 1,5·IQR y Q3 + 1,5·IQR
    Puntaje de anomalía  z = (x - media) / desviación
    Demanda              regresión lineal simple y = m·x + b, con R²

Si un cliente es nuevo (menos de 5 compras) no hay "su" normalidad: se usa el
perfil de toda la población. Así un cliente nuevo también se evalúa, con lo
que es normal para cualquier cliente de Capricho.
"""

import math
import statistics
import time
from datetime import timedelta

from ..tiempo import a_texto, ahora
from . import alertas

MINIMO_PERSONAL = 5         # compras para tener perfil propio
VENTANA_DIAS = 90
_cache_poblacion = {}      # ruta de la base -> (momento, perfil)


# =============================================================================
#  Funciones básicas (mismos métodos que Simple Statistics)
# =============================================================================

def cuantil(ordenados, p):
    """Igual que quantileSorted de Simple Statistics: si la posición n·p cae
    entre dos datos se toma el de arriba; si cae justo en uno con n par, se
    promedian los dos vecinos."""
    n = len(ordenados)
    if n == 0:
        raise ValueError("cuantil de una lista vacía")
    if p >= 1:
        return ordenados[-1]
    if p <= 0:
        return ordenados[0]
    posicion = n * p
    if posicion % 1:
        return ordenados[math.ceil(posicion) - 1]
    posicion = int(posicion)
    if n % 2 == 0:
        return (ordenados[posicion - 1] + ordenados[posicion]) / 2
    return ordenados[posicion]


def perfil(valores):
    """Resumen estadístico de una lista de montos."""
    ordenados = sorted(valores)
    if not ordenados:
        return None
    q1, q2, q3 = (cuantil(ordenados, p) for p in (0.25, 0.5, 0.75))
    iqr = q3 - q1
    return {
        "n": len(ordenados), "media": statistics.fmean(ordenados), "desviacion": statistics.pstdev(ordenados),
        "minimo": ordenados[0], "q1": q1, "mediana": q2, "q3": q3, "maximo": ordenados[-1], "iqr": iqr,
        "cerca_inferior": q1 - 1.5 * iqr, "cerca_superior": q3 + 1.5 * iqr, "cerca_extrema": q3 + 3 * iqr,
    }


def puntaje_z(valor, resumen):
    if not resumen or resumen["desviacion"] == 0:
        return 0.0
    return (valor - resumen["media"]) / resumen["desviacion"]


def regresion_lineal(xs, ys):
    """(pendiente, intercepto, r2) por mínimos cuadrados."""
    if len(xs) < 2 or len(set(xs)) < 2:
        return 0.0, (ys[0] if ys else 0.0), 0.0
    pendiente, intercepto = statistics.linear_regression(xs, ys)
    if len(set(ys)) < 2:
        return pendiente, intercepto, 1.0
    r2 = statistics.correlation(xs, ys) ** 2
    return pendiente, intercepto, r2


# =============================================================================
#  Evaluación de un monto contra el perfil del usuario (o de la población)
# =============================================================================

def evaluar_monto(valor, resumen, referencia):
    z = puntaje_z(valor, resumen)
    if valor > resumen["cerca_extrema"] and z >= 3:
        alerta = "ALTA"
    elif valor > resumen["cerca_superior"]:
        alerta = "MEDIA"
    elif abs(z) >= 2:
        alerta = "BAJA"
    else:
        alerta = "NINGUNA"
    if valor < resumen["q1"]:
        posicion = "por debajo de Q1"
    elif valor <= resumen["q3"]:
        posicion = "entre Q1 y Q3 (lo normal)"
    elif valor <= resumen["cerca_superior"]:
        posicion = "entre Q3 y la cerca superior"
    else:
        posicion = "por encima de la cerca superior (atípico)"
    return {
        "referencia": referencia, "z": round(z, 2), "alerta": alerta, "posicion": posicion,
        "puntaje": round(min(100.0, max(0.0, z) * 25), 1),
        "perfil": {k: round(v, 1) if isinstance(v, float) else v for k, v in resumen.items()},
    }


def perfil_poblacion(db, momento=None):
    """Perfil de los montos aprobados de todos los clientes (últimos 30 días).
    Con momento=None se guarda en memoria 5 minutos porque se usa en cada transacción."""
    ahora_s = time.monotonic()
    base = db.execute("PRAGMA database_list").fetchone()[2]
    guardado = _cache_poblacion.get(base)
    if momento is None and guardado and ahora_s - guardado[0] < 300:
        return guardado[1]
    desde = a_texto((momento or ahora()) - timedelta(days=30))
    valores = [f[0] for f in db.execute(
        "SELECT valor FROM transacciones WHERE estado = 'APROBADA' AND fecha_txn >= ? ORDER BY id DESC LIMIT 5000",
        (desde,))]
    resumen = perfil(valores) or perfil([10_000, 12_000, 15_000])
    if momento is None:
        _cache_poblacion[base] = (ahora_s, resumen)
    return resumen


def evaluar_transaccion(db, usuario_id, valor, fecha, poblacion=None):
    """Para el detector: ¿este monto es normal PARA ESTE cliente?"""
    previas = [f[0] for f in db.execute(
        """SELECT valor FROM transacciones WHERE usuario_id = ? AND fecha_txn < ? AND estado != 'RECHAZADA'
           ORDER BY fecha_txn DESC LIMIT 60""", (usuario_id, a_texto(fecha)))]
    if len(previas) >= MINIMO_PERSONAL:
        return evaluar_monto(valor, perfil(previas), "personal")
    return evaluar_monto(valor, poblacion or perfil_poblacion(db), "población")


# =============================================================================
#  Empleados: descuentos y anulaciones por día
# =============================================================================

FACTURAS_POR_DIA = """SELECT empleado_id AS empleado, substr(fecha_emision, 1, 10) AS dia, COUNT(*) AS total,
                             SUM(descuento > 0) AS descuentos FROM facturas
                      WHERE empleado_id IS NOT NULL AND fecha_emision >= date(?, '-60 days')
                      GROUP BY empleado_id, dia"""
ANULACIONES_POR_DIA = """SELECT anulada_por AS empleado, substr(fecha_anulacion, 1, 10) AS dia, COUNT(*) AS n
                         FROM facturas WHERE anulada_por IS NOT NULL AND fecha_anulacion >= date(?, '-60 days')
                         GROUP BY anulada_por, dia"""
ALERTA_EMPLEADO = {"descuentos": "DESCUENTOS_ATIPICOS", "anulaciones": "ANULACIONES_ATIPICAS"}
MINIMO_DIAS = 20            # días-empleado de historia para tener una "normalidad"
MINIMO_EVENTOS = 3          # con 1 o 2 descuentos en un día no se alerta a nadie


def serie_empleados(db, momento_txt):
    """Por cada empleado y día: facturas emitidas, descuentos dados y anulaciones.

    Se compara la TASA (descuentos por factura) y no el conteo: quien atiende
    el fin de semana vende más y es normal que dé más descuentos en total."""
    filas = {(f["empleado"], f["dia"]): {"empleado": f["empleado"], "dia": f["dia"], "facturas": f["total"],
                                         "descuentos": f["descuentos"], "anulaciones": 0}
             for f in db.execute(FACTURAS_POR_DIA, (momento_txt,))}
    for f in db.execute(ANULACIONES_POR_DIA, (momento_txt,)):
        fila = filas.setdefault((f["empleado"], f["dia"]), {"empleado": f["empleado"], "dia": f["dia"], "facturas": 0,
                                                            "descuentos": 0, "anulaciones": 0})
        fila["anulaciones"] = f["n"]
    for fila in filas.values():
        base = max(fila["facturas"], 1)
        fila["tasa_descuentos"] = fila["descuentos"] / base
        fila["tasa_anulaciones"] = fila["anulaciones"] / base
    return sorted(filas.values(), key=lambda f: (f["dia"], f["empleado"]))


def revisar_empleado(db, empleado_id, momento, demo=False):
    """¿Hoy este empleado dio más descuentos o hizo más anulaciones de lo
    normal? Lo normal sale de todos los días de todos los empleados: si la tasa
    de hoy supera la cerca de Tukey (Q3 + 1,5·IQR) se genera una alerta."""
    momento_txt = a_texto(momento)
    hoy = momento_txt[:10]
    serie = serie_empleados(db, momento_txt)
    actual = next((f for f in serie if f["dia"] == hoy and f["empleado"] == empleado_id), None)
    if actual is None:
        return
    nombre = db.execute("SELECT nombre FROM usuarios WHERE id = ?", (empleado_id,)).fetchone()
    nombre = nombre["nombre"] if nombre else f"Empleado {empleado_id}"
    for que, tipo in ALERTA_EMPLEADO.items():
        historicos = [f[f"tasa_{que}"] for f in serie if f["dia"] != hoy and f["facturas"] >= 3]
        if len(historicos) < MINIMO_DIAS or actual[que] < MINIMO_EVENTOS:
            continue
        resumen = perfil(historicos)
        tasa = actual[f"tasa_{que}"]
        if tasa <= resumen["cerca_superior"] or alertas.existe_hoy(db, tipo, empleado_id, momento):
            continue
        z = puntaje_z(tasa, resumen)
        nivel = "ALTO" if tasa > resumen["cerca_extrema"] else "MEDIO"
        alertas.crear(
            db, tipo, nivel, "ESTADISTICA",
            f"{nombre} lleva {actual[que]} {que} en {actual['facturas']} facturas hoy ({tasa:.0%}). Lo normal "
            f"por empleado y día está entre {resumen['q1']:.0%} y {resumen['q3']:.0%} (cerca superior "
            f"{resumen['cerca_superior']:.0%}); z = {z:.1f}.",
            usuario_id=empleado_id, entidad="USUARIO", entidad_id=empleado_id, demo=demo, momento=momento,
            datos={"hoy": actual[que], "facturas": actual["facturas"], "tasa": round(tasa, 3),
                   "q1": round(resumen["q1"], 3), "mediana": round(resumen["mediana"], 3),
                   "q3": round(resumen["q3"], 3), "cerca": round(resumen["cerca_superior"], 3), "z": round(z, 2)})


# =============================================================================
#  Perfil completo de un usuario (para la página de estadística)
# =============================================================================

def perfil_completo(db, usuario_id):
    usuario = db.execute("SELECT id, nombre, email, rol, estado FROM usuarios WHERE id = ?", (usuario_id,)).fetchone()
    if usuario is None:
        return None
    filas = db.execute(
        """SELECT valor, fecha_txn, metodo_pago, estado FROM transacciones WHERE usuario_id = ?
           ORDER BY fecha_txn DESC LIMIT 200""", (usuario_id,)).fetchall()
    montos = [f["valor"] for f in filas if f["estado"] != "RECHAZADA"]
    horas = [0] * 24
    metodos = {}
    for fila in filas:
        horas[int(fila["fecha_txn"][11:13])] += 1
        metodos[fila["metodo_pago"]] = metodos.get(fila["metodo_pago"], 0) + 1
    resumen = perfil(montos)
    poblacion = perfil_poblacion(db)
    resultado = {
        "usuario": dict(usuario), "montos": montos, "fechas": [f["fecha_txn"] for f in filas],
        "perfil": resumen, "poblacion": poblacion, "usa_poblacion": len(montos) < MINIMO_PERSONAL,
        "por_hora": horas, "por_metodo": metodos,
        "atipicos": [m for m in montos if resumen and m > resumen["cerca_superior"]],
    }
    if usuario["rol"] in ("EMPLEADO", "ADMIN"):
        momento_txt = db.execute("SELECT COALESCE(MAX(fecha_emision), datetime('now')) FROM facturas").fetchone()[0]
        serie = serie_empleados(db, momento_txt)
        empleado = {"por_dia": [f for f in serie if f["empleado"] == usuario_id]}
        for que in ALERTA_EMPLEADO:
            todos = [f[f"tasa_{que}"] for f in serie if f["facturas"] >= 3]
            empleado[que] = {"poblacion": perfil(todos) if todos else None, "valores_poblacion": todos}
        resultado["empleado"] = empleado
    return resultado


def ranking_empleados(db):
    """Descuentos y anulaciones por empleado, con su puntaje z frente a los demás."""
    filas = [dict(f) for f in db.execute(
        """SELECT u.id, u.nombre, u.email,
                  (SELECT COUNT(*) FROM facturas f WHERE f.empleado_id = u.id) AS facturas,
                  (SELECT COUNT(*) FROM facturas f WHERE f.empleado_id = u.id AND f.descuento > 0) AS descuentos,
                  (SELECT COALESCE(SUM(descuento), 0) FROM facturas f WHERE f.empleado_id = u.id) AS monto_descuentos,
                  (SELECT COUNT(*) FROM facturas f WHERE f.anulada_por = u.id) AS anulaciones,
                  (SELECT COUNT(*) FROM alertas a WHERE a.usuario_id = u.id) AS alertas
           FROM usuarios u WHERE u.rol = 'EMPLEADO' ORDER BY u.nombre""")]
    for fila in filas:
        fila["tasa_descuentos"] = fila["descuentos"] / fila["facturas"] if fila["facturas"] else 0
        fila["tasa_anulaciones"] = fila["anulaciones"] / fila["facturas"] if fila["facturas"] else 0
    for campo in ("tasa_descuentos", "tasa_anulaciones"):
        resumen = perfil([f[campo] for f in filas]) if len(filas) > 1 else None
        for fila in filas:
            fila[f"z_{campo}"] = round(puntaje_z(fila[campo], resumen), 2) if resumen else 0
    return filas
