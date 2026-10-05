from appresso.sistema import Appresso

def dinero(valor):
    return f"${valor:,.0f}".replace(",", ".")

def mostrar_menu():
    print("\n" + "=" * 58)
    print("                 APPRESSO ☕")
    print("              Tu café, a un tap")
    print("=" * 58)
    print("1. Registrar cliente")
    print("2. Crear solicitud / pedido")
    print("3. Ver solicitudes pendientes (COLA FIFO)")
    print("4. Procesar siguiente entrega")
    print("5. Ver operaciones recientes (PILA LIFO)")
    print("6. Calcular ruta más corta con Dijkstra")
    print("7. Ver historial de entregas")
    print("8. Configurar gasolina")
    print("9. Cargar datos de demostración")
    print("0. Salir")
    print("=" * 58)

def datos_demo(app):
    c1 = app.registrar_cliente("Daniel", "3001234567", "Medellín")
    c2 = app.registrar_cliente("Laura", "3017654321", "Pereira")
    c3 = app.registrar_cliente("Carlos", "3025551234", "Bogotá")

    app.crear_solicitud(c1.id, "Café especial", "Bogotá", 2)
    app.crear_solicitud(c2.id, "Combo de café", "Cali", 1)
    app.crear_solicitud(c3.id, "Café molido", "Medellín", 3)
    print("\nDatos de demostración cargados correctamente.")

def main():
    app = Appresso()

    while True:
        mostrar_menu()
        opcion = input("Seleccione una opción: ").strip()

        try:
            if opcion == "1":
                nombre = input("Nombre: ")
                telefono = input("Teléfono: ")
                ciudad = input("Ciudad de origen: ")
                if ciudad not in app.grafo.adyacencia:
                    print("Ciudad no disponible en el mapa.")
                    continue
                cliente = app.registrar_cliente(nombre, telefono, ciudad)
                print(f"Cliente registrado con ID #{cliente.id}.")

            elif opcion == "2":
                if not app.clientes:
                    print("Primero registre un cliente.")
                    continue
                print("\nClientes:")
                for c in app.clientes.values():
                    print(f"#{c.id} - {c.nombre} ({c.ciudad})")

                cid = int(input("ID del cliente: "))
                producto = input("Producto: ")
                destino = input("Ciudad destino: ")
                cantidad = int(input("Cantidad: "))

                solicitud = app.crear_solicitud(cid, producto, destino, cantidad)
                print(f"Solicitud #{solicitud.id} agregada a la cola.")

            elif opcion == "3":
                pendientes = app.solicitudes_pendientes()
                if not pendientes:
                    print("No hay solicitudes pendientes.")
                else:
                    print("\n--- COLA FIFO ---")
                    for s in pendientes:
                        print(
                            f"#{s.id} | {s.cliente.nombre} | "
                            f"{s.producto} x{s.cantidad} | "
                            f"{s.ciudad_origen} -> {s.ciudad_destino}"
                        )

            elif opcion == "4":
                entrega = app.procesar_siguiente_entrega()
                if entrega is None:
                    print("No hay solicitudes para procesar.")
                else:
                    print("\n--- ENTREGA PROCESADA ---")
                    print(f"Solicitud: #{entrega.solicitud.id}")
                    print(f"Cliente: {entrega.solicitud.cliente.nombre}")
                    print("Ruta:", " -> ".join(entrega.ruta))
                    print(f"Distancia: {entrega.distancia_km:.1f} km")
                    print(f"Gasolina: {entrega.litros:.2f} L")
                    print(f"Costo: {dinero(entrega.costo_gasolina)}")

            elif opcion == "5":
                operaciones = app.obtener_operaciones_recientes()
                if not operaciones:
                    print("No hay operaciones.")
                else:
                    print("\n--- PILA LIFO: más reciente primero ---")
                    for op in operaciones:
                        print("-", op)

            elif opcion == "6":
                origen = input("Ciudad de origen: ")
                destino = input("Ciudad destino: ")
                ruta, distancia = app.grafo.dijkstra(origen, destino)
                if ruta is None:
                    print("No existe una ruta.")
                else:
                    print("\n--- DIJKSTRA ---")
                    print("Ruta:", " -> ".join(ruta))
                    print(f"Distancia mínima: {distancia:.1f} km")
                    litros = distancia / app.rendimiento_km_l
                    costo = litros * app.precio_gasolina
                    print(f"Consumo estimado: {litros:.2f} L")
                    print(f"Costo estimado: {dinero(costo)}")

            elif opcion == "7":
                if not app.rutas():
                    print("No hay entregas realizadas.")
                else:
                    print("\n--- HISTORIAL DE ENTREGAS ---")
                    for e in app.rutas():
                        print(
                            f"#{e.solicitud.id} | {e.solicitud.cliente.nombre} | "
                            f"{' -> '.join(e.ruta)} | "
                            f"{e.distancia_km:.1f} km | "
                            f"{e.litros:.2f} L | {e.costo_formateado}"
                        )

            elif opcion == "8":
                rendimiento = float(input("Rendimiento del vehículo (km/L): "))
                precio = float(input("Precio de gasolina por litro: "))
                if rendimiento <= 0 or precio < 0:
                    print("Valores inválidos.")
                    continue
                app.rendimiento_km_l = rendimiento
                app.precio_gasolina = precio
                print("Configuración actualizada.")

            elif opcion == "9":
                datos_demo(app)

            elif opcion == "0":
                print("¡Gracias por usar Appresso!")
                break

            else:
                print("Opción inválida.")

        except ValueError as e:
            print(f"Error: {e}")
        except Exception as e:
            print(f"Error inesperado: {e}")

if __name__ == "__main__":
    main()
