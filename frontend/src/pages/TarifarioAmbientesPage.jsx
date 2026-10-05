import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { apiClient, formatApiError, formatMoney } from "@/lib/api";
import { useOfficeScope } from "@/hooks/useOfficeScope";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { toast } from "sonner";
import { Plus, Pencil, Trash2, Clock3, RefreshCw } from "lucide-react";

const MODES = [
  ["hora", "Por hora"],
  ["manana", "Mañana"],
  ["tarde", "Tarde"],
  ["noche", "Noche"],
  ["dia", "Día completo"],
  ["actividad", "Actividad"],
];
const SHIFT_MODALITIES = ["manana", "tarde", "noche"];
const blank = { nombre: "", modalidad: "hora", monto: "", descripcion: "", desde: "", hasta: "" };

export default function TarifarioAmbientesPage() {
  const { isSuperAdmin, offices, officeId, officeName, selectedOfficeId, setSelectedOfficeId } = useOfficeScope();
  const [ambientes, setAmbientes] = useState([]);
  const [selected, setSelected] = useState("");
  const [tarifas, setTarifas] = useState([]);
  const [form, setForm] = useState(blank);
  const [editing, setEditing] = useState(null);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const ambienteRequest = useRef(0);
  const tarifaRequest = useRef(0);

  const loadAmbientes = useCallback(async () => {
    const requestId = ++ambienteRequest.current;
    setAmbientes([]);
    setSelected("");
    setTarifas([]);
    tarifaRequest.current += 1;
    setEditing(null);
    setForm(blank);
    if (isSuperAdmin && !officeId) { setLoading(false); return; }
    setLoading(true); setError("");
    try {
      const params = { office_id: officeId || undefined, pag: 1, tam: 100 };
      const { data: first } = await apiClient.get("/ambientes", { params });
      const rest = await Promise.all(Array.from({ length: Math.max(0, (first.pages || 1) - 1) }, (_, index) =>
        apiClient.get("/ambientes", { params: { ...params, pag: index + 2 } }),
      ));
      const items = [...(first.items || []), ...rest.flatMap((response) => response.data.items || [])];
      if (requestId !== ambienteRequest.current) return;
      setAmbientes(items);
      setSelected(String(items[0]?.id || ""));
    } catch (e) {
      if (requestId === ambienteRequest.current) setError(formatApiError(e) || "No se pudieron cargar los ambientes.");
    } finally { if (requestId === ambienteRequest.current) setLoading(false); }
  }, [isSuperAdmin, officeId]);

  const loadTarifas = useCallback(async () => {
    const requestId = ++tarifaRequest.current;
    if (!selected) { setTarifas([]); return; }
    setError("");
    try {
      const { data } = await apiClient.get("/tarifas-ambientes", { params: { ambiente_id: selected } });
      if (requestId === tarifaRequest.current) setTarifas(Array.isArray(data) ? data : []);
    } catch (e) { if (requestId === tarifaRequest.current) setError(formatApiError(e) || "No se pudieron cargar las tarifas."); }
  }, [selected]);

  useEffect(() => { loadAmbientes(); }, [loadAmbientes]);
  useEffect(() => { loadTarifas(); }, [loadTarifas]);

  const activeAmbiente = useMemo(() => ambientes.find((a) => String(a.id) === String(selected)), [ambientes, selected]);
  const selectedShift = activeAmbiente?.turnos?.find((item) => item.turno === form.modalidad);
  const resetForm = () => { setEditing(null); setForm(blank); };
  const submit = async (event) => {
    event.preventDefault();
    if (!selected) return;
    if (SHIFT_MODALITIES.includes(form.modalidad) && (!selectedShift?.desde || !selectedShift?.hasta)) {
      toast.error("Configure primero el horario de ese turno en el ambiente.");
      return;
    }
    setSaving(true);
    const payload = { ambiente_id: selected, nombre: form.nombre.trim(), modalidad: form.modalidad, monto: Number(form.monto), descripcion: form.descripcion.trim() || undefined };
    if (SHIFT_MODALITIES.includes(form.modalidad)) {
      payload.desde = selectedShift.desde;
      payload.hasta = selectedShift.hasta;
    }
    try {
      if (editing) await apiClient.put(`/tarifas-ambientes/${editing.id}`, payload);
      else await apiClient.post("/tarifas-ambientes", payload);
      toast.success(editing ? "Tarifa actualizada." : "Tarifa registrada.");
      resetForm(); await loadTarifas();
    } catch (e) { toast.error(formatApiError(e) || "No se pudo guardar la tarifa."); }
    finally { setSaving(false); }
  };
  const edit = (tarifa) => {
    setEditing(tarifa);
    setForm({ nombre: tarifa.nombre || "", modalidad: tarifa.modalidad, monto: String(tarifa.monto), descripcion: tarifa.descripcion || "", desde: tarifa.desde || "", hasta: tarifa.hasta || "" });
    document.getElementById("tarifa-name")?.focus();
  };
  const remove = async (tarifa) => {
    if (!window.confirm(`¿Eliminar la tarifa “${tarifa.nombre}”?`)) return;
    try { await apiClient.delete(`/tarifas-ambientes/${tarifa.id}`); toast.success("Tarifa eliminada."); await loadTarifas(); }
    catch (e) { toast.error(formatApiError(e) || "No se pudo eliminar la tarifa."); }
  };

  return <div className="space-y-6" data-testid="tarifario-page">
    <header className="flex flex-wrap items-end justify-between gap-4">
      <div><div className="section-eyebrow">Gestión · Espacios</div><h1 className="font-serif-display mt-1 text-4xl">Tarifario de ambientes</h1>
        <p className="mt-1 max-w-2xl text-sm text-[color:var(--institution-muted)]">Tarifas asociadas directamente a cada ambiente, listas para aplicar al reservar.</p>
      </div>
      {isSuperAdmin ? <div className="w-full max-w-xs space-y-1.5"><Label htmlFor="tarifa-office">Oficina</Label><select id="tarifa-office" value={selectedOfficeId} onChange={(e) => setSelectedOfficeId(e.target.value)} className="h-10 w-full rounded-sm border border-input bg-background px-3 text-sm"><option value="">Seleccione una oficina</option>{offices.filter((o) => o.activa).map((o) => <option key={o.id} value={o.id}>{o.nombre}</option>)}</select></div> : <div className="text-xs text-[color:var(--institution-muted)]">Oficina · <b>{officeName || "—"}</b></div>}
    </header>
    <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_380px]">
      <section className="min-w-0 rounded-sm border bg-white" style={{ borderColor: "var(--institution-border)" }}>
        <div className="flex flex-wrap items-center justify-between gap-3 border-b px-5 py-4" style={{ borderColor: "var(--institution-border)", background: "var(--institution-cream)" }}>
          <div><div className="section-eyebrow">Catálogo</div><h2 className="mt-1 font-serif-display text-2xl">{activeAmbiente?.nombre || "Seleccione un ambiente"}</h2></div>
          <div className="flex items-center gap-2">
            <select aria-label="Ambiente" value={selected} onChange={(e) => { setSelected(e.target.value); resetForm(); }} disabled={!ambientes.length} className="h-9 max-w-[220px] rounded-sm border border-input bg-white px-2 text-sm">
              {ambientes.length ? ambientes.map((a) => <option key={a.id} value={a.id}>{a.nombre}</option>) : <option value="">{isSuperAdmin && !officeId ? "Elija oficina" : "Sin ambientes"}</option>}
            </select>
            <Button variant="outline" size="icon" aria-label="Actualizar" onClick={loadTarifas} disabled={!selected}><RefreshCw size={15}/></Button>
          </div>
        </div>
        {loading ? <div className="space-y-3 p-5" aria-label="Cargando ambientes"><div className="h-12 animate-pulse rounded-sm bg-[color:var(--institution-cream)]"/><div className="h-12 animate-pulse rounded-sm bg-[color:var(--institution-cream)]"/></div>
          : error ? <div role="alert" className="m-5 rounded-sm border border-red-200 bg-red-50 p-4 text-sm text-red-900">{error}<Button variant="outline" size="sm" className="ml-3" onClick={() => { loadAmbientes(); loadTarifas(); }}>Reintentar</Button></div>
          : !selected ? <div className="p-12 text-center text-sm text-[color:var(--institution-muted)]">{isSuperAdmin && !officeId ? "Seleccione una oficina para consultar sus ambientes." : "No hay ambientes registrados en esta oficina."}</div>
          : tarifas.length === 0 ? <div className="p-12 text-center"><div className="mx-auto mb-3 flex h-11 w-11 items-center justify-center rounded-full bg-[color:var(--institution-cream)] text-[color:var(--institution-navy)]"><Clock3 size={19}/></div><h3 className="font-medium">Aún no hay tarifas</h3><p className="mt-1 text-sm text-[color:var(--institution-muted)]">Registre una tarifa para habilitar reservas de este ambiente.</p></div>
          : <ul className="divide-y" style={{ borderColor: "var(--institution-border)" }}>{tarifas.map((t) => <li key={t.id} className="flex flex-wrap items-center justify-between gap-3 px-5 py-4 transition-colors hover:bg-[color:var(--institution-cream)]/50">
            <div className="min-w-0"><div className="flex flex-wrap items-center gap-2"><span className="font-medium">{t.nombre}</span><span className="rounded-full border px-2 py-0.5 text-[10px] uppercase tracking-wider text-[color:var(--institution-muted)]">{MODES.find(([v]) => v === t.modalidad)?.[1] || t.modalidad}</span></div><p className="mt-1 text-xs text-[color:var(--institution-muted)]">{t.descripcion || (t.desde && t.hasta ? `${t.desde}–${t.hasta}` : "Sin detalle adicional")}{t.desde && t.hasta && t.descripcion ? ` · ${t.desde}–${t.hasta}` : ""}</p></div>
            <div className="flex items-center gap-3"><span className="whitespace-nowrap font-mono-num text-sm font-semibold" style={{ color: "var(--institution-burgundy)" }}>Bs. {formatMoney(t.monto)}{t.modalidad === "hora" ? <small className="font-sans font-normal text-[color:var(--institution-muted)]"> / h</small> : null}</span><Button variant="ghost" size="icon" aria-label={`Editar ${t.nombre}`} onClick={() => edit(t)}><Pencil size={15}/></Button><Button variant="ghost" size="icon" aria-label={`Eliminar ${t.nombre}`} className="text-[color:var(--institution-danger)]" onClick={() => remove(t)}><Trash2 size={15}/></Button></div>
          </li>)}</ul>}
      </section>
      <aside className="h-fit rounded-sm border bg-white p-5" style={{ borderColor: "var(--institution-border)" }}>
        <div className="section-eyebrow">{editing ? "Edición" : "Nueva tarifa"}</div><h2 className="mt-1 font-serif-display text-2xl">{editing ? "Actualizar tarifa" : "Añadir al catálogo"}</h2>
        <form className="mt-5 space-y-4" onSubmit={submit}>
          <div className="space-y-1.5"><Label htmlFor="tarifa-name">Nombre de tarifa</Label><Input id="tarifa-name" required maxLength={120} value={form.nombre} onChange={(e) => setForm({ ...form, nombre: e.target.value })} className="rounded-sm"/></div>
          <div className="space-y-1.5"><Label htmlFor="tarifa-mode">Modalidad</Label><select id="tarifa-mode" value={form.modalidad} onChange={(e) => setForm({ ...form, modalidad: e.target.value, desde: "", hasta: "" })} className="h-10 w-full rounded-sm border border-input bg-background px-3 text-sm">{MODES.map(([v, label]) => <option key={v} value={v}>{label}</option>)}</select></div>
          {SHIFT_MODALITIES.includes(form.modalidad) && <div className="rounded-sm border p-3 text-sm" style={{ borderColor: "var(--institution-border)", background: "var(--institution-cream)" }}>
            <div className="text-xs uppercase tracking-wider text-[color:var(--institution-muted)]">Horario definido para {MODES.find(([value]) => value === form.modalidad)?.[1]}</div>
            <div className="mt-1 font-medium">{selectedShift?.desde && selectedShift?.hasta
              ? `${selectedShift.desde}–${selectedShift.hasta}`
              : "Configure este turno en el ambiente antes de registrar la tarifa."}</div>
            <p className="mt-1 text-xs text-[color:var(--institution-muted)]">El tarifario usa el horario establecido en la ficha del ambiente.</p>
          </div>}
          <div className="space-y-1.5"><Label htmlFor="tarifa-amount">Monto (Bs.)</Label><Input id="tarifa-amount" type="number" min="0.01" step="0.01" required value={form.monto} onChange={(e) => setForm({ ...form, monto: e.target.value })} className="rounded-sm"/></div>
          <div className="space-y-1.5"><Label htmlFor="tarifa-description">Descripción <span className="font-normal text-[color:var(--institution-muted)]">· opcional</span></Label><Textarea id="tarifa-description" rows={2} maxLength={500} value={form.descripcion} onChange={(e) => setForm({ ...form, descripcion: e.target.value })} className="rounded-sm"/></div>
          {form.modalidad === "hora" && <p className="text-xs text-[color:var(--institution-muted)]">El monto se calcula proporcionalmente al tiempo reservado.</p>}
          <div className="flex gap-2 pt-1"><Button type="submit" disabled={saving || !selected || !officeId && isSuperAdmin} className="flex-1 rounded-sm text-white" style={{ backgroundColor: "var(--institution-burgundy)" }}><Plus size={15} className="mr-2"/>{saving ? "Guardando…" : editing ? "Guardar cambios" : "Registrar tarifa"}</Button>{editing && <Button type="button" variant="outline" onClick={resetForm}>Cancelar</Button>}</div>
        </form>
      </aside>
    </div>
  </div>;
}