"""
Análisis de ventas para el panel: indicadores, patrones y predicción de demanda.

Patrones que se buscan en los datos (horario, monto, frecuencia y canal):
  - ventas por día, por hora del día, por día de la semana, por canal y por método
  - ticket promedio y su distribución en cuartiles
  - ranking de ítems más vendidos e inventario bajo

Predicción de la demanda de los próximos 7 días con DOS modelos que se
comparan con los mismos datos:
  - regresión lineal simple (estadística simple: tendencia y = m·x + b)
  - red neuronal de Keras (ia/demanda.py), que además aprende el patrón
    semanal (los sábados se vende más)
"""

from datetime import date, timedelta

from ..tiempo import ahora
from .estadistica import perfil, regresion_lineal

DIAS_SEMANA = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]
VENDIDAS = "f.estado != 'ANULADA'"


def _dias(desde: date, hasta: date):
    dia = desde
    while dia <= hasta:
        yield dia
        dia += timedelta(days=1)


def serie_diaria(db, dias=56):
    """[(fecha, ventas, facturas)] de los últimos `dias`, con los días sin ventas en cero."""
    hoy = ahora().date()
    desde = hoy - timedelta(days=dias - 1)
    filas = {f["dia"]: f for f in db.execute(
        f"""SELECT substr(f.fecha_emision, 1, 10) AS dia, SUM(f.total) AS ventas, COUNT(*) AS facturas
            FROM facturas f WHERE {VENDIDAS} AND f.fecha_emision >= ? GROUP BY dia""", (desde.isoformat(),))}
    return [{"dia": d.isoformat(), "ventas": filas[d.isoformat()]["ventas"] if d.isoformat() in filas else 0,
             "facturas": filas[d.isoformat()]["facturas"] if d.isoformat() in filas else 0}
            for d in _dias(desde, hoy)]


def tendencia(serie, horizonte=7):
    """Regresión lineal simple sobre los días COMPLETOS (hoy todavía no termina)."""
    completos = serie[:-1]
    xs = list(range(len(completos)))
    ys = [d["ventas"] for d in completos]
    pendiente, intercepto, r2 = regresion_lineal(xs, ys)
    ultimo = date.fromisoformat(serie[-1]["dia"])
    prediccion = [{"dia": (ultimo + timedelta(days=i)).isoformat(),
                   "ventas": max(0, round(intercepto + pendiente * (len(completos) - 1 + i)))}
                  for i in range(1, horizonte + 1)]
    ajuste = [round(intercepto + pendiente * x) for x in xs]
    errores = [abs(y - a) for y, a in zip(ys, ajuste)]
    return {"pendiente": round(pendiente, 1), "intercepto": round(intercepto, 1), "r2": round(r2, 3),
            "mae": round(sum(errores) / max(len(errores), 1)), "ajuste": ajuste, "prediccion": prediccion,
            "lectura": (f"Las ventas {'suben' if pendiente > 0 else 'bajan'} en promedio "
                        f"${abs(pendiente):,.0f} por día".replace(",", "."))}


def resumen(db, dias=30):
    hoy = ahora().date()
    desde = (hoy - timedelta(days=dias - 1)).isoformat()
    anterior = (hoy - timedelta(days=2 * dias - 1)).isoformat()

    def totales(inicio, fin):
        fila = db.execute(
            f"""SELECT COALESCE(SUM(f.total), 0) AS ventas, COUNT(*) AS facturas, COALESCE(SUM(f.descuento), 0) AS descuentos,
                       COALESCE(SUM(f.impuesto), 0) AS impuesto
                FROM facturas f WHERE {VENDIDAS} AND f.fecha_emision >= ? AND f.fecha_emision < ?""",
            (inicio, fin)).fetchone()
        return dict(fila)

    actual = totales(desde, (hoy + timedelta(days=1)).isoformat())
    previo = totales(anterior, desde)
    hoy_totales = totales(hoy.isoformat(), (hoy + timedelta(days=1)).isoformat())
    tickets = [f[0] for f in db.execute(f"SELECT total FROM facturas f WHERE {VENDIDAS} AND fecha_emision >= ?", (desde,))]

    por_canal = [dict(f) for f in db.execute(
        f"""SELECT canal, COUNT(*) AS facturas, SUM(total) AS ventas FROM facturas f
            WHERE {VENDIDAS} AND fecha_emision >= ? GROUP BY canal ORDER BY ventas DESC""", (desde,))]
    por_metodo = [dict(f) for f in db.execute(
        """SELECT p.metodo, COUNT(*) AS pagos, SUM(p.monto) AS monto FROM pagos p
           WHERE p.estado = 'APROBADO' AND p.fecha >= ? GROUP BY p.metodo ORDER BY monto DESC""", (desde,))]
    por_hora = [0] * 24
    for fila in db.execute(f"""SELECT CAST(substr(fecha_emision, 12, 2) AS INTEGER) AS hora, SUM(total) AS ventas
                              FROM facturas f WHERE {VENDIDAS} AND fecha_emision >= ? GROUP BY hora""", (desde,)):
        por_hora[fila["hora"]] = fila["ventas"]
    por_dia_semana = [0] * 7
    conteo_dias = [0] * 7
    for d in serie_diaria(db, 56)[:-1]:
        semana = date.fromisoformat(d["dia"]).weekday()
        por_dia_semana[semana] += d["ventas"]
        conteo_dias[semana] += 1
    ranking = [dict(f) for f in db.execute(
        f"""SELECT i.producto_id, i.nombre, SUM(i.cantidad) AS unidades, SUM(i.subtotal) AS ventas
            FROM pedido_items i JOIN facturas f ON f.pedido_id = i.pedido_id
            WHERE {VENDIDAS} AND f.fecha_emision >= ? GROUP BY i.producto_id ORDER BY unidades DESC LIMIT 10""",
        (desde,))]
    inventario = [dict(f) for f in db.execute(
        """SELECT p.id, p.nombre, p.stock, p.stock_minimo, c.nombre AS categoria FROM productos p
           JOIN categorias c ON c.id = p.categoria_id WHERE p.activo = 1 AND p.stock <= p.stock_minimo * 2
           ORDER BY CAST(p.stock AS REAL) / MAX(p.stock_minimo, 1) LIMIT 8""")]

    serie = serie_diaria(db, 56)
    variacion = ((actual["ventas"] - previo["ventas"]) / previo["ventas"] * 100) if previo["ventas"] else None
    return {
        "dias": dias, "actual": actual, "previo": previo, "hoy": hoy_totales,
        "variacion": round(variacion, 1) if variacion is not None else None,
        "ticket": perfil(tickets), "por_canal": por_canal, "por_metodo": por_metodo, "por_hora": por_hora,
        "por_dia_semana": [{"dia": DIAS_SEMANA[i], "promedio": round(por_dia_semana[i] / max(conteo_dias[i], 1))}
                           for i in range(7)],
        "ranking": ranking, "inventario_bajo": inventario, "serie": serie, "tendencia": tendencia(serie),
    }
