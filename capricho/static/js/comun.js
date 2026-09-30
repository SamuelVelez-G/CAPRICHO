/*
 * Utilidades compartidas por todas las páginas.
 *
 * Regla de seguridad: los datos que vienen del servidor o del usuario se
 * insertan SIEMPRE con textContent (función el()), nunca con innerHTML.
 * Así un nombre como "<script>" se muestra como texto y no se ejecuta (XSS).
 */

const RUTA_ICONOS = document.body.dataset.iconos;

export function csrf() {
  return document.querySelector('meta[name="csrf-token"]').content;
}

/** fetch con JSON, cookie de sesión y token CSRF. Nunca lanza por códigos HTTP. */
export async function api(metodo, url, cuerpo) {
  const opciones = { method: metodo, credentials: "same-origin", headers: { Accept: "application/json" } };
  if (cuerpo !== undefined) {
    opciones.headers["Content-Type"] = "application/json";
    opciones.body = typeof cuerpo === "string" ? cuerpo : JSON.stringify(cuerpo);
  }
  if (metodo !== "GET") opciones.headers["X-CSRF-Token"] = csrf();
  const inicio = performance.now();
  let respuesta;
  try {
    respuesta = await fetch(url, opciones);
  } catch {
    return { status: 0, ok: false, ms: 0, datos: { ok: false, error: "No hay conexión con el servidor" } };
  }
  let datos;
  try {
    datos = await respuesta.json();
  } catch {
    datos = { ok: false, error: `Respuesta no válida (${respuesta.status})` };
  }
  return { status: respuesta.status, ok: respuesta.ok, ms: Math.round(performance.now() - inicio), datos };
}

export const dinero = (valor) => "$" + Math.round(Number(valor) || 0).toLocaleString("es-CO");
export const numero = (valor, decimales = 0) =>
  Number(valor || 0).toLocaleString("es-CO", { minimumFractionDigits: decimales, maximumFractionDigits: decimales });

const MESES = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"];
export function fechaCorta(iso, conMilis = false) {
  if (!iso) return "";
  const [dia, hora] = iso.split("T");
  const [, mes, d] = dia.split("-");
  const h = conMilis ? hora.slice(0, 12) : hora.slice(0, 8);
  return `${Number(d)} ${MESES[Number(mes) - 1]} · ${h}`;
}

/** Crea un elemento. Los textos siempre entran como nodos de texto. */
export function el(etiqueta, atributos = {}, ...hijos) {
  const nodo = document.createElement(etiqueta);
  for (const [clave, valor] of Object.entries(atributos)) {
    if (valor === undefined || valor === null || valor === false) continue;
    if (clave === "class") nodo.className = valor;
    else if (clave === "text") nodo.textContent = valor;
    else if (clave.startsWith("on")) nodo.addEventListener(clave.slice(2).toLowerCase(), valor);
    else if (clave === "dataset") Object.assign(nodo.dataset, valor);
    else nodo.setAttribute(clave, valor === true ? "" : valor);
  }
  agregar(nodo, hijos);
  return nodo;
}

function agregar(nodo, hijos) {
  for (const hijo of hijos.flat()) {
    if (hijo === null || hijo === undefined || hijo === false) continue;
    nodo.append(hijo instanceof Node ? hijo : document.createTextNode(String(hijo)));
  }
}

export function vaciar(nodo, ...hijos) {
  nodo.replaceChildren();
  agregar(nodo, hijos);
  return nodo;
}

export function icono(nombre, clase = "") {
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("class", `icono ${clase}`.trim());
  svg.setAttribute("aria-hidden", "true");
  const uso = document.createElementNS("http://www.w3.org/2000/svg", "use");
  uso.setAttribute("href", `${RUTA_ICONOS}#${nombre}`);
  svg.append(uso);
  return svg;
}

export function svg(etiqueta, atributos = {}, ...hijos) {
  const nodo = document.createElementNS("http://www.w3.org/2000/svg", etiqueta);
  for (const [clave, valor] of Object.entries(atributos)) {
    if (valor === undefined || valor === null || valor === false) continue;
    if (clave === "text") nodo.textContent = valor;
    else if (clave.startsWith("on")) nodo.addEventListener(clave.slice(2).toLowerCase(), valor);
    else nodo.setAttribute(clave, valor);
  }
  for (const hijo of hijos.flat()) if (hijo) nodo.append(hijo);
  return nodo;
}

const ICONO_TOAST = { ok: "ok", error: "bloqueo", alerta: "alerta", info: "info" };
export function toast(mensaje, tipo = "info", duracion = 4200) {
  const caja = document.getElementById("toasts");
  const aviso = el("div", { class: `toast toast--${tipo}`, role: tipo === "error" ? "alert" : "status" },
    icono(ICONO_TOAST[tipo] || "info"), el("span", { text: mensaje }));
  caja.append(aviso);
  setTimeout(() => aviso.remove(), duracion);
}

/** Insignia de estado: siempre ícono + texto, nunca solo color. */
const ICONO_ESTADO = {
  APROBADA: "ok", ENTREGADO: "ok", REVISADA: "ok",
  SOSPECHOSA: "alerta", ABIERTA: "alerta", EN_PROCESO: "reloj",
  RECHAZADA: "bloqueo", RECHAZADO: "bloqueo", NUEVA: "alerta", INVALIDA: "bloqueo",
  DESCARTADA: "cerrar", SOLICITADO: "cola", DUPLICADA: "bloqueo",
  EN_OBSERVACION: "alerta", ACTIVO: "ok", INACTIVO: "cerrar",
};
const TEXTO_ESTADO = { EN_PROCESO: "En proceso", SOLICITADO: "En cola", EN_OBSERVACION: "En observación" };
export function insignia(estado) {
  const texto = TEXTO_ESTADO[estado] || estado.charAt(0) + estado.slice(1).toLowerCase();
  return el("span", { class: `insignia insignia--${estado}` }, icono(ICONO_ESTADO[estado] || "info"), texto);
}

export function nivel(valor) {
  return el("span", { class: `nivel nivel--${valor}`, text: valor.charAt(0) + valor.slice(1).toLowerCase() });
}

/** Pinta en el formulario los errores {campo: mensaje} que devolvió el servidor. */
export function mostrarErrores(formulario, errores = {}) {
  let primero = null;
  for (const [campo, mensaje] of Object.entries(errores)) {
    const caja = formulario.querySelector(`[data-campo="${CSS.escape(campo)}"]`);
    if (!caja) continue;
    caja.classList.add("invalido");
    caja.classList.remove("valido");
    caja.querySelector(".campo__error span").textContent = mensaje;
    primero ??= caja.querySelector("input, select, textarea");
  }
  primero?.focus();
  return primero !== null;
}

export function modal(titulo, contenido, { ancho } = {}) {
  const cerrar = () => { capa.remove(); document.removeEventListener("keydown", teclado); };
  const teclado = (evento) => { if (evento.key === "Escape") cerrar(); };
  const caja = el("div", { class: "modal__caja", role: "dialog", "aria-modal": "true", "aria-label": titulo },
    el("div", { class: "modal__cabeza" }, el("h2", { text: titulo }),
      el("button", { class: "boton-icono", type: "button", "aria-label": "Cerrar", onClick: cerrar }, icono("cerrar"))),
    el("div", { class: "modal__cuerpo" }, contenido));
  if (ancho) caja.classList.add(ancho);
  const capa = el("div", { class: "modal", onClick: (e) => { if (e.target === capa) cerrar(); } }, caja);
  document.body.append(capa);
  document.addEventListener("keydown", teclado);
  caja.querySelector("button").focus();
  return { cerrar, cuerpo: caja.querySelector(".modal__cuerpo") };
}

// --- Encabezado --------------------------------------------------------------
const botonMenu = document.getElementById("menu-movil");
botonMenu?.addEventListener("click", () => {
  const nav = document.getElementById("nav");
  const abierto = nav.classList.toggle("abierto");
  botonMenu.setAttribute("aria-expanded", String(abierto));
});

document.getElementById("boton-salir")?.addEventListener("click", async () => {
  await api("POST", "/api/auth/logout");
  window.location.href = "/";
});

