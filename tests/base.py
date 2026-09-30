"""Base común de las pruebas: una base de datos temporal por prueba."""

import shutil
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

from capricho import create_app
from capricho.seguridad import firmar_transaccion

LLAVE = b"llave_de_pruebas"


class PruebaCapricho(unittest.TestCase):
    def setUp(self):
        self.carpeta = Path(tempfile.mkdtemp(prefix="capricho_"))
        self.app = create_app({
            "BASE_DATOS": str(self.carpeta / "prueba.db"),
            "CARPETA_LOGS": str(self.carpeta / "logs"),
            "LLAVE_HMAC": LLAVE,
            "SEMBRAR": "base",
            "TESTING": True,
            "LIMITE_PETICIONES_POR_SEGUNDO": 1000,
        })
        self.app.extensions["capricho"].limitador_ip.maximo = 1000
        self.cliente = self.app.test_client()
        self._id = 5000
        self.hoy = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)

    def tearDown(self):
        shutil.rmtree(self.carpeta, ignore_errors=True)

    # --- ayudas -------------------------------------------------------------
    def csrf(self):
        return self.cliente.get("/api/auth/yo").get_json()["csrf"]

    def enviar_json(self, metodo, ruta, cuerpo=None, csrf=True):
        cabeceras = {"X-CSRF-Token": self.csrf()} if csrf else {}
        return self.cliente.open(ruta, method=metodo, json=cuerpo, headers=cabeceras)

    def iniciar_sesion(self, email, password):
        respuesta = self.enviar_json("POST", "/api/auth/login", {"email": email, "password": password})
        self.assertEqual(respuesta.status_code, 200, respuesta.get_json())

    def como_admin(self):
        self.iniciar_sesion(self.app.config["ADMIN_EMAIL"], self.app.config["ADMIN_PASSWORD"])

    def transaccion(self, usuario, cuando, valor=50000, metodo="Tarjeta", **cambios):
        self._id += 1
        txn = {"idTxn": self._id, "user": usuario, "value": valor, "paymentMethod": metodo,
               "date": cuando if isinstance(cuando, str) else cuando.isoformat(timespec="milliseconds")}
        txn["hash"] = firmar_transaccion(txn, LLAVE)
        txn.update(cambios)
        return txn

    def enviar_txn(self, usuario, cuando, **kwargs):
        return self.cliente.post("/api/transacciones", json=self.transaccion(usuario, cuando, **kwargs))

    def a_las(self, hora, minuto, segundo, milis=0):
        return self.hoy + timedelta(hours=hora, minutes=minuto, seconds=segundo, milliseconds=milis)
