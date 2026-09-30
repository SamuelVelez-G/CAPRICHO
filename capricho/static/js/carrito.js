/*
 * Carrito guardado en localStorage.
 *
 * El localStorage es del usuario: lo puede abrir en las herramientas del
 * navegador y cambiar lo que quiera. Por eso aquí el precio es solo para
 * MOSTRAR. Dos defensas:
 *   1. Al cargar la página se comparan los precios guardados con los del
 *      servidor y se corrigen (con un aviso).
 *   2. Al pagar, el servidor recalcula todo. Si lo que manda el navegador no
 *      coincide, rechaza la compra y registra la anomalía PRECIO_MANIPULADO.
 */

import { api, dinero, el, icono, toast, vaciar } from "./comun.js";

const CLAVE = "capricho_carrito";

export function leer() {
  try {
    const datos = JSON.parse(localStorage.getItem(CLAVE) || "[]");
    return Array.isArray(datos) ? datos : [];
  } catch {
    return [];
  }
}

function guardar(lineas) {
  localStorage.setItem(CLAVE, JSON.stringify(lineas));
  pintar();
  document.dispatchEvent(new CustomEvent("carrito-cambio"));
}

export function agregar(linea) {
  const lineas = leer();
  const clave = firma(linea);
  const existente = lineas.find((l) => firma(l) === clave);
  if (existente) existente.cantidad = Math.min(10, existente.cantidad + linea.cantidad);
  else lineas.push({ ...linea, id: crypto.randomUUID() });
  guardar(lineas);
}

const firma = (l) => `${l.producto_id}|${l.sabor}|${[...l.adiciones.map((a) => a.id)].sort().join(",")}`;

export function cambiarCantidad(id, delta) {
  const lineas = leer();
  const linea = lineas.find((l) => l.id === id);
  if (!linea) return;
  linea.cantidad = Math.max(1, Math.min(10, linea.cantidad + delta));
  guardar(lineas);
}

export function quitar(id) {
  guardar(leer().filter((l) => l.id !== id));
}

export function vaciarCarrito() {
  guardar([]);
}

export const subtotal = (lineas = leer()) =>
  lineas.reduce((suma, l) => suma + Number(l.precio_unitario) * Number(l.cantidad), 0);

/** Compara con los precios oficiales y corrige. Devuelve cuántas líneas cambió. */
export async function reconciliar() {
  const lineas = leer();
  if (!lineas.length) return 0;
  const { ok, datos } = await api("GET", "/api/productos");
  if (!ok) return 0;
  const precios = new Map(datos.productos.map((p) => [p.id, p]));
  let cambios = 0;
  const limpias = [];
  for (const linea of lineas) {
    const granizado = precios.get(linea.producto_id);
    const adiciones = (linea.adiciones || []).map((a) => precios.get(a.id)).filter(Boolean);
    if (!granizado || adiciones.length !== (linea.adiciones || []).length) { cambios++; continue; }
    const real = granizado.precio + adiciones.reduce((s, a) => s + a.precio, 0);
    const cantidad = Math.max(1, Math.min(10, parseInt(linea.cantidad, 10) || 1));
    if (real !== linea.precio_unitario || cantidad !== linea.cantidad) cambios++;
    limpias.push({ ...linea, precio_unitario: real, cantidad, nombre: granizado.nombre,
      adiciones: adiciones.map((a) => ({ id: a.id, nombre: a.nombre, precio: a.precio })) });
  }
  if (cambios) {
    guardar(limpias);
    toast("Detectamos precios modificados en tu carrito. Restauramos los precios oficiales.", "alerta", 6500);
  }
  return cambios;
}

// --- Panel lateral -------------------------------------------------------------
function pintar() {
  const lineas = leer();
  const cuenta = lineas.reduce((s, l) => s + Number(l.cantidad || 0), 0);
  const insignia = document.getElementById("cuenta-carrito");
  if (insignia) {
    insignia.textContent = cuenta ? String(cuenta) : "";
    insignia.toggleAttribute("data-cero", !cuenta);
  }
  const contenedor = document.getElementById("carrito-lineas");
  if (!contenedor) return;
  document.getElementById("carrito-total").textContent = dinero(subtotal(lineas));
  document.getElementById("ir-a-pagar").hidden = !lineas.length;
  if (!lineas.length) {
    vaciar(contenedor, el("div", { class: "vacio" }, icono("vaso"), el("p", { text: "Tu carrito está vacío." }),
      el("a", { href: "/#arma", class: "boton boton--sm", text: "Armar un granizado", onClick: cerrar })));
    return;
  }
  vaciar(contenedor, ...lineas.map((linea) => el("div", { class: "linea-carrito" },
    el("div", {},
      el("h4", { text: `${linea.nombre} · ${linea.sabor}` }),
      el("p", { text: linea.adiciones.length ? "Con " + linea.adiciones.map((a) => a.nombre).join(", ") : "Sin adiciones" })),
    el("div", { class: "linea-carrito__precio", text: dinero(linea.precio_unitario * linea.cantidad) }),
    el("div", { class: "linea-carrito__acciones" },
      el("div", { class: "cantidad" },
        el("button", { type: "button", "aria-label": "Quitar uno", onClick: () => cambiarCantidad(linea.id, -1) }, icono("menos")),
        el("output", { text: linea.cantidad }),
        el("button", { type: "button", "aria-label": "Agregar uno", onClick: () => cambiarCantidad(linea.id, 1) }, icono("mas"))),
      el("button", { class: "boton-texto", type: "button", onClick: () => quitar(linea.id) }, icono("basura"), " Quitar")),
  )));
}

export function abrir() {
  pintar();
  document.getElementById("carrito").hidden = false;
  document.getElementById("velo-carrito").hidden = false;
  document.getElementById("cerrar-carrito").focus();
}

export function cerrar() {
  document.getElementById("carrito").hidden = true;
  document.getElementById("velo-carrito").hidden = true;
}

function iniciarCarrito() {
  document.getElementById("abrir-carrito")?.addEventListener("click", abrir);
  document.getElementById("cerrar-carrito")?.addEventListener("click", cerrar);
  document.getElementById("velo-carrito")?.addEventListener("click", cerrar);
  document.addEventListener("keydown", (e) => { if (e.key === "Escape") cerrar(); });
  // Si otra pestaña cambia el carrito, esta se actualiza.
  window.addEventListener("storage", (e) => { if (e.key === CLAVE) pintar(); });
  pintar();
}

iniciarCarrito();
