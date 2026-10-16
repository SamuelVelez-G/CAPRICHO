/* Historial de pedidos del cliente. */

import { api, dinero, el, fechaCorta, icono, insignia, numero, vaciar } from "./comun.js";

const contenedor = document.getElementById("pedidos");
const { ok, datos } = await api("GET", "/api/pedidos/mios");

if (!ok || !datos.pedidos.length) {
  vaciar(contenedor, el("div", { class: "tarjeta vacio" }, icono("vaso"),
    el("p", { text: ok ? "Todavía no has hecho pedidos." : datos.error }),
    el("a", { class: "boton", href: "/#arma", text: "Hacer el primero" })));
} else {
  vaciar(contenedor, ...datos.pedidos.map((p) => el("article", { class: "tarjeta pedido-tarjeta" },
    el("div", { class: "pedido-tarjeta__cabeza" },
      el("h3", { text: `Pedido #${p.id}` }), insignia(p.estado)),
    el("p", { class: "muted", text: `${fechaCorta(p.fecha_creacion)} · ${p.metodo_pago} · ${p.tipo_entrega === "DOMICILIO"
      ? `${p.barrio} (${numero(p.distancia_km, 1)} km)` : "Recoger en tienda"}` }),
    el("ul", { class: "lineas-precio" }, ...p.items.map((i) => el("li", {},
      el("span", { text: `${i.cantidad} × ${i.nombre} · ${i.sabor}${i.adiciones.length ? " + " + i.adiciones.map((a) => a.nombre).join(", ") : ""}` }),
      el("span", { text: dinero(i.subtotal) }))),
      el("li", {}, el("span", { text: "Domicilio" }), el("span", { text: dinero(p.domicilio) })),
      el("li", {}, el("strong", { text: "Total" }), el("strong", { text: dinero(p.total) }))),
  )));
}
