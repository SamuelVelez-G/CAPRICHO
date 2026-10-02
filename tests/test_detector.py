"""Los casos de uso de las diapositivas 39, 42 y 43, más ráfaga, hash y replay."""

import hashlib
import hmac
import json
import unittest

from tests.base import LLAVE, PruebaCapricho


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

    def test_por_defecto_aplican_las_franjas_de_la_diapositiva_38(self):
        # Mañana: ventana de 10 s, así que 1, 5 y 9 caen juntas.
        manana = [self.enviar_txn("m1@b.com", self.a_las(10, 0, s)) for s in (1, 5, 9)]
        self.assertEqual(self.estados(manana)[-1], "SOSPECHOSA")
        # Tarde-noche: ventana de 6 s. 1, 5 y 9 no caben juntas; 1, 4 y 6 sí.
        tarde = [self.enviar_txn("t1@b.com", self.a_las(19, 0, s)) for s in (1, 5, 9)]
        self.assertEqual(self.estados(tarde), ["APROBADA"] * 3)
        tarde = [self.enviar_txn("t2@b.com", self.a_las(19, 0, s)) for s in (1, 4, 6)]
        self.assertEqual(self.estados(tarde)[-1], "SOSPECHOSA")
        # Noche: ventana de 3 s. 1, 3 y 5 no caben juntas; 1, 2 y 3 sí.
        noche = [self.enviar_txn("n1@b.com", self.a_las(21, 0, s)) for s in (1, 3, 5)]
        self.assertEqual(self.estados(noche), ["APROBADA"] * 3)
        noche = [self.enviar_txn("n2@b.com", self.a_las(21, 0, s)) for s in (1, 2, 3)]
        self.assertEqual(self.estados(noche)[-1], "SOSPECHOSA")

    def test_bordes_de_las_franjas(self):
        # 12:00:00 todavía es mañana (10 s); 12:00:01 ya es tarde (6 s).
        from capricho.servicios.detector import REGLAS_POR_DEFECTO, regla_aplicable
        self.assertEqual(regla_aplicable(REGLAS_POR_DEFECTO, self.a_las(12, 0, 0))["ventana_segundos"], 10)
        self.assertEqual(regla_aplicable(REGLAS_POR_DEFECTO, self.a_las(12, 0, 1))["ventana_segundos"], 6)
        self.assertEqual(regla_aplicable(REGLAS_POR_DEFECTO, self.a_las(20, 0, 0))["ventana_segundos"], 6)
        self.assertEqual(regla_aplicable(REGLAS_POR_DEFECTO, self.a_las(20, 0, 1))["ventana_segundos"], 3)
        self.assertEqual(regla_aplicable(REGLAS_POR_DEFECTO, self.a_las(5, 0, 0))["ventana_segundos"], 3)
        self.assertEqual(regla_aplicable(REGLAS_POR_DEFECTO, self.a_las(5, 0, 1))["ventana_segundos"], 10)

    def test_diapositiva_39_con_la_regla_fija(self):
        self.como_admin()
        self.enviar_json("PATCH", "/api/configuracion", {"modo": "FIJA"})
        respuestas = [self.enviar_txn("b@b.com", self.a_las(10, 0, s)) for s in (1, 5, 9)]
        self.assertEqual(self.estados(respuestas), ["APROBADA"] * 3)

    def test_cinco_en_el_mismo_segundo_se_bloquean(self):
        respuestas = [self.enviar_txn("r@r.com", self.a_las(15, 0, 7, 150 * n)) for n in range(5)]
        quinta = respuestas[4].get_json()
        self.assertEqual(respuestas[4].status_code, 201)       # se registró, aunque sea fraude
        self.assertEqual(quinta["estado"], "RECHAZADA")
        self.assertEqual(quinta["resultado"], "ANOMALIA")
        self.assertEqual(quinta["anomalias"], ["RAFAGA"])
        self.assertNotEqual(respuestas[3].get_json()["transaccion"]["estado"], "RECHAZADA")

    def test_un_segundo_exacto_no_es_el_mismo_segundo(self):
        # 11:00:01.000 y 11:00:02.000 NO están "en el mismo segundo".
        lote = [self.transaccion("s@s.com", self.a_las(11, 0, s)) for s in range(1, 6)]
        resultados = self.cliente.post("/api/transacciones/lote", json=lote).get_json()["lote"]["resultados"]
        self.assertNotIn("RAFAGA", {a["tipo"] for r in resultados for a in r["anomalias"]})

    def test_llegadas_rapidas_con_fechas_separadas_no_son_rafaga_por_defecto(self):
        # Un generador que envía rápido transacciones con fechas separadas por
        # minutos no debe producir ráfagas falsas.
        respuestas = [self.enviar_txn("x@x.com", self.a_las(8, n * 5, 0)) for n in range(6)]
        self.assertEqual({r.get_json()["estado"] for r in respuestas}, {"APROBADA"})

    def test_regla_de_llegada_se_puede_activar(self):
        self.como_admin()
        self.enviar_json("PATCH", "/api/configuracion",
                         {"rafaga": {"maximo": 5, "ventana_segundos": 1, "por_llegada": True}})
        respuestas = [self.enviar_txn("y@y.com", self.a_las(8, n * 5, 0)) for n in range(5)]
        self.assertEqual(respuestas[4].get_json()["anomalias"], ["RAFAGA"])

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
        self.assertEqual(respuesta.status_code, 201)
        self.assertEqual(respuesta.get_json()["estado"], "RECHAZADA")
        self.assertEqual(respuesta.get_json()["anomalias"], ["HASH_INVALIDO"])

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


class FormatosDelGenerador(PruebaCapricho):
    """Formas en que el generador del profesor podría firmar y enviar."""

    def base(self, **cambios):
        self._id += 1
        txn = {"idTxn": self._id, "user": "g@g.com", "date": self.a_las(10, 0, 1).isoformat(timespec="milliseconds"),
               "value": 50000, "paymentMethod": "Tarjeta"}
        txn.update(cambios)
        return txn

    def enviar(self, txn, ruta="/api/transacciones"):
        return self.cliente.post(ruta, json=txn).get_json()

    def test_llave_de_la_diapositiva_19(self):
        txn = self.base()
        datos = json.dumps(txn, sort_keys=True, separators=(",", ":")).encode()
        txn["hash"] = hmac.new(b"mi_llave_privada_123", datos, hashlib.sha256).hexdigest()
        cuerpo = self.enviar(txn)
        self.assertEqual(cuerpo["estado"], "APROBADA")
        self.assertIn("diapositiva 19", cuerpo["transaccion"]["analisis"]["firma"])

    def test_sha256_sin_llave_de_la_diapositiva_17(self):
        txn = self.base()
        txn["hash"] = hashlib.sha256(json.dumps(txn, sort_keys=True).encode()).hexdigest()
        self.assertEqual(self.enviar(txn)["estado"], "APROBADA")

    def test_orden_de_javascript_y_campos_extra(self):
        txn = self.base(ip="181.50.1.2", status="PENDIENTE")
        datos = json.dumps(txn, separators=(",", ":")).encode()          # como JSON.stringify
        txn["hash"] = hmac.new(LLAVE, datos, hashlib.sha256).hexdigest()
        self.assertEqual(self.enviar(txn)["estado"], "APROBADA")

    def test_sha256_alterado_igual_se_detecta(self):
        txn = self.base()
        txn["hash"] = hashlib.sha256(json.dumps(txn, sort_keys=True).encode()).hexdigest()
        txn["value"] = 1
        self.assertEqual(self.enviar(txn)["anomalias"], ["HASH_INVALIDO"])

    def test_valor_como_texto_y_otro_metodo_de_pago(self):
        txn = self.base(value="45000", paymentMethod="transferencia", date="2026-09-23 10:30:01")
        txn["hash"] = hashlib.sha256(json.dumps(txn, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        cuerpo = self.enviar(txn)
        self.assertEqual(cuerpo["estado"], "APROBADA")
        self.assertEqual(cuerpo["transaccion"]["valor"], 45000)

    def test_lista_en_el_endpoint_principal_y_ruta_alterna(self):
        lote = [self.transaccion("z@z.com", self.a_las(10, 0, s)) for s in (1, 2, 3)]
        self.assertEqual(self.enviar(lote)["lote"]["resumen"], {"APROBADA": 2, "SOSPECHOSA": 1})
        otra = self.transaccion("w@w.com", self.a_las(10, 0, 1))
        self.assertEqual(self.enviar(otra, "/transacciones")["estado"], "APROBADA")

    def test_el_limite_por_ip_no_frena_al_generador(self):
        self.app.extensions["capricho"].limitador_ip.maximo = 5
        estados = [self.enviar(self.transaccion(f"u{n}@ip.com", self.a_las(10, 0, 1)))["estado"] for n in range(30)]
        self.assertEqual(set(estados), {"APROBADA"})


class Configuracion(PruebaCapricho):
    def test_franjas_de_la_diapositiva_38(self):
        self.como_admin()
        respuesta = self.enviar_json("PATCH", "/api/configuracion", {"modo": "FRANJAS"})
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.get_json()["reglas"]["modo"], "FRANJAS")
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
