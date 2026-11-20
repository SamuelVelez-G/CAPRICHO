"""
Predicción de la demanda (ventas por día) con Keras.

Para predecir las ventas de un día, la red mira:
    el día de la semana (7 variables: los sábados se vende más),
    lo que se vendió ayer, lo que se vendió el mismo día de la semana pasada
    y el promedio de los últimos 7 días.
Todo se divide por la escala del negocio (el promedio de las últimas 4
semanas), así el modelo sirve aunque Capricho venda más o menos.

    10 variables -> Normalización -> Dense 16 (ReLU) -> Dense 8 (ReLU) -> Dense 1

Para varios días se predice uno, se agrega a la historia y se predice el
siguiente (pronóstico recursivo). Se compara con la regresión lineal simple
y con "lo mismo que el mismo día de la semana pasada".
"""

import json
from datetime import date, timedelta
from pathlib import Path

from .inferencia import RedNumpy

CARPETA = Path(__file__).with_name("artefactos")
ARCHIVO_MODELO = CARPETA / "demanda.keras"
ARCHIVO_METADATOS = CARPETA / "demanda.json"
NOMBRES = ["lunes", "martes", "miercoles", "jueves", "viernes", "sabado", "domingo", "ayer", "semana_pasada",
           "promedio_7"]


def escala(ventas):
    recientes = [v for v in ventas[-28:] if v > 0]
    return (sum(recientes) / len(recientes)) if recientes else 1.0


def vector(dia: date, historia, base):
    """historia: ventas de los días anteriores (la última es ayer); mínimo 7 días."""
    semana = [1.0 if dia.weekday() == i else 0.0 for i in range(7)]
    return [*semana, historia[-1] / base, historia[-7] / base, sum(historia[-7:]) / 7 / base]


def construir(normalizacion):
    import keras
    from keras import layers

    modelo = keras.Sequential([
        keras.Input(shape=(len(NOMBRES),), name="dia"), normalizacion,
        layers.Dense(16, activation="relu", name="oculta_1"),
        layers.Dense(8, activation="relu", name="oculta_2"),
        layers.Dense(1, activation="linear", name="ventas_relativas"),
    ], name="demanda_capricho")
    modelo.compile(optimizer=keras.optimizers.Adam(learning_rate=3e-3), loss="mse", metrics=["mae"])
    return modelo


class DemandaIA:
    def __init__(self, carpeta=CARPETA):
        import keras

        carpeta = Path(carpeta)
        self.metadatos = json.loads((carpeta / ARCHIVO_METADATOS.name).read_text(encoding="utf-8"))
        self.red = RedNumpy(keras.saving.load_model(carpeta / ARCHIVO_MODELO.name))

    def pronosticar(self, serie, horizonte=7):
        """serie: [{"dia", "ventas"}] de días COMPLETOS, en orden. Devuelve los próximos `horizonte` días."""
        historia = [float(d["ventas"]) for d in serie]
        if len(historia) < 7:
            return []
        base = escala(historia)
        ultimo = date.fromisoformat(serie[-1]["dia"])
        prediccion = []
        for i in range(1, horizonte + 1):
            dia = ultimo + timedelta(days=i)
            valor = max(0.0, float(self.red([vector(dia, historia, base)])[0, 0]) * base)
            historia.append(valor)
            prediccion.append({"dia": dia.isoformat(), "ventas": round(valor)})
        return prediccion


def cargar():
    if not ARCHIVO_MODELO.exists() or not ARCHIVO_METADATOS.exists():
        return None
    return DemandaIA()
