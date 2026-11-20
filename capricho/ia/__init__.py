"""
Inteligencia artificial de Capricho (sin LLM): redes neuronales de Keras.

    clasificador.py   red que clasifica cada operación como normal o fraudulenta
                      (aprende de TODOS los clientes: sirve también con clientes nuevos)
    monto.py          regresión del monto esperado de una compra
    modelo.py         autoencoder que mide qué tan rara es una compra para ESE cliente
    demanda.py        predicción de las ventas de los próximos días
    operaciones.py    las variables que ve el clasificador
    caracteristicas.py las variables que ve el autoencoder
    simulador.py      población simulada con fraudes etiquetados para entrenar
    inferencia.py     ejecuta las redes ya entrenadas con NumPy (rápido, en vivo)

Keras 3 corre sobre TensorFlow, JAX o PyTorch con el mismo código. Se usa
TensorFlow (Python 3.12); si no está instalado, PyTorch.
"""

import importlib.util
import os

os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "2")          # menos mensajes de TensorFlow en la consola
if "KERAS_BACKEND" not in os.environ:
    os.environ["KERAS_BACKEND"] = "tensorflow" if importlib.util.find_spec("tensorflow") else "torch"
MOTOR = os.environ["KERAS_BACKEND"]
