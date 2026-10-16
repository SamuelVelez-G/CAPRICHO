"""
Exporta una demo ESTÁTICA del proyecto a docs/ para publicarla en GitHub Pages.

GitHub Pages solo sirve archivos: no ejecuta Python. Este script arranca la
aplicación con datos de demostración en una base temporal, guarda cada página
como HTML y cada consulta GET de la API como un archivo JSON. En el navegador,
comun.js detecta data-estatico="1" y lee esos archivos en vez de llamar al
servidor; lo que necesita enviar datos (pagar, el laboratorio) avisa que en la
demo estática no se puede.

    python herramientas/exportar_demo.py

Después: commit + push de docs/, y en GitHub, Settings > Pages >
"Deploy from a branch" > main > /docs.
"""

import json
import logging
import re
import shutil
import sys
import tempfile
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from capricho import create_app  # noqa: E402
from capricho.registro import logger  # noqa: E402
from capricho.servicios import anomalias, detector, domicilios, estadisticas  # noqa: E402

DESTINO = RAIZ / "docs"
CONSERVAR = {"capturas"}            # carpetas de docs/ que no se borran al exportar
PAGINAS = {"/": "index.html", "/laboratorio": "laboratorio.html", "/dashboard": "dashboard.html",
           "/operacion": "operacion.html", "/pagar": "pagar.html", "/ingresar": "ingresar.html",
           "/registro": "registro.html", "/mis-pedidos": "index.html"}
MAX_PAGINAS_TRANSACCIONES = 8

AVISO = """<div class="aviso-estatico" role="note"><div class="contenedor">
  <svg class="icono" aria-hidden="true"><use href="static/img/iconos.svg#info"></use></svg>
  <span>Demo estática en GitHub Pages con datos de demostración: se puede recorrer todo, pero no enviar
  transacciones ni pagar. Para probar el detector en vivo ejecuta el proyecto con <code>python run.py</code>.</span>
</div></div>"""


def archivo_estatico(url):
    """El mismo nombre que calcula archivoEstatico() en comun.js."""
    partes = urlsplit(url)
    parametros = sorted((k, v) for k, v in parse_qsl(partes.query, keep_blank_values=True)
                        if k not in ("fuente", "por"))
    nombre = re.sub(r"^/api/", "", partes.path).replace("/", "_")
    if parametros:
        nombre += "__" + "_".join(f"{k}-{v}" for k, v in parametros)
    return "api/" + re.sub(r"[^A-Za-z0-9_-]", "_", nombre) + ".json"


def a_estatico(html):
    """Rutas del servidor -> rutas relativas, para que funcione en /CAPRICHO/."""
    html = html.replace('"/static/', '"static/')

    def enlace(coincidencia):
        partes = urlsplit(coincidencia.group(1))
        pagina = PAGINAS.get(partes.path)
        if pagina is None:
            return coincidencia.group(0)
        return f'href="{pagina}{"#" + partes.fragment if partes.fragment else ""}"'

    html = re.sub(r'href="(/[^"]*)"', enlace, html)
    html = html.replace("<body ", '<body data-estatico="1" ', 1)
    return html.replace("</header>", "</header>\n" + AVISO, 1)


class Exportador:
    def __init__(self, cliente):
        self.cliente = cliente
        self.archivos = 0

    def json(self, url):
        respuesta = self.cliente.get(url)
        if respuesta.status_code != 200:
            raise RuntimeError(f"{url} respondió {respuesta.status_code}: {respuesta.get_data(as_text=True)[:200]}")
        datos = respuesta.get_json()
        destino = DESTINO / archivo_estatico(url)
        destino.write_text(json.dumps(datos, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        self.archivos += 1
        return datos

    def pagina(self, ruta):
        respuesta = self.cliente.get(ruta)
        if respuesta.status_code != 200:
            raise RuntimeError(f"{ruta} respondió {respuesta.status_code}")
        (DESTINO / PAGINAS[ruta]).write_text(a_estatico(respuesta.get_data(as_text=True)), encoding="utf-8")


def limpiar_destino():
    DESTINO.mkdir(exist_ok=True)
    for elemento in DESTINO.iterdir():
        if elemento.name in CONSERVAR:
            continue
        shutil.rmtree(elemento) if elemento.is_dir() else elemento.unlink()
    (DESTINO / "api").mkdir()
    (DESTINO / ".nojekyll").write_text("", encoding="utf-8")   # que Pages sirva los archivos tal cual


def main():
    temporal = Path(tempfile.mkdtemp(prefix="capricho_demo_"))
    logger.setLevel(logging.ERROR)
    app = create_app({"BASE_DATOS": str(temporal / "demo.db"), "CARPETA_LOGS": str(temporal / "logs"),
                      "TESTING": True, "LIMITE_PETICIONES_POR_SEGUNDO": 100000})
    app.extensions["capricho"].limitador_ip.maximo = 100000
    cliente = app.test_client()
    limpiar_destino()
    shutil.copytree(RAIZ / "capricho" / "static", DESTINO / "static")
    exportar = Exportador(cliente)

    # Páginas que solo se ven sin sesión.
    for ruta in ("/ingresar", "/registro"):
        exportar.pagina(ruta)

    csrf = cliente.get("/api/auth/yo").get_json()["csrf"]
    respuesta = cliente.post("/api/auth/login", json={"email": app.config["ADMIN_EMAIL"],
                                                      "password": app.config["ADMIN_PASSWORD"]},
                             headers={"X-CSRF-Token": csrf})
    assert respuesta.status_code == 200, respuesta.get_json()
    for ruta in ("/", "/laboratorio", "/dashboard", "/operacion", "/pagar"):
        exportar.pagina(ruta)

    # Consultas sueltas.
    for url in ("/api/productos", "/api/productos?todos=1", "/api/configuracion", "/api/domicilios/mapa",
                "/api/eventos", "/api/pedidos/cola", "/api/auth/yo"):
        exportar.json(url)
    for barrio in domicilios.BARRIOS:
        exportar.json("/api/domicilios/cotizar?" + urlencode({"barrio": barrio}))

    # Dashboard y tablas: la fuente queda fija en "demo" (es lo único que hay).
    filtros_anomalias = [{}] + [{"estado": e} for e in anomalias.ESTADOS] + \
        [{"nivel": n} for n in detector.NIVELES] + [{"tipo": t} for t in detector.TIPOS_ANOMALIA]
    for rango in estadisticas.RANGOS:
        base = {"fuente": "demo", "rango": rango, "por": "txn"}
        exportar.json("/api/dashboard?" + urlencode(base))
        for extra in filtros_anomalias:
            pagina, paginas = 1, 1
            while pagina <= paginas:
                datos = exportar.json("/api/anomalias?" + urlencode({**base, "pagina": pagina, **extra}))
                paginas = datos["paginas"]
                pagina += 1
        for extra in ({}, {"estado": "APROBADA"}, {"estado": "SOSPECHOSA"}, {"estado": "RECHAZADA"}):
            pagina, paginas = 1, 1
            while pagina <= min(paginas, MAX_PAGINAS_TRANSACCIONES):
                datos = exportar.json("/api/transacciones?" + urlencode({**base, "pagina": pagina, **extra}))
                paginas = datos["paginas"]
                pagina += 1

    # Detalle de cada anomalía (línea de tiempo y ventana deslizante).
    from capricho.db import conectar
    conexion = conectar(app.config["BASE_DATOS"])
    for (anomalia_id,) in conexion.execute("SELECT id FROM anomalias"):
        exportar.json(f"/api/anomalias/{anomalia_id}")

    # Búsqueda por índice: un solo archivo con el diccionario idTxn -> respuesta.
    indice = {}
    for (id_txn,) in conexion.execute("SELECT id_txn FROM transacciones"):
        indice[id_txn] = cliente.get(f"/api/transacciones/{id_txn}").get_json()
    conexion.close()
    (DESTINO / "api" / "indice_transacciones.json").write_text(
        json.dumps(indice, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")

    tamano = sum(f.stat().st_size for f in DESTINO.rglob("*") if f.is_file()) / 1024 / 1024
    print(f"Demo estática exportada en {DESTINO}: {exportar.archivos + 1} consultas JSON, "
          f"{len(set(PAGINAS.values()))} páginas, {tamano:.1f} MB")
    shutil.rmtree(temporal, ignore_errors=True)


if __name__ == "__main__":
    main()
