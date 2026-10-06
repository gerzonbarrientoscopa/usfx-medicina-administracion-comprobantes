import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { apiClient, formatApiError, formatMoney } from "@/lib/api";
import { formatDate } from "@/lib/dateFormat";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Card, CardContent } from "@/components/ui/card";
import {
    Command,
    CommandEmpty,
    CommandGroup,
    CommandInput,
    CommandItem,
    CommandList,
} from "@/components/ui/command";
import {
    Popover,
    PopoverContent,
    PopoverTrigger,
} from "@/components/ui/popover";
import { Check, ChevronsUpDown, Printer, FileCheck2, X } from "lucide-react";
import { cn } from "@/lib/utils";
import { printComprobante } from "@/components/ComprobantePrint";
import { useOfficeScope } from "@/hooks/useOfficeScope";
import { formatComprobante } from "@/lib/receipt";
import { ClienteField } from "@/components/ClienteField";
import {
    Select, SelectTrigger, SelectValue, SelectContent, SelectItem,
} from "@/components/ui/select";

const readSavedDraftId = (key) => {
    try {
        return key ? window.sessionStorage.getItem(key) : null;
    } catch (_error) {
        return null;
    }
};

const saveDraftId = (key, id) => {
    try {
        if (key) window.sessionStorage.setItem(key, id);
    } catch (_error) {
        // The in-memory receipt remains usable if browser storage is unavailable.
    }
};

const clearSavedDraftId = (key) => {
    try {
        if (key) window.sessionStorage.removeItem(key);
    } catch (_error) {
        // Ignore unavailable browser storage.
    }
};

export default function RegistroPagoPage() {
    const {
        isSuperAdmin, offices, officeId, officeName, selectedOfficeId, setSelectedOfficeId,
    } = useOfficeScope();
    const draftStorageKey = officeId ? `usfx-pago-borrador-${officeId}` : null;
    const [tiposPago, setTiposPago] = useState([]);
    const catalogRequest = useRef(0);

    const [selectedEst, setSelectedEst] = useState(null);
    const [selectedTipo, setSelectedTipo] = useState(null);

    const [tpOpen, setTpOpen] = useState(false);
    
    const [pago, setPago] = useState(null);
    const [cantidad, setCantidad] = useState("1");
    const [fechaPago] = useState(new Date().toISOString().substring(0, 10));

    const [submitting, setSubmitting] = useState(false);

    const loadAll = useCallback(async () => {
        const requestId = ++catalogRequest.current;
        if (isSuperAdmin && !officeId) {
            setTiposPago([]);
            return;
        }
        const loadPages = async (endpoint) => {
            const params = { office_id: officeId, pag: 1, tam: 100 };
            const first = await apiClient.get(endpoint, { params });
            const rest = await Promise.all(
                Array.from({ length: (first.data.pages || 1) - 1 }, (_, index) =>
                    apiClient.get(endpoint, { params: { ...params, pag: index + 2 } }),
                ),
            );
            return [
                ...first.data.items,
                ...rest.flatMap((response) => response.data.items),
            ];
        };
        const types = await loadPages("/tipos-pagos");
        if (requestId === catalogRequest.current) {
            setTiposPago(types);
        }
    }, [officeId, isSuperAdmin]);

    useEffect(() => {
        loadAll().catch((error) => toast.error(formatApiError(error)));
    }, [loadAll]);

    useEffect(() => {
        if (!draftStorageKey) return undefined;
        const draftId = readSavedDraftId(draftStorageKey);
        if (!draftId) return undefined;

        let cancelled = false;
        apiClient.get(`/pagos/${draftId}`)
            .then(({ data }) => {
                if (cancelled) return;
                if (data.estado !== "borrador") {
                    clearSavedDraftId(draftStorageKey);
                    return;
                }
                setPago(data);
                setSelectedEst({
                    id: data.cliente_id,
                    nombre: data.cliente_nombre,
                    ci: data.cliente_ci,
                    cu: data.cliente_cu,
                });
            })
            .catch(() => {
                if (!cancelled) clearSavedDraftId(draftStorageKey);
            });
        return () => { cancelled = true; };
    }, [draftStorageKey]);

    const monto = selectedTipo ? Number(selectedTipo.monto) : 0;
    const subtotal = useMemo(() => {
        const c = Number(cantidad);
        if (isNaN(c) || c <= 0) return 0;
        return monto * c;
    }, [monto, cantidad]);
    const total = Number(pago?.total || 0);

    const generarComprobante = async () => {
        if (!officeId) return toast.error("Seleccione una oficina.");
        if (!selectedEst) return toast.error("Seleccione un cliente.");
        setSubmitting(true);
        try {
            const { data } = await apiClient.post("/pagos", {
                cliente_id: selectedEst.id,
                fecha_pago: fechaPago,
                office_id: officeId,
            });
            setPago(data);
            saveDraftId(draftStorageKey, data.id);
            toast.success(`Comprobante generado: ${formatComprobante(data)}`);
        } catch (e) {
            toast.error(formatApiError(e));
        } finally {
            setSubmitting(false);
        }
    };

    const adicionarItem = async () => {
        if (!pago) return toast.error("Primero genere el comprobante.");
        if (!selectedTipo) return toast.error("Seleccione un concepto de pago.");
        const cant = Number(cantidad);
        if (!Number.isFinite(cant) || cant <= 0) {
            return toast.error("La cantidad debe ser mayor a cero.");
        }
        setSubmitting(true);
        try {
            const { data } = await apiClient.post(`/pagos/${pago.id}/items`, {
                id_tipo_pago: selectedTipo.id,
                cantidad: cant,
            });
            setPago(data);
            setSelectedTipo(null);
            setCantidad("1");
            toast.success("Concepto añadido al comprobante.");
        } catch (e) {
            toast.error(formatApiError(e));
        } finally {
            setSubmitting(false);
        }
    };

    const confirmarComprobante = async () => {
        if (!pago) return toast.error("Primero genere el comprobante.");
        if (!pago.items?.length) {
            return toast.error("Añada al menos un concepto antes de emitir el comprobante.");
        }
        setSubmitting(true);
        try {
            const { data } = await apiClient.post(`/pagos/${pago.id}/finalizar`);
            toast.success(`Pago registrado: ${formatComprobante(data)}`);
            printComprobante(data);
            clearSavedDraftId(draftStorageKey);
            // reset
            setSelectedEst(null);
            setSelectedTipo(null);
            setCantidad("1");
            setPago(null);
        } catch (e) {
            toast.error(formatApiError(e));
        } finally {
            setSubmitting(false);
        }
    };

    const descartarComprobante = async () => {
        if (!pago) return;
        setSubmitting(true);
        try {
            const { data } = await apiClient.delete(`/pagos/${pago.id}/borrador`);
            clearSavedDraftId(draftStorageKey);
            setPago(null);
            setSelectedEst(null);
            setSelectedTipo(null);
            setCantidad("1");
            toast.success(
                data.correlativo_reutilizado
                    ? "Borrador descartado. El correlativo quedó disponible para el próximo comprobante."
                    : "Borrador descartado. Se mantuvo la secuencia para evitar duplicados.",
            );
        } catch (e) {
            toast.error(formatApiError(e));
        } finally {
            setSubmitting(false);
        }
    };
    return (
        <div className="space-y-6" data-testid="registro-page">
            <div>
                <div className="section-eyebrow">Caja</div>
                <h1 className="font-serif-display text-4xl mt-1">Registro de Pago</h1>
                <p className="text-sm text-[color:var(--institution-muted)] mt-1">
                    Seleccione un cliente, genere el comprobante y agregue los conceptos del catálogo.
                </p>
            </div>

            <Card className="rounded-sm border-[color:var(--institution-border)] shadow-none">
                <CardContent className="p-8 grid grid-cols-1 gap-8">
                    {/* Left column - selectors */}
                    <div className="space-y-5">
                        {isSuperAdmin ? (
                            <div className="space-y-1.5">
                                <Label className="text-xs uppercase tracking-widest text-[color:var(--institution-muted)]">Oficina</Label>
                                <Select
                                    value={selectedOfficeId}
                                    onValueChange={(value) => {
                                        setSelectedOfficeId(value);
                                        setSelectedEst(null);
                                        setSelectedTipo(null);
                                    }}
                                    disabled={Boolean(pago)}
                                >
                                    <SelectTrigger className="rounded-sm" data-testid="registro-office-select">
                                        <SelectValue placeholder="Seleccione una oficina" />
                                    </SelectTrigger>
                                    <SelectContent>
                                        {offices.filter((office) => office.activa).map((office) => (
                                            <SelectItem key={office.id} value={office.id}>{office.nombre}</SelectItem>
                                        ))}
                                    </SelectContent>
                                </Select>
                            </div>
                        ) : (
                            <div className="text-sm text-[color:var(--institution-muted)]">Oficina: {officeName}</div>
                        )}
                        <ClienteField
                            officeId={officeId}
                            selectedCliente={selectedEst}
                            onSelectCliente={setSelectedEst}
                            disabled={Boolean(pago)}
                        />

                        <Button
                            type="button"
                            onClick={generarComprobante}                            
                            disabled={!officeId || !selectedEst || pago || submitting}
                            className="rounded-sm w-full text-white h-11 uppercase text-xs tracking-widest"
                            style={{ backgroundColor: "var(--institution-navy)" }}
                            data-testid="generar-comprobante-btn"
                        >
                            <FileCheck2 size={16} className="mr-2" /> Generar comprobante
                        </Button>
                    </div>

                    {pago && (
                        <div
                            className="border rounded-sm p-6 space-y-4 relative"
                            style={{ borderColor: "var(--institution-border)", backgroundColor: "var(--institution-cream)" }}
                        >
                        <div className="flex items-center justify-between">
                            <div className="section-eyebrow">Comprobante N°</div>
                            <div
                                className="font-serif-display text-3xl font-bold font-mono-num"
                                style={{ color: "var(--institution-burgundy)" }}
                                data-testid="comprobante-display"
                            >                                
                                {formatComprobante(pago)}
                            </div>
                        </div>

                        <div className="space-y-2 pt-2">
                            <Row label="Oficina" value={officeName || "—"} />
                            <Row label="Cliente" value={selectedEst ? `${selectedEst.nombre}` : "—"} />
                            <Row label="C.I." value={selectedEst?.ci || "—"} />
                            <Row label="Fecha de pago" value={formatDate(pago.fecha_pago || fechaPago)} />
                        </div>

                                <div className="space-y-3 border-t pt-4" style={{ borderColor: "var(--institution-border)" }}>
                                    <Label className="text-xs uppercase tracking-widest text-[color:var(--institution-muted)]">
                                        Añadir concepto de pago
                                    </Label>
                                    <Popover open={tpOpen} onOpenChange={setTpOpen}>
                                        <PopoverTrigger asChild>
                                            <Button
                                                variant="outline"
                                                role="combobox"
                                                disabled={submitting}
                                                className="rounded-sm justify-between w-full font-normal bg-white"
                                                data-testid="tipopago-select-btn"
                                            >
                                                <span className="truncate">
                                                    {selectedTipo ? selectedTipo.nombre : "Buscar concepto en el catálogo…"}
                                                </span>
                                                <ChevronsUpDown size={14} className="ml-2 opacity-50" />
                                            </Button>
                                        </PopoverTrigger>
                                        <PopoverContent className="p-0 rounded-sm" align="start" style={{ width: "var(--radix-popover-trigger-width)" }}>
                                            <Command>
                                                <CommandInput placeholder="Buscar tipo de pago…" />
                                                <CommandList>
                                                    <CommandEmpty>Sin resultados.</CommandEmpty>
                                                    <CommandGroup>
                                                        {tiposPago.map((t) => (
                                                            <CommandItem
                                                                key={t.id}
                                                                value={t.nombre}
                                                                onSelect={() => {
                                                                    setSelectedTipo(t);
                                                                    setTpOpen(false);
                                                                }}
                                                                data-testid={`tp-option-${t.id}`}
                                                            >
                                                                <Check
                                                                    className={cn(
                                                                        "mr-2 h-4 w-4",
                                                                        selectedTipo?.id === t.id ? "opacity-100" : "opacity-0",
                                                                    )}
                                                                />
                                                                <div className="flex-1">
                                                                    <div className="font-medium text-sm">{t.nombre}</div>
                                                                    <div className="text-xs text-[color:var(--institution-muted)]">
                                                                        Bs. {formatMoney(t.monto)}
                                                                    </div>
                                                                </div>
                                                            </CommandItem>
                                                        ))}
                                                    </CommandGroup>
                                                </CommandList>
                                            </Command>
                                        </PopoverContent>
                                    </Popover>
                                    <div className="grid grid-cols-[1fr_auto] gap-3 items-end">
                                        <div className="space-y-1.5">
                                            <Label className="text-xs uppercase tracking-widest text-[color:var(--institution-muted)]">
                                                Cantidad
                                            </Label>
                                            <Input
                                                type="number"
                                                min="0.01"
                                                step="any"
                                                value={cantidad}
                                                onChange={(event) => setCantidad(event.target.value)}
                                                disabled={submitting}
                                                data-testid="cantidad-input"
                                                className="rounded-sm bg-white"
                                            />
                                        </div>
                                        <div className="text-right pb-2">
                                            <div className="text-[10px] uppercase tracking-widest text-[color:var(--institution-muted)]">
                                                Subtotal
                                            </div>
                                            <div className="font-mono-num font-semibold">
                                                Bs. {formatMoney(subtotal)}
                                            </div>
                                        </div>
                                    </div>
                                    <Button
                                        type="button"
                                        onClick={adicionarItem}
                                        disabled={!selectedTipo || submitting}
                                        className="rounded-sm w-full text-white"
                                        style={{ backgroundColor: "var(--institution-navy)" }}
                                        data-testid="add-pago-item-btn"
                                    >
                                        <Plus size={15} className="mr-2" /> Añadir concepto
                                    </Button>
                                </div>

                                <div className="space-y-2">
                                    <div className="text-xs uppercase tracking-widest text-[color:var(--institution-muted)]">
                                        Conceptos del comprobante ({pago.items?.length || 0})
                                    </div>
                                    {pago.items?.length ? (
                                        <div className="divide-y rounded-sm border bg-white px-3" style={{ borderColor: "var(--institution-border)" }}>
                                            {pago.items.map((item, index) => (
                                                <div key={item.id || `${item.id_tipo_pago}-${index}`} className="flex items-center justify-between gap-3 py-2 text-sm">
                                                    <div className="min-w-0">
                                                        <div className="font-medium truncate">{item.tipo_pago_nombre}</div>
                                                        <div className="text-xs text-[color:var(--institution-muted)]">
                                                            {item.cantidad} × Bs. {formatMoney(item.monto)}
                                                        </div>
                                                    </div>
                                                    <div className="shrink-0 font-mono-num font-semibold">
                                                        Bs. {formatMoney(item.total)}
                                                    </div>
                                                </div>
                                            ))}
                                        </div>
                                    ) : (
                                        <p className="text-sm text-[color:var(--institution-muted)]">
                                            Aún no se añadieron conceptos.
                                        </p>
                                    )}
                                </div>

                                <div className="border-t pt-3 flex items-center justify-between" style={{ borderColor: "var(--institution-border)" }}>
                                    <span className="text-xs uppercase tracking-widest text-[color:var(--institution-muted)]">Total del comprobante</span>
                                    <span className="font-serif-display text-3xl font-bold font-mono-num" style={{ color: "var(--institution-burgundy)" }} data-testid="total-display">
                                        Bs. {formatMoney(total)}
                                    </span>
                                </div>

                                <div className="space-y-2">
                                    <Button
                                        type="button"
                                        onClick={confirmarComprobante}
                                        disabled={!pago.items?.length || submitting}
                                        className="w-full rounded-sm text-white h-11 uppercase text-xs tracking-widest"
                                        style={{ backgroundColor: "var(--institution-burgundy)" }}
                                        data-testid="confirmar-comprobante-btn"
                                    >
                                        <Printer size={16} className="mr-2" /> Emitir e imprimir
                                    </Button>
                                    <Button
                                        type="button"
                                        variant="outline"
                                        onClick={descartarComprobante}
                                        disabled={submitting}
                                        className="w-full rounded-sm"
                                    >
                                        <X size={14} className="mr-2" /> Descartar borrador
                                    </Button>
                                </div>
                        </div>
                    )}
                </CardContent>
            </Card>

        </div>
    );
}

function Row({ label, value }) {
    return (
        <div className="flex items-center justify-between py-1 border-b border-dotted" style={{ borderColor: "var(--institution-border)" }}>
            <span className="text-xs uppercase tracking-widest text-[color:var(--institution-muted)]">{label}</span>
            <span className="text-sm font-medium text-right">{value}</span>
        </div>
    );
}
