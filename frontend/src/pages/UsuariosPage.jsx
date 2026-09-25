import React, { useCallback, useEffect, useState } from "react";
import { apiClient, formatApiError } from "@/lib/api";
import { useAuth } from "@/contexts/AuthContext";
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
import { Plus, Pencil, Trash2, ChevronLeft, ChevronRight } from "lucide-react";

const EMPTY = { email: "", nombre: "", password: "", rol: "Caja" };

export default function UsuariosPage() {
  const { user } = useAuth();
  const isSuperAdmin = user?.rol === "SuperAdmin";
  const isAdministrador = user?.rol === "Administrador";
  const [usuarios, setUsuarios] = useState([]);
  const [oficinas, setOficinas] = useState([]);
  const [officeFilter, setOfficeFilter] = useState("all");
  const [open, setOpen] = useState(false);
  const [editingUsuario, setEditingUsuario] = useState(null);
  const [formData, setFormData] = useState({ ...EMPTY, office_id: "" });
  const [loading, setLoading] = useState(false);
  const [pagina, setPagina] = useState(1);
  const [totalPaginas, setTotalPaginas] = useState(1);
  const FILAS_POR_PAGINA = 20;

  const fetchUsuarios = useCallback(async () => {
    try {
      const response = await apiClient.get("/usuarios", {
        params: {
          pag: pagina,
          tam: FILAS_POR_PAGINA,
          ...(isSuperAdmin && officeFilter !== "all"
            ? { office_id: officeFilter }
            : {}),
        },
      });
      setUsuarios(response.data.items || []);
      setTotalPaginas(response.data.pages || 1);
    } catch (error) {
      toast.error("Error al cargar usuarios.");
    }
  }, [pagina, officeFilter, isSuperAdmin]);

  const fetchOficinas = useCallback(async () => {
    try {
      const first = await apiClient.get("/oficinas", {
        params: { pag: 1, tam: 100 },
      });
      const rest = await Promise.all(
        Array.from({ length: (first.data.pages || 1) - 1 }, (_, index) =>
          apiClient.get("/oficinas", { params: { pag: index + 2, tam: 100 } }),
        ),
      );
      setOficinas([
        ...(first.data.items || []),
        ...rest.flatMap((response) => response.data.items || []),
      ]);
    } catch (error) {
      toast.error("Error al cargar oficinas.");
    }
  }, []);

  useEffect(() => {
    fetchUsuarios();
  }, [fetchUsuarios]);

  useEffect(() => {
    if (isSuperAdmin) fetchOficinas();
  }, [isSuperAdmin, fetchOficinas]);

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (isSuperAdmin && !formData.office_id) {
      toast.error("Selecciona una oficina.");
      return;
    }
    setLoading(true);
    try {
      if (editingUsuario) {
        const payload = {
          nombre: formData.nombre,
          rol: formData.rol,
          ...(isSuperAdmin ? { office_id: formData.office_id } : {}),
        };
        if (formData.password) payload.password = formData.password;
        await apiClient.put(`/usuarios/${editingUsuario.id}`, payload);
        toast.success("Usuario actualizado.");
      } else {
        const payload = {
          email: formData.email,
          nombre: formData.nombre,
          password: formData.password,
          rol: formData.rol,
          ...(isSuperAdmin ? { office_id: formData.office_id } : {}),
        };
        await apiClient.post("/usuarios", payload);
        toast.success("Usuario creado.");
      }
      setOpen(false);
      setEditingUsuario(null);
      fetchUsuarios();
    } catch (error) {
      const serverDetail = error.response?.data?.detail;
      if (Array.isArray(serverDetail)) {
        const primerError = serverDetail[0];
        const campo = primerError.loc
          ? primerError.loc[primerError.loc.length - 1]
          : "campo";
        toast.error(`Error en '${campo}': ${primerError.msg}`);
      } else if (typeof serverDetail === "string") {
        toast.error(serverDetail);
      } else {
        toast.error("Error al guardar los cambios.");
      }
    } finally {
      setLoading(false);
    }
  };

  const handleDelete = async (usuario) => {
    if (!canManage(usuario)) return;
    if (!window.confirm(`¿Eliminar "${usuario.nombre}"?`)) return;
    try {
      await apiClient.delete(`/usuarios/${usuario.id}`);
      toast.success("Usuario eliminado.");
      fetchUsuarios();
    } catch (err) {
      toast.error(formatApiError(err));
    }
  };

  const handleEdit = (usuario) => {
    if (!canManage(usuario)) return;
    setEditingUsuario(usuario);
    setFormData({
      email: usuario.email,
      nombre: usuario.nombre,
      password: "",
      rol: usuario.rol,
      office_id: usuario.office_id == null ? "" : String(usuario.office_id),
    });
    setOpen(true);
  };

  const canManage = (usuario) =>
    usuario.rol !== "SuperAdmin" &&
    (isSuperAdmin || (isAdministrador && usuario.rol !== "Administrador"));

  const handleOpenChange = (isOpen) => {
    setOpen(isOpen);
    if (!isOpen) {
      setEditingUsuario(null);
      setFormData({ ...EMPTY, office_id: "" });
    } else if (!editingUsuario) {
      setFormData({ ...EMPTY, office_id: "" });
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
        {isSuperAdmin && (
          <div className="flex items-center gap-3">
            <Label
              htmlFor="user-office-filter"
              className="text-xs uppercase tracking-widest text-[color:var(--institution-muted)]"
            >
              Oficina
            </Label>
            <Select
              value={officeFilter}
              onValueChange={(value) => {
                setOfficeFilter(value);
                setPagina(1);
              }}
            >
              <SelectTrigger
                id="user-office-filter"
                className="rounded-sm max-w-xs"
                data-testid="user-office-filter"
              >
                <SelectValue placeholder="Todas las oficinas" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">Todas las oficinas</SelectItem>
                {oficinas.map((oficina) => {
                  const id = oficina.id ?? oficina.office_id;
                  return (
                    <SelectItem key={id} value={String(id)}>
                      {oficina.nombre || oficina.office_nombre || `Oficina ${id}`}
                    </SelectItem>
                  );
                })}
              </SelectContent>
            </Select>
          </div>
        )}
        <Dialog open={open} onOpenChange={handleOpenChange}>
          <DialogTrigger asChild>
            <Button
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
                {editingUsuario ? "Editar usuario" : "Nuevo usuario"}
              </DialogTitle>
            </DialogHeader>
            <form onSubmit={handleSubmit} className="space-y-4">
              <div className="space-y-1.5">
                <Label className="text-xs uppercase tracking-widest text-[color:var(--institution-muted)]">
                  Nombre completo
                </Label>
                <Input
                  value={formData.nombre}
                  onChange={(e) =>
                    setFormData({ ...formData, nombre: e.target.value })
                  }
                  required
                  data-testid="user-name-input"
                  className="rounded-sm"
                />
              </div>
              <div className="space-y-1.5">
                <Label className="text-xs uppercase tracking-widest text-[color:var(--institution-muted)]">
                  Email
                </Label>
                <Input
                  type="email"
                  value={formData.email}
                  onChange={(e) =>
                    setFormData({ ...formData, email: e.target.value })
                  }
                  required
                  disabled={!!editingUsuario}
                  data-testid="user-email-input"
                  className="rounded-sm"
                />
              </div>
              <div className="space-y-1.5">
                <Label className="text-xs uppercase tracking-widest text-[color:var(--institution-muted)]">
                  {editingUsuario
                    ? "Nueva contraseña (opcional)"
                    : "Contraseña"}
                </Label>
                <Input
                  type="password"
                  value={formData.password}
                  onChange={(e) =>
                    setFormData({ ...formData, password: e.target.value })
                  }
                  required={!editingUsuario}
                  data-testid="user-password-input"
                  className="rounded-sm"
                />
              </div>
              <div className="space-y-1.5">
                <Label className="text-xs uppercase tracking-widest text-[color:var(--institution-muted)]">
                  Rol
                </Label>
                <Select
                  value={formData.rol}
                  onValueChange={(v) => setFormData({ ...formData, rol: v })}
                >
                  <SelectTrigger
                    className="rounded-sm"
                    data-testid="user-role-select"
                  >
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {isSuperAdmin && (
                      <SelectItem value="Administrador">
                        Administrador
                      </SelectItem>
                    )}
                    <SelectItem value="Caja">Caja</SelectItem>
                    <SelectItem value="Consultas">Consultas</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              {isSuperAdmin && (
                <div className="space-y-1.5">
                  <Label className="text-xs uppercase tracking-widest text-[color:var(--institution-muted)]">
                    Oficina
                  </Label>
                  <Select
                    value={formData.office_id}
                    onValueChange={(value) =>
                      setFormData({ ...formData, office_id: value })
                    }
                  >
                    <SelectTrigger
                      className="rounded-sm"
                      data-testid="user-office-select"
                    >
                      <SelectValue placeholder="Selecciona una oficina" />
                    </SelectTrigger>
                    <SelectContent>
                      {oficinas.map((oficina) => {
                        const id = oficina.id ?? oficina.office_id;
                        return (
                          <SelectItem key={id} value={String(id)}>
                            {oficina.nombre ||
                              oficina.office_nombre ||
                              `Oficina ${id}`}
                          </SelectItem>
                        );
                      })}
                    </SelectContent>
                  </Select>
                </div>
              )}
              <DialogFooter>
                <Button
                  type="submit"
                  disabled={loading}
                  data-testid="user-save-btn"
                  className="rounded-sm text-white"
                  style={{ backgroundColor: "var(--institution-burgundy)" }}
                >
                  {loading
                    ? "Guardando..."
                    : editingUsuario
                      ? "Guardar cambios"
                      : "Crear usuario"}
                </Button>
              </DialogFooter>
            </form>
          </DialogContent>
        </Dialog>
      </div>

      <div
        className="bg-white border rounded-sm"
        style={{ borderColor: "var(--institution-border)" }}
      >
        <Table>
          <TableHeader>
            <TableRow style={{ backgroundColor: "var(--institution-cream)" }}>
              <TableHead className="uppercase text-[10px] tracking-widest text-[color:var(--institution-muted)]">
                Nombre
              </TableHead>
              <TableHead className="uppercase text-[10px] tracking-widest text-[color:var(--institution-muted)]">
                Email
              </TableHead>
              <TableHead className="uppercase text-[10px] tracking-widest text-[color:var(--institution-muted)]">
                Rol
              </TableHead>
              <TableHead className="uppercase text-[10px] tracking-widest text-[color:var(--institution-muted)]">
                Oficina
              </TableHead>
              <TableHead className="text-right uppercase text-[10px] tracking-widest text-[color:var(--institution-muted)]">
                Acciones
              </TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {usuarios.map((usuario) => (
              <TableRow key={usuario.id} data-testid={`user-row-${usuario.id}`}>
                <TableCell className="font-medium">{usuario.nombre}</TableCell>
                <TableCell>{usuario.email}</TableCell>
                <TableCell>
                  <span
                    className="pill"
                    style={{
                      borderColor: "var(--institution-border)",
                      backgroundColor: "var(--institution-cream)",
                    }}
                  >
                    {usuario.rol}
                  </span>
                </TableCell>
                <TableCell>{usuario.office_nombre || "—"}</TableCell>
                <TableCell className="text-right">
                  {canManage(usuario) && (
                    <>
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => handleEdit(usuario)}
                        data-testid={`user-edit-${usuario.id}`}
                        className="rounded-sm"
                      >
                        <Pencil size={14} />
                      </Button>
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => handleDelete(usuario)}
                        data-testid={`user-delete-${usuario.id}`}
                        className="rounded-sm text-[color:var(--institution-danger)]"
                      >
                        <Trash2 size={14} />
                      </Button>
                    </>
                  )}
                </TableCell>
              </TableRow>
            ))}
            {usuarios.length === 0 && (
              <TableRow>
                <TableCell
                  colSpan={5}
                  className="text-center py-12 text-sm text-[color:var(--institution-muted)]"
                >
                  Sin usuarios registrados.
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </div>
      <div className="flex items-center justify-between px-2 text-xs text-[color:var(--institution-muted)]">
        <div>
          Página <b>{pagina}</b> de <b>{totalPaginas}</b>
        </div>
        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            className="rounded-sm gap-1 h-8 px-3"
            style={{ borderColor: "var(--institution-border)" }}
            onClick={() => setPagina((p) => Math.max(p - 1, 1))}
            disabled={pagina === 1}
          >
            <ChevronLeft size={14} />
            Anterior
          </Button>
          <Button
            variant="outline"
            size="sm"
            className="rounded-sm gap-1 h-8 px-3"
            style={{ borderColor: "var(--institution-border)" }}
            onClick={() => setPagina((p) => Math.min(p + 1, totalPaginas))}
            disabled={pagina === totalPaginas}
          >
            Siguiente
            <ChevronRight size={14} />
          </Button>
        </div>
      </div>
    </div>
  );
}
