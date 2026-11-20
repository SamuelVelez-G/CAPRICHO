"""
CRUD de categorías.

El nombre se guarda como lo escribió el administrador, pero la unicidad se
revisa con su clave normalizada: "Granizados", "granizado " y "GRANIZADOS"
son la misma categoría y no se puede crear dos veces (categorías
inconsistentes es uno de los problemas de calidad de datos del enunciado).
"""

from ..db import fila_a_dict, filas_a_dicts
from ..errores import ErrorConflicto, ErrorNoEncontrado
from ..registro import logger
from ..tiempo import a_texto, ahora
from . import normalizacion

CONSULTA = """SELECT c.*, (SELECT COUNT(*) FROM productos p WHERE p.categoria_id = c.id) AS productos
              FROM categorias c"""


def _publica(categoria):
    categoria = dict(categoria)
    categoria["activo"] = bool(categoria["activo"])
    return categoria


def listar(db, incluir_inactivas=False):
    consulta = CONSULTA + ("" if incluir_inactivas else " WHERE c.activo = 1") + " ORDER BY c.nombre"
    return [_publica(c) for c in filas_a_dicts(db.execute(consulta))]


def obtener(db, categoria_id):
    categoria = fila_a_dict(db.execute(CONSULTA + " WHERE c.id = ?", (categoria_id,)).fetchone())
    if categoria is None:
        raise ErrorNoEncontrado(f"No existe la categoría {categoria_id}")
    return _publica(categoria)


def _clave_libre(db, nombre, excepto_id=None):
    clave = normalizacion.clave(nombre)
    fila = db.execute("SELECT id, nombre FROM categorias WHERE clave = ? AND id != ?", (clave, excepto_id or 0)).fetchone()
    if fila:
        raise ErrorConflicto(f"Ya existe la categoría «{fila['nombre']}» (se compara sin tildes, mayúsculas "
                             "ni plurales)", {"nombre": "Categoría repetida"})
    return clave


def crear(db, datos):
    clave = _clave_libre(db, datos["nombre"])
    momento = a_texto(ahora())
    cursor = db.execute(
        """INSERT INTO categorias (nombre, clave, descripcion, activo, fecha_creacion, fecha_actualizacion)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (datos["nombre"], clave, datos["descripcion"], int(datos["activo"]), momento, momento))
    db.commit()
    logger.info("POST categoría #%s %s", cursor.lastrowid, datos["nombre"])
    return obtener(db, cursor.lastrowid)


def actualizar(db, categoria_id, cambios):
    """PUT y PATCH: los nombres de columna salen de la lista validada, nunca del usuario."""
    obtener(db, categoria_id)
    if "nombre" in cambios:
        cambios = {**cambios, "clave": _clave_libre(db, cambios["nombre"], categoria_id)}
    columnas = ", ".join(f"{campo} = ?" for campo in cambios)
    valores = [int(v) if isinstance(v, bool) else v for v in cambios.values()]
    db.execute(f"UPDATE categorias SET {columnas}, fecha_actualizacion = ? WHERE id = ?",
               (*valores, a_texto(ahora()), categoria_id))
    db.commit()
    logger.info("PATCH categoría #%s campos=%s", categoria_id, list(cambios))
    return obtener(db, categoria_id)


def eliminar(db, categoria_id):
    categoria = obtener(db, categoria_id)
    if categoria["productos"]:
        raise ErrorConflicto(f"La categoría tiene {categoria['productos']} productos. Muévelos a otra o "
                             "desactívala con PATCH {\"activo\": false}.")
    db.execute("DELETE FROM categorias WHERE id = ?", (categoria_id,))
    db.commit()
    logger.info("DELETE categoría #%s", categoria_id)
