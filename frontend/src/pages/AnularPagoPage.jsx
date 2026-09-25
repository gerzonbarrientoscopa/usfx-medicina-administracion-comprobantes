import React, { useRef, useState } from "react";
import { apiClient, formatApiError, formatMoney } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { useOfficeScope } from "@/hooks/useOfficeScope";
import {
    Table,
    TableBody,
    TableCell,
    TableHead,
    TableHeader,
    TableRow,
} from "@/components/ui/table";
import { Card, CardContent } from "@/components/ui/card";
import { Ban, Search, ChevronLeft, ChevronRight } from "lucide-react";
import { toast } from "sonner";
import {
    AlertDialog,
    AlertDialogAction,
    AlertDialogCancel,
    AlertDialogContent,
    AlertDialogDescription,
    AlertDialogFooter,
    AlertDialogHeader,
    AlertDialogTitle,
    AlertDialogTrigger,
} from "@/components/ui/alert-dialog";

export default function AnularPagoPage() {
    const {
        isSuperAdmin, offices, selectedOfficeId, setSelectedOfficeId, officeParams, officeName,
    } = useOfficeScope();
    const [textoBuscar, setTextoBuscar] = useState("");
    const [pagos, setPagos] = useState([]);
    const [pagina, setPagina] = useState(1);
    const [totalPaginas, setTotalPaginas] = useState(1);
    const [totalResultados, setTotalResultados] = useState(0);
    const [loading, setLoading] = useState(false);
    const requestId = useRef(0);
    const FILAS_POR_PAGINA = 20;

    const buscar = async (paginaSolicitada = 1) => {
        if (!textoBuscar.trim()) {
            toast.error("Ingrese código de comprobante o nombre del estudiante");
            return;
        }
        const currentRequest = ++requestId.current;
        setLoading(true);
        try {
            const { data } = await apiClient.get("/pagos", {
                params: {
                    q: textoBuscar.trim(),
                    pag: paginaSolicitada,
                    tam: FILAS_POR_PAGINA,
                    ...officeParams,
                },
            });
            if (currentRequest !== requestId.current) return;
            setPagos(data.items);
            setPagina(data.page);
            setTotalPaginas(data.pages || 1);
            setTotalResultados(data.total);
            if (data.items.length === 0)
                toast.message("Sin resultados.");
        } catch (e) {
            if (currentRequest === requestId.current) toast.error(formatApiError(e));
        } finally {
            if (currentRequest === requestId.current) setLoading(false);
        }
    };

    const anular = async (pago) => {
        try {
            await apiClient.post(`/pagos/${pago.id}/anular`);
            toast.success(`Comprobante ${pago.cod_comprobante}/${pago.gestion} anulado.`);
            setPagos((prev) => prev.map((x) => (x.id === pago.id ? { ...x, anulado: true } : x)));
        } catch (e) {
            toast.error(formatApiError(e));
        }
    };

    return (
        <div className="space-y-6" data-testid="anular-page">
            <div>
                <div className="section-eyebrow">Operaciones de auditoría</div>
                <h1 className="font-serif-display text-4xl mt-1">Anular Pago</h1>
                <p className="text-sm text-[color:var(--institution-muted)] mt-1">
                    La anulación no elimina el registro: queda almacenado con estado anulado para fines de auditoría.
                </p>
            </div>

            <Card className="rounded-sm border-[color:var(--institution-border)] shadow-none">
                <CardContent className="p-6 flex flex-col md:flex-row gap-4 md:items-end">
                    {isSuperAdmin && (
                        <div className="space-y-1.5 min-w-[220px]">
                            <Label className="text-xs uppercase tracking-widest text-[color:var(--institution-muted)]">Oficina</Label>
                            <Select
                                value={selectedOfficeId || "all"}
                                onValueChange={(value) => {
                                    requestId.current += 1;
                                    setSelectedOfficeId(value === "all" ? "" : value);
                                    setLoading(false);
                                    setPagos([]);
                                    setTotalResultados(0);
                                    setPagina(1);
                                }}
                            >
                                <SelectTrigger className="rounded-sm" data-testid="anular-office-select">
                                    <SelectValue placeholder="Todas las oficinas" />
                                </SelectTrigger>
                                <SelectContent>
                                    <SelectItem value="all">Todas las oficinas</SelectItem>
                                    {offices.map((office) => (
                                        <SelectItem key={office.id} value={office.id}>{office.nombre}</SelectItem>
                                    ))}
                                </SelectContent>
                            </Select>
                        </div>
                    )}
                    <div className="space-y-1.5 flex-1">
                        <Label className="text-xs uppercase tracking-widest text-[color:var(--institution-muted)]">
                            Número de comprobante o nombre del estudiante
                        </Label>
                        <Input
                            placeholder="Ej. 00001/2026 ó Juan Pérez"
                            value={textoBuscar}
                            onChange={(e) => setTextoBuscar(e.target.value)}
                            onKeyDown={(e) => e.key === "Enter" && buscar(1)}
                            className="rounded-sm"
                            data-testid="anular-q-input"
                        />
                    </div>
                    <Button
                        onClick={() => buscar(1)}
                        disabled={loading}
                        className="rounded-sm text-white"
                        style={{ backgroundColor: "var(--institution-burgundy)" }}
                        data-testid="anular-buscar-btn"
                    >
                        <Search size={14} className="mr-2" /> Buscar
                    </Button>
                </CardContent>
            </Card>

            <div className="bg-white border rounded-sm" style={{ borderColor: "var(--institution-border)" }}>
                <Table>
                    <TableHeader>
                        <TableRow style={{ backgroundColor: "var(--institution-cream)" }}>
                            <TableHead className="uppercase text-[10px] tracking-widest text-[color:var(--institution-muted)]">Código</TableHead>
                            {isSuperAdmin && <TableHead className="uppercase text-[10px] tracking-widest text-[color:var(--institution-muted)]">Oficina</TableHead>}
                            <TableHead className="uppercase text-[10px] tracking-widest text-[color:var(--institution-muted)]">Estudiante</TableHead>
                            <TableHead className="uppercase text-[10px] tracking-widest text-[color:var(--institution-muted)]">Tipo</TableHead>
                            <TableHead className="text-right uppercase text-[10px] tracking-widest text-[color:var(--institution-muted)]">Total</TableHead>
                            <TableHead className="uppercase text-[10px] tracking-widest text-[color:var(--institution-muted)]">Fecha</TableHead>
                            <TableHead className="uppercase text-[10px] tracking-widest text-[color:var(--institution-muted)]">Estado</TableHead>
                            <TableHead className="text-right uppercase text-[10px] tracking-widest text-[color:var(--institution-muted)]">Acción</TableHead>
                        </TableRow>
                    </TableHeader>
                    <TableBody>
                        {pagos.map((pago) => (
                            <TableRow key={pago.id}>
                                <TableCell className="font-mono-num font-medium">
                                    {pago.cod_comprobante}/{pago.gestion}
                                </TableCell>
                                {isSuperAdmin && <TableCell>{pago.office_nombre || officeName}</TableCell>}
                                <TableCell>{pago.estudiante_nombre || "—"}</TableCell>
                                <TableCell>{pago.tipo_pago_nombre || "—"}</TableCell>
                                <TableCell className="text-right font-mono-num">{formatMoney(pago.total)}</TableCell>
                                <TableCell className="font-mono-num">{pago.fecha_pago}</TableCell>
                                <TableCell>
                                    {pago.anulado ? (
                                        <span className="pill pill-void">Anulado</span>
                                    ) : (
                                        <span className="pill pill-valid">Válido</span>
                                    )}
                                </TableCell>
                                <TableCell className="text-right">
                                    <AlertDialog>
                                        <AlertDialogTrigger asChild>
                                            <Button
                                                size="sm"
                                                variant="outline"
                                                disabled={pago.anulado}
                                                className="rounded-sm"
                                                data-testid={`anular-btn-${pago.id}`}
                                                style={!pago.anulado ? { color: "var(--institution-danger)", borderColor: "var(--institution-danger)" } : {}}
                                            >
                                                <Ban size={12} className="mr-1" />
                                                {pago.anulado ? "Anulado" : "Anular"}
                                            </Button>
                                        </AlertDialogTrigger>
                                        <AlertDialogContent className="rounded-sm">
                                            <AlertDialogHeader>
                                                <AlertDialogTitle className="font-serif-display text-2xl">
                                                    Confirmar anulación
                                                </AlertDialogTitle>
                                                <AlertDialogDescription>
                                                     El comprobante <strong>{pago.cod_comprobante}/{pago.gestion}</strong> de{" "}
                                                    <strong>{pago.estudiante_nombre}</strong> por <strong>Bs. {formatMoney(pago.total)}</strong> quedará anulado y no podrá revertirse.
                                                </AlertDialogDescription>
                                            </AlertDialogHeader>
                                            <AlertDialogFooter>
                                                <AlertDialogCancel className="rounded-sm">Cancelar</AlertDialogCancel>
                                                <AlertDialogAction
                                                    onClick={() => anular(pago)}
                                                    className="rounded-sm text-white"
                                                    style={{ backgroundColor: "var(--institution-danger)" }}
                                                    data-testid={`confirm-anular-${pago.id}`}
                                                >
                                                    Sí, anular
                                                </AlertDialogAction>
                                            </AlertDialogFooter>
                                        </AlertDialogContent>
                                    </AlertDialog>
                                </TableCell>
                            </TableRow>
                        ))}
                        {pagos.length === 0 && (
                            <TableRow>
                                <TableCell colSpan={isSuperAdmin ? 8 : 7} className="text-center py-12 text-sm text-[color:var(--institution-muted)]">
                                    Ingrese un criterio de búsqueda y presione Buscar.
                                </TableCell>
                            </TableRow>
                        )}
                    </TableBody>
                </Table>
            </div>
            {totalResultados > 0 && (
                <div className="flex items-center justify-between px-2 text-xs text-[color:var(--institution-muted)]">
                    <div>
                        Página <b>{pagina}</b> de <b>{totalPaginas}</b> · {totalResultados} resultado{totalResultados === 1 ? "" : "s"}
                    </div>
                    <div className="flex items-center gap-2">
                        <Button
                            variant="outline"
                            size="sm"
                            className="rounded-sm gap-1 h-8 px-3"
                            onClick={() => buscar(Math.max(pagina - 1, 1))}
                            disabled={loading || pagina === 1}
                        >
                            <ChevronLeft size={14} />
                            Anterior
                        </Button>
                        <Button
                            variant="outline"
                            size="sm"
                            className="rounded-sm gap-1 h-8 px-3"
                            onClick={() => buscar(Math.min(pagina + 1, totalPaginas))}
                            disabled={loading || pagina === totalPaginas}
                        >
                            Siguiente
                            <ChevronRight size={14} />
                        </Button>
                    </div>
                </div>
            )}
        </div>
    );
}
