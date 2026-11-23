/** @jest-environment node */

import React from "react";
import { performance } from "perf_hooks";
import { renderToStaticMarkup } from "react-dom/server";
import autoTable from "jspdf-autotable";
import jsPDF from "jspdf";
import * as XLSX from "xlsx";
import { formatComprobante } from "./receipt";
import { formatDate } from "./dateFormat";
import { buildReportPdfRows } from "./reportPdfRows";
import {
    buildReportRows,
    buildReportSpreadsheetRows,
    buildReportTableRows,
} from "./reportRows";

const runBenchmark = process.env.RUN_REPORT_BENCHMARKS === "1";
const benchmarkTest = runBenchmark ? test : test.skip;

benchmarkTest("mide pantalla, PDF y Excel con 1.500 comprobantes", () => {
    const payments = Array.from({ length: 1_200 }, (_, index) => ({
        id: `p-${index}`,
        office_id: "1",
        cliente_nombre: `Cliente ${index}`,
        cod_comprobante: String(index + 1).padStart(5, "0"),
        prefijo_comprobante: "RPT",
        gestion: 2026,
        fecha_pago: `2026-${String((index % 12) + 1).padStart(2, "0")}-${String((index % 28) + 1).padStart(2, "0")}`,
        total: 30,
        anulado: index % 10 === 0,
        items: [
            { id: `i-${index}-1`, tipo_pago_nombre: "Concepto A", cantidad: 1, monto: 10, total: 10 },
            { id: `i-${index}-2`, tipo_pago_nombre: "Concepto B", cantidad: 2, monto: 10, total: 20 },
        ],
    }));
    const rentals = Array.from({ length: 300 }, (_, index) => ({
        id: `a-${index}`,
        cliente_nombre: `Cliente de alquiler ${index}`,
        cod_comprobante: String(index + 20_000).padStart(5, "0"),
        prefijo_comprobante: "RPT",
        gestion: 2026,
        fecha_pago: `2026-${String((index % 12) + 1).padStart(2, "0")}-${String((index % 28) + 1).padStart(2, "0")}`,
        ambiente_nombre: "Auditorio",
        tarifa_nombre: "Hora",
        cantidad: 1,
        monto: 50,
        total: 50,
        estado: index % 9 === 0 ? "cancelado" : "pagado",
    }));

    const screenStart = performance.now();
    const reportRows = buildReportRows(payments, rentals);
    const visibleRows = buildReportTableRows(reportRows.slice(0, 100));
    const screenMarkup = renderToStaticMarkup(
        <table>
            <tbody>
                {visibleRows.map(({ payment, item, index, rowSpan, amount }) => (
                    <tr key={`${payment.id}-${item?.id || index}`}>
                        {index === 0 && (
                            <>
                                <td rowSpan={rowSpan}>{formatComprobante(payment)}</td>
                                <td rowSpan={rowSpan}>{payment.origen}</td>
                                <td rowSpan={rowSpan}>{payment.cliente_nombre}</td>
                                <td rowSpan={rowSpan}>{formatDate(payment.fecha_pago)}</td>
                            </>
                        )}
                        <td>{item?.tipo_pago_nombre || "Sin conceptos"}</td>
                        <td>{amount}</td>
                    </tr>
                ))}
            </tbody>
        </table>,
    );
    const screenMs = performance.now() - screenStart;

    const pdfStart = performance.now();
    const pdfRows = buildReportPdfRows(
        reportRows,
        (payment, rowSpan) => [
            { content: formatComprobante(payment), rowSpan },
            { content: payment.origen, rowSpan },
            { content: payment.cliente_nombre || "—", rowSpan },
            { content: formatDate(payment.fecha_pago), rowSpan },
        ],
        (_payment, { item, amount }) => [
            item?.tipo_pago_nombre || "Sin conceptos",
            item?.cantidad ?? "",
            amount,
        ],
    );
    const pdf = new jsPDF({ unit: "pt", format: "a4" });
    autoTable(pdf, {
        head: [["Comprobante", "Origen", "Cliente", "Fecha", "Concepto", "Cantidad", "Total"]],
        body: pdfRows,
        styles: { fontSize: 8, cellPadding: 4 },
    });
    const pdfBytes = pdf.output("arraybuffer");
    const pdfMs = performance.now() - pdfStart;

    const excelStart = performance.now();
    const { headers, rows } = buildReportSpreadsheetRows(reportRows, "todos");
    const sheet = XLSX.utils.aoa_to_sheet([headers, ...rows]);
    const workbook = XLSX.utils.book_new();
    XLSX.utils.book_append_sheet(workbook, sheet, "Reporte");
    const excelBytes = XLSX.write(workbook, { type: "buffer", bookType: "xlsx" });
    const excelMs = performance.now() - excelStart;

    console.info(
        `BENCH_REPORTS 1500 comprobantes: pantalla=${screenMs.toFixed(1)}ms ` +
        `PDF=${pdfMs.toFixed(1)}ms Excel=${excelMs.toFixed(1)}ms ` +
        `lineas=${pdfRows.length} bytesPDF=${pdfBytes.byteLength} bytesExcel=${excelBytes.length}`,
    );
    expect(reportRows).toHaveLength(1_500);
    expect(visibleRows.length).toBeGreaterThanOrEqual(100);
    expect(screenMarkup).toContain("Cliente ");
    expect(pdfRows.length).toBeGreaterThan(1_500);
    expect(headers).toContain("Cliente");
    expect(rows.length).toBe(pdfRows.length);
    expect(pdfBytes.byteLength).toBeGreaterThan(0);
    expect(excelBytes.length).toBeGreaterThan(0);
    expect(screenMs).toBeLessThan(10_000);
    expect(pdfMs).toBeLessThan(30_000);
    expect(excelMs).toBeLessThan(10_000);
});
