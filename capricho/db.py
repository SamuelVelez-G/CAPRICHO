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
