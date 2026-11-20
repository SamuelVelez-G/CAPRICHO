"""
Normalización de textos y valores.

El mismo dato llega escrito de muchas formas: "Granizados ", "granizado",
"GRANIZADOS"; "$12.000", "12,000", "12 mil"; "+57 300 123 4567". Antes de
comparar, buscar duplicados o guardar, todo pasa por aquí para quedar en una
sola forma.

La función clave() es la base de la deduplicación: dos textos con la misma
clave son el mismo dato escrito distinto.
"""

import re
import unicodedata
from difflib import SequenceMatcher

PARTICULAS = {"de", "del", "la", "las", "los", "y", "e"}

# Variantes conocidas de cada método de pago (ya pasadas por clave()).
SINONIMOS_METODO = {
    "Nequi": {"nequi", "nequi app", "nequi transferencia"},
    "Daviplata": {"daviplata", "davi plata", "davivienda daviplata"},
    "Tarjeta": {"tarjeta", "tarjeta credito", "tarjeta debito", "tc", "td", "credito", "debito", "visa",
                "mastercard", "datafono"},
    "PSE": {"pse", "p s e", "boton pse", "pago pse"},
    "Efectivo": {"efectivo", "cash", "contado", "billete"},
    "Transferencia": {"transferencia", "transferencia bancaria", "bancolombia", "consignacion", "deposito"},
}
METODO_POR_CLAVE = {variante: metodo for metodo, variantes in SINONIMOS_METODO.items() for variante in variantes}


def espacios(texto: str) -> str:
    """Recorta y deja un solo espacio entre palabras."""
    return " ".join(str(texto).split())


def sin_tildes(texto: str) -> str:
    descompuesto = unicodedata.normalize("NFKD", texto)
    return "".join(c for c in descompuesto if not unicodedata.combining(c))


def _singular(palabra: str) -> str:
    """Plural sencillo del español, suficiente para comparar nombres."""
    for final, reemplazo in (("ciones", "cion"), ("siones", "sion"), ("ales", "al"), ("ores", "or")):
        if palabra.endswith(final) and len(palabra) > len(final) + 1:
            return palabra[: -len(final)] + reemplazo
    if palabra.endswith("s") and len(palabra) > 3:
        return palabra[:-1]
    return palabra


def clave(texto: str) -> str:
    """Forma canónica para comparar: sin tildes, minúsculas, sin signos y en singular.

    "Granizados " -> "granizado"; "ADICIONES" -> "adicion"; "Galleta  Óreo" -> "galleta oreo".
    """
    limpio = re.sub(r"[^a-z0-9 ]", " ", sin_tildes(str(texto)).lower())
    return " ".join(_singular(p) for p in limpio.split())


def similitud(a: str, b: str) -> float:
    """0 a 1: qué tanto se parecen dos textos ya normalizados."""
    return SequenceMatcher(None, clave(a), clave(b)).ratio()


def unificar(texto: str, canonicos, umbral=0.82):
    """Busca a qué valor oficial corresponde un texto escrito distinto.

    Devuelve (canonico, como) con como = "exacto" | "parecido" | None.
    "Granisados" -> ("Granizados", "parecido").
    """
    buscado = clave(texto)
    mejor, puntaje = None, 0.0
    for canonico in canonicos:
        if clave(canonico) == buscado:
            return canonico, "exacto"
        parecido = SequenceMatcher(None, buscado, clave(canonico)).ratio()
        if parecido > puntaje:
            mejor, puntaje = canonico, parecido
    if puntaje >= umbral:
        return mejor, "parecido"
    return None, None


def nombre_propio(texto: str) -> str:
    """"  laura   GÓMEZ de la torre" -> "Laura Gómez de la Torre"."""
    palabras = espacios(texto).lower().split(" ")
    return " ".join(p if (p in PARTICULAS and i > 0) else p[:1].upper() + p[1:] for i, p in enumerate(palabras))


def email(texto: str) -> str:
    return espacios(texto).replace(" ", "").lower()


def telefono(texto):
    """Deja solo los 10 dígitos de un celular colombiano o None si no se puede."""
    if texto is None:
        return None
    digitos = re.sub(r"\D", "", str(texto))
    if len(digitos) == 12 and digitos.startswith("57"):
        digitos = digitos[2:]
    return digitos if re.fullmatch(r"3\d{9}", digitos) else None


def metodo_pago(texto):
    """"NEQUI ", "tarjeta de crédito", "P.S.E." -> "Nequi", "Tarjeta", "PSE". None si no se reconoce."""
    llave = clave(texto)
    llave_sin_de = " ".join(p for p in llave.split() if p not in PARTICULAS)
    return METODO_POR_CLAVE.get(llave) or METODO_POR_CLAVE.get(llave_sin_de)


def precio(valor):
    """Convierte lo que escribió una persona a pesos enteros.

    Devuelve (pesos, nota). pesos es None si no se pudo interpretar.
        12000 -> 12000      "$12.000" -> 12000      "12,000" -> 12000
        "12.000,50" -> 12000 (se redondea)          "12 mil" -> 12000
    """
    if isinstance(valor, bool) or valor is None:
        return None, "vacío"
    if isinstance(valor, (int, float)):
        return (round(valor), None) if valor > 0 else (None, "no es positivo")
    texto = sin_tildes(str(valor)).lower().replace("cop", "").replace("$", "").strip()
    multiplicador = 1
    if texto.endswith(("mil", "k")):
        multiplicador = 1000
        texto = texto.removesuffix("mil").removesuffix("k").strip()
    texto = texto.replace(" ", "")
    if not re.fullmatch(r"[\d.,]+", texto or "x"):
        return None, f"«{valor}» no es un número"
    # Separadores: el último que aparezca con 1 o 2 dígitos después es decimal.
    decimal = re.search(r"[.,](\d{1,2})$", texto)
    entero, fraccion = (texto[: decimal.start()], decimal.group(1)) if decimal else (texto, "")
    entero = re.sub(r"[.,]", "", entero)
    if not entero:
        return None, f"«{valor}» no es un número"
    pesos = (int(entero) + (int(fraccion) / 10 ** len(fraccion) if fraccion else 0)) * multiplicador
    pesos = round(pesos)
    if pesos <= 0:
        return None, "no es positivo"
    nota = None if str(valor).strip() == str(pesos) else f"«{valor}» se interpretó como {pesos}"
    return pesos, nota
