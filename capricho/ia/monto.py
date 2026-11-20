"""
Regresión del MONTO ESPERADO con Keras.

¿Cuánto debería pagar normalmente este cliente, a esta hora, este día y con
este método? La red aprende de las compras legítimas de toda la población:

    13 variables -> Normalización -> Dense 32 (ReLU) -> Dense 16 (ReLU) -> Dense 1 (lineal)

Predice log10(monto) con pérdida de error absoluto; en vivo se compara el monto real con el esperado:
"esta compra es 18 veces lo esperado". Se mide contra el método simple de
usar la mediana del cliente (o de la población si es nuevo).
"""

import json
import math
from pathlib import Path

from .inferencia import RedNumpy
from .operaciones import HISTORIAL_MINIMO, METODOS

CARPETA = Path(__file__).with_name("artefactos")
ARCHIVO_MODELO = CARPETA / "monto.keras"
ARCHIVO_METADATOS = CARPETA / "monto.json"
NOMBRES = ["hora_seno", "hora_coseno", "fin_de_semana", *[f"metodo_{m.lower()}" for m in METODOS], "metodo_otro",
           "historial", "es_nuevo", "mediana_cliente", "compras_24h"]


def vector(contexto):
    """Todo lo que se sabe ANTES de ver el monto de la compra."""
    hora = contexto["hora"]
    nuevo = contexto["historial"] < HISTORIAL_MINIMO
    referencia = contexto["mediana_poblacion"] if nuevo or not contexto.get("monto_habitual") else contexto["monto_habitual"]
    metodo = [1.0 if contexto["metodo"] == m else 0.0 for m in METODOS]
    metodo.append(0.0 if contexto["metodo"] in METODOS else 1.0)
    return [math.sin(2 * math.pi * hora / 24), math.cos(2 * math.pi * hora / 24),
            1.0 if contexto["dia_semana"] >= 5 else 0.0, *metodo, math.log1p(min(contexto["historial"], 500)),
            1.0 if nuevo else 0.0, math.log10(max(referencia, 1)), math.log1p(contexto["compras_24h"])]


def construir(normalizacion):
    import keras
    from keras import layers

    modelo = keras.Sequential([
        keras.Input(shape=(len(NOMBRES),), name="contexto"), normalizacion,
        layers.Dense(32, activation="relu", name="oculta_1"),
        layers.Dense(16, activation="relu", name="oculta_2"),
        layers.Dense(1, activation="linear", name="log_monto"),
    ], name="monto_esperado")
    # Error absoluto: la red aprende la MEDIANA del monto según el contexto (no la
    # media), que es lo que se compara con la mediana del cliente.
    modelo.compile(optimizer=keras.optimizers.Adam(learning_rate=1e-3), loss="mae")
    return modelo


class MontoIA:
    def __init__(self, carpeta=CARPETA):
        import keras

        carpeta = Path(carpeta)
        self.metadatos = json.loads((carpeta / ARCHIVO_METADATOS.name).read_text(encoding="utf-8"))
        self.red = RedNumpy(keras.saving.load_model(carpeta / ARCHIVO_MODELO.name))

    def esperado(self, contexto):
        return 10 ** min(8.0, max(2.0, float(self.red([vector(contexto)])[0, 0])))

    def evaluar(self, contexto):
        esperado = self.esperado(contexto)
        razon = contexto["valor"] / esperado
        return {"esperado": round(esperado, -2), "razon": round(razon, 2),
                "lectura": (f"Lo esperado era cerca de ${esperado:,.0f}; esta operación es "
                            f"{razon:.1f} veces eso").replace(",", ".")}


def cargar():
    if not ARCHIVO_MODELO.exists() or not ARCHIVO_METADATOS.exists():
        return None
    return MontoIA()
