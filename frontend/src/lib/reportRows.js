import { sortReportReceipts } from "./sortReportReceipts";
import { reportConceptRows } from "./reportConceptRows";
import { formatDate } from "./dateFormat";
import { formatComprobante } from "./receipt";

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

export function buildReportTableRows(payments = []) {
    return payments.flatMap((payment) => {
        const concepts = reportConceptRows(payment);
        return concepts.map((concept) => ({
            payment,
            ...concept,
            rowSpan: concepts.length,
        }));
    });
}

export function buildReportSpreadsheetRows(payments = [], mode = "todos") {
    const headers = mode === "todos"
        ? ["Comprobante", "Origen", "Cliente", "Fecha", "Concepto", "Cantidad", "Importe_concepto", "Valido", "Anulado", "Total_comprobante"]
        : ["Comprobante", "Origen", "Cliente", "Fecha", "Concepto", "Cantidad", "Importe_concepto", "Total_comprobante"];
    const includeAnnulled = mode === "todos";
    const rows = [];

    for (const payment of payments) {
        const isIncluded = mode === "todos"
            || (mode === "validos" ? !payment.anulado : Boolean(payment.anulado));
        if (!isIncluded) continue;

        for (const { item, amount } of reportConceptRows(payment)) {
            const row = [
                formatComprobante(payment),
                payment.origen || "",
                payment.cliente_nombre || "—",
                formatDate(payment.fecha_pago),
                item?.tipo_pago_nombre || "Sin conceptos",
                item?.cantidad ?? "",
                item ? amount : "",
            ];
            if (includeAnnulled) {
                row.push(payment.anulado ? "" : amount);
                row.push(payment.anulado ? amount : "");
            }
            row.push(payment.total ?? amount);
            rows.push(row);
        }
    }
    return { headers, rows };
}
