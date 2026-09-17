import React, { useEffect, useMemo, useState } from "react";
import { apiClient, formatApiError, formatMoney } from "@/lib/api";
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
import {
    Dialog,
    DialogContent,
    DialogHeader,
    DialogTitle,
    DialogFooter,
} from "@/components/ui/dialog";
import { Check, ChevronsUpDown, Plus, Printer, FileCheck2 } from "lucide-react";
import { cn } from "@/lib/utils";
import { printComprobante } from "@/components/ComprobantePrint";

const NEW_EST_EMPTY = { codigo: "", ci: "", cu: "", nombre: "", gestion: new Date().getFullYear() };

export default function RegistroPagoPage() {
    const [estudiantes, setEstudiantes] = useState([]);
    const [tiposPago, setTiposPago] = useState([]);

    const [selectedEst, setSelectedEst] = useState(null);
    const [selectedTipo, setSelectedTipo] = useState(null);

    const [estOpen, setEstOpen] = useState(false);
    const [tpOpen, setTpOpen] = useState(false);

    const [comprobante, setComprobante] = useState(null); // {cod_comprobante, gestion, display}
    const [cantidad, setCantidad] = useState("1");
    const [fechaPago, setFechaPago] = useState(new Date().toISOString().substring(0, 10));

    const [newEstOpen, setNewEstOpen] = useState(false);
    const [newEst, setNewEst] = useState(NEW_EST_EMPTY);

    const [submitting, setSubmitting] = useState(false);

    const loadAll = async () => {
        const [estudiantesResponse, tiposResponse] = await Promise.all([
            apiClient.get("/estudiantes"),
            apiClient.get("/tipos-pagos"),
        ]);
        setEstudiantes(estudiantesResponse.data.items);
        setTiposPago(tiposResponse.data.items);
    };

    useEffect(() => {
        loadAll();
    }, []);

    const monto = selectedTipo ? Number(selectedTipo.monto) : 0;
    const total = useMemo(() => {
        const c = Number(cantidad);
        if (isNaN(c) || c <= 0) return 0;
        return monto * c;
    }, [monto, cantidad]);

    const generarComprobante = async () => {
        if (!selectedEst) return toast.error("Seleccione un estudiante.");
        if (!selectedTipo) return toast.error("Seleccione un tipo de pago.");
        try {
            const { data } = await apiClient.get("/pagos/preview-comprobante");
            setComprobante(data);
            toast.success(`Comprobante generado: ${data.display}`);
        } catch (e) {
            toast.error(formatApiError(e));
        }
    };

    const confirmarComprobante = async () => {
        if (!comprobante) return toast.error("Primero genere el comprobante.");
        const cant = Number(cantidad);
        if (!cant || cant <= 0) return toast.error("La cantidad debe ser mayor a cero.");
        if (!fechaPago) return toast.error("Indique la fecha de pago.");
        setSubmitting(true);
        try {
            const { data } = await apiClient.post("/pagos", {
                id_estudiante: selectedEst.id,
                id_tipo_pago: selectedTipo.id,
                cantidad: cant,
                fecha_pago: fechaPago,
            });
            toast.success(`Pago registrado: ${data.cod_comprobante}/${data.gestion}`);
            printComprobante(data);
            // reset
            setSelectedEst(null);
            setSelectedTipo(null);
            setCantidad("1");
            setComprobante(null);
            setFechaPago(new Date().toISOString().substring(0, 10));
        } catch (e) {
            toast.error(formatApiError(e));
        } finally {
            setSubmitting(false);
        }
    };

    const onCreateNewEst = async (e) => {
        e.preventDefault();
        try {
            const { data } = await apiClient.post("/estudiantes", {
                ...newEst,
                gestion: Number(newEst.gestion),
            });
            toast.success("Estudiante registrado");
            await loadAll();
            setSelectedEst(data);
            setNewEst(NEW_EST_EMPTY);
            setNewEstOpen(false);
        } catch (err) {
            toast.error(formatApiError(err));
        }
    };

    return (
        <div className="space-y-6" data-testid="registro-page">
            <div>
                <div className="section-eyebrow">Caja</div>
                <h1 className="font-serif-display text-4xl mt-1">Registro de Pago</h1>
                <p className="text-sm text-[color:var(--institution-muted)] mt-1">
                    Genere el comprobante, confirme y se procederá a la impresión automática.
                </p>
            </div>

            <Card className="rounded-sm border-[color:var(--institution-border)] shadow-none">
                <CardContent className="p-8 grid grid-cols-1 lg:grid-cols-2 gap-8">
                    {/* Left column - selectors */}
                    <div className="space-y-5">
                        <div className="space-y-1.5">
                            <Label className="text-xs uppercase tracking-widest text-[color:var(--institution-muted)]">
                                Estudiante
                            </Label>
                            <div className="flex gap-2">
                                <Popover open={estOpen} onOpenChange={setEstOpen}>
                                    <PopoverTrigger asChild>
                                        <Button
                                            variant="outline"
                                            role="combobox"
                                            className="rounded-sm justify-between flex-1 font-normal"
                                            data-testid="estudiante-select-btn"
                                        >
                                            <span className="truncate">
                                                {selectedEst
                                                    ? `${selectedEst.nombre} — CI: ${selectedEst.ci}`
                                                    : "Buscar estudiante…"}
                                            </span>
                                            <ChevronsUpDown size={14} className="ml-2 opacity-50" />
                                        </Button>
                                    </PopoverTrigger>
                                    <PopoverContent className="p-0 rounded-sm" align="start" style={{ width: "var(--radix-popover-trigger-width)" }}>
                                        <Command>
                                            <CommandInput placeholder="Nombre, CI, CU o código…" data-testid="estudiante-search-input" />
                                            <CommandList>
                                                <CommandEmpty>Sin resultados.</CommandEmpty>
                                                <CommandGroup>
                                                    {estudiantes.map((e) => (
                                                        <CommandItem
                                                            key={e.id}
                                                            value={`${e.nombre} ${e.ci} ${e.cu || ""} ${e.codigo}`}
                                                            onSelect={() => {
                                                                setSelectedEst(e);
                                                                setEstOpen(false);
                                                            }}
                                                            data-testid={`est-option-${e.id}`}
                                                        >
                                                            <Check
                                                                className={cn(
                                                                    "mr-2 h-4 w-4",
                                                                    selectedEst?.id === e.id ? "opacity-100" : "opacity-0",
                                                                )}
                                                            />
                                                            <div className="flex-1">
                                                                <div className="font-medium text-sm">{e.nombre}</div>
                                                                <div className="text-xs text-[color:var(--institution-muted)]">
                                                                    CU: {e.cu} · CI: {e.ci || "—"}
                                                                </div>
                                                            </div>
                                                        </CommandItem>
                                                    ))}
                                                </CommandGroup>
                                            </CommandList>
                                        </Command>
                                    </PopoverContent>
                                </Popover>
                                <Button
                                    type="button"
                                    variant="outline"
                                    className="rounded-sm"
                                    onClick={() => setNewEstOpen(true)}
                                    data-testid="add-new-estudiante-btn"
                                >
                                    <Plus size={14} className="mr-1" /> Nuevo
                                </Button>
                            </div>
                        </div>

                        <div className="space-y-1.5">
                            <Label className="text-xs uppercase tracking-widest text-[color:var(--institution-muted)]">
                                Tipo de Pago
                            </Label>
                            <Popover open={tpOpen} onOpenChange={setTpOpen}>
                                <PopoverTrigger asChild>
                                    <Button
                                        variant="outline"
                                        role="combobox"
                                        className="rounded-sm justify-between w-full font-normal"
                                        data-testid="tipopago-select-btn"
                                    >
                                        <span className="truncate">
                                            {selectedTipo ? selectedTipo.nombre : "Buscar tipo de pago…"}
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
                                                        value={`${t.nombre} ${t.codigo}`}
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
                        </div>

                        <Button
                            type="button"
                            onClick={generarComprobante}
                            disabled={!selectedEst || !selectedTipo}
                            className="rounded-sm w-full text-white h-11 uppercase text-xs tracking-widest"
                            style={{ backgroundColor: "var(--institution-navy)" }}
                            data-testid="generar-comprobante-btn"
                        >
                            <FileCheck2 size={16} className="mr-2" /> Generar comprobante
                        </Button>
                    </div>

                    {/* Right column - preview/data */}
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
                                {comprobante ? comprobante.display : "—"}
                            </div>
                        </div>

                        <div className="space-y-2 pt-2">
                            <Row label="Estudiante" value={selectedEst ? `${selectedEst.nombre}` : "—"} />
                            <Row label="C.I." value={selectedEst?.ci || "—"} />
                            <Row label="Tipo de pago" value={selectedTipo?.nombre || "—"} />
                            <Row label="Monto unitario (Bs.)" value={monto ? formatMoney(monto) : "—"} />
                        </div>

                        <div className="grid grid-cols-2 gap-3 pt-2">
                            <div className="space-y-1.5">
                                <Label className="text-xs uppercase tracking-widest text-[color:var(--institution-muted)]">Cantidad</Label>
                                <Input
                                    type="number"
                                    min="0"
                                    step="1"
                                    value={cantidad}
                                    onChange={(e) => setCantidad(e.target.value)}
                                    disabled={!comprobante}
                                    data-testid="cantidad-input"
                                    className="rounded-sm bg-white"
                                />
                            </div>
                            <div className="space-y-1.5">
                                <Label className="text-xs uppercase tracking-widest text-[color:var(--institution-muted)]">Fecha de pago</Label>
                                <Input
                                    type="date"
                                    value={fechaPago}
                                    onChange={(e) => setFechaPago(e.target.value)}
                                    disabled={!comprobante}
                                    data-testid="fecha-pago-input"
                                    className="rounded-sm bg-white"
                                />
                            </div>
                        </div>

                        <div className="border-t pt-3 flex items-center justify-between" style={{ borderColor: "var(--institution-border)" }}>
                            <span className="text-xs uppercase tracking-widest text-[color:var(--institution-muted)]">Total a pagar</span>
                            <span className="font-serif-display text-3xl font-bold font-mono-num" style={{ color: "var(--institution-burgundy)" }} data-testid="total-display">
                                Bs. {formatMoney(total)}
                            </span>
                        </div>

                        <Button
                            type="button"
                            onClick={confirmarComprobante}
                            disabled={!comprobante || submitting}
                            className="w-full rounded-sm text-white h-11 uppercase text-xs tracking-widest"
                            style={{ backgroundColor: "var(--institution-burgundy)" }}
                            data-testid="confirmar-comprobante-btn"
                        >
                            <Printer size={16} className="mr-2" /> Confirmar e imprimir
                        </Button>
                    </div>
                </CardContent>
            </Card>

            {/* New estudiante dialog */}
            <Dialog open={newEstOpen} onOpenChange={setNewEstOpen}>
                <DialogContent className="rounded-sm">
                    <DialogHeader>
                        <DialogTitle className="font-serif-display text-2xl">Nuevo estudiante</DialogTitle>
                    </DialogHeader>
                    <form onSubmit={onCreateNewEst} className="grid grid-cols-2 gap-4" data-testid="new-est-popup-form">
                        <div className="space-y-1.5">
                            <Label className="text-xs uppercase tracking-widest text-[color:var(--institution-muted)]">Código</Label>
                            <Input
                                value={newEst.codigo}
                                onChange={(e) => setNewEst({ ...newEst, codigo: e.target.value })}
                                required
                                className="rounded-sm"
                                data-testid="new-est-codigo"
                            />
                        </div>
                        <div className="space-y-1.5">
                            <Label className="text-xs uppercase tracking-widest text-[color:var(--institution-muted)]">Gestión</Label>
                            <Input
                                type="number"
                                value={newEst.gestion}
                                onChange={(e) => setNewEst({ ...newEst, gestion: e.target.value })}
                                required
                                className="rounded-sm"
                                data-testid="new-est-gestion"
                            />
                        </div>
                        <div className="space-y-1.5">
                            <Label className="text-xs uppercase tracking-widest text-[color:var(--institution-muted)]">C.I.</Label>
                            <Input
                                value={newEst.ci}
                                onChange={(e) => setNewEst({ ...newEst, ci: e.target.value })}
                                required
                                className="rounded-sm"
                                data-testid="new-est-ci"
                            />
                        </div>
                        <div className="space-y-1.5">
                            <Label className="text-xs uppercase tracking-widest text-[color:var(--institution-muted)]">C.U.</Label>
                            <Input
                                value={newEst.cu}
                                onChange={(e) => setNewEst({ ...newEst, cu: e.target.value })}
                                className="rounded-sm"
                                data-testid="new-est-cu"
                            />
                        </div>
                        <div className="space-y-1.5 col-span-2">
                            <Label className="text-xs uppercase tracking-widest text-[color:var(--institution-muted)]">Nombre completo</Label>
                            <Input
                                value={newEst.nombre}
                                onChange={(e) => setNewEst({ ...newEst, nombre: e.target.value })}
                                required
                                className="rounded-sm"
                                data-testid="new-est-nombre"
                            />
                        </div>
                        <DialogFooter className="col-span-2">
                            <Button
                                type="submit"
                                className="rounded-sm text-white"
                                style={{ backgroundColor: "var(--institution-burgundy)" }}
                                data-testid="new-est-save"
                            >
                                Registrar y seleccionar
                            </Button>
                        </DialogFooter>
                    </form>
                </DialogContent>
            </Dialog>
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
