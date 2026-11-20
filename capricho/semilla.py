"""
Datos de demostración.

Genera 9 semanas de operación de Capricho: pedidos por la web, la app, la caja
y domicilios telefónicos; facturas con impuesto y descuentos; pagos con
comprobante; inventario que baja con cada venta y se repone cada lunes; y
las transacciones de la pasarela con sus ataques. Nada se inserta "a mano"
como anomalía o alerta: cada operación pasa por los mismos servicios que usa
la API, en orden cronológico, así que lo que aparece en el panel es lo que
los algoritmos realmente encontraron.

Casos sembrados a propósito para la demostración:
  - Kevin Arias (empleado) empieza a dar descuentos y a anular facturas ya
    cobradas en los últimos 10 días: la estadística por empleado lo detecta.
  - Comprobantes falsos, reutilizados y que no coinciden con el pago.
  - Ventanas, ráfagas, hashes alterados, montos atípicos y fraudes
    silenciosos en la pasarela (los de la primera entrega).
  - Datos sucios para la auditoría de calidad: clientes duplicados con el
    correo en mayúsculas, celulares mal escritos, un ítem repetido y un
    precio con un cero de más.

La semilla aleatoria es fija (42): siempre se generan los mismos datos.
"""

import random
from datetime import timedelta

from .errores import ErrorApi
from .estructuras import merge_sort
from .seguridad import firmar_transaccion, hashear_password
from .servicios import catalogo, comprobantes, detector, domicilios, facturacion, normalizacion, pagos, pedidos
from .tiempo import a_texto, ahora, desde_texto

DIAS_DE_HISTORIA = 63
STOCK_INICIAL = 600

CATEGORIAS = [
    ("Granizados", "Granizado de café artesanal en tres tamaños"),
    ("Adiciones", "Galletas y dulces para el granizado"),
    ("Bebidas", "Bebidas calientes y frías"),
    ("Postres", "Para acompañar el café"),
]
GRANIZADOS = [
    ("Granizado Pequeño", "Granizado de café artesanal, vaso de 12 oz", 7_000, 12),
    ("Granizado Mediano", "Granizado de café artesanal, vaso de 16 oz", 9_000, 16),
    ("Granizado Grande", "Granizado de café artesanal, vaso de 22 oz", 12_000, 22),
]
ADICIONES = ["Galleta Milo", "Galleta Oreo", "Chokis", "Minichips", "Mr Brown", "Chocorramo",
             "Submarino", "ChocoDisk", "WaferJet", "Pingüinos", "Gol", "Piazza"]
OTROS = [
    ("Café americano", "Bebidas", "Café de origen colombiano, 8 oz", 4_000),
    ("Capuchino caliente", "Bebidas", "Espresso con leche espumada, 10 oz", 6_500),
    ("Agua en botella", "Bebidas", "Agua sin gas, 600 ml", 2_500),
    ("Brownie", "Postres", "Brownie de chocolate con nueces", 5_000),
    ("Torta de chocolate", "Postres", "Porción de torta húmeda de chocolate", 7_500),
]

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
# (nombre, correo, turno). Kevin entró hace 30 días y es el caso sospechoso.
EMPLEADOS = [
    ("Carolina Ríos", None, "manana"),
    ("Jhon Pérez", "jhon.perez@capricho.co", "tarde"),
    ("Marcela Toro", "marcela.toro@capricho.co", "fin"),
    ("Kevin Arias", "kevin.arias@capricho.co", "tarde"),
]
DOMINIOS = ["gmail.com", "hotmail.com", "outlook.com", "correo.co", "yahoo.com"]
METODOS = ["Nequi"] * 7 + ["Tarjeta"] * 5 + ["Daviplata"] * 3 + ["PSE"] * 2 + ["Efectivo"] * 3
METODOS_CAJA = ["Efectivo"] * 9 + ["Tarjeta"] * 5 + ["Nequi"] * 4 + ["Daviplata"] * 2 + ["Transferencia"]
VALORES = [7_000, 9_000, 9_000, 11_000, 12_000, 14_000, 16_000, 18_000, 21_000, 24_000, 27_000, 32_000, 38_000]

# Cada cliente tiene hábitos, como en la realidad: un método de pago que usa
# casi siempre, un tamaño de pedido, un horario y un canal. Es lo que aprende la IA.
MONTOS_PERFIL = {
    "antojo": [7_000, 9_000, 9_000, 11_000, 12_000],
    "combo": [14_000, 16_000, 18_000, 21_000, 24_000],
    "familiar": [27_000, 32_000, 38_000, 45_000],
}
GRANIZADOS_PERFIL = {"antojo": (1, 1), "combo": (1, 2), "familiar": (3, 4)}
HORARIOS_PERFIL = [8, 10, 13, 16, 19]

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
MOTIVOS_DESCUENTO = ["Cliente frecuente", "Cortesía de la casa", "Cumpleaños del cliente"]
MOTIVOS_KEVIN = ["Cortesía", "Amigo de la casa", "Cliente frecuente", "Promoción"]
MOTIVOS_ANULACION = ["Error al digitar el pedido", "El cliente cambió el pedido"]
MOTIVOS_ANULACION_KEVIN = ["El cliente se arrepintió", "Pedido duplicado", "Devolución del dinero"]

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


# =============================================================================
#  Datos base: reglas, categorías, ítems y cuentas
# =============================================================================

def sembrar_base(db, config, stock=STOCK_INICIAL):
    """Lo mínimo para que la tienda funcione."""
    creado = a_texto(ahora().replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=90))
    detector.guardar_reglas(db, detector.REGLAS_POR_DEFECTO, confirmar=False)

    categoria_id = {}
    for nombre, descripcion in CATEGORIAS:
        cursor = db.execute(
            """INSERT INTO categorias (nombre, clave, descripcion, activo, fecha_creacion, fecha_actualizacion)
               VALUES (?, ?, ?, 1, ?, ?)""", (nombre, normalizacion.clave(nombre), descripcion, creado, creado))
        categoria_id[nombre] = cursor.lastrowid

    productos = [(n, d, "Granizados", "GRANIZADO", p, o, "menu.jpg", 40) for n, d, p, o in GRANIZADOS]
    productos += [(n, "Adición para tu granizado", "Adiciones", "ADICION", 2_000, None, None, 30) for n in ADICIONES]
    productos += [(n, d, c, "OTRO", p, None, None, 15) for n, c, d, p in OTROS]
    for nombre, descripcion, categoria, tipo, precio, onzas, imagen, minimo in productos:
        cursor = db.execute(
            """INSERT INTO productos (nombre, descripcion, categoria_id, tipo, precio, onzas, imagen, stock, stock_minimo,
                                      activo, fecha_creacion, fecha_actualizacion)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?)""",
            (nombre, descripcion, categoria_id[categoria], tipo, precio, onzas, imagen, stock, minimo, creado, creado))
        db.execute("""INSERT INTO movimientos_inventario (producto_id, cantidad, motivo, fecha)
                      VALUES (?, ?, 'ENTRADA', ?)""", (cursor.lastrowid, stock, creado))

    cuentas = [
        ("Administrador Capricho", config["ADMIN_EMAIL"], "3000000000", config["ADMIN_PASSWORD"], "ADMIN"),
        ("Valentina Restrepo", config["CLIENTE_DEMO_EMAIL"], "3001234567", config["CLIENTE_DEMO_PASSWORD"], "CLIENTE"),
        ("Consumidor Final", pedidos.CONSUMIDOR_FINAL, None, None, "CLIENTE"),
    ]
    for posicion, (nombre, email, _turno) in enumerate(EMPLEADOS):
        cuentas.append((nombre, email or config["EMPLEADO_DEMO_EMAIL"], f"31000000{posicion:02d}",
                        config["EMPLEADO_DEMO_PASSWORD"], "EMPLEADO"))
    for nombre, email, telefono, password, rol in cuentas:
        db.execute(
            """INSERT INTO usuarios (nombre, email, telefono, password_hash, rol, fecha_creacion, fecha_actualizacion)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (nombre, email, telefono, hashear_password(password) if password else None, rol, creado, creado))
    db.commit()


# =============================================================================
#  Historia completa
# =============================================================================

class _Historia:
    """Arma la lista de eventos de 9 semanas y los ejecuta en orden cronológico."""

    def __init__(self, db, estado, config):
        self.db, self.estado, self.config = db, estado, config
        self.rng = random.Random(42)
        self.momento_actual = ahora()
        self.hoy = self.momento_actual.replace(hour=0, minute=0, second=0, microsecond=0)
        self.creado = a_texto(self.hoy - timedelta(days=90))
        self.comprobantes_usados = []
        self.productos = catalogo.listar(db)
        self.por_tipo = {t: [p for p in self.productos if p["tipo"] == t] for t in ("GRANIZADO", "ADICION", "OTRO")}
        self.empleados = {fila["nombre"]: dict(fila) for fila in db.execute(
            "SELECT id, nombre, email FROM usuarios WHERE rol = 'EMPLEADO'")}

    # --- clientes con hábitos --------------------------------------------------
    def crear_clientes(self):
        rng = self.rng
        correos = [self.config["CLIENTE_DEMO_EMAIL"]]
        for nombre, apellido in CLIENTES:
            email = f"{_sin_tildes(nombre)}.{_sin_tildes(apellido)}@{rng.choice(DOMINIOS)}".lower()
            telefono = "3" + "".join(str(rng.randrange(10)) for _ in range(9))
            self.db.execute(
                """INSERT INTO usuarios (nombre, email, telefono, fecha_creacion, fecha_actualizacion)
                   VALUES (?, ?, ?, ?, ?)""", (f"{nombre} {apellido}", email, telefono, self.creado, self.creado))
            correos.append(email)
        self.correos = correos
        self.usuarios = {f["email"]: dict(f) for f in self.db.execute("SELECT id, nombre, email FROM usuarios")}
        self.perfiles = {}
        for email in correos:
            tamano = rng.choices(list(MONTOS_PERFIL), weights=[5, 4, 2])[0]
            self.perfiles[email] = {
                "metodo": rng.choice(METODOS), "tamano": tamano, "montos": MONTOS_PERFIL[tamano],
                "hora": rng.choice(HORARIOS_PERFIL), "canal": rng.choice(["WEB", "WEB", "APP"]),
                "domicilio": rng.random() < 0.65, "barrio": rng.choice([b for b in domicilios.BARRIOS
                                                                        if b != domicilios.TIENDA]),
            }
        self.estado.reconstruir(self.db)

    def hora_habitual(self, email):
        perfil = self.perfiles[email]
        if self.rng.random() < 0.85:
            return min(22, max(6, round(self.rng.gauss(perfil["hora"], 1.5))))
        return _pesos(self.rng, HORAS_NORMALES)

    # --- armar pedidos --------------------------------------------------------
    def items_granizado(self, cuantos):
        rng = self.rng
        items = []
        for _ in range(cuantos):
            extras = rng.sample(self.por_tipo["ADICION"], rng.choice([0, 1, 1, 2]))
            items.append({"producto_id": rng.choice(self.por_tipo["GRANIZADO"])["id"],
                          "sabor": rng.choice(catalogo.SABORES), "cantidad": 1,
                          "adiciones": sorted(a["id"] for a in extras), "precio_unitario": None})
        return items

    def items_caja(self):
        rng = self.rng
        items = self.items_granizado(rng.choice([0, 1, 1, 1, 2]))
        for producto in rng.sample(self.por_tipo["OTRO"], rng.choice([0, 0, 1, 1, 2])):
            items.append({"producto_id": producto["id"], "sabor": None, "cantidad": rng.choice([1, 1, 2]),
                          "adiciones": []})
        return items or self.items_granizado(1)

    def entrega(self, email, forzar=None):
        perfil = self.perfiles.get(email)
        domicilio = forzar if forzar is not None else (perfil["domicilio"] if perfil else False)
        if not domicilio:
            return {"tipo_entrega": "RECOGER", "barrio": None, "direccion": None}
        rng = self.rng
        return {"tipo_entrega": "DOMICILIO", "barrio": perfil["barrio"] if perfil else rng.choice(domicilios.BARRIOS[1:]),
                "direccion": f"Calle {rng.randint(30, 110)} # {rng.randint(20, 80)}-{rng.randint(10, 99)}"}

    # --- generar eventos ------------------------------------------------------
    def empleado_de_turno(self, dia, hora, dias_atras):
        if dia.weekday() >= 5:
            return "Marcela Toro"
        if hora < 13:
            return "Carolina Ríos"
        if dias_atras < 30 and dia.weekday() in (1, 3, 4) and self.rng.random() < 0.7:
            return "Kevin Arias"
        return "Jhon Pérez"

    def eventos(self):
        rng = self.rng
        eventos = []
        for dias_atras in range(DIAS_DE_HISTORIA - 1, -1, -1):
            dia = self.hoy - timedelta(days=dias_atras)
            fin = dia.weekday() >= 5
            if dia.weekday() == 0:
                eventos.append(("reposicion", dia + timedelta(hours=6), {}))
            for _ in range(rng.randint(12, 20) + (5 if fin else 0)):          # web y app
                email = rng.choice(self.correos)
                eventos.append(("web", _instante(rng, dia, self.hora_habitual(email)), {"email": email}))
            for _ in range(rng.randint(10, 18) + (8 if fin else 0)):          # caja presencial
                hora = _pesos(rng, HORAS_NORMALES)
                eventos.append(("caja", _instante(rng, dia, hora),
                                {"empleado": self.empleado_de_turno(dia, hora, dias_atras), "dias_atras": dias_atras}))
            for _ in range(rng.randint(2, 6)):                                # domicilio por teléfono
                hora = _pesos(rng, HORAS_NORMALES)
                eventos.append(("domicilio", _instante(rng, dia, hora),
                                {"empleado": self.empleado_de_turno(dia, hora, dias_atras), "dias_atras": dias_atras,
                                 "email": rng.choice(self.correos[1:])}))
            for _ in range(rng.randint(8, 14)):                               # pasarela (API), compras normales
                email = rng.choice(self.correos)
                perfil = self.perfiles[email]
                eventos.append(("api", _instante(rng, dia, self.hora_habitual(email)), {
                    "email": email,
                    "valor": rng.choice(perfil["montos"]) if rng.random() < 0.85 else rng.choice(VALORES),
                    "metodo": perfil["metodo"] if rng.random() < 0.8 else rng.choice(METODOS)}))
            eventos += self.ataques_pasarela(dia)
        return [e for e in eventos if e[1] <= self.momento_actual - timedelta(minutes=5)]

    def ataques_pasarela(self, dia):
        """Los ataques de la primera entrega, para el dashboard antifraude."""
        rng = self.rng
        eventos = []
        if rng.random() < 0.75:                                  # 3 o 4 en la ventana
            inicio = _instante(rng, dia, _pesos(rng, HORAS_FRAUDE))
            usuario = rng.choice(self.correos)
            for n in range(rng.choice([3, 3, 3, 4])):
                eventos.append(("api", inicio + timedelta(seconds=n * rng.uniform(0.35, 0.85)),
                                {"email": usuario, "valor": rng.choice(VALORES), "metodo": rng.choice(METODOS)}))
        if rng.random() < 0.2:                                   # ráfaga: 5 o 6 en menos de 1 s
            inicio = _instante(rng, dia, _pesos(rng, HORAS_FRAUDE))
            usuario = rng.choice(self.correos)
            for n in range(rng.choice([5, 6])):
                eventos.append(("api", inicio + timedelta(milliseconds=n * rng.randint(110, 170)),
                                {"email": usuario, "valor": rng.choice(VALORES), "metodo": rng.choice(METODOS)}))
        if rng.random() < 0.3:                                   # alguien alteró el valor
            eventos.append(("api", _instante(rng, dia, _pesos(rng, HORAS_FRAUDE)),
                            {"email": rng.choice(self.correos), "valor": rng.choice(VALORES),
                             "metodo": rng.choice(METODOS), "alterado": True}))
        if rng.random() < 0.22:                                  # monto atípico
            eventos.append(("api", _instante(rng, dia, _pesos(rng, HORAS_FRAUDE)),
                            {"email": rng.choice(self.correos), "valor": rng.randrange(320, 1500) * 1000,
                             "metodo": rng.choice(METODOS)}))
        # Fraude silencioso: ninguna regla lo ve. Para entrenar la IA se siembra
        # SIN estos casos (histórico revisado); la demo sí los trae.
        if rng.random() < 0.12 and self.config.get("SEMBRAR_FRAUDES_SILENCIOSOS", True):
            victima = rng.choice(self.correos)
            otro = rng.choice([m for m in sorted(set(METODOS)) if m != self.perfiles[victima]["metodo"]])
            eventos.append(("api", _instante(rng, dia, rng.choice([1, 2, 3, 4])),
                            {"email": victima, "valor": rng.randrange(150, 290) * 1000, "metodo": otro}))
        if rng.random() < 0.1:                                   # precio manipulado en la tienda
            eventos.append(("precio", _instante(rng, dia, _pesos(rng, HORAS_NORMALES)),
                            {"email": rng.choice(self.correos), "valor": rng.choice([2_000, 3_000, 5_000])}))
        return eventos

    # --- ejecutar ---------------------------------------------------------------
    def ejecutar(self, eventos):
        eventos = merge_sort(eventos, clave=lambda e: e[1])          # orden cronológico
        for numero, (tipo, instante, datos) in enumerate(eventos, start=1):
            try:
                getattr(self, f"_{tipo}")(numero, instante, datos)
            except ErrorApi:
                continue          # sin inventario o datos que el sistema rechaza: igual que en la realidad

    def _reposicion(self, _numero, instante, _datos):
        momento = a_texto(instante)
        for fila in self.db.execute("SELECT id, stock FROM productos").fetchall():
            if fila["stock"] < STOCK_INICIAL:
                self.db.execute("UPDATE productos SET stock = ? WHERE id = ?", (STOCK_INICIAL, fila["id"]))
                self.db.execute("""INSERT INTO movimientos_inventario (producto_id, cantidad, motivo, fecha)
                                   VALUES (?, ?, 'ENTRADA', ?)""", (fila["id"], STOCK_INICIAL - fila["stock"], momento))
        self.db.commit()

    def _web(self, _numero, instante, datos):
        email = datos["email"]
        perfil = self.perfiles[email]
        minimo, maximo = GRANIZADOS_PERFIL[perfil["tamano"]]
        pedido = {"items": self.items_granizado(self.rng.randint(minimo, maximo)), **self.entrega(email),
                  "metodo_pago": perfil["metodo"] if self.rng.random() < 0.8 else self.rng.choice(METODOS[:-3])}
        pedido["total"] = pedidos.cotizar_pedido(self.db, pedido)[3]
        pedidos.crear(self.db, self.estado, self.config, self.usuarios[email], pedido, momento=instante,
                      canal=perfil["canal"], demo=True)

    def _caja(self, _numero, instante, datos, canal="PRESENCIAL", email=None):
        rng = self.rng
        empleado = self.empleados[datos["empleado"]]
        kevin = datos["empleado"] == "Kevin Arias" and datos["dias_atras"] < 10
        if kevin and rng.random() < 0.55:
            porcentaje, motivo = rng.choice([20, 25, 30, 40, 50]), rng.choice(MOTIVOS_KEVIN)
        elif rng.random() < 0.06:
            porcentaje, motivo = 10, rng.choice(MOTIVOS_DESCUENTO)
        else:
            porcentaje, motivo = 0, None
        if email is None and rng.random() < 0.3:
            email = rng.choice(self.correos)
        pedido = {"items": self.items_caja(), "canal": canal, **self.entrega(email, forzar=canal == "DOMICILIO"),
                  "metodo_pago": rng.choice(METODOS_CAJA), "cliente_email": email,
                  "descuento_porcentaje": porcentaje, "motivo_descuento": motivo}
        resultado = pedidos.crear_en_caja(self.db, self.estado, self.config, empleado, pedido, momento=instante, demo=True)
        factura = resultado["factura"]
        pago = instante + timedelta(minutes=rng.randint(1, 4))
        self.pagar(factura, pedido["metodo_pago"], empleado, pago)
        anula = (kevin and rng.random() < 0.3) or rng.random() < 0.02
        if anula:
            motivo = rng.choice(MOTIVOS_ANULACION_KEVIN if kevin else MOTIVOS_ANULACION)
            facturacion.anular(self.db, self.estado, factura["id"], motivo, empleado,
                               momento=pago + timedelta(minutes=rng.randint(10, 90)), demo=True)

    def _domicilio(self, numero, instante, datos):
        self._caja(numero, instante, datos, canal="DOMICILIO", email=datos["email"])

    def pagar(self, factura, metodo, empleado, momento):
        """Pago en caja; los de transferencia llevan comprobante y algunos son trampas."""
        rng = self.rng
        monto = factura["total"]
        archivo = None
        if metodo in pagos.METODOS_CON_COMPROBANTE:
            caso = rng.random()
            if caso < 0.04 and self.comprobantes_usados:                  # el mismo comprobante otra vez
                archivo = rng.choice(self.comprobantes_usados)
            else:
                llave = self.config["LLAVE_HMAC"]
                monto_comprobante = monto
                if caso < 0.07:
                    llave = b"llave-de-un-falsificador"                    # comprobante falso
                elif caso < 0.09:
                    monto_comprobante = max(1_000, monto - rng.choice([5_000, 10_000]))   # no coincide
                datos = {"referencia": f"{metodo[:3].upper()}{rng.randrange(10 ** 9):09d}", "metodo": metodo,
                         "monto": monto_comprobante, "fecha": a_texto(momento)[:19], "pagador": factura["cliente"]}
                archivo = (comprobantes.generar_pdf(datos, llave), f"comprobante-{datos['referencia']}.pdf")
                if len(self.comprobantes_usados) < 40:
                    self.comprobantes_usados.append(archivo)
        pagos.registrar(self.db, self.estado, self.config, factura["id"], {"metodo": metodo, "monto": monto},
                        archivo, quien=empleado, momento=momento, origen="DEMO", demo=True)

    def _api(self, numero, instante, datos):
        txn = {"id_txn": str(100000 + numero), "email": datos["email"], "fecha": instante,
               "valor": datos["valor"], "metodo_pago": datos["metodo"]}
        externo = {"idTxn": txn["id_txn"], "user": txn["email"], "date": a_texto(instante),
                   "value": txn["valor"], "paymentMethod": txn["metodo_pago"]}
        txn["hash"] = firmar_transaccion(externo, self.config["LLAVE_HMAC"])
        txn["hash_valido"] = True
        if datos.get("alterado"):
            txn["valor"] = datos["valor"] * 10         # llegó un valor distinto al firmado
            txn["hash_valido"] = False
        detector.procesar_transaccion(self.db, self.estado, txn, origen="DEMO", llegada=instante, canal="API",
                                      confirmar=False)

    def _precio(self, _numero, instante, datos):
        rng = self.rng
        real = rng.choice([9_000, 12_000, 16_000, 21_000])
        anomalia = detector._anomalia(
            "PRECIO_MANIPULADO", "ALTO", 1, 0,
            f"El navegador envió un total de {detector.dinero(datos['valor'])} y el servidor calculó "
            f"{detector.dinero(real)}. Se alteró el precio en el localStorage.")
        txn = {"id_txn": f"CAP-{instante:%Y%m%d%H%M%S}-{rng.randrange(16 ** 6):06X}", "email": datos["email"],
               "fecha": instante, "valor": datos["valor"], "metodo_pago": rng.choice(METODOS), "hash_valido": True}
        txn["hash"] = firmar_transaccion(detector._formato_externo(txn), self.config["LLAVE_HMAC"])
        usuario_id, _ = self.estado.indice_usuarios.buscar(datos["email"])
        detector._guardar(self.db, self.estado, usuario_id, txn, "RECHAZADA", [anomalia], "DEMO", None, instante, "WEB")


def sembrar(db, estado, config):
    """Datos base + 9 semanas de operación pasadas por los mismos servicios de la API."""
    sembrar_base(db, config)
    historia = _Historia(db, estado, config)
    historia.crear_clientes()
    historia.ejecutar(historia.eventos())
    db.commit()
    _avanzar_pedidos(db, historia.momento_actual)
    _revisar_anomalias(db, historia.rng, historia.momento_actual, config["ADMIN_EMAIL"])
    _revisar_alertas(db, historia.rng, historia.momento_actual)
    _eventos(db, historia.rng, historia.hoy, historia.momento_actual)
    _datos_sucios(db, historia.creado)
    db.commit()
    estado.reconstruir(db)


def _sin_tildes(texto):
    return texto.translate(str.maketrans("áéíóúÁÉÍÓÚñÑ", "aeiouAEIOUnN"))


def _avanzar_pedidos(db, momento_actual):
    """Los pedidos viejos ya se entregaron; los 5 más recientes siguen en proceso o en la cola."""
    filas = db.execute("SELECT id, fecha_creacion FROM pedidos WHERE estado = 'SOLICITADO' ORDER BY fecha_creacion, id"
                       ).fetchall()
    for posicion, fila in enumerate(filas):
        restantes = len(filas) - posicion
        instante = desde_texto(fila["fecha_creacion"])
        if restantes > 5:
            nuevo, cuando = "ENTREGADO", instante + timedelta(minutes=35)
        elif restantes == 5:
            nuevo, cuando = "EN_PROCESO", instante + timedelta(minutes=10)
        else:
            continue                          # se quedan SOLICITADOS, en la cola
        db.execute("UPDATE pedidos SET estado = ?, fecha_actualizacion = ? WHERE id = ?",
                   (nuevo, a_texto(min(cuando, momento_actual)), fila["id"]))
    # Lo que quedó pendiente de pago hace más de un día no se va a pagar: se cancela.
    db.execute("UPDATE pedidos SET estado = 'RECHAZADO' WHERE estado = 'PENDIENTE_PAGO' AND fecha_creacion < ?",
               (a_texto(momento_actual - timedelta(days=1)),))


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


def _revisar_alertas(db, rng, momento_actual):
    """Las alertas de hace más de 3 días ya las revisó el administrador."""
    limite = a_texto(momento_actual - timedelta(days=3))
    for fila in db.execute("SELECT id FROM alertas WHERE fecha < ?", (limite,)).fetchall():
        db.execute("UPDATE alertas SET estado = ? WHERE id = ?",
                   (rng.choices(["REVISADA", "DESCARTADA"], weights=[70, 30])[0], fila["id"]))


def _eventos(db, rng, hoy, momento_actual):
    for numero in range(26):
        tipo, nivel, metodo, ruta, campo, texto = rng.choice(EVENTOS)
        cuando = min(_instante(rng, hoy - timedelta(days=rng.randint(0, 20)), _pesos(rng, HORAS_FRAUDE)),
                     momento_actual - timedelta(minutes=rng.randint(10, 600)))
        detalle = f"{campo}: {texto}" if campo else texto
        db.execute(
            """INSERT INTO eventos (tipo, nivel, detalle, ruta, metodo, ip, email, atendido, fecha, demo)
               VALUES (?, ?, ?, ?, ?, ?, NULL, ?, ?, 1)""",
            (tipo, nivel, detalle, ruta, metodo, f"181.{rng.randint(50, 60)}.{rng.randint(0, 255)}.{rng.randint(1, 254)}",
             1 if numero < 19 else 0, a_texto(cuando)))


def _datos_sucios(db, creado):
    """Lo que encuentra cualquier negocio real en su base de datos: la
    auditoría de calidad (servicios/calidad.py) debe encontrar cada caso."""
    clientes = [
        ("laura  gomez", "Laura.Gomez@Gmail.com", "+57 300 555 1212"),          # duplicado de un cliente sembrado
        ("SANTIAGO RESTREPO", "santiago.r@hotmail.com", "300-555-3434"),        # mismo nombre, otro correo
        ("Ana María Ríos", "ana.rios@correo.co", "3005556789"),
        ("Ana Maria Rios", "anamaria.rios@gmail.com", "300 555 6789"),          # mismo celular escrito distinto
        ("Pedro Pablo Gil", "pedro.gil@correo.co", "12345"),                    # celular inválido
    ]
    for nombre, email, telefono in clientes:
        db.execute("""INSERT INTO usuarios (nombre, email, telefono, fecha_creacion, fecha_actualizacion)
                      VALUES (?, ?, ?, ?, ?)""", (nombre, email, telefono, creado, creado))
    adiciones = db.execute("SELECT id FROM categorias WHERE clave = 'adicion'").fetchone()["id"]
    postres = db.execute("SELECT id FROM categorias WHERE clave = 'postre'").fetchone()["id"]
    for nombre, categoria, precio in (("galleta  oreo", adiciones, 2_000),           # ítem repetido
                                      ("Torta de zanahoria", postres, 75_000)):      # un cero de más
        db.execute(
            """INSERT INTO productos (nombre, descripcion, categoria_id, tipo, precio, stock, stock_minimo, activo,
                                      fecha_creacion, fecha_actualizacion)
               VALUES (?, 'Registrado a mano', ?, 'OTRO', ?, 0, 0, 0, ?, ?)""", (nombre, categoria, precio, creado, creado))
    # El primer cliente sembrado comparte celular con su duplicado.
    db.execute("UPDATE usuarios SET telefono = '3005551212' WHERE email LIKE 'laura.gomez@%' AND email != 'Laura.Gomez@Gmail.com'")
