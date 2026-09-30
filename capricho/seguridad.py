"""
Seguridad de Capricho.

  - Contraseñas con scrypt y sal aleatoria (nunca se guardan en texto plano).
  - Firma HMAC-SHA256 de transacciones (diapositivas 14 a 19).
  - Detección de patrones de inyección SQL.
  - Token CSRF, control de sesión y cabeceras de seguridad.
"""

import hashlib
import hmac
import json
import re
import secrets
from functools import wraps

from flask import current_app, redirect, request, session, url_for

from .errores import ErrorNoAutenticado, ErrorProhibido


# =============================================================================
#  CONTRASEÑAS
# =============================================================================
# ¿Por qué no un SHA-256 simple? Porque SHA-256 es rápido a propósito: un
# atacante con la base de datos puede probar miles de millones de claves por
# segundo. scrypt es lento y consume memoria a propósito, y la sal aleatoria
# hace que dos usuarios con la misma clave tengan hashes distintos.

SCRYPT_N, SCRYPT_R, SCRYPT_P = 2 ** 14, 8, 1


def hashear_password(password: str) -> str:
    sal = secrets.token_bytes(16)
    derivada = hashlib.scrypt(password.encode("utf-8"), salt=sal,
                              n=SCRYPT_N, r=SCRYPT_R, p=SCRYPT_P, dklen=32)
    return f"scrypt${SCRYPT_N}${SCRYPT_R}${SCRYPT_P}${sal.hex()}${derivada.hex()}"


def verificar_password(password: str, almacenado: str) -> bool:
    try:
        algoritmo, n, r, p, sal_hex, hash_hex = almacenado.split("$")
        if algoritmo != "scrypt":
            return False
        calculado = hashlib.scrypt(password.encode("utf-8"), salt=bytes.fromhex(sal_hex),
                                   n=int(n), r=int(r), p=int(p), dklen=len(hash_hex) // 2)
    except (ValueError, AttributeError):
        return False
    # compare_digest tarda lo mismo acierte o falle: no deja adivinar por tiempo.
    return hmac.compare_digest(calculado.hex(), hash_hex)


# Hash de relleno para que un correo inexistente tarde lo mismo que uno real
# y no se pueda saber qué correos están registrados.
HASH_DE_RELLENO = hashear_password("relleno-para-igualar-tiempos")


# =============================================================================
#  HASH DE TRANSACCIONES (HMAC-SHA256)
# =============================================================================
# Un hash solo detecta que los datos cambiaron, pero cualquiera puede
# recalcularlo (diapositiva 18). Con HMAC además hace falta la llave secreta:
# solo la pasarela de pagos que la tiene puede producir un hash válido.

CAMPOS_FIRMADOS = ("idTxn", "user", "date", "value", "paymentMethod")


def serializar_para_firma(transaccion: dict) -> str:
    """Igual que la diapositiva 19: llaves ordenadas y sin espacios, para que
    el emisor y el receptor generen exactamente los mismos bytes."""
    datos = {campo: transaccion[campo] for campo in CAMPOS_FIRMADOS}
    return json.dumps(datos, sort_keys=True, separators=(",", ":"))


def firmar_transaccion(transaccion: dict, llave: bytes) -> str:
    mensaje = serializar_para_firma(transaccion).encode("utf-8")
    return hmac.new(llave, mensaje, hashlib.sha256).hexdigest()


def hash_es_valido(transaccion: dict, hash_recibido: str, llave: bytes) -> bool:
    esperado = firmar_transaccion(transaccion, llave)
    return hmac.compare_digest(esperado, str(hash_recibido).strip().lower())


# =============================================================================
#  INYECCIÓN SQL
# =============================================================================
# La protección real es que TODAS las consultas usan parámetros (?): SQLite
# recibe los datos aparte de la instrucción y nunca los ejecuta como SQL.
# Esta detección es una segunda capa: bloquea el intento, lo registra y deja
# ver en el dashboard quién lo está intentando.

PATRONES_SQL = [
    ("comentario SQL", re.compile(r"--|/\*|\*/")),
    ("comilla seguida de OR/AND", re.compile(r"['\"`]\s*\)?\s*(or|and|\|\||&&)\b", re.I)),
    ("tautología tipo 1=1", re.compile(r"\b(or|and)\b\s+['\"]?[\w@.]+['\"]?\s*(=|<|>|like)\s*['\"]?[\w@.]*", re.I)),
    ("UNION SELECT", re.compile(r"\bunion\b(\s+all)?\s+select\b", re.I)),
    ("SELECT ... FROM", re.compile(r"\bselect\b[\s\S]+\bfrom\b", re.I)),
    ("sentencia destructiva", re.compile(r"\b(drop|truncate|alter)\s+(table|database|schema)\b", re.I)),
    ("sentencia de escritura", re.compile(r"\b(insert\s+into|delete\s+from|update\s+\w+\s+set)\b", re.I)),
    ("sentencias encadenadas", re.compile(r";\s*\w")),
    ("función de ataque", re.compile(r"\b(sleep|benchmark|pg_sleep|load_file|xp_cmdshell|sqlite_master)\b|waitfor\s+delay", re.I)),
]

# Las contraseñas nunca se escanean: jamás tocan una consulta (solo se
# hashean) y una clave fuerte puede contener "--" o comillas legítimamente.
CAMPOS_SIN_ESCANEO = {"password", "confirmacion", "password_actual"}


def buscar_patron_sql(texto: str):
    """Devuelve el nombre del patrón encontrado o None."""
    for nombre, patron in PATRONES_SQL:
        if patron.search(texto):
            return nombre
    return None


def revisar_inyeccion(datos, ruta=""):
    """Recorre recursivamente un JSON y lanza ErrorInyeccion al primer
    texto sospechoso. Devuelve None si todo está limpio."""
    from .errores import ErrorInyeccion

    if isinstance(datos, dict):
        for clave, valor in datos.items():
            if clave in CAMPOS_SIN_ESCANEO:
                continue
            revisar_inyeccion(valor, f"{ruta}.{clave}" if ruta else str(clave))
    elif isinstance(datos, list):
        for posicion, valor in enumerate(datos):
            revisar_inyeccion(valor, f"{ruta}[{posicion}]")
    elif isinstance(datos, str):
        patron = buscar_patron_sql(datos)
        if patron:
            raise ErrorInyeccion(ruta or "cuerpo", patron, datos)


# =============================================================================
#  CSRF Y SESIÓN
# =============================================================================

def token_csrf() -> str:
    if "csrf" not in session:
        session["csrf"] = secrets.token_urlsafe(32)
    return session["csrf"]


def csrf_valido() -> bool:
    enviado = request.headers.get("X-CSRF-Token", "")
    esperado = session.get("csrf", "")
    return bool(esperado) and hmac.compare_digest(enviado, esperado)


def exigir_csrf(vista):
    @wraps(vista)
    def envoltura(*args, **kwargs):
        if not csrf_valido():
            raise ErrorProhibido("Token CSRF inválido o ausente. Recarga la página.")
        return vista(*args, **kwargs)
    return envoltura


def usuario_actual():
    if "usuario_id" not in session:
        return None
    return {
        "id": session["usuario_id"],
        "nombre": session["nombre"],
        "email": session["email"],
        "rol": session["rol"],
    }


def iniciar_sesion(usuario: dict):
    # Se limpia la sesión anterior para evitar fijación de sesión.
    session.clear()
    session.permanent = True
    session["usuario_id"] = usuario["id"]
    session["nombre"] = usuario["nombre"]
    session["email"] = usuario["email"]
    session["rol"] = usuario["rol"]
    token_csrf()


def login_requerido(vista):
    @wraps(vista)
    def envoltura(*args, **kwargs):
        if usuario_actual() is None:
            if request.path.startswith("/api/"):
                raise ErrorNoAutenticado("Debes iniciar sesión.")
            return redirect(url_for("paginas.ingresar", siguiente=request.path))
        return vista(*args, **kwargs)
    return envoltura


def admin_requerido(vista):
    @wraps(vista)
    def envoltura(*args, **kwargs):
        usuario = usuario_actual()
        if usuario is None:
            if request.path.startswith("/api/"):
                raise ErrorNoAutenticado("Debes iniciar sesión como administrador.")
            return redirect(url_for("paginas.ingresar", siguiente=request.path))
        if usuario["rol"] != "ADMIN":
            if request.path.startswith("/api/"):
                raise ErrorProhibido("Solo el administrador puede hacer esto.")
            return redirect(url_for("paginas.inicio"))
        return vista(*args, **kwargs)
    return envoltura


# =============================================================================
#  CABECERAS DE SEGURIDAD
# =============================================================================

POLITICA_CONTENIDO = "; ".join([
    "default-src 'self'",
    "script-src 'self'",                                   # nada de JS en línea
    "style-src 'self' https://fonts.googleapis.com",
    "font-src 'self' https://fonts.gstatic.com",
    "img-src 'self' data:",
    "connect-src 'self'",
    "frame-ancestors 'none'",
    "base-uri 'self'",
    "form-action 'self'",
])


def agregar_cabeceras(respuesta):
    respuesta.headers["Content-Security-Policy"] = POLITICA_CONTENIDO
    respuesta.headers["X-Content-Type-Options"] = "nosniff"
    respuesta.headers["X-Frame-Options"] = "DENY"
    respuesta.headers["Referrer-Policy"] = "same-origin"
    respuesta.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    if request.path.startswith("/api/"):
        respuesta.headers["Cache-Control"] = "no-store"
    return respuesta


def llave_hmac() -> bytes:
    return current_app.config["LLAVE_HMAC"]
