import { formatDate } from "../lib/dateFormat";

const escapeHTML = (value) => String(value ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#039;" })[c]);
const money = (n) => Number(n || 0).toLocaleString("es-BO", { minimumFractionDigits: 2, maximumFractionDigits: 2 });

export function buildAlquilerComprobanteHTML(rental) {
  const person = rental.cliente_tipo === "persona";
  const suboficina = String(rental.suboficina || "").trim();
  const ranges = (rental.tramos || []).map((r) => `${escapeHTML(r.desde)}–${escapeHTML(r.hasta)}`).join(" · ") || "Jornada completa";
  const date = formatDate(rental.fecha);
  const paymentDate = rental.fecha_pago ? formatDate(rental.fecha_pago) : "—";
  const generatedAtDate = new Date();
  const generatedAt = escapeHTML(`${formatDate(generatedAtDate)} ${generatedAtDate.toLocaleTimeString("es-BO")}`);
  return `<!doctype html><html lang="es"><head><meta charset="utf-8"><title>Comprobante de alquiler ${escapeHTML(rental.comprobante_display || rental.cod_comprobante || rental.id)}</title><style>
  *{box-sizing:border-box}body{font:14px "IBM Plex Sans",Arial,sans-serif;color:#263340;margin:0;padding:28px;background:#fff}.sheet{max-width:720px;margin:auto;border:1px dashed #7A2035;padding:34px 40px}.head{display:flex;justify-content:space-between;gap:20px;border-bottom:2px solid #7A2035;padding-bottom:16px;margin-bottom:24px}.institution{font:600 21px Georgia,serif;color:#1D3557;max-width:440px}.office{margin-top:7px;color:#7A2035;font-weight:600}.suboffice{margin-top:4px;color:#636369;font-size:10px;font-weight:600;letter-spacing:.15em;text-transform:uppercase}.code{text-align:right;color:#7A2035;font:700 24px Georgia,serif;white-space:nowrap}.label{font-size:10px;text-transform:uppercase;letter-spacing:.12em;color:#777}.title{text-align:center;font:700 21px Georgia,serif;letter-spacing:.08em;text-transform:uppercase;margin:18px 0}.row{display:flex;justify-content:space-between;gap:18px;padding:10px 0;border-bottom:1px dotted #dedbd5}.row strong{text-align:right}.total{display:flex;justify-content:space-between;border-top:2px solid #7A2035;margin-top:22px;padding-top:14px;font-size:18px;font-weight:700;color:#7A2035}.foot{margin-top:42px;display:flex;justify-content:space-between;color:#777;font-size:11px}.meta{font-size:10px;color:#636369;text-align:right}.sign{width:220px;border-top:1px solid #263340;padding-top:5px;text-align:center}@media print{body{padding:0}.sheet{border:0}}</style></head><body><main class="sheet">
  <header class="head"><div><div class="institution">Universidad Mayor, Real y Pontificia de San Francisco Xavier</div><div class="office">${escapeHTML(rental.office_nombre || "Oficina")}</div>${suboficina ? `<div class="suboffice">${escapeHTML(suboficina)}</div>` : ""}</div><div class="code"><div class="label">Comprobante</div>${escapeHTML(rental.comprobante_display || rental.cod_comprobante || `AL-${rental.id}`)}</div></header>
  <div class="title">Recibo de alquiler de ambiente</div>
  <div class="row"><span class="label">Cliente · ${person ? "Persona" : "Estudiante"}</span><strong>${escapeHTML(rental.cliente_nombre)}</strong></div>
  <div class="row"><span class="label">C.I.</span><strong>${escapeHTML(rental.cliente_ci || "—")}</strong></div>
  ${person ? "" : `<div class="row"><span class="label">C.U.</span><strong>${escapeHTML(rental.cliente_cu || "—")}</strong></div>`}
  <div class="row"><span class="label">Ambiente</span><strong>${escapeHTML(rental.ambiente_nombre)}</strong></div>
  <div class="row"><span class="label">Fecha de uso</span><strong>${escapeHTML(date)}</strong></div>
  <div class="row"><span class="label">Fecha de pago</span><strong>${escapeHTML(paymentDate)}</strong></div>
  <div class="row"><span class="label">Horario reservado</span><strong>${ranges}</strong></div>
  <div class="row"><span class="label">Tarifa</span><strong>${escapeHTML(rental.tarifa_nombre || rental.modalidad)}</strong></div>
  <div class="total"><span>Total pagado</span><span>Bs. ${money(rental.total)}</span></div>
  <footer class="foot"><div class="meta">Generado: ${generatedAt}<br />Sistema de Comprobantes USFX</div><span class="sign">Firma y sello</span></footer>
  </main><script>window.onload=function(){window.print()}</script></body></html>`;
}

export function printAlquilerComprobante(rental, printWindow) {
  if (rental?.estado !== "pagado") return false;
  const win = printWindow || window.open("", "ALQUILER_PRINT", "height=760,width=820");
  if (!win) return false;
  win.document.open();
  win.document.write(buildAlquilerComprobanteHTML(rental));
  win.document.close();
  win.focus();
  return true;
}