"""
Entrena el autoencoder de Keras que detecta compras inusuales.

    python herramientas/entrenar_ia.py

Pasos:
  1. Datos: se crea una base temporal con 9 semanas de compras de demostración
     (con la IA apagada, para no entrenarla con su propia opinión).
  2. Variables: cada compra APROBADA por las reglas se convierte en 9 números
     de comportamiento (capricho/ia/caracteristicas.py).
  3. División: 70 % entrenamiento, 15 % calibración del umbral, 15 % prueba.
  4. Entrenamiento: el autoencoder aprende a reconstruir compras normales.
  5. Umbral: el error que solo supera el 1 % de las compras normales de calibración.
  6. Evaluación: compras normales que no vio y ataques sintéticos. La columna
     de reglas ejecuta las mismas reglas transaccionales que el detector.
  7. Se guardan el modelo (.keras) y los metadatos (umbral, normalización,
     curva de aprendizaje y resultados) en capricho/ia/artefactos/.
"""

import json
import logging
import os
import random
import shutil
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

os.environ.setdefault("KERAS_BACKEND", "torch")

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import keras  # noqa: E402
import numpy as np  # noqa: E402

from capricho import create_app  # noqa: E402
from capricho.db import conectar  # noqa: E402
from capricho.ia import caracteristicas  # noqa: E402
from capricho.ia.modelo import ARCHIVO_METADATOS, ARCHIVO_MODELO, CARPETA, DetectorIA, construir  # noqa: E402
from capricho.registro import logger  # noqa: E402
from capricho.servicios import detector  # noqa: E402
from capricho.tiempo import desde_texto  # noqa: E402

SEMILLA = 42


def datos_de_entrenamiento(db):
    """Variables de cada compra normal, en orden cronológico.

    Limpieza de datos: no basta con tomar las APROBADAS. En una ráfaga de 3,
    las dos primeras pasan las reglas como aprobadas, pero eran parte del
    fraude. Si entran al entrenamiento, la red aprende que eso es normal. Por
    eso se quitan también las compras a menos de 1 minuto de una anomalía del
    mismo cliente.
    """
    filas = db.execute(
        """SELECT t.usuario_id, t.fecha_txn, t.valor, t.metodo_pago FROM transacciones t
           WHERE t.estado = 'APROBADA'
             AND NOT EXISTS (
                 SELECT 1 FROM anomalias a JOIN transacciones x ON x.id = a.transaccion_id
                 WHERE x.usuario_id = t.usuario_id
                   AND abs(julianday(x.fecha_txn) - julianday(t.fecha_txn)) * 86400 < 60)
           ORDER BY t.fecha_txn""").fetchall()
    return np.array([caracteristicas.desde_historial(db, f["usuario_id"], desde_texto(f["fecha_txn"]),
                                                     f["valor"], f["metodo_pago"])[0] for f in filas],
                    dtype="float32")


def ataques(db, rng):
    """Mezcla ataques silenciosos y casos que las reglas ya detectan.

    Se parte del historial real de un cliente y se cambia lo que haría un
    defraudador. Cada caso queda con su contexto para explicarlo.
    """
    usuarios = [f[0] for f in db.execute(
        "SELECT usuario_id FROM transacciones GROUP BY usuario_id HAVING COUNT(*) >= 15")]
    ultima = desde_texto(db.execute("SELECT MAX(fecha_txn) FROM transacciones").fetchone()[0])
    metodos = ["Tarjeta", "Nequi", "Daviplata", "PSE", "Efectivo"]
    casos = []

    def base(hora):
        usuario = rng.choice(usuarios)
        dia = (ultima + timedelta(days=rng.randint(1, 20))).replace(hour=0, minute=0, second=0, microsecond=0)
        fecha = dia + timedelta(hours=hora, minutes=rng.randrange(60))
        filas = db.execute("SELECT metodo_pago FROM transacciones WHERE usuario_id = ? AND fecha_txn < ?",
                           (usuario, fecha.isoformat(timespec="milliseconds"))).fetchall()
        usados = [f[0] for f in filas]
        raro = min(metodos, key=lambda m: usados.count(m))       # el método que menos usa
        _, contexto = caracteristicas.desde_historial(db, usuario, fecha, 10_000, raro)
        contexto["metodo"] = raro
        contexto["proporcion_metodo"] = usados[-30:].count(raro) / max(1, len(usados[-30:]))
        contexto["_usuario_id"] = usuario
        contexto["_fecha"] = fecha
        contexto["_fechas_extra"] = []
        contexto["_hash_valido"] = True
        contexto["_repetida"] = False
        return contexto

    for _ in range(60):
        # 1. Fraude silencioso: monto alto pero bajo el límite de la regla, de madrugada, método raro.
        c = base(rng.uniform(1, 4.5))
        c["valor"] = rng.randrange(150, 290) * 1000
        casos.append(("Fraude silencioso de madrugada", c))

        # 2. Cuenta tomada: otro método, lejos de su horario, monto varias veces el habitual.
        c = base(rng.choice([1, 2, 3, 23, 4]))
        c["valor"] = min(c["monto_habitual"] * rng.uniform(4, 9), 290_000)
        casos.append(("Cuenta tomada", c))

        # 3. Prueba de tarjeta: montos pequeños, varias en pocos minutos (no 3 en 3 s).
        c = base(rng.uniform(0, 24))
        c["valor"] = rng.choice([1_000, 1_500, 2_000])
        c["compras_ultima_hora"] = rng.randint(2, 4)
        cantidad = c["compras_ultima_hora"]
        c["_fechas_extra"] = [c["_fecha"] - timedelta(minutes=3 * i) for i in range(1, cantidad + 1)]
        c["horas_desde_anterior"] = (c["_fecha"] - c["_fechas_extra"][0]).total_seconds() / 3600
        casos.append(("Prueba de tarjeta", c))

        # 4. Cliente nuevo con un monto alto a deshoras.
        c = base(rng.uniform(0, 5))
        c.update({"valor": rng.randrange(180, 290) * 1000, "compras_previas": 0, "monto_habitual": 0,
                  "horas_desde_anterior": caracteristicas.TOPE_HORAS, "_usuario_id": None,
                  "_fechas_extra": []})
        casos.append(("Cliente nuevo, monto alto", c))

        # 5. Monto atípico clásico: este SÍ lo detecta la regla de $300.000.
        c = base(rng.uniform(8, 20))
        c["valor"] = rng.randrange(320, 900) * 1000
        casos.append(("Monto atípico (regla)", c))

        # 6. Ráfaga: se inyectan eventos previos por debajo de un segundo.
        c = base(rng.uniform(8, 20))
        reglas = detector.cargar_reglas(db)
        rafaga = reglas["rafaga"]
        intervalo = rafaga["ventana_segundos"] / (rafaga["maximo"] + 1)
        c["_fechas_extra"] = [c["_fecha"] - timedelta(seconds=intervalo * i)
                              for i in range(1, rafaga["maximo"])]
        c["compras_ultima_hora"] = rafaga["maximo"] - 1
        c["horas_desde_anterior"] = intervalo / 3600
        casos.append(("Ráfaga transaccional", c))

        # 7. Ventana de frecuencia de la franja activa (sin llegar a ráfaga).
        c = base(rng.uniform(8, 20))
        regla = detector.regla_aplicable(reglas, c["_fecha"])
        intervalo = regla["ventana_segundos"] / (regla["umbral"] + 1)
        c["_fechas_extra"] = [c["_fecha"] - timedelta(seconds=intervalo * i)
                              for i in range(1, regla["umbral"])]
        c["compras_ultima_hora"] = regla["umbral"] - 1
        c["horas_desde_anterior"] = intervalo / 3600
        casos.append(("Umbral de ventana", c))

        # 8. Integridad y replay: son reglas que no dependen del comportamiento.
        c = base(rng.uniform(8, 20))
        c["_hash_valido"] = False
        casos.append(("Firma inválida", c))
        c = base(rng.uniform(8, 20))
        c["_repetida"] = True
        casos.append(("ID de transacción repetido", c))

        # 9. La tienda también detecta discrepancias de precio antes de crear el pedido.
        c = base(rng.uniform(8, 20))
        c["_precio_manipulado"] = True
        casos.append(("Precio manipulado en tienda", c))

    for _, c in casos:
        if not c["monto_habitual"]:
            c["monto_habitual"] = c["valor"]
    return casos


def main():
    rng = random.Random(SEMILLA)
    keras.utils.set_random_seed(SEMILLA)
    logger.setLevel(logging.ERROR)
    temporal = Path(tempfile.mkdtemp(prefix="capricho_ia_"))
    print("1/6  Generando 9 semanas de compras de demostración...")
    # Histórico revisado: sin los fraudes silenciosos que siembra la demo. Si
    # entraran, la red los aprendería como normales (se comprobó: con ellos
    # solo detectaba 2 de 60).
    app = create_app({"BASE_DATOS": str(temporal / "datos.db"), "CARPETA_LOGS": str(temporal / "logs"),
                      "IA_ACTIVA": False, "SEMBRAR_FRAUDES_SILENCIOSOS": False})
    db = conectar(app.config["BASE_DATOS"])

    print("2/6  Calculando las variables de comportamiento...")
    X = datos_de_entrenamiento(db)
    indices = np.random.default_rng(SEMILLA).permutation(len(X))
    n_entreno, n_calibracion = int(len(X) * 0.70), int(len(X) * 0.15)
    entreno = X[indices[:n_entreno]]
    calibracion = X[indices[n_entreno:n_entreno + n_calibracion]]
    prueba = X[indices[n_entreno + n_calibracion:]]

    # Normalización: cada variable queda con media 0 y desviación 1, para
    # que el monto (≈4) no pese más que una proporción (0 a 1).
    normalizacion = keras.layers.Normalization()
    normalizacion.adapt(entreno)
    media = keras.ops.convert_to_numpy(normalizacion.mean).reshape(-1)
    varianza = keras.ops.convert_to_numpy(normalizacion.variance).reshape(-1)
    entreno_n = keras.ops.convert_to_numpy(normalizacion(entreno))

    print(f"3/6  Entrenando el autoencoder con {len(entreno)} compras normales...")
    modelo = construir(X.shape[1])
    historia = modelo.fit(
        entreno_n, entreno_n,            # entrada y salida esperada son la MISMA compra
        epochs=400, batch_size=32, validation_split=0.15, shuffle=True, verbose=0,
        callbacks=[keras.callbacks.EarlyStopping(monitor="val_loss", patience=30, restore_best_weights=True)],
    )
    print(f"     {len(historia.history['loss'])} épocas · pérdida final {historia.history['loss'][-1]:.4f}"
          f" · validación {historia.history['val_loss'][-1]:.4f}")

    CARPETA.mkdir(exist_ok=True)
    modelo.save(ARCHIVO_MODELO)
    metadatos = {
        "creado": datetime.now().isoformat(timespec="seconds"),
        "variables": caracteristicas.NOMBRES,
        "normalizacion": {"media": media.tolist(), "varianza": varianza.tolist()},
        "umbral": 1.0,
        "arquitectura": [{"capa": c.name, "neuronas": c.units, "activacion": c.activation.__name__}
                         for c in modelo.layers],
        "parametros": int(modelo.count_params()),
        "datos": {"total": int(len(X)), "entrenamiento": int(len(entreno)),
                  "calibracion": int(len(calibracion)), "prueba": int(len(prueba))},
        "historia": {"perdida": [round(float(v), 5) for v in historia.history["loss"]],
                     "validacion": [round(float(v), 5) for v in historia.history["val_loss"]]},
        "versiones": {"keras": keras.__version__, "motor": keras.backend.backend()},
    }
    ARCHIVO_METADATOS.write_text(json.dumps(metadatos, ensure_ascii=False, indent=1), encoding="utf-8")

    print("4/6  Calculando el umbral con compras que el modelo no vio...")
    ia_detector = DetectorIA()
    errores_calibracion, _ = ia_detector.errores(calibracion)
    umbral = float(np.percentile(errores_calibracion, 99))
    ia_detector.umbral = umbral

    print("5/6  Evaluando: compras normales nuevas y ataques que construimos...")
    errores_prueba, _ = ia_detector.errores(prueba)
    falsos_positivos = int((errores_prueba > umbral).sum())
    casos = ataques(db, rng)
    por_tipo = {}
    errores_ataque = []
    ejemplos = []
    for tipo, contexto in casos:
        resultado = ia_detector.evaluar(caracteristicas.desde_contexto(contexto), contexto)
        errores_ataque.append(resultado["error"])
        reglas_activas = detector.cargar_reglas(db)
        usuario_id = contexto.get("_usuario_id")
        fecha = contexto["_fecha"]
        fechas_extra = contexto.get("_fechas_extra", [])
        reglas_txn = detector.evaluar_reglas_transaccion(
            reglas_activas, fecha, contexto["valor"],
            lambda ventana: detector.contar_en_ventana_con_fechas(
                db, usuario_id, fecha, ventana, fechas_extra),
            hash_valido=contexto.get("_hash_valido", True),
            repetida=contexto.get("_repetida", False),
        )
        tipos_reglas = list(reglas_txn["tipos"])
        if contexto.get("_precio_manipulado"):
            tipos_reglas.append("PRECIO_MANIPULADO")
        regla = bool(tipos_reglas)
        fila = por_tipo.setdefault(tipo, {"tipo": tipo, "casos": 0, "ia": 0, "reglas": 0,
                                          "combinado": 0, "reglas_motivos": []})
        fila["casos"] += 1
        fila["ia"] += int(resultado["anomalia"])
        fila["reglas"] += int(regla)
        fila["combinado"] += int(resultado["anomalia"] or regla)
        for motivo in tipos_reglas:
            if motivo not in fila["reglas_motivos"]:
                fila["reglas_motivos"].append(motivo)
        if len([e for e in ejemplos if e["tipo"] == tipo]) < 1:
            ejemplos.append({"tipo": tipo, "riesgo": resultado["riesgo"],
                             "explicacion": [v["explicacion"] for v in resultado["variables"][:3]]})

    # Histograma del error (escala logarítmica) para comparar normales y ataques.
    todos = np.concatenate([errores_prueba, np.array(errores_ataque)])
    bordes = np.logspace(np.log10(max(todos.min(), 1e-4)), np.log10(todos.max() * 1.01), 25)
    metadatos.update({
        "umbral": umbral,
        "percentil_umbral": 99,
        "evaluacion": {
            "normales_prueba": int(len(prueba)),
            "falsos_positivos": falsos_positivos,
            "tasa_falsos_positivos": round(falsos_positivos / len(prueba) * 100, 2),
            "por_tipo": list(por_tipo.values()),
            "ataques": len(casos),
            "detectados_ia": sum(t["ia"] for t in por_tipo.values()),
            "detectados_reglas": sum(t["reglas"] for t in por_tipo.values()),
            "detectados_combinado": sum(t["combinado"] for t in por_tipo.values()),
            "ejemplos": ejemplos,
        },
        "histograma": {
            "bordes": [round(float(b), 5) for b in bordes],
            "normales": np.histogram(errores_prueba, bordes)[0].tolist(),
            "ataques": np.histogram(errores_ataque, bordes)[0].tolist(),
        },
    })
    ARCHIVO_METADATOS.write_text(json.dumps(metadatos, ensure_ascii=False, indent=1), encoding="utf-8")

    e = metadatos["evaluacion"]
    print(f"6/6  Listo. Umbral (percentil 99) = {umbral:.4f}")
    print(f"     Falsos positivos en compras normales nuevas: {falsos_positivos}/{len(prueba)}"
          f" ({e['tasa_falsos_positivos']} %)")
    for fila in por_tipo.values():
        print(f"     {fila['tipo']:<32} IA {fila['ia']:>3}/{fila['casos']}   reglas {fila['reglas']:>3}/{fila['casos']}")
    print(f"     Modelo guardado en {ARCHIVO_MODELO}")
    db.close()
    shutil.rmtree(temporal, ignore_errors=True)


if __name__ == "__main__":
    main()
