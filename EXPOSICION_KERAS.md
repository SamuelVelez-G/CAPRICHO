# Exposición: detector de fraude con IA (Keras) en Capricho

Duración objetivo: **30 minutos** (mínimo 20, máximo 40). Cada sección sigue
un punto del mensaje del profesor.

| # | Sección | Tiempo | Qué se muestra |
|---|---|---|---|
| 1 | Qué es Keras y para qué sirve | 4 min | Explicación simple |
| 2 | Conceptos esenciales | 5 min | Página `/ia`: la red dibujada |
| 3 | El problema y para quién | 3 min | Dashboard: fraudes que las reglas no ven |
| 4 | Cómo funciona paso a paso | 5 min | Código: `caracteristicas.py`, `modelo.py`, `entrenar_ia.py` |
| 5 | Herramientas y decisiones técnicas | 3 min | Por qué autoencoder, por qué PyTorch |
| 6 | **Demo en vivo** | 7 min | Laboratorio + probador + dashboard |
| 7 | Limitaciones, dificultades y mejoras | 2 min | Página `/ia`, sección de limitaciones |
| 8 | Conclusión | 1 min | |

---

## Antes de empezar (15 minutos antes)

**Importante:** activa primero el entorno `.venv`. Keras y PyTorch están
instalados ahí; con el Python global la IA no carga.

```bash
.venv\Scripts\activate
```

```bash
python run.py --reiniciar
```

Al arrancar debe aparecer **`IA (Keras): activa`**. Si dice `DESACTIVADA`, el
entorno no está activado. Con `--reiniciar` sale la demo con datos y anomalías
de la IA ya detectadas.
Pestañas abiertas: `/ia`, `/laboratorio` y `/dashboard` (ingresar con
`admin@capricho.co` / `Capricho2026*`). Si el profesor quiere ver el
entrenamiento en vivo: `python herramientas/entrenar_ia.py` (tarda unos 2 minutos).

---

## 1. Qué es Keras y para qué sirve (4 min)

**Qué es.** Keras es una librería de Python para construir redes neuronales, es
decir, programas que **aprenden de ejemplos** en lugar de seguir reglas
escritas a mano. Con pocas líneas se dicen las capas de la red, cómo mide sus
errores y cómo corrige; Keras se encarga de las matemáticas.

**Comparación para cualquier persona.** Un programa normal es una receta: "si
hay 3 compras en 3 segundos, es fraude". Una red neuronal es como un cajero
con experiencia: después de ver miles de compras sabe cuándo algo "no huele
bien", aunque no sepa escribir la regla.

**Para qué sirve.** Reconocer imágenes, entender texto, predecir ventas,
recomendar productos y, en nuestro caso, **detectar comportamientos raros**.

**Qué problemas resuelve.** Los que son difíciles de escribir como reglas
porque dependen de muchas variables a la vez y cambian según cada persona.

---

## 2. Conceptos esenciales (5 min)

Solo lo necesario para entender el MVP:

| Concepto | En palabras simples | En nuestro proyecto |
|---|---|---|
| **Neurona** | Suma ponderada de sus entradas más una función de activación | Los puntos del dibujo en `/ia` |
| **Capa `Dense`** | Cada neurona se conecta con todas las de la capa anterior | 6 capas: 24, 12, 4, 12, 24, 9 |
| **Activación (ReLU, tanh)** | Permite aprender relaciones no lineales | ReLU en las capas internas, tanh en el cuello |
| **Pérdida (MSE)** | Qué tan equivocada está la red | Error cuadrático entre la compra y su reconstrucción |
| **Optimizador (Adam)** | Cómo corrige los pesos para equivocarse menos | Tasa de aprendizaje 0,001 |
| **Época** | Una pasada completa por los datos | Se detuvo sola en 350 |
| **Validación** | Datos apartados para ver si generaliza o memoriza | 15 % de las compras de entrenamiento |
| **Parada temprana** | Detener cuando la validación deja de mejorar | `EarlyStopping`, paciencia 30 |
| **Normalización** | Poner todas las variables en la misma escala | `keras.layers.Normalization` |
| **Autoencoder** | Red que aprende a copiar su entrada pasando por un cuello angosto | 9 → 4 → 9 |
| **Error de reconstrucción** | Qué tanto le cuesta a la red copiar la compra | Es el puntaje de rareza |
| **Umbral** | Desde qué error se considera rara | Percentil 99 de las compras normales |

**La idea clave del autoencoder.** Si a alguien le enseñas a dibujar de memoria
solo granizados, los dibujará muy bien; si le pides dibujar una moto, le saldrá
mal. La red aprendió a "dibujar" compras normales de Capricho: cuando no logra
reproducir una compra, es porque no se parece a nada de lo que vio.

---

## 3. El problema, los usuarios y la utilidad (3 min)

**Problema concreto.** El detector de Capricho funciona con reglas: ventana
deslizante, ráfaga, monto atípico y hash. Las reglas solo atrapan lo que alguien
programó. Un fraude que no encaje en ninguna pasa como normal:

- $250.000 a las 3 a. m. con PSE, de una clienta que siempre paga $9.000 con
  Nequi al mediodía. El monto está por debajo del límite de $300.000, es una
  sola compra (no hay ventana) y la firma es válida: **ninguna regla la ve**.

**Usuarios.** El administrador de Capricho, que revisa las anomalías en el
dashboard antes de despachar los pedidos.

**Utilidad.** Detecta fraudes nuevos sin que nadie escriba una regla para cada
uno, explica por qué los marcó y no bloquea: deja la compra para revisión.

**Por qué esto justifica el MVP.** Es una necesidad real del sistema que ya
construimos, y se puede medir: la IA contra las reglas en los mismos casos.

---

## 4. Cómo funciona, paso a paso (5 min)

**Qué información necesita.** Cada transacción que llega a `POST /api/transacciones`
(usuario, fecha, monto y método) y el historial de ese usuario.

**Cómo se procesa:**

1. **Variables** (`capricho/ia/caracteristicas.py`). La compra se convierte en
   9 números: hora (en seno y coseno, porque 23:59 está junto a 00:00), monto
   (en logaritmo), monto contra su mediana habitual, qué tanto usa ese método,
   distancia a su horario habitual, compras en la última hora, horas desde la
   anterior e historial. Se calculan con la misma búsqueda por índice que la
   ventana deslizante.
2. **Normalización.** Media 0 y desviación 1 por variable.
3. **Modelo** (`capricho/ia/modelo.py`). `keras.Sequential` con capas `Dense`
   9 → 24 → 12 → **4** → 12 → 24 → 9.
4. **Error de reconstrucción.** El error cuadrático medio entre la compra y lo
   que la red reconstruyó.
5. **Riesgo.** `100 · error / (error + umbral)`: en el umbral vale 50.
6. **Explicación.** Qué variable aportó más al error, por ejemplo "$250.000 es
   27,8 veces su compra habitual".
7. **Registro** (`capricho/servicios/detector.py`). Si el riesgo pasa de 50, se
   agrega la anomalía `COMPORTAMIENTO_INUSUAL` y la compra queda SOSPECHOSA.

**Cómo se entrenó** (`herramientas/entrenar_ia.py`):

1. 9 semanas de compras de demostración con hábitos realistas por cliente.
2. Solo compras normales, quitando también las vecinas de una anomalía (limpieza de datos).
3. División: 70 % entrenamiento, 15 % calibración del umbral, 15 % prueba.
4. `modelo.fit(X, X)`: la entrada y la salida esperada son la misma compra.
5. Umbral: el error que solo supera el 1 % de las compras de calibración.
6. Evaluación con compras normales nuevas y 300 ataques construidos.

**Qué resultados produce.** El riesgo de 0 a 100 en cada transacción, la
anomalía con su explicación en el dashboard y las métricas en `/ia`.

---

## 5. Herramientas y decisiones técnicas (3 min)

| Decisión | Por qué |
|---|---|
| **Keras 3** | Lo pedido; API simple para definir, entrenar y guardar (`.keras`) |
| **PyTorch como motor** | TensorFlow no tiene versión para Python 3.14. Keras 3 es multimotor, así que el código es el mismo |
| **Autoencoder y no un clasificador** | Un clasificador necesita miles de fraudes etiquetados, y no los tenemos. El autoencoder aprende solo de compras normales (no supervisado) |
| **Variables de comportamiento** | El fraude no es "un monto alto", sino "un monto alto *para ese cliente*". Por eso se compara con su propio historial |
| **Umbral en el percentil 99** | Controla las falsas alarmas: se acepta cerca del 1 % para no saturar al administrador |
| **No bloquea, marca** | La IA se puede equivocar; las reglas siguen bloqueando ráfagas y firmas falsas |
| **Modo "solo observar"** | Si llegan datos muy distintos (otro negocio), la IA no altera el resultado de las reglas |
| **Integrarlo a Capricho** | Ya había datos, API y dashboard: el MVP funciona de principio a fin |

**Diferencia con los ejemplos de keras.io.** El de fraude con tarjetas es un
clasificador *supervisado* con un dataset de Kaggle ya etiquetado. El de
autoencoder detecta anomalías en *series de tiempo* de un sensor. El nuestro es
un autoencoder sobre variables de comportamiento diseñadas por nosotros,
conectado a una API en vivo y comparado contra un sistema de reglas.

---

## 6. Demo en vivo (7 min)

**a) La página `/ia` (1 min).** Muestra la red dibujada, la curva de aprendizaje
(las dos líneas bajan juntas, así que no memorizó) y la tabla: la IA detecta
entre el 97 y el 100 % de los ataques y las reglas el 0 %. Las falsas alarmas
son del 2 %. En el histograma, a la izquierda del umbral quedan las normales y
a la derecha los ataques.

**b) Probador (2 min).** En `/ia`, "Probador en vivo":
1. **Compra normal**: riesgo de alrededor de 10, Normal.
2. **Fraude silencioso**: riesgo de alrededor de 90, Anomalía. Lee la
   explicación: "27,8 veces su compra habitual", "compra a las 03:15".
3. Mueve **la hora** de 03:15 a 13:00: el riesgo baja. Luego baja **el monto**
   a $9.000: queda normal. Así se ve que la red pondera varias cosas a la vez.
4. **Prueba de tarjeta**: $1.000, 3 compras en la última hora. Riesgo alto.

**c) De punta a punta por el endpoint (2 min).** En `/laboratorio`, escenario
**"Fraude que solo ve la IA (Keras)"**. Envía 6 compras normales de mediodía
con Nequi (APROBADAS, riesgo de 11 a 26) y luego $250.000 a las 3 a. m. con
PSE: queda **SOSPECHOSA**, riesgo de alrededor de 92, anomalía
`COMPORTAMIENTO_INUSUAL`. Abre la consola y muestra el JSON: ninguna regla se
disparó.

**d) Dashboard (1 min).** Tarjeta "Detección con IA": cuántas anomalías marcó
y cuántas **no vio ninguna regla**. En la tabla de anomalías, filtra por tipo
"IA: compra que no se parece a los hábitos del cliente" y abre una para ver la
explicación.

**e) Una limitación en vivo (1 min).** En el probador, **Cliente nuevo, monto
alto** sale anomalía. Luego cambia el monto a $12.000 a las 15:00: con 0
compras anteriores la red solo puede juzgar hora y monto. Esa es la limitación
de los clientes nuevos.

---

## 7. Limitaciones, dificultades y mejoras (2 min)

**Limitaciones:**
- Se entrenó con datos de demostración, no con clientes reales.
- Cerca del 2 % de las compras normales generan falsa alarma.
- Los clientes con menos de 3 compras no tienen hábito con qué comparar.
- Si un cliente cambia sus hábitos, al principio se verá raro.
- Con datos de otro tipo de negocio (montos de $50.000 a $150.000), todo le
  parece raro. Por eso existe el modo "solo observar".

**Dificultades (contarlo suma puntos):**
- **Datos contaminados.** La primera versión detectaba solo 2 de 60 fraudes
  silenciosos. El histórico tenía fraudes que ninguna regla había visto, y la
  red los aprendió como normales. Se resolvió entrenando con un histórico
  revisado y quitando las compras vecinas de cada anomalía.
- Al principio los clientes de la demo no tenían hábitos: compraban a cualquier
  hora y con cualquier método. Sin hábitos no hay nada que aprender, así que se
  les dio un perfil.
- TensorFlow no existe para Python 3.14: se usó Keras 3 sobre PyTorch.

**Mejoras futuras:**
- Reentrenar cada semana con datos reales revisados por el administrador.
- Usar las anomalías que el administrador confirma o descarta para ajustar el umbral.
- Más variables: dispositivo, ubicación y barrio del domicilio.
- Un umbral distinto según el perfil de cada cliente.

---

## 8. Conclusión (1 min)

Construimos un detector que aprende sin etiquetas cómo compran normalmente los
clientes de Capricho. Detecta entre el 97 y el 100 % de ataques que ninguna
regla ve, con un 2 % de falsas alarmas, y explica por qué marcó cada compra.
No reemplaza a las reglas: las complementa. Aplicamos los conceptos de Keras
(capas `Dense`, pérdida, optimizador, épocas, validación, parada temprana y
normalización) a un problema real del sistema que ya teníamos, y el MVP
funciona de principio a fin: del endpoint al dashboard.

---

## Preguntas probables

**¿Por qué una red neuronal si ya tenían reglas?**
Las reglas detectan lo conocido. La red detecta lo que se sale de lo normal,
aunque nadie haya escrito una regla para eso: 0 % con reglas contra 97 a 100 %
con IA en los ataques de prueba.

**¿Qué es un autoencoder?**
Una red que aprende a copiar su entrada pasando por un cuello de botella. Como
solo vio compras normales, copia bien las normales y mal las raras. El error de
la copia es el puntaje de rareza.

**¿Por qué no un clasificador de fraude / no fraude?**
Porque no tenemos miles de fraudes etiquetados. El autoencoder es no
supervisado: solo necesita compras normales. Además detecta tipos de fraude que
nunca vio.

**¿Cómo eligieron el umbral?**
Con compras normales que la red no vio al entrenar (calibración): el error que
solo supera el 1 %. Se comprobó con otro grupo distinto (prueba), que dio un 2 %
de falsas alarmas.

**¿Cómo saben que no memorizó?**
Por la curva de validación: baja junto con la de entrenamiento. La parada
temprana se detiene cuando validación deja de mejorar. Y se evaluó con datos que
no vio.

**¿Qué pasa si la IA se equivoca?**
No bloquea: marca la compra como SOSPECHOSA para revisión humana. El
administrador la descarta en el dashboard y queda en la línea de tiempo.

**¿Por qué la hora en seno y coseno?**
Porque la hora es circular. Con un solo número, 23:00 y 01:00 estarían a 22
horas de distancia; con seno y coseno quedan a 2.

**¿Por qué PyTorch y no TensorFlow?**
TensorFlow no tiene versión para Python 3.14. Keras 3 corre sobre TensorFlow,
JAX o PyTorch con el mismo código; solo cambia `KERAS_BACKEND`.

**¿Cuántos datos usaron? ¿Son reales?**
2.704 compras normales de 9 semanas de demostración, con hábitos realistas por
cliente. No son reales; con datos reales habría que reentrenar y volver a medir.

**¿Cuánto tarda?**
El entrenamiento tarda unos 2 minutos en CPU. Evaluar una compra en vivo toma
milisegundos, dentro del mismo endpoint.

**¿Qué aprendieron?**
Que la calidad de los datos importa más que la red. Con datos contaminados, el
mismo modelo detectaba 2 de 60; con datos limpios, 60 de 60.

**¿Qué es una época y qué es el batch?**
Una época es una pasada por todas las compras de entrenamiento. El batch son 32
compras: la red corrige sus pesos después de cada grupo de 32.

**¿Cuántos parámetros tiene la red?**
1.189 pesos: lo que aprendió durante el entrenamiento.
