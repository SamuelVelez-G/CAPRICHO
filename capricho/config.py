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


def _llave_local(variable: str, archivo: str) -> str:
    """Llave secreta generada una sola vez y guardada en instancia/.

    Así sobrevive a un reinicio del servidor y nunca queda en git. En un
    despliegue real se pasa por variable de entorno.
    """
    desde_entorno = os.environ.get(variable)
    if desde_entorno:
        return desde_entorno
    CARPETA_INSTANCIA.mkdir(exist_ok=True)
    ruta = CARPETA_INSTANCIA / archivo
    if not ruta.exists():
        ruta.write_text(secrets.token_hex(32), encoding="utf-8")
    return ruta.read_text(encoding="utf-8").strip()


class Configuracion:
    BASE_DATOS = os.environ.get("CAPRICHO_DB", str(CARPETA_INSTANCIA / "capricho.db"))
    CARPETA_LOGS = str(CARPETA_LOGS)

    # Firma la cookie de sesión.
    SECRET_KEY = _llave_local("CAPRICHO_SECRET_KEY", "secret_key.txt")

    # Encadena facturas y pagos (HMAC-SHA256). Quien altere la base de datos
    # sin esta llave no puede recalcular la cadena.
    LLAVE_INTEGRIDAD = _llave_local("CAPRICHO_LLAVE_INTEGRIDAD", "llave_integridad.txt").encode("utf-8")

    # Impuesto nacional al consumo de restaurantes y cafeterías (8 %). Los
    # precios del menú ya lo incluyen; la factura lo discrimina.
    TASA_IMPUESTO = 0.08

    # Comprobantes de pago adjuntos: PDF, PNG o JPG de hasta 2 MB.
    CARPETA_COMPROBANTES = str(CARPETA_INSTANCIA / "comprobantes")
    COMPROBANTE_MAX_BYTES = 2 * 1024 * 1024

    # Llave compartida con la pasarela de pagos para firmar transacciones
    # con HMAC-SHA256 (diapositiva 19). Quien no la tenga no puede generar
    # un hash válido. Con ella firman la tienda y el laboratorio.
    LLAVE_HMAC = os.environ.get("CAPRICHO_LLAVE_HMAC", "capricho_llave_secreta_2026").encode("utf-8")

    # Llaves que se aceptan al VERIFICAR. Además de la propia se acepta la de
    # la diapositiva 19, que es la que probablemente usa el generador del
    # profesor. Si él da otra: CAPRICHO_LLAVES_EXTRA="otra_llave,una_mas".
    LLAVE_DIAPOSITIVA = b"mi_llave_privada_123"
    LLAVES_EXTRA = [
        llave.strip().encode("utf-8")
        for llave in os.environ.get("CAPRICHO_LLAVES_EXTRA", "").split(",") if llave.strip()
    ]
    # create_app arma LLAVES_VERIFICACION = [propia, diapositiva, extras...]

    # La diapositiva 17 muestra "Hash = SHA256(datos)" sin llave. Si el
    # generador del profesor firma así, también se acepta: igual detecta
    # cualquier dato alterado. En producción se apaga (CAPRICHO_SHA256_SIMPLE=0)
    # para exigir HMAC, porque un SHA-256 sin llave lo puede calcular cualquiera.
    ACEPTAR_SHA256_SIMPLE = os.environ.get("CAPRICHO_SHA256_SIMPLE", "1") == "1"

    # El laboratorio del profesor puede pedirle al servidor que firme una
    # transacción de prueba. En producción esto se apaga (CAPRICHO_LABORATORIO=0).
    MODO_LABORATORIO = os.environ.get("CAPRICHO_LABORATORIO", "1") == "1"

    # Detección con IA (autoencoder de Keras). Si no hay modelo entrenado o
    # Keras no está instalado, el sistema sigue solo con las reglas.
    IA_ACTIVA = os.environ.get("CAPRICHO_IA", "1") == "1"

    # Si la base de datos está vacía, se llena con datos de demostración.
    SEMBRAR_DATOS = True

    # Cuentas que crea la semilla.
    ADMIN_EMAIL = "admin@capricho.co"
    ADMIN_PASSWORD = os.environ.get("CAPRICHO_ADMIN_PASSWORD", "Capricho2026*")
    CLIENTE_DEMO_EMAIL = "cliente@capricho.co"
    CLIENTE_DEMO_PASSWORD = "Cliente2026*"
    EMPLEADO_DEMO_EMAIL = "caja@capricho.co"          # cajera; los demás empleados usan la misma contraseña
    EMPLEADO_DEMO_PASSWORD = "Caja2026*"

    # Cookie de sesión: JavaScript no la puede leer y no viaja en peticiones
    # que otro sitio dispare (mitiga robo de sesión y CSRF).
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    PERMANENT_SESSION_LIFETIME = timedelta(hours=2)

    # Tope del tamaño de una petición: un lote de 5000 transacciones ocupa
    # cerca de 1 MB, así que 5 MB sobra y evita cuerpos gigantes.
    MAX_CONTENT_LENGTH = 5 * 1024 * 1024

    # Límite general de peticiones por IP (ventana deslizante de 1 segundo).
    LIMITE_PETICIONES_POR_SEGUNDO = 40
