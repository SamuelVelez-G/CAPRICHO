/*
 * Laboratorio: arma transacciones, las firma (como lo haría la pasarela de
 * pagos) y las envía al endpoint real. Todo queda en la consola.
 */

import { api, dinero, el, icono, insignia, toast, vaciar } from "./comun.js";

const consola = document.getElementById("consola");
const formulario = document.getElementById("form-txn");
let siguienteId = Date.now() % 1_000_000_000;
let corridas = 0;

// --- Utilidades --------------------------------------------------------------
const dos = (n) => String(n).padStart(2, "0");
function isoLocal(fecha) {
  return `${fecha.getFullYear()}-${dos(fecha.getMonth() + 1)}-${dos(fecha.getDate())}T` +
    `${dos(fecha.getHours())}:${dos(fecha.getMinutes())}:${dos(fecha.getSeconds())}.${String(fecha.getMilliseconds()).padStart(3, "0")}`;
}
/** La hora pedida hoy; si todavía no ha llegado, la de ayer (así nunca queda en el futuro). */
function hoyA(hora, minuto, segundo, milis = 0) {
  const fecha = new Date();
  fecha.setHours(hora, minuto, segundo, milis);
  if (fecha > new Date()) fecha.setDate(fecha.getDate() - 1);
  return isoLocal(fecha);
}
const esperar = (ms) => new Promise((r) => setTimeout(r, ms));
const nuevoId = () => ++siguienteId;
const hexAlAzar = () => [...crypto.getRandomValues(new Uint8Array(32))].map((b) => b.toString(16).padStart(2, "0")).join("");

async function firmar(txn) {
  const { ok, datos } = await api("POST", "/api/laboratorio/firmar", txn);
  if (!ok) throw new Error(datos.error || "No se pudo firmar");
  return datos.hash;
}

/** Arma una transacción firmada. modo: valida | alterar | inventada | nula */
async function armar(txn, modo = "valida") {
  const base = { idTxn: txn.idTxn, user: txn.user, date: txn.date, value: txn.value, paymentMethod: txn.paymentMethod };
  if (modo === "nula") return { ...base, hash: null };
  if (modo === "inventada") return { ...base, hash: hexAlAzar() };
  const hash = await firmar(base);
  if (modo === "alterar") return { ...base, value: Number(base.value) + 1000, hash };
  return { ...base, hash };
}

// --- Consola ----------------------------------------------------------------------
function resumen(status, datos) {
  const txn = datos.transaccion;
  if (txn) {
    const tipos = txn.anomalias.map((a) => `${a.tipo} (${a.nivel})`).join(", ");
    const a = txn.analisis;
    const ventana = a.transacciones_en_ventana !== undefined
      ? ` · ${a.transacciones_en_ventana} en ventana de ${a.ventana_segundos}s` : "";
    return [insignia(txn.estado), ` ${txn.usuario}${ventana}${tipos ? " · " + tipos : ""}`];
  }
  if (datos.lote) {
    return [`Lote: ${Object.entries(datos.lote.resumen).map(([k, v]) => `${v} ${k}`).join(", ")}`];
  }
  if (datos.pedido) return [insignia(datos.pedido.estado), ` Pedido #${datos.pedido.id}`];
  return [datos.error || `HTTP ${status}`];
}

function registrar(metodo, url, cuerpo, respuesta) {
  if (consola.querySelector("p.muted")) vaciar(consola);
  const { status, datos, ms } = respuesta;
  const entrada = el("details", { class: "registro-peticion" },
    el("summary", {},
      el("span", { class: "metodo", text: metodo }),
      el("span", { class: `codigo codigo--${String(status)[0]}`, text: String(status) }),
      el("span", { class: "registro-peticion__resumen" }, ...resumen(status, datos)),
      el("span", { class: "muted", text: `${ms} ms` })),
    el("pre", { text: `${metodo} ${url}\n\n${JSON.stringify(cuerpo, null, 2)}\n\n→ ${status}\n${JSON.stringify(datos, null, 2)}` }));
  consola.prepend(entrada);
}

function titulo(texto, esperado) {
  if (consola.querySelector("p.muted")) vaciar(consola);
  consola.prepend(el("div", { class: "aviso" }, icono("matraz"),
    el("p", {}, el("strong", { text: texto }), el("br"), el("span", { class: "muted", text: `Esperado: ${esperado}` }))));
}

async function enviar(url, cuerpo, metodo = "POST") {
  const respuesta = await api(metodo, url, cuerpo);
  registrar(metodo, url, cuerpo, respuesta);
  return respuesta;
}

// --- Formulario principal ------------------------------------------------------------
function leerFormulario() {
  const valor = formulario.value.value.trim();
  const numero = Number(valor);
  const id = formulario.idTxn.value.trim();
  return {
    idTxn: id === "" ? null : /^\d+$/.test(id) ? Number(id) : id,
    user: formulario.user.value,
    date: formulario.date.value.trim(),
    value: valor === "" ? null : Number.isFinite(numero) ? numero : valor,
    paymentMethod: formulario.paymentMethod.value,
  };
}

function actualizarVista() {
  const txn = leerFormulario();
  const vista = { ...txn, date: txn.date || "(hora de envío)", hash: {
    valida: "(HMAC-SHA256 con la llave)", alterar: "(firma válida, pero se cambia value)",
    inventada: "(64 caracteres al azar)", nula: null }[formulario.firma.value] };
  document.getElementById("vista-previa").textContent = JSON.stringify(vista, null, 2);
}

formulario.addEventListener("input", actualizarVista);
formulario.addEventListener("submit", async (evento) => {
  evento.preventDefault();
  const base = leerFormulario();
  const repetir = Math.max(1, Math.min(20, Number(formulario.repetir.value) || 1));
  const intervalo = Math.max(0, Math.min(10000, Number(formulario.intervalo.value) || 0));
  const boton = formulario.querySelector('button[type="submit"]');
  boton.disabled = true;
  try {
    for (let i = 0; i < repetir; i++) {
      const id = typeof base.idTxn === "number" ? base.idTxn + i : base.idTxn;
      const txn = await armar({ ...base, idTxn: id, date: base.date || isoLocal(new Date()) }, formulario.firma.value);
      await enviar("/api/transacciones", txn);
      if (intervalo && i < repetir - 1) await esperar(intervalo);
    }
  } catch (error) {
    toast(error.message, "error");
  }
  boton.disabled = false;
  formulario.idTxn.value = String(nuevoId());
  actualizarVista();
  cargarReglas();
});

// --- JSON libre ----------------------------------------------------------------------------
const areaJson = document.getElementById("json-libre");
areaJson.value = JSON.stringify({ idTxn: null, user: "", date: "2026-09-23T10:30:01.120", value: "cincuenta mil",
  paymentMethod: "Bitcoin", hash: "" }, null, 2);

function leerJson() {
  try {
    return JSON.parse(areaJson.value);
  } catch {
    toast("El JSON no es válido; se enviará tal cual para ver cómo responde el servidor.", "alerta");
    return areaJson.value;
  }
}
document.getElementById("enviar-json").addEventListener("click", () =>
  enviar(document.getElementById("json-destino").value, leerJson()));
document.getElementById("firmar-json").addEventListener("click", async () => {
  const datos = leerJson();
  const objetos = Array.isArray(datos) ? datos : [datos];
  try {
    for (const objeto of objetos) objeto.hash = await firmar(objeto);
    areaJson.value = JSON.stringify(datos, null, 2);
    toast("Firmado con la llave del servidor.", "ok");
  } catch (error) {
    toast(error.message, "error");
  }
});

// --- Escenarios ----------------------------------------------------------------------------------
const ESCENARIOS = [
  {
    nombre: "Caso de uso 1 · Múltiples transacciones", detalle: "b@b.com a las 10:00:01, :02 y :03",
    esperado: "la tercera queda SOSPECHOSA (POSIBLE_FRAUDE)",
    async correr(s) {
      for (const seg of [1, 2, 3]) await mandar(`b+${s}@b.com`, hoyA(10, 0, seg));
    },
  },
  {
    nombre: "Caso de uso 2 · Transacciones normales", detalle: "c@c.com a las 10:00:01, 10:00:10 y 10:01:20",
    esperado: "las tres APROBADAS",
    async correr(s) {
      for (const [m, seg] of [[0, 1], [0, 10], [1, 20]]) await mandar(`c+${s}@c.com`, hoyA(10, m, seg));
    },
  },
  {
    nombre: "Caso de uso 3 · Diferentes usuarios", detalle: "3 usuarios, uno por segundo",
    esperado: "las tres APROBADAS: cada usuario tiene su ventana",
    async correr(s) {
      for (const n of [1, 2, 3]) await mandar(`usuario${n}+${s}@u.com`, hoyA(10, 0, n));
    },
  },
  {
    nombre: "Diapositiva 39 · Cada 4 segundos", detalle: "10:00:01, :05 y :09",
    esperado: "APROBADAS con la regla principal (3 s); SOSPECHOSA si activas las franjas (10 s en la mañana)",
    async correr(s) {
      for (const seg of [1, 5, 9]) await mandar(`b2+${s}@b.com`, hoyA(10, 0, seg));
    },
  },
  {
    nombre: "5 en el mismo segundo", detalle: "Ráfaga: 5 pagos en menos de 1 s",
    esperado: "la quinta RECHAZADA (RAFAGA, crítico)",
    async correr(s) {
      const inicio = new Date();
      for (let i = 0; i < 5; i++) await mandar(`r+${s}@r.com`, isoLocal(new Date(inicio.getTime() + i * 150)));
    },
  },
  {
    nombre: "Hash alterado", detalle: "Se firma y después se cambia el valor",
    esperado: "RECHAZADA (HASH_INVALIDO, crítico)",
    async correr(s) { await mandar(`h+${s}@h.com`, isoLocal(new Date()), "alterar"); },
  },
  {
    nombre: "Firma falsa", detalle: "Hash de 64 caracteres inventado",
    esperado: "RECHAZADA: sin la llave no se puede falsificar",
    async correr(s) { await mandar(`f+${s}@f.com`, isoLocal(new Date()), "inventada"); },
  },
  {
    nombre: "Inyección SQL", detalle: "user = a@a.com' OR '1'='1' --",
    esperado: "400: bloqueada y registrada en la pila de errores",
    async correr() {
      await enviar("/api/transacciones", { idTxn: nuevoId(), user: "a@a.com' OR '1'='1' --",
        date: isoLocal(new Date()), value: 50000, paymentMethod: "Tarjeta", hash: hexAlAzar() });
    },
  },
  {
    nombre: "Campos nulos", detalle: "Todos los campos en null o vacíos",
    esperado: "422 con un mensaje por campo",
    async correr() {
      await enviar("/api/transacciones", { idTxn: null, user: "", date: " ", value: null, paymentMethod: null, hash: "" });
    },
  },
  {
    nombre: "Tipos equivocados", detalle: "value con letras, fecha en otro formato",
    esperado: "422: no se aceptan tipos incorrectos",
    async correr() {
      await enviar("/api/transacciones", { idTxn: nuevoId(), user: "t@t.com", date: "23/09/2026 10:30",
        value: "cincuenta mil", paymentMethod: "Bitcoin", hash: hexAlAzar() });
    },
  },
  {
    nombre: "Monto atípico", detalle: "Un pago de $1.200.000 en una cafetería",
    esperado: "SOSPECHOSA (MONTO_ATIPICO, nivel bajo)",
    async correr(s) { await mandar(`m+${s}@m.com`, isoLocal(new Date()), "valida", 1_200_000); },
  },
  {
    nombre: "Replay", detalle: "La misma transacción enviada dos veces",
    esperado: "201 y luego 409",
    async correr(s) {
      const txn = await armar({ idTxn: nuevoId(), user: `p+${s}@p.com`, date: isoLocal(new Date()), value: 30000, paymentMethod: "Nequi" });
      await enviar("/api/transacciones", txn);
      await enviar("/api/transacciones", txn);
    },
  },
  {
    nombre: "Lote desordenado", detalle: "6 transacciones en desorden a /lote",
    esperado: "se ordenan con merge sort y la tercera del grupo de 3 queda SOSPECHOSA",
    async correr(s) {
      const segundos = [40, 3, 20, 1, 2, 30];
      const lote = [];
      for (const seg of segundos) {
        lote.push(await armar({ idTxn: nuevoId(), user: `l+${s}@l.com`, date: hoyA(11, 0, seg), value: 12000, paymentMethod: "Daviplata" }));
      }
      await enviar("/api/transacciones/lote", lote);
    },
  },
  {
    nombre: "Precio alterado en la compra", detalle: "Pedido de la tienda con precio 100",
    esperado: "409: el servidor recalcula y registra PRECIO_MANIPULADO (necesita sesión)",
    async correr() {
      const { datos } = await api("GET", "/api/productos");
      const granizado = datos.productos.find((p) => p.categoria === "GRANIZADO");
      await enviar("/api/pedidos", { items: [{ producto_id: granizado.id, sabor: "Capuchino", cantidad: 1, adiciones: [], precio_unitario: 100 }],
        tipo_entrega: "RECOGER", barrio: null, direccion: null, metodo_pago: "Nequi", total: 100 });
    },
  },
];

async function mandar(usuario, fecha, modo = "valida", valor = 50000) {
  const txn = await armar({ idTxn: nuevoId(), user: usuario, date: fecha, value: valor, paymentMethod: "Tarjeta" }, modo);
  return enviar("/api/transacciones", txn);
}

vaciar(document.getElementById("escenarios"), ...ESCENARIOS.map((escenario) =>
  el("button", { class: "escenario", type: "button", onClick: async (evento) => {
    const boton = evento.currentTarget;
    boton.disabled = true;
    corridas += 1;
    const sufijo = `${Date.now().toString(36)}${corridas}`;
    titulo(escenario.nombre, escenario.esperado);
    try {
      await escenario.correr(sufijo);
    } catch (error) {
      toast(error.message, "error");
    }
    boton.disabled = false;
  } },
  el("strong", { text: escenario.nombre }), el("span", { text: escenario.detalle }), el("em", { text: `→ ${escenario.esperado}` }))));

// --- Reglas activas ------------------------------------------------------------------
async function cargarReglas() {
  const { ok, datos } = await api("GET", "/api/configuracion");
  if (!ok) return;
  const r = datos.reglas;
  const filas = [["Modo", r.modo === "FIJA" ? "Regla principal" : "Por franja horaria"]];
  if (r.modo === "FIJA") {
    filas.push(["Ventana", `${r.regla_fija.ventana_segundos} s`], ["Umbral", `${r.regla_fija.umbral} o más transacciones`]);
  } else {
    for (const f of r.franjas) filas.push([`${f.nombre} (${f.desde.slice(0, 5)}–${f.hasta.slice(0, 5)})`, `${f.umbral} en ${f.ventana_segundos} s`]);
  }
  filas.push(["Ráfaga", `${r.rafaga.maximo} en menos de ${r.rafaga.ventana_segundos} s → bloqueo`],
    ["Monto atípico", `desde ${dinero(r.monto_atipico)}`]);
  vaciar(document.getElementById("reglas-activas"), ...filas.map(([k, v]) =>
    el("div", {}, el("span", { class: "muted", text: k }), el("strong", { text: v }))));
}

document.getElementById("limpiar-consola").addEventListener("click", () =>
  vaciar(consola, el("p", { class: "muted", text: "Aún no has enviado nada." })));

formulario.idTxn.value = String(nuevoId());
actualizarVista();
cargarReglas();
