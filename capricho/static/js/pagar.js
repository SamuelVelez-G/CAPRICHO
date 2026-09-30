/*
 * Página de pago.
 *
 * El cuerpo que se envía lleva lo que el navegador CREE que cuesta cada cosa
 * (precio_unitario y total, leídos del localStorage en el momento de pagar).
 * El servidor no los usa para cobrar: los compara con su propio cálculo.
 */

import { api, dinero, el, icono, mostrarErrores, numero, toast, vaciar } from "./comun.js";
import { leer, reconciliar, subtotal, vaciarCarrito } from "./carrito.js";
import { conectarFormulario } from "./validacion.js";
import { cargarMapa, resumenRuta } from "./mapa.js";

const METODOS = [
  ["Nequi", "Nequi"], ["Daviplata", "Daviplata"], ["Tarjeta", "Tarjeta"], ["PSE", "PSE"], ["Efectivo", "Efectivo contra entrega"],
];

const formulario = document.getElementById("form-pagar");
const conSesion = document.body.dataset.rol !== "";
let tarifa = 0;
let pagado = false;

function tipoEntrega() {
  return formulario.querySelector('input[name="tipo_entrega"]:checked').value;
}

function pintarResumen() {
  if (pagado) return;
  const lineas = leer();
  if (!lineas.length) {
    vaciar(document.getElementById("zona-formulario"),
      el("p", { class: "eyebrow", text: "Tu carrito" }), el("h1", { text: "Aún no hay nada por pagar" }),
      el("a", { class: "boton", href: "/#arma" }, icono("vaso"), " Armar un granizado"));
    vaciar(document.getElementById("resumen-pedido"));
    ["resumen-subtotal", "resumen-total"].forEach((id) => { document.getElementById(id).textContent = dinero(0); });
    document.getElementById("resumen-domicilio").textContent = "—";
    return;
  }
  vaciar(document.getElementById("resumen-pedido"), ...lineas.map((l) =>
    el("li", {}, el("span", { text: `${l.cantidad} × ${l.nombre} · ${l.sabor}${l.adiciones.length ? " + " + l.adiciones.map((a) => a.nombre).join(", ") : ""}` }),
      el("span", { text: dinero(l.precio_unitario * l.cantidad) }))));
  const domicilio = tipoEntrega() === "DOMICILIO" ? tarifa : 0;
  document.getElementById("resumen-subtotal").textContent = dinero(subtotal(lineas));
  document.getElementById("resumen-domicilio").textContent =
    tipoEntrega() === "RECOGER" ? "Gratis" : tarifa ? dinero(tarifa) : "Elige barrio";
  const total = subtotal(lineas) + domicilio;
  document.getElementById("resumen-total").textContent = dinero(total);
  document.querySelector("#boton-pagar span").textContent = `Pagar ${dinero(total)}`;
}

async function iniciar() {
  await reconciliar();
  vaciar(document.getElementById("metodos-pago"), ...METODOS.map(([valor, texto], i) =>
    el("label", { class: "opcion" }, el("input", { type: "radio", name: "metodo_pago", value: valor, checked: i === 0 }),
      el("span", { class: "opcion__cuerpo" }, el("strong", { text: texto })))));

  const mapa = await cargarMapa();
  const selector = document.getElementById("campo-barrio");
  if (mapa) {
    [...mapa.nodos].sort((a, b) => a.nombre.localeCompare(b.nombre, "es")).forEach((n) =>
      selector.append(el("option", { value: n.nombre, text: `${n.nombre} · ${dinero(n.tarifa)}` })));
  }
  selector.addEventListener("change", async () => {
    tarifa = 0;
    vaciar(document.getElementById("ruta-pedido"));
    if (selector.value) {
      const { ok, datos } = await api("GET", `/api/domicilios/cotizar?barrio=${encodeURIComponent(selector.value)}`);
      if (ok) {
        tarifa = datos.domicilio.tarifa;
        vaciar(document.getElementById("ruta-pedido"), resumenRuta(datos.domicilio));
      }
    }
    pintarResumen();
  });

  formulario.addEventListener("change", (evento) => {
    if (evento.target.name === "tipo_entrega") {
      const domicilio = tipoEntrega() === "DOMICILIO";
      document.getElementById("campos-domicilio").hidden = !domicilio;
      formulario.querySelectorAll("#campos-domicilio [data-regla]").forEach((c) => { c.disabled = !domicilio; });
      pintarResumen();
    }
  });

  const validar = conectarFormulario(formulario);
  formulario.addEventListener("submit", (evento) => {
    evento.preventDefault();
    if (!conSesion) return;
    if (validar()) pagar();
  });
  document.addEventListener("carrito-cambio", pintarResumen);
  pintarResumen();
}

async function pagar() {
  const boton = document.getElementById("boton-pagar");
  const errorGeneral = document.getElementById("error-general");
  errorGeneral.hidden = true;

  // Se lee el localStorage JUSTO ahora: si alguien lo editó, eso es lo que viaja.
  const lineas = leer();
  const domicilio = tipoEntrega() === "DOMICILIO";
  const cuerpo = {
    items: lineas.map((l) => ({
      producto_id: l.producto_id, sabor: l.sabor, cantidad: l.cantidad,
      adiciones: l.adiciones.map((a) => a.id), precio_unitario: l.precio_unitario,
    })),
    tipo_entrega: tipoEntrega(),
    barrio: domicilio ? formulario.barrio.value : null,
    direccion: domicilio ? formulario.direccion.value : null,
    metodo_pago: formulario.querySelector('input[name="metodo_pago"]:checked').value,
    total: subtotal(lineas) + (domicilio ? tarifa : 0),
  };

  boton.disabled = true;
  const { status, datos } = await api("POST", "/api/pedidos", cuerpo);
  boton.disabled = false;

  if (status === 201) {
    pagado = true;
    vaciarCarrito();
    mostrarExito(datos.pedido);
    return;
  }
  const detalle = [el("p", {}, el("strong", { text: datos.error }))];
  if (status === 409 && datos.total_real !== undefined) {
    detalle.push(el("p", { text: `Enviaste ${dinero(datos.total_enviado)} y el valor real es ${dinero(datos.total_real)}. El intento quedó registrado como anomalía.` }));
    detalle.push(el("button", { class: "boton boton--sm", type: "button", onClick: async () => { await reconciliar(); pintarResumen(); errorGeneral.hidden = true; } },
      icono("actualizar"), " Restaurar precios oficiales"));
  }
  if (status === 429 && datos.pedido) {
    detalle.push(el("p", { text: "El detector bloqueó el pago: demasiadas compras en un segundo desde tu cuenta." }));
  }
  if (status === 401) detalle.push(el("a", { href: "/ingresar?siguiente=/pagar", text: "Inicia sesión otra vez" }));
  vaciar(errorGeneral.querySelector("div"), ...detalle);
  errorGeneral.hidden = false;
  if (datos.errores) mostrarErrores(formulario, datos.errores);
  errorGeneral.scrollIntoView({ behavior: "smooth", block: "center" });
}

function mostrarExito(pedido) {
  const sospechoso = pedido.pago.estado === "SOSPECHOSA";
  // El resumen pasa a mostrar lo que calculó y cobró el servidor.
  vaciar(document.getElementById("resumen-pedido"), ...pedido.items.map((i) =>
    el("li", {}, el("span", { text: `${i.cantidad} × ${i.nombre} · ${i.sabor}${i.adiciones.length ? " + " + i.adiciones.map((a) => a.nombre).join(", ") : ""}` }),
      el("span", { text: dinero(i.subtotal) }))));
  document.getElementById("resumen-subtotal").textContent = dinero(pedido.subtotal);
  document.getElementById("resumen-domicilio").textContent = pedido.domicilio ? dinero(pedido.domicilio) : "Gratis";
  document.getElementById("resumen-total").textContent = dinero(pedido.total);
  vaciar(document.getElementById("zona-formulario"),
    el("div", { class: "tarjeta resultado-pedido" },
      icono("ok", "icono-grande"),
      el("p", { class: "eyebrow", text: `Pedido #${pedido.id}` }),
      el("h1", { text: "¡Tu Capricho va en camino!" }),
      el("p", { text: pedido.posicion_en_cola
        ? `Entró a la cola de preparación en la posición ${pedido.posicion_en_cola}. Se atiende en orden de llegada.`
        : "Tu pedido fue registrado." }),
      pedido.ruta ? el("p", { class: "muted", text: `Ruta: ${pedido.ruta.join(" → ")} · ${numero(pedido.distancia_km, 1)} km` }) : null,
      el("p", {}, el("strong", { text: `Total cobrado: ${dinero(pedido.total)}` })),
      sospechoso ? el("div", { class: "aviso aviso--alerta" }, icono("alerta"),
        el("p", { text: "Tu pago quedó marcado para revisión porque hiciste varias compras muy seguidas." })) : null,
      el("div", { class: "hero__acciones" },
        el("a", { class: "boton", href: "/mis-pedidos", text: "Ver mis pedidos" }),
        el("a", { class: "boton boton--contorno", href: "/#arma", text: "Pedir otro" }))));
  toast(`Pedido #${pedido.id} confirmado.`, "ok");
}

iniciar();
