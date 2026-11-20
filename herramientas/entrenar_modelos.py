"""
Entrena los modelos de IA de la entrega final (TensorFlow + Keras).

    python herramientas/entrenar_modelos.py          clasificador, monto esperado y demanda (~3 min)
    python herramientas/entrenar_modelos.py --todo   además vuelve a entrenar el autoencoder

1. CLASIFICADOR (normal o fraudulenta)
   - Datos: 90 días de una población simulada de 800 clientes con 7 tipos de
     fraude etiquetados (capricho/ia/simulador.py).
   - División TEMPORAL: días 0-62 entrenamiento, 63-75 validación, 76-89
     prueba. Así se evalúa como en la realidad: con el futuro que no vio.
   - Preparación con TensorFlow: keras.layers.Normalization (media 0,
     desviación 1) y tf.data para mezclar y AUMENTAR los fraudes (son
     pocos): se repiten con ruido gaussiano en las variables continuas.
   - Se entrena dos veces, sin y con aumento de datos, para medir su efecto.
   - Umbral: el que da el mejor F1 en validación.
   - Se compara en PRUEBA contra las reglas de la primera entrega y contra el
     autoencoder, para todos y para los clientes nuevos.
2. MONTO ESPERADO (regresión): compras legítimas, error contra la mediana del cliente.
3. DEMANDA: 26 semanas de ventas de una base de demostración; se compara con
   la regresión lineal simple y con "lo mismo que la semana pasada".
Todo se guarda (.keras + .json) en capricho/ia/artefactos/ y la aplicación
lo carga al arrancar.
"""

import json
import logging
import math
import shutil
import statistics
import sys
import tempfile
import time
from datetime import date, datetime
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import capricho.ia  # noqa: E402  (elige el motor: TensorFlow)

try:
    import tensorflow as tf  # noqa: E402
except ImportError:
    sys.exit("Este script necesita TensorFlow (Python 3.10 a 3.13): pip install -r requirements.txt")

import keras  # noqa: E402
import numpy as np  # noqa: E402

from capricho import create_app  # noqa: E402
from capricho.db import conectar  # noqa: E402
from capricho.ia import clasificador, demanda, monto, operaciones, simulador  # noqa: E402
from capricho.ia.inferencia import RedNumpy  # noqa: E402
from capricho.ia.modelo import DetectorIA, ARCHIVO_MODELO as ARCHIVO_AUTOENCODER  # noqa: E402
from capricho.registro import logger  # noqa: E402
from capricho.servicios import ventas  # noqa: E402
from capricho.servicios.estadistica import regresion_lineal  # noqa: E402

SEMILLA = 42
INICIO = datetime(2026, 7, 1)
DIAS = 90
CORTE_VALIDACION, CORTE_PRUEBA = 63, 76
BINARIAS = [i for i, n in enumerate(operaciones.NOMBRES) if n.startswith("metodo_") and n != "metodo_habitual"] + [
    operaciones.NOMBRES.index(n) for n in ("fin_de_semana", "firma_valida", "es_nuevo")]
CARPETA = clasificador.CARPETA


# =============================================================================
#  Métricas (escritas a mano para poder explicarlas)
# =============================================================================

def metricas(y, p, umbral):
    y = np.asarray(y, dtype=bool)
    pred = np.asarray(p) >= umbral
    vp, fp = int((pred & y).sum()), int((pred & ~y).sum())
    fn, vn = int((~pred & y).sum()), int((~pred & ~y).sum())
    precision = vp / (vp + fp) if vp + fp else 0.0
    recall = vp / (vp + fn) if vp + fn else 0.0
    return {"exactitud": round((vp + vn) / max(len(y), 1), 4), "precision": round(precision, 4),
            "recall": round(recall, 4), "f1": round(2 * precision * recall / (precision + recall), 4) if precision + recall else 0.0,
            "falsas_alarmas": round(fp / (fp + vn), 4) if fp + vn else 0.0,
            "matriz": {"verdaderos_positivos": vp, "falsos_positivos": fp, "falsos_negativos": fn, "verdaderos_negativos": vn}}


def auc_roc(y, p):
    """Probabilidad de que un fraude al azar tenga más puntaje que una compra normal al azar."""
    y = np.asarray(y, dtype=bool)
    orden = np.argsort(p)
    rangos = np.empty(len(p))
    rangos[orden] = np.arange(1, len(p) + 1)
    positivos, negativos = y.sum(), (~y).sum()
    return float((rangos[y].sum() - positivos * (positivos + 1) / 2) / (positivos * negativos))


def auc_pr(y, p):
    """Precisión promedio: el área bajo la curva precisión-recall."""
    y = np.asarray(y, dtype=bool)
    orden = np.argsort(-np.asarray(p))
    aciertos = np.cumsum(y[orden])
    precision = aciertos / np.arange(1, len(y) + 1)
    return float((precision * y[orden]).sum() / max(y.sum(), 1))


def mejor_umbral(y, p):
    candidatos = np.unique(np.quantile(p, np.linspace(0.5, 0.995, 200)))
    return float(max(candidatos, key=lambda u: metricas(y, p, u)["f1"]))


def curva_pr(y, p, puntos=40):
    resultado = []
    for umbral in np.quantile(p, np.linspace(0.6, 0.999, puntos)):
        m = metricas(y, p, umbral)
        resultado.append({"umbral": round(float(umbral), 4), "precision": m["precision"], "recall": m["recall"]})
    return resultado


# =============================================================================
#  1. Clasificador
# =============================================================================

def conjunto_aumentado(x, y, desviacion):
    """tf.data: mezcla 75 % compras normales y 25 % fraudes. Los fraudes se
    repiten con ruido gaussiano (8 % de la desviación de cada variable
    continua; las variables de 0/1 no se tocan): es el AUMENTO DE DATOS."""
    escala = tf.constant(desviacion * 0.08, dtype=tf.float32)
    mascara = np.ones(x.shape[1], dtype="float32")
    mascara[BINARIAS] = 0
    escala = escala * mascara

    def ruido(fila, etiqueta):
        return fila + tf.random.normal(tf.shape(fila), seed=SEMILLA) * escala, etiqueta

    normales = tf.data.Dataset.from_tensor_slices((x[y == 0], y[y == 0])).shuffle(20_000, seed=SEMILLA).repeat()
    fraudes = (tf.data.Dataset.from_tensor_slices((x[y == 1], y[y == 1])).shuffle(5_000, seed=SEMILLA).repeat()
               .map(ruido, num_parallel_calls=tf.data.AUTOTUNE))
    mezcla = tf.data.Dataset.sample_from_datasets([normales, fraudes], weights=[0.75, 0.25], seed=SEMILLA)
    return mezcla.batch(256).prefetch(tf.data.AUTOTUNE)


def entrenar_clasificador(x_tr, y_tr, x_va, y_va, aumento):
    keras.utils.set_random_seed(SEMILLA)
    normalizacion = keras.layers.Normalization(name="normalizacion")
    normalizacion.adapt(x_tr)
    modelo = clasificador.construir(normalizacion)
    parada = keras.callbacks.EarlyStopping(monitor="val_auc_pr", mode="max", patience=8, restore_best_weights=True)
    if aumento:
        historia = modelo.fit(conjunto_aumentado(x_tr, y_tr, x_tr.std(axis=0)), steps_per_epoch=math.ceil(len(x_tr) / 256),
                              epochs=80, validation_data=(x_va, y_va), callbacks=[parada], verbose=0)
    else:
        peso = float((y_tr == 0).sum() / max((y_tr == 1).sum(), 1))
        historia = modelo.fit(x_tr, y_tr, batch_size=256, epochs=80, validation_data=(x_va, y_va),
                              class_weight={0: 1.0, 1: peso}, callbacks=[parada], verbose=0)
    return modelo, historia.history


def evaluar_grupo(filas, puntajes, umbral):
    y = [f["fraude"] for f in filas]
    if not filas:
        return None
    m = metricas(y, puntajes, umbral)
    return {"operaciones": len(filas), "fraudes": int(sum(y)), **{k: m[k] for k in ("precision", "recall", "f1", "falsas_alarmas")}}


def clasificador_paso():
    print("1/4  Simulando 90 días de una población de 800 clientes con 7 tipos de fraude...")
    eventos = simulador.generar(SEMILLA, 800, DIAS, INICIO)
    entrenamiento = [e for e in eventos if (e["fecha"] - INICIO).days < CORTE_VALIDACION]
    mediana_poblacion = statistics.median(e["valor"] for e in entrenamiento if not e["fraude"])
    filas = simulador.variables(eventos, mediana_poblacion)
    for f in filas:
        f["dia"] = (f["fecha"] - INICIO).days
    tr = [f for f in filas if f["dia"] < CORTE_VALIDACION]
    va = [f for f in filas if CORTE_VALIDACION <= f["dia"] < CORTE_PRUEBA]
    pr = [f for f in filas if f["dia"] >= CORTE_PRUEBA]
    x = lambda conjunto: np.array([f["x"] for f in conjunto], dtype="float32")  # noqa: E731
    y = lambda conjunto: np.array([f["fraude"] for f in conjunto], dtype="float32")  # noqa: E731
    x_tr, y_tr, x_va, y_va, x_pr, y_pr = x(tr), y(tr), x(va), y(va), x(pr), y(pr)
    print(f"     {len(filas)} operaciones ({int(y(filas).sum())} fraudes): entrenamiento {len(tr)}, "
          f"validación {len(va)}, prueba {len(pr)}")

    print("2/4  Entrenando el clasificador sin y con aumento de datos (TensorFlow)...")
    resultados = {}
    modelos = {}
    for nombre, aumento in (("sin_aumento", False), ("con_aumento", True)):
        inicio = time.perf_counter()
        modelo, historia = entrenar_clasificador(x_tr, y_tr, x_va, y_va, aumento)
        p_va = modelo.predict(x_va, verbose=0)[:, 0]
        umbral = mejor_umbral(y_va, p_va)
        p_pr = modelo.predict(x_pr, verbose=0)[:, 0]
        resultados[nombre] = {"umbral": umbral, "prueba": metricas(y_pr, p_pr, umbral), "auc_roc": round(auc_roc(y_pr, p_pr), 4),
                              "auc_pr": round(auc_pr(y_pr, p_pr), 4), "epocas": len(historia["loss"]),
                              "segundos": round(time.perf_counter() - inicio, 1)}
        modelos[nombre] = (modelo, historia, p_pr, umbral)
        r = resultados[nombre]
        print(f"     {nombre}: F1 {r['prueba']['f1']:.3f} · precisión {r['prueba']['precision']:.3f} · "
              f"recall {r['prueba']['recall']:.3f} · AUC-PR {r['auc_pr']:.3f} · {r['epocas']} épocas")

    modelo, historia, p_pr, umbral = modelos["con_aumento"]
    # Guardar y volver a cargar: se evalúa el modelo tal como lo usa la aplicación.
    CARPETA.mkdir(exist_ok=True)
    modelo.save(clasificador.ARCHIVO_MODELO)
    cargado = keras.saving.load_model(clasificador.ARCHIVO_MODELO)
    red = RedNumpy(cargado)
    diferencia = float(np.abs(red(x_pr)[:, 0] - cargado.predict(x_pr, verbose=0)[:, 0]).max())

    # Línea base: reglas de la primera entrega y autoencoder (si está entrenado).
    reglas = np.array([1.0 if f["reglas"] else 0.0 for f in pr])
    detectores = {"clasificador": (p_pr, umbral), "reglas": (reglas, 0.5)}
    if ARCHIVO_AUTOENCODER.exists():
        autoencoder = DetectorIA()
        errores, _ = autoencoder.errores(np.array([f["x_autoencoder"] for f in pr], dtype="float32"))
        detectores["autoencoder"] = (errores, autoencoder.umbral)
    detectores["reglas_y_clasificador"] = (np.maximum(reglas, (p_pr >= umbral).astype(float)), 0.5)

    comparacion = {}
    for nombre, (puntajes, corte) in detectores.items():
        comparacion[nombre] = {
            "todos": evaluar_grupo(pr, puntajes, corte),
            "clientes_nuevos": evaluar_grupo([f for f in pr if f["nuevo"]], puntajes[[f["nuevo"] for f in pr]], corte),
            "con_historial": evaluar_grupo([f for f in pr if not f["nuevo"]], puntajes[[not f["nuevo"] for f in pr]], corte),
        }
    por_tipo = {}
    for tipo in {**simulador.TIPOS_FRAUDE, **simulador.TIPOS_LEGITIMOS}:
        indices = [i for i, f in enumerate(pr) if f["tipo"] == tipo]
        if not indices:
            continue
        fraude = tipo in simulador.TIPOS_FRAUDE
        fila = {"operaciones": len(indices), "fraude": fraude,
                "descripcion": simulador.TIPOS_FRAUDE.get(tipo) or simulador.TIPOS_LEGITIMOS[tipo]}
        for nombre, (puntajes, corte) in detectores.items():
            marcadas = sum(1 for i in indices if puntajes[i] >= corte)
            fila[nombre] = round(marcadas / len(indices), 4)        # recall si es fraude; falsas alarmas si no
        por_tipo[tipo] = fila

    normales_tr = x_tr[y_tr == 0]
    p_todos = cargado.predict(x_pr, verbose=0)[:, 0]
    histograma = np.linspace(0, 1, 21)
    metadatos = {
        "creado": datetime.now().isoformat(timespec="seconds"), "motor": keras.backend.backend(),
        "versiones": {"tensorflow": tf.__version__, "keras": keras.__version__},
        "variables": operaciones.NOMBRES, "grupos": operaciones.GRUPOS, "personales": list(operaciones.PERSONALES),
        "arquitectura": [{"capa": c.name, "tipo": type(c).__name__, "unidades": c.get_config().get("units"),
                          "activacion": c.get_config().get("activation"), "tasa": c.get_config().get("rate")}
                         for c in cargado.layers],
        "parametros": int(cargado.count_params()), "umbral": umbral, "mediana_poblacion": mediana_poblacion,
        "referencia": np.median(normales_tr, axis=0).tolist(),
        "datos": {"total": len(filas), "fraudes": int(y(filas).sum()), "entrenamiento": len(tr), "validacion": len(va),
                  "prueba": len(pr), "clientes": 800, "dias": DIAS,
                  "division": f"días 0-{CORTE_VALIDACION - 1} entrenamiento, {CORTE_VALIDACION}-{CORTE_PRUEBA - 1} validación, {CORTE_PRUEBA}-{DIAS - 1} prueba"},
        "historia": {k: [round(float(v), 4) for v in historia[k]] for k in ("loss", "val_loss", "auc_pr", "val_auc_pr")},
        "aumento": resultados, "prueba": resultados["con_aumento"]["prueba"],
        "auc_roc": resultados["con_aumento"]["auc_roc"], "auc_pr": resultados["con_aumento"]["auc_pr"],
        "comparacion": comparacion, "por_tipo": por_tipo, "curva_pr": curva_pr(y_pr, p_todos),
        "histograma": {"bordes": histograma.tolist(),
                       "normales": np.histogram(p_todos[y_pr == 0], histograma)[0].tolist(),
                       "fraudes": np.histogram(p_todos[y_pr == 1], histograma)[0].tolist()},
        "verificacion_numpy": diferencia,
        "inferencia": medir_inferencia(cargado, red, x_pr[:1]),
        "ejemplos": ejemplos(pr, p_todos, umbral),
    }
    clasificador.ARCHIVO_METADATOS.write_text(json.dumps(metadatos, ensure_ascii=False, indent=1), encoding="utf-8")
    return filas, tr, pr, mediana_poblacion, metadatos


def medir_inferencia(modelo, red, x):
    """Cuánto tarda UNA operación: Keras contra la misma red en NumPy."""
    modelo(x, training=False)
    inicio = time.perf_counter()
    for _ in range(200):
        modelo(x, training=False)
    keras_ms = (time.perf_counter() - inicio) / 200 * 1000
    inicio = time.perf_counter()
    for _ in range(5_000):
        red(x)
    numpy_ms = (time.perf_counter() - inicio) / 5_000 * 1000
    return {"keras_ms": round(keras_ms, 4), "numpy_ms": round(numpy_ms, 4), "veces": round(keras_ms / numpy_ms, 1)}


def ejemplos(pr, puntajes, umbral):
    """Un caso real de prueba por tipo, para mostrar en la página."""
    vistos, salida = set(), []
    for f, p in zip(pr, puntajes):
        if f["tipo"] in vistos:
            continue
        vistos.add(f["tipo"])
        salida.append({"tipo": f["tipo"], "fraude": bool(f["fraude"]), "nuevo": f["nuevo"], "probabilidad": round(float(p), 3),
                       "detectado": bool(p >= umbral), "valor": f["valor"], "metodo": f["metodo"],
                       "hora": f["fecha"].strftime("%H:%M"), "historial": f["contexto"]["historial"]})
    return salida


# =============================================================================
#  2. Monto esperado
# =============================================================================

def monto_paso(tr, pr):
    print("3/4  Entrenando la regresión del monto esperado...")
    legitimas = lambda conjunto: [f for f in conjunto if not f["fraude"]]  # noqa: E731
    x_tr = np.array([monto.vector(f["contexto"]) for f in legitimas(tr)], dtype="float32")
    y_tr = np.log10([f["valor"] for f in legitimas(tr)]).astype("float32")
    x_pr = np.array([monto.vector(f["contexto"]) for f in legitimas(pr)], dtype="float32")
    y_pr = np.log10([f["valor"] for f in legitimas(pr)])
    keras.utils.set_random_seed(SEMILLA)
    normalizacion = keras.layers.Normalization(name="normalizacion")
    normalizacion.adapt(x_tr)
    modelo = monto.construir(normalizacion)
    historia = modelo.fit(x_tr, y_tr, batch_size=128, epochs=60, validation_split=0.15, verbose=0,
                          callbacks=[keras.callbacks.EarlyStopping(patience=6, restore_best_weights=True)]).history
    modelo.save(monto.ARCHIVO_MODELO)
    prediccion = RedNumpy(keras.saving.load_model(monto.ARCHIVO_MODELO))(x_pr)[:, 0]
    referencia = x_pr[:, monto.NOMBRES.index("mediana_cliente")]       # log10 de la mediana (o de la población)
    error_red = np.abs(prediccion - y_pr)
    error_base = np.abs(referencia - y_pr)
    nuevos = np.array([f["nuevo"] for f in legitimas(pr)])

    def porcentaje(errores):
        """Error típico en %: si la red dice $10.000 y fue $12.000, el error es 20 %."""
        return round(float(np.mean(10 ** errores - 1) * 100), 1)

    metadatos = {
        "creado": datetime.now().isoformat(timespec="seconds"), "variables": monto.NOMBRES,
        "parametros": int(modelo.count_params()), "epocas": len(historia["loss"]),
        "datos": {"entrenamiento": len(x_tr), "prueba": len(x_pr)},
        "error_mediano": {"red": porcentaje(error_red), "mediana": porcentaje(error_base),
                          "red_nuevos": porcentaje(error_red[nuevos]), "mediana_nuevos": porcentaje(error_base[nuevos])},
        "historia": {k: [round(float(v), 5) for v in historia[k]] for k in ("loss", "val_loss")},
    }
    monto.ARCHIVO_METADATOS.write_text(json.dumps(metadatos, ensure_ascii=False, indent=1), encoding="utf-8")
    e = metadatos["error_mediano"]
    print(f"     error promedio: red {e['red']} % contra mediana del cliente {e['mediana']} % "
          f"(clientes nuevos: {e['red_nuevos']} % contra {e['mediana_nuevos']} %)")
    return metadatos


# =============================================================================
#  3. Demanda
# =============================================================================

def demanda_paso():
    print("4/4  Generando 26 semanas de ventas y entrenando la predicción de demanda...")
    temporal = Path(tempfile.mkdtemp(prefix="capricho_demanda_"))
    try:
        create_app({"BASE_DATOS": str(temporal / "d.db"), "CARPETA_LOGS": str(temporal / "logs"),
                    "CARPETA_COMPROBANTES": str(temporal / "comprobantes"), "IA_ACTIVA": False, "DIAS_DE_HISTORIA": 182})
        conexion = conectar(str(temporal / "d.db"))
        serie = ventas.serie_diaria(conexion, 182)[:-1]          # hoy todavía no termina
        conexion.close()
    finally:
        shutil.rmtree(temporal, ignore_errors=True)
    valores = [float(d["ventas"]) for d in serie]
    prueba = 28
    muestras = []
    for i in range(7, len(serie)):
        base = demanda.escala(valores[:i])
        muestras.append((demanda.vector(date.fromisoformat(serie[i]["dia"]), valores[:i], base), valores[i] / base, base))
    entrenamiento, evaluacion = muestras[:-prueba], muestras[-prueba:]
    x_tr = np.array([m[0] for m in entrenamiento], dtype="float32")
    y_tr = np.array([m[1] for m in entrenamiento], dtype="float32")

    # Aumento con TensorFlow: semanas más movidas o más flojas (todo ×0,85 a ×1,15) y un poco de ruido.
    def aumentar(fila, objetivo):
        factor = tf.random.uniform([], 0.85, 1.15, seed=SEMILLA)
        semana, niveles = fila[:7], fila[7:] * factor
        niveles = niveles * (1 + tf.random.normal(tf.shape(niveles), stddev=0.03, seed=SEMILLA))
        return tf.concat([semana, niveles], axis=0), objetivo * factor

    datos = (tf.data.Dataset.from_tensor_slices((x_tr, y_tr)).shuffle(500, seed=SEMILLA).repeat(20)
             .map(aumentar).batch(32).prefetch(tf.data.AUTOTUNE))
    keras.utils.set_random_seed(SEMILLA)
    normalizacion = keras.layers.Normalization(name="normalizacion")
    normalizacion.adapt(x_tr)
    modelo = demanda.construir(normalizacion)
    historia = modelo.fit(datos, epochs=40, verbose=0).history
    modelo.save(demanda.ARCHIVO_MODELO)
    red = RedNumpy(keras.saving.load_model(demanda.ARCHIVO_MODELO))

    reales = [valores[len(valores) - prueba + i] for i in range(prueba)]
    keras_pred = [float(red([m[0]])[0, 0]) * m[2] for m in evaluacion]
    xs = list(range(len(valores) - prueba))
    pendiente, intercepto, _ = regresion_lineal(xs, valores[:len(xs)])
    lineal_pred = [intercepto + pendiente * (len(xs) + i) for i in range(prueba)]
    ingenuo_pred = [valores[len(valores) - prueba + i - 7] for i in range(prueba)]
    mae = lambda pred: round(sum(abs(a - b) for a, b in zip(pred, reales)) / prueba)  # noqa: E731
    metadatos = {
        "creado": datetime.now().isoformat(timespec="seconds"), "variables": demanda.NOMBRES,
        "parametros": int(modelo.count_params()), "dias": len(serie), "prueba_dias": prueba,
        "error_promedio": {"red": mae(keras_pred), "regresion_lineal": mae(lineal_pred), "semana_pasada": mae(ingenuo_pred)},
        "venta_promedio": round(statistics.fmean(reales)),
        "prueba": [{"dia": serie[len(serie) - prueba + i]["dia"], "real": round(reales[i]), "red": round(keras_pred[i]),
                    "regresion_lineal": round(lineal_pred[i]), "semana_pasada": round(ingenuo_pred[i])} for i in range(prueba)],
        "historia": {"loss": [round(float(v), 5) for v in historia["loss"]]},
    }
    demanda.ARCHIVO_METADATOS.write_text(json.dumps(metadatos, ensure_ascii=False, indent=1), encoding="utf-8")
    e = metadatos["error_promedio"]
    print(f"     error promedio diario: red ${e['red']:,} · regresión lineal ${e['regresion_lineal']:,} · "
          f"semana pasada ${e['semana_pasada']:,} (venta promedio ${metadatos['venta_promedio']:,})".replace(",", "."))
    return metadatos


def main():
    logger.setLevel(logging.ERROR)
    if "--todo" in sys.argv:
        print("0/4  Reentrenando el autoencoder (herramientas/entrenar_ia.py)...")
        import entrenar_ia
        entrenar_ia.main()
    inicio = time.perf_counter()
    _, tr, pr, _, meta = clasificador_paso()
    monto_paso(tr, pr)
    demanda_paso()
    c = meta["comparacion"]
    print(f"\nListo en {time.perf_counter() - inicio:.0f} s. Prueba (días que el modelo no vio):")
    for nombre in c:
        todos, nuevos = c[nombre]["todos"], c[nombre]["clientes_nuevos"]
        print(f"  {nombre:22} recall {todos['recall']:.1%}  precisión {todos['precision']:.1%}  "
              f"falsas alarmas {todos['falsas_alarmas']:.2%}  | clientes nuevos: recall {nuevos['recall']:.1%}")
    print(f"  Inferencia de una operación: Keras {meta['inferencia']['keras_ms']} ms, NumPy "
          f"{meta['inferencia']['numpy_ms']} ms ({meta['inferencia']['veces']} veces más rápido)")


if __name__ == "__main__":
    main()
