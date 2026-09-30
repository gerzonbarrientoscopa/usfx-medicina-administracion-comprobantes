import { reportConceptRows } from "./reportConceptRows";

export function buildReportPdfRows(payments, groupedCells, conceptCells) {
    return payments.flatMap((payment) => {
        const concepts = reportConceptRows(payment);
        return concepts.map((concept) => [
            ...(concept.index === 0 ? groupedCells(payment, concepts.length) : []),
            ...conceptCells(payment, concept),
        ]);
    });
}