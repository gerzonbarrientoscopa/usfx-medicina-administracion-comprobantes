import { buildComprobanteHTML } from "./ComprobantePrint";

test("alinea a la izquierda los datos de generación del comprobante de pago", () => {
  const html = buildComprobanteHTML({});

  expect(html).toMatch(/\.meta\s*\{[^}]*text-align:\s*left;/);
});

test.each([1, 2, 3])(
  "usa media carta para pagos con %s concepto",
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

    expect(html).toMatch(/@page\s*\{\s*size:\s*5\.5in 8\.5in;\s*margin:\s*0\.25in;/);
  },
);

test("permite exceder media carta con más de tres conceptos", () => {
  const html = buildComprobanteHTML({
    items: Array.from({ length: 4 }, (_, index) => ({
      id: `item-${index}`,
      tipo_pago_nombre: `Concepto ${index + 1}`,
      cantidad: 1,
      monto: 10,
      total: 10,
    })),
  });

  expect(html).not.toMatch(/@page\s*\{\s*size:/);
  expect(html).toContain(".receipt { width: 100%; max-width: none;");
});

test("oculta los botones de imprimir y cerrar en el papel", () => {
  const html = buildComprobanteHTML({});

  expect(html).toContain('<div class="toolbar no-print">');
  expect(html).toContain(".no-print, .toolbar { display: none !important; }");
});