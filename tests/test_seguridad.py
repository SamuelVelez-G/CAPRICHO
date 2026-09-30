"""Contraseñas, HMAC, inyección SQL, estructuras y algoritmos."""

import unittest

from capricho.estructuras import Cola, Pila, LimitadorVentana, max_en_ventana, mayor_por_division, merge_sort
from capricho.seguridad import (buscar_patron_sql, firmar_transaccion, hash_es_valido, hashear_password,
                                verificar_password)
from capricho.servicios import domicilios


class Contrasenas(unittest.TestCase):
    def test_nunca_se_guarda_en_texto_plano(self):
        almacenado = hashear_password("Cafe2026*")
        self.assertTrue(almacenado.startswith("scrypt$"))
        self.assertNotIn("Cafe2026*", almacenado)
        self.assertTrue(verificar_password("Cafe2026*", almacenado))
        self.assertFalse(verificar_password("cafe2026*", almacenado))

    def test_la_sal_cambia_el_hash(self):
        self.assertNotEqual(hashear_password("Igual123*"), hashear_password("Igual123*"))


class FirmaHmac(unittest.TestCase):
    TXN = {"idTxn": 1001, "user": "aa@aa.com", "date": "2026-09-23T10:30:01.120",
           "value": 50000, "paymentMethod": "Tarjeta"}

    def test_cambiar_un_dato_cambia_el_hash(self):
        original = firmar_transaccion(self.TXN, b"llave")
        alterada = firmar_transaccion({**self.TXN, "value": 50001}, b"llave")
        self.assertNotEqual(original, alterada)
        self.assertEqual(len(original), 64)

    def test_sin_la_llave_no_se_puede_falsificar(self):
        falsa = firmar_transaccion(self.TXN, b"otra_llave")
        self.assertFalse(hash_es_valido(self.TXN, falsa, b"llave"))
        self.assertTrue(hash_es_valido(self.TXN, firmar_transaccion(self.TXN, b"llave"), b"llave"))


class InyeccionSql(unittest.TestCase):
    def test_detecta_ataques_clasicos(self):
        for ataque in ["' OR '1'='1", "admin'--", "x'; DROP TABLE usuarios; --",
                       "1 UNION SELECT password_hash FROM usuarios", "a' AND sleep(5)", "' or 1=1"]:
            with self.subTest(ataque=ataque):
                self.assertIsNotNone(buscar_patron_sql(ataque))

    def test_no_bloquea_datos_legitimos(self):
        for texto in ["Cra. 50c # 92-84", "María José Restrepo", "andres.ortiz@correo.co",
                      "Calle 10 Sur # 43A-15, apto 301", "Galleta Oreo", "Granizado Grande"]:
            with self.subTest(texto=texto):
                self.assertIsNone(buscar_patron_sql(texto))


class Estructuras(unittest.TestCase):
    def test_cola_fifo_y_pila_lifo(self):
        cola, pila = Cola(), Pila()
        for n in (1, 2, 3):
            cola.encolar(n)
            pila.apilar(n)
        self.assertEqual([cola.desencolar() for _ in range(3)], [1, 2, 3])
        self.assertEqual([pila.desapilar() for _ in range(3)], [3, 2, 1])

    def test_merge_sort_y_mayor_por_division(self):
        datos = [10, 5, 30, 8, 20]
        self.assertEqual(merge_sort(datos), sorted(datos))
        self.assertEqual(mayor_por_division(datos), 30)

    def test_ventana_deslizante(self):
        self.assertEqual(max_en_ventana([0, 1, 2], 2, 3), 3)
        self.assertEqual(max_en_ventana([0, 4, 8], 8, 3), 1)
        self.assertEqual(max_en_ventana([0, 1], 1, 1), 1)      # separadas exactamente 1 s

    def test_limitador(self):
        limitador = LimitadorVentana(maximo=4, ventana_segundos=1)
        resultados = [limitador.registrar("ip", 10 + n * 0.1)[0] for n in range(5)]
        self.assertEqual(resultados, [True, True, True, True, False])
        self.assertTrue(limitador.registrar("ip", 12)[0])      # la ventana ya se deslizó

    def test_dijkstra_desde_aranjuez(self):
        cotizacion = domicilios.cotizar("El Poblado")
        self.assertEqual(cotizacion["ruta"][0], "Aranjuez")
        self.assertEqual(cotizacion["ruta"][-1], "El Poblado")
        self.assertAlmostEqual(cotizacion["distancia_km"], 1.3 + 1.6 + 1.5 + 4.2)
        self.assertEqual(cotizacion["tarifa"], 8100)


if __name__ == "__main__":
    unittest.main()
