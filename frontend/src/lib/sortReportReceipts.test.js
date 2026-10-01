import { sortReportReceipts } from "./sortReportReceipts";

test("sorts report receipts by ascending date and then numeric receipt number", () => {
    const sorted = sortReportReceipts([
        { id: "later-code", fecha_pago: "30/09/2026", cod_comprobante: "00010", prefijo_comprobante: "A" },
        { id: "later-date", fecha_pago: "01/10/2026", cod_comprobante: "00001", prefijo_comprobante: "A" },
        { id: "earlier-date", fecha_pago: "29/09/2026", cod_comprobante: "00099", prefijo_comprobante: "A" },
        { id: "same-code-b", fecha_pago: "30/09/2026", cod_comprobante: "00002", prefijo_comprobante: "B" },
        { id: "same-code-a", fecha_pago: "30/09/2026", cod_comprobante: "00002", prefijo_comprobante: "A" },
    ]);

    expect(sorted.map(({ id }) => id)).toEqual([
        "earlier-date",
        "same-code-a",
        "same-code-b",
        "later-code",
        "later-date",
    ]);
});

test("does not mutate the source rows", () => {
    const source = [
        { id: "second", fecha_pago: "02/10/2026", cod_comprobante: "00002" },
        { id: "first", fecha_pago: "01/10/2026", cod_comprobante: "00001" },
    ];

    sortReportReceipts(source);

    expect(source.map(({ id }) => id)).toEqual(["second", "first"]);
});