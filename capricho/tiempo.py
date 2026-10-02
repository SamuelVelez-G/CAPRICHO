"""
Manejo de fechas.

Todas las fechas se guardan como texto ISO con milisegundos:
    2026-09-23T10:30:01.120
Con un formato fijo, comparar dos fechas como texto da el mismo resultado
que compararlas como fechas, y eso deja que SQLite use los índices.
"""

import re
from datetime import datetime

# Formato que acepta el endpoint (diapositiva 40): "2026-09-23T10:30:01.120"
PATRON_FECHA_ISO = re.compile(
    r"^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(\.\d{1,6})?(Z|[+-]\d{2}:?\d{2})?$"
)


def ahora() -> datetime:
    return datetime.now()


def a_texto(momento: datetime) -> str:
    return momento.isoformat(timespec="milliseconds")


def desde_texto(texto: str) -> datetime:
    return datetime.fromisoformat(texto)


def interpretar_fecha_externa(texto: str) -> datetime:
    """Convierte la fecha que manda un cliente externo.

    Si trae zona horaria (Z o -05:00) se pasa a la hora local del servidor.
    Se recorta a milisegundos porque es la precisión con la que se guarda.
    Lanza ValueError si el texto no es una fecha válida.
    """
    if not PATRON_FECHA_ISO.match(texto):
        raise ValueError("formato inválido")
    momento = datetime.fromisoformat(texto.replace("Z", "+00:00"))
    if momento.tzinfo is not None:
        momento = momento.astimezone().replace(tzinfo=None)
    return momento.replace(microsecond=(momento.microsecond // 1000) * 1000)
