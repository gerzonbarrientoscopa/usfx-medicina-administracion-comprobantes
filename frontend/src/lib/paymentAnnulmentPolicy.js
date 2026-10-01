import { toISODate } from "./dateFormat";

function currentBoliviaDate(now) {
    const parts = new Intl.DateTimeFormat("en-US", {
        timeZone: "America/La_Paz",
        year: "numeric",
        month: "2-digit",
        day: "2-digit",
    }).formatToParts(now);
    const values = Object.fromEntries(parts.map(({ type, value }) => [type, value]));
    return `${values.year}-${values.month}-${values.day}`;
}

export function canAnnulPayment(payment, user, today = new Date()) {
    const isRental = payment?.origen === "alquiler";
    if (
        !payment
        || payment.anulado
        || (isRental && payment.estado === "cancelado")
    ) return false;
    if (user?.rol === "Administrador" || user?.rol === "SuperAdmin") return true;
    const issuerId = isRental ? payment.paid_by : payment.created_by;
    if (user?.rol !== "Caja" || issuerId !== user.id) return false;

    const printedDate = toISODate(payment.fecha_pago);
    return Boolean(printedDate) && printedDate === currentBoliviaDate(today);
}