import React, { useCallback, useEffect, useState } from "react";
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
import { Plus, Pencil, Trash2, ChevronLeft, ChevronRight } from "lucide-react";

const PAGE_SIZE = 20;
const emptyForm = () => ({
  ci: "",
  nombre: "",
});

export default function PersonasPage() {
  const [personas, setPersonas] = useState([]);
  const [textoBuscar, setTextoBuscar] = useState("");
  const [open, setOpen] = useState(false);
  const [editingPersona, setEditingPersona] = useState(null);
  const [formData, setFormData] = useState(emptyForm());
  const [loading, setLoading] = useState(false);
  const [pagina, setPagina] = useState(1);
  const [totalPaginas, setTotalPaginas] = useState(1);

  const fetchPersonas = useCallback(async () => {
    try {
      const response = await apiClient.get("/personas", {
        params: {
          pag: pagina,
          tam: PAGE_SIZE,
          textoBuscar: textoBuscar || undefined,
        },
      });
      setPersonas(response.data.items);
      setTotalPaginas(response.data.pages || 1);
    } catch (error) {
      toast.error(formatApiError(error) || "Error al cargar personas.");
    }
  }, [pagina, textoBuscar]);

  useEffect(() => {
    fetchPersonas();
  }, [fetchPersonas]);

  const handleSubmit = async (event) => {
    event.preventDefault();
    setLoading(true);
    try {
      const payload = {
        ci: formData.ci.trim(),
        nombre: formData.nombre.trim(),
      };

      if (editingPersona) {
        await apiClient.put(`/personas/${editingPersona.id}`, payload);
        toast.success("Persona actualizada.");
      } else {
        await apiClient.post("/personas", payload);
        toast.success("Persona registrada.");
      }
      setOpen(false);
      setEditingPersona(null);
      fetchPersonas();
    } catch (error) {
      const detail = error.response?.data?.detail;
      if (Array.isArray(detail)) {
        const firstError = detail[0];
        const field = firstError.loc?.[firstError.loc.length - 1] || "campo";
        toast.error(`Error en '${field}': ${firstError.msg}`);
      } else {
        toast.error(
          typeof detail === "string"
            ? detail
            : formatApiError(error) || "Error al guardar la persona.",
        );
      }
    } finally {
      setLoading(false);
    }
  };

  const handleEdit = (persona) => {
    setEditingPersona(persona);
    setFormData({
      ci: persona.ci,
      nombre: persona.nombre,
    });
    setOpen(true);
  };

  const handleOpenChange = (isOpen) => {
    setOpen(isOpen);
    if (!isOpen) {
      setEditingPersona(null);
      setFormData(emptyForm());
    } else if (!editingPersona) {
      setFormData(emptyForm());
    }
  };

  const handleDelete = async (persona) => {
    if (!window.confirm(`¿Eliminar a "${persona.nombre}"?`)) return;
    try {
      await apiClient.delete(`/personas/${persona.id}`);
      toast.success("Persona eliminada.");
      if (personas.length === 1 && pagina > 1) {
        setPagina((current) => current - 1);
      } else {
        fetchPersonas();
      }
    } catch (error) {
      toast.error(formatApiError(error));
    }
  };

  const handleBuscar = (event) => {
    setTextoBuscar(event.target.value);
    setPagina(1);
  };

  return (
    <div className="space-y-6" data-testid="personas-page">
      <div className="flex items-end justify-between gap-4">
        <div>
          <div className="section-eyebrow">Registro de personas</div>
          <h1 className="font-serif-display text-4xl mt-1">Personas</h1>
          <p className="text-sm text-[color:var(--institution-muted)] mt-1">
            Clientes globales que pueden realizar operaciones en distintas oficinas.
          </p>
        </div>
        <Dialog open={open} onOpenChange={handleOpenChange}>
          <DialogTrigger asChild>
            <Button
              data-testid="new-persona-btn"
              className="rounded-sm text-white shrink-0"
              style={{ backgroundColor: "var(--institution-burgundy)" }}
            >
              <Plus size={16} className="mr-1" /> Nueva persona
            </Button>
          </DialogTrigger>
          <DialogContent className="rounded-sm">
            <DialogHeader>
              <DialogTitle className="font-serif-display text-2xl">
                {editingPersona ? "Editar persona" : "Nueva persona"}
              </DialogTitle>
            </DialogHeader>
            <form
              onSubmit={handleSubmit}
              className="grid grid-cols-2 gap-4"
              data-testid="persona-form"
            >
              <div className="space-y-1.5">
                <Label htmlFor="persona-ci">C.I.</Label>
                <Input
                  id="persona-ci"
                  value={formData.ci}
                  onChange={(event) =>
                    setFormData({ ...formData, ci: event.target.value })
                  }
                  required
                  maxLength={30}
                  data-testid="persona-ci-input"
                  className="rounded-sm"
                />
              </div>
              <div className="space-y-1.5 col-span-2">
                <Label htmlFor="persona-nombre">Nombre completo</Label>
                <Input
                  id="persona-nombre"
                  value={formData.nombre}
                  onChange={(event) =>
                    setFormData({ ...formData, nombre: event.target.value })
                  }
                  required
                  maxLength={200}
                  data-testid="persona-nombre-input"
                  className="rounded-sm"
                />
              </div>
              <p className="col-span-2 text-xs text-[color:var(--institution-muted)]">
                Se comprobará que el C.I. no esté registrado como estudiante en
                ninguna oficina.
              </p>
              <DialogFooter className="col-span-2">
                <Button
                  type="submit"
                  disabled={loading}
                  data-testid="persona-save-btn"
                  className="rounded-sm text-white"
                  style={{ backgroundColor: "var(--institution-burgundy)" }}
                >
                  {loading
                    ? "Guardando..."
                    : editingPersona
                      ? "Actualizar"
                      : "Crear"}
                </Button>
              </DialogFooter>
            </form>
          </DialogContent>
        </Dialog>
      </div>

      <div className="flex flex-col sm:flex-row gap-3">
        <Input
          placeholder="Buscar por nombre o C.I."
          value={textoBuscar}
          onChange={handleBuscar}
          className="max-w-md rounded-sm"
          data-testid="personas-search"
        />
      </div>

      <div
        className="overflow-x-auto bg-white border rounded-sm"
        style={{ borderColor: "var(--institution-border)" }}
      >
        <Table>
          <TableHeader>
            <TableRow style={{ backgroundColor: "var(--institution-cream)" }}>
              <TableHead className="uppercase text-[10px] tracking-widest text-[color:var(--institution-muted)]">
                C.I.
              </TableHead>
              <TableHead className="uppercase text-[10px] tracking-widest text-[color:var(--institution-muted)]">
                Nombre
              </TableHead>
              <TableHead className="text-right uppercase text-[10px] tracking-widest text-[color:var(--institution-muted)]">
                Acciones
              </TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {personas.map((persona) => (
              <TableRow key={persona.id} data-testid={`persona-row-${persona.id}`}>
                <TableCell className="font-mono-num">{persona.ci}</TableCell>
                <TableCell className="font-medium">{persona.nombre}</TableCell>
                <TableCell className="text-right whitespace-nowrap">
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => handleEdit(persona)}
                    data-testid={`persona-edit-${persona.id}`}
                    aria-label={`Editar ${persona.nombre}`}
                    className="rounded-sm"
                  >
                    <Pencil size={14} />
                  </Button>
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => handleDelete(persona)}
                    data-testid={`persona-delete-${persona.id}`}
                    aria-label={`Eliminar ${persona.nombre}`}
                    className="rounded-sm text-[color:var(--institution-danger)]"
                  >
                    <Trash2 size={14} />
                  </Button>
                </TableCell>
              </TableRow>
            ))}
            {personas.length === 0 && (
              <TableRow>
                <TableCell
                  colSpan={3}
                  className="text-center py-12 text-sm text-[color:var(--institution-muted)]"
                >
                  Sin personas registradas.
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
            onClick={() => setPagina((current) => Math.max(current - 1, 1))}
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
            onClick={() =>
              setPagina((current) => Math.min(current + 1, totalPaginas))
            }
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