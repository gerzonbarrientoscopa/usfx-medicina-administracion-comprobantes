import {
  buildAlquilerComprobanteHTML,
  printAlquilerComprobante,
} from "./AlquilerComprobantePrint";

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

test("incluye la fecha de generación y el nombre del sistema en el pie", () => {
  const html = buildAlquilerComprobanteHTML({ id: "rental-4" });

  expect(html).toMatch(/Generado: \d{2}\/\d{2}\/\d{4} \d{1,2}:\d{2}:\d{2} [ap]\.\s*m\./i);
  expect(html).toContain("<br />Sistema de Comprobantes USFX");
  expect(html).toMatch(/\.meta\{[^}]*text-align:left/);
});

test("marca como anulado el comprobante de un alquiler cancelado", () => {
  const html = buildAlquilerComprobanteHTML({
    id: "rental-5",
    estado: "cancelado",
    cod_comprobante: "00014",
  });

  expect(html).toContain('<div class="void-stamp" aria-label="Comprobante anulado">ANULADO</div>');
});

test("permite reimprimir un alquiler cancelado si conserva su comprobante", () => {
  const printWindow = {
    document: {
      open: jest.fn(),
      write: jest.fn(),
      close: jest.fn(),
    },
    focus: jest.fn(),
  };

  expect(printAlquilerComprobante({
    id: "rental-6",
    estado: "cancelado",
    cod_comprobante: "00014",
  }, printWindow)).toBe(true);
  expect(printWindow.document.write).toHaveBeenCalledWith(
    expect.stringContaining("Comprobante anulado"),
  );
});

test("no permite imprimir una reserva cancelada sin comprobante", () => {
  expect(printAlquilerComprobante({ id: "rental-7", estado: "cancelado" }, {})).toBe(false);
});