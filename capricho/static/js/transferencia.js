/*
 * Formulario de transferencia en vivo (lo usan /en-vivo y /transferir).
 * Los casos rápidos llenan el formulario con un cliente real de la demo
 * (habitual) o con uno nuevo, para comparar cómo decide la IA.
 */

import { api, dinero, el, icono, insignia, mostrarErrores, toast, vaciar } from "./comun.js";

export async function iniciarTransferencia(alResultado) {
  const form = document.getElementById("form-transferencia");
  const salida = document.getElementById("resultado-transferencia");
  const { ok, datos } = await api("GET", "/api/vivo/sugerencias");
  const clientes = ok ? datos.clientes : [];
  // Cada caso usa un cliente distinto: varias pruebas seguidas con el mismo
  // cliente cambiarían su frecuencia reciente (y la IA lo notaría).
  let turno = 0;
  const habitual = () => clientes[turno++ % clientes.length];
  const nuevo = () => `nuevo.${Math.random().toString(16).slice(2, 6)}@correo.co`;
  const otroMetodo = (metodo) => (metodo === "PSE" ? "Tarjeta" : "PSE");

  const casos = [
    clientes.length && ["Cliente habitual, compra normal", "Su monto y su método de siempre", () => {
      const c = habitual();
      return { email: c.email, valor: c.monto_habitual, metodo: c.metodo };
    }],
    clientes.length && ["Cuenta tomada", "Un cliente habitual: 20 veces su monto y otro método", () => {
      const c = habitual();
      return { email: c.email, valor: Math.min(600000, c.monto_habitual * 20), metodo: otroMetodo(c.metodo) };
    }],
    ["Cliente nuevo, compra normal", "Sin historial: $12.000 con Nequi", () => ({ email: nuevo(), valor: 12000, metodo: "Nequi" })],
    ["Cliente nuevo, monto alto", "Sin historial: $480.000 con PSE", () => ({ email: nuevo(), valor: 480000, metodo: "PSE" })],
  ].filter(Boolean);

  vaciar(document.getElementById("escenarios"), ...casos.map(([titulo, detalle, armar]) =>
    el("button", { class: "escenario-vivo", type: "button", onClick: () => {
      const valores = armar();
      form.email.value = valores.email;
      form.valor.value = valores.valor;
      form.metodo.value = valores.metodo;
      form.alterar_firma.checked = false;
      form.rafaga.checked = false;
      form.requestSubmit();
    } }, el("strong", { text: titulo }), el("span", { text: detalle }))));
  form.email.value = clientes.length ? clientes[clientes.length - 1].email : nuevo();

  form.addEventListener("submit", async (evento) => {
    evento.preventDefault();
    form.querySelectorAll(".campo").forEach((c) => c.classList.remove("invalido"));
    const boton = form.querySelector("button[type=submit]");
    boton.disabled = true;
    const respuesta = await api("POST", "/api/vivo/transferir", {
      email: form.email.value.trim(), valor: Number(form.valor.value), metodo: form.metodo.value,
      alterar_firma: form.alterar_firma.checked, repetir: form.rafaga.checked ? 6 : 1,
    });
    boton.disabled = false;
    if (!respuesta.ok) {
      if (!mostrarErrores(form, respuesta.datos.errores)) toast(respuesta.datos.error || "No se pudo transferir", "error");
      return;
    }
    const ultima = respuesta.datos.resultados.at(-1);
    salida.hidden = false;
    vaciar(salida, resumen(ultima, respuesta.datos.resultados.length));
    alResultado?.(respuesta.datos.resultados);
  });
}

/** Lo que ve quien transfiere: el estado y la razón principal. */
export function resumen(resultado, cantidad = 1) {
  const a = resultado.analisis || {};
  const c = a.clasificador;
  const motivo = resultado.anomalias?.[0]?.detalle || (c ? `Probabilidad de fraude ${c.porcentaje} %: normal.` : "Sin anomalías.");
  return el("div", { class: `resultado-vivo__caja resultado-vivo__caja--${resultado.estado}` },
    el("div", { class: "resultado-vivo__cabeza" }, insignia(resultado.estado),
      el("strong", { text: `${dinero(resultado.valor)} · ${resultado.idTxn}` }),
      cantidad > 1 ? el("span", { class: "muted", text: `(${cantidad} enviadas)` }) : null),
    c ? el("p", {}, icono("rayo"), ` Red neuronal: ${c.porcentaje} % de probabilidad de fraude · ${c.segmento} · `
      + `${c.conocimiento.general} % conocimiento general`) : null,
    el("p", { class: "muted", text: motivo }));
}
