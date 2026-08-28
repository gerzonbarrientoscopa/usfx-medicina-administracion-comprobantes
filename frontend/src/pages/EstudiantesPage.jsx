import React, { useEffect, useState } from "react";
import { apiClient, formatApiError } from "@/lib/api";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
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

const EMPTY = { codigo: "", ci: "", cu: "", nombre: "", gestion: new Date().getFullYear() };

export default function EstudiantesPage() {
    const [list, setList] = useState([]);
    const [q, setQ] = useState("");
    const [open, setOpen] = useState(false);
    const [editing, setEditing] = useState(null);
    const [form, setForm] = useState(EMPTY);
    const [loading, setLoading] = useState(false);

    const load = async () => {
        const { data } = await apiClient.get("/estudiantes", { params: q ? { q } : {} });
        setList(data);
    };

    useEffect(() => {
        load();
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [q]);

    const onOpenNew = () => {
        setEditing(null);
        setForm(EMPTY);
        setOpen(true);
    };

    const onEdit = (e) => {
        setEditing(e);
        setForm({ codigo: e.codigo, ci: e.ci, cu: e.cu || "", nombre: e.nombre, gestion: e.gestion });
        setOpen(true);
    };

    const onSubmit = async (ev) => {
        ev.preventDefault();
        setLoading(true);
        try {
            const payload = { ...form, gestion: Number(form.gestion) };
            if (editing) {
                await apiClient.put(`/estudiantes/${editing.id}`, payload);
                toast.success("Estudiante actualizado");
            } else {
                await apiClient.post("/estudiantes", payload);
                toast.success("Estudiante creado");
            }
            setOpen(false);
            load();
        } catch (e) {
            toast.error(formatApiError(e));
        } finally {
            setLoading(false);
        }
    };

    const onDelete = async (e) => {
        if (!window.confirm(`¿Eliminar a "${e.nombre}"?`)) return;
        try {
            await apiClient.delete(`/estudiantes/${e.id}`);
            toast.success("Estudiante eliminado");
            load();
        } catch (err) {
            toast.error(formatApiError(err));
        }
    };

    return (
        <div className="space-y-6" data-testid="estudiantes-page">
            <div className="flex items-end justify-between">
                <div>
                    <div className="section-eyebrow">Gestión académica</div>
                    <h1 className="font-serif-display text-4xl mt-1">Estudiantes</h1>
                    <p className="text-sm text-[color:var(--institution-muted)] mt-1">
                        Registro de estudiantes habilitados para realizar pagos.
                    </p>
                </div>
                <Dialog open={open} onOpenChange={setOpen}>
                    <DialogTrigger asChild>
                        <Button
                            onClick={onOpenNew}
                            data-testid="new-estudiante-btn"
                            className="rounded-sm text-white"
                            style={{ backgroundColor: "var(--institution-burgundy)" }}
                        >
                            <Plus size={16} className="mr-1" /> Nuevo estudiante
                        </Button>
                    </DialogTrigger>
                    <DialogContent className="rounded-sm">
                        <DialogHeader>
                            <DialogTitle className="font-serif-display text-2xl">
                                {editing ? "Editar estudiante" : "Nuevo estudiante"}
                            </DialogTitle>
                        </DialogHeader>
                        <form onSubmit={onSubmit} className="grid grid-cols-2 gap-4" data-testid="estudiante-form">
                            <div className="space-y-1.5">
                                <Label className="text-xs uppercase tracking-widest text-[color:var(--institution-muted)]">Código</Label>
                                <Input
                                    value={form.codigo}
                                    onChange={(e) => setForm({ ...form, codigo: e.target.value })}
                                    required
                                    data-testid="est-codigo-input"
                                    className="rounded-sm"
                                />
                            </div>
                            <div className="space-y-1.5">
                                <Label className="text-xs uppercase tracking-widest text-[color:var(--institution-muted)]">Gestión</Label>
                                <Input
                                    type="number"
                                    value={form.gestion}
                                    onChange={(e) => setForm({ ...form, gestion: e.target.value })}
                                    required
                                    data-testid="est-gestion-input"
                                    className="rounded-sm"
                                />
                            </div>
                            <div className="space-y-1.5">
                                <Label className="text-xs uppercase tracking-widest text-[color:var(--institution-muted)]">C.I.</Label>
                                <Input
                                    value={form.ci}
                                    onChange={(e) => setForm({ ...form, ci: e.target.value })}
                                    required
                                    data-testid="est-ci-input"
                                    className="rounded-sm"
                                />
                            </div>
                            <div className="space-y-1.5">
                                <Label className="text-xs uppercase tracking-widest text-[color:var(--institution-muted)]">C.U.</Label>
                                <Input
                                    value={form.cu}
                                    onChange={(e) => setForm({ ...form, cu: e.target.value })}
                                    data-testid="est-cu-input"
                                    className="rounded-sm"
                                />
                            </div>
                            <div className="space-y-1.5 col-span-2">
                                <Label className="text-xs uppercase tracking-widest text-[color:var(--institution-muted)]">Nombre completo</Label>
                                <Input
                                    value={form.nombre}
                                    onChange={(e) => setForm({ ...form, nombre: e.target.value })}
                                    required
                                    data-testid="est-nombre-input"
                                    className="rounded-sm"
                                />
                            </div>
                            <DialogFooter className="col-span-2">
                                <Button
                                    type="submit"
                                    disabled={loading}
                                    data-testid="est-save-btn"
                                    className="rounded-sm text-white"
                                    style={{ backgroundColor: "var(--institution-burgundy)" }}
                                >
                                    {editing ? "Guardar cambios" : "Crear estudiante"}
                                </Button>
                            </DialogFooter>
                        </form>
                    </DialogContent>
                </Dialog>
            </div>

            <div className="flex gap-3">
                <Input
                    placeholder="Buscar por nombre, CI, CU o código"
                    value={q}
                    onChange={(e) => setQ(e.target.value)}
                    className="max-w-md rounded-sm"
                    data-testid="estudiantes-search"
                />
            </div>

            <div className="bg-white border rounded-sm" style={{ borderColor: "var(--institution-border)" }}>
                <Table>
                    <TableHeader>
                        <TableRow style={{ backgroundColor: "var(--institution-cream)" }}>
                            <TableHead className="uppercase text-[10px] tracking-widest text-[color:var(--institution-muted)]">Código</TableHead>
                            <TableHead className="uppercase text-[10px] tracking-widest text-[color:var(--institution-muted)]">C.I.</TableHead>
                            <TableHead className="uppercase text-[10px] tracking-widest text-[color:var(--institution-muted)]">C.U.</TableHead>
                            <TableHead className="uppercase text-[10px] tracking-widest text-[color:var(--institution-muted)]">Nombre</TableHead>
                            <TableHead className="uppercase text-[10px] tracking-widest text-[color:var(--institution-muted)]">Gestión</TableHead>
                            <TableHead className="text-right uppercase text-[10px] tracking-widest text-[color:var(--institution-muted)]">Acciones</TableHead>
                        </TableRow>
                    </TableHeader>
                    <TableBody>
                        {list.map((e) => (
                            <TableRow key={e.id} data-testid={`est-row-${e.id}`}>
                                <TableCell className="font-mono-num">{e.codigo}</TableCell>
                                <TableCell className="font-mono-num">{e.ci}</TableCell>
                                <TableCell className="font-mono-num">{e.cu || "—"}</TableCell>
                                <TableCell className="font-medium">{e.nombre}</TableCell>
                                <TableCell className="font-mono-num">{e.gestion}</TableCell>
                                <TableCell className="text-right">
                                    <Button
                                        variant="ghost"
                                        size="sm"
                                        onClick={() => onEdit(e)}
                                        data-testid={`est-edit-${e.id}`}
                                        className="rounded-sm"
                                    >
                                        <Pencil size={14} />
                                    </Button>
                                    <Button
                                        variant="ghost"
                                        size="sm"
                                        onClick={() => onDelete(e)}
                                        data-testid={`est-delete-${e.id}`}
                                        className="rounded-sm text-[color:var(--institution-danger)]"
                                    >
                                        <Trash2 size={14} />
                                    </Button>
                                </TableCell>
                            </TableRow>
                        ))}
                        {list.length === 0 && (
                            <TableRow>
                                <TableCell colSpan={6} className="text-center py-12 text-sm text-[color:var(--institution-muted)]">
                                    Sin estudiantes registrados.
                                </TableCell>
                            </TableRow>
                        )}
                    </TableBody>
                </Table>
            </div>
        </div>
    );
}
