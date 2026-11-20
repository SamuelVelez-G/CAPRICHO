-- ============================================================================
--  Capricho — esquema de la base de datos (SQLite), versión 2
--
--  Operación ....... usuarios (roles), categorias, productos (ítems con
--                    inventario), pedidos, pedido_items, facturas, pagos,
--                    movimientos_inventario
--  Antifraude ...... transacciones, anomalias, anomalias_historial (modelo de
--                    la diapositiva 45), alertas
--  Análisis ........ calidad_reportes, benchmarks
--  Soporte ......... eventos (pila de errores), configuracion
-- ============================================================================

PRAGMA user_version = 2;

CREATE TABLE IF NOT EXISTS usuarios (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre              TEXT    NOT NULL,
    email               TEXT    NOT NULL UNIQUE,
    telefono            TEXT,
    password_hash       TEXT,              -- NULL: llegó solo por una transacción externa
    rol                 TEXT    NOT NULL DEFAULT 'CLIENTE' CHECK (rol IN ('CLIENTE', 'EMPLEADO', 'ADMIN')),
    estado              TEXT    NOT NULL DEFAULT 'ACTIVO'
                                CHECK (estado IN ('ACTIVO', 'EN_OBSERVACION', 'BLOQUEADO', 'INACTIVO')),
    fecha_creacion      TEXT    NOT NULL,
    fecha_actualizacion TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_usuario_telefono ON usuarios (telefono);

CREATE TABLE IF NOT EXISTS categorias (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre              TEXT    NOT NULL,
    clave               TEXT    NOT NULL UNIQUE,        -- nombre normalizado: "Granizados " y "granizados" son la misma
    descripcion         TEXT    NOT NULL DEFAULT '',
    activo              INTEGER NOT NULL DEFAULT 1 CHECK (activo IN (0, 1)),
    fecha_creacion      TEXT    NOT NULL,
    fecha_actualizacion TEXT    NOT NULL
);

-- Ítems del catálogo. "tipo" dice cómo se venden en la tienda: un granizado
-- lleva adiciones; una adición solo acompaña; "OTRO" se vende solo.
CREATE TABLE IF NOT EXISTS productos (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre              TEXT    NOT NULL UNIQUE,
    descripcion         TEXT    NOT NULL,
    categoria_id        INTEGER NOT NULL REFERENCES categorias(id),
    tipo                TEXT    NOT NULL CHECK (tipo IN ('GRANIZADO', 'ADICION', 'OTRO')),
    precio              INTEGER NOT NULL CHECK (precio > 0),
    onzas               INTEGER,
    imagen              TEXT,
    stock               INTEGER NOT NULL DEFAULT 0 CHECK (stock >= 0),
    stock_minimo        INTEGER NOT NULL DEFAULT 0 CHECK (stock_minimo >= 0),
    activo              INTEGER NOT NULL DEFAULT 1 CHECK (activo IN (0, 1)),
    fecha_creacion      TEXT    NOT NULL,
    fecha_actualizacion TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_producto_categoria ON productos (categoria_id);

CREATE TABLE IF NOT EXISTS transacciones (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    id_txn              TEXT    NOT NULL UNIQUE,        -- idTxn que envía el emisor
    usuario_id          INTEGER NOT NULL REFERENCES usuarios(id),
    valor               REAL    NOT NULL CHECK (valor > 0),
    fecha_txn           TEXT    NOT NULL,               -- cuándo ocurrió según el emisor
    estado              TEXT    NOT NULL CHECK (estado IN ('APROBADA', 'SOSPECHOSA', 'RECHAZADA')),
    hash                TEXT    NOT NULL,
    hash_valido         INTEGER NOT NULL CHECK (hash_valido IN (0, 1)),
    firma               TEXT,                           -- cómo se validó el hash
    riesgo_ia           REAL,                           -- 0 a 100 según el autoencoder (NULL sin IA)
    prob_fraude         REAL,                           -- 0 a 1 según el clasificador (NULL sin IA)
    clasificacion       TEXT    CHECK (clasificacion IN ('NORMAL', 'FRAUDULENTA')),
    metodo_pago         TEXT    NOT NULL,
    canal               TEXT,
    origen              TEXT    NOT NULL CHECK (origen IN ('API', 'LOTE', 'TIENDA', 'CAJA', 'VIVO', 'DEMO')),
    ip                  TEXT,
    analisis            TEXT,                           -- JSON: cada paso del análisis (monitor en vivo)
    fecha_creacion      TEXT    NOT NULL,               -- cuándo llegó al servidor
    fecha_actualizacion TEXT    NOT NULL
);
-- La ventana deslizante pregunta "transacciones de ESTE usuario entre dos
-- fechas". Este índice compuesto responde eso sin recorrer la tabla.
CREATE INDEX IF NOT EXISTS idx_txn_usuario_fecha    ON transacciones (usuario_id, fecha_txn);
CREATE INDEX IF NOT EXISTS idx_txn_usuario_llegada  ON transacciones (usuario_id, fecha_creacion);
CREATE INDEX IF NOT EXISTS idx_txn_fecha            ON transacciones (fecha_txn);

CREATE TABLE IF NOT EXISTS anomalias (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    transaccion_id          INTEGER NOT NULL REFERENCES transacciones(id),
    tipo                    TEXT    NOT NULL,
    nivel                   TEXT    NOT NULL CHECK (nivel IN ('BAJO', 'MEDIO', 'ALTO', 'CRITICO')),
    cantidad_transacciones  INTEGER NOT NULL,
    ventana_segundos        REAL    NOT NULL,
    estado                  TEXT    NOT NULL DEFAULT 'NUEVA' CHECK (estado IN ('NUEVA', 'ABIERTA', 'REVISADA', 'DESCARTADA')),
    detalle                 TEXT    NOT NULL,
    fecha_creacion          TEXT    NOT NULL,
    fecha_actualizacion     TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_anomalia_txn   ON anomalias (transaccion_id);
CREATE INDEX IF NOT EXISTS idx_anomalia_fecha ON anomalias (fecha_creacion);

-- Línea de tiempo de cada anomalía: quién la movió de estado y cuándo.
CREATE TABLE IF NOT EXISTS anomalias_historial (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    anomalia_id     INTEGER NOT NULL REFERENCES anomalias(id),
    estado_anterior TEXT,
    estado_nuevo    TEXT    NOT NULL,
    nota            TEXT    NOT NULL,
    responsable     TEXT    NOT NULL,
    fecha           TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_historial_anomalia ON anomalias_historial (anomalia_id);

-- Pedidos de cualquier canal. El empleado es quien lo tomó en caja (NULL en la web).
CREATE TABLE IF NOT EXISTS pedidos (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    usuario_id          INTEGER NOT NULL REFERENCES usuarios(id),
    empleado_id         INTEGER REFERENCES usuarios(id),
    transaccion_id      INTEGER REFERENCES transacciones(id),
    canal               TEXT    NOT NULL DEFAULT 'WEB' CHECK (canal IN ('PRESENCIAL', 'WEB', 'APP', 'DOMICILIO')),
    estado              TEXT    NOT NULL CHECK (estado IN ('PENDIENTE_PAGO', 'SOLICITADO', 'EN_PROCESO', 'ENTREGADO',
                                                           'RECHAZADO', 'ANULADO')),
    tipo_entrega        TEXT    NOT NULL CHECK (tipo_entrega IN ('DOMICILIO', 'RECOGER')),
    barrio              TEXT,
    direccion           TEXT,
    ruta                TEXT,               -- JSON con la ruta de Dijkstra
    distancia_km        REAL    NOT NULL DEFAULT 0,
    subtotal            INTEGER NOT NULL,
    domicilio           INTEGER NOT NULL,
    total               INTEGER NOT NULL,
    metodo_pago         TEXT    NOT NULL,
    demo                INTEGER NOT NULL DEFAULT 0 CHECK (demo IN (0, 1)),
    fecha_creacion      TEXT    NOT NULL,
    fecha_actualizacion TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_pedido_usuario ON pedidos (usuario_id);
CREATE INDEX IF NOT EXISTS idx_pedido_estado  ON pedidos (estado);
CREATE INDEX IF NOT EXISTS idx_pedido_fecha   ON pedidos (fecha_creacion);

CREATE TABLE IF NOT EXISTS pedido_items (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    pedido_id       INTEGER NOT NULL REFERENCES pedidos(id),
    producto_id     INTEGER NOT NULL REFERENCES productos(id),
    nombre          TEXT    NOT NULL,
    sabor           TEXT,
    adiciones       TEXT    NOT NULL DEFAULT '[]',   -- JSON: [{"id", "nombre", "precio"}]
    cantidad        INTEGER NOT NULL CHECK (cantidad > 0),
    precio_unitario INTEGER NOT NULL,       -- el que calculó el SERVIDOR
    subtotal        INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_item_pedido   ON pedido_items (pedido_id);
CREATE INDEX IF NOT EXISTS idx_item_producto ON pedido_items (producto_id);

-- Facturas con número consecutivo. "hash" encadena cada factura con la
-- anterior (HMAC-SHA256): si alguien cambia una factura o borra una del
-- medio, la cadena deja de cuadrar desde ese punto.
CREATE TABLE IF NOT EXISTS facturas (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    numero              INTEGER NOT NULL UNIQUE CHECK (numero > 0),
    pedido_id           INTEGER NOT NULL UNIQUE REFERENCES pedidos(id),
    usuario_id          INTEGER NOT NULL REFERENCES usuarios(id),
    empleado_id         INTEGER REFERENCES usuarios(id),
    canal               TEXT    NOT NULL,
    subtotal            INTEGER NOT NULL CHECK (subtotal >= 0),
    descuento           INTEGER NOT NULL DEFAULT 0 CHECK (descuento >= 0),
    motivo_descuento    TEXT,
    domicilio           INTEGER NOT NULL DEFAULT 0 CHECK (domicilio >= 0),
    base                INTEGER NOT NULL,            -- base gravable
    tasa_impuesto       REAL    NOT NULL,            -- impuesto al consumo (incluido en el precio)
    impuesto            INTEGER NOT NULL,
    total               INTEGER NOT NULL CHECK (total >= 0),
    estado              TEXT    NOT NULL CHECK (estado IN ('EMITIDA', 'PAGADA', 'ANULADA')),
    motivo_anulacion    TEXT,
    anulada_por         INTEGER REFERENCES usuarios(id),
    fecha_anulacion     TEXT,
    fecha_emision       TEXT    NOT NULL,
    hash_anterior       TEXT    NOT NULL,
    hash                TEXT    NOT NULL,
    fecha_actualizacion TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_factura_fecha    ON facturas (fecha_emision);
CREATE INDEX IF NOT EXISTS idx_factura_empleado ON facturas (empleado_id);

-- Pagos de una factura. El comprobante se guarda como archivo y aquí queda su
-- SHA-256: si alguien reemplaza el archivo, el hash ya no coincide.
CREATE TABLE IF NOT EXISTS pagos (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    factura_id          INTEGER NOT NULL REFERENCES facturas(id),
    transaccion_id      INTEGER REFERENCES transacciones(id),
    metodo              TEXT    NOT NULL,
    monto               INTEGER NOT NULL CHECK (monto > 0),
    referencia          TEXT    NOT NULL,
    comprobante_nombre  TEXT,
    comprobante_tipo    TEXT,
    comprobante_sha256  TEXT,
    verificacion        TEXT    NOT NULL,            -- VERIFICADO, SIN_VERIFICAR, NO_REQUIERE, FALSO, ...
    detalle_verificacion TEXT,
    estado              TEXT    NOT NULL CHECK (estado IN ('APROBADO', 'PENDIENTE', 'RECHAZADO')),
    registrado_por      INTEGER REFERENCES usuarios(id),
    fecha               TEXT    NOT NULL,
    hash_anterior       TEXT    NOT NULL,
    hash                TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_pago_factura     ON pagos (factura_id);
CREATE INDEX IF NOT EXISTS idx_pago_comprobante ON pagos (comprobante_sha256);
CREATE INDEX IF NOT EXISTS idx_pago_referencia  ON pagos (referencia);

-- Cada entrada o salida de inventario: venta, anulación, ajuste o compra.
CREATE TABLE IF NOT EXISTS movimientos_inventario (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    producto_id INTEGER NOT NULL REFERENCES productos(id),
    cantidad    INTEGER NOT NULL,           -- negativa = sale del inventario
    motivo      TEXT    NOT NULL CHECK (motivo IN ('VENTA', 'ANULACION', 'AJUSTE', 'ENTRADA')),
    pedido_id   INTEGER REFERENCES pedidos(id),
    usuario_id  INTEGER REFERENCES usuarios(id),
    fecha       TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_movimiento_producto ON movimientos_inventario (producto_id, fecha);

-- Alertas que no son de una transacción: estadística por usuario (descuentos,
-- anulaciones), integridad, comprobantes y calidad de datos.
CREATE TABLE IF NOT EXISTS alertas (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    tipo        TEXT    NOT NULL,
    nivel       TEXT    NOT NULL CHECK (nivel IN ('BAJO', 'MEDIO', 'ALTO', 'CRITICO')),
    origen      TEXT    NOT NULL CHECK (origen IN ('ESTADISTICA', 'INTEGRIDAD', 'PAGOS', 'CALIDAD', 'OPERACION')),
    usuario_id  INTEGER REFERENCES usuarios(id),
    entidad     TEXT,
    entidad_id  INTEGER,
    detalle     TEXT    NOT NULL,
    datos       TEXT,                       -- JSON con los números que dispararon la alerta
    estado      TEXT    NOT NULL DEFAULT 'NUEVA' CHECK (estado IN ('NUEVA', 'REVISADA', 'DESCARTADA')),
    demo        INTEGER NOT NULL DEFAULT 0 CHECK (demo IN (0, 1)),
    fecha       TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_alerta_fecha ON alertas (fecha);

CREATE TABLE IF NOT EXISTS calidad_reportes (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    fuente      TEXT    NOT NULL,
    tipo        TEXT    NOT NULL,           -- clientes, items, auditoria
    recibidos   INTEGER NOT NULL,
    validos     INTEGER NOT NULL,
    corregidos  INTEGER NOT NULL,
    duplicados  INTEGER NOT NULL,
    descartados INTEGER NOT NULL,
    puntaje     REAL    NOT NULL,
    detalle     TEXT    NOT NULL,           -- JSON con el reporte completo
    fecha       TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS benchmarks (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    tipo        TEXT    NOT NULL CHECK (tipo IN ('COMPLETO', 'RAPIDO')),
    duracion_s  REAL    NOT NULL,
    equipo      TEXT    NOT NULL,
    resultados  TEXT    NOT NULL,           -- JSON
    fecha       TEXT    NOT NULL
);

-- Bitácora de errores y eventos de seguridad (se muestran como una pila).
CREATE TABLE IF NOT EXISTS eventos (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    tipo        TEXT    NOT NULL,
    nivel       TEXT    NOT NULL CHECK (nivel IN ('BAJO', 'MEDIO', 'ALTO', 'CRITICO')),
    detalle     TEXT    NOT NULL,
    ruta        TEXT,
    metodo      TEXT,
    ip          TEXT,
    email       TEXT,
    atendido    INTEGER NOT NULL DEFAULT 0 CHECK (atendido IN (0, 1)),
    demo        INTEGER NOT NULL DEFAULT 0 CHECK (demo IN (0, 1)),   -- 1 = sembrado por la demo
    fecha       TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_evento_fecha ON eventos (fecha);

CREATE TABLE IF NOT EXISTS configuracion (
    clave               TEXT PRIMARY KEY,
    valor               TEXT NOT NULL,      -- JSON
    fecha_actualizacion TEXT NOT NULL
);
