/*
 * Dashboard antifraude (diapositiva 44). Pide /api/dashboard y dibuja todo.
 * En modo "en vivo" se actualiza cada 5 s: si el profesor manda pagos desde el
 * laboratorio en otra pestaña, los ve aparecer aquí.
 */

import { api, dinero, el, fechaCorta, icono, insignia, modal, mostrarErrores, nivel, numero, toast, vaciar } from "./comun.js";
import { barrasHorizontales, columnasApiladas, mapaCalor, tabla, ventanaDeslizante } from "./graficas.js";

const css = (nombre) => getComputedStyle(document.documentElement).getPropertyValue(nombre).trim();
const SERIES_ESTADO = [
  { clave: "APROBADA", nombre: "Aprobadas", color: css("--ok"), clase: "c-ok", icono: "ok" },
  { clave: "SOSPECHOSA", nombre: "Sospechosas", color: css("--alerta"), clase: "c-alerta", icono: "alerta" },
  { clave: "RECHAZADA", nombre: "Rechazadas", color: css("--critico"), clase: "c-critico", icono: "bloqueo" },
];
const COLOR_NIVEL = { BAJO: css("--nivel-bajo"), MEDIO: css("--nivel-medio"), ALTO: css("--nivel-alto"), CRITICO: css("--nivel-critico") };
const DIAS = ["dom", "lun", "mar", "mié", "jue", "vie", "sáb"];
const TIPO_CORTO = { POSIBLE_FRAUDE: "Posible fraude", RAFAGA: "Ráfaga", HASH_INVALIDO: "Hash inválido",
  MONTO_ATIPICO: "Monto atípico", PRECIO_MANIPULADO: "Precio alterado" };

const estado = { rango: "30d", por: "txn", casoVentana: null, casosVistos: "", datos: null, tipos: {}, paginaAnomalias: 1, paginaTxn: 1, vistas: {}, reglas: null, temporizador: null };
const dash = document.getElementById("dash");

// =============================================================================
//  Carga y refresco
// =============================================================================
async function cargar({ silencioso = false } = {}) {
  if (!silencioso) dash.classList.add("cargando");
  const { ok, datos } = await api("GET", `/api/dashboard?rango=${estado.rango}&por=${estado.por}`);
  dash.classList.remove("cargando");
  if (!ok) {
    toast(datos.error || "No se pudo cargar el dashboard", "error");
    return;
  }
  estado.datos = datos.dashboard;
  pintar();
}

function pintar() {
  const d = estado.datos;
  const hora = d.generado.slice(11, 19);
  document.getElementById("dash-generado").textContent =
    `${numero(d.totales.transacciones)} transacciones y ${numero(d.totales.anomalias)} anomalías en el rango · actualizado ${hora}`;

  for (const [grupo, prefijo] of [["transacciones", "txn"], ["anomalias", "anom"]]) {
    for (const periodo of ["hoy", "semana", "mes"]) {
      document.getElementById(`p-${prefijo}-${periodo}`).textContent = numero(d.periodos[grupo][periodo]);
    }
  }
  pintarKpis(d);
  pintarEstados(d);
  pintarGraficas();
  pintarListas(d);
  pintarFirmas(d);
  pintarVentanaEnVivo(d);
  pintarPila(d.eventos);
  if (!estado.reglas) cargarReglas(d.reglas);
}

function kpi(etiqueta, valor, iconoNombre, delta) {
  return el("section", { class: "tarjeta kpi" },
    el("div", { class: "kpi__etiqueta" }, icono(iconoNombre), etiqueta),
    el("div", { class: "kpi__valor", text: valor }),
    delta || null);
}

function delta(variacion, subirEsMalo, periodo) {
  if (variacion === null || variacion === undefined) return el("div", { class: "kpi__delta", text: "sin periodo anterior" });
  const sube = variacion > 0;
  // Más anomalías es malo; menos transacciones también (el negocio vende menos).
  const clase = variacion === 0 ? "" : sube === subirEsMalo ? "delta-malo" : "delta-bueno";
  return el("div", { class: `kpi__delta ${clase}`, text: `${sube ? "▲" : variacion < 0 ? "▼" : "="} ${numero(Math.abs(variacion), 1)} % vs ${periodo}` });
}

function pintarKpis(d) {
  const periodo = { hoy: "ayer", "7d": "7 días previos", "30d": "30 días previos", "90d": "90 días previos" }[estado.rango] || "";
  vaciar(document.getElementById("kpis"),
    kpi("Transacciones", numero(d.totales.transacciones), "grafico", delta(d.tendencia.transacciones, false, periodo)),
    kpi("Anomalías", numero(d.totales.anomalias), "alerta", delta(d.tendencia.anomalias, true, periodo)),
    kpi("Con anomalías", `${numero(d.totales.porcentaje_con_anomalia, 1)} %`, "escudo",
      el("div", { class: "kpi__delta", text: `${numero(d.totales.transacciones_con_anomalia)} transacciones` })),
    kpi("Usuarios afectados", numero(d.totales.usuarios_afectados), "usuario",
      el("div", { class: "kpi__delta", text: `de ${numero(d.totales.usuarios_activos)} activos` })),
    kpi("Valor sospechoso", dinero(d.totales.valor_sospechoso), "bloqueo",
      el("div", { class: "kpi__delta", text: `de ${dinero(d.totales.valor_total)} en total` })),
    kpi("Promedio por usuario", numero(d.totales.promedio_por_usuario, 1), "tabla",
      el("div", { class: "kpi__delta", text: "transacciones" })));
}

function pintarEstados(d) {
  const nombres = { NUEVA: "Nuevas", ABIERTA: "Abiertas", REVISADA: "Revisadas", DESCARTADA: "Descartadas" };
  vaciar(document.getElementById("estados-anomalias"), ...Object.entries(nombres).map(([clave, nombre]) =>
    el("div", {}, insignia(clave), el("strong", { text: numero(d.anomalias_por_estado[clave]) }), el("span", { class: "muted", text: nombre }))));

  const total = d.totales.transacciones || 1;
  const barra = document.getElementById("proporcion");
  vaciar(barra, ...SERIES_ESTADO.map((s) => {
    const trozo = el("span", { title: `${s.nombre}: ${d.estados[s.clave].cantidad}` });
    trozo.style.background = s.color;
    trozo.style.flex = `${d.estados[s.clave].cantidad} 0 0`;
    return d.estados[s.clave].cantidad ? trozo : null;
  }));
  barra.setAttribute("aria-label", SERIES_ESTADO.map((s) => `${s.nombre} ${d.estados[s.clave].cantidad}`).join(", "));
  vaciar(document.getElementById("leyenda-estados"), ...SERIES_ESTADO.map((s) =>
    el("span", { class: `leyenda__item ${s.clase}` }, el("span", { class: "leyenda__muestra" }), icono(s.icono),
      `${s.nombre} `, el("strong", { text: numero(d.estados[s.clave].cantidad) }),
      ` (${numero(d.estados[s.clave].cantidad / total * 100, 1)} %) · ${dinero(d.estados[s.clave].valor)}`)));
}

function filaTxn(t) {
  const iconos = { APROBADA: ["ok", "icono--ok"], SOSPECHOSA: ["alerta", "icono--alerta"], RECHAZADA: ["bloqueo", "icono--critico"] };
  const [nombre, clase] = iconos[t.estado];
  return el("li", {}, icono(nombre, clase),
    el("div", { class: "lista-txn__principal" }, el("strong", { text: t.email }),
      el("span", { text: `${t.id_txn} · ${fechaCorta(t.fecha_txn)} · ${t.metodo_pago}${t.tipos ? " · " + t.tipos.replaceAll(",", ", ") : ""}` })),
    el("div", { class: "lista-txn__valor" }, dinero(t.valor), el("small", { text: t.estado.toLowerCase() })));
}

function pintarListas(d) {
  const vacia = (texto) => el("li", {}, el("span", { class: "muted", text: texto }));
  vaciar(document.getElementById("ultimas-buenas"), ...(d.ultimas_aprobadas.length ? d.ultimas_aprobadas.map(filaTxn) : [vacia("Sin transacciones en el rango")]));
  vaciar(document.getElementById("ultimas-malas"), ...(d.ultimas_sospechosas.length ? d.ultimas_sospechosas.map(filaTxn) : [vacia("Nada sospechoso en el rango")]));

  vaciar(document.getElementById("horas-pico"), ...(d.calor.horas_pico.length
    ? d.calor.horas_pico.map((h) => el("li", {}, el("span", { text: `${String(h.hora).padStart(2, "0")}:00 – ${String(h.hora).padStart(2, "0")}:59` }),
      el("span", { text: `${numero(h.anomalias)} anomalías` })))
    : [el("li", {}, el("span", { class: "muted", text: "Sin anomalías en el rango" }))]));

  const mayor = d.mayor_sospechosa.transaccion;
  vaciar(document.getElementById("mayor-sospechosa"), mayor
    ? el("div", { class: "destacado" }, el("div", { class: "destacado__icono" }, icono("alerta")),
      el("div", {}, el("strong", { text: dinero(mayor.valor) }),
        el("div", { class: "muted", text: `${mayor.email} · ${mayor.id_txn}` }),
        el("div", { class: "muted", text: `Comparó ${numero(d.mayor_sospechosa.comparadas)} montos partiéndolos en mitades` })))
    : el("p", { class: "muted", text: "No hay transacciones sospechosas en el rango." }));

  vaciar(document.getElementById("t-recurrentes"), ...(d.recurrentes.length ? d.recurrentes.map((u) => el("tr", {},
    el("td", { class: "correo", title: u.email }, el("strong", { text: u.nombre }), el("br"), el("span", { class: "muted", text: u.email })),
    el("td", {}, insignia(u.estado)),
    el("td", { class: "num", text: numero(u.transacciones) }),
    el("td", { class: "num", text: numero(u.anomalias) })))
    : [el("tr", {}, el("td", { colspan: "4", class: "muted", text: "Nadie reincide en este rango." }))]));

  vaciar(document.getElementById("t-multiples"), ...(d.multiples.length ? d.multiples.map((m) => el("tr", {},
    el("td", { class: "correo", text: m.email, title: m.email }),
    el("td", {}, nivel(m.nivel), el("br"), TIPO_CORTO[m.tipo]),
    el("td", { class: "num", text: `${m.cantidad_transacciones} en ${numero(m.ventana_segundos, m.ventana_segundos % 1 ? 1 : 0)} s` }),
    el("td", { text: fechaCorta(m.fecha_txn) })))
    : [el("tr", {}, el("td", { colspan: "4", class: "muted", text: "Sin casos en el rango." }))]));
}

function pintarFirmas(d) {
  const lista = document.getElementById("firmas");
  if (!d.firmas.length) {
    vaciar(lista, el("li", {}, el("span", { class: "muted", text: "Aún no hay transacciones en el rango." })));
    return;
  }
  vaciar(lista, ...d.firmas.map((f) => el("li", {},
    el("span", {}, icono(f.firma === "Hash inválido" ? "bloqueo" : "llave"), ` ${f.firma}`),
    el("span", { text: numero(f.cantidad) }))));
}

// --- Ventana deslizante visible en el dashboard ----------------------------------
async function pintarVentanaEnVivo(d) {
  const selector = document.getElementById("caso-ventana");
  const casos = d.multiples;
  const firma = casos.map((c) => c.id).join(",");
  if (firma === estado.casosVistos) return;          // nada nuevo: no se interrumpe la animación
  const habia = estado.casosVistos !== "";
  estado.casosVistos = firma;
  if (!casos.length) {
    vaciar(selector, el("option", { text: "Aún no hay casos de múltiples transacciones" }));
    vaciar(document.getElementById("g-ventana"), el("p", { class: "muted",
      text: "Cuando un usuario haga varias transacciones dentro de la ventana, aquí se verá cómo se detectó." }));
    document.getElementById("conteo-ventana").textContent = "";
    return;
  }
  vaciar(selector, ...casos.map((c) => el("option", { value: c.id,
    text: `#${c.id} · ${c.email} · ${c.cantidad_transacciones} en ${numero(c.ventana_segundos, c.ventana_segundos % 1 ? 1 : 0)} s · ${fechaCorta(c.fecha_txn)}` })));
  // Si llegó un caso nuevo (o es la primera carga), se muestra el más reciente.
  if (!habia || !casos.some((c) => String(c.id) === String(estado.casoVentana)) || casos[0].id !== Number(estado.casoVentana)) {
    estado.casoVentana = casos[0].id;
  }
  selector.value = String(estado.casoVentana);
  await mostrarCasoVentana(estado.casoVentana, true);
}

let animacionVentana = null;
async function mostrarCasoVentana(id, reproducir) {
  const { ok, datos } = await api("GET", `/api/anomalias/${id}`);
  if (!ok) return;
  const a = datos.anomalia;
  const umbral = umbralDe(a);
  const conteo = document.getElementById("conteo-ventana");
  animacionVentana = ventanaDeslizante(document.getElementById("g-ventana"), datos.ventana, a.ventana_segundos,
    datos.margen_segundos, (n, fin) => {
      conteo.textContent = `${a.email} · ventana que termina en ${fin >= 0 ? "+" : ""}${numero(fin, 1)} s: ` +
        `${n} transacciones adentro` + (umbral && n >= umbral ? ` → llega al umbral (${umbral}): ANOMALÍA` : "");
    });
  if (reproducir) animacionVentana.reproducir();
}

document.getElementById("caso-ventana").addEventListener("change", (evento) => {
  estado.casoVentana = Number(evento.target.value);
  mostrarCasoVentana(estado.casoVentana, true);
});
document.getElementById("reproducir-ventana").addEventListener("click", () => animacionVentana?.reproducir());

function pintarPila(eventos) {
  const caja = document.getElementById("pila-mini");
  if (!eventos.cima.length) {
    vaciar(caja, el("p", { class: "muted", text: "La pila está vacía: no hay errores pendientes." }));
    return;
  }
  vaciar(caja, ...eventos.cima.slice(0, 5).map((e) => el("div", { class: "pila-item" }, nivel(e.nivel),
    el("div", { class: "pila-item__detalle" }, el("strong", { text: `${e.tipo} · ${e.metodo || ""} ${e.ruta || ""}` }), el("p", { text: e.detalle })),
    el("time", { text: fechaCorta(e.fecha) }))),
  el("p", { class: "muted", text: `${numero(eventos.total)} eventos sin atender en la pila.` }));
}

// =============================================================================
//  Gráficas (con su tabla equivalente)
// =============================================================================
function etiquetaTramo(punto, corta) {
  if (estado.datos.serie.unidad === "hora") return corta ? `${punto.tramo.slice(11, 13)}h` : `Hoy ${punto.tramo.slice(11, 13)}:00`;
  const fecha = new Date(`${punto.tramo}T12:00:00`);
  const texto = `${fecha.getDate()}/${fecha.getMonth() + 1}`;
  return corta ? texto : `${DIAS[fecha.getDay()]} ${texto}`;
}

const GRAFICAS = {
  evolucion: {
    dibujar(caja, d) {
      vaciar(document.getElementById("leyenda-evolucion"), ...SERIES_ESTADO.map((s) =>
        el("span", { class: `leyenda__item ${s.clase}` }, el("span", { class: "leyenda__muestra" }), s.nombre)),
      el("span", { class: "leyenda__item" }, el("span", { class: "leyenda__muestra leyenda__muestra--punto c-critico" }), "Pico de anomalías"));
      columnasApiladas(caja, d.serie.puntos, SERIES_ESTADO, { etiqueta: etiquetaTramo });
    },
    tabla: (d) => tabla([
      { titulo: "Tramo", valor: (p) => etiquetaTramo(p) },
      ...SERIES_ESTADO.map((s) => ({ titulo: s.nombre, num: true, valor: (p) => numero(p[s.clave]) })),
      { titulo: "Anomalías", num: true, valor: (p) => numero(p.anomalias) },
      { titulo: "Pico", valor: (p) => (p.pico ? "Sí" : "") },
    ], d.serie.puntos),
  },
  calor: {
    dibujar: (caja, d) => mapaCalor(caja, d.calor),
    tabla: (d) => tabla([
      { titulo: "Día", valor: (f) => f.dia },
      ...[0, 3, 6, 9, 12, 15, 18, 21].map((h) => ({ titulo: `${h}-${h + 2}h`, num: true, valor: (f) => numero(f.celdas.slice(h, h + 3).reduce((a, b) => a + b, 0)) })),
    ], d.calor.dias.map((dia, i) => ({ dia, celdas: d.calor.celdas[i] }))),
  },
  niveles: {
    dibujar: (caja, d) => barrasHorizontales(caja, Object.entries(d.por_nivel).map(([n, v]) =>
      ({ etiqueta: n.charAt(0) + n.slice(1).toLowerCase(), valor: v, color: COLOR_NIVEL[n] }))),
    tabla: (d) => tabla([{ titulo: "Nivel", valor: (f) => f[0] }, { titulo: "Anomalías", num: true, valor: (f) => numero(f[1]) }],
      Object.entries(d.por_nivel)),
  },
  tipos: {
    dibujar: (caja, d) => (d.por_tipo.length
      ? barrasHorizontales(caja, d.por_tipo.map((t) => ({ etiqueta: TIPO_CORTO[t.tipo] || t.tipo, valor: t.cantidad, nombre: t.nombre })),
        { extra: (f) => f.nombre })
      : vaciar(caja, el("p", { class: "muted", text: "Sin anomalías en el rango." }))),
    tabla: (d) => tabla([{ titulo: "Tipo", valor: (t) => t.nombre }, { titulo: "Cantidad", num: true, valor: (t) => numero(t.cantidad) }], d.por_tipo),
  },
  metodos: {
    dibujar: (caja, d) => barrasHorizontales(caja, d.metodos.map((m) => ({
      etiqueta: `${m.metodo} (${numero(m.sospechosas / m.cantidad * 100, 1)} %)`, valor: m.cantidad, m })),
    { extra: (f) => `${numero(f.m.sospechosas)} sospechosas · ${dinero(f.m.valor)}` }),
    tabla: (d) => tabla([
      { titulo: "Método", valor: (m) => m.metodo }, { titulo: "Transacciones", num: true, valor: (m) => numero(m.cantidad) },
      { titulo: "No aprobadas", num: true, valor: (m) => numero(m.sospechosas) }, { titulo: "Valor", num: true, valor: (m) => dinero(m.valor) },
    ], d.metodos),
  },
};

function pintarGraficas() {
  for (const tarjeta of document.querySelectorAll("[data-grafica]")) {
    const nombre = tarjeta.dataset.grafica;
    const caja = tarjeta.querySelector(".grafica");
    if (estado.vistas[nombre] === "tabla") vaciar(caja, GRAFICAS[nombre].tabla(estado.datos));
    else GRAFICAS[nombre].dibujar(caja, estado.datos);
  }
}

document.querySelectorAll("[data-grafica] .boton-tabla").forEach((boton) => {
  boton.addEventListener("click", () => {
    const nombre = boton.closest("[data-grafica]").dataset.grafica;
    const aTabla = estado.vistas[nombre] !== "tabla";
    estado.vistas[nombre] = aTabla ? "tabla" : "grafica";
    boton.setAttribute("aria-pressed", String(aTabla));
    boton.lastChild.textContent = aTabla ? " Gráfica" : " Tabla";
    pintarGraficas();
  });
});

let redimension;
new ResizeObserver(() => {
  clearTimeout(redimension);
  redimension = setTimeout(() => { if (estado.datos) pintarGraficas(); }, 150);
}).observe(dash);

// =============================================================================
//  Anomalías: tabla, detalle y cambio de estado
// =============================================================================
async function cargarAnomalias() {
  const filtros = new URLSearchParams({ pagina: estado.paginaAnomalias });
  for (const [id, clave] of [["f-estado", "estado"], ["f-nivel", "nivel"], ["f-tipo", "tipo"]]) {
    const valor = document.getElementById(id).value;
    if (valor) filtros.set(clave, valor);
  }
  const { ok, datos } = await api("GET", `/api/anomalias?${filtros}`);
  if (!ok) return;
  const cuerpo = document.getElementById("t-anomalias");
  vaciar(cuerpo, ...(datos.anomalias.length ? datos.anomalias.map((a) => el("tr", {},
    el("td", { class: "num", text: a.id }),
    el("td", { text: estado.tipos[a.tipo] || a.tipo }),
    el("td", {}, nivel(a.nivel)),
    el("td", { class: "correo", text: a.email, title: a.email }),
    el("td", { class: "num", text: dinero(a.valor) }),
    el("td", { text: fechaCorta(a.fecha_txn) }),
    el("td", {}, insignia(a.estado)),
    el("td", {}, el("button", { class: "boton boton--xs boton--contorno", type: "button", onClick: () => abrirAnomalia(a.id) }, "Ver")))) :
    [el("tr", {}, el("td", { colspan: "8", class: "muted", text: "No hay anomalías con esos filtros." }))]));
  document.getElementById("info-anomalias").textContent = `${numero(datos.total)} anomalías · página ${datos.pagina} de ${datos.paginas}`;
  document.getElementById("anom-prev").disabled = datos.pagina <= 1;
  document.getElementById("anom-sig").disabled = datos.pagina >= datos.paginas;
}

["f-estado", "f-nivel", "f-tipo"].forEach((id) => document.getElementById(id).addEventListener("change", () => {
  estado.paginaAnomalias = 1;
  cargarAnomalias();
}));
document.getElementById("anom-prev").addEventListener("click", () => { estado.paginaAnomalias--; cargarAnomalias(); });
document.getElementById("anom-sig").addEventListener("click", () => { estado.paginaAnomalias++; cargarAnomalias(); });

const ACCIONES = { ABIERTA: "Abrir / reabrir", REVISADA: "Confirmar (revisada)", DESCARTADA: "Descartar (falso positivo)" };

async function abrirAnomalia(id) {
  const { ok, datos } = await api("GET", `/api/anomalias/${id}`);
  if (!ok) {
    toast(datos.error, "error");
    return;
  }
  const contenido = el("div");
  const ventana = modal(`Anomalía #${id} · ${estado.tipos[datos.anomalia.tipo] || datos.anomalia.tipo}`, contenido);
  pintarDetalle(contenido, datos, ventana);
}

function pintarDetalle(contenido, datos, ventanaModal) {
  const a = datos.anomalia;
  const cajaVentana = el("div", { class: "grafica" });
  const leyendaConteo = el("p", { class: "tarjeta__sub" });
  const boton = el("button", { class: "boton boton--xs", type: "button" }, icono("reloj"), " Deslizar la ventana");

  const nota = el("input", { class: "entrada", type: "text", maxlength: "200", placeholder: "Nota obligatoria: qué revisaste (5 a 200 caracteres)", "aria-label": "Nota" });
  const campoNota = el("div", { class: "campo", dataset: { campo: "nota" } }, nota,
    el("span", { class: "campo__error" }, icono("alerta"), el("span")));
  const acciones = el("div", { class: "hero__acciones" }, ...datos.transiciones.map((destino) =>
    el("button", { class: `boton boton--sm ${destino === "DESCARTADA" ? "boton--contorno" : ""}`, type: "button", onClick: async () => {
      const { ok, datos: respuesta } = await api("PATCH", `/api/anomalias/${a.id}`, { estado: destino, nota: nota.value });
      if (!ok) {
        if (!mostrarErrores(contenido, respuesta.errores)) toast(respuesta.error, "error");
        return;
      }
      toast(`Anomalía #${a.id} → ${destino}`, "ok");
      pintarDetalle(contenido, respuesta, ventanaModal);
      cargarAnomalias();
      cargar({ silencioso: true });
    } }, ACCIONES[destino])));

  vaciar(contenido, el("div", { class: "detalle-rejilla" },
    el("div", {},
      el("div", { class: "tarjeta__cabeza" },
        el("div", {}, el("h3", { class: "tarjeta__titulo", text: "Ventana deslizante" }),
          el("p", { class: "tarjeta__sub", text: a.ventana_segundos
            ? `Transacciones de ${a.email} alrededor de la anomalía. El recuadro es la ventana de ${numero(a.ventana_segundos, a.ventana_segundos % 1 ? 1 : 0)} s.`
            : `Transacciones de ${a.email} alrededor de este pago. Esta anomalía no depende de una ventana.` })),
        a.ventana_segundos ? boton : null),
      cajaVentana, leyendaConteo,
      el("div", { class: "leyenda" }, ...SERIES_ESTADO.map((s) =>
        el("span", { class: `leyenda__item ${s.clase}` }, el("span", { class: "leyenda__muestra" }), s.nombre)),
      el("span", { class: "leyenda__item" }, el("span", { class: "leyenda__muestra leyenda__muestra--anillo" }), "Borde oscuro = esta transacción")),
      el("h3", { class: "tarjeta__titulo separado", text: "Línea de tiempo" }),
      el("ol", { class: "linea-tiempo" },
        el("li", {}, el("time", { text: fechaCorta(a.fecha_txn, true) }), el("p", { text: `Llega la transacción ${a.id_txn} (${dinero(a.valor)}, ${a.metodo_pago}).` })),
        ...datos.historial.map((h) => el("li", {}, el("time", { text: fechaCorta(h.fecha) }),
          el("p", {}, h.estado_anterior ? `${h.estado_anterior} → ` : "", el("strong", { text: h.estado_nuevo }), ` · ${h.nota} · ${h.responsable}`)))),
    ),
    el("div", {},
      el("dl", { class: "detalle-datos" },
        el("dt", { text: "Estado" }), el("dd", {}, insignia(a.estado)),
        el("dt", { text: "Nivel" }), el("dd", {}, nivel(a.nivel)),
        el("dt", { text: "Usuario" }), el("dd", { text: `${a.nombre} · ${a.email}` }),
        el("dt", { text: "idTxn" }), el("dd", { class: "mono", text: a.id_txn }),
        el("dt", { text: "Valor" }), el("dd", { text: dinero(a.valor) }),
        el("dt", { text: "Pago" }), el("dd", {}, insignia(a.estado_txn)),
        el("dt", { text: "Cantidad" }), el("dd", { text: `${a.cantidad_transacciones} transacciones` }),
        el("dt", { text: "Detalle" }), el("dd", { text: a.detalle }),
        el("dt", { text: "Historial" }), el("dd", { text: `${datos.otras_del_usuario} anomalías más de este usuario` })),
      el("h3", { class: "tarjeta__titulo separado", text: "Revisión" }),
      datos.transiciones.length ? campoNota : null,
      acciones)));

  requestAnimationFrame(() => {
    const umbral = umbralDe(a);
    const vis = ventanaDeslizante(cajaVentana, datos.ventana, a.ventana_segundos, datos.margen_segundos, (n, fin) => {
      leyendaConteo.textContent = `Ventana que termina en ${fin >= 0 ? "+" : ""}${numero(fin, 1)} s: ${n} transacciones dentro` +
        (umbral && n >= umbral ? ` → alcanza el umbral (${umbral})` : "");
    });
    boton.addEventListener("click", () => vis.reproducir());
  });
}

/** Umbral con el que se compara la ventana de esta anomalía (según las reglas actuales). */
function umbralDe(anomalia) {
  const reglas = estado.reglas;
  if (!reglas) return null;
  if (anomalia.tipo === "RAFAGA") return reglas.rafaga.maximo;
  if (anomalia.tipo !== "POSIBLE_FRAUDE") return null;
  if (reglas.modo === "FIJA") return reglas.regla_fija.umbral;
  const hora = anomalia.fecha_txn.slice(11, 19);
  const franja = reglas.franjas.find((f) => (f.desde < f.hasta ? hora > f.desde && hora <= f.hasta : hora > f.desde || hora <= f.hasta));
  return franja?.umbral ?? null;
}

// =============================================================================
//  Transacciones
// =============================================================================
async function cargarTransacciones() {
  const filtros = new URLSearchParams({ pagina: estado.paginaTxn });
  const valorEstado = document.getElementById("t-estado").value;
  const busqueda = document.getElementById("t-busqueda").value.trim();
  if (valorEstado) filtros.set("estado", valorEstado);
  if (busqueda) filtros.set("q", busqueda);
  const { ok, datos } = await api("GET", `/api/transacciones?${filtros}`);
  if (!ok) {
    toast(datos.error, "error");
    return;
  }
  vaciar(document.getElementById("t-transacciones"), ...(datos.transacciones.length ? datos.transacciones.map((t) => el("tr", {},
    el("td", { class: "mono", text: t.id_txn }),
    el("td", { class: "correo", text: t.email, title: t.email }),
    el("td", { class: "num", text: dinero(t.valor) }),
    el("td", { text: fechaCorta(t.fecha_txn) }),
    el("td", { text: t.metodo_pago }),
    el("td", { text: t.origen }),
    el("td", {}, insignia(t.estado), t.tipos ? el("div", { class: "muted", text: t.tipos.replaceAll(",", ", ") }) : null)))
    : [el("tr", {}, el("td", { colspan: "7", class: "muted", text: "Sin resultados." }))]));
  document.getElementById("info-transacciones").textContent = `${numero(datos.total)} transacciones · página ${datos.pagina} de ${datos.paginas}`;
  document.getElementById("txn-prev").disabled = datos.pagina <= 1;
  document.getElementById("txn-sig").disabled = datos.pagina >= datos.paginas;
}

document.getElementById("t-estado").addEventListener("change", () => { estado.paginaTxn = 1; cargarTransacciones(); });
let esperaBusqueda;
document.getElementById("t-busqueda").addEventListener("input", () => {
  clearTimeout(esperaBusqueda);
  esperaBusqueda = setTimeout(() => { estado.paginaTxn = 1; cargarTransacciones(); }, 300);
});
document.getElementById("txn-prev").addEventListener("click", () => { estado.paginaTxn--; cargarTransacciones(); });
document.getElementById("txn-sig").addEventListener("click", () => { estado.paginaTxn++; cargarTransacciones(); });

// =============================================================================
//  Reglas: PUT (todo) y PATCH (solo cambios)
// =============================================================================
const formReglas = document.getElementById("form-reglas");

function cargarReglas(reglas) {
  estado.reglas = structuredClone(reglas);
  formReglas.querySelector(`input[name="modo"][value="${reglas.modo}"]`).checked = true;
  formReglas.fija_ventana.value = reglas.regla_fija.ventana_segundos;
  formReglas.fija_umbral.value = reglas.regla_fija.umbral;
  formReglas.rafaga_maximo.value = reglas.rafaga.maximo;
  formReglas.rafaga_ventana.value = reglas.rafaga.ventana_segundos;
  formReglas.monto.value = reglas.monto_atipico;
  formReglas.rafaga_llegada.checked = Boolean(reglas.rafaga.por_llegada);
  vaciar(document.getElementById("r-franjas"), ...reglas.franjas.map((f) => el("tr", { dataset: { clave: f.clave } },
    el("td", { text: f.nombre }),
    el("td", { class: "muted", text: `${sumarSegundo(f.desde)} – ${f.hasta}` }),
    el("td", {}, el("input", { class: "entrada", type: "number", step: "0.5", min: "0.5", name: `franja_${f.clave}_ventana`, value: f.ventana_segundos, "aria-label": `Ventana ${f.nombre}` })),
    el("td", {}, el("input", { class: "entrada", type: "number", min: "2", name: `franja_${f.clave}_umbral`, value: f.umbral, "aria-label": `Umbral ${f.nombre}` })))));
}

function sumarSegundo(hora) {
  const [h, m, s] = hora.split(":").map(Number);
  const total = (h * 3600 + m * 60 + s + 1) % 86400;
  return [Math.floor(total / 3600), Math.floor(total / 60) % 60, total % 60].map((n) => String(n).padStart(2, "0")).join(":");
}

const aNumero = (valor) => (valor === "" ? null : Number(valor));

function leerReglas() {
  return {
    modo: formReglas.querySelector('input[name="modo"]:checked').value,
    regla_fija: { ventana_segundos: aNumero(formReglas.fija_ventana.value), umbral: aNumero(formReglas.fija_umbral.value) },
    franjas: estado.reglas.franjas.map((f) => ({
      clave: f.clave,
      ventana_segundos: aNumero(formReglas[`franja_${f.clave}_ventana`].value),
      umbral: aNumero(formReglas[`franja_${f.clave}_umbral`].value),
    })),
    rafaga: { maximo: aNumero(formReglas.rafaga_maximo.value), ventana_segundos: aNumero(formReglas.rafaga_ventana.value),
      por_llegada: formReglas.rafaga_llegada.checked },
    monto_atipico: aNumero(formReglas.monto.value),
  };
}

function soloCambios(nuevas) {
  const cambios = {};
  const actuales = { ...estado.reglas,
    rafaga: { por_llegada: false, ...estado.reglas.rafaga },
    franjas: estado.reglas.franjas.map((f) => ({ clave: f.clave, ventana_segundos: f.ventana_segundos, umbral: f.umbral })) };
  for (const [clave, valor] of Object.entries(nuevas)) {
    if (JSON.stringify(valor) !== JSON.stringify(actuales[clave])) cambios[clave] = valor;
  }
  return cambios;
}

async function guardarReglas(metodo) {
  formReglas.querySelectorAll(".campo").forEach((c) => c.classList.remove("invalido"));
  const nuevas = leerReglas();
  const cuerpo = metodo === "PUT" ? nuevas : soloCambios(nuevas);
  if (metodo === "PATCH" && !Object.keys(cuerpo).length) {
    toast("No cambiaste nada.", "info");
    return;
  }
  const { ok, status, datos } = await api(metodo, "/api/configuracion", cuerpo);
  const resultado = document.getElementById("reglas-resultado");
  if (!ok) {
    mostrarErrores(formReglas, datos.errores);
    resultado.textContent = `${metodo} /api/configuracion → ${status}: ${datos.error}` +
      (datos.errores ? ` (${Object.entries(datos.errores).map(([c, m]) => `${c}: ${m}`).join("; ")})` : "");
    return;
  }
  cargarReglas(datos.reglas);
  resultado.textContent = `${metodo} /api/configuracion → ${status} · enviaste: ${Object.keys(cuerpo).join(", ")}`;
  toast("Reglas actualizadas. Aplican desde la próxima transacción.", "ok");
}

document.getElementById("guardar-patch").addEventListener("click", () => guardarReglas("PATCH"));
document.getElementById("guardar-put").addEventListener("click", () => guardarReglas("PUT"));

// =============================================================================
//  Filtros de rango y modo en vivo
// =============================================================================
document.getElementById("rango").addEventListener("click", (evento) => {
  const boton = evento.target.closest("button[data-rango]");
  if (!boton) return;
  estado.rango = boton.dataset.rango;
  document.querySelectorAll("#rango button").forEach((b) => b.setAttribute("aria-pressed", String(b === boton)));
  cargar();
});

document.getElementById("por").addEventListener("click", (evento) => {
  const boton = evento.target.closest("button[data-por]");
  if (!boton) return;
  estado.por = boton.dataset.por;
  document.querySelectorAll("#por button").forEach((b) => b.setAttribute("aria-pressed", String(b === boton)));
  cargar();
});

function programarRefresco() {
  clearInterval(estado.temporizador);
  const vivo = document.getElementById("en-vivo").checked;
  document.getElementById("punto-vivo").classList.toggle("pausado", !vivo);
  if (!vivo) return;
  estado.temporizador = setInterval(() => {
    if (document.hidden || document.querySelector(".modal")) return;
    cargar({ silencioso: true });
    if (estado.paginaAnomalias === 1) cargarAnomalias();
    if (estado.paginaTxn === 1) cargarTransacciones();
  }, 5000);
}
document.getElementById("en-vivo").addEventListener("change", programarRefresco);

// =============================================================================
async function iniciar() {
  const { ok, datos } = await api("GET", "/api/configuracion");
  if (ok) {
    estado.tipos = datos.tipos;
    const selector = document.getElementById("f-tipo");
    for (const [clave, nombre] of Object.entries(datos.tipos)) selector.append(el("option", { value: clave, text: nombre }));
  }
  await cargar();
  cargarAnomalias();
  cargarTransacciones();
  programarRefresco();
}

iniciar();
