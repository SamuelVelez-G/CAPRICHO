"""
Envía transacciones firmadas con HMAC-SHA256 al endpoint de Capricho desde
la terminal. Solo usa la librería estándar.

Ejemplos (con el servidor corriendo):

    python herramientas/enviar_transacciones.py --usuario b@b.com --repetir 3 --intervalo 1000
    python herramientas/enviar_transacciones.py --usuario r@r.com --repetir 5 --intervalo 100    # ráfaga
    python herramientas/enviar_transacciones.py --usuario h@h.com --alterar                      # hash inválido
    python herramientas/enviar_transacciones.py --fecha 2026-09-23T10:00:01.000 --usuario c@c.com
"""

import argparse
import hashlib
import hmac
import json
import os
import time
import urllib.error
import urllib.request
from datetime import datetime

LLAVE = os.environ.get("CAPRICHO_LLAVE_HMAC", "capricho_llave_secreta_2026").encode("utf-8")


def firmar(transaccion: dict) -> str:
    """Igual que la diapositiva 19."""
    datos = json.dumps(transaccion, sort_keys=True, separators=(",", ":"))
    return hmac.new(LLAVE, datos.encode("utf-8"), hashlib.sha256).hexdigest()


def enviar(url: str, cuerpo: dict):
    peticion = urllib.request.Request(url, data=json.dumps(cuerpo).encode("utf-8"),
                                      headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(peticion) as respuesta:
            return respuesta.status, json.loads(respuesta.read())
    except urllib.error.HTTPError as error:
        return error.code, json.loads(error.read() or b"{}")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--servidor", default="http://127.0.0.1:5000")
    parser.add_argument("--usuario", default="aa@aa.com")
    parser.add_argument("--valor", type=float, default=50000)
    parser.add_argument("--metodo", default="Tarjeta", choices=["Tarjeta", "Nequi", "Daviplata", "PSE", "Efectivo"])
    parser.add_argument("--fecha", help="fecha fija ISO; si no se da, se usa la hora de cada envío")
    parser.add_argument("--repetir", type=int, default=1)
    parser.add_argument("--intervalo", type=int, default=0, help="milisegundos entre envíos")
    parser.add_argument("--alterar", action="store_true", help="cambia el valor después de firmar")
    argumentos = parser.parse_args()

    id_base = int(time.time() * 1000) % 1_000_000_000
    for n in range(argumentos.repetir):
        valor = int(argumentos.valor) if argumentos.valor.is_integer() else argumentos.valor
        transaccion = {
            "idTxn": id_base + n,
            "user": argumentos.usuario,
            "date": argumentos.fecha or datetime.now().isoformat(timespec="milliseconds"),
            "value": valor,
            "paymentMethod": argumentos.metodo,
        }
        transaccion["hash"] = firmar(transaccion)
        if argumentos.alterar:
            transaccion["value"] = valor + 1000

        codigo, respuesta = enviar(f"{argumentos.servidor}/api/transacciones", transaccion)
        txn = respuesta.get("transaccion")
        if txn:
            anomalias = ", ".join(f"{a['tipo']}/{a['nivel']}" for a in txn["anomalias"]) or "sin anomalías"
            print(f"{codigo}  {txn['idTxn']}  {txn['estado']:<10}  {anomalias}")
        else:
            print(f"{codigo}  {respuesta.get('error')}  {respuesta.get('errores', '')}")
        if argumentos.intervalo and n < argumentos.repetir - 1:
            time.sleep(argumentos.intervalo / 1000)


if __name__ == "__main__":
    main()
