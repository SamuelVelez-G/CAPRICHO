"""Entrega final: operación, integridad, comprobantes, calidad, estadística, algoritmos y transferencia en vivo."""

import io
import unittest
from contextlib import closing
from pathlib import Path

from capricho import algoritmos as alg
from capricho.db import conectar
from capricho.servicios import benchmark, calidad, comprobantes, estadistica, integridad, normalizacion
from tests.base import LLAVE, PruebaCapricho

RAIZ = Path(__file__).resolve().parent.parent


class Normalizacion(unittest.TestCase):
    def test_clave_unifica_mayusculas_tildes_y_plurales(self):
        self.assertEqual(normalizacion.clave("  GRANIZADOS "), normalizacion.clave("granizado"))
        self.assertEqual(normalizacion.clave("Adiciones"), normalizacion.clave("adición"))

    def test_precios_escritos_de_muchas_formas(self):
        for texto, esperado in (("$12.000", 12000), ("12,000", 12000), ("12 mil", 12000), ("6,5 mil", 6500),
                                ("12000.00", 12000), (9000, 9000)):
            self.assertEqual(normalizacion.precio(texto)[0], esperado, texto)
        self.assertIsNone(normalizacion.precio("dos mil")[0])

    def test_celular_y_metodo(self):
        self.assertEqual(normalizacion.telefono("+57 300 555 1212"), "3005551212")
        self.assertIsNone(normalizacion.telefono("12345"))
        self.assertEqual(normalizacion.metodo_pago(" NEQUI "), "Nequi")
        self.assertEqual(normalizacion.metodo_pago("tarjeta de crédito"), "Tarjeta")

    def test_unificar_por_parecido(self):
        self.assertEqual(normalizacion.unificar("Bebidaz", ["Bebidas", "Postres"]), ("Bebidas", "parecido"))


class EstadisticaSimple(unittest.TestCase):
    def test_cuantil_igual_a_simple_statistics(self):
        # quantileSorted de Simple Statistics: n·p entero y n par -> promedio de los vecinos.
        self.assertEqual(estadistica.cuantil([1, 2, 3, 4], 0.25), 1.5)
        self.assertEqual(estadistica.cuantil([1, 2, 3, 4], 0.5), 2.5)
        self.assertEqual(estadistica.cuantil([1, 2, 3, 4, 5], 0.25), 2)

    def test_atipico_por_encima_de_la_cerca(self):
        resumen = estadistica.perfil([10_000, 11_000, 12_000, 12_000, 13_000, 14_000, 15_000])
        self.assertEqual(estadistica.evaluar_monto(13_000, resumen, "personal")["alerta"], "NINGUNA")
        self.assertEqual(estadistica.evaluar_monto(200_000, resumen, "personal")["alerta"], "ALTA")

    def test_regresion_lineal(self):
        pendiente, intercepto, r2 = estadistica.regresion_lineal([0, 1, 2, 3], [10, 12, 14, 16])
        self.assertAlmostEqual(pendiente, 2)
        self.assertAlmostEqual(intercepto, 10)
        self.assertAlmostEqual(r2, 1)


class Algoritmos(unittest.TestCase):
    def test_todas_las_variantes_dan_lo_mismo(self):
        valores = [9000, 7000, 12000, 7000, 21000, 9000, 14000]
        esperado = sorted(valores)
        for ordenar in (alg.burbuja, alg.seleccion, alg.insercion, alg.merge_sort, alg.quicksort, alg.heapsort, alg.timsort):
            self.assertEqual(ordenar(valores), esperado, ordenar.__name__)
        clientes = ["a", "b", "a", "c", "a", "b"]
        self.assertEqual(alg.conteo_doble_ciclo(clientes), alg.conteo_diccionario(clientes))
        self.assertEqual(alg.conteo_ordenando(clientes), alg.conteo_diccionario(clientes))
        lineas = [("x", 2), ("y", 1), ("x", 1), ("z", 5)]
        self.assertEqual(alg.ranking_doble_ciclo(lineas), alg.ranking_heap(lineas))
        self.assertEqual(alg.ranking_ordenando(lineas), alg.ranking_heap(lineas))
        nombres = ["Laura Gómez", "laura  gomez", "LAURA GÓMEZ", "Juan Arango"]
        self.assertEqual({alg.unificar_por_pares(nombres), alg.unificar_ordenando(nombres), alg.unificar_diccionario(nombres)}, {2})

    def test_busquedas(self):
        registros = [{"id": f"T{i:03d}"} for i in range(50, 0, -1)]
        buscados = ["T007", "T049", "NO"]
        esperado = ["T007", "T049", None]
        self.assertEqual(alg.busqueda_lineal(registros, buscados), esperado)
        self.assertEqual(alg.busqueda_binaria(alg.preparar_binaria(registros), buscados), esperado)
        self.assertEqual(alg.busqueda_indice(alg.preparar_indice(registros), buscados), esperado)

    def test_rafagas_iguales_en_las_tres_versiones(self):
        flujo = sorted([("u1", i * 0.1) for i in range(7)] + [("u2", i * 2.0) for i in range(6)], key=lambda t: t[1])
        resultados = {alg.rafagas_doble_ciclo(flujo), alg.rafagas_dos_punteros(flujo), alg.rafagas_deque(flujo)}
        self.assertEqual(resultados, {3})


class Operacion(PruebaCapricho):
    def setUp(self):
        super().setUp()
        self.como_admin()
        productos = self.cliente.get("/api/productos").get_json()["productos"]
        self.brownie = next(p for p in productos if p["nombre"] == "Brownie")
        self.grande = next(p for p in productos if p["nombre"] == "Granizado Grande")

    def pedido(self, **cambios):
        cuerpo = {"canal": "PRESENCIAL", "tipo_entrega": "RECOGER", "metodo_pago": "Efectivo",
                  "items": [{"producto_id": self.brownie["id"], "cantidad": 2}], **cambios}
        return self.enviar_json("POST", "/api/caja/pedidos", cuerpo)

    def pagar(self, factura, metodo, archivo=None, monto=None):
        datos = {"metodo": metodo, "monto": str(monto or factura["total"])}
        if archivo is not None:
            datos["comprobante"] = (io.BytesIO(archivo), "comprobante.pdf")
        return self.cliente.post(f"/api/facturas/{factura['id']}/pagos", data=datos, headers={"X-CSRF-Token": self.csrf()},
                                 content_type="multipart/form-data")

    def test_factura_consecutiva_con_impuesto_y_descuento(self):
        uno = self.pedido().get_json()["factura"]
        dos = self.pedido(descuento_porcentaje=10, motivo_descuento="Cliente frecuente").get_json()["factura"]
        self.assertEqual(dos["numero"], uno["numero"] + 1)
        self.assertEqual(uno["total"], 10_000)
        self.assertEqual(uno["base"] + uno["impuesto"], uno["total"])            # el impuesto va incluido
        self.assertAlmostEqual(uno["impuesto"] / uno["base"], 0.08, places=2)
        self.assertEqual(dos["descuento"], 1_000)
        self.assertEqual(self.pedido(descuento_porcentaje=20).status_code, 422)   # sin motivo

    def test_inventario_baja_y_se_devuelve_al_anular(self):
        antes = self.cliente.get(f"/api/productos/{self.brownie['id']}").get_json()["producto"]["stock"]
        factura = self.pedido().get_json()["factura"]
        self.assertEqual(self.cliente.get(f"/api/productos/{self.brownie['id']}").get_json()["producto"]["stock"], antes - 2)
        anulada = self.enviar_json("POST", f"/api/facturas/{factura['id']}/anular", {"motivo": "Error al digitar"})
        self.assertEqual(anulada.get_json()["factura"]["estado"], "ANULADA")
        self.assertEqual(self.cliente.get(f"/api/productos/{self.brownie['id']}").get_json()["producto"]["stock"], antes)
        sin_stock = self.pedido(items=[{"producto_id": self.brownie["id"], "cantidad": 50}] * 15)
        self.assertEqual(sin_stock.status_code, 409)

    def test_comprobantes_validos_falsos_y_reutilizados(self):
        config = self.app.config
        factura = self.pedido(metodo_pago="Nequi").get_json()["factura"]
        valido = comprobantes.generar_pdf({"referencia": "NEQ1", "metodo": "Nequi", "monto": factura["total"],
                                           "fecha": "2026-11-20T10:00:00", "pagador": "Ana"}, config["LLAVE_HMAC"])
        pago = self.pagar(factura, "Nequi", valido).get_json()["pago"]
        self.assertEqual((pago["verificacion"], pago["estado"]), ("VERIFICADO", "APROBADO"))
        self.assertEqual(pago["factura"]["estado"], "PAGADA")

        otra = self.pedido(metodo_pago="Nequi").get_json()["factura"]
        self.assertEqual(self.pagar(otra, "Nequi", valido).get_json()["pago"]["verificacion"], "REUTILIZADO")
        falso = comprobantes.generar_pdf({"referencia": "NEQ2", "metodo": "Nequi", "monto": otra["total"],
                                          "fecha": "2026-11-20T10:00:00", "pagador": "Ana"}, b"otra-llave")
        tercera = self.pedido(metodo_pago="Nequi").get_json()["factura"]
        self.assertEqual(self.pagar(tercera, "Nequi", falso).get_json()["pago"]["verificacion"], "FALSO")
        cuarta = self.pedido(metodo_pago="Nequi").get_json()["factura"]
        menor = comprobantes.generar_pdf({"referencia": "NEQ3", "metodo": "Nequi", "monto": 1000,
                                          "fecha": "2026-11-20T10:00:00", "pagador": "Ana"}, config["LLAVE_HMAC"])
        self.assertEqual(self.pagar(cuarta, "Nequi", menor).get_json()["pago"]["verificacion"], "NO_COINCIDE")
        sin_archivo = self.pagar(self.pedido(metodo_pago="Nequi").get_json()["factura"], "Nequi").get_json()["pago"]
        self.assertEqual(sin_archivo["estado"], "PENDIENTE")
        self.assertEqual(self.pagar(factura, "Efectivo", monto=500).status_code, 422)      # ya no tiene saldo

    def test_hash_encadenado_detecta_cambios_y_borrados(self):
        for _ in range(4):
            self.pedido()
        llave = self.app.config["LLAVE_INTEGRIDAD"]
        with closing(conectar(self.app.config["BASE_DATOS"])) as db:
            self.assertTrue(integridad.verificar_facturas(db, llave)["integra"])
            db.execute("UPDATE facturas SET total = 1 WHERE numero = 2")
            db.commit()
            problemas = integridad.verificar_facturas(db, llave)["problemas"]
            self.assertEqual([(p["registro"], p["tipo"]) for p in problemas], [("FV-000002", "CONTENIDO_ALTERADO")])
            db.execute("UPDATE facturas SET total = 10000 WHERE numero = 2")
            db.execute("PRAGMA foreign_keys = OFF")
            db.execute("DELETE FROM facturas WHERE numero = 3")
            db.commit()
            problemas = integridad.verificar_facturas(db, llave)["problemas"]
            self.assertEqual([(p["registro"], p["tipo"]) for p in problemas], [("FV-000004", "ENLACE_ROTO")])

    def test_roles(self):
        creado = self.enviar_json("POST", "/api/usuarios", {"nombre": "Pepe Cajero", "email": "pepe@capricho.co",
                                                           "rol": "EMPLEADO", "estado": "ACTIVO", "password": "Cajero2026*"})
        self.assertEqual(creado.status_code, 201)
        self.assertEqual(self.enviar_json("POST", "/api/usuarios", {"nombre": "Sin Clave", "email": "x@capricho.co",
                                                                    "rol": "EMPLEADO", "estado": "ACTIVO"}).status_code, 422)
        yo = self.cliente.get("/api/auth/yo").get_json()["usuario"]
        self.assertEqual(self.enviar_json("DELETE", f"/api/usuarios/{yo['id']}").status_code, 409)
        self.enviar_json("POST", "/api/auth/logout")
        self.iniciar_sesion("pepe@capricho.co", "Cajero2026*")
        self.assertEqual(self.pedido().status_code, 201)                    # el empleado usa la caja
        self.assertEqual(self.cliente.get("/api/usuarios").status_code, 403)  # pero no administra usuarios

    def test_categoria_repetida_escrita_distinto(self):
        respuesta = self.enviar_json("POST", "/api/categorias", {"nombre": "GRANIZADO ", "descripcion": "", "activo": True})
        self.assertEqual(respuesta.status_code, 409)


class Calidad(PruebaCapricho):
    def test_importar_clientes_sucios(self):
        with closing(conectar(self.app.config["BASE_DATOS"])) as db:
            registros = calidad.leer_archivo((RAIZ / "datos" / "clientes_sucios.csv").read_bytes(), "clientes_sucios.csv")
            reporte = calidad.importar(db, registros, "clientes")
        self.assertEqual(reporte["recibidos"], 30)
        estados = {r["fila"]: r["estado"] for r in reporte["resultados"]}
        self.assertEqual(estados[1], "CORREGIDO")      # mayúsculas, espacios y +57
        self.assertEqual(estados[3], "DUPLICADO")      # mismo correo que la fila 2
        self.assertEqual(estados[4], "DESCARTADO")     # "Ana": 3 letras
        self.assertEqual(estados[6], "DESCARTADO")     # celular de 5 dígitos

    def test_auditoria_encuentra_duplicados(self):
        with closing(conectar(self.app.config["BASE_DATOS"])) as db:
            db.execute("""INSERT INTO usuarios (nombre, email, telefono, fecha_creacion, fecha_actualizacion)
                          VALUES ('valentina  restrepo', 'Cliente@Capricho.co', '300 123 4567', 'x', 'x')""")
            db.commit()
            auditoria = calidad.auditar(db)
        self.assertIn("CLIENTE_DUPLICADO", auditoria["por_tipo"])
        self.assertIn("CELULAR_SIN_NORMALIZAR", auditoria["por_tipo"])
        self.assertLess(auditoria["puntaje"], 100)


class BenchmarkCorto(PruebaCapricho):
    def test_todas_las_variantes_coinciden_y_hay_pendientes(self):
        with closing(conectar(self.app.config["BASE_DATOS"])) as db:
            resultado = benchmark.correr(db, "RAPIDO", tamanos=[60, 120, 240, 480])
        self.assertTrue(all(p["verificado"] for p in resultado["problemas"]))
        self.assertEqual(len(resultado["problemas"]), 8)


class EnVivo(PruebaCapricho):
    def test_transferencia_en_vivo_queda_en_el_monitor(self):
        respuesta = self.enviar_json("POST", "/api/vivo/transferir", {"email": "nuevo@correo.co", "valor": 12000, "metodo": "Nequi"})
        self.assertEqual(respuesta.status_code, 201)
        resultado = respuesta.get_json()["resultados"][0]
        self.assertEqual(resultado["analisis"]["decision"]["estado"], "APROBADA")
        rafaga = self.enviar_json("POST", "/api/vivo/transferir", {"email": "bot@correo.co", "valor": 5000, "metodo": "Tarjeta",
                                                                   "repetir": 6}).get_json()["resultados"]
        self.assertEqual(rafaga[-1]["estado"], "RECHAZADA")
        self.assertEqual(self.cliente.get("/api/vivo/feed").status_code, 401)        # el monitor es del administrador
        self.como_admin()
        feed = self.cliente.get("/api/vivo/feed").get_json()
        self.assertTrue(all(t["origen"] == "VIVO" for t in feed["transacciones"]))
        self.assertIn("decision", feed["transacciones"][-1]["analisis"])


if __name__ == "__main__":
    unittest.main()
