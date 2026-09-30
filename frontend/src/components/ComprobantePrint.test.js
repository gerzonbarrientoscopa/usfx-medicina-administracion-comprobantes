import { buildComprobanteHTML } from "./ComprobantePrint";

test("alinea a la izquierda los datos de generación del comprobante de pago", () => {
  const html = buildComprobanteHTML({});

  expect(html).toMatch(/\.meta\s*\{[^}]*text-align:\s*left;/);
});