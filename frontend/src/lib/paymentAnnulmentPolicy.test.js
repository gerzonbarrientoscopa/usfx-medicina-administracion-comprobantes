import { canAnnulPayment } from "./paymentAnnulmentPolicy";

// 03:30 UTC is still 23:30 on the previous day in Bolivia.
const today = new Date("2026-10-01T03:30:00Z");

test.each(["Administrador", "SuperAdmin"])(
    "%s can annul a payment regardless of its printed date",
    (rol) => {
        expect(canAnnulPayment({
            fecha_pago: "01/01/2020",
            created_by: "other-user",
        }, { id: "manager", rol }, today)).toBe(true);
    },
);

test("Caja can annul its own payment dated today", () => {
    expect(canAnnulPayment({
        fecha_pago: "30/09/2026",
        created_by: "cashier-1",
    }, { id: "cashier-1", rol: "Caja" }, today)).toBe(true);
});

test("Caja cannot annul another user's payment or one dated before today", () => {
    expect(canAnnulPayment({
        fecha_pago: "30/09/2026",
        created_by: "cashier-2",
    }, { id: "cashier-1", rol: "Caja" }, today)).toBe(false);
    expect(canAnnulPayment({
        fecha_pago: "29/09/2026",
        created_by: "cashier-1",
    }, { id: "cashier-1", rol: "Caja" }, today)).toBe(false);
});

test("no role can annul a payment that is already annulled", () => {
    expect(canAnnulPayment({
        anulado: true,
        fecha_pago: "30/09/2026",
        created_by: "cashier-1",
    }, { id: "cashier-1", rol: "Caja" }, today)).toBe(false);
});