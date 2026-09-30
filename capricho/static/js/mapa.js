/*
 * Dibuja el grafo de domicilios (barrios = nodos, vías = aristas) y resalta
 * la ruta de Dijkstra. Lo usan la tienda y el panel de operación.
 */

import { api, dinero, el, icono, numero, svg, vaciar } from "./comun.js";

export async function cargarMapa() {
  const { ok, datos } = await api("GET", "/api/domicilios/mapa");
  return ok ? datos : null;
}

export function dibujarMapa(lienzo, datos, alElegir) {
  const posicion = new Map(datos.nodos.map((n) => [n.nombre, n]));
  const aristas = datos.aristas.map((a) => {
    const o = posicion.get(a.origen);
    const d = posicion.get(a.destino);
    const linea = svg("line", { class: "arista", x1: o.x, y1: o.y, x2: d.x, y2: d.y });
    const km = svg("text", { class: "km", x: (o.x + d.x) / 2 + 6, y: (o.y + d.y) / 2 - 6, text: `${numero(a.km, 1)} km` });
    return { ...a, linea, km };
  });
  const nodos = datos.nodos.map((n) => {
    const esTienda = n.nombre === datos.tienda;
    const grupo = svg("g", {
      class: `nodo${esTienda ? " tienda" : ""}`, tabindex: "0", role: "button",
      "aria-label": `${n.nombre}: ${numero(n.distancia_km, 1)} km, ${dinero(n.tarifa)}`,
      onClick: () => alElegir?.(n.nombre),
      onKeydown: (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); alElegir?.(n.nombre); } },
    },
    svg("circle", { cx: n.x, cy: n.y, r: esTienda ? 17 : 11 }),
    svg("text", { x: n.x, y: n.y - (esTienda ? 26 : 20), "text-anchor": "middle", text: esTienda ? `${n.nombre} · tienda` : n.nombre }));
    return { ...n, grupo };
  });
  vaciar(lienzo, svg("g", {}, ...aristas.map((a) => a.linea)), svg("g", {}, ...aristas.map((a) => a.km)),
    svg("g", {}, ...nodos.map((n) => n.grupo)));

  return function resaltar(ruta) {
    const enRuta = new Set(ruta || []);
    const pares = new Set();
    (ruta || []).forEach((b, i) => { if (i) pares.add([ruta[i - 1], b].sort().join("|")); });
    for (const a of aristas) a.linea.classList.toggle("en-ruta", pares.has([a.origen, a.destino].sort().join("|")));
    for (const n of nodos) {
      n.grupo.classList.toggle("en-ruta", enRuta.has(n.nombre) && n.nombre !== datos.tienda);
      n.grupo.classList.toggle("destino", ruta?.at(-1) === n.nombre && n.nombre !== datos.tienda);
    }
  };
}

export function resumenRuta(domicilio) {
  const pasos = [];
  domicilio.ruta.forEach((barrio, i) => {
    if (i) pasos.push(icono("flecha"));
    pasos.push(el("span", { text: barrio }));
  });
  return el("div", { class: "ruta-info" },
    el("div", { class: "ruta-pasos" }, ...pasos),
    el("div", { class: "dato-grande" },
      el("div", {}, el("strong", { text: dinero(domicilio.tarifa) }), el("span", { text: "tarifa del domicilio" })),
      el("div", {}, el("strong", { text: `${numero(domicilio.distancia_km, 1)} km` }), el("span", { text: "ruta más corta" }))),
    el("p", { class: "muted", text: `Dijkstra visitó ${domicilio.nodos_visitados} barrios para encontrarla. ` +
      `Ida y vuelta la moto gasta ${numero(domicilio.galones_ida_y_vuelta, 3)} galones (${dinero(domicilio.costo_gasolina)}).` }));
}
