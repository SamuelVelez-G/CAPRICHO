/* Integridad: verificar las cadenas de hashes y simular una alteración. */

import { api, dinero, el, fechaCorta, icono, numero, toast, vaciar } from "./comun.js";
import { kpi } from "./ui.js";

const TIPOS = {
  CONTENIDO_ALTERADO: "Contenido alterado", ENLACE_ROTO: "Enlace roto",
  COMPROBANTE_ALTERADO: "Comprobante reemplazado", COMPROBANTE_FALTANTE: "Comprobante borrado",
};

async function verificar() {
  const { ok, datos } = await api("GET", "/api/integridad");
  if (!ok) return toast(datos.error, "error");
  const { facturas: f, pagos: p } = datos;
  vaciar(document.getElementById("integridad-kpis"),
    kpi("Estado", datos.integra ? "Íntegra" : "ALTERADA", datos.integra ? "todas las cadenas cuadran" : "hay registros alterados",
      datos.integra ? "ok" : "bloqueo", datos.integra ? "kpi--ok" : "kpi--critico"),
    kpi("Facturas íntegras", `${numero(f.integros)} / ${numero(f.total)}`, `verificadas en ${numero(f.milisegundos, 1)} ms`, "tabla"),
    kpi("Pagos íntegros", `${numero(p.integros)} / ${numero(p.total)}`, `con sus comprobantes, en ${numero(p.milisegundos, 1)} ms`, "llave"),
    kpi("Problemas", numero(f.cantidad_problemas + p.cantidad_problemas), "contenido, enlaces y archivos", "alerta"),
    kpi("Último hash", f.ultimo_hash.slice(0, 10), "cabeza de la cadena de facturas", "candado"));
  vaciar(document.getElementById("cadena"), ...datos.cadena.map((b) => el("div", { class: `bloque-cadena ${b.roto ? "bloque-cadena--roto" : ""}` },
    el("strong", { text: b.codigo }), el("span", { text: `${dinero(b.total)} · ${fechaCorta(b.fecha_emision)}` }),
    el("code", { text: `anterior ${b.hash_anterior.slice(0, 12)}…` }), el("code", { text: `hash ${b.hash.slice(0, 12)}…` }),
    b.roto ? el("span", { class: "texto-critico", text: "No cuadra" }) : el("span", { class: "texto-ok", text: "Cuadra" }))));
  const problemas = [...f.problemas, ...p.problemas];
  vaciar(document.getElementById("problemas"), problemas.length ? problemas.slice(0, 12).map((x) => el("div", { class: "problema-cadena" },
    el("strong", { text: `${x.registro}: ${TIPOS[x.tipo] || x.tipo}` }), el("br"), x.detalle,
    x.hash_guardado ? el("span", { class: "muted", text: ` (guardado ${x.hash_guardado}…, calculado ${x.hash_calculado}…)` }) : null))
    : el("p", { class: "aviso aviso--ok" }, icono("ok"), el("span", { text: "Ningún registro fue alterado: cada hash coincide con su contenido y con el anterior." })));
  const numeroFactura = document.getElementById("a-numero");
  if (!numeroFactura.value && datos.cadena.length) numeroFactura.value = datos.cadena[Math.max(0, datos.cadena.length - 4)].numero;
}

document.getElementById("verificar").addEventListener("click", verificar);
document.getElementById("form-alterar").addEventListener("submit", async (evento) => {
  evento.preventDefault();
  const form = evento.target;
  const { ok, datos } = await api("POST", "/api/integridad/alterar", { numero: Number(form.numero.value), total: Number(form.total.value) });
  if (!ok) return toast(datos.error, "error");
  toast(`FV-${String(datos.cambio.numero).padStart(6, "0")}: ${dinero(datos.cambio.total_original)} → ${dinero(datos.cambio.total_nuevo)} directamente en la base`, "alerta", 6000);
  verificar();
});
document.getElementById("restaurar").addEventListener("click", async () => {
  const { ok, datos } = await api("POST", "/api/integridad/restaurar");
  if (!ok) return toast(datos.error, "error");
  toast(`${datos.restauradas} facturas restauradas`, "ok");
  verificar();
});

verificar();
