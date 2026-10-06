import { sortReportReceipts } from "./sortReportReceipts";

export function buildReportRows(pagos = [], alquileres = []) {
    return sortReportReceipts([
        ...pagos.map((pago) => ({
            ...pago,
            origen: "Cobro",
            anulado: Boolean(pago.anulado),
        })),
        ...alquileres.map((alquiler) => ({
            ...alquiler,
            origen: "Alquiler",
            cliente_nombre: alquiler.cliente_nombre,
            items: [{
                tipo_pago_nombre: `${alquiler.ambiente_nombre} · ${alquiler.tarifa_nombre}`,
                cantidad: alquiler.cantidad,
                monto: alquiler.monto,
                total: alquiler.total,
            }],
            anulado: Boolean(
                alquiler.anulado
                || alquiler.estado === "cancelado"
                || alquiler.estado === "anulado"
            ),
        })),
    ]);
}
