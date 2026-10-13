import React from "react";
import { AlertTriangle, Clock3 } from "lucide-react";

export default function PaginaErrorAccesoInstitucional({ error }) {
  const expired = error?.kind === "expired";
  const unavailable = error?.kind === "unavailable";
  const Icon = expired ? Clock3 : AlertTriangle;
  const title = expired
    ? "Enlace caducado"
    : unavailable
      ? "No se pudo verificar el acceso"
      : "Acceso no autorizado";
  const description = expired
    ? "El enlace institucional venció. Vuelva al portal institucional e ingrese nuevamente para generar un enlace vigente."
    : unavailable
      ? "No fue posible verificar el enlace en este momento. Intente nuevamente desde el portal institucional."
      : "El enlace está incompleto o no corresponde a un usuario habilitado. Solicite un nuevo acceso desde el portal institucional.";

  return (
    <main
      className="min-h-screen flex items-center justify-center px-4 py-12 bg-paper"
      data-testid="error-acceso-institucional"
    >
      <section
        className="w-full max-w-md border bg-white px-8 py-10 text-center shadow-none"
        style={{ borderColor: "var(--institution-border)" }}
        aria-labelledby="titulo-error-acceso-institucional"
      >
        <div
          className="mx-auto mb-5 flex h-16 w-16 items-center justify-center text-white"
          style={{ backgroundColor: "var(--institution-burgundy)" }}
          aria-hidden="true"
        >
          <Icon size={30} strokeWidth={1.7} />
        </div>
        <div className="section-eyebrow mb-2">Acceso institucional</div>
        <h1
          id="titulo-error-acceso-institucional"
          className="font-serif-display text-3xl leading-tight"
          style={{ color: "var(--institution-text)" }}
        >
          {title}
        </h1>
        <p className="mt-4 text-sm leading-relaxed text-[color:var(--institution-muted)]">
          {description}
        </p>
      </section>
    </main>
  );
}
