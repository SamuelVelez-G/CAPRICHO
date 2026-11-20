"""
Población simulada para entrenar y evaluar el clasificador.

Un clasificador supervisado necesita ejemplos ETIQUETADOS (esto fue fraude,
esto no). Capricho no tiene miles de fraudes confirmados, así que se simula
una población de clientes con hábitos realistas (los mismos perfiles de la
semilla: horario, tamaño de pedido y método preferido) y se le meten fraudes
de 7 tipos, cada uno con su etiqueta.

Para que la red no aprenda atajos falsos, también hay casos legítimos
"difíciles": clientes nuevos que compran normal, pedidos grandes de una
familia u oficina, compras nocturnas de quien siempre compra de noche y
clientes que a veces cambian de método.

Todo es reproducible (semilla fija) y se recorre en orden cronológico,
calculando las variables con la misma función que se usa en vivo.
"""

import random
from collections import deque
from datetime import datetime, timedelta

from . import caracteristicas, operaciones

METODOS = operaciones.METODOS
PESOS_METODO = [7, 5, 3, 2, 3]
MONTOS = {"antojo": [7_000, 9_000, 9_000, 11_000, 12_000], "combo": [14_000, 16_000, 18_000, 21_000, 24_000],
          "familiar": [27_000, 32_000, 38_000, 45_000]}
VALORES = [7_000, 9_000, 11_000, 12_000, 14_000, 16_000, 18_000, 21_000, 24_000, 27_000, 32_000, 38_000]
HORARIOS = [8, 10, 13, 16, 19, 21]

TIPOS_FRAUDE = {
    "cuenta_tomada": "Cuenta tomada: monto muy alto para ese cliente, otro método y a deshoras",
    "cliente_nuevo": "Cuenta nueva con un monto alto a deshoras",
    "prueba_tarjeta": "Prueba de tarjeta: varios montos pequeños en minutos",
    "mula": "Cuenta nueva que paga varias veces con métodos distintos en una hora",
    "rafaga": "Ráfaga: 5 o más en menos de un segundo",
    "firma_invalida": "Firma (hash) que no coincide con los datos",
    "monto_extremo": "Monto extremo (más de $1.000.000)",
}
TIPOS_LEGITIMOS = {
    "normal": "Compra normal", "nuevo_legitimo": "Cliente nuevo que compra normal",
    "pedido_grande": "Pedido grande legítimo (familia u oficina)", "cambio_habito": "Cliente que cambió un hábito",
    "repite_el_dia": "Cliente que vuelve a comprar el mismo día",
}


class Cliente:
    def __init__(self, numero, rng, alta):
        self.id = f"sim{numero:05d}@clientes.co"
        self.alta = alta
        self.hora = rng.choice(HORARIOS) + rng.uniform(-1, 1)
        self.montos = MONTOS[rng.choices(list(MONTOS), weights=[5, 4, 2])[0]]
        self.metodo = rng.choices(METODOS, weights=PESOS_METODO)[0]
        self.frecuencia = rng.uniform(0.15, 1.0)          # probabilidad de comprar un día cualquiera


def generar(semilla=42, clientes=800, dias=90, inicio=datetime(2026, 7, 1)):
    """Devuelve la lista de operaciones en orden cronológico:
    {fecha, usuario, valor, metodo, firma_valida, fraude (0/1), tipo}."""
    rng = random.Random(semilla)
    poblacion = []
    for numero in range(clientes):
        alta = 0 if rng.random() < 0.45 else rng.randrange(0, dias - 3)
        poblacion.append(Cliente(numero, rng, alta))
    eventos = []
    nuevos = clientes

    def evento(fecha, usuario, valor, metodo, tipo, fraude, firma=True):
        eventos.append({"fecha": fecha, "usuario": usuario, "valor": float(valor), "metodo": metodo,
                        "firma_valida": firma, "fraude": fraude, "tipo": tipo})

    def instante(dia, hora):
        return inicio + timedelta(days=dia, hours=hora % 24, seconds=rng.randrange(60),
                                  milliseconds=rng.randrange(1000))

    def cuenta_nueva():
        nonlocal nuevos
        nuevos += 1
        return f"sim{nuevos:05d}@nuevos.co"

    for dia in range(dias):
        # --- compras legítimas -------------------------------------------------
        for cliente in poblacion:
            if dia < cliente.alta or rng.random() > cliente.frecuencia:
                continue
            tipo = "nuevo_legitimo" if dia - cliente.alta < 4 else "normal"
            hora = rng.gauss(cliente.hora, 1.3) if rng.random() < 0.85 else rng.uniform(7, 22)
            valor = rng.choice(cliente.montos) if rng.random() < 0.85 else rng.choice(VALORES)
            # El contexto también cambia el monto: el fin de semana se pide para la
            # familia y al almuerzo se piden combos (lo que aprende la regresión).
            if (inicio + timedelta(days=dia)).weekday() >= 5 and rng.random() < 0.6:
                valor = round(valor * rng.uniform(1.6, 2.4), -3)
            elif 12 <= hora < 14 and rng.random() < 0.55:
                valor = round(valor * rng.uniform(1.3, 1.7), -3)
            metodo = cliente.metodo if rng.random() < 0.8 else rng.choice(METODOS)
            if rng.random() < 0.015:
                metodo = "Transferencia"                 # un método fuera de la lista también es legítimo
            if rng.random() < 0.012:
                tipo, valor, hora = "pedido_grande", rng.randrange(60, 180) * 1000, rng.uniform(10, 17)
            elif rng.random() < 0.02:
                tipo, metodo, hora = "cambio_habito", rng.choice(METODOS), rng.uniform(6, 23)
            momento = instante(dia, max(5.0, min(23.4, hora)))
            evento(momento, cliente.id, valor, metodo, tipo, 0)
            # Volver el mismo día (otro granizado, uno para un amigo): a veces a los
            # pocos minutos y con otro método. Comprar dos veces en una hora es normal.
            while rng.random() < 0.18:
                momento += timedelta(minutes=rng.uniform(3, 150))
                if momento.day != (inicio + timedelta(days=dia)).day:
                    break
                otro = metodo if rng.random() < 0.65 else rng.choice(METODOS)
                evento(momento, cliente.id, rng.choice(cliente.montos), otro, "repite_el_dia", 0)

        # Los primeros días nadie tiene historia larga: se usan los clientes activos.
        establecidos = [c for c in poblacion if dia - c.alta >= 10] or [c for c in poblacion if c.alta <= dia]

        # --- fraudes ----------------------------------------------------------------
        for _ in range(_poisson(rng, 1.4)):                   # cuenta tomada
            victima = rng.choice(establecidos)
            hora = rng.uniform(0, 5) if rng.random() < 0.7 else rng.uniform(6, 23)
            otro = rng.choice([m for m in METODOS if m != victima.metodo])
            for _ in range(rng.choice([1, 1, 2])):
                valor = min(600_000, max(victima.montos) * rng.uniform(5, 22))
                evento(instante(dia, hora), victima.id, round(valor, -3), otro, "cuenta_tomada", 1)
                hora += rng.uniform(0.05, 0.5)
        for _ in range(_poisson(rng, 1.0)):                   # cuenta nueva con monto alto
            usuario = cuenta_nueva()
            hora = rng.choice([rng.uniform(22, 24), rng.uniform(0, 5)]) if rng.random() < 0.6 else rng.uniform(6, 22)
            metodo = rng.choice(["PSE", "Tarjeta", "Tarjeta"])
            for _ in range(rng.choice([1, 1, 2])):
                evento(instante(dia, hora), usuario, rng.randrange(150, 800) * 1000, metodo, "cliente_nuevo", 1)
                hora += rng.uniform(0.02, 0.3)
        for _ in range(_poisson(rng, 0.45)):                  # prueba de tarjeta
            usuario = cuenta_nueva() if rng.random() < 0.4 else rng.choice(establecidos).id
            momento = instante(dia, rng.uniform(0, 24))
            for _ in range(rng.randint(4, 7)):
                evento(momento, usuario, rng.choice([1_000, 1_500, 2_000, 2_500, 3_000]), "Tarjeta", "prueba_tarjeta", 1)
                momento += timedelta(seconds=rng.uniform(25, 200))
        for _ in range(_poisson(rng, 0.3)):                   # mula
            usuario = cuenta_nueva()
            momento = instante(dia, rng.uniform(8, 23))
            for metodo in rng.sample([*METODOS[:4], "Transferencia"], rng.randint(3, 4)):
                evento(momento, usuario, rng.randrange(60, 200) * 1000, metodo, "mula", 1)
                momento += timedelta(minutes=rng.uniform(4, 18))
        for _ in range(_poisson(rng, 0.25)):                  # ráfaga
            usuario = rng.choice(establecidos).id if establecidos and rng.random() < 0.6 else cuenta_nueva()
            momento = instante(dia, rng.uniform(0, 24))
            for _ in range(rng.randint(5, 7)):
                evento(momento, usuario, rng.choice(VALORES), rng.choice(METODOS), "rafaga", 1)
                momento += timedelta(milliseconds=rng.randint(90, 180))
        for _ in range(_poisson(rng, 0.9)):                   # firma inválida
            cliente = rng.choice(establecidos or poblacion)
            evento(instante(dia, rng.gauss(cliente.hora, 2) % 24), cliente.id, rng.choice(cliente.montos),
                   cliente.metodo, "firma_invalida", 1, firma=False)
        for _ in range(_poisson(rng, 0.35)):                  # monto extremo
            usuario = rng.choice(poblacion).id if rng.random() < 0.6 else cuenta_nueva()
            evento(instante(dia, rng.uniform(0, 24)), usuario, rng.randrange(1_200, 5_000) * 1000,
                   rng.choice(METODOS), "monto_extremo", 1)

    eventos.sort(key=lambda e: e["fecha"])
    return eventos


def _poisson(rng, media):
    """Cuántos eventos de un tipo ocurren en un día (Poisson, por el método de Knuth)."""
    limite, k, p = 2.718281828 ** -media, 0, 1.0
    while True:
        p *= rng.random()
        if p <= limite:
            return k
        k += 1


# =============================================================================
#  Variables, en orden cronológico, con la misma función que en vivo
# =============================================================================

def variables(eventos, mediana_poblacion):
    """Para cada operación: las variables del clasificador, las del autoencoder y
    lo que habrían dicho las reglas de la primera entrega (para comparar)."""
    historias = {}         # usuario -> deque de (fecha, valor, metodo), la más reciente al final
    totales = {}
    filas = []
    for e in eventos:
        historia = historias.setdefault(e["usuario"], deque(maxlen=operaciones.VENTANA_HISTORIA))
        previas = list(reversed(historia))
        total = totales.get(e["usuario"], 0)
        x, contexto = operaciones.vector(e["fecha"], e["valor"], e["metodo"], e["firma_valida"], previas, total,
                                         mediana_poblacion)
        filas.append({**e, "x": x, "contexto": contexto, "nuevo": total < operaciones.HISTORIAL_MINIMO,
                      "x_autoencoder": _vector_autoencoder(e, previas, total),
                      "reglas": _reglas(e, previas)})
        historia.append((e["fecha"], e["valor"], e["metodo"]))
        totales[e["usuario"]] = total + 1
    return filas


def _vector_autoencoder(e, previas, total):
    hora = e["fecha"].hour + e["fecha"].minute / 60
    ultimas = previas[:caracteristicas.VENTANA_HABITO]
    if ultimas:
        import statistics
        monto_habitual = statistics.median(p[1] for p in ultimas)
        proporcion = sum(1 for p in ultimas if p[2] == e["metodo"]) / len(ultimas)
        hora_habitual = caracteristicas._hora_media([p[0].hour + p[0].minute / 60 for p in ultimas])
        horas_desde = (e["fecha"] - previas[0][0]).total_seconds() / 3600
    else:
        monto_habitual, proporcion, hora_habitual, horas_desde = e["valor"], 0.5, hora, caracteristicas.TOPE_HORAS
    ultima_hora = sum(1 for p in previas if (e["fecha"] - p[0]).total_seconds() < 3600)
    return caracteristicas.vector(hora, e["valor"], monto_habitual, proporcion, hora_habitual, ultima_hora,
                                  horas_desde, total)


def _reglas(e, previas):
    """Las reglas de la primera entrega: ráfaga, ventana por franja, monto atípico y firma."""
    if not e["firma_valida"] or e["valor"] >= 300_000:
        return True
    hora = e["fecha"].hour
    ventana = 10 if 5 <= hora < 12 else 6 if 12 <= hora < 20 else 3
    segundos = [(e["fecha"] - p[0]).total_seconds() for p in previas]
    if sum(1 for s in segundos if s < 1) + 1 >= 5:
        return True
    return sum(1 for s in segundos if s < ventana) + 1 >= 3
