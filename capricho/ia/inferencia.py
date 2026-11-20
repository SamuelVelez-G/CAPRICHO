"""
Inferencia con NumPy de una red de Keras ya entrenada.

Keras sirve para construir, entrenar, guardar y cargar el modelo. Pero llamar
al modelo de Keras para UNA transacción cuesta ~1 ms (prepara tensores,
grafo, etc.), y el detector evalúa cada transacción en vivo con tres redes.
Una red densa es solo esto, capa por capa:

    salida = activación(entrada · pesos + sesgo)

así que, una vez cargado el modelo, se copian sus pesos a NumPy y se hace la
misma cuenta directamente: el resultado es idéntico (las pruebas lo
comprueban) y es decenas de veces más rápido. Es una optimización del
algoritmo crítico (ver la sección de inferencia en la página de IA).
"""

import numpy as np

ACTIVACIONES = {
    "linear": lambda x: x,
    "relu": lambda x: np.maximum(x, 0),
    "tanh": np.tanh,
    "sigmoid": lambda x: 0.5 * (1 + np.tanh(0.5 * x)),      # igual a 1/(1+e^-x), sin desbordarse
}


class RedNumpy:
    def __init__(self, modelo):
        import keras

        self.pasos = []
        for capa in modelo.layers:
            tipo = type(capa).__name__
            if tipo == "Normalization":
                # Igual que Keras: (x - media) / max(raíz(varianza), épsilon)
                media = np.asarray(keras.ops.convert_to_numpy(capa.mean), dtype="float64").reshape(-1)
                varianza = np.asarray(keras.ops.convert_to_numpy(capa.variance), dtype="float64").reshape(-1)
                self.pasos.append(("normalizar", media, np.maximum(np.sqrt(varianza), keras.config.epsilon())))
            elif tipo == "Dense":
                pesos, sesgo = (np.asarray(p, dtype="float64") for p in capa.get_weights())
                activacion = capa.get_config()["activation"]
                if activacion not in ACTIVACIONES:
                    raise ValueError(f"Activación no soportada: {activacion}")
                self.pasos.append(("densa", pesos, sesgo, ACTIVACIONES[activacion]))
            elif tipo in ("Dropout", "GaussianNoise", "InputLayer"):
                continue                         # solo actúan al entrenar
            else:
                raise ValueError(f"Capa no soportada en la inferencia rápida: {tipo}")

    def __call__(self, x):
        salida = np.atleast_2d(np.asarray(x, dtype="float64"))
        for paso in self.pasos:
            if paso[0] == "normalizar":
                salida = (salida - paso[1]) / paso[2]
            else:
                salida = paso[3](salida @ paso[1] + paso[2])
        return salida
