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
import { Plus, Pencil, Trash2, ChevronLeft, ChevronRight } from "lucide-react";

const EMPTY = { email: "", nombre: "", password: "", rol: "Caja" };

export default function UsuariosPage() {
    const [usuarios, setUsuarios] = useState([]);
    const [open, setOpen] = useState(false);
    const [editingUsuario, setEditingUsuario] = useState(null);
    const [formData, setFormData] = useState(EMPTY);
    const [loading, setLoading] = useState(false);    
    const [pagina, setPagina] = useState(1);
    const [totalPaginas, setTotalPaginas] = useState(1);
    const FILAS_POR_PAGINA = 20;

    const fetchUsuarios = async () => {
        try {
          const response = await apiClient.get("/usuarios", {
            params: {
              pag: pagina,
              tam: FILAS_POR_PAGINA,
            },
          });
          setUsuarios(response.data.items);
          if (response.data.pages) {
            setTotalPaginas(response.data.pages);
          }
        } catch (error) {
          toast.error("Error al cargar usuarios.");
        }    
    };

    useEffect(() => {
        fetchUsuarios();
    }, [pagina]);

    const handleSubmit = async (e) => {
        e.preventDefault();        
        setLoading(true);
        try {
          if (editingUsuario) {
            const payload = { nombre: formData.nombre, rol: formData.rol };
            if (formData.password) payload.password = formData.password;
            await apiClient.put(`/usuarios/${editing.id}`, payload);
            toast.success("Usuario actualizado.");
          } else {            
            await apiClient.post("/usuarios", formData);
            toast.success("Usuario creado.");
          }
          setOpen(false);
          fetchTiposPago();
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
      if (!window.confirm(`¿Eliminar "${usuario.nombre}"?`)) return;
      try {
        await apiClient.delete(`/users/${usuario.id}`);
        toast.success("Usuario eliminado.");
        fetchUsuarios();
      } catch (err) {
        toast.error(formatApiError(err));
      }
    };

    const handleEdit = (usuario) => {
      setEditingUsuario(usuario);
      setFormData({
        email: usuario.email,
        nombre: usuario.nombre,
        password: "",
        rol: usuario.rol,
      });
      setOpen(true);
    };

    const handleOpenChange = (isOpen) => {
      setOpen(isOpen);
      // Si la ventana se está abriendo, reseteamos los campos
      if (isOpen && !editingUsuario) {
        setEditingUsuario(null);
        setFormData(EMPTY);
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
                    {editingUsuario ? "Nueva contraseña (opcional)" : "Contraseña"}
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
                      <SelectItem value="Administrador">Administrador</SelectItem>
                      <SelectItem value="Caja">Caja</SelectItem>
                      <SelectItem value="Consultas">Consultas</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
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
                <TableHead className="text-right uppercase text-[10px] tracking-widest text-[color:var(--institution-muted)]">
                  Acciones
                </TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {usuarios.map((usuario) => (
                <TableRow
                  key={usuario.id}
                  data-testid={`user-row-${usuario.id}`}
                >
                  <TableCell className="font-medium">
                    {usuario.nombre}
                  </TableCell>
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
                  <TableCell className="text-right">
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
                  </TableCell>
                </TableRow>
              ))}
              {usuarios.length === 0 && (
                <TableRow>
                  <TableCell
                    colSpan={4}
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
