import { toISODate } from "./dateFormat";
import { formatComprobante } from "./receipt";

const numericReceiptCode = (payment) => {
    const code = String(payment?.cod_comprobante ?? "").trim();
    return /^\d+$/.test(code) ? Number(code) : null;
};

export function sortReportReceipts(receipts) {
    return [...receipts].sort((a, b) => {
        const byDate = toISODate(a.fecha_pago).localeCompare(toISODate(b.fecha_pago));
        if (byDate) return byDate;

        const aCode = numericReceiptCode(a);
        const bCode = numericReceiptCode(b);
        if (aCode !== null && bCode !== null && aCode !== bCode) {
            return aCode - bCode;
        }

        const byReceipt = formatComprobante(a).localeCompare(
            formatComprobante(b),
            "es",
            { numeric: true, sensitivity: "base" },
        );
        return byReceipt || String(a.id ?? "").localeCompare(String(b.id ?? ""));
    });
}