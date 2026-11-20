"""
Caja: pedidos de cualquier canal, facturas, pagos con comprobante e integridad.

    POST /api/caja/pedidos                 pedido con varios ítems, canal y descuento    personal
    GET  /api/caja/pedidos                 todos los pedidos (filtros: canal, estado)    personal
    GET  /api/facturas                     facturas (filtros: estado, canal, q)          personal
    GET  /api/facturas/<id>                factura con ítems y pagos                     personal
    POST /api/facturas/<id>/pagos          pago (multipart, con comprobante opcional)   personal
    POST /api/facturas/<id>/anular         anulación con motivo                          personal
    GET  /api/pagos/<id>/comprobante       descargar el comprobante                      personal
    GET  /api/comprobantes/prueba          PDF que entregaría la pasarela (laboratorio)
    GET  /api/integridad                   verificar las cadenas de facturas y pagos     administrador
    POST /api/integridad/alterar           laboratorio: cambiar una factura a escondidas  administrador
    POST /api/integridad/restaurar         deshacer lo anterior                          administrador
"""

from flask import Blueprint, current_app, request, send_file

from ..db import obtener_db
from ..errores import ErrorNoEncontrado, ErrorProhibido, ErrorValidacion
from ..seguridad import admin_requerido, exigir_csrf, personal_requerido, revisar_inyeccion, usuario_actual
from ..servicios import catalogo, comprobantes, domicilios, facturacion, integridad, pagos, pedidos
from ..validaciones import CANALES, METODOS_PAGO, exigir_objeto, validar_anulacion, validar_pago, validar_pedido_caja
from . import entero_de_consulta, estado_app, ip_cliente, leer_json, ok

bp = Blueprint("api_caja", __name__, url_prefix="/api")


@bp.post("/caja/pedidos")
@personal_requerido
@exigir_csrf
def crear_pedido():
    datos = leer_json()
    revisar_inyeccion(datos)
    limpio = validar_pedido_caja(datos, tuple(domicilios.BARRIOS), catalogo.MAX_ADICIONES)
    resultado = pedidos.crear_en_caja(obtener_db(), estado_app(), current_app.config, usuario_actual(), limpio)
    return ok(resultado, 201)


@bp.get("/caja/pedidos")
@personal_requerido
def listar_pedidos():
    canal = request.args.get("canal")
    estado = request.args.get("estado") or None
    return ok(pedidos.listar(obtener_db(), canal if canal in CANALES else None, estado,
                             entero_de_consulta("pagina", 1, 1, 10_000)))


@bp.get("/facturas")
@personal_requerido
def listar_facturas():
    canal = request.args.get("canal")
    estado = request.args.get("estado")
    busqueda = (request.args.get("q") or "").strip()[:60] or None
    if busqueda:
        revisar_inyeccion({"q": busqueda})
    return ok(facturacion.listar(obtener_db(), estado if estado in ("EMITIDA", "PAGADA", "ANULADA") else None,
                                 canal if canal in CANALES else None, busqueda,
                                 entero_de_consulta("pagina", 1, 1, 10_000)))


@bp.get("/facturas/<int:factura_id>")
@personal_requerido
def obtener_factura(factura_id):
    return ok({"factura": facturacion.obtener(obtener_db(), factura_id)})


@bp.post("/facturas/<int:factura_id>/pagos")
@personal_requerido
@exigir_csrf
def registrar_pago(factura_id):
    """multipart/form-data: metodo, monto, referencia (opcional) y comprobante (archivo opcional)."""
    datos = validar_pago(request.form)
    revisar_inyeccion({k: v for k, v in datos.items() if isinstance(v, str)})
    archivo = request.files.get("comprobante")
    adjunto = None
    if archivo and archivo.filename:
        contenido = archivo.read(current_app.config["COMPROBANTE_MAX_BYTES"] + 1)
        adjunto = (contenido, archivo.filename)
    resultado = pagos.registrar(obtener_db(), estado_app(), current_app.config, factura_id, datos, adjunto,
                                quien=usuario_actual(), ip=ip_cliente())
    return ok({"pago": resultado}, 201)


@bp.post("/facturas/<int:factura_id>/anular")
@personal_requerido
@exigir_csrf
def anular_factura(factura_id):
    datos = leer_json()
    revisar_inyeccion(datos)
    motivo = validar_anulacion(datos)
    return ok({"factura": facturacion.anular(obtener_db(), estado_app(), factura_id, motivo, usuario_actual())})


@bp.get("/pagos/<int:pago_id>/comprobante")
@personal_requerido
def descargar_comprobante(pago_id):
    fila = obtener_db().execute("SELECT comprobante_sha256, comprobante_nombre, comprobante_tipo FROM pagos WHERE id = ?",
                                (pago_id,)).fetchone()
    archivo = fila and comprobantes.buscar_archivo(current_app.config["CARPETA_COMPROBANTES"], fila["comprobante_sha256"])
    if not archivo:
        raise ErrorNoEncontrado("Ese pago no tiene comprobante")
    # Siempre como descarga y con su tipo real: el navegador nunca lo ejecuta.
    return send_file(archivo, mimetype=fila["comprobante_tipo"], as_attachment=True,
                     download_name=fila["comprobante_nombre"] or archivo.name)


@bp.get("/comprobantes/prueba")
def comprobante_de_prueba():
    """Lo que entregaría Nequi, Daviplata o PSE después de pagar. ?alterar=1 da uno falsificado."""
    if not current_app.config["MODO_LABORATORIO"]:
        raise ErrorProhibido("El modo laboratorio está apagado")
    metodo = request.args.get("metodo", "Nequi")
    monto = request.args.get("monto", "")
    pagador = (request.args.get("pagador") or "Cliente de prueba").strip()[:60]
    if metodo not in METODOS_PAGO or not monto.isdigit() or not 100 <= int(monto) <= 50_000_000:
        raise ErrorValidacion({"monto": "Indica metodo (Nequi, PSE...) y un monto entero"})
    revisar_inyeccion({"pagador": pagador})
    pdf, referencia = pagos.comprobante_de_prueba(current_app.config, metodo, int(monto), pagador,
                                                  alterar=request.args.get("alterar") == "1")
    from io import BytesIO
    return send_file(BytesIO(pdf), mimetype="application/pdf", as_attachment=True,
                     download_name=f"comprobante-{referencia}.pdf")


@bp.get("/integridad")
@admin_requerido
def verificar_integridad():
    config = current_app.config
    db = obtener_db()
    resultado = integridad.verificar_todo(db, config["LLAVE_INTEGRIDAD"], config["CARPETA_COMPROBANTES"])
    # Los últimos bloques de la cadena de facturas, para dibujarla.
    rotos = {p["id"] for p in resultado["facturas"]["problemas"]}
    alterada = min((p["id"] for p in resultado["facturas"]["problemas"]), default=None)
    filas = db.execute(
        """SELECT * FROM (SELECT id, numero, total, fecha_emision, hash, hash_anterior FROM facturas
           WHERE id >= COALESCE(?, 0) ORDER BY id DESC LIMIT 7) ORDER BY id""" if alterada else
        """SELECT * FROM (SELECT id, numero, total, fecha_emision, hash, hash_anterior FROM facturas
           ORDER BY id DESC LIMIT 7) ORDER BY id""", (alterada - 2,) if alterada else ()).fetchall()
    resultado["cadena"] = [{**dict(f), "codigo": facturacion.numero_visible(f["numero"]), "roto": f["id"] in rotos}
                           for f in filas]
    return ok(resultado)


@bp.post("/integridad/alterar")
@admin_requerido
@exigir_csrf
def alterar():
    if not current_app.config["MODO_LABORATORIO"]:
        raise ErrorProhibido("El modo laboratorio está apagado")
    datos = exigir_objeto(leer_json())
    numero = datos.get("numero")
    nuevo_total = datos.get("total")
    if not isinstance(numero, int) or not isinstance(nuevo_total, int) or nuevo_total < 0:
        raise ErrorValidacion({"numero": "numero y total deben ser enteros"})
    cambio = integridad.alterar_factura(obtener_db(), numero, nuevo_total)
    if cambio is None:
        raise ErrorNoEncontrado(f"No existe la factura FV-{numero:06d}")
    return ok({"cambio": cambio})


@bp.post("/integridad/restaurar")
@admin_requerido
@exigir_csrf
def restaurar():
    return ok({"restauradas": integridad.restaurar_manipulaciones(obtener_db())})
