import { reportConceptRows } from "./reportConceptRows";

describe("reportConceptRows", () => {
    it("creates a complete detail row for each concept and preserves the line amount", () => {
        const rows = reportConceptRows({
            total: 50,
            items: [
                { id: "one", tipo_pago_nombre: "Matrícula", cantidad: 1, monto: 30, total: 30 },
                { id: "two", tipo_pago_nombre: "Seguro", cantidad: 2, monto: 10, total: 20 },
            ],
        });

        expect(rows).toEqual([
            {
                item: { id: "one", tipo_pago_nombre: "Matrícula", cantidad: 1, monto: 30, total: 30 },
                index: 0,
                amount: 30,
            },
            {
                item: { id: "two", tipo_pago_nombre: "Seguro", cantidad: 2, monto: 10, total: 20 },
                index: 1,
                amount: 20,
            },
        ]);
    });

    it("supports legacy single-concept payments", () => {
        const [row] = reportConceptRows({
            id_tipo_pago: "fee",
            tipo_pago_nombre: "Matrícula",
            cantidad: 2,
            monto: 15,
            total: 30,
        });

        expect(row.item.tipo_pago_nombre).toBe("Matrícula");
        expect(row.amount).toBe(30);
    });

    it("calculates a concept amount when the API omits its total", () => {
        const [row] = reportConceptRows({
            items: [{ tipo_pago_nombre: "Material", cantidad: 3, monto: 12.5 }],
        });

        expect(row.amount).toBe(37.5);
    });

    it("keeps a receipt without concept details as one row with its receipt total", () => {
        expect(reportConceptRows({ total: 18 })).toEqual([
            { item: null, index: 0, amount: 18 },
        ]);
    });
});