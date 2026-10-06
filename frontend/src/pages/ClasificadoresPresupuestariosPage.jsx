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
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { ChevronLeft, ChevronRight, Pencil, Plus } from "lucide-react";

const EMPTY = { codigo: "", nombre: "", activa: true };
const PAGE_SIZE = 25;

export default function ClasificadoresPresupuestariosPage() {
  const { user } = useAuth();
  const [items, setItems] = useState([]);
  const [pagina, setPagina] = useState(1);
  const [totalPaginas, setTotalPaginas] = useState(1);
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState(null);
  const [formData, setFormData] = useState({ ...EMPTY });
  const [loading, setLoading] = useState(false);

  const fetchItems = useCallback(async () => {
    try {
      const response = await apiClient.get("/clasificadores-presupuestarios", {
        params: { pag: pagina, tam: PAGE_SIZE },
      });
      setItems(response.data.items || []);
      setTotalPaginas(response.data.pages || 1);
    } catch (error) {
      toast.error("No se pudieron cargar los clasificadores.");
    }
  }, [pagina]);

  useEffect(() => {
    fetchItems();
  }, [fetchItems]);

  const handleSubmit = async (event) => {
    event.preventDefault();
    if (!/^\d{5}$/.test(formData.codigo)) {
      toast.error("El código debe contener exactamente cinco dígitos.");
      return;
    }
    setLoading(true);
    try {
      if (editing) {
        await apiClient.put(
          `/clasificadores-presupuestarios/${editing.id}`,
          formData,
        );
        toast.success("Clasificador actualizado.");
      } else {
        await apiClient.post("/clasificadores-presupuestarios", formData);
        toast.success("Clasificador creado.");
      }
      setOpen(false);
      setEditing(null);
      await fetchItems();
    } catch (error) {
      toast.error(formatApiError(error));
    } finally {
      setLoading(false);
    }
  };

  const handleEdit = (item) => {
    setEditing(item);
    setFormData({
      codigo: item.codigo,
      nombre: item.nombre,
      activa: item.activa,
    });
    setOpen(true);
  };

  const handleOpenChange = (isOpen) => {
    setOpen(isOpen);
    if (!isOpen) {
      setEditing(null);
    } else if (!editing) {
      setFormData({ ...EMPTY });
    }
  };

  if (user?.rol !== "SuperAdmin") {
    return (
      <div className="rounded-sm border bg-white p-6 text-sm">
        Solo el SuperAdmin puede administrar el catálogo global.
      </div>
    );
  }

  return (
    <div className="space-y-6" data-testid="clasificadores-presupuestarios-page">
      <div className="flex items-end justify-between gap-4">
        <div>
          <div className="section-eyebrow">Catálogo global</div>
          <h1 className="font-serif-display text-4xl mt-1">
            Clasificadores presupuestarios
          </h1>
          <p className="text-sm text-[color:var(--institution-muted)] mt-1">
            Los clasificadores están disponibles para todas las oficinas. Desactive los que ya no deban asignarse.
          </p>
        </div>
        <Dialog open={open} onOpenChange={handleOpenChange}>
          <DialogTrigger asChild>
            <Button
              data-testid="new-clasificador-btn"
              className="rounded-sm text-white"
              style={{ backgroundColor: "var(--institution-burgundy)" }}
            >
              <Plus size={16} className="mr-1" /> Nuevo clasificador
            </Button>
          </DialogTrigger>
          <DialogContent className="rounded-sm">
            <DialogHeader>
              <DialogTitle className="font-serif-display text-2xl">
                {editing ? "Editar clasificador" : "Nuevo clasificador"}
              </DialogTitle>
            </DialogHeader>
            <form onSubmit={handleSubmit} className="space-y-4">
              <div className="space-y-1.5">
                <Label htmlFor="clasificador-codigo">Código (5 dígitos)</Label>
                <Input
                  id="clasificador-codigo"
                  value={formData.codigo}
                  onChange={(event) =>
                    setFormData({
                      ...formData,
                      codigo: event.target.value.replace(/\D/g, "").slice(0, 5),
                    })
                  }
                  inputMode="numeric"
                  maxLength={5}
                  pattern="[0-9]{5}"
                  placeholder="12100"
                  required
                  data-testid="clasificador-codigo-input"
                  className="rounded-sm"
                />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="clasificador-nombre">Nombre</Label>
                <Input
                  id="clasificador-nombre"
                  value={formData.nombre}
                  onChange={(event) =>
                    setFormData({ ...formData, nombre: event.target.value })
                  }
                  required
                  data-testid="clasificador-nombre-input"
                  className="rounded-sm"
                />
              </div>
              <label className="flex items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  checked={formData.activa}
                  onChange={(event) =>
                    setFormData({ ...formData, activa: event.target.checked })
                  }
                  data-testid="clasificador-activa-input"
                />
                Activo
              </label>
              <DialogFooter>
                <Button
                  type="submit"
                  disabled={loading}
                  data-testid="clasificador-save-btn"
                  className="rounded-sm text-white"
                  style={{ backgroundColor: "var(--institution-burgundy)" }}
                >
                  {editing ? "Actualizar" : "Crear"}
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
              <TableHead className="uppercase text-[10px] tracking-widest text-[color:var(--institution-muted)]">Estado</TableHead>
              <TableHead className="text-right uppercase text-[10px] tracking-widest text-[color:var(--institution-muted)]">Acciones</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {items.map((item) => (
              <TableRow key={item.id} data-testid={`clasificador-row-${item.id}`}>
                <TableCell className="font-mono">{item.codigo}</TableCell>
                <TableCell className="font-medium">{item.nombre}</TableCell>
                <TableCell>
                  <span className={item.activa ? "text-emerald-700" : "text-[color:var(--institution-muted)]"}>
                    {item.activa ? "Activo" : "Inactivo"}
                  </span>
                </TableCell>
                <TableCell className="text-right">
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => handleEdit(item)}
                    aria-label={`Editar ${item.nombre}`}
                    data-testid={`clasificador-edit-${item.id}`}
                    className="rounded-sm"
                  >
                    <Pencil size={14} />
                  </Button>
                </TableCell>
              </TableRow>
            ))}
            {items.length === 0 && (
              <TableRow>
                <TableCell colSpan={4} className="text-center py-12 text-sm text-[color:var(--institution-muted)]">
                  No hay clasificadores registrados.
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </div>
      <div className="flex items-center justify-between px-2 text-xs text-[color:var(--institution-muted)]">
        <div>Página <b>{pagina}</b> de <b>{totalPaginas}</b></div>
        <div className="flex items-center gap-2">
          <Button variant="outline" size="sm" className="rounded-sm gap-1 h-8 px-3" onClick={() => setPagina((value) => Math.max(value - 1, 1))} disabled={pagina === 1}>
            <ChevronLeft size={14} /> Anterior
          </Button>
          <Button variant="outline" size="sm" className="rounded-sm gap-1 h-8 px-3" onClick={() => setPagina((value) => Math.min(value + 1, totalPaginas))} disabled={pagina === totalPaginas}>
            Siguiente <ChevronRight size={14} />
          </Button>
        </div>
      </div>
    </div>
  );
}
