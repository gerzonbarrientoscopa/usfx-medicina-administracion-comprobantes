import React, { useEffect, useMemo, useRef, useState } from "react";
import { apiClient, formatApiError, formatMoney } from "@/lib/api";
import { formatDate, toISODate } from "@/lib/dateFormat";
import { formatComprobante } from "@/lib/receipt";
import { buildReportPdfRows } from "@/lib/reportPdfRows";
import {
    buildReportSpreadsheetRows,
    buildReportTableRows,
} from "@/lib/reportRows";
import {
    buildReportSections,
    summarizeReportSections,
} from "@/lib/reportSections";
import { Button } from "@/components/ui/button";
import { DateInput } from "@/components/DateInput";
import { Label } from "@/components/ui/label";
import { Card, CardContent } from "@/components/ui/card";
import {
    Tabs,
    TabsList,
    TabsTrigger,
} from "@/components/ui/tabs";
import {
    Table,
    TableBody,
    TableCell,
    TableHead,
    TableHeader,
    TableRow,
} from "@/components/ui/table";
import {
    Select,
    SelectTrigger,
    SelectValue,
    SelectContent,
    SelectItem,
} from "@/components/ui/select";
import { toast } from "sonner";
import jsPDF from "jspdf";
import autoTable from "jspdf-autotable";
import * as XLSX from "xlsx";
import { FileSpreadsheet, Printer, FileText } from "lucide-react";
import { useOfficeScope } from "@/hooks/useOfficeScope";

const INSTITUCION = {
    l1: "Universidad Mayor, Real y Pontificia de San Francisco Xavier",
    l2: "Administración de oficinas",
};

const PERIODOS = [
    { id: "diario", label: "Diario" },
    { id: "semanal", label: "Semanal" },
    { id: "mensual", label: "Mensual" },
    { id: "rango", label: "Rango" },
];

const MESES = [
    "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
    "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre",
];
const REPORT_PAGE_SIZE = 100;

const groupedPdfCell = (content, rowSpan) => ({
    content,
    rowSpan,
    styles: { valign: "middle" },
});

const reportConcept = (item, amount = item.total) =>
    `${item.tipo_pago_nombre || "Concepto"}\nCant.: ${item.cantidad} · Bs. ${formatMoney(amount)}`;

const formatPeriodo = (reporte) => {
    if (!reporte) return "";
    if (reporte.periodo === "diario") return formatDate(reporte.desde);
    if (reporte.periodo === "mensual") {
        const monthIndex = Number(toISODate(reporte.desde).substring(5, 7)) - 1;
        return MESES[monthIndex] || formatDate(reporte.desde);
    }
    return `${formatDate(reporte.desde)} - ${formatDate(reporte.hasta)}`;
};

export default function ReportesPage() {
    const {
        isSuperAdmin,
        offices,
        officeId,
        officeName,
        selectedOfficeId,
        setSelectedOfficeId,
    } = useOfficeScope();
    const [periodo, setPeriodo] = useState("diario");
    const [desde, setDesde] = useState("");
    const [hasta, setHasta] = useState("");
    const [rangeDatesValid, setRangeDatesValid] = useState({ desde: true, hasta: true });
    const [createdBy, setCreatedBy] = useState("");
    const [usuarios, setUsuarios] = useState([]);
    const [origen, setOrigen] = useState("Cobro");
    const [conceptoId, setConceptoId] = useState("all");
    const [conceptos, setConceptos] = useState([]);
    const [data, setData] = useState(null);
    const [reportPage, setReportPage] = useState(1);
    const [loading, setLoading] = useState(false);
    const requestId = useRef(0);

    useEffect(() => {
        let cancelled = false;
        setData(null);
        setReportPage(1);
        setCreatedBy("");
        setUsuarios([]);
        const params = officeId ? { office_id: officeId } : {};
        apiClient.get("/reportes/registradores", { params })
            .then((r) => {
                if (!cancelled) setUsuarios(r.data);
            })
            .catch((error) => {
                if (!cancelled) toast.error(formatApiError(error));
            });
        return () => { cancelled = true; };
    }, [officeId]);

    useEffect(() => {
        let cancelled = false;
        setConceptos([]);
        setConceptoId("all");
        const params = officeId ? { office_id: officeId } : {};
        const loadConceptos = async () => {
            try {
                const first = await apiClient.get("/conceptos-recaudacion", {
                    params: { ...params, pag: 1, tam: 100 },
                });
                const rest = await Promise.all(
                    Array.from(
                        { length: Math.max(0, (first.data.pages || 1) - 1) },
                        (_, index) => apiClient.get("/conceptos-recaudacion", {
                            params: { ...params, pag: index + 2, tam: 100 },
                        }),
                    ),
                );
                if (!cancelled) {
                    setConceptos([
                        ...(first.data.items || []),
                        ...rest.flatMap((response) => response.data.items || []),
                    ]);
                }
            } catch (error) {
                if (!cancelled) toast.error(formatApiError(error));
            }
        };
        loadConceptos();
        return () => { cancelled = true; };
    }, [officeId]);

    const generar = async () => {
        const thisRequest = ++requestId.current;
        setLoading(true);
        try {
            const params = { periodo, ...(officeId ? { office_id: officeId } : {}) };
            if (periodo === "rango") {
                if (!rangeDatesValid.desde || !rangeDatesValid.hasta) {
                    toast.error("Ingrese las fechas en formato dd/mm/aaaa.");
                    setLoading(false);
                    return;
                }
                if (!desde || !hasta) {
                    toast.error("Indique fechas Desde y Hasta.");
                    setLoading(false);
                    return;
                }
                params.desde = desde;
                params.hasta = hasta;
            }
            if (createdBy && createdBy !== "all") params.created_by = createdBy;
            const { data: reporte } = await apiClient.get("/reportes", { params });
            if (thisRequest === requestId.current) {
                setReportPage(1);
                setData({ ...reporte, periodo });
            }
        } catch (e) {
            if (thisRequest === requestId.current) toast.error(formatApiError(e));
        } finally {
            if (thisRequest === requestId.current) setLoading(false);
        }
    };

    useEffect(() => {
        requestId.current += 1;
        setLoading(false);
    }, [officeId]);

    const reportOfficeName = data?.office_nombre || officeName;
    const reportSections = useMemo(
        () => buildReportSections(
            data?.pagos || [],
            data?.alquileres || [],
            origen,
            conceptoId,
            conceptos,
        ),
        [data, origen, conceptoId, conceptos],
    );
    const reportSummary = useMemo(
        () => summarizeReportSections(reportSections),
        [reportSections],
    );
    const reportReceipts = useMemo(
        () => reportSections.flatMap((section) => section.payments.map((payment) => ({
            sectionKey: section.key,
            payment,
        }))),
        [reportSections],
    );
    const reportPageCount = Math.max(1, Math.ceil(reportReceipts.length / REPORT_PAGE_SIZE));
    const visibleReportReceipts = useMemo(
        () => reportReceipts.slice(
            (reportPage - 1) * REPORT_PAGE_SIZE,
            reportPage * REPORT_PAGE_SIZE,
        ),
        [reportReceipts, reportPage],
    );
    const visibleReportSections = useMemo(
        () => reportSections.map((section) => ({
            ...section,
            payments: visibleReportReceipts
                .filter((receipt) => receipt.sectionKey === section.key)
                .map((receipt) => receipt.payment),
        })).filter((section) => section.payments.length > 0),
        [reportSections, visibleReportReceipts],
    );
    const selectedConcept = conceptos.find(
        (concept) => String(concept.id) === String(conceptoId),
    );
    const reportSelectionLabel = origen === "Alquiler"
        ? "Alquileres"
        : conceptoId === "all"
            ? "Todos los conceptos"
            : selectedConcept
                ? `${selectedConcept.codigo ? `${selectedConcept.codigo} — ` : ""}${selectedConcept.nombre}`
                : "Concepto seleccionado";
    const visibleReportSectionsWithRows = useMemo(
        () => visibleReportSections.map((section) => ({
            ...section,
            rows: buildReportTableRows(section.payments),
        })),
        [visibleReportSections],
    );

    const buildPDF = (modo) => {
        if (!data) return;
        const doc = new jsPDF({ unit: "pt", format: "a4" });
        const W = doc.internal.pageSize.getWidth();

        // Header
        doc.setFont("times", "bold");
        doc.setFontSize(14);
        doc.setTextColor(29, 53, 87);
        doc.text(INSTITUCION.l1, W / 2, 40, { align: "center" });
        doc.setFontSize(11);
        doc.setTextColor(122, 32, 53);
        doc.text(INSTITUCION.l2, W / 2, 58, { align: "center" });
        doc.setFontSize(13);
        doc.setTextColor(28, 28, 30);
        const estadoLabel = modo === "validos"
            ? "Válidos"
            : modo === "anulados" ? "Anulados" : "Todos";
        const origenLabel = origen === "Cobro" ? "Cobros" : "Alquileres";
        const titulo = `Reporte de ${origenLabel} ${estadoLabel}`;
        doc.text(titulo, W / 2, 84, { align: "center" });
        doc.setFontSize(10);
        doc.setTextColor(99, 99, 105);
        doc.text(reportOfficeName, W / 2, 100, { align: "center" });
        doc.text(`Periodo: ${formatPeriodo(data)}`, W / 2, 114, { align: "center" });
        doc.text(`Filtro: ${reportSelectionLabel}`, W / 2, 128, { align: "center" });

        let cursorY = 148;
        const printSections = reportSections.map((section) => ({
            ...section,
            payments: section.payments.filter((payment) =>
                modo === "todos"
                || (modo === "validos" ? !payment.anulado : payment.anulado)
            ),
        })).filter((section) => section.payments.length > 0);

        printSections.forEach((section) => {
            if (cursorY > doc.internal.pageSize.getHeight() - 90) {
                doc.addPage();
                cursorY = 45;
            }
            doc.setFont("times", "bold");
            doc.setFontSize(11);
            doc.setTextColor(29, 53, 87);
            doc.text(section.title, 40, cursorY);
            const rows = buildReportPdfRows(
                section.payments,
                (pago, rowSpan) => [
                    groupedPdfCell(formatComprobante(pago), rowSpan),
                    groupedPdfCell(pago.origen, rowSpan),
                    groupedPdfCell(pago.cliente_nombre || "—", rowSpan),
                    groupedPdfCell(formatDate(pago.fecha_pago), rowSpan),
                ],
                (pago, { item, amount }) => modo === "todos"
                    ? [
                        item ? reportConcept(item, amount) : "Sin conceptos",
                        pago.anulado ? "" : formatMoney(amount),
                        pago.anulado ? formatMoney(amount) : "",
                    ]
                    : [
                        item ? reportConcept(item, amount) : "Sin conceptos",
                        item?.cantidad ?? "",
                        formatMoney(amount),
                    ],
            );
            autoTable(doc, {
                startY: cursorY + 8,
                head: modo === "todos"
                    ? [["Comprobante", "Origen", "Cliente", "Fecha", origen === "Cobro" ? "Concepto" : "Ambiente / tarifa", "Válido (Bs.)", "Anulado (Bs.)"]]
                    : [["Comprobante", "Origen", "Cliente", "Fecha", origen === "Cobro" ? "Concepto" : "Ambiente / tarifa", "Cant.", "Total (Bs.)"]],
                body: rows,
                styles: { fontSize: 8, cellPadding: 4 },
                headStyles: { fillColor: [122, 32, 53], textColor: 255 },
                columnStyles: { 5: { halign: "right" }, 6: { halign: "right" } },
                margin: { left: 40, right: 40 },
            });
            cursorY = doc.lastAutoTable.finalY + 6;
            const sectionTotals = section.totals;
            const summaryRows = modo === "todos"
                ? [
                    ["", "", "", "", "TOTAL VÁLIDOS", formatMoney(sectionTotals.validos), ""],
                    ["", "", "", "", "TOTAL ANULADOS", "", formatMoney(sectionTotals.anulados)],
                    ["", "", "", "", "DIFERENCIA", formatMoney(sectionTotals.diferencia), ""],
                ]
                : [[
                    "", "", "", "", "", "TOTAL",
                    formatMoney(modo === "validos" ? sectionTotals.validos : sectionTotals.anulados),
                ]];
            autoTable(doc, {
                startY: cursorY,
                body: summaryRows,
                styles: { fontSize: 9, fontStyle: "bold", cellPadding: 4 },
                columnStyles: { 5: { halign: "right" }, 6: { halign: "right" } },
                theme: "grid",
                margin: { left: 40, right: 40 },
            });
            cursorY = doc.lastAutoTable.finalY + 18;
        });

        if (printSections.length === 0) {
            doc.setFont("times", "normal");
            doc.setFontSize(10);
            doc.text("Sin registros para los filtros seleccionados.", 40, cursorY);
            cursorY += 24;
        }

        if (origen === "Cobro" && conceptoId === "all") {
            if (cursorY > doc.internal.pageSize.getHeight() - 90) {
                doc.addPage();
                cursorY = 45;
            }
            const grandTotalRows = modo === "todos"
                ? [
                    ["", "", "", "", "SUPER TOTAL VÁLIDO", formatMoney(reportSummary.validos), ""],
                    ["", "", "", "", "SUPER TOTAL ANULADO", "", formatMoney(reportSummary.anulados)],
                    ["", "", "", "", "DIFERENCIA GENERAL", formatMoney(reportSummary.diferencia), ""],
                ]
                : [[
                    "", "", "", "", "", "SUPER TOTAL",
                    formatMoney(modo === "validos" ? reportSummary.validos : reportSummary.anulados),
                ]];
            autoTable(doc, {
                startY: cursorY,
                body: grandTotalRows,
                styles: { fontSize: 10, fontStyle: "bold", cellPadding: 6 },
                columnStyles: { 5: { halign: "right" }, 6: { halign: "right" } },
                theme: "grid",
                margin: { left: 40, right: 40 },
            });
        }

        const blob = doc.output("bloburl");
        const w = window.open(blob, "_blank");
        if (w) {
            w.addEventListener("load", () => {
                try { w.print(); } catch (_e) {/* ignore */}
            });
        }
    };

    const exportExcel = (modo) => {
        if (!data) return;
        const { headers } = buildReportSpreadsheetRows([], modo);
        const blankRow = () => Array(headers.length).fill("");
        const summaryRow = (label, values) => {
            const row = blankRow();
            row[0] = label;
            Object.entries(values).forEach(([index, value]) => {
                row[Number(index)] = value;
            });
            return row;
        };
        const rows = [];
        reportSections.forEach((section) => {
            const payments = section.payments.filter((payment) =>
                modo === "todos"
                || (modo === "validos" ? !payment.anulado : payment.anulado)
            );
            if (!payments.length) return;
            rows.push(summaryRow(section.title, {}));
            rows.push(...buildReportSpreadsheetRows(payments, modo).rows);
            if (modo === "todos") {
                rows.push(summaryRow(`${section.title} · Total válido`, { 7: section.totals.validos }));
                rows.push(summaryRow(`${section.title} · Total anulado`, { 8: section.totals.anulados }));
                rows.push(summaryRow(`${section.title} · Diferencia`, { 7: section.totals.diferencia }));
            } else {
                rows.push(summaryRow(
                    `${section.title} · Total`,
                    { 7: modo === "validos" ? section.totals.validos : section.totals.anulados },
                ));
            }
            rows.push(blankRow());
        });
        if (rows.length === 0) rows.push(summaryRow("Sin registros para los filtros seleccionados.", {}));
        if (origen === "Cobro" && conceptoId === "all") {
            if (modo === "todos") {
                rows.push(summaryRow("SUPER TOTAL VÁLIDO", { 7: reportSummary.validos }));
                rows.push(summaryRow("SUPER TOTAL ANULADO", { 8: reportSummary.anulados }));
                rows.push(summaryRow("DIFERENCIA GENERAL", { 7: reportSummary.diferencia }));
            } else {
                rows.push(summaryRow(
                    "SUPER TOTAL",
                    { 7: modo === "validos" ? reportSummary.validos : reportSummary.anulados },
                ));
            }
        }
        const estadoLabel = modo === "validos"
            ? "Válidos"
            : modo === "anulados" ? "Anulados" : "Todos";
        const titulo = `Reporte de ${origen === "Cobro" ? "Cobros" : "Alquileres"} ${estadoLabel}`;
        const ws = XLSX.utils.aoa_to_sheet([headers, ...rows], { origin: "A4" });
        XLSX.utils.sheet_add_aoa(
            ws,
            [[titulo], [reportOfficeName], ["Periodo", formatPeriodo(data)], ["Filtro", reportSelectionLabel]],
            { origin: "A1" },
        );
        const wb = XLSX.utils.book_new();
        XLSX.utils.book_append_sheet(wb, ws, "Reporte");
        XLSX.writeFile(
            wb,
            `reporte_${origen.toLowerCase()}_${modo}_${toISODate(data.desde)}_${toISODate(data.hasta)}.xlsx`,
        );
    };

    return (
        <div className="space-y-6" data-testid="reportes-page">
            <div>
                <div className="section-eyebrow">Auditoría</div>
                <h1 className="font-serif-display text-4xl mt-1">Reportes de Cobros y Alquileres</h1>
                <p className="text-sm text-[color:var(--institution-muted)] mt-1">
                    Genere reportes por período, origen y concepto. Puede imprimir válidos, anulados o todos.
                </p>
                <p className="text-sm text-center text-[color:var(--institution-muted)] mt-1" data-testid="report-office-context">
                    {data?.office_nombre || officeName}
                </p>
            </div>

            <Card className="rounded-sm border-[color:var(--institution-border)] shadow-none">
                <CardContent className="p-6 space-y-4">
                    {isSuperAdmin ? (
                        <div className="space-y-1.5 max-w-sm">
                            <Label className="text-xs uppercase tracking-widest text-[color:var(--institution-muted)]">Oficina</Label>
                            <Select
                                value={selectedOfficeId || "all"}
                                onValueChange={(value) => setSelectedOfficeId(value === "all" ? "" : value)}
                            >
                                <SelectTrigger className="rounded-sm" data-testid="rep-office-select">
                                    <SelectValue />
                                </SelectTrigger>
                                <SelectContent>
                                    <SelectItem value="all">Todas las oficinas</SelectItem>
                                    {offices.map((office) => (
                                        <SelectItem key={office.id} value={office.id}>{office.nombre}</SelectItem>
                                    ))}
                                </SelectContent>
                            </Select>
                        </div>
                    ) : (
                        <div className="text-sm text-center text-[color:var(--institution-muted)]">
                            {officeName}
                        </div>
                    )}
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4 max-w-xl">
                        <div className="space-y-1.5">
                            <Label className="text-xs uppercase tracking-widest text-[color:var(--institution-muted)]">
                                Origen
                            </Label>
                            <Select
                                value={origen}
                                onValueChange={(value) => {
                                    setOrigen(value);
                                    setConceptoId("all");
                                    setReportPage(1);
                                }}
                            >
                                <SelectTrigger className="rounded-sm" data-testid="rep-origin-select">
                                    <SelectValue />
                                </SelectTrigger>
                                <SelectContent>
                                    <SelectItem value="Cobro">Cobro</SelectItem>
                                    <SelectItem value="Alquiler">Alquiler</SelectItem>
                                </SelectContent>
                            </Select>
                        </div>
                        {origen === "Cobro" && (
                            <div className="space-y-1.5">
                                <Label className="text-xs uppercase tracking-widest text-[color:var(--institution-muted)]">
                                    Concepto de recaudación
                                </Label>
                                <Select
                                    value={conceptoId}
                                    onValueChange={(value) => {
                                        setConceptoId(value);
                                        setReportPage(1);
                                    }}
                                >
                                    <SelectTrigger className="rounded-sm" data-testid="rep-concept-select">
                                        <SelectValue />
                                    </SelectTrigger>
                                    <SelectContent>
                                        <SelectItem value="all">Todos los conceptos</SelectItem>
                                        {conceptos.map((concepto) => (
                                            <SelectItem
                                                key={concepto.id}
                                                value={String(concepto.id)}
                                                data-testid={`rep-concept-option-${concepto.id}`}
                                            >
                                                {concepto.codigo ? `${concepto.codigo} — ` : ""}{concepto.nombre}
                                            </SelectItem>
                                        ))}
                                    </SelectContent>
                                </Select>
                            </div>
                        )}
                    </div>
                    <Tabs value={periodo} onValueChange={setPeriodo}>
                        <TabsList className="rounded-sm">
                            {PERIODOS.map((p) => (
                                <TabsTrigger key={p.id} value={p.id} className="rounded-sm" data-testid={`tab-${p.id}`}>
                                    {p.label}
                                </TabsTrigger>
                            ))}
                        </TabsList>
                    </Tabs>

                    {periodo === "rango" && (
                        <div className="grid grid-cols-2 gap-4 max-w-md">
                            <div className="space-y-1.5">
                                <Label htmlFor="reporte-desde" className="text-xs uppercase tracking-widest text-[color:var(--institution-muted)]">Desde</Label>
                                <DateInput id="reporte-desde" value={desde} onValueChange={setDesde} onValidityChange={(valid) => setRangeDatesValid((state) => ({ ...state, desde: valid }))} className="rounded-sm" data-testid="rep-desde" />
                            </div>
                            <div className="space-y-1.5">
                                <Label htmlFor="reporte-hasta" className="text-xs uppercase tracking-widest text-[color:var(--institution-muted)]">Hasta</Label>
                                <DateInput id="reporte-hasta" value={hasta} onValueChange={setHasta} onValidityChange={(valid) => setRangeDatesValid((state) => ({ ...state, hasta: valid }))} className="rounded-sm" data-testid="rep-hasta" />
                            </div>
                        </div>
                    )}

                    <div className="grid grid-cols-1 md:grid-cols-3 gap-4 max-w-xl">
                        <div className="space-y-1.5 md:col-span-2">
                            <Label className="text-xs uppercase tracking-widest text-[color:var(--institution-muted)]">
                                Registrado por (opcional)
                            </Label>
                            <Select value={createdBy} onValueChange={setCreatedBy}>
                                <SelectTrigger className="rounded-sm" data-testid="rep-user-select">
                                    <SelectValue placeholder="Todos los usuarios" />
                                </SelectTrigger>
                                <SelectContent>
                                    <SelectItem value="all">Todos los usuarios</SelectItem>
                                    {usuarios.map((usuario) => (
                                        <SelectItem key={usuario.id} value={usuario.id} data-testid={`rep-user-opt-${usuario.id}`}>
                                            {usuario.nombre} <span className="text-xs text-[color:var(--institution-muted)] ml-1">· {usuario.rol}</span>
                                        </SelectItem>
                                    ))}
                                </SelectContent>
                            </Select>
                        </div>
                    </div>

                    <div className="flex gap-3">
                        <Button
                            onClick={generar}
                            disabled={loading}
                            className="rounded-sm text-white"
                            style={{ backgroundColor: "var(--institution-burgundy)" }}
                            data-testid="rep-generar-btn"
                        >
                            Generar reporte
                        </Button>
                    </div>
                </CardContent>
            </Card>

            {data && (
                <>
                    <div className="flex flex-wrap gap-3">
                        <Button
                            onClick={() => buildPDF("validos")}
                            className="rounded-sm text-white"
                            style={{ backgroundColor: "var(--institution-success)" }}
                            data-testid="print-validos-btn"
                        >
                            <Printer size={14} className="mr-2" /> Imprimir {origen === "Cobro" ? "Cobros" : "Alquileres"} Válidos
                        </Button>
                        <Button
                            onClick={() => buildPDF("anulados")}
                            className="rounded-sm text-white"
                            style={{ backgroundColor: "var(--institution-danger)" }}
                            data-testid="print-anulados-btn"
                        >
                            <Printer size={14} className="mr-2" /> Imprimir {origen === "Cobro" ? "Cobros" : "Alquileres"} Anulados
                        </Button>
                        <Button
                            onClick={() => buildPDF("todos")}
                            className="rounded-sm text-white"
                            style={{ backgroundColor: "var(--institution-navy)" }}
                            data-testid="print-todos-btn"
                        >
                            <Printer size={14} className="mr-2" /> Imprimir {origen === "Cobro" ? "todos los cobros" : "todos los alquileres"}
                        </Button>
                    </div>
                    <div className="flex flex-wrap gap-3">
                        <Button variant="outline" onClick={() => exportExcel("validos")} className="rounded-sm" data-testid="excel-validos-btn">
                            <FileSpreadsheet size={14} className="mr-1" /> Excel {origen === "Cobro" ? "Cobros" : "Alquileres"} Válidos
                        </Button>
                        <Button variant="outline" onClick={() => exportExcel("anulados")} className="rounded-sm" data-testid="excel-anulados-btn">
                            <FileSpreadsheet size={14} className="mr-1" /> Excel {origen === "Cobro" ? "Cobros" : "Alquileres"} Anulados
                        </Button>
                        <Button variant="outline" onClick={() => exportExcel("todos")} className="rounded-sm" data-testid="excel-todos-btn">
                            <FileText size={14} className="mr-1" /> Excel {origen === "Cobro" ? "todos los cobros" : "todos los alquileres"}
                        </Button>
                    </div>

                    <Card className="rounded-sm border-[color:var(--institution-border)] shadow-none">
                        <CardContent className="p-6">
                            <div className="flex items-center justify-between mb-4">
                                <div>
                                    <div className="section-eyebrow">Periodo</div>
                                    <div className="font-mono-num text-sm">
                                        {formatPeriodo(data)}
                                    </div>
                                    <div className="mt-1 text-xs text-[color:var(--institution-muted)]">
                                        Filtro: {reportSelectionLabel}
                                    </div>
                                </div>
                                <div className="grid grid-cols-3 gap-6 text-right">
                                    <div>
                                        <div className="section-eyebrow">Total Válidos</div>
                                        <div className="font-serif-display text-2xl font-mono-num" style={{ color: "var(--institution-success)" }}>
                                            Bs. {formatMoney(reportSummary.validos)}
                                        </div>
                                        <div className="text-xs text-[color:var(--institution-muted)]">{reportSummary.count_validos} comprobantes</div>
                                    </div>
                                    <div>
                                        <div className="section-eyebrow">Total Anulados</div>
                                        <div className="font-serif-display text-2xl font-mono-num" style={{ color: "var(--institution-danger)" }}>
                                            Bs. {formatMoney(reportSummary.anulados)}
                                        </div>
                                        <div className="text-xs text-[color:var(--institution-muted)]">{reportSummary.count_anulados} comprobantes</div>
                                    </div>
                                    <div>
                                        <div className="section-eyebrow">Diferencia</div>
                                        <div className="font-serif-display text-2xl font-mono-num" style={{ color: "var(--institution-burgundy)" }}>
                                            Bs. {formatMoney(reportSummary.diferencia)}
                                        </div>
                                    </div>
                                </div>
                            </div>

                            <div className="bg-white border rounded-sm overflow-x-auto" style={{ borderColor: "var(--institution-border)" }}>
                                <Table>
                                    <TableHeader>
                                        <TableRow style={{ backgroundColor: "var(--institution-cream)" }}>
                                            <TableHead className="uppercase text-[10px] tracking-widest text-[color:var(--institution-muted)]">Comprobante</TableHead>
                                            <TableHead className="uppercase text-[10px] tracking-widest text-[color:var(--institution-muted)]">Origen</TableHead>
                                            <TableHead className="uppercase text-[10px] tracking-widest text-[color:var(--institution-muted)]">Cliente</TableHead>
                                            <TableHead className="uppercase text-[10px] tracking-widest text-[color:var(--institution-muted)]">Fecha</TableHead>
                                            <TableHead className="uppercase text-[10px] tracking-widest text-[color:var(--institution-muted)]">{origen === "Cobro" ? "Concepto" : "Ambiente / tarifa"}</TableHead>
                                            <TableHead className="text-right uppercase text-[10px] tracking-widest text-[color:var(--institution-muted)]">Válido (Bs.)</TableHead>
                                            <TableHead className="text-right uppercase text-[10px] tracking-widest text-[color:var(--institution-muted)]">Anulado (Bs.)</TableHead>
                                        </TableRow>
                                    </TableHeader>
                                    <TableBody>
                                        {visibleReportSectionsWithRows.map((section) => (
                                            <React.Fragment key={section.key}>
                                                <TableRow style={{ backgroundColor: "var(--institution-cream)" }}>
                                                    <TableCell colSpan={7} className="font-semibold uppercase tracking-wider text-[color:var(--institution-navy)]">
                                                        {section.title}
                                                    </TableCell>
                                                </TableRow>
                                                {section.rows.map(({ payment: pago, item, index, amount, rowSpan }) => {
                                                    const first = index === 0;
                                                    return (
                                                        <TableRow key={`${section.key}-${pago.id}-${item?.id || index}`}>
                                                            {first && (
                                                                <TableCell rowSpan={rowSpan} className="font-mono-num align-middle">
                                                                    {formatComprobante(pago)}
                                                                </TableCell>
                                                            )}
                                                            {first && (
                                                                <TableCell rowSpan={rowSpan} className="align-middle">
                                                                    {pago.origen}
                                                                </TableCell>
                                                            )}
                                                            {first && (
                                                                <TableCell rowSpan={rowSpan} className="align-middle">
                                                                    {pago.cliente_nombre || "—"}
                                                                </TableCell>
                                                            )}
                                                            {first && (
                                                                <TableCell rowSpan={rowSpan} className="font-mono-num align-middle">
                                                                    {formatDate(pago.fecha_pago)}
                                                                </TableCell>
                                                            )}
                                                            <TableCell>
                                                                {item ? (
                                                                    <>
                                                                        <div>{item.tipo_pago_nombre || "Concepto"}</div>
                                                                        <div className="text-xs text-[color:var(--institution-muted)]">
                                                                            {item.cantidad} × Bs. {formatMoney(item.monto)} = Bs. {formatMoney(amount)}
                                                                        </div>
                                                                    </>
                                                                ) : "Sin conceptos"}
                                                            </TableCell>
                                                            <TableCell className="text-right font-mono-num align-middle">
                                                                {pago.anulado ? "—" : formatMoney(amount)}
                                                            </TableCell>
                                                            <TableCell className="text-right font-mono-num align-middle">
                                                                {pago.anulado ? formatMoney(amount) : "—"}
                                                            </TableCell>
                                                        </TableRow>
                                                    );
                                                })}
                                                <TableRow style={{ backgroundColor: "var(--institution-cream)" }}>
                                                    <TableCell colSpan={5} className="text-right uppercase text-xs tracking-widest text-[color:var(--institution-muted)] font-semibold">
                                                        Subtotal · {section.title}
                                                    </TableCell>
                                                    <TableCell className="text-right font-mono-num font-semibold">{formatMoney(section.totals.validos)}</TableCell>
                                                    <TableCell className="text-right font-mono-num font-semibold">{formatMoney(section.totals.anulados)}</TableCell>
                                                </TableRow>
                                                <TableRow>
                                                    <TableCell colSpan={5} className="text-right uppercase text-xs tracking-widest text-[color:var(--institution-burgundy)] font-semibold">
                                                        Diferencia · {section.title}
                                                    </TableCell>
                                                    <TableCell colSpan={2} className="text-right font-mono-num font-bold" style={{ color: "var(--institution-burgundy)" }}>
                                                        Bs. {formatMoney(section.totals.diferencia)}
                                                    </TableCell>
                                                </TableRow>
                                            </React.Fragment>
                                        ))}
                                        {origen === "Cobro" && conceptoId === "all" && reportSections.length > 0 && (
                                            <>
                                                <TableRow style={{ backgroundColor: "var(--institution-navy)", color: "white" }}>
                                                    <TableCell colSpan={5} className="text-right uppercase text-xs tracking-widest font-bold">
                                                        Super total · todos los conceptos
                                                    </TableCell>
                                                    <TableCell className="text-right font-mono-num font-bold">{formatMoney(reportSummary.validos)}</TableCell>
                                                    <TableCell className="text-right font-mono-num font-bold">{formatMoney(reportSummary.anulados)}</TableCell>
                                                </TableRow>
                                                <TableRow>
                                                    <TableCell colSpan={5} className="text-right uppercase text-xs tracking-widest text-[color:var(--institution-burgundy)] font-semibold">
                                                        Diferencia general
                                                    </TableCell>
                                                    <TableCell colSpan={2} className="text-right font-mono-num font-bold" style={{ color: "var(--institution-burgundy)" }}>
                                                        Bs. {formatMoney(reportSummary.diferencia)}
                                                    </TableCell>
                                                </TableRow>
                                            </>
                                        )}
                                        {reportReceipts.length === 0 && (
                                            <TableRow>
                                                <TableCell colSpan={7} className="text-center py-10 text-sm text-[color:var(--institution-muted)]">
                                                    Sin registros para los filtros seleccionados.
                                                </TableCell>
                                            </TableRow>
                                        )}
                                    </TableBody>
                                </Table>
                            </div>
                            {reportReceipts.length > REPORT_PAGE_SIZE && (
                                <div className="flex flex-wrap items-center justify-between gap-3 border-t pt-3" style={{ borderColor: "var(--institution-border)" }}>
                                    <span className="text-xs text-[color:var(--institution-muted)]">
                                        Mostrando {(reportPage - 1) * REPORT_PAGE_SIZE + 1}–{Math.min(reportPage * REPORT_PAGE_SIZE, reportReceipts.length)} de {reportReceipts.length} registros
                                    </span>
                                    <div className="flex gap-2">
                                        <Button
                                            variant="outline"
                                            size="sm"
                                            disabled={reportPage <= 1}
                                            onClick={() => setReportPage((page) => Math.max(1, page - 1))}
                                        >
                                            Anterior
                                        </Button>
                                        <span className="flex items-center text-xs text-[color:var(--institution-muted)]">
                                            Página {reportPage} de {reportPageCount}
                                        </span>
                                        <Button
                                            variant="outline"
                                            size="sm"
                                            disabled={reportPage >= reportPageCount}
                                            onClick={() => setReportPage((page) => Math.min(reportPageCount, page + 1))}
                                        >
                                            Siguiente
                                        </Button>
                                    </div>
                                </div>
                            )}
                        </CardContent>
                    </Card>
                </>
            )}
        </div>
    );
}
