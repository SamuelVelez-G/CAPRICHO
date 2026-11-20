"""Registro, inicio de sesión, búsqueda por correo y CRUD de usuarios con roles.

Roles: ADMIN (todo), EMPLEADO (caja: pedidos, facturas y pagos) y CLIENTE.
"""

from ..db import fila_a_dict, filas_a_dicts
from ..errores import ErrorConflicto, ErrorLimite, ErrorNoAutenticado, ErrorNoEncontrado, ErrorValidacion
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
        "SELECT id, nombre, email, rol, estado, password_hash FROM usuarios WHERE email = ?", (email,)
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

    if fila["estado"] in ("INACTIVO", "BLOQUEADO"):
        raise ErrorNoAutenticado(f"La cuenta está {fila['estado'].lower()}. Habla con el administrador.")
    estado.limitador_login.limpiar(clave_limite)
    logger.info("Inicio de sesión de %s (%s)", email, fila["rol"])
    return {"id": fila["id"], "nombre": fila["nombre"], "email": fila["email"], "rol": fila["rol"]}


# =============================================================================
#  CRUD de usuarios (administrador)
# =============================================================================

COLUMNAS = """u.id, u.nombre, u.email, u.telefono, u.rol, u.estado, u.fecha_creacion, u.fecha_actualizacion,
              u.password_hash IS NOT NULL AS puede_ingresar"""


def listar(db, rol=None, busqueda=None, pagina=1, por_pagina=25):
    condiciones, parametros = [], []
    if rol:
        condiciones.append("u.rol = ?")
        parametros.append(rol)
    if busqueda:
        condiciones.append("(u.nombre LIKE ? OR u.email LIKE ? OR u.telefono LIKE ?)")
        parametros += [f"%{busqueda}%"] * 3
    donde = (" WHERE " + " AND ".join(condiciones)) if condiciones else ""
    total = db.execute(f"SELECT COUNT(*) FROM usuarios u{donde}", parametros).fetchone()[0]
    filas = filas_a_dicts(db.execute(
        f"""SELECT {COLUMNAS},
                   (SELECT COUNT(*) FROM transacciones t WHERE t.usuario_id = u.id) AS transacciones,
                   (SELECT COUNT(*) FROM pedidos p WHERE p.usuario_id = u.id) AS pedidos
            FROM usuarios u{donde} ORDER BY u.rol, u.nombre LIMIT ? OFFSET ?""",
        (*parametros, por_pagina, (pagina - 1) * por_pagina)))
    for fila in filas:
        fila["puede_ingresar"] = bool(fila["puede_ingresar"])
    return {"usuarios": filas, "total": total, "pagina": pagina, "paginas": max(1, -(-total // por_pagina))}


def obtener(db, usuario_id):
    usuario = fila_a_dict(db.execute(f"SELECT {COLUMNAS} FROM usuarios u WHERE u.id = ?", (usuario_id,)).fetchone())
    if usuario is None:
        raise ErrorNoEncontrado(f"No existe el usuario {usuario_id}")
    usuario["puede_ingresar"] = bool(usuario["puede_ingresar"])
    return usuario


def crear(db, estado, datos):
    if db.execute("SELECT 1 FROM usuarios WHERE email = ?", (datos["email"],)).fetchone():
        raise ErrorConflicto("Ya existe un usuario con ese correo", {"email": "Correo repetido"})
    if datos["rol"] != "CLIENTE" and not datos.get("password"):
        raise ErrorValidacion({"password": "Un empleado o administrador necesita contraseña para ingresar"})
    momento = a_texto(ahora())
    cursor = db.execute(
        """INSERT INTO usuarios (nombre, email, telefono, password_hash, rol, estado, fecha_creacion, fecha_actualizacion)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (datos["nombre"], datos["email"], datos.get("telefono"),
         hashear_password(datos["password"]) if datos.get("password") else None,
         datos["rol"], datos["estado"], momento, momento))
    db.commit()
    estado.indice_usuarios.agregar(datos["email"], cursor.lastrowid)
    logger.info("POST usuario #%s %s (%s)", cursor.lastrowid, datos["email"], datos["rol"])
    return obtener(db, cursor.lastrowid)


def _admins_activos(db, excepto_id):
    return db.execute("SELECT COUNT(*) FROM usuarios WHERE rol = 'ADMIN' AND estado = 'ACTIVO' AND id != ?",
                      (excepto_id,)).fetchone()[0]


def actualizar(db, estado, usuario_id, cambios, quien):
    """PUT y PATCH. El administrador no puede quitarse su propio rol ni dejar
    el sistema sin ningún administrador activo."""
    actual = obtener(db, usuario_id)
    if "email" in cambios and cambios["email"] != actual["email"]:
        if db.execute("SELECT 1 FROM usuarios WHERE email = ? AND id != ?", (cambios["email"], usuario_id)).fetchone():
            raise ErrorConflicto("Ya existe un usuario con ese correo", {"email": "Correo repetido"})
    pierde_admin = actual["rol"] == "ADMIN" and (cambios.get("rol", "ADMIN") != "ADMIN"
                                                 or cambios.get("estado", "ACTIVO") != "ACTIVO")
    if pierde_admin and (usuario_id == quien["id"] or not _admins_activos(db, usuario_id)):
        raise ErrorConflicto("No puedes quitarte el rol de administrador ni dejar el sistema sin administradores")
    columnas = dict(cambios)
    if "password" in columnas:
        password = columnas.pop("password")
        if password:
            columnas["password_hash"] = hashear_password(password)
    if columnas:
        asignaciones = ", ".join(f"{campo} = ?" for campo in columnas)   # nombres de una lista validada
        db.execute(f"UPDATE usuarios SET {asignaciones}, fecha_actualizacion = ? WHERE id = ?",
                   (*columnas.values(), a_texto(ahora()), usuario_id))
        db.commit()
    if "email" in cambios and cambios["email"] != actual["email"]:
        estado.indice_usuarios.quitar(actual["email"])
        estado.indice_usuarios.agregar(cambios["email"], usuario_id)
    logger.info("PATCH usuario #%s campos=%s", usuario_id, list(cambios))
    return obtener(db, usuario_id)


def eliminar(db, estado, usuario_id, quien):
    """Si el usuario tiene historial (transacciones, pedidos, facturas) no se
    borra: se desactiva, para no perder la trazabilidad."""
    usuario = obtener(db, usuario_id)
    if usuario_id == quien["id"]:
        raise ErrorConflicto("No puedes eliminar tu propia cuenta")
    if usuario["rol"] == "ADMIN" and not _admins_activos(db, usuario_id):
        raise ErrorConflicto("Es el último administrador activo")
    historial = db.execute(
        """SELECT (SELECT COUNT(*) FROM transacciones WHERE usuario_id = :id)
                + (SELECT COUNT(*) FROM pedidos WHERE usuario_id = :id OR empleado_id = :id)
                + (SELECT COUNT(*) FROM facturas WHERE empleado_id = :id OR anulada_por = :id)
                + (SELECT COUNT(*) FROM pagos WHERE registrado_por = :id)""", {"id": usuario_id}).fetchone()[0]
    if historial:
        db.execute("UPDATE usuarios SET estado = 'INACTIVO', fecha_actualizacion = ? WHERE id = ?",
                   (a_texto(ahora()), usuario_id))
        db.commit()
        logger.info("Usuario #%s desactivado (tiene %s registros)", usuario_id, historial)
        return {"eliminado": False, "desactivado": True, "registros": historial}
    db.execute("DELETE FROM alertas WHERE usuario_id = ?", (usuario_id,))
    db.execute("DELETE FROM usuarios WHERE id = ?", (usuario_id,))
    db.commit()
    estado.indice_usuarios.quitar(usuario["email"])
    logger.info("DELETE usuario #%s", usuario_id)
    return {"eliminado": True, "desactivado": False, "registros": 0}
