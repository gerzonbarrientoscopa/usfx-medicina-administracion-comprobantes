import {
    buildReportSections,
    summarizeReportSections,
} from "./reportSections";

const concepts = [
    { id: "tuition", codigo: "10001", nombre: "Matrícula" },
    { id: "insurance", codigo: "10002", nombre: "Seguro" },
];

const payments = [
    {
        id: "receipt-one",
        total: 30,
        anulado: false,
        items: [
            { id_tipo_pago: "tuition", tipo_pago_nombre: "Matrícula", cantidad: 1, total: 10 },
            { id_tipo_pago: "insurance", tipo_pago_nombre: "Seguro", cantidad: 2, total: 20 },
        ],
    },
    {
        id: "receipt-two",
        total: 5,
        anulado: true,
        items: [
            { id_tipo_pago: "tuition", tipo_pago_nombre: "Matrícula", cantidad: 1, total: 5 },
        ],
    },
];

test("groups cobros by concept and calculates section and grand totals", () => {
    const sections = buildReportSections(payments, [], "Cobro", "all", concepts);

    expect(sections.map((section) => section.title)).toEqual([
        "10001 — Matrícula",
        "10002 — Seguro",
    ]);
    expect(sections.map((section) => section.totals)).toEqual([
        {
            validos: 10,
            anulados: 5,
            diferencia: 5,
            count_validos: 1,
            count_anulados: 1,
        },
        {
            validos: 20,
            anulados: 0,
            diferencia: 20,
            count_validos: 1,
            count_anulados: 0,
        },
    ]);
    expect(sections[0].payments[0].total).toBe(30);
    expect(summarizeReportSections(sections)).toEqual({
        validos: 30,
        anulados: 5,
        diferencia: 25,
        count_validos: 1,
        count_anulados: 1,
    });
});

test("filters report sections to one selected concept", () => {
    const sections = buildReportSections(
        payments,
        [],
        "Cobro",
        "insurance",
        concepts,
    );

    expect(sections).toHaveLength(1);
    expect(sections[0].key).toBe("insurance");
    expect(sections[0].payments).toHaveLength(1);
    expect(sections[0].totals.validos).toBe(20);
});

test("groups legacy single-concept receipts by their saved concept id", () => {
    const sections = buildReportSections(
        [{
            id: "legacy-receipt",
            id_tipo_pago: "tuition",
            tipo_pago_nombre: "Matrícula",
            total: 12,
        }],
        [],
        "Cobro",
        "tuition",
        concepts,
    );

    expect(sections).toHaveLength(1);
    expect(sections[0].totals.validos).toBe(12);
});

test("shows rentals in a separate section without the concept filter", () => {
    const rentals = [{
        id: "rental-one",
        estado: "pagado",
        fecha_pago: "2026-09-30",
        total: 45,
        ambiente_nombre: "Auditorio",
        tarifa_nombre: "Por hora",
    }];
    const sections = buildReportSections(
        payments,
        rentals,
        "Alquiler",
        "insurance",
        concepts,
    );

    expect(sections).toHaveLength(1);
    expect(sections[0].title).toBe("Alquileres");
    expect(sections[0].totals.validos).toBe(45);
    expect(sections[0].payments[0].origen).toBe("Alquiler");
});
