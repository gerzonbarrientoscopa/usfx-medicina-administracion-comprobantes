import React, { useEffect, useRef, useState } from "react";
import { apiClient, formatApiError, formatMoney } from "@/lib/api";
import { formatComprobante } from "@/lib/receipt";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
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

const formatDate = (value) => {
    if (!value) return "";
    const [year, month, day] = value.substring(0, 10).split("-");
    if (!year || !month || !day) return value;
    return `${day}/${month}/${year}`;
};

const pagoItems = (pago) => {
    if (Array.isArray(pago.items) && pago.items.length) return pago.items;
    if (!pago.id_tipo_pago && !pago.tipo_pago_nombre) return [];
    return [{
        id_tipo_pago: pago.id_tipo_pago,
        tipo_pago_nombre: pago.tipo_pago_nombre || "",
        cantidad: pago.cantidad,
        monto: pago.monto,
        total: pago.total,
    }];
};

const groupedPdfCell = (content, rowSpan) => ({
    content,
    rowSpan,
    styles: { valign: "middle" },
});

const reportConcept = (item) =>
    `${item.tipo_pago_nombre || "Concepto"}\nCant.: ${item.cantidad} · Bs. ${formatMoney(item.total)}`;

const formatPeriodo = (reporte) => {
    if (!reporte) return "";
    if (reporte.periodo === "diario") return formatDate(reporte.desde);
    if (reporte.periodo === "mensual") {
        const monthIndex = Number(reporte.desde?.substring(5, 7)) - 1;
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
    const [createdBy, setCreatedBy] = useState("");
    const [usuarios, setUsuarios] = useState([]);
    const [data, setData] = useState(null);
    const [loading, setLoading] = useState(false);
    const requestId = useRef(0);

    useEffect(() => {
        let cancelled = false;
        setData(null);
        setCreatedBy("");
        setUsuarios([]);
        const params = officeId ? { office_id: officeId } : {};
        apiClient.get("/usuarios/list", { params })
            .then((r) => {
                if (!cancelled) setUsuarios(r.data);
            })
            .catch((error) => {
                if (!cancelled) toast.error(formatApiError(error));
            });
        return () => { cancelled = true; };
    }, [officeId]);

    const generar = async () => {
        const thisRequest = ++requestId.current;
        setLoading(true);
        try {
            const params = { periodo, ...(officeId ? { office_id: officeId } : {}) };
            if (periodo === "rango") {
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
            if (thisRequest === requestId.current) setData({ ...reporte, periodo });
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
    const reportRows = [
        ...(data?.pagos || []).map((pago) => ({ ...pago, origen: "Estudiantil" })),
        ...(data?.alquileres || []).map((alquiler) => ({
            ...alquiler,
            origen: "Alquiler",
            estudiante_nombre: alquiler.cliente_nombre,
            items: [{
                tipo_pago_nombre: `${alquiler.ambiente_nombre} · ${alquiler.tarifa_nombre}`,
                cantidad: alquiler.cantidad,
                monto: alquiler.monto,
                total: alquiler.total,
            }],
            anulado: false,
        })),
    ].sort((a, b) => a.fecha_pago.localeCompare(b.fecha_pago));

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
        const titulo =
            modo === "validos" ? "Reporte de Pagos Válidos" :
            modo === "anulados" ? "Reporte de Pagos Anulados" :
            "Reporte de Todos los Pagos";
        doc.text(titulo, W / 2, 84, { align: "center" });
        doc.setFontSize(10);
        doc.setTextColor(99, 99, 105);
        doc.text(`Oficina: ${reportOfficeName}`, W / 2, 100, { align: "center" });
        doc.text(`Periodo: ${formatPeriodo(data)}`, W / 2, 114, { align: "center" });

        if (modo === "todos") {
            const rows = reportRows.flatMap((pago) => {
                const items = pagoItems(pago);
                const group = items.length ? items : [null];
                return group.map((item, index) => {
                    const first = index === 0;
                    const span = (value) =>
                        first ? groupedPdfCell(value, group.length) : "";
                    return [
                        span(formatComprobante(pago)),
                        span(`${pago.origen}: ${pago.estudiante_nombre || ""}`),
                        span(formatDate(pago.fecha_pago)),
                        item ? reportConcept(item) : "Sin conceptos",
                        span(pago.office_nombre || reportOfficeName || ""),
                        span(pago.anulado ? "" : formatMoney(pago.total)),
                        span(pago.anulado ? formatMoney(pago.total) : ""),
                    ];
                });
            });
            autoTable(doc, {
                startY: 134,
                head: [["Comprobante", "Origen / cliente", "Fecha", "Concepto", "Oficina", "Válido (Bs.)", "Anulado (Bs.)"]],
                body: rows,
                styles: { fontSize: 9, cellPadding: 5 },
                headStyles: { fillColor: [122, 32, 53], textColor: 255 },
                columnStyles: { 5: { halign: "right" }, 6: { halign: "right" } },
            });
            const finalY = doc.lastAutoTable.finalY + 10;
            autoTable(doc, {
                startY: finalY,
                body: [
                    ["", "", "", "ESTUDIANTILES", "", formatMoney(data.totales.estudiantiles), ""],
                    ["", "", "", "ALQUILERES", "", formatMoney(data.totales.alquileres), ""],
                    ["", "", "", "TOTAL VÁLIDOS", "", formatMoney(data.totales.validos), ""],
                    ["", "", "", "TOTAL ANULADOS", "", "", formatMoney(data.totales.anulados)],
                    ["", "", "", "DIFERENCIA (Válidos − Anulados)", "", formatMoney(data.totales.diferencia), ""],
                ],
                styles: { fontSize: 10, fontStyle: "bold", cellPadding: 5 },
                columnStyles: { 5: { halign: "right" }, 6: { halign: "right" } },
                theme: "grid",
            });
        } else {
            const filtered = reportRows.filter((p) => (modo === "validos" ? !p.anulado : p.anulado));
            const rows = filtered.flatMap((pago) => {
                const items = pagoItems(pago);
                const group = items.length ? items : [null];
                return group.map((item, index) => {
                    const first = index === 0;
                    const span = (value) =>
                        first ? groupedPdfCell(value, group.length) : "";
                    return [
                        span(formatComprobante(pago)),
                        span(`${pago.origen}: ${pago.estudiante_nombre || ""}`),
                        span(formatDate(pago.fecha_pago)),
                        item ? reportConcept(item) : "Sin conceptos",
                        span(pago.office_nombre || reportOfficeName || ""),
                        item?.cantidad ?? "",
                        span(formatMoney(pago.total)),
                    ];
                });
            });
            autoTable(doc, {
                startY: 134,
                head: [["Comprobante", "Origen / cliente", "Fecha", "Concepto", "Oficina", "Cant.", "Total (Bs.)"]],
                body: rows,
                styles: { fontSize: 9, cellPadding: 5 },
                headStyles: { fillColor: [122, 32, 53], textColor: 255 },
                columnStyles: { 5: { halign: "right" }, 6: { halign: "right" } },
            });
            const total = modo === "validos" ? data.totales.validos : data.totales.anulados;
            const finalY = doc.lastAutoTable.finalY + 10;
            autoTable(doc, {
                startY: finalY,
                body: modo === "validos" ? [
                    ["", "", "", "", "", "ESTUDIANTILES", formatMoney(data.totales.estudiantiles)],
                    ["", "", "", "", "", "ALQUILERES", formatMoney(data.totales.alquileres)],
                    ["", "", "", "", "", "TOTAL", formatMoney(total)],
                ] : [["", "", "", "", "", "TOTAL", formatMoney(total)]],
                styles: { fontSize: 11, fontStyle: "bold", cellPadding: 6 },
                columnStyles: { 6: { halign: "right" } },
                theme: "grid",
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
        let rows = [];
        if (modo === "todos") {
            rows = reportRows.flatMap((pago) => {
                const items = pagoItems(pago);
                const group = items.length ? items : [null];
                return group.map((item, index) => ({
                    Comprobante: index === 0 ? formatComprobante(pago) : "",
                    Origen: index === 0 ? pago.origen : "",
                    Cliente: index === 0 ? pago.estudiante_nombre || "" : "",
                    Fecha: index === 0 ? formatDate(pago.fecha_pago) : "",
                    Concepto: item?.tipo_pago_nombre || "Sin conceptos",
                    Cantidad: item?.cantidad ?? "",
                    Importe_concepto: item?.total ?? "",
                    Oficina: index === 0 ? pago.office_nombre || reportOfficeName || "" : "",
                    Valido: index === 0 && !pago.anulado ? pago.total : "",
                    Anulado: index === 0 && pago.anulado ? pago.total : "",
                }));
            });
            rows.push({});
            rows.push({ Comprobante: "ESTUDIANTILES", Valido: data.totales.estudiantiles });
            rows.push({ Comprobante: "ALQUILERES", Valido: data.totales.alquileres });
            rows.push({ Comprobante: "TOTAL VÁLIDOS", Valido: data.totales.validos });
            rows.push({ Comprobante: "TOTAL ANULADOS", Anulado: data.totales.anulados });
            rows.push({ Comprobante: "DIFERENCIA", Valido: data.totales.diferencia });
        } else {
            const filtered = reportRows.filter((p) => (modo === "validos" ? !p.anulado : p.anulado));
            rows = filtered.flatMap((pago) => {
                const items = pagoItems(pago);
                const group = items.length ? items : [null];
                return group.map((item, index) => ({
                    Comprobante: index === 0 ? formatComprobante(pago) : "",
                    Origen: index === 0 ? pago.origen : "",
                    Cliente: index === 0 ? pago.estudiante_nombre || "" : "",
                    Fecha: index === 0 ? formatDate(pago.fecha_pago) : "",
                    Concepto: item?.tipo_pago_nombre || "Sin conceptos",
                    Oficina: index === 0 ? pago.office_nombre || reportOfficeName || "" : "",
                    Cantidad: item?.cantidad ?? "",
                    Importe_concepto: item?.total ?? "",
                    Total_comprobante: index === 0 ? pago.total : "",
                }));
            });
            rows.push({});
            if (modo === "validos") {
                rows.push({ Comprobante: "ESTUDIANTILES", Total: data.totales.estudiantiles });
                rows.push({ Comprobante: "ALQUILERES", Total: data.totales.alquileres });
            }
            rows.push({
                Comprobante: "TOTAL",
                Total: modo === "validos" ? data.totales.validos : data.totales.anulados,
            });
        }
        const titulo =
            modo === "validos" ? "Reporte de Pagos Válidos" :
            modo === "anulados" ? "Reporte de Pagos Anulados" :
            "Reporte de Todos los Pagos";
        const ws = XLSX.utils.json_to_sheet(rows, { origin: "A4" });
        XLSX.utils.sheet_add_aoa(
            ws,
            [[titulo], ["Oficina", reportOfficeName], ["Periodo", formatPeriodo(data)], []],
            { origin: "A1" },
        );
        const wb = XLSX.utils.book_new();
        XLSX.utils.book_append_sheet(wb, ws, "Reporte");
        XLSX.writeFile(wb, `reporte_${modo}_${data.desde}_${data.hasta}.xlsx`);
    };

    return (
        <div className="space-y-6" data-testid="reportes-page">
            <div>
                <div className="section-eyebrow">Auditoría</div>
                <h1 className="font-serif-display text-4xl mt-1">Reportes de Pagos</h1>
                <p className="text-sm text-[color:var(--institution-muted)] mt-1">
                    Genere reportes por período. Tres impresiones disponibles: válidos, anulados, todos.
                </p>
                <p className="text-sm text-[color:var(--institution-muted)] mt-1" data-testid="report-office-context">
                    Oficina: {data?.office_nombre || officeName}
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
                        <div className="text-sm text-[color:var(--institution-muted)]">
                            Oficina: {officeName}
                        </div>
                    )}
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
                                <Label className="text-xs uppercase tracking-widest text-[color:var(--institution-muted)]">Desde</Label>
                                <Input type="date" value={desde} onChange={(e) => setDesde(e.target.value)} className="rounded-sm" data-testid="rep-desde" />
                            </div>
                            <div className="space-y-1.5">
                                <Label className="text-xs uppercase tracking-widest text-[color:var(--institution-muted)]">Hasta</Label>
                                <Input type="date" value={hasta} onChange={(e) => setHasta(e.target.value)} className="rounded-sm" data-testid="rep-hasta" />
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
                            <Printer size={14} className="mr-2" /> Imprimir Pagos Válidos
                        </Button>
                        <Button
                            onClick={() => buildPDF("anulados")}
                            className="rounded-sm text-white"
                            style={{ backgroundColor: "var(--institution-danger)" }}
                            data-testid="print-anulados-btn"
                        >
                            <Printer size={14} className="mr-2" /> Imprimir Pagos Anulados
                        </Button>
                        <Button
                            onClick={() => buildPDF("todos")}
                            className="rounded-sm text-white"
                            style={{ backgroundColor: "var(--institution-navy)" }}
                            data-testid="print-todos-btn"
                        >
                            <Printer size={14} className="mr-2" /> Imprimir Todos los Pagos
                        </Button>
                    </div>
                    <div className="flex flex-wrap gap-3">
                        <Button variant="outline" onClick={() => exportExcel("validos")} className="rounded-sm" data-testid="excel-validos-btn">
                            <FileSpreadsheet size={14} className="mr-1" /> Excel Válidos
                        </Button>
                        <Button variant="outline" onClick={() => exportExcel("anulados")} className="rounded-sm" data-testid="excel-anulados-btn">
                            <FileSpreadsheet size={14} className="mr-1" /> Excel Anulados
                        </Button>
                        <Button variant="outline" onClick={() => exportExcel("todos")} className="rounded-sm" data-testid="excel-todos-btn">
                            <FileText size={14} className="mr-1" /> Excel Todos
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
                                </div>
                                <div className="grid grid-cols-3 gap-6 text-right">
                                    <div>
                                        <div className="section-eyebrow">Total Válidos</div>
                                        <div className="font-serif-display text-2xl font-mono-num" style={{ color: "var(--institution-success)" }}>
                                            Bs. {formatMoney(data.totales.validos)}
                                        </div>
                                        <div className="text-xs text-[color:var(--institution-muted)]">{data.totales.count_validos} comprobantes</div>
                                        <div className="text-xs text-[color:var(--institution-muted)]">Estudiantiles: Bs. {formatMoney(data.totales.estudiantiles)}</div>
                                        <div className="text-xs text-[color:var(--institution-muted)]">Alquileres: Bs. {formatMoney(data.totales.alquileres)} ({data.alquileres.length})</div>
                                    </div>
                                    <div>
                                        <div className="section-eyebrow">Total Anulados</div>
                                        <div className="font-serif-display text-2xl font-mono-num" style={{ color: "var(--institution-danger)" }}>
                                            Bs. {formatMoney(data.totales.anulados)}
                                        </div>
                                        <div className="text-xs text-[color:var(--institution-muted)]">{data.totales.count_anulados} comprobantes</div>
                                    </div>
                                    <div>
                                        <div className="section-eyebrow">Diferencia</div>
                                        <div className="font-serif-display text-2xl font-mono-num" style={{ color: "var(--institution-burgundy)" }}>
                                            Bs. {formatMoney(data.totales.diferencia)}
                                        </div>
                                    </div>
                                </div>
                            </div>

                            <div className="bg-white border rounded-sm overflow-x-auto" style={{ borderColor: "var(--institution-border)" }}>
                                <Table>
                                    <TableHeader>
                                        <TableRow style={{ backgroundColor: "var(--institution-cream)" }}>
                                            <TableHead className="uppercase text-[10px] tracking-widest text-[color:var(--institution-muted)]">Comprobante</TableHead>
                                            <TableHead className="uppercase text-[10px] tracking-widest text-[color:var(--institution-muted)]">Origen / cliente</TableHead>
                                            <TableHead className="uppercase text-[10px] tracking-widest text-[color:var(--institution-muted)]">Fecha</TableHead>
                                            <TableHead className="uppercase text-[10px] tracking-widest text-[color:var(--institution-muted)]">Concepto</TableHead>
                                            <TableHead className="uppercase text-[10px] tracking-widest text-[color:var(--institution-muted)]">Oficina</TableHead>
                                            <TableHead className="text-right uppercase text-[10px] tracking-widest text-[color:var(--institution-muted)]">Válido (Bs.)</TableHead>
                                            <TableHead className="text-right uppercase text-[10px] tracking-widest text-[color:var(--institution-muted)]">Anulado (Bs.)</TableHead>
                                        </TableRow>
                                    </TableHeader>
                                    <TableBody>
                                        {reportRows.flatMap((pago) => {
                                            const items = pagoItems(pago);
                                            const group = items.length ? items : [null];
                                            return group.map((item, index) => {
                                                const first = index === 0;
                                                return (
                                                    <TableRow key={`${pago.id}-${item?.id || index}`}>
                                                        {first && (
                                                            <TableCell rowSpan={group.length} className="font-mono-num align-middle">
                                                                {formatComprobante(pago)}
                                                            </TableCell>
                                                        )}
                                                        {first && (
                                                            <TableCell rowSpan={group.length} className="align-middle">
                                                                {pago.origen} · {pago.estudiante_nombre}
                                                            </TableCell>
                                                        )}
                                                        {first && (
                                                            <TableCell rowSpan={group.length} className="font-mono-num align-middle">
                                                                {formatDate(pago.fecha_pago)}
                                                            </TableCell>
                                                        )}
                                                        <TableCell>
                                                            {item ? (
                                                                <>
                                                                    <div>{item.tipo_pago_nombre || "Concepto"}</div>
                                                                    <div className="text-xs text-[color:var(--institution-muted)]">
                                                                        {item.cantidad} × Bs. {formatMoney(item.monto)} = Bs. {formatMoney(item.total)}
                                                                    </div>
                                                                </>
                                                            ) : "Sin conceptos"}
                                                        </TableCell>
                                                        {first && (
                                                            <TableCell rowSpan={group.length} className="align-middle">
                                                                {pago.office_nombre || reportOfficeName}
                                                            </TableCell>
                                                        )}
                                                        {first && (
                                                            <TableCell rowSpan={group.length} className="text-right font-mono-num align-middle">
                                                                {pago.anulado ? "—" : formatMoney(pago.total)}
                                                            </TableCell>
                                                        )}
                                                        {first && (
                                                            <TableCell rowSpan={group.length} className="text-right font-mono-num align-middle">
                                                                {pago.anulado ? formatMoney(pago.total) : "—"}
                                                            </TableCell>
                                                        )}
                                                    </TableRow>
                                                );
                                            });
                                        })}
                                        {reportRows.length > 0 && (
                                            <>
                                                <TableRow style={{ backgroundColor: "var(--institution-cream)" }}>
                                                    <TableCell colSpan={5} className="text-right uppercase text-xs tracking-widest text-[color:var(--institution-muted)] font-semibold">
                                                        Totales
                                                    </TableCell>
                                                    <TableCell className="text-right font-mono-num font-semibold">
                                                        {formatMoney(data.totales.validos)}
                                                        <div className="text-xs font-normal">Estudiantiles: {formatMoney(data.totales.estudiantiles)} · Alquileres: {formatMoney(data.totales.alquileres)}</div>
                                                    </TableCell>
                                                    <TableCell className="text-right font-mono-num font-semibold">{formatMoney(data.totales.anulados)}</TableCell>
                                                </TableRow>
                                                <TableRow>
                                                    <TableCell colSpan={5} className="text-right uppercase text-xs tracking-widest text-[color:var(--institution-burgundy)] font-semibold">
                                                        Diferencia (Válidos − Anulados)
                                                    </TableCell>
                                                    <TableCell colSpan={2} className="text-right font-mono-num font-bold" style={{ color: "var(--institution-burgundy)" }}>
                                                        Bs. {formatMoney(data.totales.diferencia)}
                                                    </TableCell>
                                                </TableRow>
                                            </>
                                        )}
                                        {reportRows.length === 0 && (
                                            <TableRow>
                                                <TableCell colSpan={7} className="text-center py-10 text-sm text-[color:var(--institution-muted)]">
                                                    Sin pagos en el periodo seleccionado.
                                                </TableCell>
                                            </TableRow>
                                        )}
                                    </TableBody>
                                </Table>
                            </div>
                        </CardContent>
                    </Card>
                </>
            )}
        </div>
    );
}
