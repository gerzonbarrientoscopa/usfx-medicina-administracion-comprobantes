import React, { useCallback, useEffect, useState } from "react";
import { apiClient, formatApiError } from "@/lib/api";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
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
import { Plus, Pencil, Trash2, ChevronLeft, ChevronRight } from "lucide-react";

const EMPTY = {
  nombre: "",
  prefijo_comprobante: "",
  suboficina: "",
  activa: true,
};
const FILAS_POR_PAGINA = 20;

export default function OficinasPage() {
  const [oficinas, setOficinas] = useState([]);
  const [textoBuscar, setTextoBuscar] = useState("");
  const [open, setOpen] = useState(false);
  const [editingOficina, setEditingOficina] = useState(null);
  const [formData, setFormData] = useState(EMPTY);
  const [loading, setLoading] = useState(false);
  const [pagina, setPagina] = useState(1);
  const [totalPaginas, setTotalPaginas] = useState(1);

  const fetchOficinas = useCallback(async () => {
    try {
      const { data } = await apiClient.get("/oficinas", {
        params: {
          pag: pagina,
          tam: FILAS_POR_PAGINA,
          q: textoBuscar || undefined,
        },
      });
      setOficinas(data.items || []);
      setTotalPaginas(Math.max(data.pages || 1, 1));
    } catch (error) {
      toast.error(formatApiError(error));
    }
  }, [pagina, textoBuscar]);

  useEffect(() => {
    fetchOficinas();
  }, [fetchOficinas]);

  const handleSubmit = async (event) => {
    event.preventDefault();
    setLoading(true);
    try {
      if (editingOficina) {
        await apiClient.put(`/oficinas/${editingOficina.id}`, formData);
        toast.success("Oficina actualizada.");
      } else {
        await apiClient.post("/oficinas", formData);
        toast.success("Oficina creada.");
      }
      setOpen(false);
      fetchOficinas();
    } catch (error) {
      toast.error(formatApiError(error));
    } finally {
      setLoading(false);
    }
  };

  const handleDelete = async (oficina) => {
    if (!window.confirm(`¿Eliminar la oficina "${oficina.nombre}"?`)) return;
    try {
      await apiClient.delete(`/oficinas/${oficina.id}`);
      toast.success("Oficina eliminada.");
      fetchOficinas();
    } catch (error) {
      // El servidor informa aquí si la oficina todavía tiene usuarios u otros registros.
      toast.error(formatApiError(error));
    }
  };

  const handleEdit = (oficina) => {
    setEditingOficina(oficina);
    setFormData({
      nombre: oficina.nombre,
      prefijo_comprobante: oficina.prefijo_comprobante || "",
      suboficina: oficina.suboficina || "",
      activa: Boolean(oficina.activa),
    });
    setOpen(true);
  };

  const handleOpenChange = (isOpen) => {
    setOpen(isOpen);
    if (!isOpen) {
      setEditingOficina(null);
      setFormData(EMPTY);
      return;
    }
    if (isOpen && !editingOficina) {
      setEditingOficina(null);
      setFormData(EMPTY);
    }
  };

  const handleBuscar = (event) => {
    setTextoBuscar(event.target.value);
    setPagina(1);
  };

  return (
    <div className="space-y-6" data-testid="oficinas-page">
      <div className="flex items-end justify-between">
        <div>
          <div className="section-eyebrow">Gestión institucional</div>
          <h1 className="font-serif-display text-4xl mt-1">Oficinas</h1>
          <p className="text-sm text-[color:var(--institution-muted)] mt-1">
            Administra las oficinas y su disponibilidad en el sistema.
          </p>
        </div>
        <Dialog open={open} onOpenChange={handleOpenChange}>
          <DialogTrigger asChild>
            <Button
              data-testid="new-oficina-btn"
              className="rounded-sm text-white"
              style={{ backgroundColor: "var(--institution-burgundy)" }}
            >
              <Plus size={16} className="mr-1" /> Nueva oficina
            </Button>
          </DialogTrigger>
          <DialogContent className="rounded-sm">
            <DialogHeader>
              <DialogTitle className="font-serif-display text-2xl">
                {editingOficina ? "Editar oficina" : "Nueva oficina"}
              </DialogTitle>
            </DialogHeader>
            <form onSubmit={handleSubmit} className="space-y-4" data-testid="oficina-form">
              <div className="space-y-1.5">
                <Label className="text-xs uppercase tracking-widest text-[color:var(--institution-muted)]">
                  Nombre
                </Label>
                <Input
                  value={formData.nombre}
                  onChange={(event) =>
                    setFormData({ ...formData, nombre: event.target.value })
                  }
                  required
                  data-testid="oficina-nombre-input"
                  className="rounded-sm"
                />
              </div>
              <div className="space-y-1.5">
                <Label className="text-xs uppercase tracking-widest text-[color:var(--institution-muted)]">
                  Prefijo del comprobante (3 letras)
                </Label>
                <Input
                  value={formData.prefijo_comprobante}
                  onChange={(event) =>
                    setFormData({
                      ...formData,
                      prefijo_comprobante: event.target.value
                        .toUpperCase()
                        .replace(/[^A-Z]/g, "")
                        .slice(0, 3),
                    })
                  }
                  placeholder="MED"
                  maxLength={3}
                  minLength={3}
                  required
                  autoCapitalize="characters"
                  data-testid="oficina-prefix-input"
                  className="rounded-sm font-mono uppercase"
                />
                <p className="text-xs text-[color:var(--institution-muted)]">
                  Debe ser único. Se mostrará, por ejemplo, como MED-00001 / 2026.
                </p>
              </div>
              <div className="space-y-1.5">
                <Label className="text-xs uppercase tracking-widest text-[color:var(--institution-muted)]">
                  Suboficina (solo para impresión)
                </Label>
                <Input
                  value={formData.suboficina}
                  onChange={(event) =>
                    setFormData({ ...formData, suboficina: event.target.value })
                  }
                  placeholder="Administración, Caja…"
                  maxLength={100}
                  data-testid="oficina-suboffice-input"
                  className="rounded-sm"
                />
                <p className="text-xs text-[color:var(--institution-muted)]">
                  Opcional. Si queda vacío, no aparecerá en el comprobante.
                </p>
              </div>
              <div className="flex items-center justify-between">
                <Label
                  htmlFor="oficina-activa"
                  className="text-xs uppercase tracking-widest text-[color:var(--institution-muted)]"
                >
                  Oficina activa
                </Label>
                <Switch
                  id="oficina-activa"
                  checked={formData.activa}
                  onCheckedChange={(activa) => setFormData({ ...formData, activa })}
                  data-testid="oficina-activa-switch"
                />
              </div>
              <DialogFooter>
                <Button
                  type="submit"
                  disabled={loading}
                  data-testid="oficina-save-btn"
                  className="rounded-sm text-white"
                  style={{ backgroundColor: "var(--institution-burgundy)" }}
                >
                  {loading ? "Guardando..." : editingOficina ? "Actualizar" : "Crear"}
                </Button>
              </DialogFooter>
            </form>
          </DialogContent>
        </Dialog>
      </div>

      <Input
        placeholder="Buscar oficinas por nombre"
        value={textoBuscar}
        onChange={handleBuscar}
        className="max-w-md rounded-sm"
        data-testid="oficinas-search"
      />

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
                Prefijo
              </TableHead>
              <TableHead className="uppercase text-[10px] tracking-widest text-[color:var(--institution-muted)]">
                Estado
              </TableHead>
              <TableHead className="text-right uppercase text-[10px] tracking-widest text-[color:var(--institution-muted)]">
                Acciones
              </TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {oficinas.map((oficina) => (
              <TableRow key={oficina.id} data-testid={`oficina-row-${oficina.id}`}>
                <TableCell className="font-medium">{oficina.nombre}</TableCell>
                <TableCell className="font-mono font-semibold">{oficina.prefijo_comprobante}</TableCell>
                <TableCell>
                  <span
                    className="pill"
                    style={{
                      borderColor: "var(--institution-border)",
                      backgroundColor: "var(--institution-cream)",
                    }}
                  >
                    {oficina.activa ? "Activa" : "Inactiva"}
                  </span>
                </TableCell>
                <TableCell className="text-right">
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => handleEdit(oficina)}
                    data-testid={`oficina-edit-${oficina.id}`}
                    className="rounded-sm"
                  >
                    <Pencil size={14} />
                  </Button>
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => handleDelete(oficina)}
                    data-testid={`oficina-delete-${oficina.id}`}
                    className="rounded-sm text-[color:var(--institution-danger)]"
                  >
                    <Trash2 size={14} />
                  </Button>
                </TableCell>
              </TableRow>
            ))}
            {oficinas.length === 0 && (
              <TableRow>
                <TableCell
                  colSpan={4}
                  className="text-center py-12 text-sm text-[color:var(--institution-muted)]"
                >
                  No hay oficinas registradas.
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
            onClick={() => setPagina((page) => Math.max(page - 1, 1))}
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
            onClick={() => setPagina((page) => Math.min(page + 1, totalPaginas))}
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