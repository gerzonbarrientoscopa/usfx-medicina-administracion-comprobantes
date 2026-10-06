import React, { useCallback, useEffect, useState } from "react";
import { apiClient, formatApiError, formatMoney } from "@/lib/api";
import { toISODate } from "@/lib/dateFormat";
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
  codigo: "",
  nombre: "",
  id_clasificador: "",
  monto: "",
  descripcion: "",
  inicio: "",
  fin: "",
  office_id: "",
};
const PAGE_SIZE = 20;

export default function ConceptosRecaudacionPage() {
  const { user } = useAuth();
  const isSuperAdmin = user?.rol === "SuperAdmin";
  const [conceptos, setConceptos] = useState([]);
  const [oficinas, setOficinas] = useState([]);
  const [clasificadores, setClasificadores] = useState([]);
  const [oficinaFiltro, setOficinaFiltro] = useState("");
  const [open, setOpen] = useState(false);
  const [editingConcepto, setEditingConcepto] = useState(null);
  const [formData, setFormData] = useState({ ...EMPTY });
  const [loading, setLoading] = useState(false);
  const [pagina, setPagina] = useState(1);
  const [totalPaginas, setTotalPaginas] = useState(1);

  useEffect(() => {
    const fetchClasificadores = async () => {
      try {
        const first = await apiClient.get("/clasificadores-presupuestarios", {
          params: { pag: 1, tam: 100 },
        });
        const rest = await Promise.all(
          Array.from({ length: Math.max(0, (first.data.pages || 1) - 1) }, (_, i) =>
            apiClient.get("/clasificadores-presupuestarios", {
              params: { pag: i + 2, tam: 100 },
            }),
          ),
        );
        setClasificadores([
          ...first.data.items,
          ...rest.flatMap((response) => response.data.items),
        ]);
      } catch (error) {
        toast.error("No se pudieron cargar los clasificadores presupuestarios.");
      }
    };
    fetchClasificadores();
  }, []);

  useEffect(() => {
    if (!isSuperAdmin) return;
    const fetchOficinas = async () => {
      try {
        const first = await apiClient.get("/oficinas", {
          params: { pag: 1, tam: 100 },
        });
        const rest = await Promise.all(
          Array.from({ length: Math.max(0, (first.data.pages || 1) - 1) }, (_, i) =>
            apiClient.get("/oficinas", {
              params: { pag: i + 2, tam: 100 },
            }),
          ),
        );
        setOficinas([
          ...first.data.items,
          ...rest.flatMap((response) => response.data.items),
        ]);
      } catch {
        toast.error("No se pudieron cargar las oficinas.");
      }
    };
    fetchOficinas();
  }, [isSuperAdmin]);

  const fetchConceptos = useCallback(async () => {
    try {
      const response = await apiClient.get("/conceptos-recaudacion", {
        params: {
          pag: pagina,
          tam: PAGE_SIZE,
          office_id: isSuperAdmin ? oficinaFiltro || undefined : undefined,
        },
      });
      setConceptos(response.data.items || []);
      setTotalPaginas(response.data.pages || 1);
    } catch {
      toast.error("No se pudieron cargar los conceptos de recaudación.");
    }
  }, [pagina, oficinaFiltro, isSuperAdmin]);

  useEffect(() => {
    fetchConceptos();
  }, [fetchConceptos]);

  const handleSubmit = async (event) => {
    event.preventDefault();
    const selectedClassifier = clasificadores.find(
      (item) => String(item.id) === String(formData.id_clasificador),
    );
    if (!selectedClassifier?.activa) {
      toast.error("Seleccione un clasificador presupuestario activo.");
      return;
    }
    if (!/^\d{5}$/.test(formData.codigo)) {
      toast.error("El código del concepto debe tener cinco dígitos.");
      return;
    }
    setLoading(true);
    try {
      const payload = {
        ...formData,
        codigo: formData.codigo.trim(),
        id_clasificador: String(formData.id_clasificador),
        monto: Number(formData.monto),
        fin: formData.fin || null,
      };
      if (editingConcepto || !isSuperAdmin) delete payload.office_id;
      if (editingConcepto) {
        await apiClient.put(
          `/conceptos-recaudacion/${editingConcepto.id}`,
          payload,
        );
        toast.success("Concepto actualizado.");
      } else {
        await apiClient.post("/conceptos-recaudacion", payload);
        toast.success("Concepto creado.");
      }
      setOpen(false);
      setEditingConcepto(null);
      await fetchConceptos();
    } catch (error) {
      toast.error(formatApiError(error));
    } finally {
      setLoading(false);
    }
  };

  const handleEdit = (concepto) => {
    setEditingConcepto(concepto);
    setFormData({
      codigo: concepto.codigo || "",
      nombre: concepto.nombre,
      id_clasificador: concepto.id_clasificador
        ? String(concepto.id_clasificador)
        : "",
      monto: concepto.monto,
      descripcion: concepto.descripcion || "",
      inicio: toISODate(concepto.inicio),
      fin: toISODate(concepto.fin) || "",
      office_id: "",
    });
    setOpen(true);
  };

  const handleOpenChange = (isOpen) => {
    setOpen(isOpen);
    if (!isOpen) {
      setEditingConcepto(null);
      return;
    }
    if (!editingConcepto) {
      setFormData({
        ...EMPTY,
        office_id: isSuperAdmin ? oficinaFiltro : "",
      });
    }
  };

  const handleDelete = async (concepto) => {
    if (!window.confirm(`¿Eliminar "${concepto.nombre}"?`)) return;
    try {
      await apiClient.delete(`/conceptos-recaudacion/${concepto.id}`);
      toast.success("Concepto eliminado.");
      await fetchConceptos();
    } catch (error) {
      toast.error(formatApiError(error));
    }
  };

  const selectedInactiveClassifier = clasificadores.find(
    (item) =>
      String(item.id) === String(formData.id_clasificador) && !item.activa,
  );
  const emptyColumns = isSuperAdmin ? 8 : 7;

  return (
    <div className="space-y-6" data-testid="conceptos-recaudacion-page">
      <div className="flex items-end justify-between gap-4">
        <div>
          <div className="section-eyebrow">Catálogo por oficina</div>
          <h1 className="font-serif-display text-4xl mt-1">
            Conceptos de recaudación
          </h1>
          <p className="text-sm text-[color:var(--institution-muted)] mt-1">
            Cada concepto pertenece a una oficina; los clasificadores se comparten entre todas.
          </p>
          {!isSuperAdmin && user?.office_nombre && (
            <p className="text-xs text-[color:var(--institution-muted)] mt-1">
              Oficina: <b>{user.office_nombre}</b>
            </p>
          )}
        </div>
        <Dialog open={open} onOpenChange={handleOpenChange}>
          <DialogTrigger asChild>
            <Button
              data-testid="new-concepto-btn"
              className="rounded-sm text-white"
              style={{ backgroundColor: "var(--institution-burgundy)" }}
            >
              <Plus size={16} className="mr-1" /> Nuevo concepto
            </Button>
          </DialogTrigger>
          <DialogContent className="rounded-sm max-w-xl">
            <DialogHeader>
              <DialogTitle className="font-serif-display text-2xl">
                {editingConcepto ? "Editar concepto" : "Nuevo concepto"}
              </DialogTitle>
            </DialogHeader>
            <form onSubmit={handleSubmit} className="grid grid-cols-2 gap-4">
              {isSuperAdmin && !editingConcepto && (
                <div className="space-y-1.5 col-span-2">
                  <Label>Oficina</Label>
                  <select
                    value={formData.office_id}
                    onChange={(event) =>
                      setFormData({ ...formData, office_id: event.target.value })
                    }
                    required
                    data-testid="concepto-office-select"
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
              )}
              {!isSuperAdmin && !editingConcepto && user?.office_nombre && (
                <div className="col-span-2 text-sm text-[color:var(--institution-muted)]">
                  Oficina: <b>{user.office_nombre}</b>
                </div>
              )}
              <div className="space-y-1.5">
                <Label htmlFor="concepto-codigo">Código (5 dígitos)</Label>
                <Input
                  id="concepto-codigo"
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
                  placeholder="10001"
                  required
                  data-testid="concepto-codigo-input"
                  className="rounded-sm"
                />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="concepto-monto">Monto (Bs.)</Label>
                <Input
                  id="concepto-monto"
                  type="number"
                  min="0"
                  step="0.01"
                  value={formData.monto}
                  onChange={(event) =>
                    setFormData({ ...formData, monto: event.target.value })
                  }
                  required
                  className="rounded-sm"
                />
              </div>
              <div className="space-y-1.5 col-span-2">
                <Label htmlFor="concepto-nombre">Nombre</Label>
                <Input
                  id="concepto-nombre"
                  value={formData.nombre}
                  onChange={(event) =>
                    setFormData({ ...formData, nombre: event.target.value })
                  }
                  required
                  data-testid="concepto-nombre-input"
                  className="rounded-sm"
                />
              </div>
              <div className="space-y-1.5 col-span-2">
                <Label htmlFor="concepto-clasificador">
                  Clasificador presupuestario (obligatorio)
                </Label>
                <select
                  id="concepto-clasificador"
                  value={formData.id_clasificador}
                  onChange={(event) =>
                    setFormData({
                      ...formData,
                      id_clasificador: event.target.value,
                    })
                  }
                  required
                  data-testid="concepto-clasificador-select"
                  className="h-10 w-full rounded-sm border border-input bg-background px-3 text-sm"
                >
                  <option value="">Seleccione un clasificador activo</option>
                  {selectedInactiveClassifier && (
                    <option
                      value={String(selectedInactiveClassifier.id)}
                      disabled
                    >
                      {selectedInactiveClassifier.codigo} — {selectedInactiveClassifier.nombre} (Inactivo; seleccione otro)
                    </option>
                  )}
                  {clasificadores
                    .filter((item) => item.activa)
                    .map((item) => (
                      <option key={item.id} value={String(item.id)}>
                        {item.codigo} — {item.nombre}
                      </option>
                    ))}
                </select>
              </div>
              <div className="space-y-1.5 col-span-2">
                <Label htmlFor="concepto-descripcion">Descripción</Label>
                <Textarea
                  id="concepto-descripcion"
                  value={formData.descripcion}
                  onChange={(event) =>
                    setFormData({
                      ...formData,
                      descripcion: event.target.value,
                    })
                  }
                  rows={2}
                  className="rounded-sm"
                />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="concepto-inicio">Inicio</Label>
                <Input
                  id="concepto-inicio"
                  type="date"
                  value={formData.inicio}
                  onChange={(event) =>
                    setFormData({ ...formData, inicio: event.target.value })
                  }
                  required
                  className="rounded-sm"
                />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="concepto-fin">Fin (opcional)</Label>
                <Input
                  id="concepto-fin"
                  type="date"
                  value={formData.fin}
                  onChange={(event) =>
                    setFormData({ ...formData, fin: event.target.value })
                  }
                  className="rounded-sm"
                />
              </div>
              <DialogFooter className="col-span-2">
                <Button
                  type="submit"
                  disabled={loading}
                  data-testid="concepto-save-btn"
                  className="rounded-sm text-white"
                  style={{ backgroundColor: "var(--institution-burgundy)" }}
                >
                  {editingConcepto ? "Actualizar" : "Crear"}
                </Button>
              </DialogFooter>
            </form>
          </DialogContent>
        </Dialog>
      </div>

      {isSuperAdmin && (
        <select
          value={oficinaFiltro}
          onChange={(event) => {
            setOficinaFiltro(event.target.value);
            setPagina(1);
          }}
          data-testid="conceptos-office-filter"
          aria-label="Filtrar conceptos por oficina"
          className="h-10 w-full max-w-xs rounded-sm border border-input bg-background px-3 text-sm"
        >
          <option value="">Todas las oficinas</option>
          {oficinas.map((oficina) => (
            <option key={oficina.id} value={oficina.id}>
              {oficina.nombre}
            </option>
          ))}
        </select>
      )}

      <div className="bg-white border rounded-sm overflow-x-auto" style={{ borderColor: "var(--institution-border)" }}>
        <Table>
          <TableHeader>
            <TableRow style={{ backgroundColor: "var(--institution-cream)" }}>
              {["Código", "Concepto", "Clasificador", "Monto (Bs.)", "Vigencia", "Descripción"].map((title) => (
                <TableHead key={title} className="uppercase text-[10px] tracking-widest text-[color:var(--institution-muted)]">
                  {title}
                </TableHead>
              ))}
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
            {conceptos.map((concepto) => (
              <TableRow key={concepto.id} data-testid={`concepto-row-${concepto.id}`}>
                <TableCell className="font-mono">{concepto.codigo || "—"}</TableCell>
                <TableCell className="font-medium">{concepto.nombre}</TableCell>
                <TableCell className="text-xs">
                  {concepto.clasificador_codigo
                    ? `${concepto.clasificador_codigo} — ${concepto.clasificador_nombre}${concepto.clasificador_activa === false ? " (Inactivo)" : ""}`
                    : "Pendiente de clasificar"}
                </TableCell>
                <TableCell className="text-right font-mono-num">{formatMoney(concepto.monto)}</TableCell>
                <TableCell className="text-xs">{concepto.inicio} → {concepto.fin || "—"}</TableCell>
                <TableCell className="text-xs text-[color:var(--institution-muted)] max-w-xs truncate">{concepto.descripcion || "—"}</TableCell>
                {isSuperAdmin && <TableCell>{concepto.office_nombre || "—"}</TableCell>}
                <TableCell className="text-right whitespace-nowrap">
                  <Button variant="ghost" size="sm" onClick={() => handleEdit(concepto)} aria-label={`Editar ${concepto.nombre}`} data-testid={`concepto-edit-${concepto.id}`} className="rounded-sm">
                    <Pencil size={14} />
                  </Button>
                  <Button variant="ghost" size="sm" onClick={() => handleDelete(concepto)} aria-label={`Eliminar ${concepto.nombre}`} data-testid={`concepto-delete-${concepto.id}`} className="rounded-sm text-[color:var(--institution-danger)]">
                    <Trash2 size={14} />
                  </Button>
                </TableCell>
              </TableRow>
            ))}
            {conceptos.length === 0 && (
              <TableRow>
                <TableCell colSpan={emptyColumns} className="text-center py-12 text-sm text-[color:var(--institution-muted)]">
                  No hay conceptos registrados.
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
