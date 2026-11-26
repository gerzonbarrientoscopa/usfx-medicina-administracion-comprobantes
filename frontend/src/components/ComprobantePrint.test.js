import { buildComprobanteHTML } from "./ComprobantePrint";

test("alinea a la izquierda los datos de generación del comprobante de pago", () => {
  const html = buildComprobanteHTML({});

  expect(html).toMatch(/\.meta\s*\{[^}]*text-align:\s*left;/);
});

test.each([1, 2, 3])(
  "usa carta vertical y reserva media altura con %s concepto",
  (conceptCount) => {
    const html = buildComprobanteHTML({
      items: Array.from({ length: conceptCount }, (_, index) => ({
        id: `item-${index}`,
        tipo_pago_nombre: `Concepto ${index + 1}`,
        cantidad: 1,
        monto: 10,
        total: 10,
      })),
    });

    expect(html).toMatch(/@page\s*\{\s*size:\s*letter;\s*margin:\s*0\.25in;/);
    expect(html).toContain(".receipt { width: 100%; max-width: none; min-height: 5.25in; margin: 0; border: 1px dashed #7A2035;");
  },
);

test("mantiene carta vertical y deja crecer el comprobante con más de tres conceptos", () => {
  const html = buildComprobanteHTML({
    items: Array.from({ length: 4 }, (_, index) => ({
      id: `item-${index}`,
      tipo_pago_nombre: `Concepto ${index + 1}`,
      cantidad: 1,
      monto: 10,
      total: 10,
    })),
  });

  expect(html).toMatch(/@page\s*\{\s*size:\s*letter;\s*margin:\s*0\.25in;/);
  expect(html).toContain(".receipt { width: 100%; max-width: none; min-height: 5.25in;");
  expect(html).toContain("Concepto 4");
});

test("compacta espacios impresos sin cambiar el encabezado ni firma", () => {
  const html = buildComprobanteHTML({});

  expect(html).toContain(".title-bar { margin-top: -16px; margin-bottom: 8px; }");
  expect(html).toContain(".receipt > .row { padding: 2px 0; font-size: 11px; }");
  expect(html).toContain("table tbody td { padding: 3px 8px; }");
  expect(html).toContain(".totals { margin-top: 4px; }");
  expect(html).toContain(".meta { font-size: 8px; }");
  expect(html).toContain(".sign { width: 220px; text-align: center; font-size: 11px;");
});

test("oculta los botones de imprimir y cerrar en el papel", () => {
  const html = buildComprobanteHTML({});

  expect(html).toContain('<div class="toolbar no-print">');
  expect(html).toContain(".no-print, .toolbar { display: none !important; }");
});