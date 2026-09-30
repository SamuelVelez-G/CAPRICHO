-- ============================================================================
--  Capricho — esquema de la base de datos (SQLite)
--  Las tablas usuarios, transacciones y anomalias siguen el modelo de la
--  diapositiva 45. El resto soporta la tienda, la cola y la bitácora.
-- ============================================================================

CREATE TABLE IF NOT EXISTS usuarios (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre              TEXT    NOT NULL,
    email               TEXT    NOT NULL UNIQUE,
    telefono            TEXT,
    password_hash       TEXT,              -- NULL: llegó solo por una transacción externa
    rol                 TEXT    NOT NULL DEFAULT 'CLIENTE' CHECK (rol IN ('CLIENTE', 'ADMIN')),
    estado              TEXT    NOT NULL DEFAULT 'ACTIVO'  CHECK (estado IN ('ACTIVO', 'EN_OBSERVACION', 'BLOQUEADO')),
    fecha_creacion      TEXT    NOT NULL,
    fecha_actualizacion TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS transacciones (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    id_txn              TEXT    NOT NULL UNIQUE,        -- idTxn que envía el emisor
    usuario_id          INTEGER NOT NULL REFERENCES usuarios(id),
    valor               REAL    NOT NULL CHECK (valor > 0),
    fecha_txn           TEXT    NOT NULL,               -- cuándo ocurrió según el emisor
    estado              TEXT    NOT NULL CHECK (estado IN ('APROBADA', 'SOSPECHOSA', 'RECHAZADA')),
    hash                TEXT    NOT NULL,
    hash_valido         INTEGER NOT NULL CHECK (hash_valido IN (0, 1)),
    metodo_pago         TEXT    NOT NULL,
    origen              TEXT    NOT NULL CHECK (origen IN ('API', 'LOTE', 'TIENDA', 'DEMO')),
    ip                  TEXT,
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

CREATE TABLE IF NOT EXISTS productos (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre              TEXT    NOT NULL UNIQUE,
    descripcion         TEXT    NOT NULL,
    categoria           TEXT    NOT NULL CHECK (categoria IN ('GRANIZADO', 'ADICION')),
    precio              INTEGER NOT NULL CHECK (precio > 0),
    onzas               INTEGER,
    imagen              TEXT,
    activo              INTEGER NOT NULL DEFAULT 1 CHECK (activo IN (0, 1)),
    fecha_creacion      TEXT    NOT NULL,
    fecha_actualizacion TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS pedidos (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    usuario_id          INTEGER NOT NULL REFERENCES usuarios(id),
    transaccion_id      INTEGER REFERENCES transacciones(id),
    estado              TEXT    NOT NULL CHECK (estado IN ('SOLICITADO', 'EN_PROCESO', 'ENTREGADO', 'RECHAZADO')),
    tipo_entrega        TEXT    NOT NULL CHECK (tipo_entrega IN ('DOMICILIO', 'RECOGER')),
    barrio              TEXT,
    direccion           TEXT,
    ruta                TEXT,               -- JSON con la ruta de Dijkstra
    distancia_km        REAL    NOT NULL DEFAULT 0,
    subtotal            INTEGER NOT NULL,
    domicilio           INTEGER NOT NULL,
    total               INTEGER NOT NULL,
    metodo_pago         TEXT    NOT NULL,
    fecha_creacion      TEXT    NOT NULL,
    fecha_actualizacion TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_pedido_usuario ON pedidos (usuario_id);
CREATE INDEX IF NOT EXISTS idx_pedido_estado  ON pedidos (estado);

CREATE TABLE IF NOT EXISTS pedido_items (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    pedido_id       INTEGER NOT NULL REFERENCES pedidos(id),
    producto_id     INTEGER NOT NULL REFERENCES productos(id),
    nombre          TEXT    NOT NULL,
    sabor           TEXT    NOT NULL,
    adiciones       TEXT    NOT NULL,       -- JSON: [{"id", "nombre", "precio"}]
    cantidad        INTEGER NOT NULL CHECK (cantidad > 0),
    precio_unitario INTEGER NOT NULL,       -- el que calculó el SERVIDOR
    subtotal        INTEGER NOT NULL
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
    fecha       TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_evento_fecha ON eventos (fecha);

CREATE TABLE IF NOT EXISTS configuracion (
    clave               TEXT PRIMARY KEY,
    valor               TEXT NOT NULL,      -- JSON
    fecha_actualizacion TEXT NOT NULL
);
