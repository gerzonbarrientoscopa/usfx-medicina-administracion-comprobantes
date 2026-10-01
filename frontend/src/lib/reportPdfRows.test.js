/** @jest-environment node */

import { buildReportPdfRows } from "./reportPdfRows";
import jsPDF from "jspdf";
import autoTable from "jspdf-autotable";

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

test.each(["validos", "anulados", "todos"])(
    "preserves every concept in its PDF columns for %s",
    (mode) => {
        const rows = buildReportPdfRows(
            [{
                items: [
                    { tipo_pago_nombre: "Primero", cantidad: 1, total: 10 },
                    { tipo_pago_nombre: "Segundo", cantidad: 2, total: 20 },
                    { tipo_pago_nombre: "Tercero", cantidad: 3, total: 30 },
                ],
            }, {
                items: [{ tipo_pago_nombre: "Otro comprobante", cantidad: 4, total: 40 }],
            }],
            (_payment, rowSpan) => [
                { content: "Comprobante", rowSpan },
                { content: "Cliente", rowSpan },
                { content: "Fecha", rowSpan },
            ],
            (_payment, { item, amount }) => mode === "todos"
                ? [item.tipo_pago_nombre, amount, ""]
                : [item.tipo_pago_nombre, item.cantidad, amount],
        );
        const doc = new jsPDF({ unit: "pt" });
        autoTable(doc, {
            head: [["Comprobante", "Cliente", "Fecha", "Concepto", "Cantidad / válido", "Total / anulado"]],
            body: rows,
        });

        const body = doc.lastAutoTable.body;
        expect(body[0].cells[0].rowSpan).toBe(3);
        expect(body[1].cells[0]).toBeUndefined();
        expect(body[2].cells[0]).toBeUndefined();
        for (const [index, name, quantity, amount] of [
            [0, "Primero", 1, 10],
            [1, "Segundo", 2, 20],
            [2, "Tercero", 3, 30],
            [3, "Otro comprobante", 4, 40],
        ]) {
            expect(body[index].cells[3].text).toEqual([name]);
            expect(body[index].cells[4].text).toEqual([String(mode === "todos" ? amount : quantity)]);
            expect(body[index].cells[5].text).toEqual([mode === "todos" ? "" : String(amount)]);
        }
        expect(body[3].cells[0].text).toEqual(["Comprobante"]);
    },
);