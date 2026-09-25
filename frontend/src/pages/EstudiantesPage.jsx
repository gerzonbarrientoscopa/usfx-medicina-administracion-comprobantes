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
import { Plus, Pencil, Trash2, ChevronLeft, ChevronRight } from "lucide-react";

const EMPTY = {  
  ci: "",
  cu: "",
  nombre: "",
  gestion: new Date().getFullYear(),
};

export default function EstudiantesPage() {
    const { user } = useAuth();
    const isSuperAdmin = user?.rol === "SuperAdmin";
    const [estudiantes, setEstudiantes] = useState([]);
    const [oficinas, setOficinas] = useState([]);
    const [oficinaFiltro, setOficinaFiltro] = useState("");
    const [textoBuscar, setTextoBuscar] = useState("");
    const [open, setOpen] = useState(false);
    const [editingEstudiante, setEditingEstudiante] = useState(null);
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

    const fetchEstudiantes = useCallback(async () => {
      try {
        const response = await apiClient.get("/estudiantes", {
          params: {
            pag: pagina,
            tam: FILAS_POR_PAGINA,
            textoBuscar: textoBuscar || undefined,
            office_id: isSuperAdmin ? oficinaFiltro || undefined : undefined,
          },
        });
        setEstudiantes(response.data.items);
        if (response.data.pages) {
          setTotalPaginas(response.data.pages);
        }
      } catch (error) {
        toast.error("Error al cargar estudiantes.");
      }
    }, [pagina, textoBuscar, oficinaFiltro, isSuperAdmin]);

    useEffect(() => {
        fetchEstudiantes();
    }, [fetchEstudiantes]);

    const handleSubmit = async (ev) => {
      ev.preventDefault();
      setLoading(true);
      try {
        const payloadFormData = {
          ...formData,
          gestion: Number(formData.gestion),
        };
        if (editingEstudiante || !isSuperAdmin) {
          delete payloadFormData.office_id;
        }
        if (editingEstudiante) {
          await apiClient.put(
            `/estudiantes/${editingEstudiante.id}`,
            payloadFormData,
          );
          toast.success("Estudiante actualizado.");
        } else {
          await apiClient.post("/estudiantes", payloadFormData);
          toast.success("Estudiante creado.");
        }
        setOpen(false);
        fetchEstudiantes();
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

    const handleDelete = async (est) => {
        if (!window.confirm(`¿Eliminar a "${est.nombre}"?`)) return;
        try {
            await apiClient.delete(`/estudiantes/${est.id}`);
            toast.success("Estudiante eliminado.");
            fetchEstudiantes();
        } catch (err) {
            toast.error(formatApiError(err));
        }
    };

    const handleEdit = (est) => {
      setEditingEstudiante(est);
      setFormData({
        ci: est.ci,
        cu: est.cu || "",
        nombre: est.nombre,
        gestion: est.gestion,
        office_id: "",
      });
      setOpen(true);
    };

    const handleOpenChange = (isOpen) => {
      setOpen(isOpen);
      if (!isOpen) {
        setEditingEstudiante(null);
        return;
      }
      // Si la ventana se está abriendo, reseteamos los campos
      if (isOpen && !editingEstudiante) {
        setEditingEstudiante(null);
        setFormData({
          ...EMPTY,
          office_id: isSuperAdmin ? oficinaFiltro : "",
        });
      }
    };     
    
    const handleBuscar = (e) => {
      setTextoBuscar(e.target.value); // 1. Actualiza el texto con lo que escribe el usuario
      setPagina(1); // 2. Reinicia la paginación a la página 1
    };

    const handleOficinaFiltro = (e) => {
      setOficinaFiltro(e.target.value);
      setPagina(1);
    };

    return (
      <div className="space-y-6" data-testid="estudiantes-page">
        <div className="flex items-end justify-between">
          <div>
            <div className="section-eyebrow">Lista estudiantes</div>
            <h1 className="font-serif-display text-4xl mt-1">Estudiantes</h1>
            <p className="text-sm text-[color:var(--institution-muted)] mt-1">
              Registro de estudiantes habilitados para realizar pagos.
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
                  {editingEstudiante ? "Editar estudiante" : "Nuevo estudiante"}
                </DialogTitle>
              </DialogHeader>
              <form
                onSubmit={handleSubmit}
                className="grid grid-cols-2 gap-4"
                data-testid="estudiante-form"
              >
                {isSuperAdmin && !editingEstudiante && (
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
                      data-testid="est-office-select"
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
                {!isSuperAdmin && !editingEstudiante && user?.office_nombre && (
                  <div className="col-span-2 text-sm text-[color:var(--institution-muted)]">
                    Oficina: <b>{user.office_nombre}</b>
                  </div>
                )}
                <div className="space-y-1.5">
                  <Label className="text-xs uppercase tracking-widest text-[color:var(--institution-muted)]">
                    Gestión
                  </Label>
                  <Input
                    type="number"
                    value={formData.gestion}
                    onChange={(e) =>
                      setFormData({ ...formData, gestion: e.target.value })
                    }
                    required
                    data-testid="est-gestion-input"
                    className="rounded-sm"
                  />
                </div>
                <div className="space-y-1.5">
                  <Label className="text-xs uppercase tracking-widest text-[color:var(--institution-muted)]">
                    C.I.
                  </Label>
                  <Input
                    value={formData.ci}
                    onChange={(e) =>
                      setFormData({ ...formData, ci: e.target.value })
                    }
                    required
                    data-testid="est-ci-input"
                    className="rounded-sm"
                  />
                </div>
                <div className="space-y-1.5">
                  <Label className="text-xs uppercase tracking-widest text-[color:var(--institution-muted)]">
                    C.U.
                  </Label>
                  <Input
                    value={formData.cu}
                    onChange={(e) =>
                      setFormData({ ...formData, cu: e.target.value })
                    }
                    data-testid="est-cu-input"
                    className="rounded-sm"
                  />
                </div>
                <div className="space-y-1.5 col-span-2">
                  <Label className="text-xs uppercase tracking-widest text-[color:var(--institution-muted)]">
                    Nombre completo
                  </Label>
                  <Input
                    value={formData.nombre}
                    onChange={(e) =>
                      setFormData({ ...formData, nombre: e.target.value })
                    }
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
                    {editingEstudiante ? "Actualizar" : "Crear"}
                  </Button>
                </DialogFooter>
              </form>
            </DialogContent>
          </Dialog>
        </div>

        <div className="flex gap-3">
          <Input
            placeholder="Buscar por nombre, CI o CU"
            value={textoBuscar}
            onChange={handleBuscar}
            className="max-w-md rounded-sm"
            data-testid="estudiantes-search"
          />
          {isSuperAdmin && (
            <select
              value={oficinaFiltro}
              onChange={handleOficinaFiltro}
              data-testid="estudiantes-office-filter"
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
          )}
        </div>

        <div
          className="bg-white border rounded-sm"
          style={{ borderColor: "var(--institution-border)" }}
        >
          <Table>
            <TableHeader>
              <TableRow style={{ backgroundColor: "var(--institution-cream)" }}>
                <TableHead className="uppercase text-[10px] tracking-widest text-[color:var(--institution-muted)]">
                  C.I.
                </TableHead>
                <TableHead className="uppercase text-[10px] tracking-widest text-[color:var(--institution-muted)]">
                  C.U.
                </TableHead>
                <TableHead className="uppercase text-[10px] tracking-widest text-[color:var(--institution-muted)]">
                  Nombre
                </TableHead>
                <TableHead className="uppercase text-[10px] tracking-widest text-[color:var(--institution-muted)]">
                  Gestión
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
              {estudiantes.map((est) => (
                <TableRow key={est.id} data-testid={`est-row-${est.id}`}>
                  <TableCell className="font-mono-num">{est.ci}</TableCell>
                  <TableCell className="font-mono-num">
                    {est.cu || "—"}
                  </TableCell>
                  <TableCell className="font-medium">{est.nombre}</TableCell>
                  <TableCell className="font-mono-num">{est.gestion}</TableCell>
                  {isSuperAdmin && <TableCell>{est.office_nombre || "—"}</TableCell>}
                  <TableCell className="text-right">
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => handleEdit(est)}
                      data-testid={`est-edit-${est.id}`}
                      className="rounded-sm"
                    >
                      <Pencil size={14} />
                    </Button>
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => handleDelete(est)}
                      data-testid={`est-delete-${est.id}`}
                      className="rounded-sm text-[color:var(--institution-danger)]"
                    >
                      <Trash2 size={14} />
                    </Button>
                  </TableCell>
                </TableRow>
              ))}
              {estudiantes.length === 0 && (
                <TableRow>
                  <TableCell
                    colSpan={isSuperAdmin ? 6 : 5}
                    className="text-center py-12 text-sm text-[color:var(--institution-muted)]"
                  >
                    Sin estudiantes registrados.
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
