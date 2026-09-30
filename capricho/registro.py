"""
Logs y diagnóstico (diapositivas 27 y 28).

Cada línea del log responde tres preguntas:
    QUÉ ocurrió    -> el mensaje
    CUÁNDO         -> fecha y hora con milisegundos
    DÓNDE          -> módulo, función y línea

    2026-09-29 19:04:11,532 | WARNING | detector.procesar_transaccion:212 | Anomalía RAFAGA ...

Además, los errores y eventos de seguridad se guardan en la tabla `eventos`
y se apilan en la PILA de errores para verlos del más reciente al más viejo.
"""

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

from .tiempo import a_texto, ahora

logger = logging.getLogger("capricho")

FORMATO = "%(asctime)s | %(levelname)-7s | %(module)s.%(funcName)s:%(lineno)d | %(message)s"


def configurar_logs(carpeta: str):
    if logger.handlers:
        return
    Path(carpeta).mkdir(parents=True, exist_ok=True)
    logger.setLevel(logging.INFO)

    archivo = RotatingFileHandler(Path(carpeta) / "capricho.log", maxBytes=1_000_000,
                                  backupCount=5, encoding="utf-8")
    archivo.setFormatter(logging.Formatter(FORMATO))
    logger.addHandler(archivo)

    consola = logging.StreamHandler()
    consola.setFormatter(logging.Formatter("%(levelname)-7s | %(message)s"))
    consola.setLevel(logging.WARNING)
    logger.addHandler(consola)
    logger.propagate = False


def registrar_evento(db, estado, tipo, nivel, detalle, *, ruta=None, metodo=None,
                     ip=None, email=None, momento=None, confirmar=True):
    """Guarda el evento, lo apila y lo escribe en el log."""
    momento = momento or ahora()
    cursor = db.execute(
        """INSERT INTO eventos (tipo, nivel, detalle, ruta, metodo, ip, email, fecha)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (tipo, nivel, detalle[:500], ruta, metodo, ip, email, a_texto(momento)),
    )
    if confirmar:
        db.commit()
    evento = {
        "id": cursor.lastrowid, "tipo": tipo, "nivel": nivel, "detalle": detalle[:500],
        "ruta": ruta, "metodo": metodo, "ip": ip, "email": email, "fecha": a_texto(momento),
    }
    with estado.candado:
        estado.pila_errores.apilar(evento)
    nivel_log = logging.ERROR if nivel == "CRITICO" else logging.WARNING
    logger.log(nivel_log, "Evento %s [%s] %s %s ip=%s: %s",
               tipo, nivel, metodo or "", ruta or "", ip or "-", detalle, stacklevel=2)
    return evento
