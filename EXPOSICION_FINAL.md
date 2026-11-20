# Guía para presentar la entrega final

Duración sugerida: **25 minutos** más preguntas. El orden sigue los criterios
de evaluación y empieza por lo que más pesa en la nota (algoritmos e IA, 30 %
cada uno), pero se abre y se cierra con las dos observaciones del profesor.

## Antes de empezar (15 minutos antes)

```bash
.venv\Scripts\activate
```

```bash
python run.py --reiniciar
```

1. En la consola debe decir `IA (Keras): clasificador, autoencoder, monto esperado, demanda sobre tensorflow`.
   Si dice `DESACTIVADA`, el entorno no está activado.
2. Ingresar como `admin@capricho.co` / `Capricho2026*`.
3. Dejar abiertas estas pestañas: **Panel**, **En vivo**, **Gestión**, **Integridad**,
   **Calidad**, **Algoritmos**, **IA** y **Estadística**.
4. Correr una vez `python herramientas/benchmark.py` (30 s) para que Algoritmos
   tenga la medición completa con 50.000 datos.
5. Si el profesor va a transferir desde su celular: en otra terminal
   `ngrok http 5000` y tener lista la dirección `https://xxxx.ngrok-free.app/transferir`.
6. Si el profesor va a usar su generador de transacciones con montos que no son de
   una cafetería: Antifraude → Reglas → IA en **"Solo observar"**.

## 1. El problema y lo que pidió el profesor (2 min)

> "Un negocio no solo necesita vender: necesita saber si lo que pasa en sus
> datos es íntegro, normal o sospechoso. Capricho ahora opera (usuarios, ítems,
> pedidos, facturas y pagos) y además valida, protege, analiza y predice."

Mostrar el **Panel**: ventas, predicción de la semana, alertas, calidad,
modelos y benchmark en una sola página.

Contar las dos observaciones de la exposición y prometer que se van a ver:
1. Aprender de todos los clientes y no solo del historial de cada uno.
2. Ver una transferencia hecha en ese momento y cómo la analiza el sistema.

## 2. Base de datos y módulos operativos (4 min) · 20 % de la nota

En **Gestión → Caja**:
1. Pedido presencial con 2 granizados con adición y un brownie, 10 % de
   descuento con motivo, pago con Nequi → **Crear pedido y factura**.
2. Señalar en la factura: número consecutivo (FV-…), base gravable, impuesto
   al consumo del 8 % incluido, descuento y el **hash** con el hash anterior.
3. **Comprobante válido** (descargarlo y adjuntarlo) → pago APROBADO y VERIFICADO.
4. Otra factura con el **comprobante falsificado** → RECHAZADO, FALSO.
5. Otra con el **mismo comprobante válido** → RECHAZADO, REUTILIZADO.

Mencionar: el inventario bajó (Ítems → movimientos), los usuarios tienen roles
(Usuarios), las categorías no se pueden repetir escritas distinto, y la base
tiene 16 tablas con llaves foráneas y restricciones.

## 3. Integridad (2 min) · 10 %

En **Integridad**: todo íntegro → **Alterar la factura** (cambia el total
directamente en SQLite, como un empleado deshonesto) → la cadena dice
"No cuadra" exactamente en esa factura → **Restaurar**.

> "Es un hash encadenado con HMAC: cada factura amarra a la anterior. Sin la
> llave, nadie puede recalcular la cadena para tapar el cambio."

## 4. Limpieza y calidad (3 min) · 10 %

En **Calidad**:
1. Auditoría: puntaje y las cuatro dimensiones; la lista encuentra a Laura
   Gómez registrada dos veces (correo en mayúsculas y mismo celular), el ítem
   "galleta  oreo" repetido y una torta de $75.000 (un cero de más).
2. **Corregir lo automático** → el puntaje sube.
3. Importar `clientes_sucios.csv` (link en la página): cada fila queda
   válida, corregida, duplicada o descartada, con el motivo.

## 5. Algoritmos y análisis experimental (4 min) · 30 %

En **Algoritmos**:
1. Elegir **Búsqueda por ID**: en la gráfica log-log la lineal sube, la binaria
   casi plana, el hash plano. "La pendiente es el exponente: la medimos con
   una regresión."
2. **Ventana deslizante**: el doble ciclo O(n²) contra dos punteros: más de
   9.000 veces más rápido con 50.000 transacciones. "Este es el algoritmo
   crítico del detector, y así lo optimizamos."
3. **Teoría contra lo medido**: O(n²) da pendiente ≈ 2, O(n) ≈ 1, O(1) ≈ 0.
4. Ordenamiento simple: todos O(n²); entre ellos solo cambia la constante (2×).

> "Todas las variantes dan el mismo resultado (se verifica en cada corrida);
> lo único que cambia es el tiempo cuando crecen los datos."

## 6. Modelos de IA (6 min) · 30 %

En **IA**:
1. Las 4 tarjetas: clasificador, monto esperado, autoencoder y demanda.
2. **Clasificador**: datos simulados etiquetados, 23 variables, red
   64-32-1, TensorFlow para normalizar y aumentar los fraudes.
3. **Tabla por segmento** (observación 1 del profesor): con clientes nuevos el
   clasificador detecta 85 % con 100 % de precisión; las reglas 56 %; el
   autoencoder 82 % pero con muchas falsas alarmas.
4. **Por tipo**: los pedidos grandes legítimos los marca el autoencoder (90 %)
   y casi nunca el clasificador: aprendió de toda la población que eso es normal.
5. **Aumento de datos**: F1 de 0,929 a 0,950.
6. **Probador**: "Cliente nuevo, monto alto" → FRAUDULENTA con 100 %
   conocimiento general; "Cliente habitual" → NORMAL.

En **Estadística** (Simple Statistics):
- Elegir un cliente: caja de cuartiles, y la tabla "Python contra Simple
  Statistics" → coinciden.
- Empleados: Kevin Arias tiene z alto en descuentos y anulaciones; las alertas
  del Panel lo señalan.

En el **Panel**: la predicción de demanda de la red contra la regresión lineal.

## 7. Transferencia en vivo (3 min) · observación 2 del profesor

Pedirle al profesor que entre desde su celular a la dirección de ngrok
`/transferir` (o hacerlo desde el formulario de **En vivo**):
1. **Cliente habitual, compra normal** → APROBADA, probabilidad ≈ 0 %, "lo que
   la hizo ver normal".
2. **Cuenta tomada** → SOSPECHOSA: el monto está fuera de sus cuartiles, la red
   da casi 100 % y explica que el monto es muchas veces el típico, que el
   método no es el suyo, etc., con el reparto general/personal.
3. **Cliente nuevo, monto alto** → la red decide con 100 % de conocimiento
   general.
4. (Opcional) **6 en el mismo segundo** → RECHAZADA por ráfaga.

> "Esto pasó ahora, con modelos entrenados antes: el sistema aplicó lo que
> aprendió a una transferencia que nunca había visto, en menos de 3 milisegundos."

## 8. Limitaciones y cierre (1 min)

- Datos simulados: con clientes reales hay que reentrenar y medir otra vez.
- La IA aprende lo que se le muestra (contar el error del 19 % y cómo se corrigió).
- No bloquea: marca para revisión humana; las reglas siguen bloqueando lo evidente.

Cierre: "Pasamos de un detector de reglas a una plataforma que opera, limpia,
protege, mide sus algoritmos y aprende de todos sus clientes."

## Preguntas probables

**¿Por qué un clasificador y además el autoencoder?** Son preguntas distintas.
El clasificador aprende de fraudes etiquetados de toda la población (sirve con
clientes nuevos); el autoencoder no necesita etiquetas y mide si una compra se
parece a los hábitos de ese cliente. Medidos con los mismos datos, el
clasificador es mejor (90,5 % contra 71,6 %, y muchas menos falsas alarmas).

**¿De dónde salen las etiquetas?** De un simulador (`ia/simulador.py`) que
genera 800 clientes con los hábitos de Capricho y siete tipos de fraude. Se
evalúa con días posteriores a los de entrenamiento (división temporal).

**¿Qué hace TensorFlow?** Prepara los datos (`Normalization`), arma el
`tf.data` que mezcla y aumenta los fraudes con ruido, entrena y guarda/carga los
modelos en formato `.keras`.

**¿Qué es el aumento de datos?** Los fraudes son pocos (3,7 %). Se repiten con un
poco de ruido gaussiano en las variables continuas para que la red vea más
variedad. Subió el F1 de 0,929 a 0,950.

**¿Cómo sabe cuánto conocimiento general o personal usó?** A cada grupo de
variables se le pone el valor típico de una compra normal y se mide cuánto
cambia la decisión (en log-odds). Se suman los cambios de las variables
generales y de las personales.

**¿Por qué el umbral es 99 %?** Se entrenó viendo 25 % de fraudes (por el
aumento), así que la red da probabilidades altas; el umbral se eligió con el
mejor F1 en validación, no a ojo.

**¿Por qué NumPy en vivo si se usa Keras?** Keras entrena, guarda y carga. Para
una sola operación, llamar a Keras toma 3 ms; la misma cuenta con NumPy toma
0,02 ms. Las pruebas verifican que el resultado es idéntico.

**¿Cómo se estima la complejidad?** Con una regresión lineal de log(tiempo)
contra log(n): si t = c·nᵏ, entonces log t = log c + k·log n, y la pendiente es k.

**¿Qué pasa si alguien cambia una factura en la base?** Su hash ya no coincide
con su contenido; si la borra, la siguiente ya no apunta a la anterior. Con
HMAC, sin la llave no puede recalcular la cadena.

**¿Cómo se sabe que el comprobante corresponde al pago?** El PDF de la pasarela
trae los datos firmados; se verifica la firma, el monto, el método, y que el
archivo o la referencia no se hayan usado antes.

**¿Por qué Python 3.12?** TensorFlow 2.21 no existe para Python 3.14. Si alguien
solo tiene 3.14, la aplicación corre igual sobre PyTorch (Keras 3 es
multimotor); solo reentrenar exige TensorFlow.

## Si algo falla

| Problema | Qué hacer |
|---|---|
| `IA (Keras): DESACTIVADA` | Activar `.venv` y volver a arrancar |
| El generador del profesor marca todo como fraude | Antifraude → Reglas → IA en "Solo observar" |
| ngrok no abre | Usar el formulario de **En vivo** en el mismo computador |
| Algoritmos dice "Todavía no se ha medido" | `python herramientas/benchmark.py` o el botón del benchmark rápido |
| La página no muestra cambios | Reiniciar `python run.py` (las plantillas quedan en caché) |
