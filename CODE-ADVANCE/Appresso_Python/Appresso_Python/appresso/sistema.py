from datetime import datetime
from .estructuras import Cola, Pila, Grafo
from .modelos import Cliente, Solicitud, Entrega

class Appresso:
    def __init__(self, rendimiento_km_l=40.0, precio_gasolina=16000.0):
        self.cola_solicitudes = Cola()
        self.pila_operaciones = Pila()
        self.grafo = Grafo()
        self.clientes = {}
        self.entregas = []
        self.rendimiento_km_l = rendimiento_km_l
        self.precio_gasolina = precio_gasolina
        self._id_cliente = 1
        self._id_solicitud = 1
        self._crear_mapa()

    def _crear_mapa(self):
        # Mapa de demostración basado en ciudades conectadas.
        conexiones = [
            ("Medellín", "Bogotá", 415),
            ("Medellín", "Pereira", 215),
            ("Medellín", "Manizales", 195),
            ("Pereira", "Cali", 210),
            ("Pereira", "Manizales", 155),
            ("Manizales", "Bogotá", 290),
            ("Cali", "Bogotá", 460),
            ("Bogotá", "Bucaramanga", 395),
            ("Medellín", "Bucaramanga", 390),
            ("Bogotá", "Cartagena", 1050),
            ("Bucaramanga", "Cartagena", 650),
        ]
        for a, b, d in conexiones:
            self.grafo.agregar_conexion(a, b, d)

    def registrar_cliente(self, nombre, telefono, ciudad):
        cliente = Cliente(self._id_cliente, nombre, telefono, ciudad)
        self.clientes[cliente.id] = cliente
        self._id_cliente += 1
        self.pila_operaciones.apilar(
            f"Registró cliente #{cliente.id}: {cliente.nombre}"
        )
        return cliente

    def crear_solicitud(self, cliente_id, producto, destino, cantidad):
        if cliente_id not in self.clientes:
            raise ValueError("El cliente no existe.")

        cliente = self.clientes[cliente_id]
        if destino not in self.grafo.adyacencia:
            raise ValueError("La ciudad destino no está en el mapa.")

        solicitud = Solicitud(
            self._id_solicitud,
            cliente,
            producto,
            cliente.ciudad,
            destino,
            cantidad,
            datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        )
        self._id_solicitud += 1
        self.cola_solicitudes.encolar(solicitud)
        self.pila_operaciones.apilar(
            f"Creó solicitud #{solicitud.id} para {cliente.nombre}"
        )
        return solicitud

    def procesar_siguiente_entrega(self):
        solicitud = self.cola_solicitudes.desencolar()
        if solicitud is None:
            return None

        ruta, distancia = self.grafo.dijkstra(
            solicitud.ciudad_origen,
            solicitud.ciudad_destino
        )

        if ruta is None:
            raise ValueError("No existe una ruta entre las ciudades.")

        litros = distancia / self.rendimiento_km_l
        costo = litros * self.precio_gasolina

        entrega = Entrega(
            solicitud,
            ruta,
            distancia,
            litros,
            costo,
            datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        )
        self.entregas.append(entrega)
        self.pila_operaciones.apilar(
            f"Procesó entrega #{solicitud.id}: {distancia:.1f} km"
        )
        return entrega

    def obtener_operaciones_recientes(self):
        return self.pila_operaciones.elementos()

    def solicitudes_pendientes(self):
        return self.cola_solicitudes.elementos()

    def rutas(self):
        return self.entregas
