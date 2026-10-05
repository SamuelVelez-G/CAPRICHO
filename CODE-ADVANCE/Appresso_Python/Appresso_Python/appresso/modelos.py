from dataclasses import dataclass
from datetime import datetime

@dataclass
class Cliente:
    id: int
    nombre: str
    telefono: str
    ciudad: str

@dataclass
class Solicitud:
    id: int
    cliente: Cliente
    producto: str
    ciudad_origen: str
    ciudad_destino: str
    cantidad: int
    fecha: str

@dataclass
class Entrega:
    solicitud: Solicitud
    ruta: list
    distancia_km: float
    litros: float
    costo_gasolina: float
    fecha: str

    @property
    def costo_formateado(self):
        return f"${self.costo_gasolina:,.0f}".replace(",", ".")
