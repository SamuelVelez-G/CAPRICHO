"""
Estadísticas del dashboard (diapositiva 44).

Por defecto se cuenta con `fecha_txn` (cuándo ocurrió la transacción, según
el emisor). Con por="llegada" se cuenta con `fecha_creacion` (cuándo llegó al
servidor): útil en la prueba en vivo si el generador usa fechas pasadas.
El nombre de la columna sale de un diccionario fijo, nunca del usuario.
Cada bloque es una consulta agregada; SQLite hace el conteo y Python solo
arma la respuesta.
"""

import math
from datetime import timedelta

from ..db import filas_a_dicts
from ..estructuras import mayor_por_division
from ..tiempo import a_texto, ahora, desde_texto
from . import detector

RANGOS = {"hoy": 1, "7d": 7, "30d": 30, "90d": 90, "todo": None}
COLUMNAS = {"txn": "t.fecha_txn", "llegada": "t.fecha_creacion"}
UNION_ANOMALIAS = "FROM anomalias a JOIN transacciones t ON t.id = a.transaccion_id"


def _inicio_del_dia(momento):
    return momento.replace(hour=0, minute=0, second=0, microsecond=0)


def limites(rango, momento):
    """(desde, anterior_desde) del rango elegido. 'anterior' sirve para la tendencia."""
    hoy = _inicio_del_dia(momento)
    dias = RANGOS[rango]
    if dias is None:
        return None, None
    desde = hoy - timedelta(days=dias - 1)
    return desde, desde - timedelta(days=dias)


def _variacion(actual, anterior):
    if anterior in (None, 0):
        return None
    return round((actual - anterior) / anterior * 100, 1)


def resumen(db, estado, rango="30d", por="txn"):
    col = COLUMNAS[por]
    momento = ahora()
    desde_dt, anterior_dt = limites(rango, momento)
    desde = a_texto(desde_dt) if desde_dt else "0000"
    hoy = _inicio_del_dia(momento)
    periodos = {
        "hoy": a_texto(hoy),
        "semana": a_texto(hoy - timedelta(days=hoy.weekday())),   # desde el lunes
        "mes": a_texto(hoy.replace(day=1)),
    }

    # --- Hoy | Esta semana | Este mes -------------------------------------
    minimo = min(periodos.values())
    txn_periodos = db.execute(
        f"""SELECT COALESCE(SUM({col} >= :hoy), 0), COALESCE(SUM({col} >= :semana), 0),
                   COALESCE(SUM({col} >= :mes), 0)
            FROM transacciones t WHERE {col} >= :minimo""", {**periodos, "minimo": minimo}).fetchone()
    anom_periodos = db.execute(
        f"""SELECT COALESCE(SUM({col} >= :hoy), 0), COALESCE(SUM({col} >= :semana), 0),
                   COALESCE(SUM({col} >= :mes), 0)
            {UNION_ANOMALIAS} WHERE {col} >= :minimo""", {**periodos, "minimo": minimo}).fetchone()

    # --- Totales del rango ----------------------------------------------
    estados = {fila["estado"]: {"cantidad": fila["cantidad"], "valor": fila["valor"]}
               for fila in db.execute(
                   f"""SELECT t.estado, COUNT(*) AS cantidad, COALESCE(SUM(t.valor), 0) AS valor
                       FROM transacciones t WHERE {col} >= ? GROUP BY t.estado""", (desde,))}
    for nombre in ("APROBADA", "SOSPECHOSA", "RECHAZADA"):
        estados.setdefault(nombre, {"cantidad": 0, "valor": 0})
    total_txn = sum(e["cantidad"] for e in estados.values())

    fila = db.execute(
        f"""SELECT COUNT(*) AS anomalias, COUNT(DISTINCT a.transaccion_id) AS txn_con_anomalia,
                   COUNT(DISTINCT t.usuario_id) AS usuarios_afectados
            {UNION_ANOMALIAS} WHERE {col} >= ?""", (desde,)).fetchone()
    usuarios_activos = db.execute(
        f"SELECT COUNT(DISTINCT t.usuario_id) FROM transacciones t WHERE {col} >= ?", (desde,)).fetchone()[0]

    tendencia = {"transacciones": None, "anomalias": None}
    if anterior_dt:
        previas = db.execute(
            f"SELECT COUNT(*) FROM transacciones t WHERE {col} >= ? AND {col} < ?",
            (a_texto(anterior_dt), desde)).fetchone()[0]
        previas_anom = db.execute(
            f"SELECT COUNT(*) {UNION_ANOMALIAS} WHERE {col} >= ? AND {col} < ?",
            (a_texto(anterior_dt), desde)).fetchone()[0]
        tendencia = {"transacciones": _variacion(total_txn, previas),
                     "anomalias": _variacion(fila["anomalias"], previas_anom)}

    por_estado_anomalia = {e: 0 for e in ("NUEVA", "ABIERTA", "REVISADA", "DESCARTADA")}
    for f in db.execute(f"SELECT a.estado, COUNT(*) {UNION_ANOMALIAS} WHERE {col} >= ? GROUP BY a.estado",
                        (desde,)):
        por_estado_anomalia[f[0]] = f[1]

    por_nivel = {n: 0 for n in detector.NIVELES}
    for f in db.execute(f"SELECT a.nivel, COUNT(*) {UNION_ANOMALIAS} WHERE {col} >= ? GROUP BY a.nivel",
                        (desde,)):
        por_nivel[f[0]] = f[1]

    por_tipo = [{"tipo": f[0], "nombre": detector.TIPOS_ANOMALIA.get(f[0], f[0]), "cantidad": f[1]}
                for f in db.execute(
                    f"""SELECT a.tipo, COUNT(*) AS n {UNION_ANOMALIAS} WHERE {col} >= ?
                        GROUP BY a.tipo ORDER BY n DESC""", (desde,))]

    metodos = filas_a_dicts(db.execute(
        f"""SELECT t.metodo_pago AS metodo, COUNT(*) AS cantidad,
                   SUM(t.estado != 'APROBADA') AS sospechosas, COALESCE(SUM(t.valor), 0) AS valor
            FROM transacciones t WHERE {col} >= ? GROUP BY t.metodo_pago ORDER BY cantidad DESC""", (desde,)))

    firmas = {}
    for f in db.execute(f"""SELECT t.firma, t.hash_valido, t.origen, COUNT(*) FROM transacciones t
                            WHERE {col} >= ? GROUP BY 1, 2, 3""", (desde,)):
        nombre = _nombre_firma(f[0], f[1], f[2])
        firmas[nombre] = firmas.get(nombre, 0) + f[3]

    return {
        "rango": rango,
        "por": por,
        "generado": a_texto(momento),
        "periodos": {
            "transacciones": dict(zip(("hoy", "semana", "mes"), txn_periodos)),
            "anomalias": dict(zip(("hoy", "semana", "mes"), anom_periodos)),
        },
        "totales": {
            "transacciones": total_txn,
            "anomalias": fila["anomalias"],
            "transacciones_con_anomalia": fila["txn_con_anomalia"],
            "porcentaje_con_anomalia": round(fila["txn_con_anomalia"] / total_txn * 100, 1) if total_txn else 0,
            "usuarios_afectados": fila["usuarios_afectados"],
            "usuarios_activos": usuarios_activos,
            "promedio_por_usuario": round(total_txn / usuarios_activos, 1) if usuarios_activos else 0,
            "valor_sospechoso": estados["SOSPECHOSA"]["valor"] + estados["RECHAZADA"]["valor"],
            "valor_total": sum(e["valor"] for e in estados.values()),
        },
        "tendencia": tendencia,
        "estados": estados,
        "anomalias_por_estado": por_estado_anomalia,
        "por_nivel": por_nivel,
        "por_tipo": por_tipo,
        "metodos": metodos,
        "firmas": sorted(({"firma": k, "cantidad": v} for k, v in firmas.items()), key=lambda x: -x["cantidad"]),
        "serie": _serie(db, rango, desde_dt, momento, col),
        "calor": _mapa_de_calor(db, desde, col),
        "recurrentes": _recurrentes(db, desde, col),
        "multiples": _multiples(db, desde, col),
        "ultimas_aprobadas": _ultimas(db, desde, ("APROBADA",), col),
        "ultimas_sospechosas": _ultimas(db, desde, ("SOSPECHOSA", "RECHAZADA"), col),
        "mayor_sospechosa": _mayor_sospechosa(db, desde, col),
        "eventos": {"total": len(estado.pila_errores), "cima": estado.pila_errores.elementos()[:8]},
        "cola_pedidos": len(estado.cola_pedidos),
        "reglas": detector.cargar_reglas(db),
    }


def _nombre_firma(firma, valido, origen):
    if not valido:
        return "Hash inválido"
    if origen in ("TIENDA", "DEMO") or not firma:
        return "Firmadas por la tienda o la demo"
    if firma.startswith("SHA-256"):
        return "SHA-256 sin llave"
    if "diapositiva" in firma:
        return "HMAC con la llave de la diapositiva 19"
    if "propia" in firma:
        return "HMAC con la llave propia"
    return "HMAC con llave extra"


def _serie(db, rango, desde_dt, momento, col):
    """Transacciones por día (o por hora si el rango es 'hoy') según estado,
    más las anomalías de cada tramo. Marca los picos repentinos."""
    if rango == "hoy":
        tramo = f"substr({col}, 1, 13)"               # 2026-09-29T14
        claves = [a_texto(desde_dt + timedelta(hours=h))[:13] for h in range(momento.hour + 1)]
    else:
        tramo = f"substr({col}, 1, 10)"               # 2026-09-29
        if desde_dt is None:
            primera = db.execute(f"SELECT MIN({col}) FROM transacciones t").fetchone()[0]
            desde_dt = _inicio_del_dia(desde_texto(primera)) if primera else _inicio_del_dia(momento)
        dias = (_inicio_del_dia(momento) - desde_dt).days + 1
        claves = [a_texto(desde_dt + timedelta(days=d))[:10] for d in range(dias)]
    desde = a_texto(desde_dt)

    base = {c: {"tramo": c, "APROBADA": 0, "SOSPECHOSA": 0, "RECHAZADA": 0, "anomalias": 0} for c in claves}
    for fila in db.execute(
            f"""SELECT {tramo} AS tramo, t.estado, COUNT(*) FROM transacciones t
                WHERE {col} >= ? GROUP BY tramo, t.estado""", (desde,)):
        if fila[0] in base:
            base[fila[0]][fila[1]] = fila[2]
    for fila in db.execute(
            f"SELECT {tramo} AS tramo, COUNT(*) {UNION_ANOMALIAS} WHERE {col} >= ? GROUP BY tramo", (desde,)):
        if fila[0] in base:
            base[fila[0]]["anomalias"] = fila[1]

    serie = list(base.values())
    conteos = [p["anomalias"] for p in serie]
    if len(conteos) > 2:
        media = sum(conteos) / len(conteos)
        desviacion = math.sqrt(sum((c - media) ** 2 for c in conteos) / len(conteos))
        limite = media + 2 * desviacion
        for punto in serie:
            punto["pico"] = punto["anomalias"] > limite and punto["anomalias"] >= 3
    return {"unidad": "hora" if rango == "hoy" else "dia", "puntos": serie}


def _mapa_de_calor(db, desde, col):
    """Anomalías por día de la semana (0 = domingo en SQLite) y hora."""
    celdas = [[0] * 24 for _ in range(7)]
    for fila in db.execute(
            f"""SELECT CAST(strftime('%w', {col}) AS INTEGER), CAST(substr({col}, 12, 2) AS INTEGER),
                       COUNT(*) {UNION_ANOMALIAS} WHERE {col} >= ? GROUP BY 1, 2""", (desde,)):
        celdas[fila[0]][fila[1]] = fila[2]
    # Se reordena para empezar en lunes.
    celdas = celdas[1:] + celdas[:1]
    por_hora = [sum(celdas[d][h] for d in range(7)) for h in range(24)]
    top = sorted(range(24), key=lambda h: por_hora[h], reverse=True)[:3]
    return {"dias": ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"], "celdas": celdas,
            "por_hora": por_hora, "horas_pico": [{"hora": h, "anomalias": por_hora[h]} for h in top if por_hora[h]]}


def _recurrentes(db, desde, col):
    """Usuarios reincidentes: los que acumulan más anomalías en el rango."""
    return filas_a_dicts(db.execute(
        f"""SELECT u.id, u.nombre, u.email, u.estado,
                   COUNT(a.id) AS anomalias,
                   COUNT(DISTINCT a.tipo) AS tipos_distintos,
                   MAX(t.fecha_txn) AS ultima,
                   (SELECT COUNT(*) FROM transacciones x WHERE x.usuario_id = u.id
                       AND {col.replace("t.", "x.")} >= :desde) AS transacciones
            {UNION_ANOMALIAS} JOIN usuarios u ON u.id = t.usuario_id
            WHERE {col} >= :desde
            GROUP BY u.id HAVING COUNT(a.id) >= 2
            ORDER BY anomalias DESC, transacciones DESC LIMIT 8""", {"desde": desde}))


def _multiples(db, desde, col):
    """Últimos casos de múltiples transacciones en la ventana."""
    return filas_a_dicts(db.execute(
        f"""SELECT a.id, a.tipo, a.nivel, a.cantidad_transacciones, a.ventana_segundos, a.estado,
                   t.fecha_txn, t.id_txn, u.email
            {UNION_ANOMALIAS} JOIN usuarios u ON u.id = t.usuario_id
            WHERE {col} >= ? AND a.tipo IN ('POSIBLE_FRAUDE', 'RAFAGA')
            ORDER BY {col} DESC LIMIT 8""", (desde,)))


def _ultimas(db, desde, estados, col):
    marcadores = ",".join("?" for _ in estados)
    return filas_a_dicts(db.execute(
        f"""SELECT t.id, t.id_txn, t.valor, t.fecha_txn, t.metodo_pago, t.estado, t.origen, u.email,
                   (SELECT GROUP_CONCAT(tipo) FROM anomalias WHERE transaccion_id = t.id) AS tipos
            FROM transacciones t JOIN usuarios u ON u.id = t.usuario_id
            WHERE {col} >= ? AND t.estado IN ({marcadores})
            ORDER BY {col} DESC, t.id DESC LIMIT 8""", (desde, *estados)))


def _mayor_sospechosa(db, desde, col):
    """Divide y vencerás sobre los montos sospechosos del rango."""
    filas = filas_a_dicts(db.execute(
        f"""SELECT t.id_txn, t.valor, t.fecha_txn, u.email FROM transacciones t
            JOIN usuarios u ON u.id = t.usuario_id
            WHERE {col} >= ? AND t.estado != 'APROBADA'""", (desde,)))
    mayor = mayor_por_division(filas, clave=lambda f: f["valor"])
    return {"transaccion": mayor, "comparadas": len(filas)}


def listar_transacciones(db, estado=None, busqueda=None, pagina=1, por_pagina=15):
    condiciones, parametros = [], []
    if estado:
        condiciones.append("t.estado = ?")
        parametros.append(estado)
    if busqueda:
        condiciones.append("(u.email LIKE ? OR t.id_txn LIKE ?)")
        patron = f"%{busqueda}%"
        parametros += [patron, patron]
    donde = (" WHERE " + " AND ".join(condiciones)) if condiciones else ""
    total = db.execute(
        f"SELECT COUNT(*) FROM transacciones t JOIN usuarios u ON u.id = t.usuario_id{donde}", parametros
    ).fetchone()[0]
    filas = filas_a_dicts(db.execute(
        f"""SELECT t.id, t.id_txn, t.valor, t.fecha_txn, t.metodo_pago, t.estado, t.origen, t.hash_valido,
                   t.firma, t.fecha_creacion, u.email,
                   (SELECT GROUP_CONCAT(tipo) FROM anomalias WHERE transaccion_id = t.id) AS tipos
            FROM transacciones t JOIN usuarios u ON u.id = t.usuario_id{donde}
            ORDER BY t.fecha_creacion DESC, t.id DESC LIMIT ? OFFSET ?""",
        (*parametros, por_pagina, (max(1, pagina) - 1) * por_pagina)))
    return {"transacciones": filas, "total": total, "pagina": max(1, pagina),
            "paginas": max(1, -(-total // por_pagina))}
