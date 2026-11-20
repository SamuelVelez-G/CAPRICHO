/* Panel: ventas, predicción de demanda, alertas, calidad, modelos y benchmark. */

import { api, dinero, el, fechaCorta, insignia, nivel, numero, toast, vaciar } from "./comun.js";
import { barrasHorizontales, serieXY } from "./graficas.js";
import { barraPct, css, kpi, leyenda, pct, tablaDatos } from "./ui.js";

const DIAS = ["dom", "lun", "mar", "mié", "jue", "vie", "sáb"];
const fechaDia = (iso) => { const d = new Date(`${iso}T12:00:00`); return `${DIAS[d.getDay()]} ${d.getDate()}`; };
const pesosCortos = (v) => (Math.abs(v) >= 1e6 ? `$${numero(v / 1e6, 1)} M` : `$${numero(v / 1000, 0)} mil`);

async function ventas() {
  const { ok, datos } = await api("GET", "/api/ventas?dias=30");
  if (!ok) return toast(datos.error, "error");
  const v = datos;
  vaciar(document.getElementById("panel-kpis"),
    kpi("Ventas 30 días", dinero(v.actual.ventas), v.variacion === null ? "" : `${v.variacion >= 0 ? "+" : ""}${numero(v.variacion, 1)} % frente a los 30 anteriores`, "grafico"),
    kpi("Ventas de hoy", dinero(v.hoy.ventas), `${numero(v.hoy.facturas)} facturas`, "reloj"),
    kpi("Ticket típico", dinero(v.ticket?.mediana || 0), v.ticket ? `Q1 ${dinero(v.ticket.q1)} · Q3 ${dinero(v.ticket.q3)}` : "", "carrito"),
    kpi("Facturas 30 días", numero(v.actual.facturas), `impuesto al consumo ${dinero(v.actual.impuesto)}`, "tabla"),
    kpi("Descuentos 30 días", dinero(v.actual.descuentos), "quién los da: ver Estadística", "alerta"));

  // Serie: x = índice de día. Lo real, la tendencia (regresión) y las dos predicciones.
  const serie = v.serie;
  const n = serie.length;
  const reales = serie.map((d, i) => ({ x: i, y: i === n - 1 ? null : d.ventas }));     // hoy todavía no termina
  const tendencia = v.tendencia.ajuste.map((y, i) => ({ x: i, y }));
  const lineal = [{ x: n - 2, y: serie[n - 2].ventas }, ...v.tendencia.prediccion.map((p, i) => ({ x: n - 1 + i, y: p.ventas }))];
  const red = v.prediccion_red ? [{ x: n - 2, y: serie[n - 2].ventas }, ...v.prediccion_red.map((p, i) => ({ x: n - 1 + i, y: p.ventas }))] : [];
  const etiquetas = [...serie.map((d) => d.dia), ...v.tendencia.prediccion.map((p) => p.dia)];
  const series = [
    { nombre: "Ventas reales", color: css("--serie-1"), puntos: reales },
    { nombre: "Tendencia (regresión lineal)", color: css("--tinta-3"), puntos: tendencia, punteada: true, marcas: false },
    { nombre: "Predicción: regresión lineal", color: css("--serie-2"), puntos: lineal, punteada: true },
  ];
  if (red.length) series.push({ nombre: "Predicción: red de Keras", color: css("--serie-3"), puntos: red });
  vaciar(document.getElementById("leyenda-ventas"), leyenda(series.map((s) => [s.nombre, s.color, s.punteada])));
  serieXY(document.getElementById("g-ventas"), series, {
    alto: 300, formatoX: (i) => fechaDia(etiquetas[i] || etiquetas.at(-1)), formatoY: pesosCortos, tituloTip: (i) => etiquetas[i] || "",
  });
  const m = v.modelo_demanda;
  document.getElementById("nota-demanda").textContent = `${v.tendencia.lectura} (R² = ${numero(v.tendencia.r2, 2)}).` +
    (m ? ` Error promedio por día en 4 semanas de prueba: red ${dinero(m.red)}, regresión lineal ${dinero(m.regresion_lineal)}, `
      + `"igual que la semana pasada" ${dinero(m.semana_pasada)}.` : " La red de demanda no está entrenada.");

  const nombresCanal = { PRESENCIAL: "Caja", WEB: "Web", APP: "App", DOMICILIO: "Domicilio" };
  barrasHorizontales(document.getElementById("g-canal"), v.por_canal.map((c) => ({ etiqueta: nombresCanal[c.canal] || c.canal, valor: c.ventas })),
    { formato: pesosCortos, extra: (f) => "" });
  serieXY(document.getElementById("g-hora"), [{ nombre: "Ventas", color: css("--serie-1"), puntos: v.por_hora.map((y, x) => ({ x, y })) }],
    { alto: 220, formatoX: (h) => `${h}h`, formatoY: pesosCortos, ticksX: [6, 9, 12, 15, 18, 21] });
  barrasHorizontales(document.getElementById("g-semana"), v.por_dia_semana.map((d) => ({ etiqueta: d.dia, valor: d.promedio })),
    { formato: pesosCortos });

  vaciar(document.getElementById("t-ranking"), tablaDatos([
    { titulo: "#", valor: (f) => String(v.ranking.indexOf(f) + 1) },
    { titulo: "Ítem", valor: (f) => f.nombre },
    { titulo: "Unidades", valor: (f) => numero(f.unidades), num: true },
    { titulo: "Ventas", valor: (f) => dinero(f.ventas), num: true },
  ], v.ranking));
  vaciar(document.getElementById("t-inventario"), tablaDatos([
    { titulo: "Ítem", valor: (f) => f.nombre },
    { titulo: "Categoría", valor: (f) => f.categoria },
    { titulo: "Stock", valor: (f) => numero(f.stock), num: true },
    { titulo: "Mínimo", valor: (f) => numero(f.stock_minimo), num: true },
    { titulo: "", valor: (f) => (f.stock <= f.stock_minimo ? insignia("RECHAZADO") : insignia("PENDIENTE")) },
  ], v.inventario_bajo, "Todo el inventario está por encima del doble del mínimo."));
}

async function alertas() {
  const { ok, datos } = await api("GET", "/api/alertas?limite=8");
  if (!ok) return;
  vaciar(document.getElementById("t-alertas"), tablaDatos([
    { titulo: "Cuándo", valor: (a) => fechaCorta(a.fecha) },
    { titulo: "Nivel", valor: (a) => nivel(a.nivel) },
    { titulo: "Qué pasó", valor: (a) => el("span", {}, el("strong", { text: a.descripcion }), el("br"), el("span", { class: "muted", text: a.detalle })) },
  ], datos.alertas, "Sin alertas."), el("p", { class: "nota", text: `${numero(datos.resumen.total)} alertas en total, ${numero(datos.resumen.nuevas)} sin revisar.` }));
}

async function calidad() {
  const { ok, datos } = await api("GET", "/api/calidad/auditoria");
  if (!ok) return;
  const a = datos.auditoria;
  vaciar(document.getElementById("resumen-calidad"),
    el("p", { class: "cifra", text: `${numero(a.puntaje, 1)} / 100` }),
    tablaDatos([{ titulo: "Dimensión", valor: (d) => d[0] }, { titulo: "", valor: (d) => barraPct(d[1] / 100, d[1] >= 95 ? "barra-pct--ok" : "") }],
      Object.entries(a.dimensiones).map(([k, val]) => [k[0].toUpperCase() + k.slice(1), val])),
    el("p", { class: "nota", text: `${a.problemas.length} problemas encontrados, ${a.automaticos} se pueden corregir solos.` }));
}

async function modelos() {
  const { ok, datos } = await api("GET", "/api/ia/estado");
  const caja = document.getElementById("resumen-modelos");
  if (!ok || !datos.disponible) return vaciar(caja, el("p", { class: "muted", text: "Los modelos no están entrenados (python herramientas/entrenar_modelos.py --todo)." }));
  const c = datos.modelos.clasificador;
  const filas = [];
  if (c) {
    const comp = c.comparacion;
    filas.push(["Clasificador: detecta", barraPct(comp.clasificador.todos.recall, "barra-pct--ok")],
      ["Clasificador: acierta cuando alerta", barraPct(comp.clasificador.todos.precision, "barra-pct--ok")],
      ["Clientes nuevos: detecta", barraPct(comp.clasificador.clientes_nuevos.recall, "barra-pct--ok")],
      ["Reglas de la 1.ª entrega: detectan", barraPct(comp.reglas.todos.recall)]);
  }
  const mo = datos.modelos.monto;
  if (mo) filas.push(["Monto esperado: error típico", el("span", { text: `${numero(mo.error_mediano.red, 1)} % (mediana del cliente: ${numero(mo.error_mediano.mediana, 1)} %)` })]);
  vaciar(caja, tablaDatos([{ titulo: "Métrica (días que la red no vio)", valor: (f) => f[0] }, { titulo: "", valor: (f) => f[1] }], filas),
    el("p", { class: "nota", text: `Motor: ${datos.motor}. Precisión = de lo que marcó, cuánto era fraude; detecta (recall) = de los fraudes, cuántos encontró.` }));
}

async function bench() {
  const { ok, datos } = await api("GET", "/api/benchmark");
  const caja = document.getElementById("resumen-benchmark");
  if (!ok || !datos.benchmark) return vaciar(caja, el("p", { class: "muted", text: "Todavía no se ha corrido el benchmark (página Algoritmos)." }));
  const b = datos.benchmark;
  vaciar(caja, tablaDatos([
    { titulo: "Problema", valor: (p) => p.titulo },
    { titulo: "Mejora", valor: (p) => (p.mejora ? `${numero(p.mejora.veces, 0)}× (${p.mejora.lenta_complejidad} → ${p.mejora.rapida_complejidad})` : "—") },
  ], b.problemas), el("p", { class: "nota", text: `Benchmark ${b.tipo.toLowerCase()} del ${fechaCorta(b.fecha)} · ${b.equipo}.` }));
}

ventas();
alertas();
calidad();
modelos();
bench();
