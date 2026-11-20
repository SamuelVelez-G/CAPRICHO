/* Algoritmos: resultados del benchmark (gráfica log-log, tablas y conclusiones). */

import { api, el, fechaCorta, numero, toast, vaciar } from "./comun.js";
import { serieXY } from "./graficas.js";
import { css, etiqueta, kpi, leyenda, ms, tablaDatos } from "./ui.js";

const COLORES = ["--serie-1", "--serie-2", "--serie-3", "--caramelo", "--tinta-3"];
const TONO = { "O(1)": "ok", "O(log n)": "ok", "O(n)": "ok", "O(n log n)": "vino", "O(n²)": "critico" };
let benchmark = null;
let actual = null;

function tiempo(p) {
  if (!p) return "—";
  return p.omitido ? `~${ms(p.estimado_ms)} (estimado)` : ms(p.ms);
}

function mostrarProblema(clave) {
  actual = clave;
  const problema = benchmark.problemas.find((p) => p.clave === clave);
  document.querySelectorAll("#selector button").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.clave === clave)));
  document.getElementById("titulo-problema").textContent = problema.titulo;
  document.getElementById("descripcion-problema").textContent = `${problema.descripcion} ${problema.verificado
    ? "Todas las variantes dieron exactamente el mismo resultado." : "¡Las variantes NO coinciden!"}`;
  const series = [];
  problema.variantes.forEach((v, i) => {
    const color = css(COLORES[i % COLORES.length]);
    const medidos = v.puntos.filter((p) => !p.omitido).map((p) => ({ x: p.n, y: Math.max(p.ms, 0.0005) }));
    series.push({ nombre: `${v.nombre} · ${v.complejidad}`, color, puntos: medidos });
    const ultimo = medidos.at(-1);
    const estimados = v.puntos.filter((p) => p.omitido).map((p) => ({ x: p.n, y: p.estimado_ms }));
    if (estimados.length && ultimo) series.push({ nombre: `${v.nombre} (estimado)`, color, punteada: true, puntos: [ultimo, ...estimados] });
  });
  vaciar(document.getElementById("leyenda-bench"), leyenda(series.filter((s) => !s.punteada).map((s) => [s.nombre, s.color])));
  serieXY(document.getElementById("g-bench"), series, { alto: 320, logX: true, logY: true, formatoX: (n) => numero(n),
    formatoY: ms, tituloTip: (n) => `n = ${numero(n)}`, ticksX: benchmark.tamanos });
  vaciar(document.getElementById("t-bench"), tablaDatos([
    { titulo: "Variante", valor: (v) => el("span", {}, v.nombre, " ", etiqueta(v.complejidad, TONO[v.complejidad])) },
    ...benchmark.tamanos.map((n) => ({ titulo: `n = ${numero(n)}`, valor: (v) => tiempo(v.puntos.find((p) => p.n === n)), num: true })),
    { titulo: "Operaciones (n mayor contado)", valor: (v) => { const p = [...v.puntos].reverse().find((x) => x.ops); return p ? `${numero(p.ops)} con n = ${numero(p.n)}` : "—"; } },
  ], problema.variantes));
  const m = problema.mejora;
  document.querySelector("#conclusion span").textContent = m ? `Con n = ${numero(m.n)}: ${m.rapida} (${m.rapida_complejidad}) tarda ${ms(m.rapida_ms)} `
    + `y ${m.lenta} (${m.lenta_complejidad}) ${m.estimado ? "tardaría unos" : "tarda"} ${ms(m.lenta_ms)}: ${numero(m.veces, 0)} veces más.` : "";
}

function pintar() {
  document.getElementById("sin-benchmark").hidden = Boolean(benchmark);
  if (!benchmark) return;
  const mejor = benchmark.problemas.filter((p) => p.mejora).sort((a, b) => b.mejora.veces - a.mejora.veces)[0];
  vaciar(document.getElementById("bench-kpis"),
    kpi("Problemas", numero(benchmark.problemas.length), `${benchmark.problemas.reduce((s, p) => s + p.variantes.length, 0)} variantes`, "tabla"),
    kpi("Resultados iguales", benchmark.problemas.every((p) => p.verificado) ? "Todos" : "¡No!", "cada variante da lo mismo", "ok", "kpi--ok"),
    kpi("Tamaño mayor", numero(Math.max(...benchmark.tamanos)), "datos del sistema replicados", "grafico"),
    kpi("Mayor mejora", mejor ? `${numero(mejor.mejora.veces, 0)}×` : "—", mejor ? mejor.titulo : "", "rayo"),
    kpi("Medido", fechaCorta(benchmark.fecha), `${benchmark.tipo.toLowerCase()} · ${numero(benchmark.duracion_s, 1)} s`, "reloj"));
  vaciar(document.getElementById("selector"), ...benchmark.problemas.map((p) => el("button", {
    class: "boton boton--xs boton--contorno", type: "button", dataset: { clave: p.clave }, text: p.titulo, onClick: () => mostrarProblema(p.clave) })));
  mostrarProblema(actual && benchmark.problemas.some((p) => p.clave === actual) ? actual : benchmark.problemas[0].clave);
  const filas = benchmark.problemas.flatMap((p) => p.variantes.map((v) => ({ ...v, problema: p.titulo })));
  vaciar(document.getElementById("t-teoria"), tablaDatos([
    { titulo: "Problema", valor: (v) => v.problema },
    { titulo: "Variante", valor: (v) => v.nombre },
    { titulo: "Teoría", valor: (v) => etiqueta(v.complejidad, TONO[v.complejidad]) },
    { titulo: "Pendiente medida", valor: (v) => (v.pendiente === null ? "—" : numero(v.pendiente, 2)), num: true },
    { titulo: "R²", valor: (v) => (v.r2 === null ? "—" : numero(v.r2, 3)), num: true },
    { titulo: "Lo que se observa", valor: (v) => v.observado },
  ], filas));
  const critico = benchmark.problemas.find((p) => p.clave === "ventana");
  if (critico) {
    vaciar(document.getElementById("t-critico"), tablaDatos([
      { titulo: "Variante", valor: (v) => `${v.nombre} · ${v.complejidad}` },
      ...benchmark.tamanos.slice(-3).map((n) => ({ titulo: `n = ${numero(n)}`, valor: (v) => tiempo(v.puntos.find((p) => p.n === n)), num: true })),
    ], critico.variantes));
  }
}

async function cargar() {
  const { ok, datos } = await api("GET", "/api/benchmark");
  if (!ok) return toast(datos.error, "error");
  benchmark = datos.benchmark;
  pintar();
}

document.getElementById("correr")?.addEventListener("click", async (evento) => {
  const boton = evento.currentTarget;
  boton.disabled = true;
  boton.lastChild.textContent = " Midiendo…";
  const { ok, datos } = await api("POST", "/api/benchmark");
  boton.disabled = false;
  boton.lastChild.textContent = " Correr benchmark rápido";
  if (!ok) return toast(datos.error, "error");
  benchmark = datos.benchmark;
  toast(`Medido en ${numero(benchmark.duracion_s, 1)} s`, "ok");
  pintar();
});

cargar();
