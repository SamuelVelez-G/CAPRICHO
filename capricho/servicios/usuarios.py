"""Registro, inicio de sesión y búsqueda de usuarios por correo."""

from ..errores import ErrorConflicto, ErrorLimite, ErrorNoAutenticado
from ..registro import logger, registrar_evento
from ..seguridad import HASH_DE_RELLENO, hashear_password, verificar_password
from ..tiempo import a_texto, ahora


def _nombre_desde_email(email: str) -> str:
    """laura.gomez@correo.co -> Laura Gomez (para usuarios que llegan por la API)."""
    local = email.split("@")[0].replace(".", " ").replace("_", " ").replace("-", " ")
    return " ".join(parte.capitalize() for parte in local.split()) or email


def obtener_o_crear_por_email(db, estado, email, momento=None):
    """Busca al usuario en el índice hash (O(1)); si no existe lo crea."""
    usuario_id, _ = estado.indice_usuarios.buscar(email)
    if usuario_id is not None:
        return usuario_id
    momento = a_texto(momento or ahora())
    cursor = db.execute(
        """INSERT INTO usuarios (nombre, email, fecha_creacion, fecha_actualizacion)
           VALUES (?, ?, ?, ?)""",
        (_nombre_desde_email(email), email, momento, momento),
    )
    estado.indice_usuarios.agregar(email, cursor.lastrowid)
    return cursor.lastrowid


def registrar_cliente(db, estado, datos):
    existente = db.execute(
        "SELECT id, password_hash FROM usuarios WHERE email = ?", (datos["email"],)
    ).fetchone()
    momento = a_texto(ahora())
    password_hash = hashear_password(datos["password"])

    if existente and existente["password_hash"]:
        raise ErrorConflicto("Ya existe una cuenta con ese correo", {"email": "Este correo ya está registrado"})

    if existente:
        # Ya había pagado por la API sin cuenta: se completa su registro.
        db.execute(
            """UPDATE usuarios SET nombre = ?, telefono = ?, password_hash = ?, fecha_actualizacion = ?
               WHERE id = ?""",
            (datos["nombre"], datos["telefono"], password_hash, momento, existente["id"]),
        )
        usuario_id = existente["id"]
    else:
        cursor = db.execute(
            """INSERT INTO usuarios (nombre, email, telefono, password_hash, fecha_creacion, fecha_actualizacion)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (datos["nombre"], datos["email"], datos["telefono"], password_hash, momento, momento),
        )
        usuario_id = cursor.lastrowid
        estado.indice_usuarios.agregar(datos["email"], usuario_id)
    db.commit()
    logger.info("Cliente registrado #%s %s", usuario_id, datos["email"])
    return {"id": usuario_id, "nombre": datos["nombre"], "email": datos["email"], "rol": "CLIENTE"}


def autenticar(db, estado, email, password, ip):
    clave_limite = f"{email}|{ip}"
    if estado.limitador_login.cantidad(clave_limite) >= estado.limitador_login.maximo:
        raise ErrorLimite("Demasiados intentos fallidos. Espera 5 minutos e inténtalo de nuevo.")

    fila = db.execute(
        "SELECT id, nombre, email, rol, password_hash FROM usuarios WHERE email = ?", (email,)
    ).fetchone()

    # Si el correo no existe igual se verifica contra un hash de relleno,
    # para que la respuesta tarde lo mismo y no revele qué correos existen.
    almacenado = fila["password_hash"] if fila and fila["password_hash"] else HASH_DE_RELLENO
    correcto = verificar_password(password, almacenado) and fila is not None and fila["password_hash"]

    if not correcto:
        estado.limitador_login.registrar(clave_limite)
        registrar_evento(db, estado, "LOGIN_FALLIDO", "MEDIO",
                         f"Intento fallido de inicio de sesión para {email}",
                         ruta="/api/auth/login", metodo="POST", ip=ip, email=email)
        raise ErrorNoAutenticado("Correo o contraseña incorrectos")

    estado.limitador_login.limpiar(clave_limite)
    logger.info("Inicio de sesión de %s (%s)", email, fila["rol"])
    return {"id": fila["id"], "nombre": fila["nombre"], "email": fila["email"], "rol": fila["rol"]}
