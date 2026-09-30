"""
Datos de demostración.

Genera 9 semanas de historia para que el dashboard tenga qué mostrar. Nada se
inserta "a mano" como anomalía: cada transacción pasa por el mismo detector
que usa la API, en orden cronológico, así que las anomalías que aparecen son
las que el algoritmo realmente encontró.

La semilla aleatoria es fija (42), igual que en el primer trabajo: siempre
se generan los mismos datos y los resultados se pueden comparar.
"""

import json
import random
from datetime import timedelta

from .errores import ErrorValidacion
from .estructuras import merge_sort
from .seguridad import firmar_transaccion, hashear_password
from .servicios import catalogo, detector, domicilios
from .servicios.pedidos import cotizar_pedido
from .tiempo import a_texto, ahora, desde_texto

DIAS_DE_HISTORIA = 63

GRANIZADOS = [
    ("Granizado Pequeño", "Granizado de café artesanal, vaso de 12 oz", 7_000, 12),
    ("Granizado Mediano", "Granizado de café artesanal, vaso de 16 oz", 9_000, 16),
    ("Granizado Grande", "Granizado de café artesanal, vaso de 22 oz", 12_000, 22),
]
ADICIONES = ["Galleta Milo", "Galleta Oreo", "Chokis", "Minichips", "Mr Brown", "Chocorramo",
             "Submarino", "ChocoDisk", "WaferJet", "Pingüinos", "Gol", "Piazza"]

CLIENTES = [
    ("Laura", "Gómez"), ("Santiago", "Restrepo"), ("Mariana", "Zapata"), ("Andrés", "Mejía"),
    ("Camila", "Ospina"), ("Juan", "Arango"), ("Daniela", "Vélez"), ("Sebastián", "Cardona"),
    ("Valeria", "Hincapié"), ("Mateo", "Londoño"), ("Isabella", "Correa"), ("Tomás", "Uribe"),
    ("Sofía", "Muñoz"), ("Nicolás", "Echeverri"), ("Manuela", "Toro"), ("Samuel", "Posada"),
    ("Antonella", "Giraldo"), ("Emilio", "Álvarez"), ("Salomé", "Jaramillo"), ("David", "Montoya"),
    ("Luciana", "Rendón"), ("Felipe", "Quintero"), ("Gabriela", "Betancur"), ("Julián", "Castaño"),
    ("Paulina", "Agudelo"), ("Esteban", "Henao"), ("Juliana", "Marín"), ("Miguel", "Tabares"),
    ("Sara", "Bedoya"), ("Alejandro", "Duque"), ("Natalia", "Suárez"), ("Simón", "Palacio"),
]
DOMINIOS = ["gmail.com", "hotmail.com", "outlook.com", "correo.co", "yahoo.com"]
METODOS = ["Nequi"] * 7 + ["Tarjeta"] * 5 + ["Daviplata"] * 3 + ["PSE"] * 2 + ["Efectivo"] * 3
VALORES = [7_000, 9_000, 9_000, 11_000, 12_000, 14_000, 16_000, 18_000, 21_000, 24_000, 27_000, 32_000, 38_000]

HORAS_NORMALES = {6: 1, 7: 3, 8: 5, 9: 6, 10: 6, 11: 5, 12: 5, 13: 4, 14: 5, 15: 6, 16: 7,
                  17: 7, 18: 6, 19: 5, 20: 4, 21: 3, 22: 1}
HORAS_FRAUDE = {0: 2, 1: 2, 2: 1, 3: 1, 9: 1, 11: 1, 14: 1, 16: 1, 18: 2, 19: 3, 20: 4, 21: 4, 22: 4, 23: 3}

NOTAS = {
    "ABIERTA": ["En revisión por el administrador", "Se pidió soporte a la pasarela de pagos"],
    "REVISADA": ["Confirmado: tarjeta reportada, se bloqueó el medio de pago",
                 "Confirmado con el banco: compras no reconocidas por el titular",
                 "Usuario notificado; se reforzó la verificación en sus próximos pagos"],
    "DESCARTADA": ["Falso positivo: pedido grupal de una oficina",
                   "El cliente confirmó las compras por teléfono",
                   "Reintentos de la app por mala conexión, no es fraude"],
}

EVENTOS = [
    ("INYECCION_SQL", "CRITICO", "POST", "/api/auth/login", "email", "' OR '1'='1' --"),
    ("INYECCION_SQL", "CRITICO", "POST", "/api/transacciones", "user", "a@a.com'; DROP TABLE transacciones; --"),
    ("INYECCION_SQL", "CRITICO", "POST", "/api/auth/registro", "nombre", "Ana' UNION SELECT password_hash FROM usuarios"),
    ("VALIDACION", "BAJO", "POST", "/api/transacciones", "value", "Debe ser un número (no texto ni booleano)"),
    ("VALIDACION", "BAJO", "POST", "/api/auth/registro", "nombre", "Debe tener más de 3 letras"),
    ("VALIDACION", "BAJO", "POST", "/api/transacciones", "idTxn", "Es obligatorio y no puede ser nulo ni vacío"),
    ("LOGIN_FALLIDO", "MEDIO", "POST", "/api/auth/login", None, "Intento fallido de inicio de sesión"),
    ("REPLAY", "ALTO", "POST", "/api/transacciones", None, "idTxn repetido: posible reenvío"),
    ("LIMITE_PETICIONES", "MEDIO", "POST", "/api/transacciones", None, "Más de 40 peticiones en un segundo"),
]


def _pesos(rng, tabla):
    return rng.choices(list(tabla), weights=list(tabla.values()))[0]


def _instante(rng, dia, hora):
    return dia + timedelta(hours=hora, minutes=rng.randrange(60), seconds=rng.randrange(60),
                           milliseconds=rng.randrange(1000))


def sembrar_base(db, config):
    """Lo mínimo para que la tienda funcione: reglas, productos y cuentas."""
    creado = a_texto(ahora().replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=90))
    detector.guardar_reglas(db, detector.REGLAS_POR_DEFECTO, confirmar=False)

    # --- Productos -----------------------------------------------------------
    for nombre, descripcion, precio, onzas in GRANIZADOS:
        db.execute(
            """INSERT INTO productos (nombre, descripcion, categoria, precio, onzas, imagen, activo,
                                      fecha_creacion, fecha_actualizacion)
               VALUES (?, ?, 'GRANIZADO', ?, ?, 'menu.jpg', 1, ?, ?)""",
            (nombre, descripcion, precio, onzas, creado, creado))
    for nombre in ADICIONES:
        db.execute(
            """INSERT INTO productos (nombre, descripcion, categoria, precio, onzas, imagen, activo,
                                      fecha_creacion, fecha_actualizacion)
               VALUES (?, 'Adición para tu granizado', 'ADICION', 2000, NULL, NULL, 1, ?, ?)""",
            (nombre, creado, creado))

    # --- Cuentas -------------------------------------------------------------
    cuentas = [
        ("Administrador Capricho", config["ADMIN_EMAIL"], "3000000000", config["ADMIN_PASSWORD"], "ADMIN"),
        ("Valentina Restrepo", config["CLIENTE_DEMO_EMAIL"], "3001234567", config["CLIENTE_DEMO_PASSWORD"], "CLIENTE"),
    ]
    for nombre, email, telefono, password, rol in cuentas:
        db.execute(
            """INSERT INTO usuarios (nombre, email, telefono, password_hash, rol, fecha_creacion, fecha_actualizacion)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (nombre, email, telefono, hashear_password(password), rol, creado, creado))
    db.commit()


def sembrar(db, estado, config):
    """Datos base + 9 semanas de historia pasadas por el detector."""
    rng = random.Random(42)
    momento_actual = ahora()
    hoy = momento_actual.replace(hour=0, minute=0, second=0, microsecond=0)
    creado = a_texto(hoy - timedelta(days=90))
    llave = config["LLAVE_HMAC"]
    sembrar_base(db, config)

    correos = [config["CLIENTE_DEMO_EMAIL"]]
    for nombre, apellido in CLIENTES:
        email = f"{_sin_tildes(nombre)}.{_sin_tildes(apellido)}@{rng.choice(DOMINIOS)}".lower()
        telefono = "3" + "".join(str(rng.randrange(10)) for _ in range(9))
        db.execute(
            """INSERT INTO usuarios (nombre, email, telefono, fecha_creacion, fecha_actualizacion)
               VALUES (?, ?, ?, ?, ?)""",
            (f"{nombre} {apellido}", email, telefono, creado, creado))
        correos.append(email)
    estado.reconstruir(db)

    # --- Historia de 9 semanas: así "30 días" se compara con los 30 anteriores ---
    eventos = []
    for dias_atras in range(DIAS_DE_HISTORIA - 1, -1, -1):
        dia = hoy - timedelta(days=dias_atras)
        cantidad = rng.randint(30, 50) + (12 if dia.weekday() >= 5 else 0)
        for _ in range(cantidad):
            eventos.append(("normal", _instante(rng, dia, _pesos(rng, HORAS_NORMALES)),
                            rng.choice(correos), rng.choice(VALORES)))

        if rng.random() < 0.75:                                  # 3 o 4 en la ventana
            inicio = _instante(rng, dia, _pesos(rng, HORAS_FRAUDE))
            usuario = rng.choice(correos)
            for n in range(rng.choice([3, 3, 3, 4])):
                eventos.append(("normal", inicio + timedelta(seconds=n * rng.uniform(0.35, 0.85)),
                                usuario, rng.choice(VALORES)))
        if rng.random() < 0.2:                                   # ráfaga: 5 o 6 en menos de 1 s
            inicio = _instante(rng, dia, _pesos(rng, HORAS_FRAUDE))
            usuario = rng.choice(correos)
            for n in range(rng.choice([5, 6])):
                eventos.append(("normal", inicio + timedelta(milliseconds=n * rng.randint(110, 170)),
                                usuario, rng.choice(VALORES)))
        if rng.random() < 0.3:                                   # alguien alteró el valor
            eventos.append(("hash_alterado", _instante(rng, dia, _pesos(rng, HORAS_FRAUDE)),
                            rng.choice(correos), rng.choice(VALORES)))
        if rng.random() < 0.22:                                  # monto atípico
            eventos.append(("normal", _instante(rng, dia, _pesos(rng, HORAS_FRAUDE)),
                            rng.choice(correos), rng.randrange(320, 1500) * 1000))
        if rng.random() < 0.1:                                   # precio manipulado en la tienda
            eventos.append(("precio", _instante(rng, dia, _pesos(rng, HORAS_NORMALES)),
                            rng.choice(correos), rng.choice([2_000, 3_000, 5_000])))
        if dias_atras <= 12:                                     # pedidos de la tienda
            for _ in range(rng.randint(1, 3)):
                eventos.append(("pedido", _instante(rng, dia, _pesos(rng, HORAS_NORMALES)),
                                rng.choice(correos[:12]), None))

    eventos = [e for e in eventos if e[1] <= momento_actual - timedelta(minutes=5)]
    eventos = merge_sort(eventos, clave=lambda e: e[1])          # orden cronológico

    pedidos = []
    for numero, (tipo, instante, email, valor) in enumerate(eventos, start=1):
        if tipo == "pedido":
            pedidos.append(_pedido(db, estado, rng, instante, email))
            continue
        txn = {"id_txn": str(100000 + numero), "email": email, "fecha": instante,
               "valor": valor, "metodo_pago": rng.choice(METODOS)}
        externo = {"idTxn": txn["id_txn"], "user": email, "date": a_texto(instante),
                   "value": valor, "paymentMethod": txn["metodo_pago"]}
        txn["hash"] = firmar_transaccion(externo, llave)
        txn["hash_valido"] = True
        if tipo == "hash_alterado":
            txn["valor"] = valor * 10         # llegó un valor distinto al firmado
            txn["hash_valido"] = False
        if tipo == "precio":
            _precio_manipulado(db, estado, txn, instante, rng)
            continue
        detector.procesar_transaccion(db, estado, txn, origen="DEMO", llegada=instante, confirmar=False)

    _avanzar_pedidos(db, pedidos, momento_actual)
    _revisar_anomalias(db, rng, momento_actual, config["ADMIN_EMAIL"])
    _eventos(db, rng, hoy, momento_actual)
    db.commit()
    estado.reconstruir(db)


def _sin_tildes(texto):
    return texto.translate(str.maketrans("áéíóúÁÉÍÓÚñÑ", "aeiouAEIOUnN"))


def _precio_manipulado(db, estado, txn, instante, rng):
    real = rng.choice([9_000, 12_000, 16_000, 21_000])
    anomalia = detector._anomalia(
        "PRECIO_MANIPULADO", "ALTO", 1, 0,
        f"El navegador envió un total de {detector.dinero(txn['valor'])} y el servidor calculó "
        f"{detector.dinero(real)}. Se alteró el precio en el localStorage.")
    txn["id_txn"] = f"CAP-{instante:%Y%m%d%H%M%S}-{rng.randrange(16 ** 6):06X}"
    usuario_id, _ = estado.indice_usuarios.buscar(txn["email"])
    detector._guardar(db, estado, usuario_id, txn, "RECHAZADA", [anomalia], "TIENDA", None, instante)


def _pedido(db, estado, rng, instante, email):
    productos = catalogo.listar(db)
    granizados = [p for p in productos if p["categoria"] == "GRANIZADO"]
    adiciones = [p for p in productos if p["categoria"] == "ADICION"]
    items = []
    for _ in range(rng.choice([1, 1, 2, 2, 3])):
        extras = rng.sample(adiciones, rng.choice([0, 1, 1, 2]))
        granizado = rng.choice(granizados)
        items.append({"producto_id": granizado["id"], "sabor": rng.choice(catalogo.SABORES),
                      "cantidad": rng.choice([1, 1, 2]), "adiciones": sorted(a["id"] for a in extras),
                      "precio_unitario": granizado["precio"] + sum(a["precio"] for a in extras)})
    domicilio = rng.random() < 0.75
    barrio = rng.choice([b for b in domicilios.BARRIOS if b != domicilios.TIENDA])
    datos = {"items": items, "tipo_entrega": "DOMICILIO" if domicilio else "RECOGER",
             "barrio": barrio if domicilio else None,
             "direccion": f"Calle {rng.randint(30, 110)} # {rng.randint(20, 80)}-{rng.randint(10, 99)}" if domicilio else None,
             "metodo_pago": rng.choice(METODOS)}
    try:
        lineas, subtotal, tarifa, total, _, entrega = cotizar_pedido(db, datos)
    except ErrorValidacion:
        return None
    txn = detector.transaccion_de_tienda(estado, email, total, datos["metodo_pago"], instante)
    resultado = detector.procesar_transaccion(db, estado, txn, origen="TIENDA", llegada=instante, confirmar=False)
    usuario_id, _ = estado.indice_usuarios.buscar(email)
    cursor = db.execute(
        """INSERT INTO pedidos (usuario_id, transaccion_id, estado, tipo_entrega, barrio, direccion, ruta,
                                distancia_km, subtotal, domicilio, total, metodo_pago, fecha_creacion,
                                fecha_actualizacion)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (usuario_id, resultado["id"], "RECHAZADO" if resultado["estado"] == "RECHAZADA" else "SOLICITADO",
         datos["tipo_entrega"], datos["barrio"], datos["direccion"],
         json.dumps(entrega["ruta"], ensure_ascii=False) if entrega else None,
         entrega["distancia_km"] if entrega else 0, subtotal, tarifa, total, datos["metodo_pago"],
         a_texto(instante), a_texto(instante)))
    for linea in lineas:
        db.execute(
            """INSERT INTO pedido_items (pedido_id, producto_id, nombre, sabor, adiciones, cantidad,
                                         precio_unitario, subtotal) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (cursor.lastrowid, linea["producto_id"], linea["nombre"], linea["sabor"],
             json.dumps(linea["adiciones"], ensure_ascii=False), linea["cantidad"],
             linea["precio_unitario"], linea["subtotal"]))
    return cursor.lastrowid, instante


def _avanzar_pedidos(db, pedidos, momento_actual):
    """Los viejos ya se entregaron; los 2 más recientes siguen en proceso o en cola."""
    pedidos = [p for p in pedidos if p]
    for posicion, (pedido_id, instante) in enumerate(pedidos):
        restantes = len(pedidos) - posicion
        if restantes > 5:
            nuevo, cuando = "ENTREGADO", instante + timedelta(minutes=35)
        elif restantes == 5:
            nuevo, cuando = "EN_PROCESO", instante + timedelta(minutes=10)
        else:
            continue                          # se quedan SOLICITADOS, en la cola
        db.execute(
            "UPDATE pedidos SET estado = ?, fecha_actualizacion = ? WHERE id = ? AND estado = 'SOLICITADO'",
            (nuevo, a_texto(min(cuando, momento_actual)), pedido_id))


def _revisar_anomalias(db, rng, momento_actual, admin):
    """Simula el trabajo del administrador: lo viejo ya está revisado, lo de
    hoy sigue nuevo. Cada cambio queda en el historial (línea de tiempo)."""
    filas = db.execute("SELECT id, fecha_creacion FROM anomalias").fetchall()
    for fila in filas:
        creada = desde_texto(fila["fecha_creacion"])
        edad = (momento_actual - creada).days
        if edad >= 4:
            final = rng.choices(["REVISADA", "DESCARTADA", "ABIERTA"], weights=[55, 35, 10])[0]
        elif edad >= 1:
            final = rng.choices(["ABIERTA", "REVISADA", "DESCARTADA", "NUEVA"], weights=[40, 30, 10, 20])[0]
        else:
            final = rng.choices(["NUEVA", "ABIERTA"], weights=[70, 30])[0]
        if final == "NUEVA":
            continue
        pasos = ["ABIERTA"] if final == "ABIERTA" else (
            ["ABIERTA", final] if rng.random() < 0.7 else [final])
        anterior, cuando = "NUEVA", creada
        for paso in pasos:
            cuando = min(cuando + timedelta(minutes=rng.randint(12, 60 * 20)), momento_actual)
            db.execute(
                """INSERT INTO anomalias_historial (anomalia_id, estado_anterior, estado_nuevo, nota, responsable, fecha)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (fila["id"], anterior, paso, rng.choice(NOTAS[paso]), admin, a_texto(cuando)))
            anterior = paso
        db.execute("UPDATE anomalias SET estado = ?, fecha_actualizacion = ? WHERE id = ?",
                   (final, a_texto(cuando), fila["id"]))


def _eventos(db, rng, hoy, momento_actual):
    for numero in range(26):
        tipo, nivel, metodo, ruta, campo, texto = rng.choice(EVENTOS)
        cuando = min(_instante(rng, hoy - timedelta(days=rng.randint(0, 20)), _pesos(rng, HORAS_FRAUDE)),
                     momento_actual - timedelta(minutes=rng.randint(10, 600)))
        detalle = f"{campo}: {texto}" if campo else texto
        db.execute(
            """INSERT INTO eventos (tipo, nivel, detalle, ruta, metodo, ip, email, atendido, fecha)
               VALUES (?, ?, ?, ?, ?, ?, NULL, ?, ?)""",
            (tipo, nivel, detalle, ruta, metodo, f"181.{rng.randint(50, 60)}.{rng.randint(0, 255)}.{rng.randint(1, 254)}",
             1 if numero < 19 else 0, a_texto(cuando)))
