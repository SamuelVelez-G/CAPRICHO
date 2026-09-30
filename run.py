"""
Arranca Capricho.

    python run.py              servidor en http://127.0.0.1:5000
    python run.py --reiniciar  borra la base de datos y vuelve a crear los datos de demo
    python run.py --puerto 8000
"""

import argparse
from pathlib import Path

from capricho import create_app
from capricho.config import Configuracion


def main():
    parser = argparse.ArgumentParser(description="Capricho — tienda y monitoreo antifraude")
    parser.add_argument("--reiniciar", action="store_true", help="borra la base de datos y la vuelve a sembrar")
    parser.add_argument("--puerto", type=int, default=5000)
    parser.add_argument("--host", default="127.0.0.1")
    argumentos = parser.parse_args()

    if argumentos.reiniciar:
        for sufijo in ("", "-wal", "-shm"):
            Path(Configuracion.BASE_DATOS + sufijo).unlink(missing_ok=True)
        print("Base de datos borrada. Se crearán datos de demostración nuevos.")

    app = create_app()
    print(f"\n  Capricho corriendo en http://{argumentos.host}:{argumentos.puerto}")
    print(f"  Administrador: {app.config['ADMIN_EMAIL']} / {app.config['ADMIN_PASSWORD']}")
    print(f"  Cliente demo:  {app.config['CLIENTE_DEMO_EMAIL']} / {app.config['CLIENTE_DEMO_PASSWORD']}\n")
    app.run(host=argumentos.host, port=argumentos.puerto, debug=False, threaded=True)


if __name__ == "__main__":
    main()
