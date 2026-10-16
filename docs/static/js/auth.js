/* Formularios de ingreso y registro. */

import { api, el, mostrarErrores, vaciar } from "./comun.js";
import { conectarFormulario, requisitosPassword } from "./validacion.js";

function mostrarErrorGeneral(mensaje) {
  const caja = document.getElementById("error-general");
  caja.hidden = !mensaje;
  caja.querySelector("p").textContent = mensaje || "";
}

function enviarCon(formulario, ruta, cuerpo) {
  const boton = formulario.querySelector('button[type="submit"]');
  return async () => {
    boton.disabled = true;
    const { status, datos } = await api("POST", ruta, cuerpo());
    boton.disabled = false;
    if (status === 200 || status === 201) {
      window.location.href = formulario.dataset.siguiente || "/";
      return;
    }
    mostrarErrorGeneral(datos.error);
    if (datos.errores) mostrarErrores(formulario, datos.errores);
  };
}

const ingresar = document.getElementById("form-ingresar");
if (ingresar) {
  const validar = conectarFormulario(ingresar);
  const enviar = enviarCon(ingresar, "/api/auth/login", () => ({
    email: ingresar.email.value.trim(), password: ingresar.password.value,
  }));
  ingresar.addEventListener("submit", (evento) => {
    evento.preventDefault();
    mostrarErrorGeneral("");
    if (validar()) enviar();
  });
}

const registro = document.getElementById("form-registro");
if (registro) {
  const validar = conectarFormulario(registro, {
    confirmacion: (valor, form) => (!valor ? "Confirma la contraseña"
      : valor !== form.password.value ? "Las contraseñas no coinciden" : null),
  });
  const lista = document.getElementById("requisitos");
  const pintarRequisitos = () => vaciar(lista, ...requisitosPassword(registro.password.value).map((r) =>
    el("li", { class: r.cumple ? "cumple" : "", text: (r.cumple ? "✓ " : "") + r.texto })));
  registro.password.addEventListener("input", pintarRequisitos);
  pintarRequisitos();

  const enviar = enviarCon(registro, "/api/auth/registro", () => ({
    nombre: registro.nombre.value, email: registro.email.value.trim(), telefono: registro.telefono.value,
    password: registro.password.value, confirmacion: registro.confirmacion.value,
  }));
  registro.addEventListener("submit", (evento) => {
    evento.preventDefault();
    mostrarErrorGeneral("");
    if (validar()) enviar();
  });
}
