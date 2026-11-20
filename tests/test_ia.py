"""Detector con IA: variables de comportamiento, probador y uso desde el endpoint."""

import unittest
from datetime import timedelta

from capricho.ia import caracteristicas
from tests.base import PruebaCapricho

try:
    from capricho.ia.modelo import ARCHIVO_MODELO      # primero: deja KERAS_BACKEND=torch
    import keras  # noqa: F401
    DISPONIBLE = ARCHIVO_MODELO.exists()
except Exception:
    DISPONIBLE = False

NORMAL = {"hora": 13.25, "valor": 9000, "metodo": "Nequi", "proporcion_metodo": 0.9, "monto_habitual": 9000,
          "hora_habitual": 13, "compras_ultima_hora": 0, "horas_desde_anterior": 20, "compras_previas": 40}
SILENCIOSO = {**NORMAL, "hora": 3.25, "valor": 250000, "metodo": "PSE", "proporcion_metodo": 0}


class Caracteristicas(unittest.TestCase):
    def test_nueve_variables(self):
        self.assertEqual(len(caracteristicas.desde_contexto(NORMAL)), len(caracteristicas.NOMBRES))

    def test_la_hora_es_circular(self):
        self.assertAlmostEqual(caracteristicas._distancia_horaria(23.5, 0.5), 1)
        self.assertAlmostEqual(caracteristicas._hora_media([23, 1]) % 24, 0, places=5)

    def test_cliente_sin_historial_queda_neutral(self):
        x = caracteristicas.desde_contexto({**SILENCIOSO, "compras_previas": 0})
        self.assertEqual(x[3], 0.0)       # monto vs habitual
        self.assertEqual(x[4], 0.5)       # método habitual
        self.assertEqual(x[5], 0.5)       # hora vs habitual


@unittest.skipUnless(DISPONIBLE, "Keras o el modelo entrenado no están disponibles")
class DetectorIA(PruebaCapricho):
    CONFIG_EXTRA = {"IA_ACTIVA": True}

    def evaluar(self, datos):
        return self.enviar_json("POST", "/api/ia/evaluar", datos).get_json()["resultado"]

    def test_estado_del_modelo(self):
        estado = self.cliente.get("/api/ia/estado").get_json()
        self.assertTrue(estado["disponible"])
        self.assertEqual(estado["modelo"]["variables"], caracteristicas.NOMBRES)

    def test_compra_normal_tiene_riesgo_bajo(self):
        resultado = self.evaluar(NORMAL)
        self.assertFalse(resultado["anomalia"])
        self.assertLess(resultado["riesgo"], 50)

    def test_fraude_silencioso_es_anomalia(self):
        resultado = self.evaluar(SILENCIOSO)
        self.assertTrue(resultado["anomalia"])
        self.assertGreaterEqual(resultado["riesgo"], 50)

    def test_el_probador_valida(self):
        respuesta = self.enviar_json("POST", "/api/ia/evaluar", {**NORMAL, "valor": "mucho"})
        self.assertEqual(respuesta.status_code, 422)

    def test_modo_observar_no_cambia_el_resultado(self):
        self.como_admin()
        self.enviar_json("PATCH", "/api/configuracion", {"ia_modo": "observar"})
        cuerpo = self.enviar_txn("nuevo@cliente.com", self.hoy + timedelta(hours=3), valor=250000, metodo="PSE").get_json()
        self.assertEqual(cuerpo["resultado"], "NORMAL")
        self.assertIn("riesgo", cuerpo["transaccion"]["analisis"]["ia"])

    def test_endpoint_detecta_lo_que_las_reglas_no(self):
        usuario = "habitual@cliente.com"
        for dias in range(7, 1, -1):
            cuerpo = self.enviar_txn(usuario, self.hoy - timedelta(days=dias) + timedelta(hours=12, minutes=dias),
                                     valor=9000 + dias * 500, metodo="Nequi").get_json()
            self.assertEqual(cuerpo["estado"], "APROBADA")
        cuerpo = self.enviar_txn(usuario, self.hoy - timedelta(days=1) + timedelta(hours=3, minutes=10),
                                 valor=250000, metodo="PSE").get_json()
        # Ninguna regla de la primera entrega la ve; sí el clasificador, el autoencoder y los cuartiles del cliente.
        self.assertEqual(set(cuerpo["anomalias"]), {"FRAUDE_CLASIFICADOR", "COMPORTAMIENTO_INUSUAL",
                                                    "MONTO_FUERA_DE_CUARTILES"})
        self.assertEqual(cuerpo["estado"], "SOSPECHOSA")
        analisis = cuerpo["transaccion"]["analisis"]
        self.assertGreaterEqual(analisis["ia"]["riesgo"], 50)
        self.assertGreaterEqual(analisis["clasificador"]["probabilidad"], analisis["clasificador"]["umbral"])

    def test_cliente_nuevo_se_juzga_con_el_conocimiento_general(self):
        """Observación del profesor: sin historial, la red decide con lo que aprendió de todos."""
        nuevo = self.enviar_txn("recien.llegado@correo.co", self.hoy - timedelta(hours=20) + timedelta(hours=3),
                                valor=480000, metodo="PSE").get_json()
        normal = self.enviar_txn("otro.nuevo@correo.co", self.hoy - timedelta(hours=10), valor=12000,
                                 metodo="Nequi").get_json()
        clasificador = nuevo["transaccion"]["analisis"]["clasificador"]
        self.assertEqual(clasificador["segmento"], "cliente nuevo")
        self.assertEqual(clasificador["conocimiento"]["general"], 100.0)
        self.assertEqual(clasificador["clasificacion"], "FRAUDULENTA")
        self.assertEqual(normal["transaccion"]["analisis"]["clasificador"]["clasificacion"], "NORMAL")

    def test_inferencia_numpy_igual_a_keras(self):
        import numpy as np

        from capricho.ia import operaciones
        clasificador = self.app.extensions["capricho"].clasificador
        x = np.random.default_rng(1).normal(size=(50, len(operaciones.NOMBRES))).astype("float32")
        keras_p = clasificador.modelo.predict(x, verbose=0)[:, 0]
        self.assertLess(float(np.abs(clasificador.probabilidades(x) - keras_p).max()), 1e-4)


if __name__ == "__main__":
    unittest.main()
