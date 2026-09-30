import { buildReportPdfRows } from "./reportPdfRows";

test("leaves row-spanned receipt cells out of subsequent concept rows", () => {
    const payment = {
        total: 30,
        items: [
            { tipo_pago_nombre: "Concepto 1", cantidad: 1, total: 10 },
            { tipo_pago_nombre: "Concepto 2", cantidad: 2, total: 20 },
        ],
    };

    const rows = buildReportPdfRows(
        [payment],
        (_payment, rowSpan) => [
            { content: "R-1", rowSpan },
            { content: "Cliente", rowSpan },
            { content: "30/09/2026", rowSpan },
        ],
        (_payment, { item, amount }) => [
            item.tipo_pago_nombre,
            item.cantidad,
            amount,
        ],
    );

    expect(rows).toEqual([
        [
            { content: "R-1", rowSpan: 2 },
            { content: "Cliente", rowSpan: 2 },
            { content: "30/09/2026", rowSpan: 2 },
            "Concepto 1",
            1,
            10,
        ],
        ["Concepto 2", 2, 20],
    ]);
});