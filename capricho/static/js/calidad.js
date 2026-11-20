/* Calidad de datos: auditoría con puntaje, corrección automática e importación de archivos sucios. */

import { api, csrf, el, fechaCorta, mostrarErrores, numero, toast, vaciar } from "./comun.js";
import { etiqueta, kpi, tablaDatos } from "./ui.js";

const NOMBRES = {
  CLIENTE_DUPLICADO: "Cliente duplicado", CORREO_SIN_NORMALIZAR: "Correo sin normalizar", CELULAR_SIN_NORMALIZAR: "Celular sin normalizar",
  CELULAR_INVALIDO: "Celular inválido", NOMBRE_SIN_NORMALIZAR: "Nombre sin normalizar", ITEM_DUPLICADO: "Ítem repetido",
  PRECIO_SOSPECHOSO: "Precio sospechoso", CATEGORIA_PARECIDA: "Categorías parecidas", FACTURA_DESCUADRADA: "Factura descuadrada",
  METODO_NO_ESTANDAR: "Método de pago no estándar",
};
const DIMENSIONES = {
  completitud: "clientes con celular", validez: "formatos correctos", unicidad: "registros sin duplicar", consistencia: "facturas y precios coherentes",
};

function pintarAuditoria(a, historial) {
  document.getElementById("sub-auditoria").textContent =
    `Puntaje ${numero(a.puntaje, 1)} / 100 · ${a.problemas.length} problemas en ${numero(a.registros.usuarios)} usuarios, `
    + `${numero(a.registros.productos)} ítems y ${numero(a.registros.facturas)} facturas · revisado en ${numero(a.milisegundos, 1)} ms.`;
  vaciar(document.getElementById("dimensiones"),
    el("div", { class: "dimension" }, el("strong", { text: `${numero(a.puntaje, 1)}` }), el("span", { text: "Puntaje general" })),
    ...Object.entries(a.dimensiones).map(([k, v]) => el("div", { class: "dimension" }, el("strong", { text: `${numero(v, 1)} %` }),
      el("span", { text: `${k[0].toUpperCase() + k.slice(1)}: ${DIMENSIONES[k]}` }))));
  vaciar(document.getElementById("t-problemas"), tablaDatos([
    { titulo: "Problema", valor: (p) => el("strong", { text: NOMBRES[p.tipo] || p.tipo }) },
    { titulo: "Registros", valor: (p) => p.registros.map((r) => r.valor).join(" · ") },
    { titulo: "Por qué", valor: (p) => p.detalle },
    { titulo: "Corrección", valor: (p) => el("span", {}, p.correccion || "—", " ", p.automatica ? etiqueta("automática", "ok") : etiqueta("revisión humana", "alerta")) },
  ], a.problemas, "Sin problemas: los datos están limpios."));
  vaciar(document.getElementById("t-historial"), tablaDatos([
    { titulo: "Fecha", valor: (h) => fechaCorta(h.fecha) },
    { titulo: "Fuente", valor: (h) => h.fuente },
    { titulo: "Tipo", valor: (h) => h.tipo },
    { titulo: "Recibidos", valor: (h) => numero(h.recibidos), num: true },
    { titulo: "Válidos", valor: (h) => numero(h.validos), num: true },
    { titulo: "Corregidos", valor: (h) => numero(h.corregidos), num: true },
    { titulo: "Duplicados", valor: (h) => numero(h.duplicados), num: true },
    { titulo: "Descartados", valor: (h) => numero(h.descartados), num: true },
    { titulo: "Puntaje", valor: (h) => numero(h.puntaje, 1), num: true },
  ], historial, "Todavía no hay reportes."));
}

async function auditar() {
  const { ok, datos } = await api("GET", "/api/calidad/auditoria");
  if (!ok) return toast(datos.error, "error");
  pintarAuditoria(datos.auditoria, datos.historial);
}

document.getElementById("corregir").addEventListener("click", async () => {
  const { ok, datos } = await api("POST", "/api/calidad/corregir");
  if (!ok) return toast(datos.error, "error");
  const aviso = document.getElementById("resultado-correccion");
  aviso.hidden = false;
  const hechos = Object.entries(datos.corregidos).map(([t, n]) => `${n} ${(NOMBRES[t] || t).toLowerCase()}`).join(", ");
  aviso.querySelector("p").textContent = `Puntaje ${numero(datos.antes, 1)} → ${numero(datos.despues, 1)}. Corregido: ${hechos || "nada pendiente"}. `
    + "Lo que necesita criterio humano (mismo nombre con distinto correo, precios raros) sigue en la lista.";
  auditar();
});

const form = document.getElementById("form-importar");
form.addEventListener("submit", async (evento) => {
  evento.preventDefault();
  form.querySelectorAll(".campo").forEach((c) => c.classList.remove("invalido"));
  const cuerpo = new FormData(form);
  if (!form.aplicar.checked) cuerpo.delete("aplicar");
  const respuesta = await fetch("/api/calidad/importar", { method: "POST", body: cuerpo, credentials: "same-origin",
    headers: { "X-CSRF-Token": csrf(), Accept: "application/json" } });
  const datos = await respuesta.json().catch(() => ({ error: "Respuesta inválida" }));
  if (!respuesta.ok) {
    if (!mostrarErrores(form, datos.errores)) toast(datos.error, "error");
    return;
  }
  const r = datos.reporte;
  vaciar(document.getElementById("reporte"),
    el("div", { class: "kpis kpis--5" },
      kpi("Recibidos", numero(r.recibidos), `${r.fuente}`, "tabla"),
      kpi("Válidos", numero(r.valido), "sin cambios", "ok", "kpi--ok"),
      kpi("Corregidos", numero(r.corregido), "normalizados", "actualizar"),
      kpi("Duplicados", numero(r.duplicado), "en el archivo o en la base", "alerta", "kpi--alerta"),
      kpi("Descartados", numero(r.descartado), "no cumplen el esquema", "bloqueo", "kpi--critico")),
    el("p", { class: "nota", text: `Calidad del archivo: ${numero(r.puntaje_original, 1)} % de registros válidos tal como llegaron; `
      + `${numero(r.puntaje_final, 1)} % utilizables después de limpiar. ${r.aplicado ? `Se guardaron ${r.guardados} registros.` : "No se guardó nada (solo análisis)."} `
      + `Procesado en ${numero(r.milisegundos, 1)} ms.` }),
    tablaDatos([
      { titulo: "Fila", valor: (f) => String(f.fila), num: true },
      { titulo: "Estado", valor: (f) => etiqueta(...{ VALIDO: ["Válido", "ok"], CORREGIDO: ["Corregido", "vino"],
        DUPLICADO: ["Duplicado", "alerta"], DESCARTADO: ["Descartado", "critico"] }[f.estado]) },
      { titulo: "Original", valor: (f) => Object.values(f.original || {}).join(" · ") },
      { titulo: "Qué se hizo", valor: (f) => (f.errores.length || f.cambios.length
        ? el("ul", { class: "cambios" }, ...[...f.errores, ...f.cambios].map((t) => el("li", { text: t }))) : "Nada: estaba limpio") },
    ], r.resultados));
  auditar();
});

auditar();
