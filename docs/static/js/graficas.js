/*
 * Gráficas en SVG hechas a mano (sin librerías): funcionan sin internet y
 * usan la paleta de la marca.
 *
 * Reglas de diseño: barras de máximo 24 px con la punta redondeada, 2 px de
 * separación entre segmentos, rejilla tenue, un solo eje Y, y los colores de
 * estado (verde/ámbar/rojo) solo para bueno/sospechoso/bloqueado, siempre
 * acompañados de texto. Cada gráfica tiene tooltip y una vista de tabla.
 */

import { el, numero, svg, vaciar } from "./comun.js";

const css = (nombre) => getComputedStyle(document.documentElement).getPropertyValue(nombre).trim();
export const RAMPA_CALOR = ["#f6ece0", "#f0d3cc", "#e2aab0", "#cb7d8a", "#a9505f", "#7d2f3f", "#521b27"];

function pasoLimpio(maximo, divisiones = 4) {
  if (maximo <= 0) return 1;
  const bruto = maximo / divisiones;
  const potencia = 10 ** Math.floor(Math.log10(bruto));
  const opciones = [1, 2, 2.5, 5, 10].map((m) => m * potencia);
  return opciones.find((o) => o >= bruto) || opciones.at(-1);
}

/** Barra con la punta redondeada (4 px) y la base recta. */
function rutaBarra(x, y, ancho, alto, radio = 4, arriba = true) {
  if (alto <= 0) return "";
  const r = Math.min(radio, alto, ancho / 2);
  if (!arriba) return `M${x},${y}h${ancho}v${alto}h${-ancho}z`;
  return `M${x},${y + alto}v${-(alto - r)}q0,${-r} ${r},${-r}h${ancho - 2 * r}q${r},0 ${r},${r}v${alto - r}z`;
}

function rutaBarraHorizontal(x, y, largo, grosor, radio = 4) {
  if (largo <= 0) return "";
  const r = Math.min(radio, largo, grosor / 2);
  return `M${x},${y}h${largo - r}q${r},0 ${r},${r}v${grosor - 2 * r}q0,${r} ${-r},${r}h${-(largo - r)}z`;
}

function crearTooltip(contenedor) {
  let tip = contenedor.querySelector(".tooltip");
  if (!tip) {
    tip = el("div", { class: "tooltip", role: "status", hidden: true });
    contenedor.append(tip);
  }
  return {
    mostrar(x, y, tituloTexto, filas) {
      vaciar(tip, el("div", { class: "tooltip__titulo", text: tituloTexto }),
        ...filas.map(([color, etiqueta, valor]) => {
          const clave = color ? el("span", { class: "leyenda__linea" }) : null;
          if (clave) clave.style.background = color;
          return el("div", { class: "tooltip__fila" }, clave, el("span", { text: etiqueta }), el("strong", { text: valor }));
        }));
      tip.hidden = false;
      const ancho = contenedor.clientWidth;
      tip.style.left = `${Math.max(80, Math.min(ancho - 80, x))}px`;
      tip.style.top = `${y}px`;
    },
    ocultar() { tip.hidden = true; },
  };
}

/**
 * Columnas apiladas por tramo (día u hora).
 * series: [{clave, nombre, color}] en orden de abajo hacia arriba.
 */
export function columnasApiladas(contenedor, puntos, series, { etiqueta, alto = 260, marcarPicos = true } = {}) {
  const ancho = Math.max(320, contenedor.clientWidth);
  const margen = { arriba: 22, derecha: 8, abajo: 28, izquierda: 42 };
  const anchoUtil = ancho - margen.izquierda - margen.derecha;
  const altoUtil = alto - margen.arriba - margen.abajo;
  const totales = puntos.map((p) => series.reduce((s, serie) => s + (p[serie.clave] || 0), 0));
  const paso = pasoLimpio(Math.max(...totales, 1));
  const tope = Math.ceil(Math.max(...totales, 1) / paso) * paso;
  const y = (v) => margen.arriba + altoUtil - (v / tope) * altoUtil;
  const banda = anchoUtil / puntos.length;
  const grosor = Math.min(24, Math.max(3, banda * 0.66));

  const capas = [];
  for (let v = 0; v <= tope; v += paso) {
    capas.push(svg("line", { class: v === 0 ? "eje" : "rejilla-linea", x1: margen.izquierda, x2: ancho - margen.derecha, y1: y(v), y2: y(v) }));
    capas.push(svg("text", { class: "tick", x: margen.izquierda - 8, y: y(v) + 4, "text-anchor": "end", text: numero(v) }));
  }
  const cadaCuanto = Math.ceil(puntos.length / Math.max(2, Math.floor(anchoUtil / 58)));
  const tip = crearTooltip(contenedor);

  puntos.forEach((punto, i) => {
    const x = margen.izquierda + banda * i + (banda - grosor) / 2;
    let acumulado = 0;
    const grupo = svg("g", { class: "columna" });
    const visibles = series.filter((s) => punto[s.clave] > 0);
    series.forEach((serie) => {
      const valor = punto[serie.clave] || 0;
      if (!valor) return;
      const esTope = serie === visibles.at(-1);
      const base = y(acumulado);
      acumulado += valor;
      const cima = y(acumulado) + (esTope ? 0 : 1);      // 2 px de separación entre segmentos
      const altoSeg = Math.max(0, base - cima - (acumulado - valor > 0 ? 1 : 0));
      grupo.append(svg("path", { d: rutaBarra(x, cima, grosor, altoSeg, 4, esTope), fill: serie.color, class: "marca-hover" }));
    });
    if (marcarPicos && punto.pico) {
      grupo.append(svg("circle", { class: "pico", cx: x + grosor / 2, cy: y(totales[i]) - 9, r: 4.5 }));
    }
    // Zona de contacto más grande que la barra.
    const zona = svg("rect", { x: margen.izquierda + banda * i, y: margen.arriba, width: banda, height: altoUtil, fill: "transparent", tabindex: "0",
      "aria-label": `${etiqueta(punto)}: ${series.map((s) => `${s.nombre} ${punto[s.clave] || 0}`).join(", ")}` });
    const mostrar = () => {
      grupo.classList.add("activo");
      tip.mostrar(x + grosor / 2, y(totales[i]), etiqueta(punto), [
        ...series.slice().reverse().map((s) => [s.color, s.nombre, numero(punto[s.clave] || 0)]),
        [null, "Anomalías", numero(punto.anomalias || 0)],
      ]);
    };
    const ocultar = () => { grupo.classList.remove("activo"); tip.ocultar(); };
    zona.addEventListener("pointerenter", mostrar);
    zona.addEventListener("focus", mostrar);
    zona.addEventListener("pointerleave", ocultar);
    zona.addEventListener("blur", ocultar);
    capas.push(grupo, zona);
    if (i % cadaCuanto === 0) {
      capas.push(svg("text", { class: "tick", x: x + grosor / 2, y: alto - 8, "text-anchor": "middle", text: etiqueta(punto, true) }));
    }
  });

  const lienzo = svg("svg", { viewBox: `0 0 ${ancho} ${alto}`, width: ancho, height: alto, role: "img" }, ...capas);
  const tipActual = contenedor.querySelector(".tooltip");
  vaciar(contenedor, lienzo, tipActual);
}

/** Barras horizontales: una categoría por fila, valor en la punta. */
export function barrasHorizontales(contenedor, filas, { formato = numero, colorPorDefecto = css("--serie-1"), extra } = {}) {
  const ancho = Math.max(280, contenedor.clientWidth);
  const etiquetaAncho = Math.min(150, ancho * 0.38);
  const valorAncho = 64;
  const alturaFila = 34;
  const grosor = 18;
  const alto = filas.length * alturaFila + 4;
  const maximo = Math.max(...filas.map((f) => f.valor), 1);
  const largoUtil = ancho - etiquetaAncho - valorAncho - 10;
  const tip = crearTooltip(contenedor);

  const capas = [svg("line", { class: "eje", x1: etiquetaAncho, x2: etiquetaAncho, y1: 0, y2: alto })];
  filas.forEach((fila, i) => {
    const yFila = i * alturaFila + (alturaFila - grosor) / 2;
    const largo = (fila.valor / maximo) * largoUtil;
    const color = fila.color || colorPorDefecto;
    const grupo = svg("g", {},
      svg("text", { class: "etiqueta-barra", x: etiquetaAncho - 10, y: yFila + grosor / 2 + 4, "text-anchor": "end", text: fila.etiqueta }),
      svg("path", { class: "marca-hover", d: rutaBarraHorizontal(etiquetaAncho, yFila, Math.max(largo, fila.valor ? 3 : 0), grosor), fill: color }),
      svg("text", { class: "valor", x: etiquetaAncho + largo + 8, y: yFila + grosor / 2 + 4, text: formato(fila.valor) }));
    const zona = svg("rect", { x: 0, y: i * alturaFila, width: ancho, height: alturaFila, fill: "transparent", tabindex: "0",
      "aria-label": `${fila.etiqueta}: ${formato(fila.valor)}${extra ? ", " + extra(fila) : ""}` });
    const mostrar = () => {
      grupo.classList.add("activo");
      tip.mostrar(etiquetaAncho + largo / 2, i * alturaFila + 4, fila.etiqueta,
        [[color, "Total", formato(fila.valor)], ...(extra ? [[null, extra(fila), ""]] : [])]);
    };
    const ocultar = () => { grupo.classList.remove("activo"); tip.ocultar(); };
    zona.addEventListener("pointerenter", mostrar);
    zona.addEventListener("focus", mostrar);
    zona.addEventListener("pointerleave", ocultar);
    zona.addEventListener("blur", ocultar);
    capas.push(grupo, zona);
  });
  const tipActual = contenedor.querySelector(".tooltip");
  vaciar(contenedor, svg("svg", { viewBox: `0 0 ${ancho} ${alto}`, width: ancho, height: alto, role: "img" }, ...capas), tipActual);
}

/** Mapa de calor día x hora. La intensidad = cantidad de anomalías. */
export function mapaCalor(contenedor, calor) {
  const maximo = Math.max(...calor.celdas.flat(), 1);
  const color = (v) => (v === 0 ? RAMPA_CALOR[0] : RAMPA_CALOR[Math.min(6, 1 + Math.floor((v / maximo) * 5.999))]);
  const tip = crearTooltip(contenedor);
  const rejilla = el("div", { class: "calor", role: "grid", "aria-label": "Anomalías por día de la semana y hora" });
  rejilla.append(el("span"));
  for (let h = 0; h < 24; h++) rejilla.append(el("span", { class: "calor__hora", text: h % 3 === 0 ? String(h) : "" }));
  calor.dias.forEach((dia, d) => {
    rejilla.append(el("span", { class: "calor__dia", text: dia }));
    for (let h = 0; h < 24; h++) {
      const valor = calor.celdas[d][h];
      const celda = el("span", { class: "calor__celda", tabindex: valor ? "0" : "-1", role: "gridcell",
        "aria-label": `${dia} ${h}:00, ${valor} anomalías` });
      celda.style.background = color(valor);
      const mostrar = () => {
        const caja = celda.getBoundingClientRect();
        const base = contenedor.getBoundingClientRect();
        tip.mostrar(caja.left - base.left + caja.width / 2, caja.top - base.top, `${dia} · ${dos(h)}:00 – ${dos(h)}:59`,
          [[null, "Anomalías", numero(valor)]]);
      };
      celda.addEventListener("pointerenter", mostrar);
      celda.addEventListener("focus", mostrar);
      celda.addEventListener("pointerleave", () => tip.ocultar());
      celda.addEventListener("blur", () => tip.ocultar());
      rejilla.append(celda);
    }
  });
  const escala = el("div", { class: "escala" }, el("span", { class: "muted", text: "Menos" }),
    ...RAMPA_CALOR.map((c) => { const s = el("span", { class: "escala__muestra" }); s.style.background = c; return s; }),
    el("span", { class: "muted", text: `Más (${maximo})` }));
  const tipActual = contenedor.querySelector(".tooltip");
  vaciar(contenedor, rejilla, escala, tipActual);
}

const dos = (n) => String(n).padStart(2, "0");

/**
 * Ventana deslizante: cada punto es una transacción del usuario en el eje del
 * tiempo (segundos respecto a la anomalía). El rectángulo es la ventana; con
 * "Reproducir" se desliza de izquierda a derecha contando lo que queda adentro.
 */
export function ventanaDeslizante(contenedor, puntos, ventana, margenSegundos, alCambiar) {
  const ancho = Math.max(320, contenedor.clientWidth);
  const alto = 150;
  const m = { izquierda: 16, derecha: 16 };
  const escalaX = (s) => m.izquierda + ((s + margenSegundos) / (2 * margenSegundos)) * (ancho - m.izquierda - m.derecha);
  const colores = { APROBADA: css("--ok"), SOSPECHOSA: css("--alerta"), RECHAZADA: css("--critico") };
  const ejeY = 96;

  const caja = svg("rect", { class: "ventana-caja", y: 26, height: 96, rx: 8 });
  const conteo = svg("text", { class: "valor", y: 18, "text-anchor": "middle" });
  const circulos = puntos.map((p, i) => svg("circle", {
    class: `punto${p.es_actual ? " actual" : ""}`, cx: escalaX(p.desfase), cy: ejeY - (i % 3) * 16, r: p.es_actual ? 8 : 6.5,
    fill: p.hash_valido ? colores[p.estado] : css("--tinta-3"),
  }, svg("title", { text: `${p.id_txn} · ${p.fecha_txn.slice(11)} · ${p.estado}` })));

  const marcas = [];
  const pasoTick = pasoLimpio(margenSegundos, 3);
  for (let s = -Math.floor(margenSegundos / pasoTick) * pasoTick; s <= margenSegundos; s += pasoTick) {
    marcas.push(svg("line", { class: "rejilla-linea", x1: escalaX(s), x2: escalaX(s), y1: 30, y2: 124 }));
    marcas.push(svg("text", { class: "tick", x: escalaX(s), y: 140, "text-anchor": "middle", text: `${s > 0 ? "+" : ""}${numero(s, s % 1 ? 1 : 0)} s` }));
  }

  function ubicar(fin) {
    const dentro = puntos.filter((p) => p.desfase > fin - ventana && p.desfase <= fin);
    const x1 = escalaX(Math.max(-margenSegundos, fin - ventana));
    const x2 = escalaX(Math.min(margenSegundos, fin));
    caja.setAttribute("x", x1);
    caja.setAttribute("width", Math.max(2, x2 - x1));
    conteo.setAttribute("x", (x1 + x2) / 2);
    conteo.textContent = `${dentro.length} en ${numero(ventana, ventana % 1 ? 1 : 0)} s`;
    circulos.forEach((c, i) => c.setAttribute("opacity", dentro.includes(puntos[i]) || !ventana ? "1" : ".35"));
    alCambiar?.(dentro.length, fin);
  }

  const lienzo = svg("svg", { viewBox: `0 0 ${ancho} ${alto}`, width: ancho, height: alto, class: "ventana-vis", role: "img",
    "aria-label": `Transacciones del usuario alrededor de la anomalía; ventana de ${ventana} segundos` },
  ...marcas, svg("line", { class: "eje", x1: m.izquierda, x2: ancho - m.derecha, y1: 124, y2: 124 }),
  ventana ? caja : null, ventana ? conteo : null, ...circulos);
  vaciar(contenedor, lienzo);
  if (ventana) ubicar(0);

  let animacion = null;
  return {
    reproducir() {
      cancelAnimationFrame(animacion);
      const inicio = performance.now();
      const duracion = 6500;
      const desde = -margenSegundos + ventana;
      const hasta = margenSegundos;
      const cuadro = (ahora) => {
        const t = Math.min(1, (ahora - inicio) / duracion);
        ubicar(desde + (hasta - desde) * t);
        if (t < 1) animacion = requestAnimationFrame(cuadro);
        else setTimeout(() => ubicar(0), 700);
      };
      animacion = requestAnimationFrame(cuadro);
    },
  };
}

/** Tabla equivalente a una gráfica (para accesibilidad y para leer valores exactos). */
export function tabla(columnas, filas) {
  return el("div", { class: "tabla-caja" }, el("table", { class: "tabla" },
    el("thead", {}, el("tr", {}, ...columnas.map((c) => el("th", { class: c.num ? "num" : "", text: c.titulo })))),
    el("tbody", {}, ...filas.map((fila) => el("tr", {}, ...columnas.map((c) =>
      el("td", { class: c.num ? "num" : "", text: c.valor(fila) })))))));
}
