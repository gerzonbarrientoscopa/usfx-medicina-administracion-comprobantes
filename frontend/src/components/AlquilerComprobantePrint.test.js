import { buildAlquilerComprobanteHTML } from "./AlquilerComprobantePrint";

test("incluye la suboficina en el encabezado y escapa el texto", () => {
  const html = buildAlquilerComprobanteHTML({
    id: "rental-1",
    cliente_tipo: "persona",
    office_nombre: "Oficina Central",
    suboficina: "Suboficina <Norte>",
  });

  expect(html).toContain('<div class="office">Oficina Central</div>');
  expect(html).toContain('<div class="suboffice">Suboficina &lt;Norte&gt;</div>');
});

test("omite la suboficina vacía", () => {
  const html = buildAlquilerComprobanteHTML({
    id: "rental-2",
    office_nombre: "Oficina Central",
  });

  expect(html).not.toContain('class="suboffice"');
});

test("muestra las fechas de alquiler en formato dd/mm/yyyy", () => {
  const html = buildAlquilerComprobanteHTML({
    id: "rental-3",
    fecha: "2026-09-03",
    fecha_pago: "03/09/2026",
  });

  expect(html).toContain('<strong>03/09/2026</strong>');
  expect(html).toContain('<strong>03/09/2026</strong>');
});