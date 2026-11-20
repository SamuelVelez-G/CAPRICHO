"""
Comprobantes de pago: ¿el pago corresponde a su comprobante?

La pasarela de pagos simulada (Nequi, Daviplata, PSE, transferencia) entrega
un comprobante en PDF. Además del texto que ve una persona, el PDF lleva un
bloque con los datos del pago FIRMADOS con HMAC-SHA256:

    %CAPRICHO-COMPROBANTE <datos en base64>
    datos = {"referencia", "metodo", "monto", "fecha", "pagador", "firma"}

Al adjuntarlo se revisa, en este orden:
  1. Tipo y tamaño del archivo (PDF, PNG o JPG; se mira el contenido, no la extensión).
  2. Que el mismo archivo (mismo SHA-256) o la misma referencia no se haya
     usado ya en otro pago                                  -> REUTILIZADO
  3. Que la firma cuadre con los datos                      -> FALSO si no
  4. Que el monto y el método sean los del pago             -> NO_COINCIDE si no
Un comprobante sin bloque firmado (una foto, un pantallazo) no se puede
verificar solo: queda SIN_VERIFICAR para revisión humana.
"""

import base64
import hashlib
import hmac
import json
import re
from pathlib import Path

FIRMAS = {b"%PDF-": ("application/pdf", "pdf"), b"\x89PNG\r\n\x1a\n": ("image/png", "png"),
          b"\xff\xd8\xff": ("image/jpeg", "jpg")}
RE_BLOQUE = re.compile(rb"%CAPRICHO-COMPROBANTE ([A-Za-z0-9+/=]+)")
CAMPOS_FIRMADOS = ("referencia", "metodo", "monto", "fecha", "pagador")


def tipo_archivo(contenido: bytes):
    """(mime, extensión) según los primeros bytes; None si no es PDF, PNG ni JPG."""
    for firma, tipo in FIRMAS.items():
        if contenido.startswith(firma):
            return tipo
    return None


def sha256(contenido: bytes) -> str:
    return hashlib.sha256(contenido).hexdigest()


def _firma(datos: dict, llave: bytes) -> str:
    mensaje = json.dumps({c: datos[c] for c in CAMPOS_FIRMADOS}, sort_keys=True, separators=(",", ":"),
                         ensure_ascii=False)
    return hmac.new(llave, mensaje.encode("utf-8"), hashlib.sha256).hexdigest()


def _texto_pdf(texto: str) -> str:
    """Escapa un texto para un PDF (fuente estándar, Latin-1)."""
    texto = texto.encode("latin-1", "replace").decode("latin-1")
    return texto.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def generar_pdf(datos: dict, llave: bytes) -> bytes:
    """Arma un PDF de una página con el comprobante y el bloque firmado."""
    datos = {**{c: datos[c] for c in CAMPOS_FIRMADOS}}
    datos["firma"] = _firma(datos, llave)
    monto = f"${datos['monto']:,.0f}".replace(",", ".")
    lineas = [("F2", 18, "Comprobante de pago"), ("F1", 11, "Pasarela de pagos simulada - Capricho"),
              ("F1", 11, ""), ("F2", 13, f"Monto: {monto}"), ("F1", 12, f"Metodo: {datos['metodo']}"),
              ("F1", 12, f"Referencia: {datos['referencia']}"), ("F1", 12, f"Fecha: {datos['fecha']}"),
              ("F1", 12, f"Pagador: {datos['pagador']}"), ("F1", 11, ""),
              ("F1", 8, f"Firma HMAC-SHA256: {datos['firma']}")]
    flujo = ["BT", "50 780 Td"]
    for fuente, tamano, texto in lineas:
        flujo += [f"/{fuente} {tamano} Tf", f"({_texto_pdf(texto)}) Tj", f"0 -{tamano + 10} Td"]
    flujo.append("ET")
    contenido = "\n".join(flujo).encode("latin-1")

    objetos = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Contents 4 0 R "
        b"/Resources << /Font << /F1 5 0 R /F2 6 0 R >> >> >>",
        b"<< /Length %d >>\nstream\n" % len(contenido) + contenido + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold >>",
    ]
    bloque = base64.b64encode(json.dumps(datos, ensure_ascii=False).encode("utf-8"))
    salida = bytearray(b"%PDF-1.4\n%CAPRICHO-COMPROBANTE " + bloque + b"\n")
    posiciones = []
    for numero, cuerpo in enumerate(objetos, start=1):
        posiciones.append(len(salida))
        salida += b"%d 0 obj\n" % numero + cuerpo + b"\nendobj\n"
    inicio_xref = len(salida)
    salida += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objetos) + 1)
    for posicion in posiciones:
        salida += b"%010d 00000 n \n" % posicion
    salida += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objetos) + 1, inicio_xref)
    return bytes(salida)


def leer_bloque(contenido: bytes):
    coincidencia = RE_BLOQUE.search(contenido[:4096])
    if not coincidencia:
        return None
    try:
        datos = json.loads(base64.b64decode(coincidencia.group(1)).decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return {}
    return datos if isinstance(datos, dict) else {}


def verificar(contenido: bytes, llave: bytes, metodo: str, monto: int):
    """Devuelve (verificacion, detalle, datos_del_comprobante)."""
    datos = leer_bloque(contenido)
    if datos is None:
        return ("SIN_VERIFICAR", "El comprobante no trae la firma de la pasarela (foto o pantallazo): "
                "requiere revisión humana.", None)
    if not all(c in datos for c in (*CAMPOS_FIRMADOS, "firma")) or not hmac.compare_digest(
            str(datos["firma"]), _firma(datos, llave)):
        return ("FALSO", "La firma del comprobante no coincide con sus datos: el archivo fue editado o "
                "no lo emitió la pasarela.", datos)
    if round(float(datos["monto"])) != monto:
        return ("NO_COINCIDE", f"El comprobante es por ${float(datos['monto']):,.0f} y el pago por ${monto:,.0f}."
                .replace(",", "."), datos)
    if str(datos["metodo"]).lower() != metodo.lower():
        return ("NO_COINCIDE", f"El comprobante es de {datos['metodo']} y el pago dice {metodo}.", datos)
    return ("VERIFICADO", "Firma de la pasarela válida; monto y método coinciden con el pago.", datos)


def guardar(contenido: bytes, carpeta: str) -> str:
    """Guarda el archivo con su SHA-256 como nombre (el mismo archivo no se duplica)."""
    _, extension = tipo_archivo(contenido)
    huella = sha256(contenido)
    ruta = Path(carpeta) / f"{huella}.{extension}"
    if not ruta.exists():
        ruta.parent.mkdir(parents=True, exist_ok=True)
        ruta.write_bytes(contenido)
    return huella


def buscar_archivo(carpeta: str, huella: str):
    if not re.fullmatch(r"[0-9a-f]{64}", huella or ""):
        return None
    return next(Path(carpeta).glob(f"{huella}.*"), None)
