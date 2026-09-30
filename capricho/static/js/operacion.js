/* Panel de operación: cola FIFO, pila LIFO, grafo, índice hash y CRUD. */

import { api, dinero, el, fechaCorta, icono, insignia, mostrarErrores, nivel, numero, toast, vaciar } from "./comun.js";
import { cargarMapa, dibujarMapa, resumenRuta } from "./mapa.js";

// --- Pestañas -------------------------------------------------------------------
const pestanas = [...document.querySelectorAll("[data-pestana]")];
function mostrarPestana(nombre) {
  for (const boton of pestanas) {
    const activa = boton.dataset.pestana === nombre;
    boton.setAttribute("aria-selected", String(activa));
    document.getElementById(`panel-${boton.dataset.pestana}`).hidden = !activa;
  }
  history.replaceState(null, "", `#${nombre}`);
  ({ cola: cargarCola, pila: cargarPila, grafo: cargarGrafo, productos: cargarProductos })[nombre]?.();
}
pestanas.forEach((b) => b.addEventListener("click", () => mostrarPestana(b.dataset.pestana)));

const resumenItems = (items) => items.map((i) => `${i.cantidad}× ${i.nombre.replace("Granizado ", "")} ${i.sabor}` +
  (i.adiciones.length ? ` + ${i.adiciones.map((a) => a.nombre).join(", ")}` : "")).join(" · ");

// --- Cola ---------------------------------------------------------------------------
async function cargarCola() {
  const { ok, datos } = await api("GET", "/api/pedidos/cola");
  if (!ok) return toast(datos.error, "error");
  vaciar(document.getElementById("fila-cola"), ...(datos.cola.length ? datos.cola.map((p, i) => el("article", { class: "ficha-pedido" },
    el("h4", { text: `#${p.id} · ${p.cliente}` }),
    el("p", { text: `Posición ${i + 1} · ${fechaCorta(p.fecha_creacion)}` }),
    el("p", { text: resumenItems(p.items) }),
    el("p", {}, el("strong", { text: dinero(p.total) }), ` · ${p.tipo_entrega === "DOMICILIO" ? p.barrio : "Recoge"}`),
    p.estado_pago === "SOSPECHOSA" ? insignia("SOSPECHOSA") : null))
    : [el("p", { class: "muted", text: "La cola está vacía. Haz un pedido desde la tienda." })]));
  document.getElementById("atender").disabled = !datos.cola.length;

  vaciar(document.getElementById("en-proceso"), ...(datos.en_proceso.length ? datos.en_proceso.map((p) => el("tr", {},
    el("td", { class: "num", text: p.id }),
    el("td", { text: p.cliente }),
    el("td", { text: resumenItems(p.items) }),
    el("td", { text: p.tipo_entrega === "DOMICILIO" ? `${p.ruta.join(" → ")} (${numero(p.distancia_km, 1)} km)` : "Recoge en tienda" }),
    el("td", { class: "num", text: dinero(p.total) }),
    el("td", {}, el("button", { class: "boton boton--xs", type: "button", onClick: () => entregar(p.id) }, icono("ok"), " Entregado"))))
    : [el("tr", {}, el("td", { colspan: "6", class: "muted", text: "Nada en preparación." }))]));
}

document.getElementById("atender").addEventListener("click", async () => {
  const { ok, datos } = await api("POST", "/api/pedidos/cola/atender");
  if (!ok) return toast(datos.error, "error");
  toast(datos.pedido ? `Desencolado el pedido #${datos.pedido.id}. Quedan ${datos.restantes}.` : "La cola está vacía.", "ok");
  cargarCola();
});

async function entregar(id) {
  const { ok, datos } = await api("PATCH", `/api/pedidos/${id}`, { estado: "ENTREGADO" });
  if (!ok) return toast(datos.error, "error");
  toast(`Pedido #${id} entregado.`, "ok");
  cargarCola();
}

// --- Pila -----------------------------------------------------------------------------
async function cargarPila() {
  const { ok, datos } = await api("GET", "/api/eventos");
  if (!ok) return toast(datos.error, "error");
  vaciar(document.getElementById("pila-completa"), ...(datos.eventos.length ? datos.eventos.map((e, i) => el("div", { class: "pila-item" },
    nivel(e.nivel),
    el("div", { class: "pila-item__detalle" },
      el("strong", { text: `${i === 0 ? "CIMA · " : ""}${e.tipo} · ${e.metodo || ""} ${e.ruta || ""}` }),
      el("p", { text: e.detalle }),
      el("p", { class: "muted", text: `IP ${e.ip || "—"}${e.email ? " · " + e.email : ""}` })),
    el("time", { text: fechaCorta(e.fecha) })))
    : [el("p", { class: "muted", text: "La pila está vacía." })]),
  datos.total > datos.eventos.length ? el("p", { class: "muted", text: `…y ${datos.total - datos.eventos.length} más abajo.` }) : null);
  document.getElementById("desapilar").disabled = !datos.total;
}

document.getElementById("desapilar").addEventListener("click", async () => {
  const { ok, datos } = await api("POST", "/api/eventos/desapilar");
  if (!ok) return toast(datos.error, "error");
  if (datos.evento) toast(`Atendido: ${datos.evento.tipo}. Quedan ${datos.restantes}.`, "ok");
  cargarPila();
});

// --- Grafo ------------------------------------------------------------------------------
let grafoListo = false;
async function cargarGrafo() {
  if (grafoListo) return;
  const datos = await cargarMapa();
  if (!datos) return;
  grafoListo = true;
  const resaltar = dibujarMapa(document.getElementById("mapa-operacion"), datos, async (barrio) => {
    const { ok, datos: r } = await api("GET", `/api/domicilios/cotizar?barrio=${encodeURIComponent(barrio)}`);
    if (!ok) return;
    resaltar(r.domicilio.ruta);
    vaciar(document.getElementById("ruta-operacion"), resumenRuta(r.domicilio));
  });
}

// --- Índice -------------------------------------------------------------------------------
document.getElementById("form-indice").addEventListener("submit", async (evento) => {
  evento.preventDefault();
  const clave = document.getElementById("clave-indice").value.trim();
  const caja = document.getElementById("resultado-indice");
  if (!clave) return;
  const { ok, datos, ms } = await api("GET", `/api/transacciones/${encodeURIComponent(clave)}`);
  if (!ok) {
    vaciar(caja, el("div", { class: "aviso aviso--error separado" }, icono("bloqueo"), el("p", { text: datos.error })));
    return;
  }
  const t = datos.transaccion;
  vaciar(caja,
    el("div", { class: "comparacion" },
      el("div", {}, el("span", { class: "muted", text: "Con el índice hash" }), el("strong", { text: `${datos.busqueda.operaciones} operación` }),
        el("span", { class: "muted", text: `entre ${numero(datos.busqueda.registros_indexados)} registros · ${ms} ms ida y vuelta` })),
      el("div", {}, el("span", { class: "muted", text: "Una búsqueda lineal habría revisado" }),
        el("strong", { text: `${numero(datos.busqueda.busqueda_lineal_habria_revisado)} registros` }),
        el("span", { class: "muted", text: "uno por uno, desde el primero" }))),
    el("dl", { class: "detalle-datos separado" },
      el("dt", { text: "idTxn" }), el("dd", { class: "mono", text: t.id_txn }),
      el("dt", { text: "Usuario" }), el("dd", { text: `${t.nombre} · ${t.email}` }),
      el("dt", { text: "Valor" }), el("dd", { text: dinero(t.valor) }),
      el("dt", { text: "Fecha" }), el("dd", { text: fechaCorta(t.fecha_txn, true) }),
      el("dt", { text: "Resultado" }), el("dd", {}, insignia(t.estado)),
      el("dt", { text: "Hash" }), el("dd", { class: "mono", text: `${t.hash.slice(0, 32)}… (${t.hash_valido ? "válido" : "inválido"})` }),
      el("dt", { text: "Anomalías" }), el("dd", { text: datos.anomalias.length ? datos.anomalias.map((a) => `${a.tipo} (${a.nivel})`).join(", ") : "Ninguna" })));
});

// --- Productos: GET, POST, PUT, PATCH, DELETE ----------------------------------------------------
const formProducto = document.getElementById("form-producto");
let productoActual = null;

async function cargarProductos() {
  const { ok, datos } = await api("GET", "/api/productos?todos=1");
  if (!ok) return toast(datos.error, "error");
  vaciar(document.getElementById("t-productos"), ...datos.productos.map((p) => el("tr", {},
    el("td", { class: "num", text: p.id }),
    el("td", { text: p.nombre }),
    el("td", { text: p.categoria }),
    el("td", { class: "num", text: dinero(p.precio) }),
    el("td", {}, insignia(p.activo ? "ACTIVO" : "INACTIVO")),
    el("td", {}, el("button", { class: "boton boton--xs boton--contorno", type: "button", onClick: () => editar(p) }, "Editar")))));
}

function leerProducto() {
  const onzas = formProducto.onzas.value;
  return {
    nombre: formProducto.nombre.value,
    descripcion: formProducto.descripcion.value,
    categoria: formProducto.categoria.value,
    precio: formProducto.precio.value === "" ? null : Number(formProducto.precio.value),
    onzas: onzas === "" ? null : Number(onzas),
    imagen: formProducto.imagen.value || null,
    activo: formProducto.activo.checked,
  };
}

function editar(producto) {
  productoActual = producto;
  document.getElementById("titulo-producto").textContent = `Editar #${producto.id} (PUT / PATCH / DELETE)`;
  formProducto.nombre.value = producto.nombre;
  formProducto.descripcion.value = producto.descripcion;
  formProducto.categoria.value = producto.categoria;
  formProducto.precio.value = producto.precio;
  formProducto.onzas.value = producto.onzas ?? "";
  formProducto.imagen.value = producto.imagen ?? "";
  formProducto.activo.checked = producto.activo;
  document.getElementById("guardar-producto").textContent = "PUT · reemplazar todo";
  ["patch-producto", "borrar-producto", "cancelar-producto"].forEach((id) => { document.getElementById(id).hidden = false; });
  limpiarErrores();
}

function nuevo() {
  productoActual = null;
  formProducto.reset();
  document.getElementById("titulo-producto").textContent = "Nuevo producto (POST)";
  document.getElementById("guardar-producto").textContent = "POST · Crear";
  ["patch-producto", "borrar-producto", "cancelar-producto"].forEach((id) => { document.getElementById(id).hidden = true; });
  limpiarErrores();
}

function limpiarErrores() {
  formProducto.querySelectorAll(".campo").forEach((c) => c.classList.remove("invalido"));
}

async function enviarProducto(metodo, url, cuerpo) {
  limpiarErrores();
  const respuesta = await api(metodo, url, cuerpo);
  const log = document.getElementById("log-producto");
  log.hidden = false;
  log.textContent = `${metodo} ${url}\n${cuerpo ? JSON.stringify(cuerpo, null, 2) + "\n" : ""}→ ${respuesta.status}\n${JSON.stringify(respuesta.datos, null, 2)}`;
  if (!respuesta.ok) {
    mostrarErrores(formProducto, respuesta.datos.errores);
    toast(respuesta.datos.error, "error");
    return null;
  }
  cargarProductos();
  return respuesta.datos;
}

formProducto.addEventListener("submit", async (evento) => {
  evento.preventDefault();
  const datos = leerProducto();
  const resultado = productoActual
    ? await enviarProducto("PUT", `/api/productos/${productoActual.id}`, datos)
    : await enviarProducto("POST", "/api/productos", datos);
  if (resultado) {
    toast(productoActual ? "Producto reemplazado (PUT)." : "Producto creado (POST).", "ok");
    editar(resultado.producto);
  }
});

document.getElementById("patch-producto").addEventListener("click", async () => {
  const nuevos = leerProducto();
  const cambios = Object.fromEntries(Object.entries(nuevos).filter(([clave, valor]) => valor !== productoActual[clave]));
  if (!Object.keys(cambios).length) return toast("No cambiaste nada.", "info");
  const resultado = await enviarProducto("PATCH", `/api/productos/${productoActual.id}`, cambios);
  if (resultado) {
    toast(`PATCH: se cambió ${Object.keys(cambios).join(", ")}.`, "ok");
    editar(resultado.producto);
  }
});

document.getElementById("borrar-producto").addEventListener("click", async () => {
  if (!window.confirm(`¿Eliminar "${productoActual.nombre}"? Esta acción no se puede deshacer.`)) return;
  const resultado = await enviarProducto("DELETE", `/api/productos/${productoActual.id}`);
  if (resultado) {
    toast("Producto eliminado (DELETE).", "ok");
    nuevo();
  }
});

document.getElementById("nuevo-producto").addEventListener("click", nuevo);
document.getElementById("cancelar-producto").addEventListener("click", nuevo);

function desdeUrl() {
  const pedida = window.location.hash.slice(1);
  mostrarPestana(pestanas.some((b) => b.dataset.pestana === pedida) ? pedida : "cola");
}
window.addEventListener("hashchange", desdeUrl);
desdeUrl();
