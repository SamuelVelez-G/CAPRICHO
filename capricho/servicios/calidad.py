"""
Limpieza y calidad de datos.

Dos herramientas:

1. AUDITORÍA de lo que ya está en la base de datos. Busca:
     clientes duplicados (mismo correo con otra capitalización, mismo celular
     o mismo nombre escrito distinto), celulares y correos sin normalizar,
     ítems repetidos, precios mal escritos (un cero de más), categorías
     parecidas, facturas que no cuadran y métodos de pago no estándar.
   y calcula un puntaje de calidad con cuatro dimensiones:
     completitud, validez, unicidad y consistencia.
   corregir() arregla lo que se puede arreglar solo (formatos) y desactiva
   los duplicados; lo que necesita criterio humano queda en el reporte.

2. IMPORTACIÓN de archivos CSV o JSON (clientes o ítems): valida el esquema
   de cada registro, lo normaliza, detecta duplicados contra el archivo y
   contra la base, y lo clasifica como VÁLIDO, CORREGIDO, DUPLICADO o
   DESCARTADO. Con aplicar=True guarda los válidos y corregidos.

Los duplicados se buscan con un diccionario de claves normalizadas: una sola
pasada, O(n). Compararlos de dos en dos sería O(n²) (ver el benchmark).
"""

import csv
import io
import json
import re
import statistics
import time

from ..tiempo import a_texto, ahora
from ..validaciones import METODOS_PAGO, RE_EMAIL, RE_TEXTO_PRODUCTO, validar_nombre
from . import alertas, normalizacion

MAX_REGISTROS = 5000
RE_CELULAR = re.compile(r"^3\d{9}$")


def _agrupar(registros, clave_de):
    """Agrupa por clave normalizada en una sola pasada (diccionario = O(n))."""
    grupos = {}
    for registro in registros:
        clave = clave_de(registro)
        if clave:
            grupos.setdefault(clave, []).append(registro)
    return [grupo for grupo in grupos.values() if len(grupo) > 1]


def _problema(tipo, tabla, registros, detalle, correccion=None, automatica=False):
    return {"tipo": tipo, "tabla": tabla, "registros": registros, "detalle": detalle,
            "correccion": correccion, "automatica": automatica}


# =============================================================================
#  Auditoría de la base de datos
# =============================================================================

def auditar(db) -> dict:
    inicio = time.perf_counter()
    problemas = []
    usuarios = [dict(f) for f in db.execute(
        "SELECT id, nombre, email, telefono, rol, estado FROM usuarios WHERE estado != 'INACTIVO'")]
    productos = [dict(f) for f in db.execute(
        """SELECT p.id, p.nombre, p.precio, p.categoria_id, c.nombre AS categoria, p.activo
           FROM productos p JOIN categorias c ON c.id = p.categoria_id""")]
    categorias = [dict(f) for f in db.execute("SELECT id, nombre, clave FROM categorias")]

    # --- Clientes duplicados (tres criterios) --------------------------------
    vistos = set()
    criterios = [("correo", lambda u: normalizacion.email(u["email"])),
                 ("celular", lambda u: normalizacion.telefono(u["telefono"])),
                 ("nombre", lambda u: normalizacion.clave(u["nombre"]) if u["rol"] == "CLIENTE" else None)]
    for criterio, clave_de in criterios:
        for grupo in _agrupar(usuarios, clave_de):
            ids = tuple(sorted(u["id"] for u in grupo))
            if ids in vistos:
                continue
            vistos.add(ids)
            problemas.append(_problema(
                "CLIENTE_DUPLICADO", "usuarios", [{"id": u["id"], "valor": f"{u['nombre']} <{u['email']}>"} for u in grupo],
                f"{len(grupo)} registros con el mismo {criterio} normalizado: probablemente es la misma persona.",
                f"Conservar #{ids[0]} y desactivar los demás", automatica=criterio != "nombre"))

    # --- Formatos de usuarios ---------------------------------------------------
    for u in usuarios:
        if u["email"] != normalizacion.email(u["email"]):
            problemas.append(_problema("CORREO_SIN_NORMALIZAR", "usuarios", [{"id": u["id"], "valor": u["email"]}],
                                       "El correo tiene mayúsculas o espacios.", normalizacion.email(u["email"]), True))
        if u["telefono"] and not RE_CELULAR.match(u["telefono"]):
            limpio = normalizacion.telefono(u["telefono"])
            if limpio:
                problemas.append(_problema("CELULAR_SIN_NORMALIZAR", "usuarios", [{"id": u["id"], "valor": u["telefono"]}],
                                           "Celular con espacios, guiones o +57.", limpio, True))
            else:
                problemas.append(_problema("CELULAR_INVALIDO", "usuarios", [{"id": u["id"], "valor": u["telefono"]}],
                                           "No es un celular colombiano de 10 dígitos.", "Pedir el dato al cliente"))
        if u["nombre"] != normalizacion.nombre_propio(u["nombre"]):
            problemas.append(_problema("NOMBRE_SIN_NORMALIZAR", "usuarios", [{"id": u["id"], "valor": u["nombre"]}],
                                       "Mayúsculas o espacios inconsistentes.", normalizacion.nombre_propio(u["nombre"]), True))

    # --- Ítems repetidos y precios mal escritos ---------------------------------
    for grupo in _agrupar(productos, lambda p: normalizacion.clave(p["nombre"])):
        principal = min(grupo, key=lambda p: (not p["activo"], p["id"]))
        problemas.append(_problema(
            "ITEM_DUPLICADO", "productos", [{"id": p["id"], "valor": p["nombre"]} for p in grupo],
            f"«{grupo[0]['nombre']}» y «{grupo[1]['nombre']}» son el mismo ítem escrito distinto.",
            f"Conservar #{principal['id']} y desactivar los demás", True))
    por_categoria = {}
    for p in productos:
        por_categoria.setdefault(p["categoria_id"], []).append(p)
    for grupo in por_categoria.values():
        if len(grupo) < 3:
            continue
        mediana = statistics.median(p["precio"] for p in grupo)
        for p in grupo:
            razon = p["precio"] / mediana
            if razon >= 5 or razon <= 0.2:
                sugerido = p["precio"] // 10 if razon >= 5 else p["precio"] * 10
                problemas.append(_problema(
                    "PRECIO_SOSPECHOSO", "productos", [{"id": p["id"], "valor": f"{p['nombre']}: ${p['precio']:,}".replace(",", ".")}],
                    f"Es {razon:.1f} veces la mediana de {p['categoria']} (${mediana:,.0f}): ¿un cero de más o de menos?"
                    .replace(",", "."), f"${sugerido:,}".replace(",", ".")))

    # --- Categorías parecidas ---------------------------------------------------
    for i, a in enumerate(categorias):
        for b in categorias[i + 1:]:
            if normalizacion.similitud(a["nombre"], b["nombre"]) >= 0.82:
                problemas.append(_problema("CATEGORIA_PARECIDA", "categorias",
                                           [{"id": a["id"], "valor": a["nombre"]}, {"id": b["id"], "valor": b["nombre"]}],
                                           "Dos categorías casi iguales: los ítems quedan repartidos.", "Unificar"))

    # --- Facturas que no cuadran -------------------------------------------------
    descuadradas = db.execute(
        """SELECT id, numero, subtotal, descuento, domicilio, base, impuesto, total FROM facturas
           WHERE total != subtotal - descuento + domicilio OR base + impuesto != subtotal - descuento""").fetchall()
    for f in descuadradas:
        problemas.append(_problema("FACTURA_DESCUADRADA", "facturas", [{"id": f["id"], "valor": f"FV-{f['numero']:06d}"}],
                                   f"Total ${f['total']:,} pero subtotal - descuento + domicilio = "
                                   f"${f['subtotal'] - f['descuento'] + f['domicilio']:,}".replace(",", "."),
                                   "Revisar con el hash encadenado (página Integridad)"))

    # --- Métodos de pago escritos distinto ---------------------------------------
    for fila in db.execute("SELECT metodo_pago, COUNT(*) AS n FROM transacciones GROUP BY metodo_pago"):
        if fila["metodo_pago"] not in METODOS_PAGO:
            sugerido = normalizacion.metodo_pago(fila["metodo_pago"])
            problemas.append(_problema("METODO_NO_ESTANDAR", "transacciones",
                                       [{"id": None, "valor": f"{fila['metodo_pago']} ({fila['n']})"}],
                                       "Método de pago que no está en la lista oficial.", sugerido or "Revisar"))

    # --- Puntaje -------------------------------------------------------------------
    total_usuarios = max(len(usuarios), 1)
    clientes = [u for u in usuarios if u["rol"] == "CLIENTE"]
    duplicados = sum(len(p["registros"]) - 1 for p in problemas if p["tipo"] in ("CLIENTE_DUPLICADO", "ITEM_DUPLICADO"))
    invalidos = sum(1 for p in problemas if p["tipo"] in ("CELULAR_INVALIDO", "CELULAR_SIN_NORMALIZAR",
                                                         "CORREO_SIN_NORMALIZAR", "NOMBRE_SIN_NORMALIZAR"))
    facturas = db.execute("SELECT COUNT(*) FROM facturas").fetchone()[0] or 1
    precios_raros = sum(1 for p in problemas if p["tipo"] == "PRECIO_SOSPECHOSO")
    dimensiones = {
        "completitud": 100 * sum(1 for u in clientes if u["telefono"]) / max(len(clientes), 1),
        "validez": 100 * (1 - invalidos / (total_usuarios * 3)),
        "unicidad": 100 * (1 - duplicados / (total_usuarios + len(productos))),
        "consistencia": 100 * (1 - (len(descuadradas) + precios_raros) / (facturas + len(productos))),
    }
    puntaje = statistics.fmean(dimensiones.values())
    por_tipo = {}
    for p in problemas:
        por_tipo[p["tipo"]] = por_tipo.get(p["tipo"], 0) + 1
    return {
        "puntaje": round(puntaje, 1), "dimensiones": {k: round(v, 1) for k, v in dimensiones.items()},
        "problemas": problemas, "por_tipo": por_tipo,
        "registros": {"usuarios": len(usuarios), "productos": len(productos), "categorias": len(categorias),
                      "facturas": facturas},
        "automaticos": sum(1 for p in problemas if p["automatica"]),
        "milisegundos": round((time.perf_counter() - inicio) * 1000, 1),
    }


def corregir(db) -> dict:
    """Aplica las correcciones automáticas: formatos y duplicados evidentes."""
    antes = auditar(db)
    momento = a_texto(ahora())
    hechos = {}
    for p in antes["problemas"]:
        if not p["automatica"]:
            continue
        registro = p["registros"][0]
        if p["tipo"] == "CORREO_SIN_NORMALIZAR":
            libre = not db.execute("SELECT 1 FROM usuarios WHERE email = ? AND id != ?",
                                   (p["correccion"], registro["id"])).fetchone()
            if libre:
                db.execute("UPDATE usuarios SET email = ?, fecha_actualizacion = ? WHERE id = ?",
                           (p["correccion"], momento, registro["id"]))
        elif p["tipo"] == "CELULAR_SIN_NORMALIZAR":
            db.execute("UPDATE usuarios SET telefono = ?, fecha_actualizacion = ? WHERE id = ?",
                       (p["correccion"], momento, registro["id"]))
        elif p["tipo"] == "NOMBRE_SIN_NORMALIZAR":
            db.execute("UPDATE usuarios SET nombre = ?, fecha_actualizacion = ? WHERE id = ?",
                       (p["correccion"], momento, registro["id"]))
        elif p["tipo"] == "CLIENTE_DUPLICADO":
            conservar = min(r["id"] for r in p["registros"])
            for r in p["registros"]:
                if r["id"] != conservar:
                    db.execute("UPDATE usuarios SET estado = 'INACTIVO', fecha_actualizacion = ? WHERE id = ?",
                               (momento, r["id"]))
        elif p["tipo"] == "ITEM_DUPLICADO":
            conservar = int(p["correccion"].split("#")[1].split()[0])
            for r in p["registros"]:
                if r["id"] != conservar:
                    db.execute("UPDATE productos SET activo = 0, fecha_actualizacion = ? WHERE id = ?",
                               (momento, r["id"]))
        else:
            continue
        hechos[p["tipo"]] = hechos.get(p["tipo"], 0) + 1
    db.commit()
    despues = auditar(db)
    _guardar_reporte(db, "auditoría + corrección", "auditoria", antes["registros"]["usuarios"],
                     antes["registros"]["usuarios"] - len(antes["problemas"]), sum(hechos.values()),
                     antes["por_tipo"].get("CLIENTE_DUPLICADO", 0), 0, despues["puntaje"],
                     {"antes": antes["puntaje"], "despues": despues["puntaje"], "corregidos": hechos})
    return {"antes": antes["puntaje"], "despues": despues["puntaje"], "corregidos": hechos, "auditoria": despues}


# =============================================================================
#  Importación de archivos
# =============================================================================

ESQUEMAS = {
    "clientes": {"obligatorios": ("nombre", "email"), "opcionales": ("telefono",)},
    "items": {"obligatorios": ("nombre", "categoria", "precio"), "opcionales": ("descripcion", "stock")},
}


def leer_archivo(contenido: bytes, nombre: str):
    """CSV (coma o punto y coma) o JSON (lista de objetos). Devuelve la lista de registros crudos."""
    texto = contenido.decode("utf-8-sig", errors="replace")
    if nombre.lower().endswith(".json") or texto.lstrip().startswith("["):
        datos = json.loads(texto)
        if not isinstance(datos, list):
            raise ValueError("El JSON debe ser una lista de objetos")
        return datos[:MAX_REGISTROS + 1]
    dialecto = csv.Sniffer().sniff(texto[:2048], delimiters=",;") if texto.strip() else csv.excel
    return list(csv.DictReader(io.StringIO(texto), dialect=dialecto))[:MAX_REGISTROS + 1]


def _limpiar_cliente(crudo, errores, cambios):
    nombre = normalizacion.nombre_propio(crudo["nombre"])
    if nombre != crudo["nombre"]:
        cambios.append(f"nombre «{crudo['nombre']}» → «{nombre}»")
    if error := validar_nombre(nombre):
        errores.append(f"nombre: {error}")
    email = normalizacion.email(crudo["email"])
    if email != crudo["email"]:
        cambios.append(f"correo «{crudo['email']}» → «{email}»")
    if ".." in email or not RE_EMAIL.match(email):
        errores.append("correo inválido")
    telefono = None
    if crudo.get("telefono") not in (None, ""):
        telefono = normalizacion.telefono(crudo["telefono"])
        if telefono is None:
            errores.append(f"celular «{crudo['telefono']}» inválido")
        elif telefono != str(crudo["telefono"]):
            cambios.append(f"celular «{crudo['telefono']}» → {telefono}")
    return {"nombre": nombre, "email": email, "telefono": telefono}


def _limpiar_item(crudo, errores, cambios, categorias, medianas):
    nombre = normalizacion.espacios(crudo["nombre"])
    nombre = nombre[:1].upper() + nombre[1:]
    if nombre != crudo["nombre"]:
        cambios.append(f"nombre «{crudo['nombre']}» → «{nombre}»")
    if not 3 <= len(nombre) <= 60 or not RE_TEXTO_PRODUCTO.match(nombre):
        errores.append("nombre con caracteres no permitidos")
    categoria, como = normalizacion.unificar(crudo["categoria"], [c["nombre"] for c in categorias])
    if categoria is None:
        errores.append(f"categoría «{crudo['categoria']}» no existe")
    elif categoria != crudo["categoria"]:
        cambios.append(f"categoría «{crudo['categoria']}» → «{categoria}»" + (" (parecida)" if como == "parecido" else ""))
    precio, nota = normalizacion.precio(crudo["precio"])
    if precio is None:
        errores.append(f"precio: {nota}")
    else:
        if nota:
            cambios.append(f"precio {nota}")
        mediana = medianas.get(categoria)
        if mediana and precio / mediana >= 5 and 500 <= precio // 10:
            cambios.append(f"precio ${precio:,} es {precio / mediana:.0f} veces la mediana de la categoría: "
                           f"se corrigió a ${precio // 10:,} (un cero de más)".replace(",", "."))
            precio //= 10
        if not 500 <= precio <= 500_000:
            errores.append("precio fuera de rango ($500 a $500.000)")
    stock = 0
    if crudo.get("stock") not in (None, ""):
        stock, _ = normalizacion.precio(crudo["stock"])
        if stock is None or stock > 100_000:
            errores.append("stock inválido")
    descripcion = normalizacion.espacios(crudo.get("descripcion") or "Importado") or "Importado"
    return {"nombre": nombre, "categoria": categoria, "precio": precio, "stock": stock or 0, "descripcion": descripcion}


def importar(db, registros, tipo, fuente="archivo", aplicar=False) -> dict:
    inicio = time.perf_counter()
    if tipo not in ESQUEMAS:
        raise ValueError("tipo debe ser clientes o items")
    if len(registros) > MAX_REGISTROS:
        raise ValueError(f"Máximo {MAX_REGISTROS} registros por archivo")
    esquema = ESQUEMAS[tipo]
    categorias = [dict(f) for f in db.execute("SELECT id, nombre FROM categorias")]
    medianas = {}
    for c in categorias:
        precios = [f[0] for f in db.execute("SELECT precio FROM productos WHERE categoria_id = ? AND activo = 1", (c["id"],))]
        if precios:
            medianas[c["nombre"]] = statistics.median(precios)
    if tipo == "clientes":
        existentes = {normalizacion.email(f["email"]): f["id"] for f in db.execute("SELECT id, email FROM usuarios")}
        celulares = {normalizacion.telefono(f["telefono"]): f["id"] for f in db.execute("SELECT id, telefono FROM usuarios")
                     if normalizacion.telefono(f["telefono"])}
    else:
        existentes = {normalizacion.clave(f["nombre"]): f["id"] for f in db.execute("SELECT id, nombre FROM productos")}
        celulares = {}

    vistos = {}
    resultados = []
    for posicion, crudo in enumerate(registros, start=1):
        errores, cambios = [], []
        if not isinstance(crudo, dict):
            resultados.append({"fila": posicion, "estado": "DESCARTADO", "errores": ["no es un objeto"], "cambios": []})
            continue
        crudo = {str(k).strip().lower(): (v.strip() if isinstance(v, str) else v) for k, v in crudo.items() if k}
        faltan = [c for c in esquema["obligatorios"] if crudo.get(c) in (None, "")]
        if faltan:
            resultados.append({"fila": posicion, "estado": "DESCARTADO", "errores": [f"falta {', '.join(faltan)}"],
                               "cambios": [], "original": crudo})
            continue
        limpio = (_limpiar_cliente(crudo, errores, cambios) if tipo == "clientes"
                  else _limpiar_item(crudo, errores, cambios, categorias, medianas))
        if errores:
            estado = "DESCARTADO"
        else:
            claves = ([("correo", limpio["email"]), ("celular", limpio["telefono"])] if tipo == "clientes"
                      else [("nombre", normalizacion.clave(limpio["nombre"]))])
            duplicado = None
            for criterio, clave in claves:
                if not clave:
                    continue
                if clave in vistos:
                    duplicado = f"mismo {criterio} que la fila {vistos[clave]}"
                elif clave in existentes or clave in celulares:
                    duplicado = f"ya existe en la base (mismo {criterio})"
                if duplicado:
                    break
            for _, clave in claves:
                if clave:
                    vistos.setdefault(clave, posicion)
            estado = "DUPLICADO" if duplicado else ("CORREGIDO" if cambios else "VALIDO")
            if duplicado:
                errores.append(duplicado)
        resultados.append({"fila": posicion, "estado": estado, "errores": errores, "cambios": cambios,
                           "original": crudo, "limpio": limpio})

    conteo = {e: sum(1 for r in resultados if r["estado"] == e) for e in ("VALIDO", "CORREGIDO", "DUPLICADO", "DESCARTADO")}
    guardados = 0
    if aplicar:
        guardados = _guardar(db, tipo, [r["limpio"] for r in resultados if r["estado"] in ("VALIDO", "CORREGIDO")],
                             categorias)
    total = max(len(resultados), 1)
    puntaje = 100 * conteo["VALIDO"] / total
    reporte = {
        "tipo": tipo, "fuente": fuente, "recibidos": len(resultados), **{k.lower(): v for k, v in conteo.items()},
        "puntaje_original": round(puntaje, 1),
        "puntaje_final": round(100 * (conteo["VALIDO"] + conteo["CORREGIDO"]) / total, 1),
        "guardados": guardados, "aplicado": aplicar, "resultados": resultados[:300],
        "milisegundos": round((time.perf_counter() - inicio) * 1000, 1),
    }
    _guardar_reporte(db, fuente, tipo, len(resultados), conteo["VALIDO"], conteo["CORREGIDO"], conteo["DUPLICADO"],
                     conteo["DESCARTADO"], reporte["puntaje_original"],
                     {k: v for k, v in reporte.items() if k != "resultados"})
    return reporte


def _guardar(db, tipo, limpios, categorias):
    momento = a_texto(ahora())
    if tipo == "clientes":
        for c in limpios:
            db.execute("""INSERT INTO usuarios (nombre, email, telefono, fecha_creacion, fecha_actualizacion)
                          VALUES (?, ?, ?, ?, ?)""", (c["nombre"], c["email"], c["telefono"], momento, momento))
    else:
        ids = {c["nombre"]: c["id"] for c in categorias}
        for i in limpios:
            db.execute("""INSERT INTO productos (nombre, descripcion, categoria_id, tipo, precio, stock, stock_minimo,
                                                 activo, fecha_creacion, fecha_actualizacion)
                          VALUES (?, ?, ?, 'OTRO', ?, ?, 0, 1, ?, ?)""",
                       (i["nombre"], i["descripcion"], ids[i["categoria"]], i["precio"], i["stock"], momento, momento))
    db.commit()
    return len(limpios)


def _guardar_reporte(db, fuente, tipo, recibidos, validos, corregidos, duplicados, descartados, puntaje, detalle):
    db.execute(
        """INSERT INTO calidad_reportes (fuente, tipo, recibidos, validos, corregidos, duplicados, descartados, puntaje,
                                         detalle, fecha) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (fuente[:80], tipo, recibidos, validos, corregidos, duplicados, descartados, puntaje,
         json.dumps(detalle, ensure_ascii=False, default=str), a_texto(ahora())))
    if descartados + duplicados > 0 and recibidos and (descartados + duplicados) / recibidos > 0.3:
        alertas.crear(db, "CALIDAD_DATOS", "MEDIO", "CALIDAD",
                      f"El archivo «{fuente}» trae {descartados} registros inválidos y {duplicados} duplicados de "
                      f"{recibidos}.", datos={"recibidos": recibidos, "descartados": descartados, "duplicados": duplicados})
    db.commit()


def historial(db, limite=15):
    return [dict(f) for f in db.execute(
        "SELECT id, fuente, tipo, recibidos, validos, corregidos, duplicados, descartados, puntaje, fecha "
        "FROM calidad_reportes ORDER BY id DESC LIMIT ?", (limite,))]
