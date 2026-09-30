"""Formularios, sesión, precios validados en el servidor y métodos HTTP."""

import unittest
from contextlib import closing

from capricho.db import conectar
from tests.base import PruebaCapricho

REGISTRO_VALIDO = {"nombre": "Ana María", "email": "ana@correo.co", "telefono": "3001112233",
                   "password": "Granizado1*", "confirmacion": "Granizado1*"}


class Formularios(PruebaCapricho):
    def test_nombre_de_tres_letras_no_pasa(self):
        respuesta = self.enviar_json("POST", "/api/auth/registro", {**REGISTRO_VALIDO, "nombre": "Ana"})
        self.assertEqual(respuesta.status_code, 422)
        self.assertIn("nombre", respuesta.get_json()["errores"])

    def test_ningun_campo_nulo(self):
        respuesta = self.enviar_json("POST", "/api/auth/registro", {c: None for c in REGISTRO_VALIDO})
        self.assertEqual(set(respuesta.get_json()["errores"]), set(REGISTRO_VALIDO))

    def test_contrasena_debil(self):
        debil = {**REGISTRO_VALIDO, "password": "12345678", "confirmacion": "12345678"}
        self.assertIn("password", self.enviar_json("POST", "/api/auth/registro", debil).get_json()["errores"])

    def test_html_en_el_nombre_se_rechaza(self):
        respuesta = self.enviar_json("POST", "/api/auth/registro", {**REGISTRO_VALIDO, "nombre": "<script>x</script>"})
        self.assertEqual(respuesta.status_code, 422)

    def test_sin_token_csrf_se_rechaza(self):
        respuesta = self.enviar_json("POST", "/api/auth/registro", REGISTRO_VALIDO, csrf=False)
        self.assertEqual(respuesta.status_code, 403)

    def test_registro_guarda_la_contrasena_hasheada(self):
        self.assertEqual(self.enviar_json("POST", "/api/auth/registro", REGISTRO_VALIDO).status_code, 201)
        with closing(conectar(self.app.config["BASE_DATOS"])) as conexion:
            fila = conexion.execute("SELECT password_hash FROM usuarios WHERE email = 'ana@correo.co'").fetchone()
        self.assertTrue(fila[0].startswith("scrypt$"))
        self.assertNotIn("Granizado1*", fila[0])

    def test_login_con_inyeccion(self):
        respuesta = self.enviar_json("POST", "/api/auth/login", {"email": "' OR '1'='1' --", "password": "x"})
        self.assertEqual(respuesta.status_code, 400)

    def test_cinco_intentos_fallidos_bloquean(self):
        for _ in range(5):
            self.enviar_json("POST", "/api/auth/login", {"email": "admin@capricho.co", "password": "Mala123*"})
        respuesta = self.enviar_json("POST", "/api/auth/login",
                                     {"email": "admin@capricho.co", "password": self.app.config["ADMIN_PASSWORD"]})
        self.assertEqual(respuesta.status_code, 429)


class PreciosEnElServidor(PruebaCapricho):
    def setUp(self):
        super().setUp()
        productos = self.cliente.get("/api/productos").get_json()["productos"]
        self.mediano = next(p for p in productos if p["nombre"] == "Granizado Mediano")
        self.oreo = next(p for p in productos if p["nombre"] == "Galleta Oreo")
        self.iniciar_sesion(self.app.config["CLIENTE_DEMO_EMAIL"], self.app.config["CLIENTE_DEMO_PASSWORD"])

    def pedido(self, precio_unitario, total):
        return {"items": [{"producto_id": self.mediano["id"], "sabor": "Capuchino", "cantidad": 2,
                           "adiciones": [self.oreo["id"]], "precio_unitario": precio_unitario}],
                "tipo_entrega": "DOMICILIO", "barrio": "Prado", "direccion": "Calle 58 # 50-20",
                "metodo_pago": "Nequi", "total": total}

    def test_compra_correcta_entra_a_la_cola(self):
        # (9.000 + 2.000) x 2 = 22.000 + domicilio a Prado (2,9 km) = 4.100
        respuesta = self.enviar_json("POST", "/api/pedidos", self.pedido(11000, 26100))
        self.assertEqual(respuesta.status_code, 201, respuesta.get_json())
        pedido = respuesta.get_json()["pedido"]
        self.assertEqual(pedido["total"], 26100)
        self.assertEqual(pedido["estado"], "SOLICITADO")
        self.assertEqual(pedido["ruta"], ["Aranjuez", "Campo Valdés", "Prado"])

    def test_precio_alterado_en_el_localstorage(self):
        respuesta = self.enviar_json("POST", "/api/pedidos", self.pedido(100, 4300))
        self.assertEqual(respuesta.status_code, 409)
        self.assertEqual(respuesta.get_json()["total_real"], 26100)
        with closing(conectar(self.app.config["BASE_DATOS"])) as conexion:
            tipo = conexion.execute("SELECT tipo FROM anomalias").fetchone()[0]
        self.assertEqual(tipo, "PRECIO_MANIPULADO")

    def test_sin_sesion_no_se_compra(self):
        self.enviar_json("POST", "/api/auth/logout")
        self.assertEqual(self.enviar_json("POST", "/api/pedidos", self.pedido(11000, 26100)).status_code, 401)


class MetodosHttp(PruebaCapricho):
    NUEVO = {"nombre": "Granizado Familiar", "descripcion": "Granizado de café artesanal de 32 oz",
             "categoria": "GRANIZADO", "precio": 16000, "onzas": 32, "imagen": "menu.jpg", "activo": True}

    def test_crud_completo(self):
        self.como_admin()
        creado = self.enviar_json("POST", "/api/productos", self.NUEVO)
        self.assertEqual(creado.status_code, 201)
        producto_id = creado.get_json()["producto"]["id"]

        patch = self.enviar_json("PATCH", f"/api/productos/{producto_id}", {"precio": 17000})
        self.assertEqual(patch.get_json()["producto"]["precio"], 17000)
        self.assertEqual(patch.get_json()["producto"]["nombre"], "Granizado Familiar")

        incompleto = self.enviar_json("PUT", f"/api/productos/{producto_id}", {"precio": 18000})
        self.assertEqual(incompleto.status_code, 422)
        put = self.enviar_json("PUT", f"/api/productos/{producto_id}", {**self.NUEVO, "precio": 18000})
        self.assertEqual(put.get_json()["producto"]["precio"], 18000)

        self.assertEqual(self.enviar_json("DELETE", f"/api/productos/{producto_id}").status_code, 200)
        self.assertEqual(self.cliente.get(f"/api/productos/{producto_id}").status_code, 404)

    def test_un_cliente_no_puede_cambiar_precios(self):
        self.iniciar_sesion(self.app.config["CLIENTE_DEMO_EMAIL"], self.app.config["CLIENTE_DEMO_PASSWORD"])
        self.assertEqual(self.enviar_json("PATCH", "/api/productos/1", {"precio": 100}).status_code, 403)


if __name__ == "__main__":
    unittest.main()
