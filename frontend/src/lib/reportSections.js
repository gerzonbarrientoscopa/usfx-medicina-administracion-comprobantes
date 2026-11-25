import { reportConceptRows } from "./reportConceptRows";
import { buildReportRows } from "./reportRows";

const numericAmount = (value) => {
    const amount = Number(value);
    return Number.isFinite(amount) ? amount : 0;
};

function summarizePayments(payments) {
    const totals = {
        validos: 0,
        anulados: 0,
        diferencia: 0,
        count_validos: 0,
        count_anulados: 0,
    };
    const countedValid = new Set();
    const countedAnnulled = new Set();

    payments.forEach((payment, index) => {
        const amount = reportConceptRows(payment).reduce(
            (sum, row) => sum + numericAmount(row.amount),
            0,
        );
        const key = String(payment.id ?? `${payment.origen}-${index}`);
        if (payment.anulado) {
            totals.anulados += amount;
            countedAnnulled.add(key);
        } else {
            totals.validos += amount;
            countedValid.add(key);
        }
    });

    totals.diferencia = totals.validos - totals.anulados;
    totals.count_validos = countedValid.size;
    totals.count_anulados = countedAnnulled.size;
    return totals;
}

function conceptDescriptor(item, conceptsById, idsByName) {
    const id = item?.id_tipo_pago == null ? "" : String(item.id_tipo_pago);
    const name = String(item?.tipo_pago_nombre || "").trim();
    const nameKey = name.toLocaleLowerCase("es");
    const resolvedId = id || (
        idsByName.get(nameKey)?.length === 1 ? idsByName.get(nameKey)[0] : ""
    );
    const concept = resolvedId ? conceptsById.get(resolvedId) : null;
    const key = resolvedId || (nameKey ? `name:${nameKey}` : "sin-concepto");
    const title = concept?.nombre || name || "Sin concepto";
    return {
        key,
        id: resolvedId || null,
        title: concept?.codigo ? `${concept.codigo} — ${title}` : title,
    };
}

export function summarizeReportSections(sections = []) {
    const summary = {
        validos: 0,
        anulados: 0,
        diferencia: 0,
        count_validos: 0,
        count_anulados: 0,
    };
    const validReceipts = new Set();
    const annulledReceipts = new Set();

    sections.forEach((section) => {
        summary.validos += section.totals.validos;
        summary.anulados += section.totals.anulados;
        summary.diferencia += section.totals.diferencia;
        section.payments.forEach((payment, index) => {
            const key = String(payment.id ?? `${section.key}-${index}`);
            if (payment.anulado) annulledReceipts.add(key);
            else validReceipts.add(key);
        });
    });
    summary.count_validos = validReceipts.size;
    summary.count_anulados = annulledReceipts.size;
    return summary;
}

export function buildReportSections(
    pagos = [],
    alquileres = [],
    origen = "Cobro",
    conceptoId = "all",
    conceptos = [],
) {
    if (origen === "Alquiler") {
        const payments = buildReportRows([], alquileres);
        return [{
            key: "alquileres",
            title: "Alquileres",
            payments,
            totals: summarizePayments(payments),
        }];
    }

    const conceptsById = new Map(
        conceptos.map((concept) => [String(concept.id), concept]),
    );
    const idsByName = new Map();
    conceptos.forEach((concept) => {
        const key = String(concept.nombre || "").trim().toLocaleLowerCase("es");
        if (!key) return;
        idsByName.set(key, [...(idsByName.get(key) || []), String(concept.id)]);
    });

    const grouped = new Map();
    pagos.forEach((payment) => {
        const linesByConcept = new Map();
        reportConceptRows(payment).forEach(({ item, amount }) => {
            const concept = conceptDescriptor(item, conceptsById, idsByName);
            if (conceptoId !== "all" && concept.id !== String(conceptoId)) return;
            const lines = linesByConcept.get(concept.key) || { concept, items: [] };
            if (item) {
                lines.items.push({ ...item, total: numericAmount(amount) });
            }
            linesByConcept.set(concept.key, lines);
        });

        linesByConcept.forEach(({ concept, items }) => {
            let section = grouped.get(concept.key);
            if (!section) {
                section = { key: concept.key, title: concept.title, receipts: new Map() };
                grouped.set(concept.key, section);
            }
            const receiptKey = String(payment.id ?? `${payment.fecha_pago}-${section.receipts.size}`);
            const receipt = section.receipts.get(receiptKey) || {
                ...payment,
                id_tipo_pago: items[0]?.id_tipo_pago ?? null,
                tipo_pago_nombre: items[0]?.tipo_pago_nombre ?? null,
                items: [],
            };
            receipt.items.push(...items);
            section.receipts.set(receiptKey, receipt);
        });
    });

    return [...grouped.values()]
        .sort((left, right) => left.title.localeCompare(right.title, "es"))
        .map((section) => {
            const payments = buildReportRows([...section.receipts.values()]);
            return {
                key: section.key,
                title: section.title,
                payments,
                totals: summarizePayments(payments),
            };
        });
}
