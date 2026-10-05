import React, { useCallback, useEffect, useState } from "react";
import { apiClient, formatApiError } from "@/lib/api";
import { toast } from "sonner";
import { ImportSelection } from "@/components/ImportSelection";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Plus, Pencil, Trash2 } from "lucide-react";

const EMPTY = { ci: "", cu: "", nombre: "" };
const SIZE = 20;

export default function ClientesPage() {
  const [rows, setRows] = useState([]);
  const [query, setQuery] = useState("");
  const [page, setPage] = useState(1);
  const [pages, setPages] = useState(1);
  const [total, setTotal] = useState(0);
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState(null);
  const [form, setForm] = useState({ ...EMPTY });
  const [saving, setSaving] = useState(false);
  const [loading, setLoading] = useState(false);
  const load = useCallback(async () => {
    setLoading(true);
    try {
      const { data } = await apiClient.get("/clientes", { params: { pag: page, tam: SIZE, textoBuscar: query } });
      setRows(data.items); setPages(data.pages); setTotal(data.total);
      if (page > data.pages) setPage(data.pages);
    } catch (err) { toast.error(formatApiError(err)); }
    finally { setLoading(false); }
  }, [page, query]);
  useEffect(() => { load(); }, [load]);
  const create = (data = EMPTY) => {
    setEditing(null); setForm({ ci: data.ci || "", cu: data.cu || "", nombre: data.nombre || "" }); setOpen(true);
  };
  const save = async (event) => {
    event.preventDefault(); setSaving(true);
    try {
      const payload = { ci: form.ci.trim(), cu: form.cu.trim(), nombre: form.nombre.trim() };
      if (editing) await apiClient.put(`/clientes/${editing.id}`, payload);
      else await apiClient.post("/clientes", payload);
      toast.success(editing ? "Cliente actualizado." : "Cliente registrado.");
      setOpen(false); await load();
    } catch (err) { toast.error(formatApiError(err)); }
    finally { setSaving(false); }
  };
  const remove = async (row) => {
    if (!window.confirm(`¿Eliminar a "${row.nombre}"?`)) return;
    try {
      await apiClient.delete(`/clientes/${row.id}`);
      toast.success("Cliente eliminado."); await load();
    } catch (err) { toast.error(formatApiError(err)); }
  };
  return <div className="space-y-6" data-testid="clientes-page">
    <div className="flex flex-wrap items-end justify-between gap-4">
      <div>
        <div className="section-eyebrow">Catálogo compartido</div>
        <h1 className="font-serif-display text-4xl mt-1">Clientes</h1>
        <p className="text-sm text-[color:var(--institution-muted)] mt-1">
          Clientes de pagos y alquileres, disponibles para todas las oficinas.
        </p>
      </div>
      <div className="flex gap-2">
        <ImportSelection kind="clientes" onSelect={create} />
        <Button className="rounded-sm text-white" style={{ backgroundColor: "var(--institution-burgundy)" }}
          onClick={() => create()}><Plus size={16} className="mr-1" /> Nuevo cliente</Button>
      </div>
    </div>
    <Input placeholder="Buscar por C.I., C.U. o nombre completo..." aria-label="Buscar clientes" value={query}
      onChange={(event) => { setQuery(event.target.value); setPage(1); }} className="max-w-lg rounded-sm" />
    <div className="border bg-white overflow-x-auto rounded-sm">
      <Table>
        <TableHeader><TableRow>
          <TableHead>Id</TableHead><TableHead>C.I.</TableHead><TableHead>C.U.</TableHead>
          <TableHead>Nombre completo</TableHead><TableHead className="text-right">Acciones</TableHead>
        </TableRow></TableHeader>
        <TableBody>
          {rows.map((row) => <TableRow key={row.id}>
            <TableCell className="font-mono text-xs" title={String(row.id)}>{row.id}</TableCell>
            <TableCell>{row.ci || "—"}</TableCell><TableCell>{row.cu || "—"}</TableCell><TableCell>{row.nombre}</TableCell>
            <TableCell className="text-right whitespace-nowrap">
              <Button variant="ghost" size="icon" aria-label={`Editar ${row.nombre}`}
                onClick={() => { setEditing(row); setForm({ ci: row.ci || "", cu: row.cu || "", nombre: row.nombre }); setOpen(true); }}><Pencil size={16} /></Button>
              <Button variant="ghost" size="icon" aria-label={`Eliminar ${row.nombre}`} onClick={() => remove(row)}><Trash2 size={16} /></Button>
            </TableCell>
          </TableRow>)}
          {!rows.length && <TableRow><TableCell colSpan={5} className="text-center p-8">
            {loading ? "Cargando clientes…" : "No hay clientes para mostrar."}
          </TableCell></TableRow>}
        </TableBody>
      </Table>
    </div>
    <div className="flex items-center justify-between text-sm">
      <span>{total} clientes · Página {page} de {pages}</span>
      <div className="flex gap-2"><Button variant="outline" disabled={page <= 1} onClick={() => setPage(page - 1)}>Anterior</Button>
        <Button variant="outline" disabled={page >= pages} onClick={() => setPage(page + 1)}>Siguiente</Button></div>
    </div>
    <Dialog open={open} onOpenChange={setOpen}><DialogContent className="rounded-sm">
      <DialogHeader><DialogTitle>{editing ? "Editar cliente" : "Nuevo cliente"}</DialogTitle></DialogHeader>
      <form onSubmit={save} className="space-y-4">
        <p className="text-xs text-[color:var(--institution-muted)]">
          {editing ? `Id: ${editing.id}` : "El Id se generará automáticamente al guardar."}
        </p>
        {!editing && <ImportSelection kind="clientes" onSelect={(row) => setForm(row)} />}
        <div className="grid grid-cols-2 gap-4">
          <div className="space-y-1.5"><Label htmlFor="client-ci">C.I.</Label>
            <Input id="client-ci" value={form.ci} maxLength={30} required={!form.cu.trim()}
              onChange={(e) => setForm({ ...form, ci: e.target.value })} /></div>
          <div className="space-y-1.5"><Label htmlFor="client-cu">C.U.</Label>
            <Input id="client-cu" value={form.cu} maxLength={50}
              onChange={(e) => setForm({ ...form, cu: e.target.value })} /></div>
        </div>
        <div className="space-y-1.5"><Label htmlFor="client-name">Nombre completo</Label>
          <Input id="client-name" value={form.nombre} maxLength={200} required
            onChange={(e) => setForm({ ...form, nombre: e.target.value })} /></div>
        <DialogFooter><Button type="submit" disabled={saving}>{saving ? "Guardando…" : "Guardar cliente"}</Button></DialogFooter>
      </form>
    </DialogContent></Dialog>
  </div>;
}
