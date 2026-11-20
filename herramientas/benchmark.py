"""
Benchmark completo de los algoritmos (hasta 50.000 datos) sobre la base de Capricho.

    python herramientas/benchmark.py              guarda el resultado en la base y escribe docs/INFORME_ALGORITMOS.md
    python herramientas/benchmark.py --rapido     solo hasta 2.000 datos (unos segundos)

La página /algoritmos muestra el último resultado guardado.
"""

import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from capricho.config import Configuracion  # noqa: E402
from capricho.db import conectar, crear_esquema  # noqa: E402
from capricho.servicios import benchmark  # noqa: E402

INFORME = RAIZ / "docs" / "INFORME_ALGORITMOS.md"


def ms(valor):
    return f"{valor / 1000:.2f} s" if valor >= 1000 else f"{valor:.2f} ms" if valor >= 1 else f"{valor * 1000:.0f} µs"


def informe(resultado):
    lineas = [
        "# Informe del análisis experimental de algoritmos", "",
        f"Generado por `herramientas/benchmark.py` el {resultado['fecha'][:16].replace('T', ' ')} "
        f"en {resultado['equipo']} ({resultado['duracion_s']} s).", "",
        "Cada problema se resolvió de varias formas sobre datos reales de la base de Capricho (replicados para los "
        "tamaños grandes). Se midió el mejor de varios intentos con `time.perf_counter`, se contaron las operaciones "
        "básicas y se verificó que todas las variantes dieran el mismo resultado. La **pendiente** es el exponente "
        "estimado con una regresión lineal de log(tiempo) contra log(n): ≈ 0 es constante, ≈ 1 lineal, ≈ 2 cuadrático.", "",
    ]
    for p in resultado["problemas"]:
        lineas += [f"## {p['titulo']}", "", p["descripcion"] + (" Todas las variantes dieron el mismo resultado." if p["verificado"] else ""), ""]
        encabezado = "| Variante | Teoría | " + " | ".join(f"n = {n:,}".replace(",", ".") for n in resultado["tamanos"]) + " | Pendiente | R² |"
        lineas += [encabezado, "|" + "---|" * (len(resultado["tamanos"]) + 4)]
        for v in p["variantes"]:
            celdas = []
            for n in resultado["tamanos"]:
                punto = next((x for x in v["puntos"] if x["n"] == n), None)
                celdas.append("—" if punto is None else f"~{ms(punto['estimado_ms'])}*" if punto.get("omitido") else ms(punto["ms"]))
            lineas.append(f"| {v['nombre']} | {v['complejidad']} | " + " | ".join(celdas) +
                          f" | {v['pendiente'] if v['pendiente'] is not None else '—'} | {v['r2'] if v['r2'] is not None else '—'} |")
        m = p["mejora"]
        if m:
            lineas += ["", f"**Mejora:** con n = {m['n']:,}".replace(",", ".") +
                       f", {m['rapida']} ({m['rapida_complejidad']}) tarda {ms(m['rapida_ms'])} y {m['lenta']} "
                       f"({m['lenta_complejidad']}) {'tardaría' if m['estimado'] else 'tarda'} {ms(m['lenta_ms'])}: "
                       f"**{m['veces']:,.0f} veces más rápido**.".replace(",", ".")]
        lineas.append("")
    lineas += ["\\* Tiempo estimado: con ese tamaño la variante tardaría demasiado y no se corrió; se proyectó con su complejidad.", ""]
    return "\n".join(lineas)


def main():
    tipo = "RAPIDO" if "--rapido" in sys.argv else "COMPLETO"
    conexion = conectar(Configuracion.BASE_DATOS)
    crear_esquema(conexion)
    if not conexion.execute("SELECT COUNT(*) FROM transacciones").fetchone()[0]:
        sys.exit("La base no tiene datos. Ejecuta primero: python run.py --reiniciar")
    print(f"Benchmark {tipo.lower()} sobre {Configuracion.BASE_DATOS}...")
    resultado = benchmark.correr(conexion, tipo, al_avanzar=lambda texto: print("  ", texto))
    benchmark.guardar(conexion, resultado)
    INFORME.parent.mkdir(exist_ok=True)
    INFORME.write_text(informe(resultado), encoding="utf-8")
    print(f"\nListo en {resultado['duracion_s']} s. Guardado en la base e informe en {INFORME}")
    for p in resultado["problemas"]:
        if p["mejora"]:
            print(f"  {p['titulo']:38} {p['mejora']['veces']:>10,.0f}×  ({p['mejora']['lenta_complejidad']} → {p['mejora']['rapida_complejidad']})")


if __name__ == "__main__":
    main()
