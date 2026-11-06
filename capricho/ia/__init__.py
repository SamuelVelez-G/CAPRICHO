"""
Detección de fraude con IA (Keras): un autoencoder que aprende cómo son las
compras normales y marca las que no se parecen, aunque no rompan ninguna regla.

    caracteristicas.py  convierte cada compra en 9 números de comportamiento
    modelo.py           el autoencoder: construirlo, cargarlo y puntuar
    herramientas/entrenar_ia.py  entrena, evalúa y guarda el modelo en artefactos/

Si Keras no está instalado o no hay modelo entrenado, la aplicación sigue
funcionando solo con las reglas.
"""
