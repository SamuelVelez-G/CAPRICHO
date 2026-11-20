"""
Variables que ve el CLASIFICADOR de operaciones (normal o fraudulenta).

Respuesta a la observación del profesor: el autoencoder de la exposición
solo comparaba cada compra con los hábitos de ESE cliente; con un cliente
nuevo no tenía con qué comparar. El clasificador aprende de TODA la
población, con dos tipos de variables:

  GENERALES (sirven aunque el cliente sea nuevo): hora, día, monto, monto
  frente a lo que paga cualquier cliente, método de pago, firma, frecuencia
  en el último minuto, hora y día, métodos distintos en 24 h, tiempo desde la
  compra anterior y antigüedad del cliente.

  PERSONALES (solo si hay historial; si no, quedan en un valor neutro): monto
  frente a su mediana, puntaje z del monto, qué tanto usa ese método y qué tan
  lejos está de su horario.

La variable "historial" le dice a la red cuánto puede confiar en las
personales. Así, con un cliente nuevo la red decide con lo que aprendió de
todos los demás (por ejemplo: cuenta nueva + madrugada + PSE + monto alto).

La MISMA función se usa con el simulador (entrenamiento) y con la base de
datos (en vivo): si se calcularan distinto, el modelo vería datos que nunca aprendió.
"""

import math
import statistics
from datetime import timedelta

from ..tiempo import a_texto, desde_texto

METODOS = ["Nequi", "Tarjeta", "Daviplata", "PSE", "Efectivo"]
NOMBRES = [
    "hora_seno", "hora_coseno", "fin_de_semana", "monto_log", "monto_vs_poblacion",
    "metodo_nequi", "metodo_tarjeta", "metodo_daviplata", "metodo_pse", "metodo_efectivo", "metodo_otro",
    "firma_valida", "compras_1min", "compras_1h", "compras_24h", "metodos_24h", "horas_desde_anterior",
    "historial", "es_nuevo",
    "monto_vs_habitual", "metodo_habitual", "hora_vs_habitual", "monto_z",
]
# Grupos para explicar el resultado (las variables de un mismo concepto se explican juntas).
GRUPOS = {
    "hora": [0, 1], "dia": [2], "monto": [3, 4], "metodo": [5, 6, 7, 8, 9, 10], "firma": [11],
    "frecuencia": [12, 13, 14, 15], "recencia": [16], "antiguedad": [17, 18],
    "monto_habitual": [19, 22], "metodo_habitual": [20], "hora_habitual": [21],
}
PERSONALES = ("monto_habitual", "metodo_habitual", "hora_habitual")
ETIQUETAS = {
    "hora": "Hora de la operación", "dia": "Día de la semana", "monto": "Monto frente a cualquier cliente",
    "metodo": "Método de pago", "firma": "Firma de la transacción", "frecuencia": "Frecuencia reciente",
    "recencia": "Tiempo desde la compra anterior", "antiguedad": "Antigüedad del cliente",
    "monto_habitual": "Monto frente a lo habitual del cliente", "metodo_habitual": "Método frente al habitual",
    "hora_habitual": "Hora frente a su horario",
}
HISTORIAL_MINIMO = 3
TOPE_HORAS = 24 * 30
VENTANA_HISTORIA = 60      # compras anteriores que se miran


def _distancia_horaria(a, b):
    d = abs(a - b) % 24
    return min(d, 24 - d)


def _hora_media(horas):
    seno = sum(math.sin(2 * math.pi * h / 24) for h in horas)
    coseno = sum(math.cos(2 * math.pi * h / 24) for h in horas)
    return (math.atan2(seno, coseno) * 24 / (2 * math.pi)) % 24


def vector(fecha, valor, metodo, firma_valida, previas, total_previas, mediana_poblacion):
    """previas: [(fecha, valor, metodo)] del mismo cliente ANTES de esta operación,
    de la más reciente a la más antigua (máximo VENTANA_HISTORIA).
    Devuelve (vector de 23 números, contexto legible para explicar)."""
    hora = fecha.hour + fecha.minute / 60 + fecha.second / 3600
    segundos = [(fecha - p[0]).total_seconds() for p in previas]
    compras_1min = sum(1 for s in segundos if s < 60)
    compras_1h = sum(1 for s in segundos if s < 3600)
    compras_24h = sum(1 for s in segundos if s < 86400)
    metodos_24h = len({p[2] for p, s in zip(previas, segundos) if s < 86400} | {metodo})
    horas_desde = min(segundos[0] / 3600, TOPE_HORAS) if segundos else TOPE_HORAS
    con_historial = total_previas >= HISTORIAL_MINIMO

    contexto = {"hora": hora, "valor": valor, "metodo": metodo, "firma_valida": bool(firma_valida),
                "compras_1min": compras_1min, "compras_1h": compras_1h, "compras_24h": compras_24h,
                "metodos_24h": metodos_24h, "horas_desde_anterior": horas_desde, "historial": total_previas,
                "mediana_poblacion": mediana_poblacion, "dia_semana": fecha.weekday()}
    if con_historial:
        valores = [p[1] for p in previas]
        mediana = statistics.median(valores)
        desviacion = statistics.pstdev(valores) or 1.0
        z = max(-5.0, min(10.0, (valor - statistics.fmean(valores)) / desviacion))
        proporcion = sum(1 for p in previas if p[2] == metodo) / len(previas)
        hora_habitual = _hora_media([p[0].hour + p[0].minute / 60 for p in previas])
        personales = [math.log10(max(valor, 1) / max(mediana, 1)), proporcion,
                      _distancia_horaria(hora, hora_habitual) / 12, z / 5]
        contexto.update(monto_habitual=mediana, proporcion_metodo=proporcion, hora_habitual=hora_habitual, z=z)
    else:
        personales = [0.0, 0.5, 0.5, 0.0]
        contexto.update(monto_habitual=None, proporcion_metodo=None, hora_habitual=None, z=None)

    metodo_onehot = [1.0 if metodo == m else 0.0 for m in METODOS]
    metodo_onehot.append(0.0 if metodo in METODOS else 1.0)
    x = [
        math.sin(2 * math.pi * hora / 24), math.cos(2 * math.pi * hora / 24), 1.0 if fecha.weekday() >= 5 else 0.0,
        math.log10(max(valor, 1)), math.log10(max(valor, 1) / mediana_poblacion),
        *metodo_onehot, 1.0 if firma_valida else 0.0,
        math.log1p(compras_1min), math.log1p(compras_1h), math.log1p(compras_24h), metodos_24h / 4,
        math.log10(1 + horas_desde), math.log1p(min(total_previas, 500)), 0.0 if con_historial else 1.0,
        *personales,
    ]
    return x, contexto


def desde_db(db, usuario_id, fecha, valor, metodo, firma_valida, mediana_poblacion):
    """Lo mismo, con el historial real del cliente en la base de datos."""
    filas = db.execute(
        """SELECT fecha_txn, valor, metodo_pago FROM transacciones
           WHERE usuario_id = ? AND fecha_txn < ? ORDER BY fecha_txn DESC LIMIT ?""",
        (usuario_id, a_texto(fecha), VENTANA_HISTORIA)).fetchall()
    total = db.execute("SELECT COUNT(*) FROM transacciones WHERE usuario_id = ? AND fecha_txn < ?",
                       (usuario_id, a_texto(fecha))).fetchone()[0]
    previas = [(desde_texto(f["fecha_txn"]), f["valor"], f["metodo_pago"]) for f in filas]
    return vector(fecha, valor, metodo, firma_valida, previas, total, mediana_poblacion)


# =============================================================================
#  Explicaciones para una persona
# =============================================================================

def _hhmm(hora):
    h = int(hora) % 24
    return f"{h:02d}:{int((hora - int(hora)) * 60) % 60:02d}"


def _dinero(valor):
    return f"${valor:,.0f}".replace(",", ".")


DIAS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]


def explicar(grupo, c):
    if grupo == "hora":
        return f"Operación a las {_hhmm(c['hora'])}"
    if grupo == "dia":
        return f"Es {DIAS[c['dia_semana']]}"
    if grupo == "monto":
        veces = c["valor"] / c["mediana_poblacion"]
        return f"{_dinero(c['valor'])}: {veces:.1f} veces la compra típica de cualquier cliente ({_dinero(c['mediana_poblacion'])})"
    if grupo == "metodo":
        return f"Pagó con {c['metodo']}"
    if grupo == "firma":
        return "Firma válida" if c["firma_valida"] else "La firma (hash) NO coincide con los datos"
    if grupo == "frecuencia":
        return (f"{c['compras_1min']} compras en el último minuto, {c['compras_1h']} en la última hora, "
                f"{c['metodos_24h']} métodos distintos en 24 h")
    if grupo == "recencia":
        horas = c["horas_desde_anterior"]
        if horas >= TOPE_HORAS:
            return "Sin compras anteriores (o hace más de 30 días)"
        return f"{horas * 60:.0f} minutos desde su compra anterior" if horas < 2 else f"{horas:.0f} horas desde su compra anterior"
    if grupo == "antiguedad":
        return "Cliente nuevo: sin historial" if c["historial"] < HISTORIAL_MINIMO else f"{c['historial']} compras anteriores"
    if c["monto_habitual"] is None:
        return "Sin historial personal para comparar"
    if grupo == "monto_habitual":
        return f"{c['valor'] / c['monto_habitual']:.1f} veces su compra habitual ({_dinero(c['monto_habitual'])}); z = {c['z']:.1f}"
    if grupo == "metodo_habitual":
        return f"Usa {c['metodo']} en el {c['proporcion_metodo'] * 100:.0f} % de sus compras"
    if grupo == "hora_habitual":
        return f"Suele comprar cerca de las {_hhmm(c['hora_habitual'])}"
    return grupo


def desde_resumen(r, mediana_poblacion):
    """Para el probador de la página: la persona describe la operación y el
    historial del cliente con números sueltos (en vivo se calculan con su
    historial real). El puntaje z se aproxima suponiendo que sus montos varían
    un 35 % alrededor de su mediana, que es lo típico en Capricho."""
    from datetime import datetime, timedelta

    hora, historial = r["hora"], int(r["historial"])
    fecha = datetime(2026, 11, 2) + timedelta(days=int(r["dia_semana"]), hours=hora)    # 2 nov 2026 es lunes
    con_historial = historial >= HISTORIAL_MINIMO
    contexto = {"hora": hora, "valor": r["valor"], "metodo": r["metodo"], "firma_valida": r["firma_valida"],
                "compras_1min": int(r["compras_1min"]), "compras_1h": int(r["compras_1h"]),
                "compras_24h": int(r["compras_24h"]), "metodos_24h": int(r["metodos_24h"]),
                "horas_desde_anterior": min(r["horas_desde_anterior"], TOPE_HORAS), "historial": historial,
                "mediana_poblacion": mediana_poblacion, "dia_semana": fecha.weekday(),
                "monto_habitual": None, "proporcion_metodo": None, "hora_habitual": None, "z": None}
    if con_historial:
        z = max(-5.0, min(10.0, (r["valor"] - r["monto_habitual"]) / max(0.35 * r["monto_habitual"], 1)))
        personales = [math.log10(max(r["valor"], 1) / max(r["monto_habitual"], 1)), r["proporcion_metodo"],
                      _distancia_horaria(hora, r["hora_habitual"]) / 12, z / 5]
        contexto.update(monto_habitual=r["monto_habitual"], proporcion_metodo=r["proporcion_metodo"],
                        hora_habitual=r["hora_habitual"], z=z)
    else:
        personales = [0.0, 0.5, 0.5, 0.0]
    metodo_onehot = [1.0 if r["metodo"] == m else 0.0 for m in METODOS]
    metodo_onehot.append(0.0 if r["metodo"] in METODOS else 1.0)
    x = [
        math.sin(2 * math.pi * hora / 24), math.cos(2 * math.pi * hora / 24), 1.0 if fecha.weekday() >= 5 else 0.0,
        math.log10(max(r["valor"], 1)), math.log10(max(r["valor"], 1) / mediana_poblacion),
        *metodo_onehot, 1.0 if r["firma_valida"] else 0.0,
        math.log1p(contexto["compras_1min"]), math.log1p(contexto["compras_1h"]), math.log1p(contexto["compras_24h"]),
        max(1, contexto["metodos_24h"]) / 4, math.log10(1 + contexto["horas_desde_anterior"]),
        math.log1p(min(historial, 500)), 0.0 if con_historial else 1.0, *personales,
    ]
    return x, contexto
