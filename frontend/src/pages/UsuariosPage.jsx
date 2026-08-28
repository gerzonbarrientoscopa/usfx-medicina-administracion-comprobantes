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
import { Plus, Pencil, Trash2 } from "lucide-react";

const EMPTY = { email: "", name: "", password: "", role: "caja" };
const ROLE_LABEL = { admin: "Administrador", caja: "Caja", consultas: "Consultas" };

export default function UsuariosPage() {
    const [list, setList] = useState([]);
    const [open, setOpen] = useState(false);
    const [editing, setEditing] = useState(null);
    const [form, setForm] = useState(EMPTY);

    const load = async () => {
        const { data } = await apiClient.get("/users");
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
    const onEdit = (u) => {
        setEditing(u);
        setForm({ email: u.email, name: u.name, password: "", role: u.role });
        setOpen(true);
    };

    const onSubmit = async (e) => {
        e.preventDefault();
        try {
            if (editing) {
                const payload = { name: form.name, role: form.role };
                if (form.password) payload.password = form.password;
                await apiClient.put(`/users/${editing.id}`, payload);
                toast.success("Usuario actualizado");
            } else {
                await apiClient.post("/users", form);
                toast.success("Usuario creado");
            }
            setOpen(false);
            load();
        } catch (err) {
            toast.error(formatApiError(err));
        }
    };

    const onDelete = async (u) => {
        if (!window.confirm(`¿Eliminar a "${u.name}"?`)) return;
        try {
            await apiClient.delete(`/users/${u.id}`);
            toast.success("Usuario eliminado");
            load();
        } catch (err) {
            toast.error(formatApiError(err));
        }
    };

    return (
        <div className="space-y-6" data-testid="usuarios-page">
            <div className="flex items-end justify-between">
                <div>
                    <div className="section-eyebrow">Acceso al sistema</div>
                    <h1 className="font-serif-display text-4xl mt-1">Usuarios</h1>
                    <p className="text-sm text-[color:var(--institution-muted)] mt-1">
                        Usuarios habilitados para iniciar sesión en el sistema.
                    </p>
                </div>
                <Dialog open={open} onOpenChange={setOpen}>
                    <DialogTrigger asChild>
                        <Button
                            onClick={onOpenNew}
                            data-testid="new-user-btn"
                            className="rounded-sm text-white"
                            style={{ backgroundColor: "var(--institution-burgundy)" }}
                        >
                            <Plus size={16} className="mr-1" /> Nuevo usuario
                        </Button>
                    </DialogTrigger>
                    <DialogContent className="rounded-sm">
                        <DialogHeader>
                            <DialogTitle className="font-serif-display text-2xl">
                                {editing ? "Editar usuario" : "Nuevo usuario"}
                            </DialogTitle>
                        </DialogHeader>
                        <form onSubmit={onSubmit} className="space-y-4">
                            <div className="space-y-1.5">
                                <Label className="text-xs uppercase tracking-widest text-[color:var(--institution-muted)]">Nombre completo</Label>
                                <Input
                                    value={form.name}
                                    onChange={(e) => setForm({ ...form, name: e.target.value })}
                                    required
                                    data-testid="user-name-input"
                                    className="rounded-sm"
                                />
                            </div>
                            <div className="space-y-1.5">
                                <Label className="text-xs uppercase tracking-widest text-[color:var(--institution-muted)]">Email</Label>
                                <Input
                                    type="email"
                                    value={form.email}
                                    onChange={(e) => setForm({ ...form, email: e.target.value })}
                                    required
                                    disabled={!!editing}
                                    data-testid="user-email-input"
                                    className="rounded-sm"
                                />
                            </div>
                            <div className="space-y-1.5">
                                <Label className="text-xs uppercase tracking-widest text-[color:var(--institution-muted)]">
                                    {editing ? "Nueva contraseña (opcional)" : "Contraseña"}
                                </Label>
                                <Input
                                    type="password"
                                    value={form.password}
                                    onChange={(e) => setForm({ ...form, password: e.target.value })}
                                    required={!editing}
                                    data-testid="user-password-input"
                                    className="rounded-sm"
                                />
                            </div>
                            <div className="space-y-1.5">
                                <Label className="text-xs uppercase tracking-widest text-[color:var(--institution-muted)]">Rol</Label>
                                <Select value={form.role} onValueChange={(v) => setForm({ ...form, role: v })}>
                                    <SelectTrigger className="rounded-sm" data-testid="user-role-select">
                                        <SelectValue />
                                    </SelectTrigger>
                                    <SelectContent>
                                        <SelectItem value="admin">Administrador</SelectItem>
                                        <SelectItem value="caja">Caja</SelectItem>
                                        <SelectItem value="consultas">Consultas</SelectItem>
                                    </SelectContent>
                                </Select>
                            </div>
                            <DialogFooter>
                                <Button
                                    type="submit"
                                    data-testid="user-save-btn"
                                    className="rounded-sm text-white"
                                    style={{ backgroundColor: "var(--institution-burgundy)" }}
                                >
                                    {editing ? "Guardar cambios" : "Crear usuario"}
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
                            <TableHead className="uppercase text-[10px] tracking-widest text-[color:var(--institution-muted)]">Nombre</TableHead>
                            <TableHead className="uppercase text-[10px] tracking-widest text-[color:var(--institution-muted)]">Email</TableHead>
                            <TableHead className="uppercase text-[10px] tracking-widest text-[color:var(--institution-muted)]">Rol</TableHead>
                            <TableHead className="text-right uppercase text-[10px] tracking-widest text-[color:var(--institution-muted)]">Acciones</TableHead>
                        </TableRow>
                    </TableHeader>
                    <TableBody>
                        {list.map((u) => (
                            <TableRow key={u.id}>
                                <TableCell className="font-medium">{u.name}</TableCell>
                                <TableCell>{u.email}</TableCell>
                                <TableCell>
                                    <span className="pill" style={{ borderColor: "var(--institution-border)", backgroundColor: "var(--institution-cream)" }}>
                                        {ROLE_LABEL[u.role]}
                                    </span>
                                </TableCell>
                                <TableCell className="text-right">
                                    <Button variant="ghost" size="sm" onClick={() => onEdit(u)} className="rounded-sm" data-testid={`user-edit-${u.id}`}>
                                        <Pencil size={14} />
                                    </Button>
                                    <Button
                                        variant="ghost"
                                        size="sm"
                                        onClick={() => onDelete(u)}
                                        className="rounded-sm text-[color:var(--institution-danger)]"
                                        data-testid={`user-delete-${u.id}`}
                                    >
                                        <Trash2 size={14} />
                                    </Button>
                                </TableCell>
                            </TableRow>
                        ))}
                    </TableBody>
                </Table>
            </div>
        </div>
    );
}
