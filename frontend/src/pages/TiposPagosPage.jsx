import React, { useEffect, useState } from "react";
import { apiClient, formatApiError, formatMoney } from "@/lib/api";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
    Dialog,
    DialogContent,
    DialogHeader,
    DialogTitle,
    DialogTrigger,
    DialogFooter,
} from "@/components/ui/dialog";
import {
    Table,
    TableBody,
    TableCell,
    TableHead,
    TableHeader,
    TableRow,
} from "@/components/ui/table";
import { Plus, Pencil, Trash2 } from "lucide-react";

const EMPTY = { codigo: "", nombre: "", monto: "", descripcion: "", inicio: "", fin: "" };

export default function TiposPagosPage() {
    const [list, setList] = useState([]);
    const [open, setOpen] = useState(false);
    const [editing, setEditing] = useState(null);
    const [form, setForm] = useState(EMPTY);
    const [loading, setLoading] = useState(false);

    const load = async () => {
        const { data } = await apiClient.get("/tipospagos");
        setList(data);
    };

    useEffect(() => {
        load();
    }, []);

    const onOpenNew = () => {
        setEditing(null);
        setForm(EMPTY);
        setOpen(true);
    };

    const onEdit = (t) => {
        setEditing(t);
        setForm({
            codigo: t.codigo,
            nombre: t.nombre,
            monto: t.monto,
            descripcion: t.descripcion || "",
            inicio: t.inicio,
            fin: t.fin || "",
        });
        setOpen(true);
    };

    const onSubmit = async (e) => {
        e.preventDefault();
        setLoading(true);
        try {
            const payload = {
                ...form,
                monto: Number(form.monto),
                fin: form.fin || null,
            };
            if (editing) {
                await apiClient.put(`/tipospagos/${editing.id}`, payload);
                toast.success("Tipo de pago actualizado");
            } else {
                await apiClient.post("/tipospagos", payload);
                toast.success("Tipo de pago creado");
            }
            setOpen(false);
            load();
        } catch (err) {
            toast.error(formatApiError(err));
        } finally {
            setLoading(false);
        }
    };

    const onDelete = async (t) => {
        if (!window.confirm(`¿Eliminar "${t.nombre}"?`)) return;
        try {
            await apiClient.delete(`/tipospagos/${t.id}`);
            toast.success("Tipo de pago eliminado");
            load();
        } catch (err) {
            toast.error(formatApiError(err));
        }
    };

    return (
        <div className="space-y-6" data-testid="tipospagos-page">
            <div className="flex items-end justify-between">
                <div>
                    <div className="section-eyebrow">Catálogo</div>
                    <h1 className="font-serif-display text-4xl mt-1">Tipos de Pago</h1>
                    <p className="text-sm text-[color:var(--institution-muted)] mt-1">
                        Conceptos por los cuales se pueden emitir comprobantes.
                    </p>
                </div>
                <Dialog open={open} onOpenChange={setOpen}>
                    <DialogTrigger asChild>
                        <Button
                            onClick={onOpenNew}
                            data-testid="new-tipopago-btn"
                            className="rounded-sm text-white"
                            style={{ backgroundColor: "var(--institution-burgundy)" }}
                        >
                            <Plus size={16} className="mr-1" /> Nuevo tipo de pago
                        </Button>
                    </DialogTrigger>
                    <DialogContent className="rounded-sm">
                        <DialogHeader>
                            <DialogTitle className="font-serif-display text-2xl">
                                {editing ? "Editar tipo de pago" : "Nuevo tipo de pago"}
                            </DialogTitle>
                        </DialogHeader>
                        <form onSubmit={onSubmit} className="grid grid-cols-2 gap-4">
                            <div className="space-y-1.5">
                                <Label className="text-xs uppercase tracking-widest text-[color:var(--institution-muted)]">Código</Label>
                                <Input
                                    value={form.codigo}
                                    onChange={(e) => setForm({ ...form, codigo: e.target.value })}
                                    required
                                    data-testid="tp-codigo-input"
                                    className="rounded-sm"
                                />
                            </div>
                            <div className="space-y-1.5">
                                <Label className="text-xs uppercase tracking-widest text-[color:var(--institution-muted)]">Monto (Bs.)</Label>
                                <Input
                                    type="number"
                                    step="0.01"
                                    value={form.monto}
                                    onChange={(e) => setForm({ ...form, monto: e.target.value })}
                                    required
                                    data-testid="tp-monto-input"
                                    className="rounded-sm"
                                />
                            </div>
                            <div className="space-y-1.5 col-span-2">
                                <Label className="text-xs uppercase tracking-widest text-[color:var(--institution-muted)]">Nombre</Label>
                                <Input
                                    value={form.nombre}
                                    onChange={(e) => setForm({ ...form, nombre: e.target.value })}
                                    required
                                    data-testid="tp-nombre-input"
                                    className="rounded-sm"
                                />
                            </div>
                            <div className="space-y-1.5 col-span-2">
                                <Label className="text-xs uppercase tracking-widest text-[color:var(--institution-muted)]">Descripción</Label>
                                <Textarea
                                    value={form.descripcion}
                                    onChange={(e) => setForm({ ...form, descripcion: e.target.value })}
                                    rows={2}
                                    data-testid="tp-desc-input"
                                    className="rounded-sm"
                                />
                            </div>
                            <div className="space-y-1.5">
                                <Label className="text-xs uppercase tracking-widest text-[color:var(--institution-muted)]">Inicio</Label>
                                <Input
                                    type="date"
                                    value={form.inicio}
                                    onChange={(e) => setForm({ ...form, inicio: e.target.value })}
                                    required
                                    data-testid="tp-inicio-input"
                                    className="rounded-sm"
                                />
                            </div>
                            <div className="space-y-1.5">
                                <Label className="text-xs uppercase tracking-widest text-[color:var(--institution-muted)]">Fin (opcional)</Label>
                                <Input
                                    type="date"
                                    value={form.fin}
                                    onChange={(e) => setForm({ ...form, fin: e.target.value })}
                                    data-testid="tp-fin-input"
                                    className="rounded-sm"
                                />
                            </div>
                            <DialogFooter className="col-span-2">
                                <Button
                                    type="submit"
                                    disabled={loading}
                                    data-testid="tp-save-btn"
                                    className="rounded-sm text-white"
                                    style={{ backgroundColor: "var(--institution-burgundy)" }}
                                >
                                    {editing ? "Guardar cambios" : "Crear"}
                                </Button>
                            </DialogFooter>
                        </form>
                    </DialogContent>
                </Dialog>
            </div>

            <div className="bg-white border rounded-sm" style={{ borderColor: "var(--institution-border)" }}>
                <Table>
                    <TableHeader>
                        <TableRow style={{ backgroundColor: "var(--institution-cream)" }}>
                            <TableHead className="uppercase text-[10px] tracking-widest text-[color:var(--institution-muted)]">Código</TableHead>
                            <TableHead className="uppercase text-[10px] tracking-widest text-[color:var(--institution-muted)]">Nombre</TableHead>
                            <TableHead className="text-right uppercase text-[10px] tracking-widest text-[color:var(--institution-muted)]">Monto (Bs.)</TableHead>
                            <TableHead className="uppercase text-[10px] tracking-widest text-[color:var(--institution-muted)]">Vigencia</TableHead>
                            <TableHead className="uppercase text-[10px] tracking-widest text-[color:var(--institution-muted)]">Descripción</TableHead>
                            <TableHead className="text-right uppercase text-[10px] tracking-widest text-[color:var(--institution-muted)]">Acciones</TableHead>
                        </TableRow>
                    </TableHeader>
                    <TableBody>
                        {list.map((t) => (
                            <TableRow key={t.id} data-testid={`tp-row-${t.id}`}>
                                <TableCell className="font-mono-num">{t.codigo}</TableCell>
                                <TableCell className="font-medium">{t.nombre}</TableCell>
                                <TableCell className="text-right font-mono-num">{formatMoney(t.monto)}</TableCell>
                                <TableCell className="text-xs">
                                    {t.inicio} → {t.fin || "—"}
                                </TableCell>
                                <TableCell className="text-xs text-[color:var(--institution-muted)] max-w-xs truncate">
                                    {t.descripcion || "—"}
                                </TableCell>
                                <TableCell className="text-right">
                                    <Button variant="ghost" size="sm" onClick={() => onEdit(t)} data-testid={`tp-edit-${t.id}`} className="rounded-sm">
                                        <Pencil size={14} />
                                    </Button>
                                    <Button variant="ghost" size="sm" onClick={() => onDelete(t)} data-testid={`tp-delete-${t.id}`} className="rounded-sm text-[color:var(--institution-danger)]">
                                        <Trash2 size={14} />
                                    </Button>
                                </TableCell>
                            </TableRow>
                        ))}
                        {list.length === 0 && (
                            <TableRow>
                                <TableCell colSpan={6} className="text-center py-12 text-sm text-[color:var(--institution-muted)]">
                                    Sin tipos de pago registrados.
                                </TableCell>
                            </TableRow>
                        )}
                    </TableBody>
                </Table>
            </div>
        </div>
    );
}
