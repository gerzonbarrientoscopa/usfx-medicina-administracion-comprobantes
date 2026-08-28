import React, { useState } from "react";
import { apiClient, formatApiError, formatMoney } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
    Table,
    TableBody,
    TableCell,
    TableHead,
    TableHeader,
    TableRow,
} from "@/components/ui/table";
import { Card, CardContent } from "@/components/ui/card";
import { Ban, Search } from "lucide-react";
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
    const [q, setQ] = useState("");
    const [pagos, setPagos] = useState([]);

    const buscar = async () => {
        if (!q.trim()) {
            toast.error("Ingrese código de comprobante o nombre del estudiante");
            return;
        }
        try {
            const { data } = await apiClient.get("/pagos", { params: { q } });
            setPagos(data);
            if (data.length === 0) toast.message("Sin resultados");
        } catch (e) {
            toast.error(formatApiError(e));
        }
    };

    const anular = async (p) => {
        try {
            await apiClient.post(`/pagos/${p.id}/anular`);
            toast.success(`Comprobante ${p.codcomprobante}/${p.gestion} anulado`);
            // refresh local list
            setPagos((prev) => prev.map((x) => (x.id === p.id ? { ...x, anulado: true } : x)));
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
                    <div className="space-y-1.5 flex-1">
                        <Label className="text-xs uppercase tracking-widest text-[color:var(--institution-muted)]">
                            Número de comprobante o nombre del estudiante
                        </Label>
                        <Input
                            placeholder="Ej. 00001/2026 ó Juan Pérez"
                            value={q}
                            onChange={(e) => setQ(e.target.value)}
                            onKeyDown={(e) => e.key === "Enter" && buscar()}
                            className="rounded-sm"
                            data-testid="anular-q-input"
                        />
                    </div>
                    <Button
                        onClick={buscar}
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
                            <TableHead className="uppercase text-[10px] tracking-widest text-[color:var(--institution-muted)]">Estudiante</TableHead>
                            <TableHead className="uppercase text-[10px] tracking-widest text-[color:var(--institution-muted)]">Tipo</TableHead>
                            <TableHead className="text-right uppercase text-[10px] tracking-widest text-[color:var(--institution-muted)]">Total</TableHead>
                            <TableHead className="uppercase text-[10px] tracking-widest text-[color:var(--institution-muted)]">Fecha</TableHead>
                            <TableHead className="uppercase text-[10px] tracking-widest text-[color:var(--institution-muted)]">Estado</TableHead>
                            <TableHead className="text-right uppercase text-[10px] tracking-widest text-[color:var(--institution-muted)]">Acción</TableHead>
                        </TableRow>
                    </TableHeader>
                    <TableBody>
                        {pagos.map((p) => (
                            <TableRow key={p.id}>
                                <TableCell className="font-mono-num font-medium">
                                    {p.codcomprobante}/{p.gestion}
                                </TableCell>
                                <TableCell>{p.estudiante_nombre || "—"}</TableCell>
                                <TableCell>{p.tipopago_nombre || "—"}</TableCell>
                                <TableCell className="text-right font-mono-num">{formatMoney(p.total)}</TableCell>
                                <TableCell className="font-mono-num">{p.fecha_pago}</TableCell>
                                <TableCell>
                                    {p.anulado ? (
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
                                                disabled={p.anulado}
                                                className="rounded-sm"
                                                data-testid={`anular-btn-${p.id}`}
                                                style={!p.anulado ? { color: "var(--institution-danger)", borderColor: "var(--institution-danger)" } : {}}
                                            >
                                                <Ban size={12} className="mr-1" />
                                                {p.anulado ? "Anulado" : "Anular"}
                                            </Button>
                                        </AlertDialogTrigger>
                                        <AlertDialogContent className="rounded-sm">
                                            <AlertDialogHeader>
                                                <AlertDialogTitle className="font-serif-display text-2xl">
                                                    Confirmar anulación
                                                </AlertDialogTitle>
                                                <AlertDialogDescription>
                                                    El comprobante <strong>{p.codcomprobante}/{p.gestion}</strong> de{" "}
                                                    <strong>{p.estudiante_nombre}</strong> por <strong>Bs. {formatMoney(p.total)}</strong> quedará anulado y no podrá revertirse.
                                                </AlertDialogDescription>
                                            </AlertDialogHeader>
                                            <AlertDialogFooter>
                                                <AlertDialogCancel className="rounded-sm">Cancelar</AlertDialogCancel>
                                                <AlertDialogAction
                                                    onClick={() => anular(p)}
                                                    className="rounded-sm text-white"
                                                    style={{ backgroundColor: "var(--institution-danger)" }}
                                                    data-testid={`confirm-anular-${p.id}`}
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
                                <TableCell colSpan={7} className="text-center py-12 text-sm text-[color:var(--institution-muted)]">
                                    Ingrese un criterio de búsqueda y presione Buscar.
                                </TableCell>
                            </TableRow>
                        )}
                    </TableBody>
                </Table>
            </div>
        </div>
    );
}
