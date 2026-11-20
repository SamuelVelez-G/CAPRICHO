/*
 * Monitor en vivo: cada 1,5 s pregunta por transacciones nuevas (de cualquier
 * origen: este formulario, un celular, el generador del profesor o la API) y
 * muestra cómo las analizó cada parte del sistema, paso a paso.
 */

import { api, dinero, el, fechaCorta, icono, insignia, numero, toast, vaciar } from "./comun.js";
import { cajas } from "./graficas.js";
import { css, kpi } from "./ui.js";
import { iniciarTransferencia } from "./transferencia.js";

const feed = document.getElementById("feed");
const pasosCaja = document.getElementById("pasos");
const seguir = document.getElementById("seguir");
const transacciones = new Map();
let ultimo = 0;
let seleccionada = null;

document.getElementById("enlace-celular").textContent = `${location.origin}/transferir`;

// --- Pasos del análisis -----------------------------------------------------------
function paso(numeroPaso, simbolo, titulo, tono, ...contenido) {
  return el("li", { class: `paso-vivo paso-vivo--${tono}` },
    el("div", { class: "paso-vivo__icono" }, icono(simbolo)),
    el("div", { class: "paso-vivo__cuerpo" },
      el("h3", {}, el("span", { class: "paso-vivo__numero", text: numeroPaso }), titulo),
      ...contenido));
}

function medidor(probabilidad, umbral) {
  const relleno = el("span", { class: "medidor__relleno" });
  relleno.style.width = `${Math.min(100, probabilidad * 100)}%`;
  const marca = el("span", { class: "medidor__umbral", title: `Umbral ${numero(umbral * 100, 0)} %` });
  marca.style.left = `${umbral * 100}%`;
  return el("div", { class: `medidor ${probabilidad >= umbral ? "medidor--alto" : ""}` }, relleno, marca);
}

function conocimiento(c) {
  const general = el("span", { class: "reparto__general" });
  general.style.width = `${c.general}%`;
  const personal = el("span", { class: "reparto__personal" });
  personal.style.width = `${c.personal}%`;
  return el("div", { class: "reparto" },
    el("div", { class: "reparto__barra" }, general, personal),
    el("div", { class: "reparto__leyenda" },
      el("span", { text: `Conocimiento general (de todos los clientes): ${numero(c.general, 0)} %` }),
      el("span", { text: `Personal (historial de este cliente): ${numero(c.personal, 0)} %` })));
}

function factores(lista) {
  return el("ul", { class: "aportes" }, ...lista.filter((f) => Math.abs(f.aporte) >= 1).slice(0, 5).map((f) => {
    const barra = el("span", { class: `aportes__relleno ${f.direccion === "normal" ? "aportes__relleno--baja" : ""}` });
    barra.style.width = `${Math.min(100, Math.abs(f.aporte))}%`;
    return el("li", {},
      el("div", { class: "aportes__cabeza" }, el("strong", { text: f.nombre }),
        el("span", { class: "muted", text: `${numero(Math.abs(f.aporte), 0)} % del peso · hacia ${f.direccion} · ${f.tipo}` })),
      el("div", { class: "aportes__barra" }, barra),
      el("span", { class: "muted", text: f.explicacion }));
  }));
}

function construirPasos(t) {
  const a = t.analisis || {};
  const lista = [];
  lista.push(paso("1", "enviar", "Llega la transferencia", "ok",
    el("p", {}, el("strong", { text: `${dinero(t.valor)} con ${t.metodo_pago}` }), ` · ${fechaCorta(t.fecha_txn, true)}`),
    el("p", { class: "muted", text: `${t.email}${a.anonimo ? " (cliente sin registrar)" : ""} · origen ${t.origen} · ${t.id_txn}` }),
    el("p", { class: "muted", text: "Esquema validado: campos obligatorios, tipos, formato de fecha y sin inyección SQL." })));
  lista.push(paso("2", "llave", "Firma HMAC-SHA256", t.hash_valido ? "ok" : "critico",
    el("p", { text: t.hash_valido ? "La firma coincide con los datos: nadie los cambió en el camino."
      : "La firma NO coincide: los datos se alteraron en el camino o la firma es falsa." })));
  const rafaga = Math.max(a.rafaga_por_fecha || 1, a.rafaga_por_llegada || 1);
  const tonoReglas = rafaga >= a.rafaga_maximo ? "critico" : a.transacciones_en_ventana >= a.umbral ? "alerta" : "ok";
  lista.push(paso("3", "reloj", "Reglas: ventana deslizante", tonoReglas,
    el("p", { text: `${a.transacciones_en_ventana ?? 1} ${(a.transacciones_en_ventana ?? 1) === 1 ? "transacción" : "transacciones"} `
      + `en ${a.ventana_segundos ?? "-"} s · ${a.regla ?? ""} (umbral ${a.umbral ?? "-"})` }),
    el("p", { class: "muted", text: `${rafaga} en el mismo segundo (se bloquea desde ${a.rafaga_maximo ?? 5}) · monto límite ${dinero(a.monto_limite || 300000)}` }),
    a.anonimo ? el("p", { class: "muted", text: "Cliente sin registrar: cada persona en caja es distinta, no se agrupan en una ventana." }) : null));

  const e = a.estadistica;
  if (e) {
    const grafica = el("div", { class: "grafica grafica--baja" });
    lista.push(paso("4", "tabla", `Estadística: cuartiles ${e.referencia === "personal" ? "del cliente" : "de la población"}`,
      e.alerta === "ALTA" ? "alerta" : "ok",
      el("p", { text: `${e.posicion} · puntaje z = ${numero(e.z, 2)} · alerta ${e.alerta.toLowerCase()}` }),
      el("p", { class: "muted", text: e.referencia === "personal"
        ? `Comparado con sus últimas ${e.perfil.n} compras.` : "Sin perfil propio (menos de 5 compras): se compara con todos los clientes." }),
      grafica));
    requestAnimationFrame(() => cajas(grafica, [{ nombre: e.referencia === "personal" ? "Su perfil" : "Población",
      color: css("--serie-1"), perfil: e.perfil, marca: t.valor }], { formato: dinero, log: true }));
  }

  const c = a.clasificador;
  if (c) {
    lista.push(paso("5", "rayo", "Clasificador: red neuronal de Keras", c.fraudulenta ? "critico" : "ok",
      el("div", { class: "riesgo-linea" }, el("span", { class: "riesgo-linea__valor", text: `${numero(c.porcentaje, 1)} %` }),
        el("span", { text: `de probabilidad de fraude → ${c.clasificacion} (umbral ${numero(c.umbral * 100, 0)} %) · ${c.segmento}` })),
      medidor(c.probabilidad, c.umbral), conocimiento(c.conocimiento),
      el("p", { class: "paso-vivo__subtitulo", text: c.fraudulenta ? "Lo que la empujó hacia fraude" : "Lo que la hizo ver normal" }),
      factores(c.factores),
      c.modo !== "marcar" ? el("p", { class: "muted", text: `Modo ${c.modo}: la IA no cambia el resultado de las reglas.` }) : null));
  }
  if (a.monto_esperado) {
    lista.push(paso("6", "grafico", "Monto esperado: regresión de Keras", a.monto_esperado.razon >= 4 ? "alerta" : "ok",
      el("p", { text: a.monto_esperado.lectura })));
  }
  const ia = a.ia;
  if (ia) {
    lista.push(paso("7", "matraz", "Autoencoder: ¿se parece a los hábitos de este cliente?", ia.anomalia ? "alerta" : "ok",
      el("p", { text: `Riesgo ${numero(ia.riesgo, 0)}/100 · error de reconstrucción ${numero(ia.error, 3)} (umbral ${numero(ia.umbral, 3)})` }),
      el("p", { class: "muted", text: `Lo más inusual: ${ia.variables[0].explicacion}` })));
  }
  const tono = { APROBADA: "ok", SOSPECHOSA: "alerta", RECHAZADA: "critico" }[t.estado];
  lista.push(paso("✓", "escudo", "Decisión", tono,
    el("div", { class: "decision" }, insignia(t.estado), el("strong", { text: t.anomalias.length ? "ANOMALÍA" : "NORMAL" })),
    t.anomalias.length ? el("ul", { class: "lista-anomalias" }, ...t.anomalias.map((x) =>
      el("li", {}, el("strong", { text: x.tipo.replaceAll("_", " ").toLowerCase() }), ` · ${x.detalle}`)))
      : el("p", { text: "Ninguna regla ni modelo encontró algo raro." }),
    a.tiempos_ms ? el("p", { class: "muted", text: `Todo el análisis tomó ${numero(a.tiempos_ms.total, 2)} ms `
      + `(reglas ${numero(a.tiempos_ms.reglas, 2)} · estadística ${numero(a.tiempos_ms.estadistica ?? 0, 2)} · `
      + `clasificador ${numero(a.tiempos_ms.clasificador ?? 0, 2)} · autoencoder ${numero(a.tiempos_ms.autoencoder ?? 0, 2)} ms).` }) : null));
  return lista;
}

function mostrar(t, animar) {
  seleccionada = t.id;
  document.getElementById("analisis-sub").textContent = `${t.id_txn} · ${t.email} · ${fechaCorta(t.fecha_creacion, true)}`;
  const lista = construirPasos(t);
  vaciar(pasosCaja, ...lista);
  lista.forEach((item, i) => {
    if (!animar) return item.classList.add("visible");
    setTimeout(() => item.classList.add("visible"), 120 + i * 380);
  });
  feed.querySelectorAll("li").forEach((li) => li.classList.toggle("activa", Number(li.dataset.id) === t.id));
}

// --- Llegadas -------------------------------------------------------------------------
function itemFeed(t) {
  const prob = t.prob_fraude !== null && t.prob_fraude !== undefined ? `${numero(t.prob_fraude * 100, 0)} %` : "—";
  return el("li", { dataset: { id: t.id } },
    el("button", { type: "button", onClick: () => mostrar(transacciones.get(t.id), false) },
      insignia(t.estado), el("span", { class: "feed-vivo__monto", text: dinero(t.valor) }),
      el("span", { class: "feed-vivo__quien", text: `${t.email.split("@")[0]} · ${t.origen}` }),
      el("span", { class: "feed-vivo__prob", text: prob })));
}

function contadores(c, modo) {
  vaciar(document.getElementById("vivo-kpis"),
    kpi("En vivo", numero(c.total || 0), "transacciones que no son de la demo", "rayo"),
    kpi("Aprobadas", numero(c.aprobadas || 0), null, "ok"),
    kpi("Sospechosas", numero(c.sospechosas || 0), null, "alerta"),
    kpi("Rechazadas", numero(c.rechazadas || 0), null, "bloqueo"),
    kpi("Fraudulentas (red)", numero(c.fraudulentas || 0), "según el clasificador", "escudo"));
  const aviso = document.getElementById("aviso-modo");
  aviso.hidden = modo === "marcar";
  aviso.querySelector("p").textContent = modo === "marcar" ? "" :
    `La IA está en modo "${modo}": analiza y muestra su opinión, pero no cambia el resultado de las reglas (se cambia en Antifraude → Reglas).`;
}

async function consultar() {
  const { ok, datos } = await api("GET", `/api/vivo/feed?desde=${ultimo}`);
  if (!ok) return;
  contadores(datos.contadores, datos.modo_ia);
  const nuevas = datos.transacciones.filter((t) => !transacciones.has(t.id));
  for (const t of nuevas) {
    transacciones.set(t.id, t);
    feed.prepend(itemFeed(t));
  }
  while (feed.children.length > 30) feed.lastElementChild.remove();
  if (!feed.children.length) vaciar(feed, el("li", { class: "muted", text: "Todavía no llega ninguna transferencia." }));
  else feed.querySelector("li.muted")?.remove();
  if (nuevas.length && (seguir.checked || seleccionada === null)) mostrar(nuevas.at(-1), ultimo !== 0);
  ultimo = Math.max(ultimo, datos.ultimo);
}

iniciarTransferencia(() => consultar()).catch(() => toast("No se pudieron cargar los clientes de ejemplo", "error"));
consultar();
setInterval(consultar, 1500);
