"""
Validación de todo lo que entra al servidor.

El navegador valida lo mismo para dar mensajes rápidos, pero esa validación
se puede saltar (basta con usar curl o editar el HTML). La que manda es esta.

Reglas generales:
  - Ningún campo obligatorio puede venir nulo, vacío o solo con espacios.
  - Los textos se recortan y se revisan contra una lista de caracteres permitidos.
  - Los números se revisan con su tipo real: en Python True es un int, así
    que se descarta explícitamente.
"""

import math
import re
from datetime import timedelta

from .errores import ErrorValidacion
from .tiempo import ahora, interpretar_fecha_externa

NOMBRE_MIN_LETRAS = 4          # "más de 3 letras"
NOMBRE_MAX = 60
METODOS_PAGO = ("Tarjeta", "Nequi", "Daviplata", "PSE", "Efectivo")
VALOR_MAXIMO_TRANSACCION = 50_000_000

RE_NOMBRE = re.compile(r"^[A-Za-zÁÉÍÓÚÜÑáéíóúüñ]+( [A-Za-zÁÉÍÓÚÜÑáéíóúüñ]+)*$")
RE_EMAIL = re.compile(r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}$")
RE_TELEFONO = re.compile(r"^3\d{9}$")
RE_DIRECCION = re.compile(r"^[A-Za-z0-9ÁÉÍÓÚÜÑáéíóúüñ#.,°/\- ]+$")
RE_ID_TXN = re.compile(r"^[A-Za-z0-9_-]{1,40}$")
RE_TEXTO_PRODUCTO = re.compile(r"^[A-Za-z0-9ÁÉÍÓÚÜÑáéíóúüñ.,()% \-]+$")


# =============================================================================
#  Piezas reutilizables
# =============================================================================

def _vacio(valor) -> bool:
    return valor is None or (isinstance(valor, str) and not valor.strip())


def _es_entero(valor) -> bool:
    return isinstance(valor, int) and not isinstance(valor, bool)


def _es_numero(valor) -> bool:
    return (isinstance(valor, (int, float)) and not isinstance(valor, bool)
            and math.isfinite(valor))


def exigir_objeto(datos):
    if not isinstance(datos, dict):
        raise ErrorValidacion({"cuerpo": "El cuerpo debe ser un objeto JSON"},
                              "Formato de solicitud inválido")
    return datos


def _texto(datos, campo, errores, etiqueta):
    """Lee un texto obligatorio. Devuelve el texto recortado o None."""
    valor = datos.get(campo)
    if _vacio(valor):
        errores[campo] = f"{etiqueta} es obligatorio y no puede estar vacío"
        return None
    if not isinstance(valor, str):
        errores[campo] = f"{etiqueta} debe ser texto"
        return None
    return " ".join(valor.split())


def validar_nombre(valor):
    if not RE_NOMBRE.match(valor):
        return "Solo se permiten letras y espacios"
    letras = sum(1 for c in valor if c.isalpha())
    if letras < NOMBRE_MIN_LETRAS:
        return f"Debe tener más de {NOMBRE_MIN_LETRAS - 1} letras"
    if len(valor) > NOMBRE_MAX:
        return f"Máximo {NOMBRE_MAX} caracteres"
    return None


def validar_email(valor):
    if len(valor) > 120:
        return "Máximo 120 caracteres"
    if ".." in valor or not RE_EMAIL.match(valor):
        return "No es un correo válido (ejemplo: nombre@correo.com)"
    return None


def validar_password(valor):
    if len(valor) < 8 or len(valor) > 64:
        return "Debe tener entre 8 y 64 caracteres"
    faltan = []
    if not re.search(r"[a-z]", valor):
        faltan.append("una minúscula")
    if not re.search(r"[A-Z]", valor):
        faltan.append("una mayúscula")
    if not re.search(r"\d", valor):
        faltan.append("un número")
    if not re.search(r"[^A-Za-z0-9]", valor):
        faltan.append("un símbolo")
    if faltan:
        return "Le falta " + ", ".join(faltan)
    return None


def _entero(datos, campo, errores, etiqueta, minimo, maximo):
    valor = datos.get(campo)
    if valor is None:
        errores[campo] = f"{etiqueta} es obligatorio"
        return None
    if not _es_entero(valor):
        errores[campo] = f"{etiqueta} debe ser un número entero"
        return None
    if not minimo <= valor <= maximo:
        errores[campo] = f"{etiqueta} debe estar entre {minimo:,} y {maximo:,}".replace(",", ".")
        return None
    return valor


def _opcion(datos, campo, errores, etiqueta, opciones):
    valor = _texto(datos, campo, errores, etiqueta)
    if valor is None:
        return None
    if valor not in opciones:
        errores[campo] = f"{etiqueta} debe ser uno de: {', '.join(opciones)}"
        return None
    return valor


# =============================================================================
#  Cuentas
# =============================================================================

def validar_registro(datos):
    exigir_objeto(datos)
    errores = {}

    nombre = _texto(datos, "nombre", errores, "El nombre")
    if nombre and (error := validar_nombre(nombre)):
        errores["nombre"] = error

    email = _texto(datos, "email", errores, "El correo")
    if email:
        email = email.lower()
        if error := validar_email(email):
            errores["email"] = error

    telefono = _texto(datos, "telefono", errores, "El celular")
    if telefono:
        telefono = re.sub(r"[\s-]", "", telefono)
        if not RE_TELEFONO.match(telefono):
            errores["telefono"] = "Debe ser un celular colombiano de 10 dígitos que empiece por 3"

    password = datos.get("password")
    if _vacio(password):
        errores["password"] = "La contraseña es obligatoria"
    elif not isinstance(password, str):
        errores["password"] = "La contraseña debe ser texto"
    elif error := validar_password(password):
        errores["password"] = error

    confirmacion = datos.get("confirmacion")
    if _vacio(confirmacion):
        errores["confirmacion"] = "Confirma la contraseña"
    elif confirmacion != password:
        errores["confirmacion"] = "Las contraseñas no coinciden"

    if errores:
        raise ErrorValidacion(errores)
    return {"nombre": nombre, "email": email, "telefono": telefono, "password": password}


def validar_login(datos):
    exigir_objeto(datos)
    errores = {}
    email = _texto(datos, "email", errores, "El correo")
    if email:
        email = email.lower()
        if error := validar_email(email):
            errores["email"] = error
    password = datos.get("password")
    if _vacio(password) or not isinstance(password, str):
        errores["password"] = "La contraseña es obligatoria"
    if errores:
        raise ErrorValidacion(errores)
    return {"email": email, "password": password}


# =============================================================================
#  Transacciones (formato de la diapositiva 40)
# =============================================================================

def validar_transaccion(datos):
    """Devuelve la transacción limpia. Los valores crudos se conservan en
    `datos` para verificar el hash tal como los firmó el emisor."""
    exigir_objeto(datos)
    errores = {}

    for campo in ("idTxn", "user", "date", "value", "paymentMethod", "hash"):
        if _vacio(datos.get(campo)):
            errores[campo] = "Es obligatorio y no puede ser nulo ni vacío"

    id_txn = datos.get("idTxn")
    if "idTxn" not in errores:
        if _es_entero(id_txn) and id_txn > 0:
            id_txn = str(id_txn)
        elif isinstance(id_txn, str) and RE_ID_TXN.match(id_txn.strip()):
            id_txn = id_txn.strip()
        else:
            errores["idTxn"] = "Debe ser un entero positivo o un código alfanumérico de hasta 40 caracteres"

    email = datos.get("user")
    if "user" not in errores:
        if not isinstance(email, str):
            errores["user"] = "Debe ser un correo electrónico"
        else:
            email = email.strip().lower()
            if error := validar_email(email):
                errores["user"] = error

    fecha = None
    if "date" not in errores:
        if not isinstance(datos["date"], str):
            errores["date"] = "Debe ser texto con formato ISO 8601"
        else:
            try:
                fecha = interpretar_fecha_externa(datos["date"].strip())
            except ValueError:
                errores["date"] = "Formato esperado: 2026-09-23T10:30:01.120"
            else:
                if fecha > ahora() + timedelta(days=1):
                    errores["date"] = "La fecha no puede estar en el futuro"

    valor = datos.get("value")
    if "value" not in errores:
        if not _es_numero(valor):
            errores["value"] = "Debe ser un número (no texto ni booleano)"
        elif valor <= 0:
            errores["value"] = "Debe ser mayor que cero"
        elif valor > VALOR_MAXIMO_TRANSACCION:
            errores["value"] = "Supera el máximo permitido de $50.000.000"
        elif round(valor, 2) != valor:
            errores["value"] = "Máximo dos decimales"

    metodo = datos.get("paymentMethod")
    if "paymentMethod" not in errores:
        if not isinstance(metodo, str) or metodo.strip() not in METODOS_PAGO:
            errores["paymentMethod"] = f"Debe ser uno de: {', '.join(METODOS_PAGO)}"
        else:
            metodo = metodo.strip()

    hash_recibido = datos.get("hash")
    if "hash" not in errores:
        if not isinstance(hash_recibido, str) or len(hash_recibido) > 128:
            errores["hash"] = "Debe ser texto hexadecimal (SHA-256 = 64 caracteres)"

    if errores:
        raise ErrorValidacion(errores, "La transacción no cumple el formato esperado")

    return {
        "id_txn": id_txn,
        "email": email,
        "fecha": fecha,
        "valor": valor,
        "metodo_pago": metodo,
        "hash": hash_recibido.strip(),
    }


# =============================================================================
#  Pedidos de la tienda
# =============================================================================

def validar_pedido(datos, sabores, barrios, max_adiciones):
    exigir_objeto(datos)
    errores = {}

    items = datos.get("items")
    items_limpios = []
    if not isinstance(items, list) or not items:
        errores["items"] = "El carrito está vacío"
    elif len(items) > 20:
        errores["items"] = "Máximo 20 productos distintos por pedido"
    else:
        for posicion, item in enumerate(items):
            prefijo = f"items[{posicion}]"
            if not isinstance(item, dict):
                errores[prefijo] = "Formato inválido"
                continue
            errores_item = {}
            producto_id = _entero(item, "producto_id", errores_item, "El producto", 1, 10 ** 9)
            cantidad = _entero(item, "cantidad", errores_item, "La cantidad", 1, 10)
            precio = _entero(item, "precio_unitario", errores_item, "El precio", 0, 10 ** 7)
            sabor = _opcion(item, "sabor", errores_item, "El sabor", sabores)
            adiciones = item.get("adiciones")
            if not isinstance(adiciones, list):
                errores_item["adiciones"] = "Debe ser una lista (puede estar vacía)"
            elif len(adiciones) > max_adiciones:
                errores_item["adiciones"] = f"Máximo {max_adiciones} adiciones por granizado"
            elif not all(_es_entero(a) and a > 0 for a in adiciones):
                errores_item["adiciones"] = "Adiciones inválidas"
            elif len(set(adiciones)) != len(adiciones):
                errores_item["adiciones"] = "No repitas la misma adición"
            for campo, mensaje in errores_item.items():
                errores[f"{prefijo}.{campo}"] = mensaje
            if not errores_item:
                items_limpios.append({
                    "producto_id": producto_id, "cantidad": cantidad, "sabor": sabor,
                    "adiciones": sorted(adiciones), "precio_unitario": precio,
                })

    tipo_entrega = _opcion(datos, "tipo_entrega", errores, "El tipo de entrega", ("DOMICILIO", "RECOGER"))
    barrio = direccion = None
    if tipo_entrega == "DOMICILIO":
        barrio = _opcion(datos, "barrio", errores, "El barrio", barrios)
        direccion = _texto(datos, "direccion", errores, "La dirección")
        if direccion:
            if len(direccion) < 6 or len(direccion) > 120:
                errores["direccion"] = "Entre 6 y 120 caracteres"
            elif not RE_DIRECCION.match(direccion):
                errores["direccion"] = "Solo letras, números y # . , - /"
            elif not re.search(r"\d", direccion):
                errores["direccion"] = "Incluye el número de la dirección"

    metodo = _opcion(datos, "metodo_pago", errores, "El método de pago", METODOS_PAGO)
    total = _entero(datos, "total", errores, "El total", 0, 10 ** 8)

    if errores:
        raise ErrorValidacion(errores)
    return {
        "items": items_limpios, "tipo_entrega": tipo_entrega, "barrio": barrio,
        "direccion": direccion, "metodo_pago": metodo, "total": total,
    }


# =============================================================================
#  Productos (CRUD de la diapositiva 3)
# =============================================================================

CAMPOS_PRODUCTO = ("nombre", "descripcion", "categoria", "precio", "onzas", "imagen", "activo")


def validar_producto(datos, imagenes_permitidas, parcial=False):
    """parcial=False -> PUT/POST: deben venir todos los campos.
    parcial=True  -> PATCH: solo los que se quieren cambiar."""
    exigir_objeto(datos)
    desconocidos = set(datos) - set(CAMPOS_PRODUCTO)
    if desconocidos:
        raise ErrorValidacion({c: "Campo desconocido" for c in sorted(desconocidos)})
    if parcial and not datos:
        raise ErrorValidacion({"cuerpo": "Envía al menos un campo para actualizar"})

    errores = {}
    limpio = {}

    def pedir(campo):
        return not parcial or campo in datos

    if pedir("nombre"):
        nombre = _texto(datos, "nombre", errores, "El nombre")
        if nombre:
            if not 3 <= len(nombre) <= 60 or not RE_TEXTO_PRODUCTO.match(nombre):
                errores["nombre"] = "Entre 3 y 60 caracteres: letras, números y . , ( ) -"
            else:
                limpio["nombre"] = nombre
    if pedir("descripcion"):
        descripcion = _texto(datos, "descripcion", errores, "La descripción")
        if descripcion:
            if not 5 <= len(descripcion) <= 200 or not RE_TEXTO_PRODUCTO.match(descripcion):
                errores["descripcion"] = "Entre 5 y 200 caracteres: letras, números y . , ( ) % -"
            else:
                limpio["descripcion"] = descripcion
    if pedir("categoria"):
        categoria = _opcion(datos, "categoria", errores, "La categoría", ("GRANIZADO", "ADICION"))
        if categoria:
            limpio["categoria"] = categoria
    if pedir("precio"):
        precio = _entero(datos, "precio", errores, "El precio", 500, 500_000)
        if precio is not None:
            if precio % 100:
                errores["precio"] = "Debe ser múltiplo de $100"
            else:
                limpio["precio"] = precio
    if pedir("onzas"):
        onzas = datos.get("onzas")
        if onzas is None:
            limpio["onzas"] = None       # las adiciones no tienen onzas
        elif not _es_entero(onzas) or not 4 <= onzas <= 40:
            errores["onzas"] = "Debe ser un entero entre 4 y 40, o null para adiciones"
        else:
            limpio["onzas"] = onzas
    if pedir("imagen"):
        imagen = datos.get("imagen")
        if imagen is None:
            limpio["imagen"] = None
        elif imagen not in imagenes_permitidas:
            errores["imagen"] = f"Debe ser una de: {', '.join(imagenes_permitidas)}"
        else:
            limpio["imagen"] = imagen
    if pedir("activo"):
        if not isinstance(datos.get("activo"), bool):
            errores["activo"] = "Debe ser true o false"
        else:
            limpio["activo"] = datos["activo"]

    if errores:
        raise ErrorValidacion(errores)
    return limpio


# =============================================================================
#  Reglas del detector (configurables con PUT y PATCH)
# =============================================================================

def _ventana_y_umbral(bloque, prefijo, errores):
    if not isinstance(bloque, dict):
        errores[prefijo] = "Debe ser un objeto"
        return None
    sub = {}
    ventana = bloque.get("ventana_segundos")
    if not _es_numero(ventana) or not 0.5 <= ventana <= 600:
        sub["ventana_segundos"] = "Entre 0.5 y 600 segundos"
    umbral = bloque.get("umbral")
    if not _es_entero(umbral) or not 2 <= umbral <= 100:
        sub["umbral"] = "Entero entre 2 y 100"
    for campo, mensaje in sub.items():
        errores[f"{prefijo}.{campo}"] = mensaje
    return None if sub else {"ventana_segundos": ventana, "umbral": umbral}


def validar_reglas(datos, actuales, parcial=False):
    """PUT reemplaza la configuración completa; PATCH mezcla solo lo enviado."""
    exigir_objeto(datos)
    permitidos = {"modo", "regla_fija", "franjas", "rafaga", "monto_atipico"}
    desconocidos = set(datos) - permitidos
    if desconocidos:
        raise ErrorValidacion({c: "Campo desconocido" for c in sorted(desconocidos)})
    if not parcial:
        faltan = permitidos - set(datos)
        if faltan:
            raise ErrorValidacion({c: "Obligatorio en PUT (usa PATCH para cambios parciales)" for c in sorted(faltan)})

    errores = {}
    nuevas = {**actuales}

    if "modo" in datos:
        if datos["modo"] not in ("FIJA", "FRANJAS"):
            errores["modo"] = "Debe ser FIJA o FRANJAS"
        else:
            nuevas["modo"] = datos["modo"]

    if "regla_fija" in datos:
        bloque = _ventana_y_umbral(datos["regla_fija"], "regla_fija", errores)
        if bloque:
            nuevas["regla_fija"] = bloque

    if "franjas" in datos:
        franjas = datos["franjas"]
        claves = [f["clave"] for f in actuales["franjas"]]
        if not isinstance(franjas, list) or len(franjas) != len(claves):
            errores["franjas"] = f"Debe traer las {len(claves)} franjas: {', '.join(claves)}"
        else:
            nuevas_franjas = []
            for franja_actual, enviada in zip(actuales["franjas"], franjas):
                prefijo = f"franjas.{franja_actual['clave']}"
                if not isinstance(enviada, dict) or enviada.get("clave") != franja_actual["clave"]:
                    errores[prefijo] = f"Se esperaba la franja '{franja_actual['clave']}' en esta posición"
                    continue
                bloque = _ventana_y_umbral(enviada, prefijo, errores)
                if bloque:
                    nuevas_franjas.append({**franja_actual, **bloque})
            if len(nuevas_franjas) == len(claves):
                nuevas["franjas"] = nuevas_franjas

    if "rafaga" in datos:
        rafaga = datos["rafaga"]
        if not isinstance(rafaga, dict):
            errores["rafaga"] = "Debe ser un objeto"
        else:
            maximo = rafaga.get("maximo")
            ventana = rafaga.get("ventana_segundos")
            if not _es_entero(maximo) or not 2 <= maximo <= 100:
                errores["rafaga.maximo"] = "Entero entre 2 y 100"
            if not _es_numero(ventana) or not 0.1 <= ventana <= 60:
                errores["rafaga.ventana_segundos"] = "Entre 0.1 y 60 segundos"
            if "rafaga.maximo" not in errores and "rafaga.ventana_segundos" not in errores:
                nuevas["rafaga"] = {"maximo": maximo, "ventana_segundos": ventana}

    if "monto_atipico" in datos:
        monto = datos["monto_atipico"]
        if not _es_entero(monto) or not 10_000 <= monto <= VALOR_MAXIMO_TRANSACCION:
            errores["monto_atipico"] = "Entero entre 10.000 y 50.000.000"
        else:
            nuevas["monto_atipico"] = monto

    if errores:
        raise ErrorValidacion(errores)
    return nuevas
