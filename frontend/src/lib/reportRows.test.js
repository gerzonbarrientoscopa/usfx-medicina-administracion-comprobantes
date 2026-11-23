import {
    buildReportRows,
    buildReportSpreadsheetRows,
    buildReportTableRows,
} from "./reportRows";

test("marks annulled payments and rentals consistently for all report outputs", () => {
    const rows = buildReportRows(
        [
            { id: "void-payment", fecha_pago: "2026-03-12", anulado: true },
            { id: "valid-payment", fecha_pago: "2026-03-12", anulado: false },
        ],
        [
            { id: "void-rental", fecha_pago: "2026-03-12", estado: "cancelado" },
            { id: "valid-rental", fecha_pago: "2026-03-12", estado: "pagado" },
        ],
    );

    expect(rows.find((row) => row.id === "void-payment")).toMatchObject({
        origen: "Cobro",
        anulado: true,
    });
    expect(rows.find((row) => row.id === "valid-payment")).toMatchObject({
        origen: "Cobro",
        anulado: false,
    });
    expect(rows.find((row) => row.id === "void-rental")).toMatchObject({
        origen: "Alquiler",
        anulado: true,
    });
    expect(rows.find((row) => row.id === "valid-rental")).toMatchObject({
        origen: "Alquiler",
        anulado: false,
    });
});

test("includes each customer's name in on-screen and spreadsheet report rows", () => {
    const payments = buildReportRows(
        [{
            id: "payment-1",
            cliente_nombre: "Ana Pérez",
            fecha_pago: "2026-03-12",
            cod_comprobante: "00001",
            prefijo_comprobante: "ABC",
            gestion: 2026,
            total: 20,
            items: [{ id: "item-1", tipo_pago_nombre: "Matrícula", cantidad: 1, total: 20 }],
        }],
        [{
            id: "rental-1",
            cliente_nombre: "Luis Gómez",
            fecha_pago: "2026-03-13",
            cod_comprobante: "00002",
            prefijo_comprobante: "ABC",
            gestion: 2026,
            estado: "pagado",
            total: 30,
        }],
    );
    const tableRows = buildReportTableRows(payments);
    const allExport = buildReportSpreadsheetRows(payments, "todos");
    const validExport = buildReportSpreadsheetRows(payments, "validos");

    expect(tableRows.map(({ payment }) => payment.cliente_nombre)).toEqual([
        "Ana Pérez",
        "Luis Gómez",
    ]);
    expect(allExport.headers).toContain("Cliente");
    expect(allExport.rows.map((row) => row[2])).toEqual(["Ana Pérez", "Luis Gómez"]);
    expect(validExport.rows[0][2]).toBe("Ana Pérez");
});

test("exports only the requested annulment mode without dropping customer names", () => {
    const payments = buildReportRows(
        [
            { id: "valid", cliente_nombre: "Cliente válido", anulado: false },
            { id: "void", cliente_nombre: "Cliente anulado", anulado: true },
        ],
    );

    expect(buildReportSpreadsheetRows(payments, "validos").rows.map((row) => row[2]))
        .toEqual(["Cliente válido"]);
    expect(buildReportSpreadsheetRows(payments, "anulados").rows.map((row) => row[2]))
        .toEqual(["Cliente anulado"]);
});
