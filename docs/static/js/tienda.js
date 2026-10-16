/* Página de inicio: menú, armador de granizados y domicilios. */

import { api, dinero, el, icono, numero, toast, vaciar } from "./comun.js";
import { abrir, agregar, reconciliar } from "./carrito.js";
import { cargarMapa, dibujarMapa, resumenRuta } from "./mapa.js";

const estado = { granizados: [], adiciones: [], sabores: [], maxAdiciones: 3, cantidad: 1 };

async function iniciar() {
  const { ok, datos } = await api("GET", "/api/productos");
  if (!ok) {
    toast("No se pudo cargar el menú. Recarga la página.", "error");
    return;
  }
  estado.granizados = datos.productos.filter((p) => p.categoria === "GRANIZADO").sort((a, b) => a.onzas - b.onzas);
  estado.adiciones = datos.productos.filter((p) => p.categoria === "ADICION");
  estado.sabores = datos.sabores;
  estado.maxAdiciones = datos.max_adiciones;

  pintarMenu();
  pintarArmador();
  reconciliar();
  iniciarDomicilios();
}

function badgeOnzas(onzas) {
  return el("span", { class: "onzas", "aria-hidden": "true" }, String(onzas), el("small", { text: "oz" }));
}

const nombreTamano = (p) => p.nombre.replace("Granizado ", "");

function pintarMenu() {
  vaciar(document.getElementById("hero-precios"), ...estado.granizados.map((p) =>
    el("div", { class: "hero__precio" }, badgeOnzas(p.onzas),
      el("div", {}, el("strong", { text: dinero(p.precio) }), el("span", { text: nombreTamano(p) })))));

  vaciar(document.getElementById("menu-tamanos"), ...estado.granizados.map((p) =>
    el("div", { class: "tamano" }, badgeOnzas(p.onzas),
      el("div", {}, el("h3", { text: nombreTamano(p) }), el("p", { text: p.descripcion })),
      el("div", { class: "tamano__precio", text: dinero(p.precio) }))));

  const precios = new Set(estado.adiciones.map((a) => a.precio));
  document.getElementById("precio-adicion").textContent =
    precios.size === 1 ? dinero([...precios][0]) : "desde " + dinero(Math.min(...precios));
  vaciar(document.getElementById("menu-adiciones"), ...estado.adiciones.map((a) => el("li", { text: a.nombre })));
}

function pintarArmador() {
  const porDefecto = estado.granizados[1]?.id ?? estado.granizados[0]?.id;
  vaciar(document.getElementById("opciones-tamano"), ...estado.granizados.map((p) =>
    el("label", { class: "opcion" },
      el("input", { type: "radio", name: "tamano", value: p.id, checked: p.id === porDefecto }),
      el("span", { class: "opcion__cuerpo" }, icono("vaso", "vasito"),
        el("span", { class: "opcion__nombre", text: `${nombreTamano(p)} · ${p.onzas} oz` }),
        el("span", { class: "opcion__precio", text: dinero(p.precio) })))));

  vaciar(document.getElementById("opciones-sabor"), ...estado.sabores.map((sabor, i) =>
    el("label", { class: "opcion" },
      el("input", { type: "radio", name: "sabor", value: sabor, checked: i === 0 }),
      el("span", { class: "opcion__cuerpo" }, el("span", { class: "opcion__nombre", text: sabor })))));

  vaciar(document.getElementById("opciones-adiciones"), ...estado.adiciones.map((a) =>
    el("label", { class: "opcion" },
      el("input", { type: "checkbox", name: "adicion", value: a.id }),
      el("span", { class: "opcion__cuerpo" }, el("span", { text: a.nombre }), el("small", { text: `+${dinero(a.precio)}` })))));

  const formulario = document.getElementById("armador");
  formulario.addEventListener("change", actualizarResumen);
  document.getElementById("cantidad-armado").addEventListener("click", (evento) => {
    const boton = evento.target.closest("button[data-delta]");
    if (!boton) return;
    estado.cantidad = Math.max(1, Math.min(10, estado.cantidad + Number(boton.dataset.delta)));
    actualizarResumen();
  });
  document.getElementById("agregar-carrito").addEventListener("click", agregarAlCarrito);
  actualizarResumen();
}

function seleccion() {
  const formulario = document.getElementById("armador");
  const tamanoId = Number(formulario.querySelector('input[name="tamano"]:checked')?.value);
  const granizado = estado.granizados.find((p) => p.id === tamanoId);
  const sabor = formulario.querySelector('input[name="sabor"]:checked')?.value;
  const marcadas = [...formulario.querySelectorAll('input[name="adicion"]:checked')].map((c) => Number(c.value));
  const adiciones = estado.adiciones.filter((a) => marcadas.includes(a.id));
  return { granizado, sabor, adiciones };
}

function actualizarResumen() {
  const { granizado, sabor, adiciones } = seleccion();
  const casillas = document.querySelectorAll('#opciones-adiciones input[name="adicion"]');
  const lleno = adiciones.length >= estado.maxAdiciones;
  casillas.forEach((c) => { c.disabled = lleno && !c.checked; });
  document.getElementById("contador-adiciones").textContent =
    `${adiciones.length} de ${estado.maxAdiciones} · ${lleno ? "máximo alcanzado" : "opcional"}`;
  document.getElementById("cantidad-valor").textContent = String(estado.cantidad);

  if (!granizado) return;
  const unitario = granizado.precio + adiciones.reduce((s, a) => s + a.precio, 0);
  const lineas = [
    el("li", {}, el("span", { text: `${granizado.nombre} · ${sabor}` }), el("span", { text: dinero(granizado.precio) })),
    ...adiciones.map((a) => el("li", {}, el("span", { text: `+ ${a.nombre}` }), el("span", { text: dinero(a.precio) }))),
    el("li", {}, el("span", { text: "Cantidad" }), el("span", { text: `× ${estado.cantidad}` })),
  ];
  vaciar(document.getElementById("resumen-lineas"), ...lineas);
  document.getElementById("resumen-total").textContent = dinero(unitario * estado.cantidad);
}

function agregarAlCarrito() {
  const { granizado, sabor, adiciones } = seleccion();
  if (!granizado || !sabor) {
    toast("Elige un tamaño y un sabor.", "alerta");
    return;
  }
  agregar({
    producto_id: granizado.id,
    nombre: granizado.nombre,
    sabor,
    adiciones: adiciones.map((a) => ({ id: a.id, nombre: a.nombre, precio: a.precio })),
    cantidad: estado.cantidad,
    precio_unitario: granizado.precio + adiciones.reduce((s, a) => s + a.precio, 0),
  });
  toast(`${granizado.nombre} agregado al carrito.`, "ok");
  estado.cantidad = 1;
  document.querySelectorAll('#opciones-adiciones input:checked').forEach((c) => { c.checked = false; });
  actualizarResumen();
  abrir();
}

async function iniciarDomicilios() {
  const datos = await cargarMapa();
  if (!datos) return;
  const selector = document.getElementById("barrio-consulta");
  const resultado = document.getElementById("ruta-resultado");
  const ordenados = [...datos.nodos].sort((a, b) => a.distancia_km - b.distancia_km);

  const resaltar = dibujarMapa(document.getElementById("mapa-domicilios"), datos, (barrio) => {
    selector.value = barrio;
    consultar(barrio);
  });

  vaciar(selector, el("option", { value: "", text: "Elige tu barrio" }),
    ...ordenados.filter((n) => n.nombre !== datos.tienda).map((n) => el("option", { value: n.nombre, text: n.nombre })));
  vaciar(document.getElementById("lista-tarifas"), ...ordenados.map((n) =>
    el("li", {}, el("span", { text: `${n.nombre} · ${numero(n.distancia_km, 1)} km` }), el("span", { text: dinero(n.tarifa) }))));

  async function consultar(barrio) {
    if (!barrio) return;
    const { ok, datos: respuesta } = await api("GET", `/api/domicilios/cotizar?barrio=${encodeURIComponent(barrio)}`);
    if (!ok) return;
    resaltar(respuesta.domicilio.ruta);
    vaciar(resultado, resumenRuta(respuesta.domicilio));
  }
  selector.addEventListener("change", () => consultar(selector.value));
  selector.value = "El Poblado";
  consultar("El Poblado");
}

iniciar();
