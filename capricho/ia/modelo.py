"""
El autoencoder de Keras.

Idea: una red que recibe los 9 números de una compra y debe devolver esos
MISMOS 9 números, pero pasando por un "cuello de botella" de solo 4 neuronas.
Para lograrlo tiene que aprender cómo son las compras normales de Capricho
(quién compra a qué hora, por cuánto, con qué método...).

    9 -> 24 -> 12 -> [4] -> 12 -> 24 -> 9
         codificador  cuello  decodificador

Con una compra normal la reconstrucción sale casi igual (error bajo). Con una
compra rara la red no sabe reconstruirla porque nunca vio algo así (error
alto). Ese error de reconstrucción es el puntaje de rareza.

Keras 3 funciona sobre varios motores. TensorFlow todavía no tiene versión
para Python 3.14, así que se usa PyTorch (KERAS_BACKEND=torch).
"""

import json
import os
from pathlib import Path

import numpy as np

os.environ.setdefault("KERAS_BACKEND", "torch")

from .caracteristicas import ETIQUETAS, GRUPOS, NOMBRES, explicar  # noqa: E402

CARPETA = Path(__file__).with_name("artefactos")
ARCHIVO_MODELO = CARPETA / "autoencoder.keras"
ARCHIVO_METADATOS = CARPETA / "metadatos.json"


def construir(n_entradas):
    import keras
    from keras import layers

    modelo = keras.Sequential([
        keras.Input(shape=(n_entradas,), name="compra"),
        layers.Dense(24, activation="relu", name="codificador_1"),
        layers.Dense(12, activation="relu", name="codificador_2"),
        layers.Dense(4, activation="tanh", name="cuello_de_botella"),
        layers.Dense(12, activation="relu", name="decodificador_1"),
        layers.Dense(24, activation="relu", name="decodificador_2"),
        layers.Dense(n_entradas, activation="linear", name="reconstruccion"),
    ], name="autoencoder_capricho")
    # Error cuadrático medio: qué tan lejos quedó la reconstrucción del original.
    modelo.compile(optimizer=keras.optimizers.Adam(learning_rate=1e-3), loss="mse")
    return modelo


class DetectorIA:
    """El modelo ya entrenado, listo para puntuar transacciones en vivo."""

    def __init__(self, carpeta=CARPETA):
        import keras

        self.metadatos = json.loads((Path(carpeta) / "metadatos.json").read_text(encoding="utf-8"))
        self.modelo = keras.saving.load_model(Path(carpeta) / "autoencoder.keras")
        self.media = np.array(self.metadatos["normalizacion"]["media"], dtype="float32")
        self.desviacion = np.sqrt(np.array(self.metadatos["normalizacion"]["varianza"], dtype="float32")) + 1e-6
        self.umbral = float(self.metadatos["umbral"])
        self._keras = keras

    def errores(self, matriz):
        """Error de reconstrucción de varias compras a la vez (para entrenar y evaluar)."""
        normalizada = (np.asarray(matriz, dtype="float32") - self.media) / self.desviacion
        reconstruida = self._keras.ops.convert_to_numpy(self.modelo(normalizada, training=False))
        return ((normalizada - reconstruida) ** 2).mean(axis=1), (normalizada - reconstruida) ** 2

    def riesgo(self, error):
        """0 a 100. Justo en el umbral vale 50; mientras más raro, más se acerca a 100."""
        return round(100 * error / (error + self.umbral), 1)

    def evaluar(self, x, contexto):
        errores, por_variable = self.errores([x])
        error = float(errores[0])
        aporte = {}
        for nombre, valor in zip(NOMBRES, por_variable[0]):
            grupo = GRUPOS[nombre]
            aporte[grupo] = aporte.get(grupo, 0.0) + float(valor)
        total = sum(aporte.values()) or 1.0
        variables = sorted(
            ({"variable": g, "nombre": ETIQUETAS[g], "aporte": round(v / total * 100, 1),
              "explicacion": explicar(g, contexto)} for g, v in aporte.items()),
            key=lambda d: -d["aporte"],
        )
        riesgo = self.riesgo(error)
        return {
            "riesgo": riesgo,
            "error": round(error, 4),
            "umbral": round(self.umbral, 4),
            "anomalia": error > self.umbral,
            "nivel": "ALTO" if riesgo >= 75 else "MEDIO" if riesgo >= 50 else None,
            "variables": variables,
        }


def cargar():
    """Devuelve el detector o None si no hay modelo entrenado o falta Keras."""
    if not ARCHIVO_MODELO.exists() or not ARCHIVO_METADATOS.exists():
        return None
    return DetectorIA()
