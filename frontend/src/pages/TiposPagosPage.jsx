import React, { useCallback, useEffect, useState } from "react";
import { apiClient, formatApiError, formatMoney } from "@/lib/api";
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
  nombre: "",
  monto: "",
  descripcion: "",
  inicio: "",
  fin: "",
};

export default function TiposPagosPage() {
  const { user } = useAuth();
  const isSuperAdmin = user?.rol === "SuperAdmin";
  const [tiposPagos, setTiposPagos] = useState([]);
  const [oficinas, setOficinas] = useState([]);
  const [oficinaFiltro, setOficinaFiltro] = useState("");
  const [open, setOpen] = useState(false);
  const [editingTipo, setEditingTipo] = useState(null);
  const [formData, setFormData] = useState({ ...EMPTY, office_id: "" });
  const [loading, setLoading] = useState(false);
  const [pagina, setPagina] = useState(1);
  const [totalPaginas, setTotalPaginas] = useState(1);
  const FILAS_POR_PAGINA = 20; 

  useEffect(() => {
    if (!isSuperAdmin) return;
    const fetchOficinas = async () => {
      try {
        const firstResponse = await apiClient.get("/oficinas", {
          params: { pag: 1, tam: 100 },
        });
        const paginas = firstResponse.data.pages || 1;
        const remainingResponses = await Promise.all(
          Array.from({ length: paginas - 1 }, (_, index) =>
            apiClient.get("/oficinas", {
              params: { pag: index + 2, tam: 100 },
            }),
          ),
        );
        setOficinas([
          ...firstResponse.data.items,
          ...remainingResponses.flatMap((response) => response.data.items),
        ]);
      } catch (error) {
        toast.error("Error al cargar oficinas.");
      }
    };
    fetchOficinas();
  }, [isSuperAdmin]);

  const fetchTiposPago = useCallback(async () => {
    try {
      const response = await apiClient.get("/tipos-pagos", {
        params: {
          pag: pagina,
          tam: FILAS_POR_PAGINA,
          office_id: isSuperAdmin ? oficinaFiltro || undefined : undefined,
        },
      });
      setTiposPagos(response.data.items);
      if (response.data.pages) {
        setTotalPaginas(response.data.pages);
      }
    } catch (error) {
      toast.error("Error al cargar tipos de pagos.");
    }
  }, [pagina, oficinaFiltro, isSuperAdmin]);

  useEffect(() => {
    fetchTiposPago();
  }, [fetchTiposPago]);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setLoading(true);
    try {
      const payloadFormData = {
        ...formData,
        monto: Number(formData.monto),
        fin: formData.fin || null,
      };
      if (editingTipo || !isSuperAdmin) {
        delete payloadFormData.office_id;
      }
      if (editingTipo) {
        await apiClient.put(`/tipos-pagos/${editingTipo.id}`, payloadFormData);
        toast.success("Tipo de pago actualizado.");
      } else {
        await apiClient.post("/tipos-pagos", payloadFormData);
        toast.success("Tipo de pago creado.");
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

  const handleDelete = async (tipo) => {
    if (!window.confirm(`¿Eliminar "${tipo.nombre}"?`)) return;
    try {
      await apiClient.delete(`/tipos-pagos/${tipo.id}`);
      toast.success("Tipo de pago eliminado.");
      fetchTiposPago();
    } catch (err) {
      toast.error(formatApiError(err));
    }
  };

  const handleEdit = (tipo) => {
    setEditingTipo(tipo);
    setFormData({
      nombre: tipo.nombre,
      monto: tipo.monto,
      descripcion: tipo.descripcion || "",
      inicio: tipo.inicio,
      fin: tipo.fin || "",
      office_id: "",
    });
    setOpen(true);
  };

  const handleOpenChange = (isOpen) => {
    setOpen(isOpen);
    if (!isOpen) {
      setEditingTipo(null);
      return;
    }
    // Si la ventana se está abriendo, reseteamos los campos
    if (isOpen && !editingTipo) {
      setEditingTipo(null);
      setFormData({
        ...EMPTY,
        office_id: isSuperAdmin ? oficinaFiltro : "",
      });
    }
  }; 

  const handleOficinaFiltro = (e) => {
    setOficinaFiltro(e.target.value);
    setPagina(1);
  };

  return (
    <div className="space-y-6" data-testid="tipospagos-page">
      <div className="flex items-end justify-between">
        <div>
          <div className="section-eyebrow">Catálogo Tipos de Pagos</div>
          <h1 className="font-serif-display text-4xl mt-1">Tipos de Pago</h1>
          <p className="text-sm text-[color:var(--institution-muted)] mt-1">
            Conceptos por los cuales se pueden emitir comprobantes.
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
                {editingTipo ? "Editar Tipo de Pago" : "Nuevo Tipo de Pago"}
              </DialogTitle>
            </DialogHeader>
            <form onSubmit={handleSubmit} className="grid grid-cols-2 gap-4">
              {isSuperAdmin && !editingTipo && (
                <div className="space-y-1.5 col-span-2">
                  <Label className="text-xs uppercase tracking-widest text-[color:var(--institution-muted)]">
                    Oficina
                  </Label>
                  <select
                    value={formData.office_id}
                    onChange={(e) =>
                      setFormData({ ...formData, office_id: e.target.value })
                    }
                    required
                    data-testid="tp-office-select"
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
              {!isSuperAdmin && !editingTipo && user?.office_nombre && (
                <div className="col-span-2 text-sm text-[color:var(--institution-muted)]">
                  Oficina: <b>{user.office_nombre}</b>
                </div>
              )}
              <div className="space-y-1.5">
                <Label className="text-xs uppercase tracking-widest text-[color:var(--institution-muted)]">
                  Monto (Bs.)
                </Label>
                <Input
                  type="number"
                  step="0.01"
                  value={formData.monto}
                  onChange={(e) =>
                    setFormData({ ...formData, monto: e.target.value })
                  }
                  required
                  data-testid="tp-monto-input"
                  className="rounded-sm"
                />
              </div>
              <div className="space-y-1.5 col-span-2">
                <Label className="text-xs uppercase tracking-widest text-[color:var(--institution-muted)]">
                  Nombre
                </Label>
                <Input
                  value={formData.nombre}
                  onChange={(e) =>
                    setFormData({ ...formData, nombre: e.target.value })
                  }
                  required
                  data-testid="tp-nombre-input"
                  className="rounded-sm"
                />
              </div>
              <div className="space-y-1.5 col-span-2">
                <Label className="text-xs uppercase tracking-widest text-[color:var(--institution-muted)]">
                  Descripción
                </Label>
                <Textarea
                  value={formData.descripcion}
                  onChange={(e) =>
                    setFormData({ ...formData, descripcion: e.target.value })
                  }
                  rows={2}
                  data-testid="tp-desc-input"
                  className="rounded-sm"
                />
              </div>
              <div className="space-y-1.5">
                <Label className="text-xs uppercase tracking-widest text-[color:var(--institution-muted)]">
                  Inicio
                </Label>
                <Input
                  type="date"
                  value={formData.inicio}
                  onChange={(e) =>
                    setFormData({ ...formData, inicio: e.target.value })
                  }
                  required
                  data-testid="tp-inicio-input"
                  className="rounded-sm"
                />
              </div>
              <div className="space-y-1.5">
                <Label className="text-xs uppercase tracking-widest text-[color:var(--institution-muted)]">
                  Fin (opcional)
                </Label>
                <Input
                  type="date"
                  value={formData.fin}
                  onChange={(e) =>
                    setFormData({ ...formData, fin: e.target.value })
                  }
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
                  {editingTipo ? "Actualizar" : "Crear"}
                </Button>
              </DialogFooter>
            </form>
          </DialogContent>
        </Dialog>
      </div>

      {isSuperAdmin && (
        <div className="flex gap-3">
          <select
            value={oficinaFiltro}
            onChange={handleOficinaFiltro}
            data-testid="tipos-pagos-office-filter"
            aria-label="Filtrar por oficina"
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
        className="bg-white border rounded-sm"
        style={{ borderColor: "var(--institution-border)" }}
      >
        <Table>
          <TableHeader>
            <TableRow style={{ backgroundColor: "var(--institution-cream)" }}>
              <TableHead className="uppercase text-[10px] tracking-widest text-[color:var(--institution-muted)]">
                Código
              </TableHead>
              <TableHead className="uppercase text-[10px] tracking-widest text-[color:var(--institution-muted)]">
                Nombre
              </TableHead>
              <TableHead className="text-right uppercase text-[10px] tracking-widest text-[color:var(--institution-muted)]">
                Monto (Bs.)
              </TableHead>
              <TableHead className="uppercase text-[10px] tracking-widest text-[color:var(--institution-muted)]">
                Vigencia
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
            {tiposPagos.map((tipo) => (
              <TableRow key={tipo.id} data-testid={`tp-row-${tipo.id}`}>
                <TableCell className="font-mono-num">{tipo.id}</TableCell>
                <TableCell className="font-medium">{tipo.nombre}</TableCell>
                <TableCell className="text-right font-mono-num">
                  {formatMoney(tipo.monto)}
                </TableCell>
                <TableCell className="text-xs">
                  {tipo.inicio} → {tipo.fin || "—"}
                </TableCell>
                <TableCell className="text-xs text-[color:var(--institution-muted)] max-w-xs truncate">
                  {tipo.descripcion || "—"}
                </TableCell>
                {isSuperAdmin && <TableCell>{tipo.office_nombre || "—"}</TableCell>}
                <TableCell className="text-right">
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => handleEdit(tipo)}
                    data-testid={`tp-edit-${tipo.id}`}
                    className="rounded-sm"
                  >
                    <Pencil size={14} />
                  </Button>
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => handleDelete(tipo)}
                    data-testid={`tp-delete-${tipo.id}`}
                    className="rounded-sm text-[color:var(--institution-danger)]"
                  >
                    <Trash2 size={14} />
                  </Button>
                </TableCell>
              </TableRow>
            ))}
            {tiposPagos.length === 0 && (
              <TableRow>
                <TableCell
                  colSpan={isSuperAdmin ? 7 : 6}
                  className="text-center py-12 text-sm text-[color:var(--institution-muted)]"
                >
                  Sin tipos de pago registrados.
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
