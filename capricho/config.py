"""
Configuración central de Capricho.

Todo lo que se puede cambiar sin tocar el código vive aquí. Los valores
sensibles (llaves) se pueden sobreescribir con variables de entorno para no
dejarlos quemados en el repositorio en un despliegue real.
"""

import os
import secrets
from datetime import timedelta
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
CARPETA_INSTANCIA = RAIZ / "instancia"
CARPETA_LOGS = RAIZ / "logs"


def _llave_de_sesion() -> str:
    """Llave que firma la cookie de sesión.

    Se genera una sola vez y se guarda en instancia/, así las sesiones
    sobreviven a un reinicio del servidor y la llave nunca queda en git.
    """
    desde_entorno = os.environ.get("CAPRICHO_SECRET_KEY")
    if desde_entorno:
        return desde_entorno
    CARPETA_INSTANCIA.mkdir(exist_ok=True)
    archivo = CARPETA_INSTANCIA / "secret_key.txt"
    if not archivo.exists():
        archivo.write_text(secrets.token_hex(32), encoding="utf-8")
    return archivo.read_text(encoding="utf-8").strip()


class Configuracion:
    BASE_DATOS = os.environ.get("CAPRICHO_DB", str(CARPETA_INSTANCIA / "capricho.db"))
    CARPETA_LOGS = str(CARPETA_LOGS)

    SECRET_KEY = _llave_de_sesion()

    # Llave compartida con la pasarela de pagos para firmar transacciones
    # con HMAC-SHA256 (diapositiva 19). Quien no la tenga no puede generar
    # un hash válido.
    LLAVE_HMAC = os.environ.get("CAPRICHO_LLAVE_HMAC", "capricho_llave_secreta_2026").encode("utf-8")

    # El laboratorio del profesor puede pedirle al servidor que firme una
    # transacción de prueba. En producción esto se apaga (CAPRICHO_LABORATORIO=0).
    MODO_LABORATORIO = os.environ.get("CAPRICHO_LABORATORIO", "1") == "1"

    # Si la base de datos está vacía, se llena con datos de demostración.
    SEMBRAR_DATOS = True

    # Cuentas que crea la semilla.
    ADMIN_EMAIL = "admin@capricho.co"
    ADMIN_PASSWORD = os.environ.get("CAPRICHO_ADMIN_PASSWORD", "Capricho2026*")
    CLIENTE_DEMO_EMAIL = "cliente@capricho.co"
    CLIENTE_DEMO_PASSWORD = "Cliente2026*"

    # Cookie de sesión: JavaScript no la puede leer y no viaja en peticiones
    # que otro sitio dispare (mitiga robo de sesión y CSRF).
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    PERMANENT_SESSION_LIFETIME = timedelta(hours=2)

    # Nadie necesita mandar más de 512 KB en una petición; un lote de 500
    # transacciones ocupa cerca de 100 KB.
    MAX_CONTENT_LENGTH = 512 * 1024

    # Límite general de peticiones por IP (ventana deslizante de 1 segundo).
    LIMITE_PETICIONES_POR_SEGUNDO = 40
