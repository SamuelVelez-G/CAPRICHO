"""Los casos de uso de las diapositivas 39, 42 y 43, más ráfaga, hash y replay."""

import unittest

from tests.base import PruebaCapricho


class CasosDeUso(PruebaCapricho):
    def estados(self, respuestas):
        return [r.get_json()["transaccion"]["estado"] for r in respuestas]

    def test_caso_1_multiples_transacciones_es_anomalia(self):
        respuestas = [self.enviar_txn("b@b.com", self.a_las(10, 0, s)) for s in (1, 2, 3)]
        self.assertEqual(self.estados(respuestas), ["APROBADA", "APROBADA", "SOSPECHOSA"])
        anomalia = respuestas[2].get_json()["transaccion"]["anomalias"][0]
        self.assertEqual(anomalia["tipo"], "POSIBLE_FRAUDE")
        self.assertEqual(anomalia["cantidad_transacciones"], 3)

    def test_caso_2_transacciones_espaciadas_son_normales(self):
        horas = [self.a_las(10, 0, 1), self.a_las(10, 0, 10), self.a_las(10, 1, 20)]
        respuestas = [self.enviar_txn("c@c.com", h) for h in horas]
        self.assertEqual(self.estados(respuestas), ["APROBADA"] * 3)

    def test_caso_3_cada_usuario_tiene_su_ventana(self):
        respuestas = [self.enviar_txn(f"u{n}@u.com", self.a_las(10, 0, n)) for n in (1, 2, 3)]
        self.assertEqual(self.estados(respuestas), ["APROBADA"] * 3)

    def test_diapositiva_39_cada_cuatro_segundos_es_normal(self):
        respuestas = [self.enviar_txn("b@b.com", self.a_las(10, 0, s)) for s in (1, 5, 9)]
        self.assertEqual(self.estados(respuestas), ["APROBADA"] * 3)

    def test_cinco_en_el_mismo_segundo_se_bloquean(self):
        respuestas = [self.enviar_txn("r@r.com", self.a_las(15, 0, 7, 150 * n)) for n in range(5)]
        self.assertEqual(respuestas[4].status_code, 429)
        self.assertEqual(respuestas[4].get_json()["transaccion"]["anomalias"][0]["tipo"], "RAFAGA")
        self.assertNotEqual(respuestas[3].get_json()["transaccion"]["estado"], "RECHAZADA")

    def test_un_segundo_exacto_no_es_el_mismo_segundo(self):
        # 11:00:01.000 y 11:00:02.000 NO están "en el mismo segundo". Se manda
        # como lote para que la regla de llegada al servidor no intervenga.
        lote = [self.transaccion("s@s.com", self.a_las(11, 0, s)) for s in range(1, 6)]
        resultados = self.cliente.post("/api/transacciones/lote", json=lote).get_json()["lote"]["resultados"]
        self.assertNotIn("RAFAGA", {a["tipo"] for r in resultados for a in r["anomalias"]})

    def test_cinco_llegadas_en_un_segundo_aunque_mientan_en_la_fecha(self):
        # Fechas separadas por minutos, pero las 5 peticiones llegan juntas.
        respuestas = [self.enviar_txn("x@x.com", self.a_las(8, n * 5, 0)) for n in range(5)]
        self.assertEqual(respuestas[4].status_code, 429)

    def test_fuera_de_orden_tambien_se_detecta(self):
        self.enviar_txn("d@d.com", self.a_las(9, 0, 3))
        self.enviar_txn("d@d.com", self.a_las(9, 0, 1))
        ultima = self.enviar_txn("d@d.com", self.a_las(9, 0, 2))
        self.assertEqual(ultima.get_json()["transaccion"]["estado"], "SOSPECHOSA")

    def test_monto_atipico(self):
        respuesta = self.enviar_txn("m@m.com", self.a_las(12, 30, 0), valor=900_000)
        cuerpo = respuesta.get_json()["transaccion"]
        self.assertEqual(cuerpo["estado"], "SOSPECHOSA")
        self.assertEqual(cuerpo["anomalias"][0]["tipo"], "MONTO_ATIPICO")


class Integridad(PruebaCapricho):
    def test_hash_alterado_se_rechaza(self):
        txn = self.transaccion("h@h.com", self.a_las(10, 0, 1))
        txn["value"] = 1          # se cambió el valor después de firmar
        respuesta = self.cliente.post("/api/transacciones", json=txn)
        self.assertEqual(respuesta.status_code, 401)
        self.assertEqual(respuesta.get_json()["transaccion"]["anomalias"][0]["tipo"], "HASH_INVALIDO")

    def test_replay_con_el_mismo_id(self):
        txn = self.transaccion("p@p.com", self.a_las(10, 0, 1))
        self.assertEqual(self.cliente.post("/api/transacciones", json=txn).status_code, 201)
        self.assertEqual(self.cliente.post("/api/transacciones", json=txn).status_code, 409)

    def test_campos_nulos_y_vacios(self):
        respuesta = self.cliente.post("/api/transacciones", json={
            "idTxn": None, "user": "", "date": "   ", "value": None, "paymentMethod": None, "hash": ""})
        self.assertEqual(respuesta.status_code, 422)
        self.assertEqual(set(respuesta.get_json()["errores"]),
                         {"idTxn", "user", "date", "value", "paymentMethod", "hash"})

    def test_tipos_invalidos(self):
        txn = self.transaccion("t@t.com", self.a_las(10, 0, 1), value=True)
        errores = self.cliente.post("/api/transacciones", json=txn).get_json()["errores"]
        self.assertIn("value", errores)
        txn = self.transaccion("t@t.com", "23/09/2026 10:30")
        self.assertIn("date", self.cliente.post("/api/transacciones", json=txn).get_json()["errores"])

    def test_inyeccion_sql_bloqueada_y_registrada(self):
        txn = self.transaccion("a@a.com' OR '1'='1", self.a_las(10, 0, 1))
        respuesta = self.cliente.post("/api/transacciones", json=txn)
        self.assertEqual(respuesta.status_code, 400)
        cima = self.app.extensions["capricho"].pila_errores.cima()
        self.assertEqual(cima["tipo"], "INYECCION_SQL")

    def test_lote_desordenado_se_ordena_con_merge_sort(self):
        lote = [self.transaccion("l@l.com", self.a_las(10, 0, s)) for s in (3, 1, 2)]
        respuesta = self.cliente.post("/api/transacciones/lote", json=lote)
        cuerpo = respuesta.get_json()["lote"]
        self.assertEqual(cuerpo["orden_cronologico"], [str(lote[1]["idTxn"]), str(lote[2]["idTxn"]), str(lote[0]["idTxn"])])
        self.assertEqual(cuerpo["resumen"], {"APROBADA": 2, "SOSPECHOSA": 1})


class Configuracion(PruebaCapricho):
    def test_franjas_de_la_diapositiva_38(self):
        self.como_admin()
        respuesta = self.enviar_json("PATCH", "/api/configuracion", {"modo": "FRANJAS"})
        self.assertEqual(respuesta.status_code, 200)
        # En la mañana la ventana es de 10 s: 1, 5 y 9 ahora sí caen juntas.
        estados = [self.enviar_txn("f@f.com", self.a_las(10, 0, s)).get_json()["transaccion"]["estado"]
                   for s in (1, 5, 9)]
        self.assertEqual(estados[-1], "SOSPECHOSA")
        # En la noche la ventana es de 3 s: las mismas separaciones son normales.
        estados = [self.enviar_txn("g@g.com", self.a_las(22, 0, s)).get_json()["transaccion"]["estado"]
                   for s in (1, 5, 9)]
        self.assertEqual(estados, ["APROBADA"] * 3)

    def test_put_exige_todo_y_patch_no(self):
        self.como_admin()
        self.assertEqual(self.enviar_json("PUT", "/api/configuracion", {"modo": "FIJA"}).status_code, 422)
        self.assertEqual(self.enviar_json("PATCH", "/api/configuracion", {"monto_atipico": 500000}).status_code, 200)

    def test_cliente_no_puede_cambiar_reglas(self):
        self.iniciar_sesion(self.app.config["CLIENTE_DEMO_EMAIL"], self.app.config["CLIENTE_DEMO_PASSWORD"])
        self.assertEqual(self.enviar_json("PATCH", "/api/configuracion", {"modo": "FRANJAS"}).status_code, 403)


if __name__ == "__main__":
    unittest.main()
