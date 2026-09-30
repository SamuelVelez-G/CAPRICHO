"""
Errores de la API.

Cada error sabe qué código HTTP devolver y, si vale la pena, qué evento de
seguridad dejar en la pila de errores para que el administrador lo vea.
"""


class ErrorApi(Exception):
    codigo = 400
    tipo_evento = None      # si no es None, se registra en la bitácora
    nivel_evento = "BAJO"

    def __init__(self, mensaje, detalles=None):
        super().__init__(mensaje)
        self.mensaje = mensaje
        self.detalles = detalles or {}

    def cuerpo(self):
        cuerpo = {"ok": False, "error": self.mensaje}
        if self.detalles:
            cuerpo["errores"] = self.detalles
        return cuerpo


class ErrorValidacion(ErrorApi):
    """Uno o varios campos no cumplen las reglas. `detalles` = {campo: mensaje}."""
    codigo = 422
    tipo_evento = "VALIDACION"

    def __init__(self, errores, mensaje="Hay datos inválidos en la solicitud"):
        super().__init__(mensaje, errores)


class ErrorInyeccion(ErrorApi):
    codigo = 400
    tipo_evento = "INYECCION_SQL"
    nivel_evento = "CRITICO"

    def __init__(self, campo, patron, valor=""):
        super().__init__(
            "Solicitud bloqueada: se detectó un posible intento de inyección SQL",
            {campo: f"Contiene un patrón de inyección SQL ({patron})"},
        )
        # Se guarda un extracto del ataque para la bitácora (se muestra escapado).
        self.extracto = f"{campo}: {valor[:120]}"


class ErrorNoAutenticado(ErrorApi):
    codigo = 401


class ErrorProhibido(ErrorApi):
    codigo = 403


class ErrorNoEncontrado(ErrorApi):
    codigo = 404


class ErrorConflicto(ErrorApi):
    codigo = 409


class ErrorReplay(ErrorConflicto):
    """Llegó otra vez un idTxn que ya se había procesado."""
    tipo_evento = "REPLAY"
    nivel_evento = "ALTO"


class ErrorPrecioManipulado(ErrorConflicto):
    """El total que mandó el navegador no coincide con el que calcula el servidor."""
    tipo_evento = "PRECIO_MANIPULADO"
    nivel_evento = "ALTO"

    def __init__(self, mensaje, extra):
        super().__init__(mensaje, {"total": "No coincide con el precio real"})
        self.extra = extra

    def cuerpo(self):
        return {**super().cuerpo(), **self.extra}


class ErrorLimite(ErrorApi):
    codigo = 429
    tipo_evento = "LIMITE_PETICIONES"
    nivel_evento = "MEDIO"
