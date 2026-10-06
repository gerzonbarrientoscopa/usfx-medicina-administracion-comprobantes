import { buildReportRows } from "./reportRows";

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
