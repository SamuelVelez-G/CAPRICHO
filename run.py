"""
Arranca Capricho.

    python run.py                       servidor en http://127.0.0.1:5000
    python run.py --reiniciar           borra la base de datos y crea 9 semanas de datos de demo
    python run.py --reiniciar --limpio  borra la base de datos y la deja SIN transacciones
                                        (solo productos y cuentas): para la prueba del profesor
    python run.py --puerto 8000
"""

import argparse
from pathlib import Path

from capricho import create_app
from capricho.config import Configuracion


def main():
    parser = argparse.ArgumentParser(description="Capricho — tienda y monitoreo antifraude")
    parser.add_argument("--reiniciar", action="store_true", help="borra la base de datos y la vuelve a sembrar")
    parser.add_argument("--limpio", action="store_true", help="con --reiniciar: sin transacciones de demostración")
    parser.add_argument("--puerto", type=int, default=5000)
    parser.add_argument("--host", default="127.0.0.1")
    argumentos = parser.parse_args()

    if argumentos.reiniciar:
        for sufijo in ("", "-wal", "-shm"):
            Path(Configuracion.BASE_DATOS + sufijo).unlink(missing_ok=True)
        print("Base de datos borrada. " + ("Queda sin transacciones (modo limpio)." if argumentos.limpio
                                           else "Se crearán datos de demostración nuevos."))

    app = create_app({"SEMBRAR": "base"} if argumentos.limpio else None)
    print(f"\n  Capricho corriendo en http://{argumentos.host}:{argumentos.puerto}")
    print(f"  Administrador: {app.config['ADMIN_EMAIL']} / {app.config['ADMIN_PASSWORD']}")
    print(f"  Cliente demo:  {app.config['CLIENTE_DEMO_EMAIL']} / {app.config['CLIENTE_DEMO_PASSWORD']}")
    print(f"  Endpoint:      POST http://{argumentos.host}:{argumentos.puerto}/api/transacciones\n")
    app.run(host=argumentos.host, port=argumentos.puerto, debug=False, threaded=True)


if __name__ == "__main__":
    main()
