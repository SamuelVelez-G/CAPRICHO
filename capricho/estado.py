"""
Estructuras que viven en memoria mientras el servidor está encendido.

La base de datos es la fuente de verdad; estas estructuras se reconstruyen
desde ella al arrancar (O(n) una sola vez) y se mantienen al día con cada
operación. Así las consultas frecuentes no tocan el disco.
"""

import threading

from .estructuras import Cola, IndiceHash, LimitadorVentana, Pila


class EstadoMemoria:
    def __init__(self, llave_hmac: bytes, limite_por_segundo=40):
        self.llave_hmac = llave_hmac               # para firmar las compras de la tienda
        self.cola_pedidos = Cola()                 # ids de pedidos SOLICITADOS
        self.pila_errores = Pila()                 # eventos sin atender
        self.indice_usuarios = IndiceHash()        # email  -> id
        self.indice_transacciones = IndiceHash()   # idTxn  -> id
        self.limitador_ip = LimitadorVentana(limite_por_segundo, 1)
        self.limitador_login = LimitadorVentana(5, 300)   # 5 fallos en 5 minutos
        # Un solo hilo a la vez puede analizar y guardar una transacción.
        # Sin esto, dos peticiones simultáneas contarían la misma ventana
        # y ninguna vería a la otra (condición de carrera).
        self.candado = threading.RLock()

    def reconstruir(self, db):
        with self.candado:
            self.indice_usuarios = IndiceHash(
                (fila["email"], fila["id"]) for fila in db.execute("SELECT id, email FROM usuarios")
            )
            self.indice_transacciones = IndiceHash(
                (fila["id_txn"], fila["id"]) for fila in db.execute("SELECT id, id_txn FROM transacciones")
            )
            self.cola_pedidos = Cola(
                fila["id"] for fila in db.execute(
                    "SELECT id FROM pedidos WHERE estado = 'SOLICITADO' ORDER BY fecha_creacion, id")
            )
            self.pila_errores = Pila(
                dict(fila) for fila in db.execute(
                    """SELECT id, tipo, nivel, detalle, ruta, metodo, ip, email, fecha
                       FROM eventos WHERE atendido = 0 ORDER BY fecha, id""")
            )
