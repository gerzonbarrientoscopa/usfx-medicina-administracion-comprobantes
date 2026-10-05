import React, { useEffect, useRef, useState } from "react";
import { apiClient, formatApiError, formatMoney } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { useOfficeScope } from "@/hooks/useOfficeScope";
import { formatComprobante } from "@/lib/receipt";
import { useAuth } from "@/contexts/AuthContext";
import { canAnnulPayment } from "@/lib/paymentAnnulmentPolicy";
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

const pagoItems = (pago) => {
    if (Array.isArray(pago.items) && pago.items.length) return pago.items;
    if (!pago.id_tipo_pago && !pago.tipo_pago_nombre) return [];
    return [{
        tipo_pago_nombre: pago.tipo_pago_nombre || "",
        cantidad: pago.cantidad,
        monto: pago.monto,
    }];
};

const comprobanteItems = (pago) => pago.origen === "alquiler"
    ? [{
        tipo_pago_nombre: `${pago.ambiente_nombre || "Ambiente"} · ${pago.tarifa_nombre || "Alquiler"}`,
        cantidad: pago.cantidad,
        monto: pago.monto,
        total: pago.total,
    }]
    : pagoItems(pago);

export default function AnularPagoPage() {
    const { user } = useAuth();
    const {
        isSuperAdmin, offices, officeId, selectedOfficeId, setSelectedOfficeId, officeParams,
    } = useOfficeScope();
    const [textoBuscar, setTextoBuscar] = useState("");
    const [pagos, setPagos] = useState([]);
    const [usuarios, setUsuarios] = useState([]);
    const [pagina, setPagina] = useState(1);
    const [totalPaginas, setTotalPaginas] = useState(1);
    const [totalResultados, setTotalResultados] = useState(0);
    const [loading, setLoading] = useState(false);
    const requestId = useRef(0);
    const FILAS_POR_PAGINA = 20;

    useEffect(() => {
        let cancelled = false;
        setUsuarios([]);
        apiClient.get("/reportes/registradores", {
            params: officeId ? { office_id: officeId } : {},
        }).then(({ data }) => {
            if (!cancelled) setUsuarios(data);
        }).catch((error) => {
            if (!cancelled) toast.error(formatApiError(error));
        });
        return () => { cancelled = true; };
    }, [officeId]);

    const buscar = async (paginaSolicitada = 1) => {
        if (!textoBuscar.trim()) {
            toast.error("Ingrese código de comprobante o nombre del cliente");
            return;
        }
        const currentRequest = ++requestId.current;
        setLoading(true);
        try {
            const { data } = await apiClient.get("/comprobantes", {
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
            const endpoint = pago.origen === "alquiler"
                ? `/alquileres/${pago.id}/anular`
                : `/pagos/${pago.id}/anular`;
            await apiClient.post(endpoint);
            toast.success(`Comprobante ${formatComprobante(pago)} anulado.`);
            setPagos((prev) => prev.map((x) => (x.id === pago.id && x.origen === pago.origen
                ? { ...x, anulado: true, ...(x.origen === "alquiler" ? { estado: "cancelado" } : {}) }
                : x)));
        } catch (e) {
            toast.error(formatApiError(e));
        }
    };

    return (
        <div className="space-y-6" data-testid="anular-page">
            <div>
                <div className="section-eyebrow">Operaciones de auditoría</div>
                <h1 className="font-serif-display text-4xl mt-1">Anular comprobante</h1>
                <p className="text-sm text-[color:var(--institution-muted)] mt-1">
                    La anulación no elimina el registro: queda almacenado con estado anulado para fines de auditoría.
                </p>
                {user?.rol === "Caja" && (
                    <p className="text-sm text-[color:var(--institution-muted)] mt-1">
                        Caja solo puede anular sus propios comprobantes el día de la fecha impresa.
                    </p>
                )}
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
                            Número de comprobante, cliente o cliente
                        </Label>
                        <Input
                            placeholder="Ej. 00014, 00014/2026 o nombre"
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

            <div className="bg-white border rounded-sm overflow-x-auto" style={{ borderColor: "var(--institution-border)" }}>
                <Table>
                    <TableHeader>
                        <TableRow style={{ backgroundColor: "var(--institution-cream)" }}>
                            <TableHead className="uppercase text-[10px] tracking-widest text-[color:var(--institution-muted)]">Código</TableHead>
                            {isSuperAdmin && <TableHead className="uppercase text-[10px] tracking-widest text-[color:var(--institution-muted)]">Oficina</TableHead>}
                            <TableHead className="uppercase text-[10px] tracking-widest text-[color:var(--institution-muted)]">Origen</TableHead>
                            <TableHead className="uppercase text-[10px] tracking-widest text-[color:var(--institution-muted)]">Cliente / cliente</TableHead>
                            <TableHead className="uppercase text-[10px] tracking-widest text-[color:var(--institution-muted)]">Conceptos y detalle</TableHead>
                            <TableHead className="text-right uppercase text-[10px] tracking-widest text-[color:var(--institution-muted)]">Total comprobante</TableHead>
                            <TableHead className="uppercase text-[10px] tracking-widest text-[color:var(--institution-muted)]">Fecha</TableHead>
                            <TableHead className="uppercase text-[10px] tracking-widest text-[color:var(--institution-muted)]">Registrado por</TableHead>
                            <TableHead className="uppercase text-[10px] tracking-widest text-[color:var(--institution-muted)]">Estado</TableHead>
                            <TableHead className="text-right uppercase text-[10px] tracking-widest text-[color:var(--institution-muted)]">Acciones</TableHead>
                        </TableRow>
                    </TableHeader>
                    <TableBody>
                        {pagos.map((pago) => (
                            <TableRow key={pago.id}>
                                <TableCell className="font-mono-num font-medium">
                                    {formatComprobante(pago)}
                                </TableCell>
                                {isSuperAdmin && <TableCell>{pago.office_nombre || "—"}</TableCell>}
                                <TableCell>{pago.origen === "alquiler" ? "Alquiler" : "de cliente"}</TableCell>
                                <TableCell>{pago.origen === "alquiler" ? pago.cliente_nombre || "—" : pago.cliente_nombre || "—"}</TableCell>
                                <TableCell>
                                    <div className="min-w-[420px]">
                                        <div className="grid grid-cols-[minmax(120px,1fr)_64px_92px_92px] gap-3 border-b pb-1 text-[9px] uppercase tracking-wider text-[color:var(--institution-muted)]">
                                            <span>Concepto / ambiente</span>
                                            <span className="text-right">Cantidad</span>
                                            <span className="text-right">Precio unit.</span>
                                            <span className="text-right">Subtotal</span>
                                        </div>
                                        {comprobanteItems(pago).length ? comprobanteItems(pago).map((item, index) => (
                                            <div
                                                key={`${item.id_tipo_pago || item.tipo_pago_nombre}-${index}`}
                                                className="grid grid-cols-[minmax(120px,1fr)_64px_92px_92px] gap-3 border-b last:border-b-0 py-1.5 text-xs"
                                            >
                                                <span className="font-medium">{item.tipo_pago_nombre || "—"}</span>
                                                <span className="text-right font-mono-num">{item.cantidad ?? "—"}</span>
                                                <span className="text-right font-mono-num">{formatMoney(item.monto)}</span>
                                                <span className="text-right font-mono-num">{formatMoney(item.total ?? Number(item.cantidad || 0) * Number(item.monto || 0))}</span>
                                            </div>
                                        )) : <div className="py-1.5 text-xs text-[color:var(--institution-muted)]">Sin conceptos.</div>}
                                    </div>
                                </TableCell>
                                <TableCell className="text-right font-mono-num font-semibold">{formatMoney(pago.total)}</TableCell>
                                <TableCell className="font-mono-num">{pago.fecha_pago}</TableCell>
                                <TableCell className="text-xs text-[color:var(--institution-muted)]">
                                    {pago.origen === "alquiler"
                                        ? usuarios.find((usuario) => usuario.id === pago.paid_by)?.nombre || "—"
                                        : pago.created_by_name || "—"}
                                </TableCell>
                                <TableCell>
                                    {pago.anulado || (pago.origen === "alquiler" && pago.estado === "cancelado") ? (
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
                                                disabled={!canAnnulPayment(pago, user)}
                                                className="rounded-sm"
                                                data-testid={`anular-btn-${pago.id}`}
                                                style={canAnnulPayment(pago, user) ? { color: "var(--institution-danger)", borderColor: "var(--institution-danger)" } : {}}
                                                title={user?.rol === "Caja" && !canAnnulPayment(pago, user)
                                                    ? "Solo puede anular sus propios comprobantes el día de la fecha impresa."
                                                    : undefined}
                                            >
                                                <Ban size={12} className="mr-1" />
                                                {pago.anulado || (pago.origen === "alquiler" && pago.estado === "cancelado") ? "Anulado" : "Anular"}
                                            </Button>
                                        </AlertDialogTrigger>
                                        <AlertDialogContent className="rounded-sm">
                                            <AlertDialogHeader>
                                                <AlertDialogTitle className="font-serif-display text-2xl">
                                                    Confirmar anulación
                                                </AlertDialogTitle>
                                                <AlertDialogDescription>
                                                    El comprobante <strong>{formatComprobante(pago)}</strong> de{" "}
                                                    <strong>{pago.origen === "alquiler" ? pago.cliente_nombre : pago.cliente_nombre}</strong> por <strong>Bs. {formatMoney(pago.total)}</strong> quedará anulado y no podrá revertirse.
                                                    {pago.origen === "alquiler" && " El horario del ambiente quedará disponible nuevamente."}
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
                                <TableCell colSpan={isSuperAdmin ? 10 : 9} className="text-center py-12 text-sm text-[color:var(--institution-muted)]">
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
