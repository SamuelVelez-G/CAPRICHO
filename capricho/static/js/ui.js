/* Piezas de interfaz compartidas por las páginas de la entrega final. */

import { el, icono, numero } from "./comun.js";

export const css = (nombre) => getComputedStyle(document.documentElement).getPropertyValue(nombre).trim();
export const pct = (valor, decimales = 1) => `${numero((valor || 0) * 100, decimales)} %`;
export const ms = (valor) => (valor >= 1000 ? `${numero(valor / 1000, 2)} s` : valor >= 1 ? `${numero(valor, 1)} ms`
  : `${numero(valor * 1000, 0)} µs`);

export function kpi(etiqueta, valor, nota, nombreIcono = "grafico", clase = "") {
  return el("div", { class: `tarjeta kpi ${clase}` },
    el("p", { class: "kpi__etiqueta" }, icono(nombreIcono), etiqueta),
    el("p", { class: "kpi__valor", text: valor }),
    nota ? el("p", { class: "kpi__delta", text: nota }) : null);
}

/** Pestañas con [data-pestana] y paneles #panel-<nombre>; recuerda la pestaña en la URL. */
export function pestanas(alMostrar = {}, porDefecto) {
  const botones = [...document.querySelectorAll("[data-pestana]")];
  const mostrar = (nombre) => {
    for (const boton of botones) {
      const activa = boton.dataset.pestana === nombre;
      boton.setAttribute("aria-selected", String(activa));
      document.getElementById(`panel-${boton.dataset.pestana}`).hidden = !activa;
    }
    history.replaceState(null, "", `#${nombre}`);
    alMostrar[nombre]?.();
  };
  botones.forEach((b) => b.addEventListener("click", () => mostrar(b.dataset.pestana)));
  const pedida = location.hash.slice(1);
  mostrar(botones.some((b) => b.dataset.pestana === pedida) ? pedida : porDefecto || botones[0]?.dataset.pestana);
  return mostrar;
}

/** Tabla a partir de columnas {titulo, valor(fila) -> texto o nodo, num}. */
export function tablaDatos(columnas, filas, vacio = "Sin datos.") {
  if (!filas.length) return el("p", { class: "muted", text: vacio });
  return el("div", { class: "tabla-caja" }, el("table", { class: "tabla" },
    el("thead", {}, el("tr", {}, ...columnas.map((c) => el("th", { class: c.num ? "num" : "", text: c.titulo })))),
    el("tbody", {}, ...filas.map((fila) => el("tr", { class: c_fila(columnas, fila) }, ...columnas.map((c) => {
      const contenido = c.valor(fila);
      return el("td", { class: c.num ? "num" : "" }, contenido instanceof Node ? contenido : String(contenido ?? ""));
    }))))));
}
const c_fila = (columnas, fila) => columnas.find((c) => c.claseFila)?.claseFila(fila) || null;

/** Barra de porcentaje con su número (0 a 1). */
export function barraPct(valor, clase = "") {
  const ancho = Math.max(0, Math.min(1, valor || 0)) * 100;
  const barra = el("span", { class: "barra-pct__relleno" });
  barra.style.width = `${ancho}%`;
  return el("span", { class: `barra-pct ${clase}` }, el("span", { class: "barra-pct__fondo" }, barra),
    el("span", { class: "barra-pct__texto", text: pct(valor) }));
}

export function etiqueta(texto, tono = "") {
  return el("span", { class: `etiqueta ${tono ? `etiqueta--${tono}` : ""}`, text: texto });
}

export function leyenda(items) {
  return el("div", { class: "leyenda" }, ...items.map(([nombre, color, punteada]) => {
    const muestra = el("span", { class: punteada ? "leyenda__linea leyenda__linea--punteada" : "leyenda__linea" });
    muestra.style.background = punteada ? "none" : color;
    muestra.style.borderColor = color;
    return el("span", { class: "leyenda__item" }, muestra, nombre);
  }));
}

/** Anterior / siguiente para las tablas largas. */
export function paginacion(caja, pagina, paginas, ir) {
  caja.replaceChildren(
    el("button", { class: "boton boton--xs boton--contorno", type: "button", disabled: pagina <= 1, onClick: () => ir(pagina - 1), text: "Anterior" }),
    el("span", { class: "muted", text: `Página ${pagina} de ${paginas}` }),
    el("button", { class: "boton boton--xs boton--contorno", type: "button", disabled: pagina >= paginas, onClick: () => ir(pagina + 1), text: "Siguiente" }));
}
