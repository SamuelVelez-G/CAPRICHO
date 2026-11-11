"""
Variables de comportamiento que "ve" la red neuronal por cada transacción.

Una red neuronal no entiende "la cliente compró a las 3 a. m. con un método
raro": entiende números. Aquí se convierte cada compra en 9 números que
describen QUÉ se compró y, sobre todo, si se parece a lo que ese cliente
suele hacer. Se calculan con la misma búsqueda por índice que usa la ventana
deslizante: solo las transacciones anteriores del mismo usuario.

La MISMA función se usa al entrenar y al evaluar en vivo; si se calcularan
distinto, el modelo vería datos que nunca aprendió.
"""

import math
from datetime import timedelta
from statistics import median

from ..tiempo import a_texto, desde_texto

NOMBRES = [
    "hora_seno", "hora_coseno", "monto", "monto_vs_habitual", "metodo_habitual",
    "hora_vs_habitual", "compras_ultima_hora", "horas_desde_anterior", "historial",
]

# Cómo se le explica cada variable a una persona.
ETIQUETAS = {
    "hora": "Hora de la compra",
    "monto": "Monto de la compra",
    "monto_vs_habitual": "Monto comparado con lo habitual del cliente",
    "metodo_habitual": "Método de pago comparado con el habitual",
    "hora_vs_habitual": "Hora comparada con su horario habitual",
    "compras_ultima_hora": "Compras en la última hora",
    "horas_desde_anterior": "Tiempo desde su compra anterior",
    "historial": "Historial del cliente",
}

HISTORIAL_MINIMO = 3        # con menos compras no hay "hábito" que comparar
VENTANA_HABITO = 30         # se miran sus últimas 30 compras
TOPE_HORAS = 24 * 30        # más de 30 días sin comprar cuenta como 30 días


def _distancia_horaria(a, b):
    """Distancia en un reloj de 24 horas: entre las 23:00 y las 01:00 hay 2 horas, no 22."""
    d = abs(a - b) % 24
    return min(d, 24 - d)


def _hora_media(horas):
    """Promedio circular: el promedio de 23:00 y 01:00 es medianoche, no mediodía."""
    seno = sum(math.sin(2 * math.pi * h / 24) for h in horas)
    coseno = sum(math.cos(2 * math.pi * h / 24) for h in horas)
    return (math.atan2(seno, coseno) * 24 / (2 * math.pi)) % 24


def vector(hora, valor, monto_habitual, proporcion_metodo, hora_habitual, compras_ultima_hora,
           horas_desde_anterior, compras_previas):
    """Los 9 números que entran a la red. Si el cliente no tiene historial
    suficiente, las comparaciones con su hábito quedan en un valor neutro."""
    con_habito = compras_previas >= HISTORIAL_MINIMO
    return [
        math.sin(2 * math.pi * hora / 24),                     # la hora es circular: 23:59 está
        math.cos(2 * math.pi * hora / 24),                     # junto a 00:00, por eso seno y coseno
        math.log10(max(valor, 1)),                             # escala logarítmica: $7.000 vs $700.000
        math.log10(max(valor, 1) / monto_habitual) if con_habito else 0.0,
        proporcion_metodo if con_habito else 0.5,
        _distancia_horaria(hora, hora_habitual) / 12 if con_habito else 0.5,
        math.log1p(compras_ultima_hora),
        math.log10(1 + min(horas_desde_anterior, TOPE_HORAS)),
        math.log1p(min(compras_previas, 200)),
    ]


def desde_historial(db, usuario_id, fecha, valor, metodo):
    """Calcula el vector con el historial real del usuario en la base de datos.

    Devuelve (vector, contexto). `contexto` guarda los valores legibles para
    explicar el resultado ("su compra habitual es de $10.000").
    """
    previas = db.execute(
        """SELECT fecha_txn, valor, metodo_pago FROM transacciones
           WHERE usuario_id = ? AND fecha_txn < ?
           ORDER BY fecha_txn DESC LIMIT ?""",
        (usuario_id, a_texto(fecha), VENTANA_HABITO),
    ).fetchall()
    total_previas = db.execute(
        "SELECT COUNT(*) FROM transacciones WHERE usuario_id = ? AND fecha_txn < ?",
        (usuario_id, a_texto(fecha)),
    ).fetchone()[0]
    ultima_hora = db.execute(
        "SELECT COUNT(*) FROM transacciones WHERE usuario_id = ? AND fecha_txn >= ? AND fecha_txn < ?",
        (usuario_id, a_texto(fecha - timedelta(hours=1)), a_texto(fecha)),
    ).fetchone()[0]

    hora = fecha.hour + fecha.minute / 60
    if previas:
        horas_previas = [desde_texto(f["fecha_txn"]) for f in previas]
        monto_habitual = median(f["valor"] for f in previas)
        proporcion_metodo = sum(f["metodo_pago"] == metodo for f in previas) / len(previas)
        hora_habitual = _hora_media([h.hour + h.minute / 60 for h in horas_previas])
        horas_desde = (fecha - horas_previas[0]).total_seconds() / 3600
    else:
        monto_habitual, proporcion_metodo, hora_habitual, horas_desde = valor, 0.5, hora, TOPE_HORAS

    contexto = {
        "hora": hora, "valor": valor, "metodo": metodo, "monto_habitual": monto_habitual,
        "proporcion_metodo": proporcion_metodo, "hora_habitual": hora_habitual,
        "compras_ultima_hora": ultima_hora, "horas_desde_anterior": horas_desde,
        "compras_previas": total_previas,
    }
    return vector(hora, valor, monto_habitual, proporcion_metodo, hora_habitual, ultima_hora,
                  horas_desde, total_previas), contexto


def desde_contexto(contexto):
    """Para el probador: el contexto lo describe la persona en el formulario."""
    return vector(contexto["hora"], contexto["valor"], contexto["monto_habitual"],
                  contexto["proporcion_metodo"], contexto["hora_habitual"],
                  contexto["compras_ultima_hora"], contexto["horas_desde_anterior"],
                  contexto["compras_previas"])


def _hhmm(hora):
    h = int(hora) % 24
    return f"{h:02d}:{int(round((hora - int(hora)) * 60)) % 60:02d}"


def _dinero(valor):
    return f"${valor:,.0f}".replace(",", ".")


def explicar(grupo, contexto):
    """Frase para una persona sobre por qué esa variable se ve rara."""
    c = contexto
    if grupo == "hora":
        return f"Compra a las {_hhmm(c['hora'])}"
    if grupo == "monto":
        return f"Monto de {_dinero(c['valor'])}"
    if grupo == "monto_vs_habitual":
        veces = c["valor"] / c["monto_habitual"] if c["monto_habitual"] else 1
        return f"{_dinero(c['valor'])} es {veces:.1f} veces su compra habitual ({_dinero(c['monto_habitual'])})"
    if grupo == "metodo_habitual":
        return f"Pagó con {c['metodo']}, que usa en el {c['proporcion_metodo'] * 100:.0f} % de sus compras"
    if grupo == "hora_vs_habitual":
        return f"Compró a las {_hhmm(c['hora'])} y suele comprar cerca de las {_hhmm(c['hora_habitual'])}"
    if grupo == "compras_ultima_hora":
        return f"{c['compras_ultima_hora']} compras en la última hora"
    if grupo == "horas_desde_anterior":
        horas = c["horas_desde_anterior"]
        texto = f"{horas * 60:.0f} minutos" if horas < 2 else f"{horas:.0f} horas" if horas < 48 else f"{horas / 24:.0f} días"
        return f"{texto} desde su compra anterior"
    if grupo == "historial":
        return f"{c['compras_previas']} compras anteriores"
    return grupo


# Las dos variables de la hora se explican juntas.
GRUPOS = {
    "hora_seno": "hora", "hora_coseno": "hora", "monto": "monto", "monto_vs_habitual": "monto_vs_habitual",
    "metodo_habitual": "metodo_habitual", "hora_vs_habitual": "hora_vs_habitual",
    "compras_ultima_hora": "compras_ultima_hora", "horas_desde_anterior": "horas_desde_anterior",
    "historial": "historial",
}
