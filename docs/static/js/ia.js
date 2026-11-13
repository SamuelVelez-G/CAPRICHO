/* Página del detector con IA: entrenamiento, evaluación y probador en vivo. */

import { ESTATICO, api, dinero, el, icono, mostrarErrores, numero, svg, vaciar } from "./comun.js";
import { histogramaDoble, lineas } from "./graficas.js";

const css = (nombre) => getComputedStyle(document.documentElement).getPropertyValue(nombre).trim();
const formulario = document.getElementById("form-probador");
const puedeUsarClientes = document.body.dataset.rol === "ADMIN" && !ESTATICO;
let modelo = null;
let solicitudActual = 0;

const hhmm = (hora) => `${String(Math.floor(hora)).padStart(2, "0")}:${String(Math.round((hora % 1) * 60)).padStart(2, "0")}`;

// Casos listos para la demostración en vivo.
const PRESETS = [
  { nombre: "Compra normal", datos: { hora: 13.25, valor: 9000, metodo: "Nequi", proporcion_metodo: 0.9, monto_habitual: 9000,
    hora_habitual: 13, compras_ultima_hora: 0, horas_desde_anterior: 20, compras_previas: 40 } },
  { nombre: "Fraude silencioso", datos: { hora: 3.25, valor: 250000, metodo: "PSE", proporcion_metodo: 0, monto_habitual: 9000,
    hora_habitual: 13, compras_ultima_hora: 0, horas_desde_anterior: 15, compras_previas: 40 } },
  { nombre: "Prueba de tarjeta", datos: { hora: 15.5, valor: 1000, metodo: "Tarjeta", proporcion_metodo: 0.1, monto_habitual: 12000,
    hora_habitual: 15, compras_ultima_hora: 3, horas_desde_anterior: 0.05, compras_previas: 40 } },
  { nombre: "Cliente nuevo, monto alto", datos: { hora: 2.5, valor: 220000, metodo: "Tarjeta", proporcion_metodo: 0.5,
    monto_habitual: 220000, hora_habitual: 2.5, compras_ultima_hora: 0, horas_desde_anterior: 720, compras_previas: 0 } },
  { nombre: "Familia el sábado", datos: { hora: 16, valor: 45000, metodo: "Daviplata", proporcion_metodo: 0.8, monto_habitual: 38000,
    hora_habitual: 16, compras_ultima_hora: 0, horas_desde_anterior: 160, compras_previas: 25 } },
];

// =============================================================================
async function iniciar() {
  const { ok, datos } = await api("GET", "/api/ia/estado");
  if (!ok || !datos.disponible) {
    const aviso = document.getElementById("ia-no-disponible");
    aviso.hidden = false;
    aviso.querySelector("p").textContent = datos.motivo || datos.error || "La IA no está disponible.";
    return;
  }
  modelo = datos.modelo;
  pintarArquitectura();
  pintarKpis();
  pintarCurva();
  pintarEvaluacion();
  iniciarProbador();
}

function kpi(etiqueta, valor, nota, nombreIcono) {
  return el("section", { class: "tarjeta kpi" },
    el("div", { class: "kpi__etiqueta" }, icono(nombreIcono), etiqueta),
    el("div", { class: "kpi__valor", text: valor }),
    el("div", { class: "kpi__delta", text: nota }));
}

function pintarKpis() {
  const e = modelo.evaluacion;
  vaciar(document.getElementById("ia-kpis"),
    kpi("Compras para entrenar", numero(modelo.datos.entrenamiento), `de ${numero(modelo.datos.total)} normales`, "tabla"),
    kpi("Épocas", numero(modelo.historia.perdida.length), "se detiene sola", "reloj"),
    kpi("Parámetros", numero(modelo.parametros), "pesos que aprendió", "grafo"),
    kpi("Ataques detectados", `${numero(e.detectados_ia / e.ataques * 100, 0)} %`, `reglas: ${numero(e.detectados_reglas / e.ataques * 100, 0)} %`, "escudo"),
    kpi("Falsas alarmas", `${numero(e.tasa_falsos_positivos, 1)} %`, `${e.falsos_positivos} de ${numero(e.normales_prueba)} normales`, "alerta"),
    kpi("Motor", `Keras ${modelo.versiones.keras}`, `sobre ${modelo.versiones.motor === "torch" ? "PyTorch" : modelo.versiones.motor}`, "llave"));
}

function pintarArquitectura() {
  const caja = document.getElementById("g-arquitectura");
  const capas = [{ capa: "entrada", neuronas: modelo.variables.length }, ...modelo.arquitectura];
  const nombres = { entrada: "Entrada", codificador_1: "Codificador", codificador_2: "Codificador", cuello_de_botella: "Cuello",
    decodificador_1: "Decodificador", decodificador_2: "Decodificador", reconstruccion: "Reconstrucción" };
  const ancho = Math.max(320, caja.clientWidth);
  const alto = 230;
  const maximo = 12;                                  // se dibujan hasta 12 puntos por capa
  const columnas = capas.map((c, i) => {
    const x = 50 + (i / (capas.length - 1)) * (ancho - 100);
    const visibles = Math.min(c.neuronas, maximo);
    const ys = Array.from({ length: visibles }, (_, j) => 20 + ((j + 0.5) / visibles) * (alto - 70));
    return { ...c, x, ys };
  });
  const capasSvg = [];
  columnas.forEach((col, i) => {
    if (!i) return;
    const previa = columnas[i - 1];
    for (const y1 of previa.ys) for (const y2 of col.ys) {
      capasSvg.push(svg("line", { x1: previa.x, y1, x2: col.x, y2, stroke: "var(--linea-2)", "stroke-width": 0.6 }));
    }
  });
  columnas.forEach((col) => {
    const cuello = col.capa === "cuello_de_botella";
    const borde = col.capa === "entrada" || col.capa === "reconstruccion";
    for (const y of col.ys) {
      capasSvg.push(svg("circle", { cx: col.x, cy: y, r: cuello ? 7 : 5.5,
        fill: cuello ? css("--pajita") : borde ? css("--vino") : css("--serie-1"), stroke: "var(--papel)", "stroke-width": 2 }));
    }
    capasSvg.push(svg("text", { class: "etiqueta-barra", x: col.x, y: alto - 26, "text-anchor": "middle", text: nombres[col.capa] || col.capa }));
    capasSvg.push(svg("text", { class: "tick", x: col.x, y: alto - 10, "text-anchor": "middle",
      text: `${col.neuronas}${col.neuronas > maximo ? " (12 visibles)" : ""}` }));
  });
  vaciar(caja, svg("svg", { viewBox: `0 0 ${ancho} ${alto}`, width: ancho, height: alto, role: "img",
    "aria-label": `Autoencoder: ${capas.map((c) => c.neuronas).join(", ")} neuronas por capa` }, ...capasSvg));
}

function pintarCurva() {
  lineas(document.getElementById("g-perdida"), [
    { nombre: "Entrenamiento", color: css("--serie-1"), valores: modelo.historia.perdida },
    { nombre: "Validación", color: css("--serie-2"), valores: modelo.historia.validacion },
  ], { formato: (v) => numero(v, 2) });
}

function barraPorcentaje(valor, color) {
  const pista = el("div", { class: "barra-mini" }, el("span"));
  pista.firstChild.style.width = `${valor}%`;
  pista.firstChild.style.background = color;
  return el("div", { class: "barra-mini__fila" }, pista, el("strong", { text: `${numero(valor, 0)} %` }));
}

const NOMBRES_REGLAS = {
  POSIBLE_FRAUDE: "Ventana de frecuencia",
  RAFAGA: "Límite de ráfagas",
  HASH_INVALIDO: "Firma inválida",
  MONTO_ATIPICO: "Monto atípico",
  REPLAY: "ID repetido",
  PRECIO_MANIPULADO: "Precio manipulado",
};

function pintarEvaluacion() {
  const e = modelo.evaluacion;
  vaciar(document.getElementById("t-evaluacion"), ...e.por_tipo.map((t) => el("tr", {},
    el("td", { text: t.tipo }),
    el("td", { class: "num", text: numero(t.casos) }),
    el("td", {}, barraPorcentaje(t.ia / t.casos * 100, css("--serie-1"))),
    el("td", {}, barraPorcentaje(t.reglas / t.casos * 100, css("--tinta-3")),
      el("small", { class: "muted", text: t.reglas_motivos?.length
        ? `Detectan: ${t.reglas_motivos.map((r) => NOMBRES_REGLAS[r] || r).join(", ")}`
        : "No la detectan estas reglas" })))));
  document.getElementById("falsos-positivos").textContent =
    `Compras normales que no vio: ${e.falsos_positivos} falsas alarmas de ${numero(e.normales_prueba)} (${numero(e.tasa_falsos_positivos, 1)} %). ` +
    `Umbral: percentil ${modelo.percentil_umbral} del error en compras normales de calibración (${numero(modelo.umbral, 3)}).`;
  const h = modelo.histograma;
  histogramaDoble(document.getElementById("g-histograma"), h.bordes, [
    { nombre: "Normales", color: css("--serie-3"), valores: h.normales },
    { nombre: "Ataques", color: css("--serie-1"), valores: h.ataques },
  ], modelo.umbral);
}

// =============================================================================
//  Probador
// =============================================================================
function leer() {
  const datos = {};
  for (const campo of ["hora", "valor", "proporcion_metodo", "monto_habitual", "hora_habitual",
    "compras_ultima_hora", "horas_desde_anterior", "compras_previas"]) {
    const valor = formulario.elements[campo].value;
    datos[campo] = valor === "" ? null : Number(valor);
  }
  datos.metodo = formulario.metodo.value;
  return datos;
}

function escribir(datos) {
  for (const [campo, valor] of Object.entries(datos)) formulario.elements[campo].value = valor;
  etiquetas();
}

function etiquetas() {
  document.getElementById("v-hora").textContent = hhmm(Number(formulario.hora.value));
  document.getElementById("v-hora-habitual").textContent = hhmm(Number(formulario.hora_habitual.value));
  document.getElementById("v-prop").textContent = `${Math.round(Number(formulario.proporcion_metodo.value) * 100)} %`;
}

let espera;
function programarEvaluacion() {
  etiquetas();
  clearTimeout(espera);
  espera = setTimeout(evaluar, 220);
}

async function evaluar() {
  const idSolicitud = ++solicitudActual;
  formulario.querySelectorAll(".campo").forEach((c) => c.classList.remove("invalido"));
  const caja = document.getElementById("resultado-probador");
  const cuerpo = leer();
  const real = modoReal();
  const respuesta = real
    ? await api("POST", "/api/ia/evaluar-cliente", {
      usuario_id: Number(document.getElementById("cliente-real").value),
      hora: cuerpo.hora, valor: cuerpo.valor, metodo: cuerpo.metodo,
    })
    : await api("POST", "/api/ia/evaluar", cuerpo);
  if (idSolicitud !== solicitudActual) return;
  const { ok, datos } = respuesta;
  if (!ok) {
    mostrarErrores(formulario, datos.errores);
    vaciar(caja, el("div", { class: "aviso aviso--alerta" }, icono("info"), el("p", { text: datos.error })));
    return;
  }
  const r = datos.resultado;
  if (datos.cliente) {
    const c = datos.contexto;
    document.getElementById("resumen-cliente-real").textContent =
      `Historial de ${datos.cliente.nombre} (${datos.cliente.email}): ${numero(c.compras_previas)} compras anteriores, ` +
      `monto habitual ${dinero(c.monto_habitual)}, método elegido usado en ${numero(c.proporcion_metodo * 100)} % ` +
      `y ${numero(c.compras_ultima_hora)} compras en la última hora. La compra evaluada es hipotética.`;
  }
  const medidor = el("div", { class: "medidor" }, el("span", { class: "medidor__relleno" }), el("span", { class: "medidor__umbral" }));
  medidor.firstChild.style.width = `${r.riesgo}%`;
  medidor.firstChild.style.background = r.anomalia ? css("--critico") : css("--ok");
  vaciar(caja,
    el("p", { class: "eyebrow", text: "Puntaje de anomalía · no es probabilidad de fraude" }),
    el("div", { class: "riesgo-grande" }, el("strong", { text: numero(r.riesgo, 1) }), el("span", { text: "/ 100" }),
      el("span", { class: `insignia insignia--${r.anomalia ? "SOSPECHOSA" : "APROBADA"}` },
        icono(r.anomalia ? "alerta" : "ok"), r.anomalia ? "Anomalía" : "Normal")),
    medidor,
    el("p", { class: "tarjeta__sub", text: `Error de reconstrucción ${numero(r.error, 4)} · umbral ${numero(r.umbral, 4)}. Se marca anomalía cuando el error supera el umbral.` }),
    el("p", { class: "etiqueta separado", text: "Qué hizo que se viera rara" }),
    el("ul", { class: "aportes" }, ...r.variables.slice(0, 5).map((v) => {
      const barra = el("span", { class: "aportes__barra" }, el("span"));
      barra.firstChild.style.width = `${v.aporte}%`;
      return el("li", {}, el("div", { class: "aportes__cabeza" }, el("strong", { text: v.nombre }), el("span", { text: `${numero(v.aporte, 0)} %` })),
        barra, el("span", { class: "muted", text: v.explicacion }));
    })));
}

function iniciarProbador() {
  vaciar(document.getElementById("presets"), ...PRESETS.map((p, i) =>
    el("button", { class: `boton boton--sm ${i ? "boton--contorno" : ""}`, type: "button", onClick: (evento) => {
      document.querySelectorAll("#presets button").forEach((b) => b.classList.add("boton--contorno"));
      evento.currentTarget.classList.remove("boton--contorno");
      if (modoReal()) escribirCompra(p.datos);
      else escribir(p.datos);
      evaluar();
    } }, p.nombre)));
  formulario.addEventListener("input", programarEvaluacion);
  formulario.addEventListener("submit", (evento) => evento.preventDefault());
  if (puedeUsarClientes) configurarPerfilesReales();
  escribir(PRESETS[0].datos);
  if (ESTATICO) {
    vaciar(document.getElementById("resultado-probador"), el("div", { class: "aviso aviso--alerta" }, icono("info"),
      el("p", { text: "En la demo estática el probador no puede consultar la red. Ejecuta el proyecto con python run.py para usarlo." })));
    return;
  }
  evaluar();
}

function escribirCompra(datos) {
  for (const campo of ["hora", "valor", "metodo"]) formulario.elements[campo].value = datos[campo];
  etiquetas();
}

function modoReal() {
  return puedeUsarClientes && document.getElementById("modo-perfil")?.value === "real";
}

async function configurarPerfilesReales() {
  const selector = document.getElementById("selector-perfil");
  const modo = document.getElementById("modo-perfil");
  const cliente = document.getElementById("cliente-real");
  selector.hidden = false;
  const respuesta = await api("GET", "/api/ia/clientes");
  const clientes = respuesta.ok ? respuesta.datos.clientes : [];
  if (!clientes.length) {
    modo.value = "manual";
    modo.querySelector('option[value="real"]').disabled = true;
    document.getElementById("resumen-cliente-real").textContent =
      respuesta.datos.error || "No hay clientes con compras en la base de datos; usa un escenario manual.";
  } else {
    vaciar(cliente, ...clientes.map((c) => el("option", { value: c.id,
      text: `${c.nombre} · ${c.email} · ${numero(c.compras)} compras` })));
  }
  modo.addEventListener("change", actualizarModoPerfil);
  cliente.addEventListener("change", evaluar);
  actualizarModoPerfil();
}

function actualizarModoPerfil() {
  const real = modoReal();
  document.getElementById("perfil-real").hidden = !real;
  document.getElementById("habitos-manuales").hidden = real;
  document.getElementById("presets").setAttribute("aria-label", real
    ? "Escenarios de compra para el cliente seleccionado" : "Escenarios de compra manuales");
  evaluar();
}

iniciar();
