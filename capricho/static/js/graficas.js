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

/**
 * Líneas sobre un mismo eje (por ejemplo, la pérdida por época al entrenar).
 * series: [{nombre, color, valores: [números]}]
 */
export function lineas(contenedor, series, { alto = 240, etiquetaX = (i) => String(i + 1), formato = (v) => numero(v, 2) } = {}) {
  const ancho = Math.max(320, contenedor.clientWidth);
  const m = { arriba: 16, derecha: 12, abajo: 28, izquierda: 48 };
  const n = Math.max(...series.map((s) => s.valores.length));
  const maximo = Math.max(...series.flatMap((s) => s.valores), 1e-9);
  const paso = pasoLimpio(maximo);
  const tope = Math.ceil(maximo / paso) * paso;
  const x = (i) => m.izquierda + (i / Math.max(1, n - 1)) * (ancho - m.izquierda - m.derecha);
  const y = (v) => m.arriba + (alto - m.arriba - m.abajo) * (1 - v / tope);
  const capas = [];
  for (let v = 0; v <= tope + 1e-9; v += paso) {
    capas.push(svg("line", { class: v === 0 ? "eje" : "rejilla-linea", x1: m.izquierda, x2: ancho - m.derecha, y1: y(v), y2: y(v) }));
    capas.push(svg("text", { class: "tick", x: m.izquierda - 8, y: y(v) + 4, "text-anchor": "end", text: formato(v) }));
  }
  const cada = Math.ceil(n / 8);
  for (let i = 0; i < n; i += cada) capas.push(svg("text", { class: "tick", x: x(i), y: alto - 8, "text-anchor": "middle", text: etiquetaX(i) }));
  for (const serie of series) {
    const d = serie.valores.map((v, i) => `${i ? "L" : "M"}${x(i).toFixed(1)},${y(v).toFixed(1)}`).join("");
    capas.push(svg("path", { d, fill: "none", stroke: serie.color, "stroke-width": 2, "stroke-linejoin": "round", "stroke-linecap": "round" }));
    const ultimo = serie.valores.length - 1;
    capas.push(svg("circle", { cx: x(ultimo), cy: y(serie.valores[ultimo]), r: 4, fill: serie.color, stroke: "var(--papel)", "stroke-width": 2 }));
  }
  // Retícula vertical que sigue al puntero y muestra todas las series.
  const tip = crearTooltip(contenedor);
  const guia = svg("line", { class: "guia", y1: m.arriba, y2: alto - m.abajo, visibility: "hidden" });
  const zona = svg("rect", { x: m.izquierda, y: m.arriba, width: ancho - m.izquierda - m.derecha, height: alto - m.arriba - m.abajo, fill: "transparent" });
  zona.addEventListener("pointermove", (evento) => {
    const caja = zona.getBoundingClientRect();
    const i = Math.max(0, Math.min(n - 1, Math.round(((evento.clientX - caja.left) / caja.width) * (n - 1))));
    guia.setAttribute("x1", x(i)); guia.setAttribute("x2", x(i)); guia.setAttribute("visibility", "visible");
    tip.mostrar(x(i), m.arriba + 10, `Época ${etiquetaX(i)}`, series.map((s) => [s.color, s.nombre, formato(s.valores[i] ?? 0)]));
  });
  zona.addEventListener("pointerleave", () => { guia.setAttribute("visibility", "hidden"); tip.ocultar(); });
  capas.push(guia, zona);
  const tipActual = contenedor.querySelector(".tooltip");
  vaciar(contenedor, svg("svg", { viewBox: `0 0 ${ancho} ${alto}`, width: ancho, height: alto, role: "img" }, ...capas), tipActual);
}

/** Dos histogramas sobre los mismos rangos (bordes) y una línea vertical para el umbral. */
export function histogramaDoble(contenedor, bordes, grupos, umbral, { alto = 240 } = {}) {
  const ancho = Math.max(320, contenedor.clientWidth);
  const m = { arriba: 22, derecha: 10, abajo: 30, izquierda: 40 };
  const bandas = bordes.length - 1;
  const maximo = Math.max(1, ...grupos.flatMap((g) => g.valores));
  const paso = pasoLimpio(maximo);
  const tope = Math.ceil(maximo / paso) * paso;
  const anchoBanda = (ancho - m.izquierda - m.derecha) / bandas;
  const y = (v) => m.arriba + (alto - m.arriba - m.abajo) * (1 - v / tope);
  const xLog = (valor) => {
    const a = Math.log10(bordes[0]);
    const b = Math.log10(bordes[bandas]);
    return m.izquierda + ((Math.log10(valor) - a) / (b - a)) * (ancho - m.izquierda - m.derecha);
  };
  const capas = [];
  for (let v = 0; v <= tope; v += paso) {
    capas.push(svg("line", { class: v === 0 ? "eje" : "rejilla-linea", x1: m.izquierda, x2: ancho - m.derecha, y1: y(v), y2: y(v) }));
    capas.push(svg("text", { class: "tick", x: m.izquierda - 8, y: y(v) + 4, "text-anchor": "end", text: numero(v) }));
  }
  const tip = crearTooltip(contenedor);
  const grosor = Math.max(2, Math.min(12, (anchoBanda - 4) / grupos.length));
  for (let i = 0; i < bandas; i++) {
    grupos.forEach((g, j) => {
      const v = g.valores[i];
      if (!v) return;
      const x0 = m.izquierda + anchoBanda * i + (anchoBanda - grosor * grupos.length - 2 * (grupos.length - 1)) / 2 + j * (grosor + 2);
      const barra = svg("path", { class: "marca-hover", d: rutaBarra(x0, y(v), grosor, alto - m.abajo - y(v)), fill: g.color, tabindex: "0",
        "aria-label": `${g.nombre}: ${v} con error entre ${numero(bordes[i], 3)} y ${numero(bordes[i + 1], 3)}` });
      const mostrar = () => tip.mostrar(x0, y(v), `Error ${numero(bordes[i], 3)} – ${numero(bordes[i + 1], 3)}`, [[g.color, g.nombre, numero(v)]]);
      barra.addEventListener("pointerenter", mostrar);
      barra.addEventListener("focus", mostrar);
      barra.addEventListener("pointerleave", () => tip.ocultar());
      capas.push(barra);
    });
  }
  for (const marca of [bordes[0], umbral, bordes[bandas]]) {
    capas.push(svg("text", { class: "tick", x: xLog(marca), y: alto - 10, "text-anchor": "middle", text: numero(marca, 2) }));
  }
  const xu = xLog(umbral);
  capas.push(svg("line", { x1: xu, x2: xu, y1: m.arriba - 6, y2: alto - m.abajo, stroke: "var(--tinta)", "stroke-width": 1.5 }));
  capas.push(svg("text", { class: "valor", x: xu + 6, y: m.arriba + 4, text: "Umbral" }));
  const tipActual = contenedor.querySelector(".tooltip");
  vaciar(contenedor, svg("svg", { viewBox: `0 0 ${ancho} ${alto}`, width: ancho, height: alto, role: "img" }, ...capas), tipActual);
}

/**
 * Líneas sobre ejes X e Y numéricos, con huecos (y = null) y escala
 * logarítmica opcional (el benchmark usa log-log: una recta de pendiente 2 es O(n²)).
 * series: [{nombre, color, puntos: [{x, y}], punteada}]
 */
export function serieXY(contenedor, series, { alto = 260, logX = false, logY = false, formatoX = (v) => numero(v),
  formatoY = (v) => numero(v), tituloTip = (x) => formatoX(x), ticksX } = {}) {
  const ancho = Math.max(320, contenedor.clientWidth);
  const m = { arriba: 16, derecha: 14, abajo: 30, izquierda: 58 };
  const puntos = series.flatMap((s) => s.puntos.filter((p) => p.y !== null && p.y !== undefined));
  if (!puntos.length) return vaciar(contenedor, el("p", { class: "muted", text: "Sin datos." }));
  const fx = logX ? Math.log10 : (v) => v;
  const fy = logY ? Math.log10 : (v) => v;
  const xs = puntos.map((p) => fx(p.x));
  const ys = puntos.map((p) => fy(Math.max(p.y, logY ? 1e-6 : -Infinity)));
  let [xmin, xmax] = [Math.min(...xs), Math.max(...xs)];
  let [ymin, ymax] = [logY ? Math.floor(Math.min(...ys)) : Math.min(0, ...ys), Math.max(...ys)];
  if (logY) ymax = Math.ceil(ymax);
  if (xmax === xmin) xmax = xmin + 1;
  if (ymax === ymin) ymax = ymin + 1;
  const x = (v) => m.izquierda + ((fx(v) - xmin) / (xmax - xmin)) * (ancho - m.izquierda - m.derecha);
  const y = (v) => m.arriba + (alto - m.arriba - m.abajo) * (1 - (fy(Math.max(v, logY ? 1e-6 : -Infinity)) - ymin) / (ymax - ymin));
  const capas = [];
  const marcasY = [];
  if (logY) for (let e = ymin; e <= ymax; e++) marcasY.push(10 ** e);
  else { const paso = pasoLimpio(ymax - ymin); for (let v = Math.ceil(ymin / paso) * paso; v <= ymax + 1e-9; v += paso) marcasY.push(v); }
  for (const v of marcasY) {
    capas.push(svg("line", { class: "rejilla-linea", x1: m.izquierda, x2: ancho - m.derecha, y1: y(v), y2: y(v) }));
    capas.push(svg("text", { class: "tick", x: m.izquierda - 8, y: y(v) + 4, "text-anchor": "end", text: formatoY(v) }));
  }
  const unicos = [...new Set(puntos.map((p) => p.x))].sort((a, b) => a - b);
  const marcasX = ticksX || unicos.filter((_, i) => i % Math.ceil(unicos.length / 7) === 0);
  for (const v of marcasX) capas.push(svg("text", { class: "tick", x: x(v), y: alto - 8, "text-anchor": "middle", text: formatoX(v) }));
  capas.push(svg("line", { class: "eje", x1: m.izquierda, x2: ancho - m.derecha, y1: alto - m.abajo, y2: alto - m.abajo }));
  for (const serie of series) {
    let d = "";
    let abierto = false;
    for (const p of serie.puntos) {
      if (p.y === null || p.y === undefined) { abierto = false; continue; }
      d += `${abierto ? "L" : "M"}${x(p.x).toFixed(1)},${y(p.y).toFixed(1)}`;
      abierto = true;
    }
    capas.push(svg("path", { d, fill: "none", stroke: serie.color, "stroke-width": 2.2, "stroke-linejoin": "round",
      "stroke-linecap": "round", "stroke-dasharray": serie.punteada ? "6 5" : null }));
    for (const p of serie.puntos) {
      if (p.y !== null && p.y !== undefined && serie.marcas !== false) {
        capas.push(svg("circle", { cx: x(p.x), cy: y(p.y), r: 3, fill: serie.color, stroke: "var(--papel)", "stroke-width": 1.5 }));
      }
    }
  }
  const tip = crearTooltip(contenedor);
  const guia = svg("line", { class: "guia", y1: m.arriba, y2: alto - m.abajo, visibility: "hidden" });
  const zona = svg("rect", { x: m.izquierda, y: m.arriba, width: ancho - m.izquierda - m.derecha, height: alto - m.arriba - m.abajo, fill: "transparent" });
  zona.addEventListener("pointermove", (evento) => {
    const caja = zona.getBoundingClientRect();
    const px = m.izquierda + ((evento.clientX - caja.left) / caja.width) * (ancho - m.izquierda - m.derecha);
    const cercano = unicos.reduce((a, b) => (Math.abs(x(b) - px) < Math.abs(x(a) - px) ? b : a));
    guia.setAttribute("x1", x(cercano)); guia.setAttribute("x2", x(cercano)); guia.setAttribute("visibility", "visible");
    const filas = series.map((s) => [s.color, s.nombre, s.puntos.find((p) => p.x === cercano)?.y])
      .filter((f) => f[2] !== null && f[2] !== undefined).map(([c, n, v]) => [c, n, formatoY(v)]);
    tip.mostrar(x(cercano), m.arriba + 10, tituloTip(cercano), filas);
  });
  zona.addEventListener("pointerleave", () => { guia.setAttribute("visibility", "hidden"); tip.ocultar(); });
  capas.push(guia, zona);
  const tipActual = contenedor.querySelector(".tooltip");
  vaciar(contenedor, svg("svg", { viewBox: `0 0 ${ancho} ${alto}`, width: ancho, height: alto, role: "img" }, ...capas), tipActual);
}

/**
 * Diagramas de caja horizontales (cuartiles). grupos: [{nombre, color, perfil:
 * {minimo, q1, mediana, q3, maximo, cerca_superior}, atipicos: [], marca: valor a resaltar}]
 */
export function cajas(contenedor, grupos, { formato = (v) => numero(v), log = false } = {}) {
  const ancho = Math.max(320, contenedor.clientWidth);
  const etiqueta = Math.min(130, ancho * 0.3);
  const fila = 58;
  const alto = grupos.length * fila + 30;
  const valores = grupos.flatMap((g) => [g.perfil.minimo, g.perfil.maximo, g.marca ?? g.perfil.minimo]).filter((v) => v > 0 || !log);
  const f = log ? Math.log10 : (v) => v;
  const [a, b] = [f(Math.min(...valores)), f(Math.max(...valores))];
  const x = (v) => etiqueta + 10 + ((f(Math.max(v, log ? 1 : -Infinity)) - a) / Math.max(b - a, 1e-9)) * (ancho - etiqueta - 30);
  const capas = [];
  grupos.forEach((g, i) => {
    const p = g.perfil;
    const yc = i * fila + 26;
    const tope = Math.min(p.maximo, p.cerca_superior);
    capas.push(
      svg("text", { class: "etiqueta-barra", x: etiqueta, y: yc + 4, "text-anchor": "end", text: g.nombre }),
      svg("line", { x1: x(p.minimo), x2: x(tope), y1: yc, y2: yc, stroke: "var(--tinta-3)", "stroke-width": 1.5 }),
      svg("line", { x1: x(p.minimo), x2: x(p.minimo), y1: yc - 8, y2: yc + 8, stroke: "var(--tinta-3)", "stroke-width": 1.5 }),
      svg("line", { x1: x(tope), x2: x(tope), y1: yc - 8, y2: yc + 8, stroke: "var(--tinta-3)", "stroke-width": 1.5 }),
      svg("rect", { x: x(p.q1), y: yc - 13, width: Math.max(2, x(p.q3) - x(p.q1)), height: 26, rx: 4, fill: g.color, "fill-opacity": 0.22,
        stroke: g.color, "stroke-width": 1.5 }),
      svg("line", { x1: x(p.mediana), x2: x(p.mediana), y1: yc - 13, y2: yc + 13, stroke: g.color, "stroke-width": 3 }),
      svg("line", { x1: x(p.cerca_superior), x2: x(p.cerca_superior), y1: yc - 18, y2: yc + 18, stroke: "var(--critico)",
        "stroke-width": 1, "stroke-dasharray": "3 3" }));
    for (const atipico of g.atipicos || []) {
      capas.push(svg("circle", { cx: x(atipico), cy: yc, r: 4, fill: "var(--papel)", stroke: "var(--critico)", "stroke-width": 1.5 }));
    }
    if (g.marca !== undefined && g.marca !== null) {
      capas.push(svg("path", { d: `M${x(g.marca)},${yc - 20} l-6,-9 h12 z`, fill: "var(--tinta)" }));
      capas.push(svg("text", { class: "valor", x: x(g.marca), y: yc - 31, "text-anchor": "middle", text: formato(g.marca) }));
    }
    capas.push(svg("text", { class: "tick", x: x(p.q1), y: yc + 28, "text-anchor": "middle", text: `Q1 ${formato(p.q1)}` }),
      svg("text", { class: "tick", x: x(p.q3), y: yc + 28, "text-anchor": "middle", text: `Q3 ${formato(p.q3)}` }));
  });
  vaciar(contenedor, svg("svg", { viewBox: `0 0 ${ancho} ${alto}`, width: ancho, height: alto, role: "img",
    "aria-label": grupos.map((g) => `${g.nombre}: Q1 ${formato(g.perfil.q1)}, mediana ${formato(g.perfil.mediana)}, Q3 ${formato(g.perfil.q3)}`).join(". ") }, ...capas));
}
