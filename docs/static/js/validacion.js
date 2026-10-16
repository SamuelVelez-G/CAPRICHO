/*
 * Validación en el navegador: da mensajes inmediatos mientras se escribe.
 * Son las MISMAS reglas de capricho/validaciones.py, pero esta capa se puede
 * saltar (curl, Postman, editar el HTML). La que decide es la del servidor.
 */

const RE_NOMBRE = /^[A-Za-zÁÉÍÓÚÜÑáéíóúüñ]+( [A-Za-zÁÉÍÓÚÜÑáéíóúüñ]+)*$/;
const RE_EMAIL = /^[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}$/;
const RE_DIRECCION = /^[A-Za-z0-9ÁÉÍÓÚÜÑáéíóúüñ#.,°/\- ]+$/;

// Mismos patrones que seguridad.py (versión resumida para el aviso rápido).
const PATRONES_SQL = [
  /--|\/\*|\*\//,
  /['"`]\s*\)?\s*(or|and|\|\||&&)\b/i,
  /\b(or|and)\b\s+['"]?[\w@.]+['"]?\s*(=|<|>|like)/i,
  /\bunion\b(\s+all)?\s+select\b/i,
  /\bselect\b[\s\S]+\bfrom\b/i,
  /\b(drop|truncate|alter)\s+(table|database|schema)\b/i,
  /\b(insert\s+into|delete\s+from|update\s+\w+\s+set)\b/i,
  /;\s*\w/,
];

const limpiar = (v) => (v ?? "").trim().replace(/\s+/g, " ");

export function pareceInyeccion(texto) {
  return PATRONES_SQL.some((p) => p.test(texto));
}

export const reglas = {
  requerido(valor) {
    return limpiar(valor) ? null : "Este campo es obligatorio y no puede estar vacío";
  },
  nombre(valor) {
    const v = limpiar(valor);
    if (!v) return "El nombre es obligatorio";
    if (!RE_NOMBRE.test(v)) return "Solo se permiten letras y espacios";
    if ((v.match(/\p{L}/gu) || []).length < 4) return "Debe tener más de 3 letras";
    if (v.length > 60) return "Máximo 60 caracteres";
    return null;
  },
  email(valor) {
    const v = limpiar(valor);
    if (!v) return "El correo es obligatorio";
    if (v.length > 120 || v.includes("..") || !RE_EMAIL.test(v)) return "No es un correo válido (ejemplo: nombre@correo.com)";
    return null;
  },
  telefono(valor) {
    const v = (valor ?? "").replace(/[\s-]/g, "");
    if (!v) return "El celular es obligatorio";
    if (!/^3\d{9}$/.test(v)) return "Debe ser un celular colombiano de 10 dígitos que empiece por 3";
    return null;
  },
  password(valor) {
    if (!valor) return "La contraseña es obligatoria";
    const faltan = requisitosPassword(valor).filter((r) => !r.cumple).map((r) => r.texto);
    return faltan.length ? "Le falta: " + faltan.join(", ") : null;
  },
  direccion(valor) {
    const v = limpiar(valor);
    if (!v) return "La dirección es obligatoria";
    if (v.length < 6 || v.length > 120) return "Entre 6 y 120 caracteres";
    if (!RE_DIRECCION.test(v)) return "Solo letras, números y # . , - /";
    if (!/\d/.test(v)) return "Incluye el número de la dirección";
    return null;
  },
};

export function requisitosPassword(valor = "") {
  return [
    { texto: "8 a 64 caracteres", cumple: valor.length >= 8 && valor.length <= 64 },
    { texto: "una minúscula", cumple: /[a-z]/.test(valor) },
    { texto: "una mayúscula", cumple: /[A-Z]/.test(valor) },
    { texto: "un número", cumple: /\d/.test(valor) },
    { texto: "un símbolo", cumple: /[^A-Za-z0-9]/.test(valor) },
  ];
}

/**
 * Conecta un formulario: cada campo con data-regla se valida al salir de él
 * y, una vez marcado, mientras se escribe. Devuelve validar() para el envío.
 */
export function conectarFormulario(formulario, extras = {}) {
  const campos = [...formulario.querySelectorAll("[data-regla]")];

  function revisar(entrada) {
    const caja = entrada.closest(".campo");
    const regla = extras[entrada.name] || reglas[entrada.dataset.regla];
    let error = regla ? regla(entrada.value, formulario) : null;
    if (!error && entrada.type !== "password" && pareceInyeccion(entrada.value)) {
      error = "Contiene caracteres o palabras no permitidas (posible inyección SQL)";
    }
    caja.classList.toggle("invalido", Boolean(error));
    caja.classList.toggle("valido", !error && Boolean(entrada.value));
    caja.querySelector(".campo__error span").textContent = error || "";
    entrada.setAttribute("aria-invalid", error ? "true" : "false");
    return !error;
  }

  for (const entrada of campos) {
    entrada.addEventListener("blur", () => { entrada.dataset.tocado = "1"; revisar(entrada); });
    entrada.addEventListener("input", () => { if (entrada.dataset.tocado) revisar(entrada); });
  }

  return function validar() {
    let valido = true;
    let primero = null;
    for (const entrada of campos) {
      entrada.dataset.tocado = "1";
      if (!revisar(entrada)) {
        valido = false;
        primero ??= entrada;
      }
    }
    primero?.focus();
    return valido;
  };
}
