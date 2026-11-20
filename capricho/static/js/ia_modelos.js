/* Página de IA: clasificador, monto esperado y demanda (el autoencoder lo pinta ia.js). */

import { ESTATICO, api, dinero, el, numero, vaciar } from "./comun.js";
import { serieXY } from "./graficas.js";
import { barraPct, css, etiqueta, kpi, leyenda, ms, pct, tablaDatos } from "./ui.js";

const NOMBRES_DETECTOR = { reglas: "Reglas (1.ª entrega)", autoencoder: "Autoencoder (exposición)", clasificador: "Clasificador",
  reglas_y_clasificador: "Reglas + clasificador" };
const SEGMENTOS = { todos: "Todos", clientes_nuevos: "Clientes nuevos", con_historial: "Con historial" };

function resumen(m) {
  const tarjeta = (numeroModelo, titulo, pregunta, tipo, dato, nota) => el("article", { class: "tarjeta modelo-tarjeta" },
    el("p", { class: "eyebrow eyebrow--oscuro", text: `Modelo ${numeroModelo} · ${tipo}` }), el("h3", { text: titulo }),
    el("p", { class: "muted", text: pregunta }), el("p", { class: "cifra", text: dato }), el("p", { class: "nota", text: nota }));
  const c = m.clasificador;
  vaciar(document.getElementById("modelos-resumen"),
    c && tarjeta(1, "Clasificador", "¿Esta operación es normal o fraudulenta?", "supervisado",
      pct(c.comparacion.clasificador.todos.recall, 0), `de los fraudes detectados · ${pct(c.comparacion.clasificador.todos.precision, 0)} de precisión`),
    m.monto && tarjeta(2, "Monto esperado", "¿Cuánto debería pagar este cliente?", "regresión",
      `${numero(m.monto.error_mediano.red, 0)} %`, `error típico (mediana del cliente: ${numero(m.monto.error_mediano.mediana, 0)} %)`),
    m.autoencoder && tarjeta(3, "Autoencoder", "¿Se parece a los hábitos de ESTE cliente?", "sin etiquetas",
      `${numero(m.autoencoder.parametros)}`, "parámetros · el de la exposición"),
    m.demanda && tarjeta(4, "Demanda", "¿Cuánto se va a vender?", "series de tiempo",
      dinero(m.demanda.error_promedio.red), `error por día (regresión lineal: ${dinero(m.demanda.error_promedio.regresion_lineal)})`));
}

function clasificador(c) {
  const p = c.prueba;
  vaciar(document.getElementById("clasificador-kpis"),
    kpi("Detecta (recall)", pct(p.recall), `${p.matriz.verdaderos_positivos} de ${p.matriz.verdaderos_positivos + p.matriz.falsos_negativos} fraudes`, "escudo", "kpi--ok"),
    kpi("Precisión", pct(p.precision), "de lo que marca, es fraude", "ok"),
    kpi("F1", numero(p.f1, 3), `AUC-PR ${numero(c.auc_pr, 3)} · AUC-ROC ${numero(c.auc_roc, 3)}`, "grafico"),
    kpi("Falsas alarmas", pct(p.falsas_alarmas, 2), `${p.matriz.falsos_positivos} de ${numero(p.matriz.falsos_positivos + p.matriz.verdaderos_negativos)} legítimas`, "alerta"),
    kpi("La red", `${numero(c.parametros)} pesos`, `${numero(c.datos.total)} operaciones · ${c.motor}`, "matraz"));

  const filas = Object.entries(c.comparacion).flatMap(([detector, segmentos]) => Object.entries(segmentos).map(([seg, v]) => ({ detector, seg, ...v })));
  vaciar(document.getElementById("t-comparacion"), tablaDatos([
    { titulo: "Detector", valor: (f) => (f.seg === "todos" ? el("strong", { text: NOMBRES_DETECTOR[f.detector] }) : "") },
    { titulo: "Segmento", valor: (f) => (f.seg === "clientes_nuevos" ? etiqueta(SEGMENTOS[f.seg], "vino") : SEGMENTOS[f.seg]) },
    { titulo: "Fraudes", valor: (f) => numero(f.fraudes), num: true },
    { titulo: "Detecta", valor: (f) => barraPct(f.recall, f.detector.includes("clasificador") ? "barra-pct--ok" : "") },
    { titulo: "Precisión", valor: (f) => pct(f.precision), num: true },
    { titulo: "Falsas alarmas", valor: (f) => pct(f.falsas_alarmas, 2), num: true },
  ], filas));

  vaciar(document.getElementById("t-tipos"), tablaDatos([
    { titulo: "Operación", valor: (t) => el("span", {}, t.descripcion, " ", etiqueta(t.fraude ? "fraude" : "legítima", t.fraude ? "critico" : "ok")) },
    { titulo: "Casos", valor: (t) => numero(t.operaciones), num: true },
    { titulo: "Reglas", valor: (t) => pct(t.reglas, 0), num: true },
    { titulo: "Autoencoder", valor: (t) => (t.autoencoder === undefined ? "—" : pct(t.autoencoder, 0)), num: true },
    { titulo: "Clasificador", valor: (t) => el("strong", { class: (t.fraude ? t.clasificador >= 0.8 : t.clasificador <= 0.02) ? "texto-ok" : "texto-critico", text: pct(t.clasificador, 0) }), num: true },
  ], Object.values(c.por_tipo).sort((a, b) => b.fraude - a.fraude)));

  const m = p.matriz;
  document.getElementById("sub-matriz").textContent = `${numero(c.datos.prueba)} operaciones de los días ${c.datos.division.split(", ").at(-1)}. Umbral ${pct(c.umbral, 1)} (el que dio el mejor F1 en validación).`;
  vaciar(document.getElementById("matriz"), el("div", { class: "matriz" },
    el("div", { class: "matriz__titulo", text: "" }), el("div", { class: "matriz__titulo", text: "La red dijo fraude" }), el("div", { class: "matriz__titulo", text: "La red dijo normal" }),
    el("div", { class: "matriz__titulo", text: "Era fraude" }), el("div", { class: "matriz__bien", text: `${numero(m.verdaderos_positivos)} detectados` }),
    el("div", { class: "matriz__mal", text: `${numero(m.falsos_negativos)} se escaparon` }),
    el("div", { class: "matriz__titulo", text: "Era normal" }), el("div", { class: "matriz__mal", text: `${numero(m.falsos_positivos)} falsas alarmas` }),
    el("div", { class: "matriz__bien", text: `${numero(m.verdaderos_negativos)} correctas` })));
  const a = c.aumento;
  vaciar(document.getElementById("t-aumento"), tablaDatos([
    { titulo: "Entrenamiento", valor: (f) => f[0] }, { titulo: "F1", valor: (f) => numero(f[1].prueba.f1, 3), num: true },
    { titulo: "Detecta", valor: (f) => pct(f[1].prueba.recall), num: true }, { titulo: "Precisión", valor: (f) => pct(f[1].prueba.precision), num: true },
    { titulo: "Épocas", valor: (f) => String(f[1].epocas), num: true },
  ], [["Sin aumento (solo pesos por clase)", a.sin_aumento], ["Con aumento (tf.data + ruido)", a.con_aumento]]));
  document.getElementById("inferencia").textContent = `Evaluar una operación llamando a Keras toma ${ms(c.inferencia.keras_ms)}; la misma red copiada `
    + `a NumPy toma ${ms(c.inferencia.numpy_ms)}: ${numero(c.inferencia.veces, 0)} veces más rápido, con el mismo resultado (diferencia máxima `
    + `${c.verificacion_numpy.toExponential(1)}). Por eso el detector en vivo usa NumPy.`;

  const h = c.historia;
  const curva = [
    { nombre: "Entrenamiento", color: css("--serie-1"), puntos: h.auc_pr.map((y, x) => ({ x: x + 1, y })) },
    { nombre: "Validación", color: css("--serie-2"), puntos: h.val_auc_pr.map((y, x) => ({ x: x + 1, y })) },
  ];
  vaciar(document.getElementById("leyenda-curva-c"), leyenda(curva.map((s) => [s.nombre, s.color])));
  serieXY(document.getElementById("g-curva-clasificador"), curva, { alto: 220, formatoY: (v) => numero(v, 2), tituloTip: (x) => `Época ${x}` });
  const centros = c.histograma.bordes.slice(0, -1).map((b, i) => (b + c.histograma.bordes[i + 1]) / 2);
  const histo = [
    { nombre: "Normales", color: css("--serie-3"), puntos: centros.map((x, i) => ({ x, y: c.histograma.normales[i] || null })) },
    { nombre: "Fraudes", color: css("--serie-1"), puntos: centros.map((x, i) => ({ x, y: c.histograma.fraudes[i] || null })) },
  ];
  vaciar(document.getElementById("leyenda-histograma-c"), leyenda(histo.map((s) => [s.nombre, s.color])));
  serieXY(document.getElementById("g-histograma-clasificador"), histo, { alto: 220, logY: true, formatoX: (v) => pct(v, 0),
    tituloTip: (x) => `Probabilidad ≈ ${pct(x, 0)}` });
}

function montoYDemanda(mo, de) {
  if (mo) {
    const e = mo.error_mediano;
    vaciar(document.getElementById("t-monto"), tablaDatos([
      { titulo: "Método", valor: (f) => f[0] }, { titulo: "Error típico (todos)", valor: (f) => `${numero(f[1], 1)} %`, num: true },
      { titulo: "Clientes nuevos", valor: (f) => `${numero(f[2], 1)} %`, num: true },
    ], [["Red de Keras (regresión)", e.red, e.red_nuevos], ["Mediana del cliente (o de la población)", e.mediana, e.mediana_nuevos]]),
    el("p", { class: "nota", text: `${numero(mo.datos.entrenamiento)} compras legítimas para entrenar · ${numero(mo.parametros)} pesos · pérdida: error absoluto.` }));
  }
  if (de) {
    const dias = de.prueba;
    const series = [
      { nombre: "Real", color: css("--serie-1"), puntos: dias.map((d, i) => ({ x: i, y: d.real })) },
      { nombre: "Red de Keras", color: css("--serie-3"), puntos: dias.map((d, i) => ({ x: i, y: d.red })) },
      { nombre: "Regresión lineal", color: css("--serie-2"), punteada: true, marcas: false, puntos: dias.map((d, i) => ({ x: i, y: d.regresion_lineal })) },
    ];
    vaciar(document.getElementById("leyenda-demanda"), leyenda(series.map((s) => [s.nombre, s.color, s.punteada])));
    serieXY(document.getElementById("g-demanda"), series, { alto: 220, formatoX: (i) => dias[i]?.dia.slice(5) ?? "",
      formatoY: (v) => `$${numero(v / 1000, 0)} mil`, tituloTip: (i) => dias[i]?.dia ?? "" });
    vaciar(document.getElementById("t-demanda"), tablaDatos([
      { titulo: "Método", valor: (f) => f[0] }, { titulo: "Error promedio por día", valor: (f) => dinero(f[1]), num: true },
      { titulo: "Frente a la venta promedio", valor: (f) => pct(f[1] / de.venta_promedio), num: true },
    ], [["Red de Keras", de.error_promedio.red], ["Regresión lineal simple", de.error_promedio.regresion_lineal],
      ["Igual que la semana pasada", de.error_promedio.semana_pasada]]));
  }
}

// --- Probador del clasificador -------------------------------------------------------------
const PRESETS = [
  ["Cliente habitual, compra normal", { valor: 12000, hora: 13, metodo: "Nequi", historial: 40, monto_habitual: 12000, proporcion_metodo: 0.85, compras_1h: 0, metodos_24h: 1, firma_valida: true }],
  ["Cuenta tomada", { valor: 260000, hora: 3.25, metodo: "PSE", historial: 40, monto_habitual: 12000, proporcion_metodo: 0, compras_1h: 0, metodos_24h: 1, firma_valida: true }],
  ["Cliente nuevo, compra normal", { valor: 12000, hora: 15, metodo: "Nequi", historial: 0, monto_habitual: 12000, proporcion_metodo: 0.5, compras_1h: 0, metodos_24h: 1, firma_valida: true }],
  ["Cliente nuevo, monto alto", { valor: 480000, hora: 23, metodo: "PSE", historial: 0, monto_habitual: 12000, proporcion_metodo: 0.5, compras_1h: 0, metodos_24h: 1, firma_valida: true }],
  ["Prueba de tarjeta", { valor: 1500, hora: 16, metodo: "Tarjeta", historial: 2, monto_habitual: 1500, proporcion_metodo: 1, compras_1h: 4, metodos_24h: 1, firma_valida: true }],
  ["Firma alterada", { valor: 12000, hora: 13, metodo: "Nequi", historial: 40, monto_habitual: 12000, proporcion_metodo: 0.85, compras_1h: 0, metodos_24h: 1, firma_valida: false }],
];
const form = document.getElementById("form-clasificador");
const hhmm = (h) => `${String(Math.floor(h)).padStart(2, "0")}:${String(Math.round((h % 1) * 60)).padStart(2, "0")}`;

function escribir(datos) {
  for (const [clave, valor] of Object.entries(datos)) {
    const control = form.elements[clave];
    if (!control) continue;
    if (control.type === "checkbox") control.checked = valor; else control.value = valor;
  }
  etiquetas();
}
function etiquetas() {
  document.getElementById("kv-hora").textContent = hhmm(Number(form.hora.value));
  document.getElementById("kv-prop").textContent = pct(Number(form.proporcion_metodo.value), 0);
}
function leerFormulario() {
  const historial = Number(form.historial.value) || 0;
  const compras1h = Number(form.compras_1h.value) || 0;
  return {
    valor: Number(form.valor.value), hora: Number(form.hora.value), metodo: form.metodo.value, historial,
    monto_habitual: Number(form.monto_habitual.value) || 12000, proporcion_metodo: Number(form.proporcion_metodo.value),
    hora_habitual: 13, dia_semana: (new Date().getDay() + 6) % 7, compras_1min: compras1h >= 3 ? 1 : 0, compras_1h: compras1h,
    compras_24h: compras1h, metodos_24h: Number(form.metodos_24h.value) || 1,
    horas_desde_anterior: compras1h ? 0.1 : historial ? 20 : 720, firma_valida: form.firma_valida.checked,
  };
}
let espera;
async function evaluar() {
  etiquetas();
  const { ok, datos } = await api("POST", "/api/ia/clasificar", leerFormulario());
  const caja = document.getElementById("resultado-clasificador");
  if (!ok) return vaciar(caja, el("p", { class: "muted", text: datos.error || "No se pudo evaluar" }));
  const r = datos.resultado;
  const relleno = el("span", { class: "medidor__relleno" });
  relleno.style.width = `${r.porcentaje}%`;
  const marca = el("span", { class: "medidor__umbral" });
  marca.style.left = `${r.umbral * 100}%`;
  vaciar(caja,
    el("div", { class: "riesgo-linea" }, el("span", { class: "riesgo-linea__valor", text: `${numero(r.porcentaje, 1)} %` }),
      etiqueta(r.clasificacion, r.fraudulenta ? "critico" : "ok")),
    el("div", { class: `medidor ${r.fraudulenta ? "medidor--alto" : ""}` }, relleno, marca),
    el("p", { class: "muted", text: `${r.segmento} · conocimiento general ${numero(r.conocimiento.general, 0)} % · personal ${numero(r.conocimiento.personal, 0)} %` }),
    datos.monto_esperado ? el("p", { class: "muted", text: datos.monto_esperado.lectura }) : null,
    el("ul", { class: "aportes" }, ...r.factores.filter((f) => Math.abs(f.aporte) >= 2).slice(0, 4).map((f) => {
      const barra = el("span", { class: `aportes__relleno ${f.direccion === "normal" ? "aportes__relleno--baja" : ""}` });
      barra.style.width = `${Math.min(100, Math.abs(f.aporte))}%`;
      return el("li", {}, el("div", { class: "aportes__cabeza" }, el("strong", { text: f.nombre }),
        el("span", { class: "muted", text: `hacia ${f.direccion} · ${f.tipo}` })), el("div", { class: "aportes__barra" }, barra),
      el("span", { class: "muted", text: f.explicacion }));
    })));
}

async function iniciar() {
  const { ok, datos } = await api("GET", "/api/ia/estado");
  if (!ok || !datos.disponible) return;
  const m = datos.modelos;
  resumen(m);
  if (m.clasificador) clasificador(m.clasificador);
  montoYDemanda(m.monto, m.demanda);
  if (!m.clasificador || ESTATICO) {
    document.getElementById("probador-clasificador").hidden = !m.clasificador;
    if (ESTATICO) vaciar(document.getElementById("resultado-clasificador"), el("p", { class: "muted", text: "En la demo estática el probador no responde: ejecuta el proyecto." }));
  }
  vaciar(document.getElementById("presets-clasificador"), ...PRESETS.map(([nombre, valores]) =>
    el("button", { class: "boton boton--xs boton--contorno", type: "button", text: nombre, onClick: () => { escribir(valores); evaluar(); } })));
  escribir(PRESETS[0][1]);
  if (!ESTATICO) evaluar();
  form.addEventListener("input", () => { clearTimeout(espera); espera = setTimeout(evaluar, 250); });
}

iniciar();
