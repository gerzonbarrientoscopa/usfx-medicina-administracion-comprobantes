export function formatComprobante(pago) {
  if (pago?.comprobante_display) return pago.comprobante_display;
  const codigo = String(pago?.cod_comprobante ?? "").padStart(5, "0");
  const gestion = String(pago?.gestion ?? "").padStart(4, "0");
  const prefijo = pago?.prefijo_comprobante;
  return `${prefijo ? `${prefijo}-` : ""}${codigo} / ${gestion}`;
}