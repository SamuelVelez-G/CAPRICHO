"""Revisión de anomalías: listado con filtros, detalle con su línea de tiempo
y cambio de estado (NUEVA -> ABIERTA -> REVISADA / DESCARTADA)."""

from datetime import timedelta

from ..db import fila_a_dict, filas_a_dicts
from ..errores import ErrorConflicto, ErrorNoEncontrado, ErrorValidacion
from ..registro import logger
from ..tiempo import a_texto, ahora, desde_texto
from .detector import NIVELES, TIPOS_ANOMALIA

ESTADOS = ("NUEVA", "ABIERTA", "REVISADA", "DESCARTADA")
TRANSICIONES = {
    "NUEVA": ("ABIERTA", "REVISADA", "DESCARTADA"),
    "ABIERTA": ("REVISADA", "DESCARTADA"),
    "REVISADA": ("ABIERTA",),
    "DESCARTADA": ("ABIERTA",),
}
POR_PAGINA = 12

CONSULTA = """SELECT a.*, t.id_txn, t.valor, t.fecha_txn, t.metodo_pago, t.estado AS estado_txn,
                     u.id AS usuario_id, u.email, u.nombre
              FROM anomalias a
              JOIN transacciones t ON t.id = a.transaccion_id
              JOIN usuarios u ON u.id = t.usuario_id"""


def listar(db, estado=None, nivel=None, tipo=None, pagina=1):
    """Los filtros solo aceptan valores de listas cerradas; el SQL se arma
    con condiciones fijas y los valores van como parámetros."""
    errores = {}
    if estado and estado not in ESTADOS:
        errores["estado"] = "Estado desconocido"
    if nivel and nivel not in NIVELES:
        errores["nivel"] = "Nivel desconocido"
    if tipo and tipo not in TIPOS_ANOMALIA:
        errores["tipo"] = "Tipo desconocido"
    if errores:
        raise ErrorValidacion(errores)

    condiciones, parametros = [], []
    for columna, valor in (("a.estado", estado), ("a.nivel", nivel), ("a.tipo", tipo)):
        if valor:
            condiciones.append(f"{columna} = ?")
            parametros.append(valor)
    donde = (" WHERE " + " AND ".join(condiciones)) if condiciones else ""

    total = db.execute(f"SELECT COUNT(*) FROM anomalias a{donde}", parametros).fetchone()[0]
    pagina = max(1, pagina)
    filas = filas_a_dicts(db.execute(
        CONSULTA + donde + " ORDER BY a.fecha_creacion DESC, a.id DESC LIMIT ? OFFSET ?",
        (*parametros, POR_PAGINA, (pagina - 1) * POR_PAGINA),
    ))
    return {"anomalias": filas, "total": total, "pagina": pagina,
            "paginas": max(1, -(-total // POR_PAGINA))}


def detalle(db, anomalia_id):
    anomalia = fila_a_dict(db.execute(CONSULTA + " WHERE a.id = ?", (anomalia_id,)).fetchone())
    if anomalia is None:
        raise ErrorNoEncontrado(f"No existe la anomalía #{anomalia_id}")

    historial = filas_a_dicts(db.execute(
        "SELECT * FROM anomalias_historial WHERE anomalia_id = ? ORDER BY fecha, id", (anomalia_id,)))

    # Transacciones del mismo usuario alrededor del momento, para dibujar
    # la ventana deslizante.
    instante = desde_texto(anomalia["fecha_txn"])
    margen = max(anomalia["ventana_segundos"] * 2.5, 8)
    vecinas = filas_a_dicts(db.execute(
        """SELECT t.id, t.id_txn, t.valor, t.fecha_txn, t.estado, t.hash_valido,
                  (SELECT GROUP_CONCAT(tipo) FROM anomalias WHERE transaccion_id = t.id) AS tipos
           FROM transacciones t
           WHERE t.usuario_id = ? AND t.fecha_txn BETWEEN ? AND ?
           ORDER BY t.fecha_txn LIMIT 80""",
        (anomalia["usuario_id"], a_texto(instante - timedelta(seconds=margen)),
         a_texto(instante + timedelta(seconds=margen))),
    ))
    for vecina in vecinas:
        vecina["desfase"] = round((desde_texto(vecina["fecha_txn"]) - instante).total_seconds(), 3)
        vecina["es_actual"] = vecina["id"] == anomalia["transaccion_id"]

    otras = db.execute(
        """SELECT COUNT(*) FROM anomalias a JOIN transacciones t ON t.id = a.transaccion_id
           WHERE t.usuario_id = ? AND a.id != ?""", (anomalia["usuario_id"], anomalia_id)).fetchone()[0]

    return {"anomalia": anomalia, "historial": historial, "ventana": vecinas,
            "margen_segundos": margen, "otras_del_usuario": otras,
            "transiciones": TRANSICIONES[anomalia["estado"]]}


def cambiar_estado(db, anomalia_id, nuevo, nota, responsable):
    fila = db.execute("SELECT estado FROM anomalias WHERE id = ?", (anomalia_id,)).fetchone()
    if fila is None:
        raise ErrorNoEncontrado(f"No existe la anomalía #{anomalia_id}")
    actual = fila["estado"]
    if nuevo not in TRANSICIONES[actual]:
        raise ErrorConflicto(
            f"Una anomalía {actual} no puede pasar a {nuevo}. Opciones: {', '.join(TRANSICIONES[actual])}")
    momento = a_texto(ahora())
    db.execute("UPDATE anomalias SET estado = ?, fecha_actualizacion = ? WHERE id = ?",
               (nuevo, momento, anomalia_id))
    db.execute(
        """INSERT INTO anomalias_historial (anomalia_id, estado_anterior, estado_nuevo, nota, responsable, fecha)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (anomalia_id, actual, nuevo, nota, responsable, momento),
    )
    db.commit()
    logger.info("Anomalía #%s %s -> %s por %s", anomalia_id, actual, nuevo, responsable)
    return detalle(db, anomalia_id)
