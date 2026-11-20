"""
Análisis: ventas, calidad de datos, benchmark de algoritmos y estadística.

    GET  /api/ventas                      indicadores, patrones y predicción de demanda   administrador
    GET  /api/calidad/auditoria           puntaje de calidad y problemas encontrados       administrador
    POST /api/calidad/corregir            corrección automática                            administrador
    POST /api/calidad/importar            CSV o JSON (multipart: archivo, tipo, aplicar)   administrador
    GET  /api/calidad/ejemplo/<archivo>   archivos sucios de ejemplo (datos/)
    GET  /api/benchmark                   último resultado del análisis experimental
    POST /api/benchmark                   correr el benchmark rápido (unos segundos)       administrador
    GET  /api/estadistica/usuarios        clientes y empleados para elegir                 administrador
    GET  /api/estadistica/usuarios/<id>   perfil estadístico (cuartiles, z, por hora...)   administrador
    GET  /api/estadistica/empleados       descuentos y anulaciones por empleado            administrador
"""

from pathlib import Path

from flask import Blueprint, request, send_file

from ..db import obtener_db
from ..errores import ErrorNoEncontrado, ErrorValidacion
from ..registro import logger
from ..seguridad import admin_requerido, exigir_csrf, revisar_inyeccion
from ..servicios import benchmark, calidad, estadistica, ventas
from . import entero_de_consulta, estado_app, ok

bp = Blueprint("api_analisis", __name__, url_prefix="/api")
EJEMPLOS = {"clientes_sucios.csv": "text/csv", "items_sucios.json": "application/json"}
CARPETA_DATOS = Path(__file__).resolve().parents[2] / "datos"


@bp.get("/ventas")
@admin_requerido
def resumen_ventas():
    resumen = ventas.resumen(obtener_db(), entero_de_consulta("dias", 30, 7, 90))
    demanda = estado_app().demanda
    resumen["prediccion_red"] = demanda.pronosticar(resumen["serie"][:-1]) if demanda else None
    resumen["modelo_demanda"] = demanda.metadatos["error_promedio"] if demanda else None
    return ok(resumen)


@bp.get("/calidad/auditoria")
@admin_requerido
def auditoria():
    db = obtener_db()
    return ok({"auditoria": calidad.auditar(db), "historial": calidad.historial(db)})


@bp.post("/calidad/corregir")
@admin_requerido
@exigir_csrf
def corregir():
    return ok(calidad.corregir(obtener_db()))


@bp.post("/calidad/importar")
@admin_requerido
@exigir_csrf
def importar():
    archivo = request.files.get("archivo")
    tipo = request.form.get("tipo")
    if not archivo or not archivo.filename:
        raise ErrorValidacion({"archivo": "Adjunta un archivo CSV o JSON"})
    if tipo not in calidad.ESQUEMAS:
        raise ErrorValidacion({"tipo": "Debe ser clientes o items"})
    nombre = Path(archivo.filename).name[:80]
    revisar_inyeccion({"archivo": nombre})
    try:
        registros = calidad.leer_archivo(archivo.read(), nombre)
        reporte = calidad.importar(obtener_db(), registros, tipo, nombre, aplicar=request.form.get("aplicar") == "1")
    except (ValueError, UnicodeDecodeError) as error:
        raise ErrorValidacion({"archivo": f"No se pudo leer: {error}"}) from None
    if reporte["aplicado"]:
        estado_app().reconstruir(obtener_db())        # el índice de usuarios incluye los importados
    return ok({"reporte": reporte})


@bp.get("/calidad/ejemplo/<nombre>")
def ejemplo(nombre):
    if nombre not in EJEMPLOS:
        raise ErrorNoEncontrado("No existe ese archivo de ejemplo")
    return send_file(CARPETA_DATOS / nombre, mimetype=EJEMPLOS[nombre], as_attachment=True, download_name=nombre)


@bp.get("/benchmark")
def ver_benchmark():
    db = obtener_db()
    tipo = request.args.get("tipo")
    resultado = benchmark.ultimo(db, tipo if tipo in ("COMPLETO", "RAPIDO") else None) or benchmark.ultimo(db)
    return ok({"benchmark": resultado})


@bp.post("/benchmark")
@admin_requerido
@exigir_csrf
def correr_benchmark():
    db = obtener_db()
    resultado = benchmark.correr(db, "RAPIDO")
    resultado["id"] = benchmark.guardar(db, resultado)
    logger.info("Benchmark rápido en %.1f s", resultado["duracion_s"])
    return ok({"benchmark": resultado}, 201)


@bp.get("/estadistica/usuarios")
@admin_requerido
def usuarios_para_perfil():
    busqueda = (request.args.get("q") or "").strip()[:60]
    if busqueda:
        revisar_inyeccion({"q": busqueda})
    filas = obtener_db().execute(
        """SELECT u.id, u.nombre, u.email, u.rol, COUNT(t.id) AS transacciones FROM usuarios u
           LEFT JOIN transacciones t ON t.usuario_id = u.id
           WHERE u.estado != 'INACTIVO' AND (u.nombre LIKE ? OR u.email LIKE ?)
           GROUP BY u.id ORDER BY u.rol = 'CLIENTE', transacciones DESC LIMIT 60""",
        (f"%{busqueda}%", f"%{busqueda}%")).fetchall()
    return ok({"usuarios": [dict(f) for f in filas]})


@bp.get("/estadistica/usuarios/<int:usuario_id>")
@admin_requerido
def perfil_usuario(usuario_id):
    perfil = estadistica.perfil_completo(obtener_db(), usuario_id)
    if perfil is None:
        raise ErrorNoEncontrado(f"No existe el usuario {usuario_id}")
    return ok({"perfil": perfil})


@bp.get("/estadistica/empleados")
@admin_requerido
def empleados():
    db = obtener_db()
    momento = db.execute("SELECT COALESCE(MAX(fecha_emision), datetime('now')) FROM facturas").fetchone()[0]
    return ok({"empleados": estadistica.ranking_empleados(db),
               "serie": estadistica.serie_empleados(db, momento)[-120:],
               "config": {"minimo_dias": estadistica.MINIMO_DIAS, "minimo_eventos": estadistica.MINIMO_EVENTOS}})
