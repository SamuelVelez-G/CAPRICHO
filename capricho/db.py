"""
Conexión a SQLite.

Regla de oro del proyecto: NINGUNA consulta arma SQL pegando texto del
usuario. Todas usan parámetros con "?", y SQLite recibe los datos por
separado, así que un "' OR 1=1 --" se guarda como texto y nunca se ejecuta.
"""

import sqlite3
from pathlib import Path

from flask import current_app, g

ESQUEMA = Path(__file__).with_name("esquema.sql")


def conectar(ruta: str) -> sqlite3.Connection:
    Path(ruta).parent.mkdir(parents=True, exist_ok=True)
    conexion = sqlite3.connect(ruta, timeout=15)
    conexion.row_factory = sqlite3.Row
    conexion.execute("PRAGMA foreign_keys = ON")
    conexion.execute("PRAGMA busy_timeout = 15000")
    # En modo WAL, NORMAL es seguro y evita esperar al disco en cada commit:
    # importante cuando llegan miles de transacciones seguidas.
    conexion.execute("PRAGMA synchronous = NORMAL")
    return conexion


def obtener_db() -> sqlite3.Connection:
    """Una conexión por petición, guardada en `g` y cerrada al terminar."""
    if "db" not in g:
        g.db = conectar(current_app.config["BASE_DATOS"])
    return g.db


def cerrar_db(_error=None):
    conexion = g.pop("db", None)
    if conexion is not None:
        conexion.close()


VERSION_ESQUEMA = 2


def respaldar_si_es_antigua(ruta: str):
    """La versión 2 cambió tablas (categorías, inventario, facturas, pagos).
    Una base de la versión 1 no se puede migrar con ALTER TABLE porque
    cambian restricciones CHECK; se guarda como respaldo y se crea una nueva.
    Devuelve la ruta del respaldo o None."""
    archivo = Path(ruta)
    if not archivo.exists():
        return None
    conexion = sqlite3.connect(ruta)
    try:
        version = conexion.execute("PRAGMA user_version").fetchone()[0]
        tablas = conexion.execute("SELECT COUNT(*) FROM sqlite_master WHERE type = 'table'").fetchone()[0]
    finally:
        conexion.close()
    if tablas == 0 or version >= VERSION_ESQUEMA:
        return None
    from datetime import datetime
    respaldo = archivo.with_name(f"{archivo.stem}-v{version or 1}-respaldo-{datetime.now():%Y%m%d%H%M%S}{archivo.suffix}")
    archivo.rename(respaldo)
    for sufijo in ("-wal", "-shm"):
        Path(ruta + sufijo).unlink(missing_ok=True)
    return respaldo


def crear_esquema(conexion: sqlite3.Connection):
    conexion.execute("PRAGMA journal_mode = WAL")   # lecturas y escrituras en paralelo
    conexion.executescript(ESQUEMA.read_text(encoding="utf-8"))
    conexion.commit()


def esta_vacia(conexion: sqlite3.Connection) -> bool:
    return conexion.execute("SELECT COUNT(*) FROM usuarios").fetchone()[0] == 0


def fila_a_dict(fila):
    return dict(fila) if fila is not None else None


def filas_a_dicts(filas):
    return [dict(fila) for fila in filas]


def init_app(app):
    app.teardown_appcontext(cerrar_db)
