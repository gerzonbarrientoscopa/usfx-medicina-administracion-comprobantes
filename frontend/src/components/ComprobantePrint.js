import React from "react";

const INSTITUTION = {
    linea1: "Universidad Mayor, Real y Pontificia de San Francisco Xavier",
    linea2: "Facultad de Medicina",
    linea3: "Administración",
};

export function buildComprobanteHTML(p) {
    const fecha = (p.fecha_pago || "").substring(0, 10);
    const moneyFmt = (n) =>
        Number(n || 0).toLocaleString("es-BO", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    const generadoEn = new Date().toLocaleString("es-BO");

    return `<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8" />
<title>Comprobante ${p.codcomprobante}/${p.gestion}</title>
<style>
  @import url("https://fonts.googleapis.com/css2?family=Cormorant+Garamond:wght@600;700&family=IBM+Plex+Sans:wght@400;500;600&display=swap");
  * { box-sizing: border-box; }
  body { font-family: "IBM Plex Sans", sans-serif; color: #1c1c1e; margin: 0; padding: 24px; background: #fff; }
  .receipt { max-width: 720px; margin: 0 auto; border: 1px dashed #7A2035; padding: 32px 40px; background: #fff; }
  .header { display: flex; align-items: flex-start; justify-content: space-between; border-bottom: 2px solid #7A2035; padding-bottom: 12px; margin-bottom: 24px; }
  .header-text h1 { font-family: "Cormorant Garamond", Georgia, serif; font-size: 22px; margin: 0 0 4px 0; color: #1D3557; line-height: 1.15; max-width: 460px; }
  .header-text h2 { font-family: "Cormorant Garamond", Georgia, serif; font-size: 18px; margin: 0; color: #7A2035; font-weight: 600; }
  .header-text h3 { font-family: "IBM Plex Sans", sans-serif; font-size: 11px; letter-spacing: 0.15em; text-transform: uppercase; color: #636369; margin: 4px 0 0 0; }
  .cod-box { text-align: right; }
  .cod-label { font-size: 10px; letter-spacing: 0.15em; text-transform: uppercase; color: #636369; }
  .cod-num { font-family: "Cormorant Garamond", Georgia, serif; font-size: 28px; font-weight: 700; color: #7A2035; line-height: 1; }
  .title-bar { text-align: center; font-family: "Cormorant Garamond", Georgia, serif; font-size: 20px; font-weight: 700; letter-spacing: 0.1em; text-transform: uppercase; color: #1c1c1e; margin-bottom: 18px; }
  .row { display: flex; justify-content: space-between; gap: 16px; padding: 8px 0; border-bottom: 1px dotted #E5E2DC; font-size: 13px; }
  .row .label { color: #636369; text-transform: uppercase; letter-spacing: 0.08em; font-size: 11px; font-weight: 600; }
  .row .value { font-weight: 500; text-align: right; }
  table { width: 100%; border-collapse: collapse; margin-top: 20px; font-size: 13px; }
  table thead th { background: #FDFBF7; color: #636369; text-transform: uppercase; font-size: 10px; letter-spacing: 0.1em; padding: 8px 10px; text-align: left; border-bottom: 1px solid #E5E2DC; }
  table tbody td { padding: 10px; border-bottom: 1px dotted #E5E2DC; }
  .totals { margin-top: 18px; display: flex; justify-content: flex-end; }
  .totals-box { min-width: 280px; border-top: 2px solid #7A2035; padding-top: 12px; }
  .totals-box .row { border: 0; padding: 4px 0; }
  .grand { font-family: "Cormorant Garamond", Georgia, serif; font-size: 22px; font-weight: 700; color: #7A2035; }
  .footer { margin-top: 36px; display: flex; justify-content: space-between; align-items: flex-end; }
  .sign { width: 220px; text-align: center; font-size: 11px; color: #636369; }
  .sign .line { border-top: 1px solid #1c1c1e; padding-top: 4px; }
  .meta { font-size: 10px; color: #636369; text-align: right; }
  .void-stamp { position: absolute; top: 40%; left: 50%; transform: translate(-50%, -50%) rotate(-18deg); font-family: "Cormorant Garamond", serif; font-size: 90px; color: rgba(208, 0, 0, 0.18); border: 8px solid rgba(208, 0, 0, 0.25); padding: 6px 32px; letter-spacing: 0.08em; pointer-events: none; }
  .receipt-wrap { position: relative; }
  @media print {
    body { padding: 0; }
    .no-print { display: none; }
  }
  .toolbar { max-width: 720px; margin: 0 auto 16px; display: flex; gap: 8px; justify-content: flex-end; }
  .toolbar button { font-family: "IBM Plex Sans", sans-serif; font-size: 13px; padding: 8px 16px; border: 1px solid #E5E2DC; background: #fff; color: #1c1c1e; cursor: pointer; border-radius: 2px; }
  .toolbar button.primary { background: #7A2035; color: #fff; border-color: #7A2035; }
</style>
</head>
<body>
  <div class="toolbar no-print">
    <button class="primary" onclick="window.print()">Imprimir</button>
    <button onclick="window.close()">Cerrar</button>
  </div>
  <div class="receipt-wrap">
    ${p.anulado ? '<div class="void-stamp">ANULADO</div>' : ""}
    <div class="receipt">
      <div class="header">
        <div class="header-text">
          <h1>${INSTITUTION.linea1}</h1>
          <h2>${INSTITUTION.linea2}</h2>
          <h3>${INSTITUTION.linea3}</h3>
        </div>
        <div class="cod-box">
          <div class="cod-label">Comprobante N°</div>
          <div class="cod-num">${p.codcomprobante}/${p.gestion}</div>
        </div>
      </div>

      <div class="title-bar">Comprobante de Pago</div>

      <div class="row"><span class="label">Estudiante</span><span class="value">${p.estudiante_nombre || ""}</span></div>
      <div class="row"><span class="label">C.I.</span><span class="value">${p.estudiante_ci || ""}</span></div>
      <div class="row"><span class="label">C.U.</span><span class="value">${p.estudiante_cu || "-"}</span></div>
      <div class="row"><span class="label">Fecha de Pago</span><span class="value">${fecha}</span></div>

      <table>
        <thead>
          <tr><th>Concepto</th><th style="text-align:right">Cantidad</th><th style="text-align:right">Monto Unit.</th><th style="text-align:right">Subtotal</th></tr>
        </thead>
        <tbody>
          <tr>
            <td>${p.tipopago_nombre || ""}</td>
            <td style="text-align:right">${p.cantidad}</td>
            <td style="text-align:right">Bs. ${moneyFmt(p.monto)}</td>
            <td style="text-align:right">Bs. ${moneyFmt(p.total)}</td>
          </tr>
        </tbody>
      </table>

      <div class="totals">
        <div class="totals-box">
          <div class="row"><span class="label">Total a Pagar</span><span class="value grand">Bs. ${moneyFmt(p.total)}</span></div>
        </div>
      </div>

      <div class="footer">
        <div class="meta">Generado: ${generadoEn}<br />Sistema de Comprobantes USFX</div>
        <div class="sign"><div class="line">Firma y Sello</div></div>
      </div>
    </div>
  </div>
</body>
</html>`;
}

export function printComprobante(pago) {
    const w = window.open("", "PRINT", "height=700,width=800");
    if (!w) return;
    w.document.write(buildComprobanteHTML(pago));
    w.document.close();
    w.focus();
}
