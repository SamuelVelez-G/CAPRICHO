/*
 * Gestión: caja, facturas, pedidos, ítems con inventario, categorías y usuarios.
 * Todo pasa por la API (los mismos endpoints que usaría otra aplicación);
 * el servidor valida y calcula, aquí solo se muestra.
 */

import { api, csrf, dinero, el, fechaCorta, icono, insignia, modal, mostrarErrores, numero, toast, vaciar } from "./comun.js";
import { etiqueta, paginacion, pestanas, tablaDatos } from "./ui.js";

const ES_ADMIN = document.querySelector("[data-rol-gestion]").dataset.rolGestion === "ADMIN";
const CANAL = { PRESENCIAL: "Caja", WEB: "Web", APP: "App", DOMICILIO: "Domicilio" };
const CON_COMPROBANTE = ["Nequi", "Daviplata", "PSE", "Transferencia"];
let productos = [];
let categorias = [];

async function cargarCatalogo() {
  const [p, c] = await Promise.all([api("GET", "/api/productos?todos=1"), api("GET", `/api/categorias${ES_ADMIN ? "?todas=1" : ""}`)]);
  if (p.ok) productos = p.datos.productos;
  if (c.ok) categorias = c.datos.categorias;
}

// --- Formularios en ventana ----------------------------------------------------------
function campo(c, valor) {
  const id = `m-${c.nombre}`;
  const error = el("span", { class: "campo__error" }, icono("alerta"), el("span"));
  if (c.tipo === "checkbox") {
    return el("div", { class: "campo", dataset: { campo: c.nombre } },
      el("label", { class: "casilla" }, el("input", { type: "checkbox", name: c.nombre, checked: Boolean(valor) }), c.etiqueta), error);
  }
  const control = c.tipo === "select"
    ? el("select", { id, name: c.nombre }, ...c.opciones.map(([v, t]) => el("option", { value: v, text: t, selected: String(v) === String(valor ?? "") })))
    : el("input", { id, name: c.nombre, type: c.tipo || "text", value: valor ?? "", autocomplete: "off", min: c.min, max: c.max, step: c.paso });
  return el("div", { class: "campo", dataset: { campo: c.nombre } }, el("label", { for: id, text: c.etiqueta }), control,
    c.ayuda ? el("span", { class: "ayuda", text: c.ayuda }) : null, error);
}

function leer(form, campos) {
  const datos = {};
  for (const c of campos) {
    const control = form.elements[c.nombre];
    if (c.tipo === "checkbox") datos[c.nombre] = control.checked;
    else if (c.tipo === "number" || c.numero) datos[c.nombre] = control.value === "" ? null : Number(control.value);
    else datos[c.nombre] = control.value.trim() === "" && c.nulo ? null : control.value.trim();
  }
  return datos;
}

function formularioModal(titulo, campos, valores, enviar, textoBoton = "Guardar") {
  const form = el("form", { class: "formulario formulario--ancho", novalidate: true },
    ...campos.map((c) => campo(c, valores?.[c.nombre])),
    el("button", { class: "boton boton--bloque", type: "submit" }, icono("ok"), textoBoton));
  const { cerrar } = modal(titulo, form);
  form.addEventListener("submit", async (evento) => {
    evento.preventDefault();
    form.querySelectorAll(".campo").forEach((c) => c.classList.remove("invalido"));
    const respuesta = await enviar(leer(form, campos));
    if (respuesta.ok) { cerrar(); toast("Guardado", "ok"); return; }
    if (!mostrarErrores(form, respuesta.datos.errores)) toast(respuesta.datos.error || "No se pudo guardar", "error");
  });
}

async function confirmarBorrado(texto, url, alTerminar) {
  formularioModal(texto, [], {}, async () => {
    const r = await api("DELETE", url);
    if (r.ok) {
      toast(r.datos.desactivado ? `Tenía ${r.datos.registros} registros: se desactivó en vez de borrarse` : "Eliminado", "ok");
      alTerminar();
    }
    return r;
  }, "Sí, eliminar");
}

// --- Caja ------------------------------------------------------------------------------
const formCaja = document.getElementById("form-caja");
const lineas = [];
let tarifa = 0;

function prepararCaja(barrios) {
  const vendibles = productos.filter((p) => p.activo && p.tipo !== "ADICION");
  vaciar(document.getElementById("c-producto"), ...vendibles.map((p) => el("option", { value: p.id, text: `${p.nombre} · ${dinero(p.precio)} · stock ${p.stock}` })));
  vaciar(document.getElementById("c-adiciones"), ...productos.filter((p) => p.activo && p.tipo === "ADICION")
    .map((p) => el("option", { value: p.id, text: `${p.nombre} (+${dinero(p.precio)})` })));
  vaciar(formCaja.barrio, ...barrios.map((b) => el("option", { value: b, text: b })));
  const alCambiarProducto = () => {
    const p = productos.find((x) => x.id === Number(document.getElementById("c-producto").value));
    document.getElementById("caja-adiciones").hidden = !p || p.tipo !== "GRANIZADO";
  };
  document.getElementById("c-producto").addEventListener("change", alCambiarProducto);
  alCambiarProducto();
}

function pintarLineas() {
  const subtotal = lineas.reduce((s, l) => s + l.precio * l.cantidad, 0);
  const porcentaje = Number(formCaja.descuento_porcentaje.value) || 0;
  const descuento = Math.round((subtotal * porcentaje) / 100 / 100) * 100;
  document.getElementById("caja-total").textContent = dinero(subtotal - descuento + (formCaja.tipo_entrega.value === "DOMICILIO" ? tarifa : 0));
  vaciar(document.getElementById("lineas-caja"), lineas.length ? tablaDatos([
    { titulo: "Ítem", valor: (l) => l.nombre + (l.adiciones.length ? ` + ${l.nombresAdiciones.join(", ")}` : "") },
    { titulo: "Cant.", valor: (l) => String(l.cantidad), num: true },
    { titulo: "Subtotal", valor: (l) => dinero(l.precio * l.cantidad), num: true },
    { titulo: "", valor: (l) => el("button", { class: "boton-tabla", type: "button", "aria-label": "Quitar",
      onClick: () => { lineas.splice(lineas.indexOf(l), 1); pintarLineas(); } }, icono("basura")) },
  ], lineas) : el("p", { class: "muted", text: "Agrega al menos un ítem." }));
}

document.getElementById("agregar-linea").addEventListener("click", () => {
  const p = productos.find((x) => x.id === Number(document.getElementById("c-producto").value));
  if (!p) return;
  const adiciones = p.tipo === "GRANIZADO" ? [...document.getElementById("c-adiciones").selectedOptions].map((o) => Number(o.value)) : [];
  if (adiciones.length > 3) return toast("Máximo 3 adiciones por granizado", "alerta");
  const extras = adiciones.map((id) => productos.find((x) => x.id === id));
  lineas.push({ producto_id: p.id, nombre: p.nombre, cantidad: Math.max(1, Number(document.getElementById("c-cantidad").value) || 1),
    adiciones, nombresAdiciones: extras.map((a) => a.nombre), precio: p.precio + extras.reduce((s, a) => s + a.precio, 0) });
  pintarLineas();
});
formCaja.descuento_porcentaje.addEventListener("input", pintarLineas);
formCaja.tipo_entrega.addEventListener("change", () => {
  const domicilio = formCaja.tipo_entrega.value === "DOMICILIO";
  formCaja.querySelector('[data-campo="barrio"]').hidden = !domicilio;
  formCaja.querySelector('[data-campo="direccion"]').hidden = !domicilio;
  if (domicilio) formCaja.barrio.dispatchEvent(new Event("change"));
  pintarLineas();
});
formCaja.barrio.addEventListener("change", async () => {
  const r = await api("GET", `/api/domicilios/cotizar?barrio=${encodeURIComponent(formCaja.barrio.value)}`);
  tarifa = r.ok ? r.datos.domicilio.tarifa : 0;
  pintarLineas();
});

formCaja.addEventListener("submit", async (evento) => {
  evento.preventDefault();
  formCaja.querySelectorAll("[data-campo]").forEach((c) => c.classList.remove("invalido"));
  const domicilio = formCaja.tipo_entrega.value === "DOMICILIO";
  const r = await api("POST", "/api/caja/pedidos", {
    cliente_email: formCaja.cliente_email.value.trim() || null, canal: formCaja.canal.value, tipo_entrega: formCaja.tipo_entrega.value,
    barrio: domicilio ? formCaja.barrio.value : null, direccion: domicilio ? formCaja.direccion.value.trim() : null,
    items: lineas.map((l) => ({ producto_id: l.producto_id, cantidad: l.cantidad, adiciones: l.adiciones })),
    descuento_porcentaje: Number(formCaja.descuento_porcentaje.value) || 0,
    motivo_descuento: formCaja.motivo_descuento.value.trim() || null, metodo_pago: formCaja.metodo_pago.value,
  });
  if (!r.ok) {
    if (!mostrarErrores(formCaja, r.datos.errores)) toast(r.datos.error || "No se pudo crear el pedido", "error");
    return;
  }
  toast(`Pedido #${r.datos.pedido.id} y factura ${r.datos.factura.codigo} creados`, "ok");
  lineas.length = 0;
  pintarLineas();
  vaciar(document.getElementById("caja-factura"), vistaFactura(r.datos.factura, formCaja.metodo_pago.value));
  await cargarCatalogo();
  prepararCaja([...formCaja.barrio.options].map((o) => o.value));
});

// --- Factura (vista y pago) -------------------------------------------------------------
function vistaFactura(f, metodoSugerido) {
  const contenedor = el("div", { class: "factura" });
  const pintar = (factura) => vaciar(contenedor,
    el("div", { class: "factura__cabeza" }, el("h3", { text: factura.codigo }), insignia(factura.estado),
      etiqueta(CANAL[factura.canal] || factura.canal, "vino")),
    el("p", { class: "muted", text: `${fechaCorta(factura.fecha_emision)} · ${factura.cliente} · ${factura.empleado ? `atendió ${factura.empleado}` : "compra en línea"}` }),
    tablaDatos([
      { titulo: "Ítem", valor: (i) => i.nombre + (JSON.parse(i.adiciones || "[]").length ? " + adiciones" : "") },
      { titulo: "Cant.", valor: (i) => String(i.cantidad), num: true },
      { titulo: "Unitario", valor: (i) => dinero(i.precio_unitario), num: true },
      { titulo: "Subtotal", valor: (i) => dinero(i.subtotal), num: true },
    ], factura.items),
    el("ul", { class: "lineas-precio" },
      el("li", {}, el("span", { text: "Subtotal" }), el("span", { text: dinero(factura.subtotal) })),
      factura.descuento ? el("li", {}, el("span", { text: `Descuento (${factura.motivo_descuento})` }), el("span", { text: `−${dinero(factura.descuento)}` })) : null,
      el("li", {}, el("span", { text: "Base gravable" }), el("span", { text: dinero(factura.base) })),
      el("li", {}, el("span", { text: `Impuesto al consumo ${numero(factura.tasa_impuesto * 100, 0)} % (incluido)` }), el("span", { text: dinero(factura.impuesto) })),
      factura.domicilio ? el("li", {}, el("span", { text: "Domicilio" }), el("span", { text: dinero(factura.domicilio) })) : null,
      el("li", { class: "total-grande" }, el("span", { text: "Total" }), el("strong", { text: dinero(factura.total) })),
      el("li", {}, el("span", { text: "Pagado / saldo" }), el("span", { text: `${dinero(factura.pagado)} / ${dinero(factura.saldo)}` }))),
    el("p", { class: "hash-linea" }, icono("candado"), el("span", { text: `Hash ${factura.hash.slice(0, 20)}… · anterior ${factura.hash_anterior.slice(0, 12)}…` })),
    factura.motivo_anulacion ? el("p", { class: "aviso aviso--error" }, icono("bloqueo"), el("span", { text: `Anulada por ${factura.anulador}: ${factura.motivo_anulacion}` })) : null,
    factura.pagos.length ? el("div", {}, el("h4", { text: "Pagos" }), tablaDatos([
      { titulo: "#", valor: (p) => String(p.id) },
      { titulo: "Método", valor: (p) => p.metodo },
      { titulo: "Monto", valor: (p) => dinero(p.monto), num: true },
      { titulo: "Comprobante", valor: (p) => el("span", {}, insignia(p.verificacion), p.comprobante_sha256
        ? el("a", { href: `/api/pagos/${p.id}/comprobante`, class: "boton-texto", text: " descargar" }) : null) },
      { titulo: "Estado", valor: (p) => insignia(p.estado) },
      { titulo: "IA", valor: (p) => (p.prob_fraude === null || p.prob_fraude === undefined ? "—" : `${numero(p.prob_fraude * 100, 0)} %`) },
    ], factura.pagos), ...factura.pagos.filter((p) => p.verificacion !== "NO_REQUIERE" && p.detalle_verificacion)
      .map((p) => el("p", { class: "nota", text: `Pago #${p.id}: ${p.detalle_verificacion}` }))) : null,
    factura.saldo > 0 && factura.estado !== "ANULADA" ? formularioPago(factura, metodoSugerido, pintar) : null,
    factura.estado !== "ANULADA" ? el("button", { class: "boton boton--sm boton--peligro", type: "button",
      onClick: () => formularioModal(`Anular ${factura.codigo}`, [{ nombre: "motivo", etiqueta: "Motivo de la anulación", ayuda: "Queda registrado con tu nombre; el inventario se devuelve." }], {},
        async (datos) => { const r = await api("POST", `/api/facturas/${factura.id}/anular`, datos); if (r.ok) pintar(r.datos.factura); return r; }, "Anular") },
    icono("bloqueo"), "Anular factura") : null);
  pintar(f);
  return contenedor;
}

function formularioPago(factura, metodoSugerido, alPagar) {
  const form = el("form", { class: "formulario formulario--ancho pago-caja", novalidate: true },
    el("h4", { text: "Registrar pago" }),
    el("div", { class: "fila-campos" },
      campo({ nombre: "metodo", etiqueta: "Método", tipo: "select", opciones: ["Efectivo", "Tarjeta", "Nequi", "Daviplata", "PSE", "Transferencia"].map((m) => [m, m]) }, metodoSugerido || "Efectivo"),
      campo({ nombre: "monto", etiqueta: "Monto", tipo: "number", min: 100 }, factura.saldo),
      campo({ nombre: "referencia", etiqueta: "Referencia (opcional)" }, "")),
    el("div", { class: "campo", dataset: { campo: "comprobante" } }, el("label", { for: "pago-comprobante", text: "Comprobante (PDF, PNG o JPG)" }),
      el("input", { id: "pago-comprobante", name: "comprobante", type: "file", accept: ".pdf,.png,.jpg,.jpeg,application/pdf,image/png,image/jpeg" }),
      el("span", { class: "ayuda", text: "Nequi, Daviplata, PSE y transferencia lo exigen. Para probar, descarga uno de la pasarela simulada:" }),
      el("span", { class: "campo__error" }, icono("alerta"), el("span"))),
    el("div", { class: "enlaces-prueba" }),
    el("button", { class: "boton boton--bloque", type: "submit" }, icono("ok"), "Registrar pago"));
  const enlaces = () => {
    const metodo = form.metodo.value;
    const base = `/api/comprobantes/prueba?metodo=${encodeURIComponent(metodo)}&monto=${form.monto.value}&pagador=${encodeURIComponent(factura.cliente)}`;
    vaciar(form.querySelector(".enlaces-prueba"), CON_COMPROBANTE.includes(metodo) ? [
      el("a", { class: "boton boton--xs boton--contorno", href: base, text: "Comprobante válido" }),
      el("a", { class: "boton boton--xs boton--contorno", href: `${base}&alterar=1`, text: "Comprobante falsificado" }),
    ] : el("span", { class: "muted", text: `${metodo}: no necesita comprobante.` }));
  };
  form.metodo.addEventListener("change", enlaces);
  form.monto.addEventListener("change", enlaces);
  enlaces();
  form.addEventListener("submit", async (evento) => {
    evento.preventDefault();
    form.querySelectorAll(".campo").forEach((c) => c.classList.remove("invalido"));
    const cuerpo = new FormData(form);
    if (!form.comprobante.files.length) cuerpo.delete("comprobante");
    const respuesta = await fetch(`/api/facturas/${factura.id}/pagos`, { method: "POST", body: cuerpo, credentials: "same-origin",
      headers: { "X-CSRF-Token": csrf(), Accept: "application/json" } });
    const datos = await respuesta.json().catch(() => ({ error: "Respuesta inválida" }));
    if (!respuesta.ok) {
      if (!mostrarErrores(form, datos.errores)) toast(datos.error || "No se pudo registrar el pago", "error");
      return;
    }
    const pago = datos.pago;
    toast(`Pago ${pago.estado.toLowerCase()} · comprobante ${pago.verificacion.toLowerCase().replaceAll("_", " ")}`,
      pago.estado === "APROBADO" ? "ok" : pago.estado === "PENDIENTE" ? "alerta" : "error", 6000);
    alPagar(pago.factura);
  });
  return form;
}

// --- Facturas y pedidos ---------------------------------------------------------------------
let paginaFacturas = 1;
async function cargarFacturas(pagina = paginaFacturas) {
  paginaFacturas = pagina;
  const filtros = new URLSearchParams({ pagina, estado: document.getElementById("f-estado").value,
    canal: document.getElementById("f-canal").value, q: document.getElementById("f-buscar").value.trim() });
  const { ok, datos } = await api("GET", `/api/facturas?${filtros}`);
  if (!ok) return toast(datos.error, "error");
  vaciar(document.getElementById("t-facturas"), tablaDatos([
    { titulo: "Factura", valor: (f) => el("button", { class: "boton-texto", type: "button", text: f.codigo, onClick: () => abrirFactura(f.id) }) },
    { titulo: "Fecha", valor: (f) => fechaCorta(f.fecha_emision) },
    { titulo: "Cliente", valor: (f) => f.cliente },
    { titulo: "Canal", valor: (f) => CANAL[f.canal] || f.canal },
    { titulo: "Atendió", valor: (f) => f.empleado || "En línea" },
    { titulo: "Descuento", valor: (f) => (f.descuento ? dinero(f.descuento) : "—"), num: true },
    { titulo: "Total", valor: (f) => dinero(f.total), num: true },
    { titulo: "Estado", valor: (f) => insignia(f.estado) },
  ], datos.facturas, "No hay facturas con esos filtros."));
  paginacion(document.getElementById("p-facturas"), datos.pagina, datos.paginas, cargarFacturas);
}
async function abrirFactura(id) {
  const { ok, datos } = await api("GET", `/api/facturas/${id}`);
  if (!ok) return toast(datos.error, "error");
  modal(`Factura ${datos.factura.codigo}`, vistaFactura(datos.factura, datos.factura.pagos.at(-1)?.metodo), { ancho: "modal__caja--ancha" });
}
["f-estado", "f-canal"].forEach((id) => document.getElementById(id).addEventListener("change", () => cargarFacturas(1)));
let espera;
document.getElementById("f-buscar").addEventListener("input", () => { clearTimeout(espera); espera = setTimeout(() => cargarFacturas(1), 350); });

let paginaPedidos = 1;
async function cargarPedidos(pagina = paginaPedidos) {
  paginaPedidos = pagina;
  const filtros = new URLSearchParams({ pagina, canal: document.getElementById("pd-canal").value, estado: document.getElementById("pd-estado").value });
  const { ok, datos } = await api("GET", `/api/caja/pedidos?${filtros}`);
  if (!ok) return toast(datos.error, "error");
  vaciar(document.getElementById("t-pedidos"), tablaDatos([
    { titulo: "#", valor: (p) => String(p.id) },
    { titulo: "Fecha", valor: (p) => fechaCorta(p.fecha_creacion) },
    { titulo: "Cliente", valor: (p) => p.cliente },
    { titulo: "Canal", valor: (p) => CANAL[p.canal] || p.canal },
    { titulo: "Ítems", valor: (p) => p.items.map((i) => `${i.cantidad}× ${i.nombre}`).join(", ") },
    { titulo: "Total", valor: (p) => dinero(p.total), num: true },
    { titulo: "Factura", valor: (p) => (p.factura ? el("button", { class: "boton-texto", type: "button", text: p.factura, onClick: () => abrirFactura(p.factura_id) }) : "—") },
    { titulo: "Estado", valor: (p) => insignia(p.estado) },
  ], datos.pedidos));
  paginacion(document.getElementById("p-pedidos"), datos.pagina, datos.paginas, cargarPedidos);
}
["pd-canal", "pd-estado"].forEach((id) => document.getElementById(id).addEventListener("change", () => cargarPedidos(1)));

// --- Ítems y categorías ------------------------------------------------------------------------
const camposItem = () => [
  { nombre: "nombre", etiqueta: "Nombre" }, { nombre: "descripcion", etiqueta: "Descripción" },
  { nombre: "categoria_id", etiqueta: "Categoría", tipo: "select", numero: true, opciones: categorias.map((c) => [c.id, c.nombre]) },
  { nombre: "tipo", etiqueta: "Cómo se vende", tipo: "select", opciones: [["GRANIZADO", "Granizado (lleva adiciones)"], ["ADICION", "Adición"], ["OTRO", "Se vende solo"]] },
  { nombre: "precio", etiqueta: "Precio ($)", tipo: "number", min: 500, paso: 100 },
  { nombre: "onzas", etiqueta: "Onzas (solo granizados)", tipo: "number", min: 4, max: 40 },
  { nombre: "stock", etiqueta: "Inventario", tipo: "number", min: 0 }, { nombre: "stock_minimo", etiqueta: "Inventario mínimo", tipo: "number", min: 0 },
  { nombre: "imagen", etiqueta: "Imagen", tipo: "select", nulo: true, opciones: [["", "Sin imagen"], ["menu.jpg", "menu.jpg"], ["capuchino.jpg", "capuchino.jpg"], ["cargador.jpg", "cargador.jpg"]] },
  { nombre: "activo", etiqueta: "Activo (se puede vender)", tipo: "checkbox" },
];
async function cargarItems() {
  await cargarCatalogo();
  vaciar(document.getElementById("t-items"), tablaDatos([
    { titulo: "Ítem", valor: (p) => p.nombre },
    { titulo: "Categoría", valor: (p) => p.categoria },
    { titulo: "Tipo", valor: (p) => p.tipo.toLowerCase() },
    { titulo: "Precio", valor: (p) => dinero(p.precio), num: true },
    { titulo: "Stock", valor: (p) => el("span", {}, numero(p.stock), p.stock_bajo ? el("span", {}, " ", etiqueta("bajo", "critico")) : null), num: true },
    { titulo: "Estado", valor: (p) => insignia(p.activo ? "ACTIVO" : "INACTIVO") },
    { titulo: "", valor: (p) => el("span", { class: "acciones-tabla" },
      el("button", { class: "boton-tabla", type: "button", title: "Movimientos de inventario", "aria-label": "Movimientos", onClick: () => movimientos(p.id) }, icono("reloj")),
      ES_ADMIN ? el("button", { class: "boton-tabla", type: "button", "aria-label": "Editar", onClick: () => editarItem(p) }, icono("actualizar")) : null,
      ES_ADMIN ? el("button", { class: "boton-tabla", type: "button", "aria-label": "Eliminar", onClick: () => confirmarBorrado(`¿Eliminar «${p.nombre}»?`, `/api/productos/${p.id}`, cargarItems) }, icono("basura")) : null) },
  ], productos));
}
function editarItem(p) {
  formularioModal(p ? `Editar ${p.nombre}` : "Nuevo ítem", camposItem(), p || { activo: true, stock: 0, stock_minimo: 10, tipo: "OTRO" }, async (datos) => {
    datos.imagen = datos.imagen || null;
    const r = await api(p ? "PUT" : "POST", p ? `/api/productos/${p.id}` : "/api/productos", datos);
    if (r.ok) cargarItems();
    return r;
  });
}
async function movimientos(id) {
  const { ok, datos } = await api("GET", `/api/productos/${id}/movimientos`);
  if (!ok) return toast(datos.error, "error");
  modal(`Inventario de ${datos.producto.nombre}: ${datos.producto.stock}`, tablaDatos([
    { titulo: "Fecha", valor: (m) => fechaCorta(m.fecha) },
    { titulo: "Motivo", valor: (m) => m.motivo.toLowerCase() },
    { titulo: "Cantidad", valor: (m) => (m.cantidad > 0 ? `+${m.cantidad}` : String(m.cantidad)), num: true },
    { titulo: "Pedido", valor: (m) => (m.pedido_id ? `#${m.pedido_id}` : "—") },
    { titulo: "Quién", valor: (m) => m.usuario || "Sistema" },
  ], datos.movimientos));
}

async function cargarCategorias() {
  await cargarCatalogo();
  vaciar(document.getElementById("t-categorias"), tablaDatos([
    { titulo: "Categoría", valor: (c) => c.nombre },
    { titulo: "Clave normalizada", valor: (c) => el("code", { class: "mono", text: c.clave }) },
    { titulo: "Descripción", valor: (c) => c.descripcion || "—" },
    { titulo: "Ítems", valor: (c) => numero(c.productos), num: true },
    { titulo: "Estado", valor: (c) => insignia(c.activo ? "ACTIVO" : "INACTIVO") },
    { titulo: "", valor: (c) => (ES_ADMIN ? el("span", { class: "acciones-tabla" },
      el("button", { class: "boton-tabla", type: "button", "aria-label": "Editar", onClick: () => editarCategoria(c) }, icono("actualizar")),
      el("button", { class: "boton-tabla", type: "button", "aria-label": "Eliminar", onClick: () => confirmarBorrado(`¿Eliminar «${c.nombre}»?`, `/api/categorias/${c.id}`, cargarCategorias) }, icono("basura"))) : "") },
  ], categorias));
}
function editarCategoria(c) {
  formularioModal(c ? `Editar ${c.nombre}` : "Nueva categoría", [
    { nombre: "nombre", etiqueta: "Nombre" }, { nombre: "descripcion", etiqueta: "Descripción" },
    { nombre: "activo", etiqueta: "Activa", tipo: "checkbox" }], c || { activo: true }, async (datos) => {
    const r = await api(c ? "PUT" : "POST", c ? `/api/categorias/${c.id}` : "/api/categorias", datos);
    if (r.ok) cargarCategorias();
    return r;
  });
}

// --- Usuarios ----------------------------------------------------------------------------------
let paginaUsuarios = 1;
async function cargarUsuarios(pagina = paginaUsuarios) {
  paginaUsuarios = pagina;
  const filtros = new URLSearchParams({ pagina, rol: document.getElementById("u-rol").value, q: document.getElementById("u-buscar").value.trim() });
  const { ok, datos } = await api("GET", `/api/usuarios?${filtros}`);
  if (!ok) return toast(datos.error, "error");
  vaciar(document.getElementById("t-usuarios"), tablaDatos([
    { titulo: "Nombre", valor: (u) => u.nombre },
    { titulo: "Correo", valor: (u) => u.email },
    { titulo: "Celular", valor: (u) => u.telefono || "—" },
    { titulo: "Rol", valor: (u) => etiqueta(u.rol.toLowerCase(), u.rol === "ADMIN" ? "vino" : u.rol === "EMPLEADO" ? "alerta" : "") },
    { titulo: "Estado", valor: (u) => insignia(u.estado) },
    { titulo: "Transacciones", valor: (u) => numero(u.transacciones), num: true },
    { titulo: "", valor: (u) => el("span", { class: "acciones-tabla" },
      el("button", { class: "boton-tabla", type: "button", "aria-label": "Editar", onClick: () => editarUsuario(u) }, icono("actualizar")),
      el("button", { class: "boton-tabla", type: "button", "aria-label": "Eliminar", onClick: () => confirmarBorrado(`¿Eliminar a ${u.nombre}?`, `/api/usuarios/${u.id}`, () => cargarUsuarios()) }, icono("basura"))) },
  ], datos.usuarios));
  paginacion(document.getElementById("p-usuarios"), datos.pagina, datos.paginas, cargarUsuarios);
}
function editarUsuario(u) {
  formularioModal(u ? `Editar a ${u.nombre}` : "Nuevo usuario", [
    { nombre: "nombre", etiqueta: "Nombre" }, { nombre: "email", etiqueta: "Correo", tipo: "email" },
    { nombre: "telefono", etiqueta: "Celular", nulo: true },
    { nombre: "rol", etiqueta: "Rol", tipo: "select", opciones: [["CLIENTE", "Cliente"], ["EMPLEADO", "Empleado (caja)"], ["ADMIN", "Administrador"]] },
    { nombre: "estado", etiqueta: "Estado", tipo: "select", opciones: ["ACTIVO", "EN_OBSERVACION", "BLOQUEADO", "INACTIVO"].map((e) => [e, e.toLowerCase().replace("_", " ")]) },
    { nombre: "password", etiqueta: u ? "Nueva contraseña (vacía = no cambia)" : "Contraseña", tipo: "password", nulo: true,
      ayuda: "8 a 64 caracteres con mayúscula, minúscula, número y símbolo. Se guarda con hash (scrypt)." },
  ], u || { rol: "EMPLEADO", estado: "ACTIVO" }, async (datos) => {
    if (!datos.password) delete datos.password;
    const r = await api(u ? "PATCH" : "POST", u ? `/api/usuarios/${u.id}` : "/api/usuarios", datos);
    if (r.ok) cargarUsuarios();
    return r;
  });
}

// --- Arranque ------------------------------------------------------------------------------------
document.getElementById("nuevo-item")?.addEventListener("click", () => editarItem(null));
document.getElementById("nueva-categoria")?.addEventListener("click", () => editarCategoria(null));
document.getElementById("nuevo-usuario")?.addEventListener("click", () => editarUsuario(null));
document.getElementById("u-rol")?.addEventListener("change", () => cargarUsuarios(1));
document.getElementById("u-buscar")?.addEventListener("input", () => { clearTimeout(espera); espera = setTimeout(() => cargarUsuarios(1), 350); });

await cargarCatalogo();
const mapa = await api("GET", "/api/domicilios/mapa");
prepararCaja(mapa.ok ? mapa.datos.nodos.map((n) => n.nombre).filter((b) => b !== mapa.datos.tienda) : []);
pintarLineas();
pestanas({ facturas: () => cargarFacturas(), pedidos: () => cargarPedidos(), items: cargarItems, categorias: cargarCategorias,
  usuarios: () => cargarUsuarios() }, "caja");
