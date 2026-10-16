"""
Estadísticas del dashboard (diapositiva 44).

Todo lo que muestra el dashboard pasa por un único `Filtro` con tres partes,
las mismas que el usuario elige arriba del dashboard:

  fuente  vivo  -> lo que llegó de verdad: API (generador del profesor,
                   laboratorio), lotes y compras de la tienda
          demo  -> solo los datos sembrados de demostración
          todo  -> ambos
  rango   hoy, 7d, 30d, 90d, todo
  por     txn     -> la fecha que trae la transacción (campo date)
          llegada -> cuándo llegó al servidor

Así ninguna parte del dashboard mezcla datos: si una tarjeta usa el filtro,
todas lo usan. Los fragmentos de SQL salen de diccionarios fijos, nunca de
lo que escribe el usuario; los valores van como parámetros.
"""

import math
from datetime import timedelta

from ..db import filas_a_dicts
from ..errores import ErrorValidacion
from ..estructuras import mayor_por_division
from ..tiempo import a_texto, ahora, desde_texto
from . import detector

RANGOS = {"hoy": 1, "7d": 7, "30d": 30, "90d": 90, "todo": None}
COLUMNAS = {"txn": "t.fecha_txn", "llegada": "t.fecha_creacion"}
FUENTES = {
    "vivo": ("t.origen != 'DEMO'", "En vivo: API, laboratorio y tienda"),
    "demo": ("t.origen = 'DEMO'", "Demo: datos de demostración"),
    "todo": ("1 = 1", "Todos los datos: en vivo y demo"),
}
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


class Filtro:
    """Fuente + rango + columna de fecha, validados una sola vez."""

    def __init__(self, rango="30d", por="txn", fuente="vivo", momento=None):
        errores = {}
        if rango not in RANGOS:
            errores["rango"] = f"Debe ser uno de: {', '.join(RANGOS)}"
        if por not in COLUMNAS:
            errores["por"] = "Debe ser txn o llegada"
        if fuente not in FUENTES:
            errores["fuente"] = f"Debe ser uno de: {', '.join(FUENTES)}"
        if errores:
            raise ErrorValidacion(errores)
        self.rango, self.por, self.fuente = rango, por, fuente
        self.momento = momento or ahora()
        self.col = COLUMNAS[por]
        self.sql_fuente = FUENTES[fuente][0]
        self.desde_dt, self.anterior_dt = limites(rango, self.momento)
        self.desde = a_texto(self.desde_dt) if self.desde_dt else "0000"

    def donde(self):
        """Condición para cualquier consulta con la tabla transacciones como `t`."""
        return f"{self.col} >= ? AND {self.sql_fuente}", (self.desde,)

    def eventos_demo(self):
        """Qué eventos de la pila mostrar: None = todos, True/False = solo demo / solo en vivo."""
        return {"vivo": False, "demo": True, "todo": None}[self.fuente]

    def describir(self):
        return {"rango": self.rango, "por": self.por, "fuente": self.fuente,
                "fuente_nombre": FUENTES[self.fuente][1]}


def _variacion(actual, anterior):
    if anterior in (None, 0):
        return None
    return round((actual - anterior) / anterior * 100, 1)


def filtrar_eventos(eventos, filtro):
    demo = filtro.eventos_demo()
    return eventos if demo is None else [e for e in eventos if bool(e.get("demo")) == demo]


def resumen(db, estado, filtro):
    col, fuente = filtro.col, filtro.sql_fuente
    where, params = filtro.donde()
    hoy = _inicio_del_dia(filtro.momento)
    periodos = {
        "hoy": a_texto(hoy),
        "semana": a_texto(hoy - timedelta(days=hoy.weekday())),   # desde el lunes
        "mes": a_texto(hoy.replace(day=1)),
    }

    # --- Hoy | Esta semana | Este mes (con la misma fuente) ---------------------
    minimo = min(periodos.values())
    txn_periodos = db.execute(
        f"""SELECT COALESCE(SUM({col} >= :hoy), 0), COALESCE(SUM({col} >= :semana), 0),
                   COALESCE(SUM({col} >= :mes), 0)
            FROM transacciones t WHERE {col} >= :minimo AND {fuente}""", {**periodos, "minimo": minimo}).fetchone()
    anom_periodos = db.execute(
        f"""SELECT COALESCE(SUM({col} >= :hoy), 0), COALESCE(SUM({col} >= :semana), 0),
                   COALESCE(SUM({col} >= :mes), 0)
            {UNION_ANOMALIAS} WHERE {col} >= :minimo AND {fuente}""", {**periodos, "minimo": minimo}).fetchone()

    # --- Totales del rango ----------------------------------------------------------
    estados = {fila["estado"]: {"cantidad": fila["cantidad"], "valor": fila["valor"]}
               for fila in db.execute(
                   f"""SELECT t.estado, COUNT(*) AS cantidad, COALESCE(SUM(t.valor), 0) AS valor
                       FROM transacciones t WHERE {where} GROUP BY t.estado""", params)}
    for nombre in ("APROBADA", "SOSPECHOSA", "RECHAZADA"):
        estados.setdefault(nombre, {"cantidad": 0, "valor": 0})
    total_txn = sum(e["cantidad"] for e in estados.values())

    fila = db.execute(
        f"""SELECT COUNT(*) AS anomalias, COUNT(DISTINCT a.transaccion_id) AS txn_con_anomalia,
                   COUNT(DISTINCT t.usuario_id) AS usuarios_afectados
            {UNION_ANOMALIAS} WHERE {where}""", params).fetchone()
    usuarios_activos = db.execute(
        f"SELECT COUNT(DISTINCT t.usuario_id) FROM transacciones t WHERE {where}", params).fetchone()[0]

    tendencia = {"transacciones": None, "anomalias": None}
    if filtro.anterior_dt:
        anteriores = (a_texto(filtro.anterior_dt), filtro.desde)
        previas = db.execute(
            f"SELECT COUNT(*) FROM transacciones t WHERE {col} >= ? AND {col} < ? AND {fuente}",
            anteriores).fetchone()[0]
        previas_anom = db.execute(
            f"SELECT COUNT(*) {UNION_ANOMALIAS} WHERE {col} >= ? AND {col} < ? AND {fuente}",
            anteriores).fetchone()[0]
        tendencia = {"transacciones": _variacion(total_txn, previas),
                     "anomalias": _variacion(fila["anomalias"], previas_anom)}

    por_estado_anomalia = {e: 0 for e in ("NUEVA", "ABIERTA", "REVISADA", "DESCARTADA")}
    for f in db.execute(f"SELECT a.estado, COUNT(*) {UNION_ANOMALIAS} WHERE {where} GROUP BY a.estado", params):
        por_estado_anomalia[f[0]] = f[1]

    por_nivel = {n: 0 for n in detector.NIVELES}
    for f in db.execute(f"SELECT a.nivel, COUNT(*) {UNION_ANOMALIAS} WHERE {where} GROUP BY a.nivel", params):
        por_nivel[f[0]] = f[1]

    por_tipo = [{"tipo": f[0], "nombre": detector.TIPOS_ANOMALIA.get(f[0], f[0]), "cantidad": f[1]}
                for f in db.execute(
                    f"""SELECT a.tipo, COUNT(*) AS n {UNION_ANOMALIAS} WHERE {where}
                        GROUP BY a.tipo ORDER BY n DESC""", params)]

    metodos = filas_a_dicts(db.execute(
        f"""SELECT t.metodo_pago AS metodo, COUNT(*) AS cantidad,
                   SUM(t.estado != 'APROBADA') AS sospechosas, COALESCE(SUM(t.valor), 0) AS valor
            FROM transacciones t WHERE {where} GROUP BY t.metodo_pago ORDER BY cantidad DESC""", params))

    origenes = {f[0]: f[1] for f in db.execute(
        f"SELECT t.origen, COUNT(*) FROM transacciones t WHERE {where} GROUP BY t.origen", params)}

    firmas = {}
    for f in db.execute(f"""SELECT t.firma, t.hash_valido, t.origen, COUNT(*) FROM transacciones t
                            WHERE {where} GROUP BY 1, 2, 3""", params):
        nombre = _nombre_firma(f[0], f[1], f[2])
        firmas[nombre] = firmas.get(nombre, 0) + f[3]

    with estado.candado:
        pila = filtrar_eventos(estado.pila_errores.elementos(), filtro)

    return {
        **filtro.describir(),
        "generado": a_texto(filtro.momento),
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
        "origenes": origenes,
        "anomalias_por_estado": por_estado_anomalia,
        "por_nivel": por_nivel,
        "por_tipo": por_tipo,
        "metodos": metodos,
        "firmas": sorted(({"firma": k, "cantidad": v} for k, v in firmas.items()), key=lambda x: -x["cantidad"]),
        "serie": _serie(db, filtro),
        "calor": _mapa_de_calor(db, filtro),
        "recurrentes": _recurrentes(db, filtro),
        "multiples": _multiples(db, filtro),
        "ultimas_aprobadas": _ultimas(db, filtro, ("APROBADA",)),
        "ultimas_sospechosas": _ultimas(db, filtro, ("SOSPECHOSA", "RECHAZADA")),
        "mayor_sospechosa": _mayor_sospechosa(db, filtro),
        "eventos": {"total": len(pila), "cima": pila[:8]},
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


def _serie(db, filtro):
    """Transacciones por día (o por hora si el rango es 'hoy') según estado,
    más las anomalías de cada tramo. Marca los picos repentinos."""
    col, fuente = filtro.col, filtro.sql_fuente
    desde_dt = filtro.desde_dt
    if filtro.rango == "hoy":
        tramo = f"substr({col}, 1, 13)"               # 2026-09-29T14
        claves = [a_texto(desde_dt + timedelta(hours=h))[:13] for h in range(filtro.momento.hour + 1)]
    else:
        tramo = f"substr({col}, 1, 10)"               # 2026-09-29
        if desde_dt is None:
            primera = db.execute(f"SELECT MIN({col}) FROM transacciones t WHERE {fuente}").fetchone()[0]
            desde_dt = _inicio_del_dia(desde_texto(primera)) if primera else _inicio_del_dia(filtro.momento)
        dias = max(1, (_inicio_del_dia(filtro.momento) - desde_dt).days + 1)
        claves = [a_texto(desde_dt + timedelta(days=d))[:10] for d in range(dias)]

    where, params = filtro.donde()
    base = {c: {"tramo": c, "APROBADA": 0, "SOSPECHOSA": 0, "RECHAZADA": 0, "anomalias": 0} for c in claves}
    for fila in db.execute(
            f"""SELECT {tramo} AS tramo, t.estado, COUNT(*) FROM transacciones t
                WHERE {where} GROUP BY tramo, t.estado""", params):
        if fila[0] in base:
            base[fila[0]][fila[1]] = fila[2]
    for fila in db.execute(f"SELECT {tramo} AS tramo, COUNT(*) {UNION_ANOMALIAS} WHERE {where} GROUP BY tramo",
                           params):
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
    return {"unidad": "hora" if filtro.rango == "hoy" else "dia", "puntos": serie}


def _mapa_de_calor(db, filtro):
    """Anomalías por día de la semana (0 = domingo en SQLite) y hora."""
    col = filtro.col
    where, params = filtro.donde()
    celdas = [[0] * 24 for _ in range(7)]
    for fila in db.execute(
            f"""SELECT CAST(strftime('%w', {col}) AS INTEGER), CAST(substr({col}, 12, 2) AS INTEGER),
                       COUNT(*) {UNION_ANOMALIAS} WHERE {where} GROUP BY 1, 2""", params):
        celdas[fila[0]][fila[1]] = fila[2]
    # Se reordena para empezar en lunes.
    celdas = celdas[1:] + celdas[:1]
    por_hora = [sum(celdas[d][h] for d in range(7)) for h in range(24)]
    top = sorted(range(24), key=lambda h: por_hora[h], reverse=True)[:3]
    return {"dias": ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"], "celdas": celdas,
            "por_hora": por_hora, "horas_pico": [{"hora": h, "anomalias": por_hora[h]} for h in top if por_hora[h]]}


def _recurrentes(db, filtro):
    """Usuarios reincidentes: los que acumulan más anomalías en el rango."""
    where, params = filtro.donde()
    where_x = where.replace("t.", "x.")
    return filas_a_dicts(db.execute(
        f"""SELECT u.id, u.nombre, u.email, u.estado,
                   COUNT(a.id) AS anomalias,
                   COUNT(DISTINCT a.tipo) AS tipos_distintos,
                   MAX(t.fecha_txn) AS ultima,
                   (SELECT COUNT(*) FROM transacciones x WHERE x.usuario_id = u.id AND {where_x}) AS transacciones
            {UNION_ANOMALIAS} JOIN usuarios u ON u.id = t.usuario_id
            WHERE {where}
            GROUP BY u.id HAVING COUNT(a.id) >= 2
            ORDER BY anomalias DESC, transacciones DESC LIMIT 8""", params + params))


def _multiples(db, filtro):
    """Últimos casos de múltiples transacciones en la ventana."""
    where, params = filtro.donde()
    return filas_a_dicts(db.execute(
        f"""SELECT a.id, a.tipo, a.nivel, a.cantidad_transacciones, a.ventana_segundos, a.estado,
                   t.fecha_txn, t.id_txn, t.origen, u.email
            {UNION_ANOMALIAS} JOIN usuarios u ON u.id = t.usuario_id
            WHERE {where} AND a.tipo IN ('POSIBLE_FRAUDE', 'RAFAGA')
            ORDER BY {filtro.col} DESC, a.id DESC LIMIT 8""", params))


def _ultimas(db, filtro, estados):
    where, params = filtro.donde()
    marcadores = ",".join("?" for _ in estados)
    return filas_a_dicts(db.execute(
        f"""SELECT t.id, t.id_txn, t.valor, t.fecha_txn, t.metodo_pago, t.estado, t.origen, u.email,
                   (SELECT GROUP_CONCAT(tipo) FROM anomalias WHERE transaccion_id = t.id) AS tipos
            FROM transacciones t JOIN usuarios u ON u.id = t.usuario_id
            WHERE {where} AND t.estado IN ({marcadores})
            ORDER BY {filtro.col} DESC, t.id DESC LIMIT 8""", (*params, *estados)))


def _mayor_sospechosa(db, filtro):
    """Divide y vencerás sobre los montos sospechosos del rango."""
    where, params = filtro.donde()
    filas = filas_a_dicts(db.execute(
        f"""SELECT t.id_txn, t.valor, t.fecha_txn, t.origen, u.email FROM transacciones t
            JOIN usuarios u ON u.id = t.usuario_id
            WHERE {where} AND t.estado != 'APROBADA'""", params))
    mayor = mayor_por_division(filas, clave=lambda f: f["valor"])
    return {"transaccion": mayor, "comparadas": len(filas)}


def listar_transacciones(db, filtro, estado=None, busqueda=None, pagina=1, por_pagina=15):
    """La tabla "Todas las transacciones" con el mismo filtro que el resto."""
    where, params = filtro.donde()
    condiciones, parametros = [where], list(params)
    if estado:
        condiciones.append("t.estado = ?")
        parametros.append(estado)
    if busqueda:
        condiciones.append("(u.email LIKE ? OR t.id_txn LIKE ?)")
        patron = f"%{busqueda}%"
        parametros += [patron, patron]
    donde = " WHERE " + " AND ".join(condiciones)
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
            "paginas": max(1, -(-total // por_pagina)), **filtro.describir()}
