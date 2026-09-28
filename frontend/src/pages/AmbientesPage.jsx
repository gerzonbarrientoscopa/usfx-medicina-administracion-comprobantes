import React, { useCallback, useEffect, useState } from "react";
import { apiClient, formatApiError } from "@/lib/api";
import { useAuth } from "@/contexts/AuthContext";
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
import {
  Plus,
  Pencil,
  Trash2,
  ChevronLeft,
  ChevronRight,
  Clock3,
} from "lucide-react";

const DAYS = [
  { value: "lunes", label: "Lunes" },
  { value: "martes", label: "Martes" },
  { value: "miercoles", label: "Miércoles" },
  { value: "jueves", label: "Jueves" },
  { value: "viernes", label: "Viernes" },
  { value: "sabado", label: "Sábado" },
  { value: "domingo", label: "Domingo" },
];

const PAGE_SIZE = 20;
const emptyForm = (officeId = "") => ({
  nombre: "",
  descripcion: "",
  office_id: officeId,
  horarios: [],
});

function summarizeSchedule(horarios = []) {
  const days = DAYS.map(({ value, label }) => {
    const ranges = horarios
      .filter((block) => block.dia === value)
      .sort((a, b) => a.desde.localeCompare(b.desde));
    if (!ranges.length) return null;
    return `${label.slice(0, 3)} ${ranges
      .map(({ desde, hasta }) => `${desde}–${hasta}`)
      .join(", ")}`;
  }).filter(Boolean);
  return days.length ? days.join(" · ") : "Sin horarios registrados";
}

export default function AmbientesPage() {
  const { user } = useAuth();
  const isSuperAdmin = user?.rol === "SuperAdmin";
  const [ambientes, setAmbientes] = useState([]);
  const [oficinas, setOficinas] = useState([]);
  const [oficinaFiltro, setOficinaFiltro] = useState("");
  const [pagina, setPagina] = useState(1);
  const [totalPaginas, setTotalPaginas] = useState(1);
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState(null);
  const [formData, setFormData] = useState(emptyForm());
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!isSuperAdmin) return;
    let active = true;
    const fetchOficinas = async () => {
      try {
        const first = await apiClient.get("/oficinas", {
          params: { pag: 1, tam: 100 },
        });
        const rest = await Promise.all(
          Array.from({ length: Math.max(0, (first.data.pages || 1) - 1) }, (_, index) =>
            apiClient.get("/oficinas", {
              params: { pag: index + 2, tam: 100 },
            }),
          ),
        );
        if (active) {
          setOficinas([
            ...first.data.items,
            ...rest.flatMap((response) => response.data.items),
          ]);
        }
      } catch {
        if (active) toast.error("Error al cargar oficinas.");
      }
    };
    fetchOficinas();
    return () => {
      active = false;
    };
  }, [isSuperAdmin]);

  const fetchAmbientes = useCallback(async () => {
    try {
      const response = await apiClient.get("/ambientes", {
        params: {
          pag: pagina,
          tam: PAGE_SIZE,
          office_id: isSuperAdmin ? oficinaFiltro || undefined : undefined,
        },
      });
      setAmbientes(response.data.items);
      setTotalPaginas(response.data.pages || 1);
    } catch (error) {
      toast.error(formatApiError(error) || "Error al cargar ambientes.");
    }
  }, [pagina, oficinaFiltro, isSuperAdmin]);

  useEffect(() => {
    fetchAmbientes();
  }, [fetchAmbientes]);

  const openNewForm = () => {
    setEditing(null);
    setFormData(emptyForm(isSuperAdmin ? oficinaFiltro : ""));
    setOpen(true);
  };

  const handleOpenChange = (isOpen) => {
    setOpen(isOpen);
    if (!isOpen) {
      setEditing(null);
      setFormData(emptyForm(isSuperAdmin ? oficinaFiltro : ""));
    }
  };

  const handleEdit = (ambiente) => {
    setEditing(ambiente);
    setFormData({
      nombre: ambiente.nombre,
      descripcion: ambiente.descripcion || "",
      office_id: "",
      horarios: ambiente.horarios || [],
    });
    setOpen(true);
  };

  const addHorario = (dia) => {
    setFormData((current) => ({
      ...current,
      horarios: [
        ...current.horarios,
        { dia, desde: "08:00", hasta: "12:00" },
      ],
    }));
  };

  const updateHorario = (index, field, value) => {
    setFormData((current) => ({
      ...current,
      horarios: current.horarios.map((block, blockIndex) =>
        blockIndex === index ? { ...block, [field]: value } : block,
      ),
    }));
  };

  const removeHorario = (index) => {
    setFormData((current) => ({
      ...current,
      horarios: current.horarios.filter((_, blockIndex) => blockIndex !== index),
    }));
  };

  const handleSubmit = async (event) => {
    event.preventDefault();
    setLoading(true);
    try {
      const payload = {
        nombre: formData.nombre.trim(),
        descripcion: formData.descripcion.trim(),
        horarios: formData.horarios,
      };
      if (!editing && isSuperAdmin) payload.office_id = formData.office_id;

      if (editing) {
        await apiClient.put(`/ambientes/${editing.id}`, payload);
        toast.success("Ambiente actualizado.");
      } else {
        await apiClient.post("/ambientes", payload);
        toast.success("Ambiente registrado.");
      }
      setOpen(false);
      setEditing(null);
      fetchAmbientes();
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
            : formatApiError(error) || "Error al guardar el ambiente.",
        );
      }
    } finally {
      setLoading(false);
    }
  };

  const handleDelete = async (ambiente) => {
    if (!window.confirm(`¿Eliminar el ambiente "${ambiente.nombre}"?`)) return;
    try {
      await apiClient.delete(`/ambientes/${ambiente.id}`);
      toast.success("Ambiente eliminado.");
      if (ambientes.length === 1 && pagina > 1) {
        setPagina((current) => current - 1);
      } else {
        fetchAmbientes();
      }
    } catch (error) {
      toast.error(formatApiError(error));
    }
  };

  const handleOfficeFilter = (event) => {
    setOficinaFiltro(event.target.value);
    setPagina(1);
  };

  return (
    <div className="space-y-6" data-testid="ambientes-page">
      <div className="flex items-end justify-between gap-4">
        <div>
          <div className="section-eyebrow">Catálogo de espacios</div>
          <h1 className="font-serif-display text-4xl mt-1">Ambientes</h1>
          <p className="text-sm text-[color:var(--institution-muted)] mt-1">
            Ambientes disponibles para alquiler y sus horarios semanales.
          </p>
          {!isSuperAdmin && user?.office_nombre && (
            <p className="text-xs text-[color:var(--institution-muted)] mt-1">
              Oficina: <b>{user.office_nombre}</b>
            </p>
          )}
        </div>
        <Button
          onClick={openNewForm}
          data-testid="new-ambiente-btn"
          className="rounded-sm text-white shrink-0"
          style={{ backgroundColor: "var(--institution-burgundy)" }}
        >
          <Plus size={16} className="mr-1" /> Nuevo ambiente
        </Button>
      </div>

      <Dialog open={open} onOpenChange={handleOpenChange}>
        <DialogContent className="max-w-3xl max-h-[92vh] overflow-y-auto rounded-sm">
          <DialogHeader>
            <DialogTitle className="font-serif-display text-2xl">
              {editing ? "Editar ambiente" : "Nuevo ambiente"}
            </DialogTitle>
          </DialogHeader>
          <form onSubmit={handleSubmit} className="space-y-5">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {isSuperAdmin && !editing ? (
                <div className="space-y-1.5 md:col-span-2">
                  <Label htmlFor="ambiente-office">Oficina</Label>
                  <select
                    id="ambiente-office"
                    value={formData.office_id}
                    onChange={(event) =>
                      setFormData({ ...formData, office_id: event.target.value })
                    }
                    required
                    data-testid="ambiente-office-select"
                    className="h-10 w-full rounded-sm border border-input bg-background px-3 text-sm"
                  >
                    <option value="">Seleccione una oficina</option>
                    {oficinas.map((oficina) => (
                      <option key={oficina.id} value={oficina.id}>
                        {oficina.nombre}
                      </option>
                    ))}
                  </select>
                </div>
              ) : (
                <div className="text-sm text-[color:var(--institution-muted)] md:col-span-2">
                  Oficina:{" "}
                  <b>
                    {editing?.office_nombre ||
                      user?.office_nombre ||
                      oficinas.find((office) => office.id === oficinaFiltro)?.nombre ||
                      "Seleccione una oficina"}
                  </b>
                </div>
              )}
              <div className="space-y-1.5 md:col-span-2">
                <Label htmlFor="ambiente-nombre">Nombre del ambiente</Label>
                <Input
                  id="ambiente-nombre"
                  value={formData.nombre}
                  onChange={(event) =>
                    setFormData({ ...formData, nombre: event.target.value })
                  }
                  required
                  maxLength={120}
                  data-testid="ambiente-nombre-input"
                  className="rounded-sm"
                />
              </div>
              <div className="space-y-1.5 md:col-span-2">
                <Label htmlFor="ambiente-descripcion">Descripción (opcional)</Label>
                <Textarea
                  id="ambiente-descripcion"
                  value={formData.descripcion}
                  onChange={(event) =>
                    setFormData({ ...formData, descripcion: event.target.value })
                  }
                  rows={2}
                  maxLength={500}
                  data-testid="ambiente-descripcion-input"
                  className="rounded-sm"
                />
              </div>
            </div>

            <section className="space-y-3">
              <div>
                <h2 className="font-medium">Disponibilidad semanal</h2>
                <p className="text-xs text-[color:var(--institution-muted)] mt-1">
                  Agregue uno o más intervalos por día. Los días sin intervalos
                  quedan cerrados; el horario se repite cada semana.
                </p>
              </div>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                {DAYS.map(({ value, label }) => {
                  const blocks = formData.horarios
                    .map((block, index) => ({ ...block, index }))
                    .filter((block) => block.dia === value);
                  return (
                    <div
                      key={value}
                      className="rounded-sm border p-3 space-y-2"
                      style={{ borderColor: "var(--institution-border)" }}
                    >
                      <div className="flex items-center justify-between gap-2">
                        <span className="text-sm font-medium">{label}</span>
                        <Button
                          type="button"
                          variant="outline"
                          size="sm"
                          onClick={() => addHorario(value)}
                          data-testid={`ambiente-add-${value}`}
                          className="h-8 rounded-sm"
                        >
                          <Plus size={14} className="mr-1" />
                          Agregar horario
                        </Button>
                      </div>
                      {blocks.length === 0 ? (
                        <p className="text-xs text-[color:var(--institution-muted)]">
                          Cerrado
                        </p>
                      ) : (
                        blocks.map((block) => (
                          <div
                            key={`${value}-${block.index}`}
                            className="flex items-center gap-2"
                          >
                            <Input
                              type="time"
                              value={block.desde}
                              onChange={(event) =>
                                updateHorario(block.index, "desde", event.target.value)
                              }
                              required
                              aria-label={`${label}: hora de inicio`}
                              data-testid={`ambiente-${value}-${block.index}-desde`}
                              className="h-9 rounded-sm"
                            />
                            <span className="text-xs text-[color:var(--institution-muted)]">
                              a
                            </span>
                            <Input
                              type="time"
                              value={block.hasta}
                              onChange={(event) =>
                                updateHorario(block.index, "hasta", event.target.value)
                              }
                              required
                              aria-label={`${label}: hora de fin`}
                              data-testid={`ambiente-${value}-${block.index}-hasta`}
                              className="h-9 rounded-sm"
                            />
                            <Button
                              type="button"
                              variant="ghost"
                              size="icon"
                              onClick={() => removeHorario(block.index)}
                              aria-label={`Quitar horario de ${label}`}
                              data-testid={`ambiente-${value}-${block.index}-remove`}
                              className="h-9 w-9 shrink-0 text-[color:var(--institution-danger)]"
                            >
                              <Trash2 size={15} />
                            </Button>
                          </div>
                        ))
                      )}
                    </div>
                  );
                })}
              </div>
            </section>

            <DialogFooter>
              <Button
                type="submit"
                disabled={loading}
                data-testid="ambiente-save-btn"
                className="rounded-sm text-white"
                style={{ backgroundColor: "var(--institution-burgundy)" }}
              >
                {loading ? "Guardando..." : editing ? "Actualizar" : "Crear ambiente"}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      {isSuperAdmin && (
        <div>
          <select
            value={oficinaFiltro}
            onChange={handleOfficeFilter}
            data-testid="ambientes-office-filter"
            aria-label="Filtrar ambientes por oficina"
            className="h-10 w-full max-w-xs rounded-sm border border-input bg-background px-3 text-sm"
          >
            <option value="">Todas las oficinas</option>
            {oficinas.map((oficina) => (
              <option key={oficina.id} value={oficina.id}>
                {oficina.nombre}
              </option>
            ))}
          </select>
        </div>
      )}

      <div
        className="overflow-x-auto bg-white border rounded-sm"
        style={{ borderColor: "var(--institution-border)" }}
      >
        <Table>
          <TableHeader>
            <TableRow style={{ backgroundColor: "var(--institution-cream)" }}>
              <TableHead className="uppercase text-[10px] tracking-widest text-[color:var(--institution-muted)]">
                Ambiente
              </TableHead>
              <TableHead className="min-w-[350px] uppercase text-[10px] tracking-widest text-[color:var(--institution-muted)]">
                Horarios semanales
              </TableHead>
              <TableHead className="uppercase text-[10px] tracking-widest text-[color:var(--institution-muted)]">
                Descripción
              </TableHead>
              {isSuperAdmin && (
                <TableHead className="uppercase text-[10px] tracking-widest text-[color:var(--institution-muted)]">
                  Oficina
                </TableHead>
              )}
              <TableHead className="text-right uppercase text-[10px] tracking-widest text-[color:var(--institution-muted)]">
                Acciones
              </TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {ambientes.map((ambiente) => (
              <TableRow key={ambiente.id} data-testid={`ambiente-row-${ambiente.id}`}>
                <TableCell className="font-medium">{ambiente.nombre}</TableCell>
                <TableCell className="text-xs leading-5">
                  <span className="inline-flex items-start gap-2">
                    <Clock3
                      size={14}
                      className="mt-0.5 shrink-0 text-[color:var(--institution-muted)]"
                    />
                    <span>{summarizeSchedule(ambiente.horarios)}</span>
                  </span>
                </TableCell>
                <TableCell className="text-xs text-[color:var(--institution-muted)] max-w-xs">
                  {ambiente.descripcion || "—"}
                </TableCell>
                {isSuperAdmin && (
                  <TableCell>{ambiente.office_nombre || "—"}</TableCell>
                )}
                <TableCell className="text-right whitespace-nowrap">
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => handleEdit(ambiente)}
                    data-testid={`ambiente-edit-${ambiente.id}`}
                    aria-label={`Editar ${ambiente.nombre}`}
                    className="rounded-sm"
                  >
                    <Pencil size={14} />
                  </Button>
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => handleDelete(ambiente)}
                    data-testid={`ambiente-delete-${ambiente.id}`}
                    aria-label={`Eliminar ${ambiente.nombre}`}
                    className="rounded-sm text-[color:var(--institution-danger)]"
                  >
                    <Trash2 size={14} />
                  </Button>
                </TableCell>
              </TableRow>
            ))}
            {ambientes.length === 0 && (
              <TableRow>
                <TableCell
                  colSpan={isSuperAdmin ? 5 : 4}
                  className="text-center py-12 text-sm text-[color:var(--institution-muted)]"
                >
                  No hay ambientes registrados para esta oficina.
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