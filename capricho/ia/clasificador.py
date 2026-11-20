"""
Clasificador de operaciones con Keras: ¿normal o fraudulenta?

    23 variables -> Normalización -> Dense 64 (ReLU) -> Dropout 20 %
                 -> Dense 32 (ReLU) -> Dropout 10 % -> Dense 1 (sigmoide)

La salida es la probabilidad de fraude (0 a 1). Es aprendizaje SUPERVISADO:
se entrena con operaciones etiquetadas (ia/simulador.py) y aprende de toda
la población, no de un solo cliente.

Explicación de cada decisión:
  a cada grupo de variables se le pone el valor típico de una compra normal y
  se mide cuánto cambia la decisión, en log-odds (log(p / (1 - p))): así se
  nota el efecto aunque la probabilidad esté pegada a 0 o a 1. Si quitar el
  grupo baja la probabilidad, ese grupo empujaba hacia FRAUDE; si la sube,
  empujaba hacia NORMAL. Sumando el peso de las variables generales y el de
  las personales se sabe cuánto conocimiento GENERAL (de todos los clientes)
  y cuánto PERSONAL (del historial de ese cliente) usó la red. Con un cliente
  nuevo es 100 % general.
"""

import json
from pathlib import Path

import numpy as np

from . import operaciones
from .inferencia import RedNumpy

CARPETA = Path(__file__).with_name("artefactos")
ARCHIVO_MODELO = CARPETA / "clasificador.keras"
ARCHIVO_METADATOS = CARPETA / "clasificador.json"


def construir(normalizacion):
    """normalizacion: capa keras.layers.Normalization ya adaptada a los datos de entrenamiento."""
    import keras
    from keras import layers

    modelo = keras.Sequential([
        keras.Input(shape=(len(operaciones.NOMBRES),), name="operacion"),
        normalizacion,
        layers.Dense(64, activation="relu", name="oculta_1"),
        layers.Dropout(0.2, name="apagado_1"),
        layers.Dense(32, activation="relu", name="oculta_2"),
        layers.Dropout(0.1, name="apagado_2"),
        layers.Dense(1, activation="sigmoid", name="probabilidad_fraude"),
    ], name="clasificador_capricho")
    modelo.compile(
        optimizer=keras.optimizers.Adam(learning_rate=1e-3),
        loss="binary_crossentropy",
        metrics=[keras.metrics.AUC(curve="PR", name="auc_pr"), keras.metrics.Precision(name="precision"),
                 keras.metrics.Recall(name="recall")],
    )
    return modelo


class ClasificadorIA:
    def __init__(self, carpeta=CARPETA):
        import keras

        carpeta = Path(carpeta)
        self.metadatos = json.loads((carpeta / ARCHIVO_METADATOS.name).read_text(encoding="utf-8"))
        self.modelo = keras.saving.load_model(carpeta / ARCHIVO_MODELO.name)
        self.red = RedNumpy(self.modelo)
        self.umbral = float(self.metadatos["umbral"])
        self.referencia = np.array(self.metadatos["referencia"], dtype="float64")
        self.mediana_poblacion = float(self.metadatos["mediana_poblacion"])

    def probabilidades(self, matriz):
        return self.red(matriz)[:, 0]

    def evaluar(self, x, contexto):
        x = np.asarray(x, dtype="float64")
        nuevo = contexto["historial"] < operaciones.HISTORIAL_MINIMO
        grupos = list(operaciones.GRUPOS)
        # Fila 0: la operación tal cual. Filas 1..: un grupo reemplazado por su valor típico.
        lote = np.repeat(x[None, :], len(grupos) + 1, axis=0)
        for fila, grupo in enumerate(grupos, start=1):
            indices = operaciones.GRUPOS[grupo]
            lote[fila, indices] = self.referencia[indices]
        salida = self.probabilidades(lote)
        probabilidad = float(salida[0])
        logit = np.log(np.clip(salida, 1e-9, 1 - 1e-9) / np.clip(1 - salida, 1e-9, 1))

        cambios = {}
        for fila, grupo in enumerate(grupos, start=1):
            personal = grupo in operaciones.PERSONALES
            cambios[grupo] = 0.0 if (personal and nuevo) else float(logit[0] - logit[fila])
        suma = sum(abs(v) for v in cambios.values()) or 1.0
        factores = []
        for grupo, cambio in cambios.items():
            factores.append({"grupo": grupo, "nombre": operaciones.ETIQUETAS[grupo],
                             "aporte": round(100 * cambio / suma, 1),      # % del peso total, con signo
                             "direccion": "fraude" if cambio > 0 else "normal",
                             "tipo": "personal" if grupo in operaciones.PERSONALES else "general",
                             "explicacion": operaciones.explicar(grupo, contexto)})
        # Primero lo que empujó hacia la decisión que se tomó.
        fraudulenta = probabilidad >= self.umbral
        factores.sort(key=lambda f: -f["aporte"] if fraudulenta else f["aporte"])
        general = sum(abs(f["aporte"]) for f in factores if f["tipo"] == "general")
        personal = sum(abs(f["aporte"]) for f in factores if f["tipo"] == "personal")
        total = (general + personal) or 1.0
        return {
            "probabilidad": round(probabilidad, 4), "porcentaje": round(probabilidad * 100, 1),
            "umbral": round(self.umbral, 4), "fraudulenta": fraudulenta,
            "clasificacion": "FRAUDULENTA" if fraudulenta else "NORMAL",
            "nivel": ("ALTO" if probabilidad >= 0.9 else "MEDIO") if fraudulenta else None,
            "segmento": "cliente nuevo" if nuevo else f"cliente con {contexto['historial']} compras",
            "conocimiento": {"general": round(100 * general / total, 1), "personal": round(100 * personal / total, 1)},
            "factores": factores,
        }


def cargar():
    if not ARCHIVO_MODELO.exists() or not ARCHIVO_METADATOS.exists():
        return None
    return ClasificadorIA()
