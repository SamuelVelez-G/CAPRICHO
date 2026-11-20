"""
Alertas que no pertenecen a una sola transacción: descuentos o anulaciones
fuera de lo normal de un empleado, comprobantes falsos o reutilizados,
cadenas de integridad rotas y problemas de calidad de datos.
"""

import json

from ..db import filas_a_dicts
from ..errores import ErrorNoEncontrado, ErrorValidacion
from ..registro import logger
from ..tiempo import a_texto, ahora

TIPOS = {
    "DESCUENTOS_ATIPICOS": "Un empleado dio muchos más descuentos de lo normal",
    "DESCUENTO_ALTO": "Descuento muy alto en una sola factura",
    "ANULACIONES_ATIPICAS": "Un empleado anuló muchas más facturas de lo normal",
    "ANULACION_DESPUES_DE_PAGO": "Factura pagada que luego se anuló",
    "MONTO_ATIPICO_USUARIO": "Monto fuera de los cuartiles del cliente",
    "COMPROBANTE_REUTILIZADO": "El mismo comprobante o referencia en dos pagos",
    "COMPROBANTE_FALSO": "Comprobante con firma inválida",
    "COMPROBANTE_NO_COINCIDE": "El comprobante no corresponde al pago",
    "CADENA_ROTA": "La cadena de hashes de facturas o pagos no cuadra",
    "CALIDAD_DATOS": "Problemas de calidad en los datos",
}
NIVELES = ("BAJO", "MEDIO", "ALTO", "CRITICO")


def crear(db, tipo, nivel, origen, detalle, *, usuario_id=None, entidad=None, entidad_id=None, datos=None,
          demo=False, momento=None):
    cursor = db.execute(
        """INSERT INTO alertas (tipo, nivel, origen, usuario_id, entidad, entidad_id, detalle, datos, demo, fecha)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (tipo, nivel, origen, usuario_id, entidad, entidad_id, detalle[:500],
         json.dumps(datos, ensure_ascii=False) if datos is not None else None, int(demo),
         a_texto(momento or ahora())))
    if not demo:
        logger.warning("Alerta %s [%s]: %s", tipo, nivel, detalle)
    return cursor.lastrowid


def existe_hoy(db, tipo, usuario_id, momento):
    """Para no repetir la misma alerta del mismo usuario varias veces el mismo día."""
    dia = a_texto(momento)[:10]
    return db.execute("SELECT 1 FROM alertas WHERE tipo = ? AND usuario_id = ? AND substr(fecha, 1, 10) = ?",
                      (tipo, usuario_id, dia)).fetchone() is not None


def listar(db, origen=None, estado=None, nivel=None, limite=60):
    condiciones, parametros = [], []
    for columna, valor in (("a.origen", origen), ("a.estado", estado), ("a.nivel", nivel)):
        if valor:
            condiciones.append(f"{columna} = ?")
            parametros.append(valor)
    donde = (" WHERE " + " AND ".join(condiciones)) if condiciones else ""
    filas = filas_a_dicts(db.execute(
        f"""SELECT a.*, u.nombre AS usuario, u.email, u.rol FROM alertas a
            LEFT JOIN usuarios u ON u.id = a.usuario_id{donde} ORDER BY a.fecha DESC, a.id DESC LIMIT ?""",
        (*parametros, limite)))
    for fila in filas:
        fila["datos"] = json.loads(fila["datos"]) if fila["datos"] else None
        fila["descripcion"] = TIPOS.get(fila["tipo"], fila["tipo"])
    return filas


def resumen(db):
    filas = db.execute("""SELECT origen, nivel, estado, COUNT(*) AS n FROM alertas GROUP BY origen, nivel, estado""")
    total = {"total": 0, "nuevas": 0, "por_origen": {}, "por_nivel": {}}
    for fila in filas:
        total["total"] += fila["n"]
        total["nuevas"] += fila["n"] if fila["estado"] == "NUEVA" else 0
        total["por_origen"][fila["origen"]] = total["por_origen"].get(fila["origen"], 0) + fila["n"]
        total["por_nivel"][fila["nivel"]] = total["por_nivel"].get(fila["nivel"], 0) + fila["n"]
    return total


def cambiar_estado(db, alerta_id, nuevo):
    if nuevo not in ("NUEVA", "REVISADA", "DESCARTADA"):
        raise ErrorValidacion({"estado": "Debe ser NUEVA, REVISADA o DESCARTADA"})
    cursor = db.execute("UPDATE alertas SET estado = ? WHERE id = ?", (nuevo, alerta_id))
    if cursor.rowcount == 0:
        raise ErrorNoEncontrado(f"No existe la alerta {alerta_id}")
    db.commit()
