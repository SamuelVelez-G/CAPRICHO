/*
 * Perfil estadístico por usuario. El servidor manda los datos crudos y su
 * propio cálculo (Python); aquí se recalcula con la librería Simple Statistics
 * (static/js/vendor/simple-statistics.mjs, versión 7.8.8) y se comparan.
 */

import * as ss from "./vendor/simple-statistics.mjs";
import { api, dinero, el, numero, toast, vaciar } from "./comun.js";
import { cajas, serieXY } from "./graficas.js";
import { css, etiqueta, kpi, leyenda, pct, tablaDatos } from "./ui.js";

let usuarioActual = null;

/** Lo mismo que capricho/servicios/estadistica.py, pero con Simple Statistics. */
function perfilJS(valores) {
  const ordenados = [...valores].sort((a, b) => a - b);
  const q1 = ss.quantileSorted(ordenados, 0.25);
  const q3 = ss.quantileSorted(ordenados, 0.75);
  const iqr = q3 - q1;
  return { n: ordenados.length, media: ss.mean(ordenados), desviacion: ss.standardDeviation(ordenados), minimo: ordenados[0],
    q1, mediana: ss.quantileSorted(ordenados, 0.5), q3, maximo: ordenados.at(-1), iqr, cerca_superior: q3 + 1.5 * iqr };
}

const iguales = (a, b) => Math.abs(a - b) <= 1e-6 * Math.max(1, Math.abs(a), Math.abs(b));

function comparar(servidor, navegador, ultimo) {
  const filas = [["Q1", "q1"], ["Mediana", "mediana"], ["Q3", "q3"], ["IQR (Q3 − Q1)", "iqr"], ["Media", "media"],
    ["Desviación", "desviacion"], ["Cerca superior", "cerca_superior"]].map(([nombre, clave]) => ({
    nombre, python: servidor[clave], js: navegador[clave], ok: iguales(servidor[clave], navegador[clave]) }));
  if (ultimo !== undefined) {
    const zPy = servidor.desviacion ? (ultimo - servidor.media) / servidor.desviacion : 0;
    const zJs = navegador.desviacion ? ss.zScore(ultimo, navegador.media, navegador.desviacion) : 0;
    filas.push({ nombre: `z de su última compra (${dinero(ultimo)})`, python: zPy, js: zJs, ok: iguales(zPy, zJs), z: true });
  }
  const todos = filas.every((f) => f.ok);
  return el("div", {},
    tablaDatos([
      { titulo: "Medida", valor: (f) => f.nombre },
      { titulo: "Python (servidor)", valor: (f) => (f.z ? numero(f.python, 4) : dinero(f.python)), num: true },
      { titulo: "Simple Statistics (navegador)", valor: (f) => (f.z ? numero(f.js, 4) : dinero(f.js)), num: true },
      { titulo: "", valor: (f) => etiqueta(f.ok ? "coinciden" : "distintos", f.ok ? "ok" : "critico") },
    ], filas),
    el("p", { class: "nota", text: todos ? "Las dos implementaciones dan exactamente lo mismo." : "Hay diferencias: revisar el método de cuartiles." }));
}

async function cargarUsuarios(busqueda = "") {
  const { ok, datos } = await api("GET", `/api/estadistica/usuarios?q=${encodeURIComponent(busqueda)}`);
  if (!ok) return toast(datos.error, "error");
  vaciar(document.getElementById("usuarios"), ...datos.usuarios.map((u) => el("button", { type: "button", dataset: { id: u.id },
    "aria-pressed": String(u.id === usuarioActual), onClick: () => perfil(u.id) },
    el("strong", { text: u.nombre }), el("small", { text: `${u.rol.toLowerCase()} · ${u.transacciones} transacciones · ${u.email}` }))));
  if (usuarioActual === null) {
    const conDatos = datos.usuarios.find((u) => u.rol === "CLIENTE" && u.transacciones >= 20 && !u.email.startsWith("consumidor"));
    if (conDatos) perfil(conDatos.id);
  }
}

async function perfil(id) {
  usuarioActual = id;
  document.querySelectorAll("#usuarios button").forEach((b) => b.setAttribute("aria-pressed", String(Number(b.dataset.id) === id)));
  const { ok, datos } = await api("GET", `/api/estadistica/usuarios/${id}`);
  if (!ok) return toast(datos.error, "error");
  const p = datos.perfil;
  document.getElementById("perfil-titulo").textContent = p.usuario.nombre;
  document.getElementById("perfil-sub").textContent = `${p.usuario.email} · ${p.usuario.rol.toLowerCase()} · ${p.montos.length} montos`
    + (p.usa_poblacion ? " · tiene menos de 5 compras: sus operaciones se comparan con la población" : "");
  const r = p.perfil;
  vaciar(document.getElementById("perfil-kpis"), r ? [
    kpi("Compras", numero(r.n), "últimas 200", "carrito"),
    kpi("Mediana", dinero(r.mediana), `media ${dinero(r.media)}`, "grafico"),
    kpi("Q1 – Q3", `${dinero(r.q1)} – ${dinero(r.q3)}`, `IQR ${dinero(r.iqr)}`, "tabla"),
    kpi("Cerca superior", dinero(r.cerca_superior), "desde aquí es atípico", "alerta"),
    kpi("Atípicas", numero(p.atipicos.length), r.n ? `${pct(p.atipicos.length / r.n)} de sus compras` : "", "bloqueo"),
  ] : el("p", { class: "muted", text: "Sin compras registradas." }));
  const grupos = [];
  if (r) grupos.push({ nombre: "Este usuario", color: css("--serie-1"), perfil: r, atipicos: p.atipicos, marca: p.montos[0] });
  if (p.poblacion) grupos.push({ nombre: "Población", color: css("--serie-3"), perfil: p.poblacion });
  cajas(document.getElementById("g-cajas"), grupos, { formato: dinero, log: true });
  vaciar(document.getElementById("comparacion"), r ? comparar(r, perfilJS(p.montos), p.montos[0])
    : el("p", { class: "muted", text: "Sin datos para comparar." }));
  serieXY(document.getElementById("g-horas"), [{ nombre: "Compras", color: css("--serie-1"), puntos: p.por_hora.map((y, x) => ({ x, y })) }],
    { alto: 200, formatoX: (h) => `${h}h`, ticksX: [0, 6, 12, 18, 23] });
  vaciar(document.getElementById("t-metodos"), tablaDatos([
    { titulo: "Método", valor: (f) => f[0] }, { titulo: "Veces", valor: (f) => numero(f[1]), num: true },
    { titulo: "Proporción", valor: (f) => pct(f[1] / p.fechas.length) },
  ], Object.entries(p.por_metodo).sort((a, b) => b[1] - a[1])));

  const seccion = document.getElementById("seccion-empleado");
  seccion.hidden = !p.empleado;
  if (p.empleado) {
    const dias = p.empleado.por_dia;
    const cerca = (que) => p.empleado[que].poblacion?.cerca_superior ?? 0;
    const series = [
      { nombre: "Descuentos por factura", color: css("--serie-1"), puntos: dias.map((d, i) => ({ x: i, y: d.tasa_descuentos })) },
      { nombre: "Anulaciones por factura", color: css("--serie-2"), puntos: dias.map((d, i) => ({ x: i, y: d.tasa_anulaciones })) },
      { nombre: "Cerca superior de descuentos", color: css("--serie-1"), punteada: true, marcas: false, puntos: dias.map((_, i) => ({ x: i, y: cerca("descuentos") })) },
      { nombre: "Cerca superior de anulaciones", color: css("--serie-2"), punteada: true, marcas: false, puntos: dias.map((_, i) => ({ x: i, y: cerca("anulaciones") })) },
    ];
    vaciar(document.getElementById("leyenda-empleado"), leyenda(series.map((s) => [s.nombre, s.color, s.punteada])));
    serieXY(document.getElementById("g-empleado"), series, { alto: 240, formatoX: (i) => dias[i]?.dia.slice(5) ?? "",
      formatoY: (v) => pct(v, 0), tituloTip: (i) => `${dias[i]?.dia}: ${dias[i]?.facturas} facturas` });
  }
}

async function empleados() {
  const { ok, datos } = await api("GET", "/api/estadistica/empleados");
  if (!ok) return;
  vaciar(document.getElementById("t-empleados"), tablaDatos([
    { titulo: "Empleado", valor: (e) => e.nombre },
    { titulo: "Facturas", valor: (e) => numero(e.facturas), num: true },
    { titulo: "Con descuento", valor: (e) => `${numero(e.descuentos)} (${pct(e.tasa_descuentos)})`, num: true },
    { titulo: "z descuentos", valor: (e) => etiqueta(numero(e.z_tasa_descuentos, 2), e.z_tasa_descuentos >= 1.5 ? "critico" : "ok") },
    { titulo: "Anuladas", valor: (e) => `${numero(e.anulaciones)} (${pct(e.tasa_anulaciones)})`, num: true },
    { titulo: "z anulaciones", valor: (e) => etiqueta(numero(e.z_tasa_anulaciones, 2), e.z_tasa_anulaciones >= 1.5 ? "critico" : "ok") },
    { titulo: "Alertas", valor: (e) => numero(e.alertas), num: true },
  ], datos.empleados));
}

async function regresion() {
  const { ok, datos } = await api("GET", "/api/ventas?dias=30");
  if (!ok) return;
  const completos = datos.serie.slice(0, -1);
  const puntos = completos.map((d, i) => [i, d.ventas]);
  const { m, b } = ss.linearRegression(puntos);
  const recta = ss.linearRegressionLine({ m, b });
  const r2 = ss.rSquared(puntos, recta);
  const series = [
    { nombre: "Ventas reales", color: css("--serie-1"), puntos: puntos.map(([x, y]) => ({ x, y })) },
    { nombre: "Recta de Simple Statistics", color: css("--serie-3"), punteada: true, marcas: false, puntos: puntos.map(([x]) => ({ x, y: recta(x) })) },
  ];
  vaciar(document.getElementById("leyenda-regresion"), leyenda(series.map((s) => [s.nombre, s.color, s.punteada])));
  serieXY(document.getElementById("g-regresion"), series, { alto: 240, formatoX: (i) => completos[i]?.dia.slice(5) ?? "",
    formatoY: (v) => `$${numero(v / 1000, 0)} mil`, tituloTip: (i) => completos[i]?.dia ?? "" });
  const t = datos.tendencia;
  vaciar(document.getElementById("comparacion-regresion"), tablaDatos([
    { titulo: "Medida", valor: (f) => f[0] }, { titulo: "Python (servidor)", valor: (f) => f[1], num: true },
    { titulo: "Simple Statistics", valor: (f) => f[2], num: true }, { titulo: "", valor: (f) => etiqueta(f[3] ? "coinciden" : "distintos", f[3] ? "ok" : "critico") },
  ], [["Pendiente (pesos por día)", numero(t.pendiente, 1), numero(m, 1), Math.abs(t.pendiente - m) < 0.1],
    ["Intercepto", numero(t.intercepto, 1), numero(b, 1), Math.abs(t.intercepto - b) < 0.1],
    ["R²", numero(t.r2, 3), numero(r2, 3), Math.abs(t.r2 - r2) < 0.001],
    ["Predicción de mañana", dinero(t.prediccion[0].ventas), dinero(Math.max(0, recta(completos.length))),
      Math.abs(t.prediccion[0].ventas - Math.max(0, recta(completos.length))) < 1.5]]));
}

let espera;
document.getElementById("buscar-usuario").addEventListener("input", (evento) => {
  clearTimeout(espera);
  espera = setTimeout(() => cargarUsuarios(evento.target.value.trim()), 300);
});
cargarUsuarios();
empleados();
regresion();
