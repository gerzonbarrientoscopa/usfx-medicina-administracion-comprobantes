import React, { useEffect, useMemo, useRef, useState } from "react";
import { apiClient, formatApiError, formatMoney } from "@/lib/api";
import { useAuth } from "@/contexts/AuthContext";
import { useOfficeScope } from "@/hooks/useOfficeScope";
import { formatComprobante } from "@/lib/receipt";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
    Select,
    SelectTrigger,
    SelectValue,
    SelectContent,
    SelectItem,
} from "@/components/ui/select";
import {
    Table,
    TableBody,
    TableCell,
    TableHead,
    TableHeader,
    TableRow,
} from "@/components/ui/table";
import { Card, CardContent } from "@/components/ui/card";
import {
    Dialog,
    DialogContent,
    DialogHeader,
    DialogTitle,
    DialogFooter,
} from "@/components/ui/dialog";
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
import { Printer, Search, Pencil, ChevronsUpDown, Check, ChevronLeft, ChevronRight } from "lucide-react";
import { toast } from "sonner";
import { cn } from "@/lib/utils";
import { printComprobante } from "@/components/ComprobantePrint";

export default function BusquedaPagosPage() {
    const { user } = useAuth();
    const {
        isSuperAdmin, offices, officeId, selectedOfficeId, setSelectedOfficeId,
    } = useOfficeScope();
    const canEdit = isSuperAdmin || user?.rol === "Administrador" || user?.rol === "Caja";

    const [tipos, setTipos] = useState([]);
    const [users, setUsers] = useState([]);
    const [editTipos, setEditTipos] = useState([]);
    const [editEstudiantes, setEditEstudiantes] = useState([]);

    const [q, setQ] = useState("");
    const [tipo, setTipo] = useState("");
    const [desde, setDesde] = useState("");
    const [hasta, setHasta] = useState("");
    const [createdBy, setCreatedBy] = useState("");

    const [pagos, setPagos] = useState([]);
    const [loading, setLoading] = useState(false);
    const [pagina, setPagina] = useState(1);
    const [totalPaginas, setTotalPaginas] = useState(1);
    const [totalResultados, setTotalResultados] = useState(0);
    const FILAS_POR_PAGINA = 20;

    // Edit state
    const [editOpen, setEditOpen] = useState(false);
    const [editing, setEditing] = useState(null);
    const [editForm, setEditForm] = useState({ id_estudiante: "", id_tipo_pago: "", cantidad: "", fecha_pago: "" });
    const [editEstOpen, setEditEstOpen] = useState(false);
    const [editTpOpen, setEditTpOpen] = useState(false);
    const [savingEdit, setSavingEdit] = useState(false);
    const searchRequest = useRef(0);
    const catalogRequest = useRef(0);
    const editOptionsRequest = useRef(0);
    const officeIdRef = useRef(officeId);
    officeIdRef.current = officeId;

    useEffect(() => {
        const requestId = ++catalogRequest.current;
        const cargarTodasLasPaginas = async (endpoint, params) => {
            const primera = await apiClient.get(endpoint, { params: { ...params, pag: 1, tam: 100 } });
            const paginas = primera.data.pages || 1;
            if (paginas === 1) return primera.data.items;
            const restantes = await Promise.all(
                Array.from({ length: paginas - 1 }, (_, index) =>
                    apiClient.get(endpoint, { params: { ...params, pag: index + 2, tam: 100 } }),
                ),
            );
            return [
                ...primera.data.items,
                ...restantes.flatMap((response) => response.data.items),
            ];
        };
        const cargarCatalogos = async () => {
            try {
                const params = officeId ? { office_id: officeId } : {};
                const [tiposResponse, usuariosResponse] = await Promise.all([
                    cargarTodasLasPaginas("/tipos-pagos", params),
                    apiClient.get("/usuarios/list", { params }),
                ]);
                if (requestId !== catalogRequest.current || officeIdRef.current !== officeId) return;
                setTipos(tiposResponse);
                setUsers(usuariosResponse.data);
            } catch (error) {
                if (requestId === catalogRequest.current && officeIdRef.current === officeId) {
                    toast.error(formatApiError(error));
                }
            }
        };
        setTipos([]);
        setUsers([]);
        setPagos([]);
        setPagina(1);
        setTotalPaginas(1);
        setTotalResultados(0);
        setTipo("");
        setCreatedBy("");
        cargarCatalogos();
        buscar(1, true);
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [officeId]);

    const buscar = async (paginaSolicitada = 1, resetOfficeFilters = false) => {
        if (desde && hasta && desde > hasta) {
            toast.error("La fecha inicial no puede ser posterior a la fecha final.");
            return;
        }
        const requestId = ++searchRequest.current;
        const officeAtStart = officeId;
        setLoading(true);
        try {
            const params = {
                pag: paginaSolicitada,
                tam: FILAS_POR_PAGINA,
            };
            if (officeId) params.office_id = officeId;
            if (q.trim()) params.q = q.trim();
            if (!resetOfficeFilters && tipo && tipo !== "all") params.id_tipo_pago = tipo;
            if (desde) params.fecha_desde = desde;
            if (hasta) params.fecha_hasta = hasta;
            if (!resetOfficeFilters && createdBy && createdBy !== "all") params.created_by = createdBy;
            const { data } = await apiClient.get("/pagos", { params });
            if (requestId !== searchRequest.current || officeIdRef.current !== officeAtStart) return null;
            setPagos(data.items);
            setPagina(data.page);
            setTotalPaginas(data.pages || 1);
            setTotalResultados(data.total);
            return data;
        } catch (e) {
            if (requestId === searchRequest.current && officeIdRef.current === officeAtStart) {
                toast.error(formatApiError(e));
            }
            return null;
        } finally {
            if (requestId === searchRequest.current) setLoading(false);
        }
    };

    const cargarOpcionesEdicion = async (p, requestId) => {
        const paymentOfficeId = p.office_id;
        const paymentStudent = {
            id: p.id_estudiante,
            nombre: p.estudiante_nombre,
            ci: p.estudiante_ci,
            cu: p.estudiante_cu,
        };
        const paymentTipo = {
            id: p.id_tipo_pago,
            nombre: p.tipo_pago_nombre,
            monto: p.monto,
            codigo: p.tipo_pago_codigo || "",
        };
        setEditEstudiantes([paymentStudent]);
        setEditTipos([paymentTipo]);
        if (!paymentOfficeId) return;
        const params = { office_id: paymentOfficeId };
        try {
            const cargarTodasLasPaginas = async (endpoint) => {
                const primera = await apiClient.get(endpoint, { params: { ...params, pag: 1, tam: 100 } });
                const paginas = primera.data.pages || 1;
                if (paginas === 1) return primera.data.items;
                const restantes = await Promise.all(
                    Array.from({ length: paginas - 1 }, (_, index) =>
                        apiClient.get(endpoint, { params: { ...params, pag: index + 2, tam: 100 } }),
                    ),
                );
                return [
                    ...primera.data.items,
                    ...restantes.flatMap((response) => response.data.items),
                ];
            };
            const [students, types] = await Promise.all([
                cargarTodasLasPaginas("/estudiantes"),
                cargarTodasLasPaginas("/tipos-pagos"),
            ]);
            if (requestId !== editOptionsRequest.current) return;
            setEditEstudiantes(students.some((student) => student.id === p.id_estudiante)
                ? students
                : [...students, paymentStudent]);
            setEditTipos(types.some((paymentType) => paymentType.id === p.id_tipo_pago)
                ? types
                : [...types, paymentTipo]);
        } catch (error) {
            if (requestId === editOptionsRequest.current) toast.error(formatApiError(error));
        }
    };

    const openEdit = (p) => {
        setEditing(p);
        setEditForm({
            id_estudiante: p.id_estudiante,
            id_tipo_pago: p.id_tipo_pago,
            cantidad: String(p.cantidad),
            fecha_pago: p.fecha_pago,
        });
        const requestId = ++editOptionsRequest.current;
        setEditOpen(true);
        cargarOpcionesEdicion(p, requestId);
    };

    const selectedEditEst = useMemo(
        () => editEstudiantes.find((e) => e.id === editForm.id_estudiante) || null,
        [editEstudiantes, editForm.id_estudiante],
    );
    const selectedEditTipo = useMemo(
        () => editTipos.find((t) => t.id === editForm.id_tipo_pago) || null,
        [editTipos, editForm.id_tipo_pago],
    );
    const editTotal = useMemo(() => {
        const m = selectedEditTipo ? Number(selectedEditTipo.monto) : 0;
        const c = Number(editForm.cantidad);
        if (isNaN(c) || c <= 0) return 0;
        return m * c;
    }, [selectedEditTipo, editForm.cantidad]);

    const submitEdit = async () => {
        if (!editing) return;
        setSavingEdit(true);
        try {
            const payload = {
                id_estudiante: editForm.id_estudiante,
                id_tipo_pago: editForm.id_tipo_pago,
                cantidad: Number(editForm.cantidad),
                fecha_pago: editForm.fecha_pago,
            };
            const { data } = await apiClient.put(`/pagos/${editing.id}`, payload);
            toast.success(`Pago ${formatComprobante(data)} actualizado`);
            setEditOpen(false);
            const resultado = await buscar(pagina);
            if (resultado?.items.length === 0 && pagina > 1) {
                await buscar(pagina - 1);
            }
        } catch (e) {
            toast.error(formatApiError(e));
        } finally {
            setSavingEdit(false);
        }
    };

    return (
        <div className="space-y-6" data-testid="busqueda-page">
            <div>
                <div className="section-eyebrow">Consultas</div>
                <h1 className="font-serif-display text-4xl mt-1">Búsqueda de Pagos</h1>
                <p className="text-sm text-[color:var(--institution-muted)] mt-1">
                    Busque por código (ej. MED-00001 / 2026), nombre de estudiante, tipo de pago, rango de fechas o usuario que registró.
                </p>
            </div>

            <Card className="rounded-sm border-[color:var(--institution-border)] shadow-none">
                <CardContent className="p-6 grid grid-cols-1 md:grid-cols-6 gap-4">
                    {isSuperAdmin && (
                        <div className="space-y-1.5 md:col-span-2">
                            <Label className="text-xs uppercase tracking-widest text-[color:var(--institution-muted)]">Oficina</Label>
                            <Select
                                value={selectedOfficeId || "all"}
                                onValueChange={(value) => setSelectedOfficeId(value === "all" ? "" : value)}
                            >
                                <SelectTrigger className="rounded-sm" data-testid="busq-office-select">
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
                    <div className="space-y-1.5 md:col-span-2">
                        <Label className="text-xs uppercase tracking-widest text-[color:var(--institution-muted)]">Búsqueda</Label>
                        <Input
                            placeholder="Código, estudiante, tipo…"
                            value={q}
                            onChange={(e) => setQ(e.target.value)}
                            className="rounded-sm"
                            data-testid="busq-q-input"
                        />
                    </div>
                    <div className="space-y-1.5">
                        <Label className="text-xs uppercase tracking-widest text-[color:var(--institution-muted)]">Tipo de pago</Label>
                        <Select value={tipo} onValueChange={setTipo}>
                            <SelectTrigger className="rounded-sm" data-testid="busq-tipo-select">
                                <SelectValue placeholder="Todos" />
                            </SelectTrigger>
                            <SelectContent>
                                <SelectItem value="all">Todos</SelectItem>
                                {tipos.map((t) => (
                                    <SelectItem key={t.id} value={t.id}>
                                        {t.nombre}
                                    </SelectItem>
                                ))}
                            </SelectContent>
                        </Select>
                    </div>
                    <div className="space-y-1.5">
                        <Label className="text-xs uppercase tracking-widest text-[color:var(--institution-muted)]">Registrado por</Label>
                        <Select value={createdBy} onValueChange={setCreatedBy}>
                            <SelectTrigger className="rounded-sm" data-testid="busq-user-select">
                                <SelectValue placeholder="Todos" />
                            </SelectTrigger>
                            <SelectContent>
                                <SelectItem value="all">Todos</SelectItem>
                                {users.map((u) => (
                                    <SelectItem key={u.id} value={u.id} data-testid={`busq-user-opt-${u.id}`}>
                                        {u.nombre} <span className="text-xs text-[color:var(--institution-muted)] ml-1">· {u.rol}</span>
                                    </SelectItem>
                                ))}
                            </SelectContent>
                        </Select>
                    </div>
                    <div className="space-y-1.5">
                        <Label className="text-xs uppercase tracking-widest text-[color:var(--institution-muted)]">Desde</Label>
                        <Input
                            type="date"
                            value={desde}
                            onChange={(e) => setDesde(e.target.value)}
                            className="rounded-sm"
                            data-testid="busq-desde-input"
                        />
                    </div>
                    <div className="space-y-1.5">
                        <Label className="text-xs uppercase tracking-widest text-[color:var(--institution-muted)]">Hasta</Label>
                        <Input
                            type="date"
                            value={hasta}
                            onChange={(e) => setHasta(e.target.value)}
                            className="rounded-sm"
                            data-testid="busq-hasta-input"
                        />
                    </div>
                    <div className="md:col-span-6 flex justify-end">
                        <Button
                            onClick={() => buscar(1)}
                            disabled={loading}
                            className="rounded-sm text-white"
                            style={{ backgroundColor: "var(--institution-burgundy)" }}
                            data-testid="busq-buscar-btn"
                        >
                            <Search size={14} className="mr-2" /> Buscar
                        </Button>
                    </div>
                </CardContent>
            </Card>

            <div className="bg-white border rounded-sm overflow-x-auto" style={{ borderColor: "var(--institution-border)" }}>
                <Table>
                    <TableHeader>
                        <TableRow style={{ backgroundColor: "var(--institution-cream)" }}>
                            <TableHead className="uppercase text-[10px] tracking-widest text-[color:var(--institution-muted)]">Código</TableHead>
                            {isSuperAdmin && <TableHead className="uppercase text-[10px] tracking-widest text-[color:var(--institution-muted)]">Oficina</TableHead>}
                            <TableHead className="uppercase text-[10px] tracking-widest text-[color:var(--institution-muted)]">Estudiante</TableHead>
                            <TableHead className="uppercase text-[10px] tracking-widest text-[color:var(--institution-muted)]">Tipo de pago</TableHead>
                            <TableHead className="text-right uppercase text-[10px] tracking-widest text-[color:var(--institution-muted)]">Cantidad</TableHead>
                            <TableHead className="text-right uppercase text-[10px] tracking-widest text-[color:var(--institution-muted)]">Monto</TableHead>
                            <TableHead className="text-right uppercase text-[10px] tracking-widest text-[color:var(--institution-muted)]">Total</TableHead>
                            <TableHead className="uppercase text-[10px] tracking-widest text-[color:var(--institution-muted)]">Fecha</TableHead>
                            <TableHead className="uppercase text-[10px] tracking-widest text-[color:var(--institution-muted)]">Registrado por</TableHead>
                            <TableHead className="uppercase text-[10px] tracking-widest text-[color:var(--institution-muted)]">Estado</TableHead>
                            <TableHead className="text-right uppercase text-[10px] tracking-widest text-[color:var(--institution-muted)]">Acciones</TableHead>
                        </TableRow>
                    </TableHeader>
                    <TableBody>
                        {pagos.map((p) => (
                            <TableRow key={p.id} data-testid={`pago-row-${p.id}`}>
                                <TableCell className="font-mono-num font-medium">
                                    {formatComprobante(p)}
                                </TableCell>
                                {isSuperAdmin && <TableCell>{p.office_nombre || "—"}</TableCell>}
                                <TableCell>{p.estudiante_nombre || "—"}</TableCell>
                                <TableCell>{p.tipo_pago_nombre || "—"}</TableCell>
                                <TableCell className="text-right font-mono-num">{p.cantidad}</TableCell>
                                <TableCell className="text-right font-mono-num">{formatMoney(p.monto)}</TableCell>
                                <TableCell className="text-right font-mono-num font-semibold">{formatMoney(p.total)}</TableCell>
                                <TableCell className="font-mono-num">{p.fecha_pago}</TableCell>
                                <TableCell className="text-xs text-[color:var(--institution-muted)]">
                                    {p.created_by_name || "—"}
                                    {p.edited_by_name && (
                                        <div className="text-[10px] italic">editado por {p.edited_by_name}</div>
                                    )}
                                </TableCell>
                                <TableCell>
                                    {p.anulado ? (
                                        <span className="pill pill-void" data-testid={`pago-status-${p.id}`}>Anulado</span>
                                    ) : (
                                        <span className="pill pill-valid" data-testid={`pago-status-${p.id}`}>Válido</span>
                                    )}
                                </TableCell>
                                <TableCell className="text-right whitespace-nowrap">
                                    {canEdit && !p.anulado && (
                                        <Button
                                            size="sm"
                                            variant="ghost"
                                            onClick={() => openEdit(p)}
                                            className="rounded-sm mr-1"
                                            data-testid={`edit-pago-btn-${p.id}`}
                                        >
                                            <Pencil size={12} />
                                        </Button>
                                    )}
                                    <Button
                                        size="sm"
                                        variant="outline"
                                        onClick={() => printComprobante(p)}
                                        className="rounded-sm"
                                        data-testid={`reimprimir-btn-${p.id}`}
                                    >
                                        <Printer size={12} className="mr-1" /> Reimprimir
                                    </Button>
                                </TableCell>
                            </TableRow>
                        ))}
                        {!loading && pagos.length === 0 && (
                            <TableRow>
                                <TableCell colSpan={isSuperAdmin ? 11 : 10} className="text-center py-12 text-sm text-[color:var(--institution-muted)]">
                                    Sin resultados.
                                </TableCell>
                            </TableRow>
                        )}
                        {loading && (
                            <TableRow>
                                <TableCell colSpan={isSuperAdmin ? 11 : 10} className="text-center py-12 text-sm text-[color:var(--institution-muted)]">
                                    Buscando…
                                </TableCell>
                            </TableRow>
                        )}
                    </TableBody>
                </Table>
            </div>
            <div className="flex items-center justify-between px-2 text-xs text-[color:var(--institution-muted)]">
                <div>
                    Página <b>{pagina}</b> de <b>{totalPaginas}</b> · {totalResultados} resultado{totalResultados === 1 ? "" : "s"}
                </div>
                <div className="flex items-center gap-2">
                    <Button
                        variant="outline"
                        size="sm"
                        className="rounded-sm gap-1 h-8 px-3"
                        style={{ borderColor: "var(--institution-border)" }}
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
                        style={{ borderColor: "var(--institution-border)" }}
                        onClick={() => buscar(Math.min(pagina + 1, totalPaginas))}
                        disabled={loading || pagina === totalPaginas}
                    >
                        Siguiente
                        <ChevronRight size={14} />
                    </Button>
                </div>
            </div>

            {/* Edit dialog */}
            <Dialog open={editOpen} onOpenChange={setEditOpen}>
                <DialogContent className="rounded-sm max-w-2xl">
                    <DialogHeader>
                        <DialogTitle className="font-serif-display text-2xl">
                            Editar pago {editing ? formatComprobante(editing) : ""}
                        </DialogTitle>
                    </DialogHeader>
                    {editing && (
                        <div className="grid grid-cols-2 gap-4">
                            <div className="space-y-1.5 col-span-2">
                                <Label className="text-xs uppercase tracking-widest text-[color:var(--institution-muted)]">Estudiante</Label>
                                <Popover open={editEstOpen} onOpenChange={setEditEstOpen}>
                                    <PopoverTrigger asChild>
                                        <Button
                                            variant="outline"
                                            role="combobox"
                                            className="rounded-sm justify-between w-full font-normal"
                                            data-testid="edit-est-select-btn"
                                        >
                                            <span className="truncate">
                                                {selectedEditEst ? `${selectedEditEst.nombre} — CI: ${selectedEditEst.ci}` : "Seleccionar…"}
                                            </span>
                                            <ChevronsUpDown size={14} className="ml-2 opacity-50" />
                                        </Button>
                                    </PopoverTrigger>
                                    <PopoverContent className="p-0 rounded-sm" align="start" style={{ width: "var(--radix-popover-trigger-width)" }}>
                                        <Command>
                                            <CommandInput placeholder="Buscar estudiante…" />
                                            <CommandList>
                                                <CommandEmpty>Sin resultados.</CommandEmpty>
                                                <CommandGroup>
                                                     {editEstudiantes.map((e) => (
                                                        <CommandItem
                                                            key={e.id}
                                                            value={`${e.nombre} ${e.ci} ${e.cu || ""} ${e.codigo}`}
                                                            onSelect={() => {
                                                                setEditForm({ ...editForm, id_estudiante: e.id });
                                                                setEditEstOpen(false);
                                                            }}
                                                        >
                                                            <Check className={cn("mr-2 h-4 w-4", editForm.id_estudiante === e.id ? "opacity-100" : "opacity-0")} />
                                                            <div className="flex-1">
                                                                <div className="font-medium text-sm">{e.nombre}</div>
                                                                <div className="text-xs text-[color:var(--institution-muted)]">CI: {e.ci}</div>
                                                            </div>
                                                        </CommandItem>
                                                    ))}
                                                </CommandGroup>
                                            </CommandList>
                                        </Command>
                                    </PopoverContent>
                                </Popover>
                            </div>

                            <div className="space-y-1.5 col-span-2">
                                <Label className="text-xs uppercase tracking-widest text-[color:var(--institution-muted)]">Tipo de pago</Label>
                                <Popover open={editTpOpen} onOpenChange={setEditTpOpen}>
                                    <PopoverTrigger asChild>
                                        <Button
                                            variant="outline"
                                            role="combobox"
                                            className="rounded-sm justify-between w-full font-normal"
                                            data-testid="edit-tp-select-btn"
                                        >
                                            <span className="truncate">
                                                {selectedEditTipo ? `${selectedEditTipo.nombre} — Bs. ${formatMoney(selectedEditTipo.monto)}` : "Seleccionar…"}
                                            </span>
                                            <ChevronsUpDown size={14} className="ml-2 opacity-50" />
                                        </Button>
                                    </PopoverTrigger>
                                    <PopoverContent className="p-0 rounded-sm" align="start" style={{ width: "var(--radix-popover-trigger-width)" }}>
                                        <Command>
                                            <CommandInput placeholder="Buscar tipo…" />
                                            <CommandList>
                                                <CommandEmpty>Sin resultados.</CommandEmpty>
                                                <CommandGroup>
                                                     {editTipos.map((t) => (
                                                        <CommandItem
                                                            key={t.id}
                                                            value={`${t.nombre} ${t.codigo}`}
                                                            onSelect={() => {
                                                                setEditForm({ ...editForm, id_tipo_pago: t.id });
                                                                setEditTpOpen(false);
                                                            }}
                                                        >
                                                            <Check className={cn("mr-2 h-4 w-4", editForm.id_tipo_pago === t.id ? "opacity-100" : "opacity-0")} />
                                                            <div className="flex-1">
                                                                <div className="font-medium text-sm">{t.nombre}</div>
                                                                <div className="text-xs text-[color:var(--institution-muted)]">Bs. {formatMoney(t.monto)}</div>
                                                            </div>
                                                        </CommandItem>
                                                    ))}
                                                </CommandGroup>
                                            </CommandList>
                                        </Command>
                                    </PopoverContent>
                                </Popover>
                            </div>

                            <div className="space-y-1.5">
                                <Label className="text-xs uppercase tracking-widest text-[color:var(--institution-muted)]">Cantidad</Label>
                                <Input
                                    type="number"
                                    min="0"
                                    value={editForm.cantidad}
                                    onChange={(e) => setEditForm({ ...editForm, cantidad: e.target.value })}
                                    className="rounded-sm"
                                    data-testid="edit-cantidad-input"
                                />
                            </div>
                            <div className="space-y-1.5">
                                <Label className="text-xs uppercase tracking-widest text-[color:var(--institution-muted)]">Fecha de pago</Label>
                                <Input
                                    type="date"
                                    value={editForm.fecha_pago}
                                    onChange={(e) => setEditForm({ ...editForm, fecha_pago: e.target.value })}
                                    className="rounded-sm"
                                    data-testid="edit-fecha-input"
                                />
                            </div>

                            <div className="col-span-2 border-t pt-3 flex items-center justify-between" style={{ borderColor: "var(--institution-border)" }}>
                                <span className="text-xs uppercase tracking-widest text-[color:var(--institution-muted)]">Nuevo total</span>
                                <span className="font-serif-display text-2xl font-mono-num font-bold" style={{ color: "var(--institution-burgundy)" }}>
                                    Bs. {formatMoney(editTotal)}
                                </span>
                            </div>
                        </div>
                    )}
                    <DialogFooter>
                        <Button variant="outline" onClick={() => setEditOpen(false)} className="rounded-sm">
                            Cancelar
                        </Button>
                        <Button
                            onClick={submitEdit}
                            disabled={savingEdit}
                            className="rounded-sm text-white"
                            style={{ backgroundColor: "var(--institution-burgundy)" }}
                            data-testid="edit-save-btn"
                        >
                            Guardar cambios
                        </Button>
                    </DialogFooter>
                </DialogContent>
            </Dialog>
        </div>
    );
}
