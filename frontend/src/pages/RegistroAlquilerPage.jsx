import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { apiClient, formatApiError, formatMoney } from "@/lib/api";
import { formatDate, toISODate } from "@/lib/dateFormat";
import { useOfficeScope } from "@/hooks/useOfficeScope";
import { useAuth } from "@/contexts/AuthContext";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { toast } from "sonner";
import { ChevronLeft, ChevronRight, CalendarDays, Clock3, Search, Check, Printer, RefreshCw, Plus } from "lucide-react";
import { printAlquilerComprobante } from "@/components/AlquilerComprobantePrint";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from "@/components/ui/dialog";

const DAY_NAMES = ["domingo", "lunes", "martes", "miercoles", "jueves", "viernes", "sabado"];
const fmtDate = (date) => `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`;
const parseDate = (value) => { const [y, m, d] = toISODate(value).split("-").map(Number); return new Date(y, m - 1, d, 12); };
const addDays = (date, n) => { const next = new Date(date); next.setDate(next.getDate() + n); return next; };
const prettyDate = (value, options = { weekday: "short", day: "numeric", month: "short" }) => parseDate(value).toLocaleDateString("es-BO", options);
const mins = (value) => { const [h, m] = (value || "00:00").split(":").map(Number); return h * 60 + m; };
const time = (value) => `${String(Math.floor(value / 60)).padStart(2, "0")}:${String(value % 60).padStart(2, "0")}`;
const overlaps = (a, b, c, d) => a < d && c < b;
const SHIFT_MODALITIES = ["manana", "tarde", "noche"];
const SHIFT_LABELS = { manana: "Mañana", tarde: "Tarde", noche: "Noche" };

export default function RegistroAlquilerPage() {
  const { user } = useAuth();
  const { isSuperAdmin, offices, officeId, officeName, selectedOfficeId, setSelectedOfficeId } = useOfficeScope();
  const [ambientes, setAmbientes] = useState([]);
  const [ambienteId, setAmbienteId] = useState("");
  const [tarifas, setTarifas] = useState([]);
  const [tarifaId, setTarifaId] = useState("");
  const [anchor, setAnchor] = useState(() => { const d = new Date(); d.setDate(d.getDate() - ((d.getDay() + 6) % 7)); return fmtDate(d); });
  const dates = useMemo(() => Array.from({ length: 7 }, (_, i) => fmtDate(addDays(parseDate(anchor), i))), [anchor]);
  const [reservas, setReservas] = useState([]);
  const [catalogLoading, setCatalogLoading] = useState(false);
  const [calendarLoading, setCalendarLoading] = useState(false);
  const [calendarError, setCalendarError] = useState("");
  const [customerQuery, setCustomerQuery] = useState("");
  const [customers, setCustomers] = useState([]);
  const [customerLoading, setCustomerLoading] = useState(false);
  const [customerSearchFailed, setCustomerSearchFailed] = useState(false);
  const [customer, setCustomer] = useState(null);
  const [newClientOpen, setNewClientOpen] = useState(false);
  const [newClientForm, setNewClientForm] = useState(() => ({
    ci: "",
    cu: "",
    nombre: "",
  }));
  const [creatingClient, setCreatingClient] = useState(false);
  const [date, setDate] = useState("");
  const [start, setStart] = useState("");
  const [end, setEnd] = useState("");
  const [saving, setSaving] = useState(false);
  const [lastSaved, setLastSaved] = useState(null);
  const ambienteRequest = useRef(0);
  const tarifaRequest = useRef(0);

  const ambiente = useMemo(() => ambientes.find((a) => String(a.id) === String(ambienteId)), [ambientes, ambienteId]);
  const tarifa = useMemo(() => tarifas.find((t) => String(t.id) === String(tarifaId)), [tarifas, tarifaId]);
  const selectedDaySchedule = useMemo(() => {
    if (!ambiente || !date) return [];
    const day = DAY_NAMES[parseDate(date).getDay()];
    return (ambiente.horarios || []).filter((block) => block.dia === day).slice().sort((a, b) => a.desde.localeCompare(b.desde));
  }, [ambiente, date]);
  const isWholeDay = tarifa?.modalidad === "dia";

  const loadAmbientes = useCallback(async () => {
    const requestId = ++ambienteRequest.current;
    setAmbientes([]);
    setAmbienteId("");
    setTarifas([]);
    setTarifaId("");
    setReservas([]);
    setCustomer(null);
    setCustomerQuery("");
    setDate("");
    setStart("");
    setEnd("");
    setLastSaved(null);
    if (isSuperAdmin && !officeId) return;
    setCatalogLoading(true);
    try {
      const params = { office_id: officeId || undefined, pag: 1, tam: 100 };
      const { data: first } = await apiClient.get("/ambientes", { params });
      const rest = await Promise.all(Array.from({ length: Math.max(0, (first.pages || 1) - 1) }, (_, index) =>
        apiClient.get("/ambientes", { params: { ...params, pag: index + 2 } }),
      ));
      const items = [...(first.items || []), ...rest.flatMap((response) => response.data.items || [])];
      if (requestId !== ambienteRequest.current) return;
      setAmbientes(items);
      setAmbienteId(String(items[0]?.id || ""));
    } catch (e) { if (requestId === ambienteRequest.current) toast.error(formatApiError(e) || "No se pudieron cargar los ambientes."); }
    finally { if (requestId === ambienteRequest.current) setCatalogLoading(false); }
  }, [isSuperAdmin, officeId]);
  useEffect(() => { loadAmbientes(); }, [loadAmbientes]);

  useEffect(() => {
    const requestId = ++tarifaRequest.current;
    let cancelled = false;
    const load = async () => {
      if (!ambienteId) { setTarifas([]); setTarifaId(""); return; }
      try {
        const { data } = await apiClient.get("/tarifas-ambientes", { params: { ambiente_id: ambienteId } });
        if (cancelled || requestId !== tarifaRequest.current) return;
        const list = Array.isArray(data) ? data : [];
        setTarifas(list); setTarifaId(String(list[0]?.id || ""));
      } catch (e) { if (!cancelled && requestId === tarifaRequest.current) { setTarifas([]); setTarifaId(""); toast.error(formatApiError(e) || "No se pudieron cargar las tarifas."); } }
    };
    load(); return () => { cancelled = true; };
  }, [ambienteId]);

  const loadCalendar = useCallback(async () => {
    if (!ambienteId || (isSuperAdmin && !officeId)) { setReservas([]); return; }
    setCalendarLoading(true); setCalendarError("");
    try {
      const { data } = await apiClient.get("/alquileres", { params: { ambiente_id: ambienteId, fecha_desde: dates[0], fecha_hasta: dates[6], office_id: officeId || undefined } });
      setReservas(Array.isArray(data) ? data : []);
    } catch (e) { setCalendarError(formatApiError(e) || "No se pudo cargar la disponibilidad."); }
    finally { setCalendarLoading(false); }
  }, [ambienteId, dates, isSuperAdmin, officeId]);
  useEffect(() => { loadCalendar(); }, [loadCalendar]);

  useEffect(() => {
    if (customerQuery.trim().length < 2) {
      setCustomers([]);
      setCustomerLoading(false);
      setCustomerSearchFailed(false);
      return undefined;
    }
    setCustomers([]);
    setCustomerLoading(true);
    setCustomerSearchFailed(false);
    let cancelled = false;
    const timer = window.setTimeout(async () => {
      try {
        const { data } = await apiClient.get("/clientes/buscar", { params: { q: customerQuery.trim() } });
        if (!cancelled) {
          setCustomers(Array.isArray(data) ? data : []);
          setCustomerSearchFailed(false);
        }
      } catch (e) {
        if (!cancelled) {
          setCustomers([]);
          setCustomerSearchFailed(true);
          toast.error(formatApiError(e) || "No se pudo buscar al cliente.");
        }
      }
      finally { if (!cancelled) setCustomerLoading(false); }
    }, 280);
    return () => { cancelled = true; window.clearTimeout(timer); };
  }, [customerQuery]);

  useEffect(() => {
    if (!date || !tarifa) return;
    if (tarifa.modalidad === "dia") { setStart(""); setEnd(""); }
    else if (SHIFT_MODALITIES.includes(tarifa.modalidad)) { setStart(tarifa.desde || ""); setEnd(tarifa.hasta || ""); }
    else if (start && !selectedDaySchedule.some((b) => mins(start) >= mins(b.desde) && mins(start) < mins(b.hasta))) { setStart(""); setEnd(""); }
  }, [date, tarifa, selectedDaySchedule, start]);

  const occupiedFor = (day) => reservas.filter((r) => toISODate(r.fecha) === day && r.estado !== "cancelado");
  const reservationForSlot = (day, from, to) => occupiedFor(day).find((r) =>
    (r.tramos || []).some((block) => overlaps(from, to, mins(block.desde), mins(block.hasta))),
  );
  const scheduleFor = (day) => {
    if (!ambiente) return [];
    const weekday = DAY_NAMES[parseDate(day).getDay()];
    return (ambiente.horarios || []).filter((s) => s.dia === weekday).slice().sort((a, b) => a.desde.localeCompare(b.desde));
  };
  const isOccupied = (day, from, to) => occupiedFor(day).some((r) => (r.tramos || []).some((block) => overlaps(from, to, mins(block.desde), mins(block.hasta))));
  const selectedContinuous = selectedDaySchedule.find((b) => mins(start) >= mins(b.desde) && mins(start) < mins(b.hasta));
  const endOptions = useMemo(() => {
    if (!selectedContinuous || !start) return [];
    const candidates = [];
    for (let m = mins(start) + 30; m < mins(selectedContinuous.hasta); m += 30) candidates.push(m);
    if (mins(selectedContinuous.hasta) > mins(start)) candidates.push(mins(selectedContinuous.hasta));
    for (const rental of reservas) {
      if (toISODate(rental.fecha) !== date || rental.estado === "cancelado") continue;
      for (const block of rental.tramos || []) {
        const occupiedStart = mins(block.desde);
        if (occupiedStart > mins(start) && occupiedStart < mins(selectedContinuous.hasta)) candidates.push(occupiedStart);
      }
    }
    const found = [];
    for (const m of [...new Set(candidates)].sort((a, b) => a - b)) {
      const conflicts = reservas.some((r) => toISODate(r.fecha) === date && r.estado !== "cancelado" &&
        (r.tramos || []).some((block) => overlaps(mins(start), m, mins(block.desde), mins(block.hasta))));
      if (conflicts) break;
      found.push(time(m));
    }
    return found;
  }, [date, start, selectedContinuous, reservas]);
  const selectedTramos = useMemo(() => {
    if (!tarifa || !date) return [];
    if (tarifa.modalidad === "dia") return selectedDaySchedule;
    if (SHIFT_MODALITIES.includes(tarifa.modalidad)) return start && end ? [{ desde: start, hasta: end }] : [];
    return start && end ? [{ desde: start, hasta: end }] : [];
  }, [tarifa, date, selectedDaySchedule, start, end]);
  const durationHours = selectedTramos.reduce((sum, block) => sum + Math.max(0, mins(block.hasta) - mins(block.desde)) / 60, 0);
  const estimated = tarifa ? (tarifa.modalidad === "hora" ? Number(tarifa.monto) * durationHours : Number(tarifa.monto)) : 0;
  const scheduleAllowsSelection = selectedTramos.length > 0 && selectedTramos.every((range) =>
    scheduleFor(date).some((block) => mins(block.desde) <= mins(range.desde) && mins(block.hasta) >= mins(range.hasta)));
  const selectionOccupied = selectedTramos.some((range) => isOccupied(date, mins(range.desde), mins(range.hasta)));

  const chooseSlot = (day, value) => {
    if (!tarifa || tarifa.modalidad === "dia" || SHIFT_MODALITIES.includes(tarifa.modalidad)) return;
    setDate(day); setStart(value); setEnd("");
  };
  const createRental = async (chargeNow) => {
    if (!officeId && isSuperAdmin) return toast.error("Seleccione una oficina.");
    if (!ambienteId || !tarifaId || !customer || !date) return toast.error("Complete ambiente, tarifa, cliente y fecha.");
    if (!isWholeDay && (!start || !end)) return toast.error("Seleccione un horario disponible.");
    if (!isWholeDay && isOccupied(date, mins(start), mins(end))) return toast.error("Ese horario acaba de ser ocupado. Actualice el calendario.");
    const printWindow = chargeNow ? window.open("", "ALQUILER_PRINT", "height=760,width=820") : null;
    setSaving(true);
    try {
      const payload = { ambiente_id: ambienteId, tarifa_id: tarifaId, fecha: date, cliente_id: customer.id, cobrar_ahora: chargeNow };
      if (officeId) payload.office_id = officeId;
      if (!isWholeDay) { payload.desde = start; payload.hasta = end; }
      const { data } = await apiClient.post("/alquileres", payload);
      const record = data;
      setLastSaved(record);
      toast.success(chargeNow
        ? record.estado === "pagado" ? "Pago registrado y comprobante emitido." : "La reserva quedó pendiente de pago."
        : "Reserva guardada.");
      await loadCalendar();
      if (chargeNow && record.estado === "pagado") {
        if (!printAlquilerComprobante(record, printWindow)) toast.error("No fue posible abrir el comprobante. Habilite ventanas emergentes e imprima desde la reserva.");
      } else printWindow?.close();
      if (!chargeNow) { setDate(""); setStart(""); setEnd(""); }
    } catch (e) {
      printWindow?.close();
      await loadCalendar();
      toast.error(formatApiError(e) || "No se pudo guardar la reserva.");
    }
    finally { setSaving(false); }
  };
  const openNewClient = () => {
    setNewClientForm({
      ci: "",
      cu: "",
      nombre: "",
      });
    setNewClientOpen(true);
  };
  const createNewClient = async (event) => {
    event.preventDefault();
    setCreatingClient(true);
    try {
      const { data } = await apiClient.post("/clientes", newClientForm);
      setCustomer(data);
      setCustomerQuery("");
      setCustomers([]);
      setCustomerSearchFailed(false);
      setNewClientOpen(false);
      toast.success("Cliente registrado y seleccionado.");
    } catch (error) {
      toast.error(formatApiError(error) || "No se pudo registrar al cliente.");
    } finally {
      setCreatingClient(false);
    }
  };
  const payLater = async (rental) => {
    const printWindow = window.open("", "ALQUILER_PRINT", "height=760,width=820");
    setSaving(true);
    try {
      const { data } = await apiClient.post(`/alquileres/${rental.id}/pagar`);
      setLastSaved(data); toast.success("Pago registrado."); await loadCalendar();
      if (!printAlquilerComprobante(data, printWindow)) toast.error("No fue posible abrir el comprobante. Habilite ventanas emergentes.");
    } catch (e) { printWindow?.close(); toast.error(formatApiError(e) || "No se pudo registrar el pago."); }
    finally { setSaving(false); }
  };
  const cancelReservation = async (rental) => {
    if (!window.confirm("¿Cancelar esta reserva y liberar el horario?")) return;
    try { await apiClient.post(`/alquileres/${rental.id}/cancelar`); toast.success("Reserva cancelada; horario liberado."); await loadCalendar(); }
    catch (e) { toast.error(formatApiError(e) || "No se pudo cancelar la reserva."); }
  };

  const slotTicks = useMemo(() => {
    const ticks = new Set();
    for (const block of ambiente?.horarios || []) {
      const from = mins(block.desde);
      const until = mins(block.hasta);
      if (until <= from) continue;
      ticks.add(from);
      for (let point = from + 30; point < until; point += 30) ticks.add(point);
      ticks.add(until);
    }
    return [...ticks].sort((a, b) => a - b);
  }, [ambiente]);
  const selectable = tarifa && tarifa.modalidad !== "dia" && !SHIFT_MODALITIES.includes(tarifa.modalidad);

  return <div className="space-y-6" data-testid="registro-alquiler-page">
    <header className="flex flex-wrap items-end justify-between gap-4"><div><div className="section-eyebrow">Operaciones · Espacios</div><h1 className="font-serif-display mt-1 text-4xl">Registro de Alquiler</h1><p className="mt-1 max-w-2xl text-sm text-[color:var(--institution-muted)]">Consulte disponibilidad, reserve un ambiente y emita el comprobante de pago.</p></div>
      {isSuperAdmin ? <div className="w-full max-w-xs space-y-1.5"><Label htmlFor="alquiler-office">Oficina</Label><select id="alquiler-office" value={selectedOfficeId} onChange={(e) => { setSelectedOfficeId(e.target.value); setAmbientes([]); setAmbienteId(""); setTarifas([]); setTarifaId(""); setReservas([]); setCustomer(null); setCustomerQuery(""); setDate(""); setStart(""); setEnd(""); setLastSaved(null); }} className="h-10 w-full rounded-sm border border-input bg-background px-3 text-sm"><option value="">Seleccione una oficina</option>{offices.filter((o) => o.activa).map((o) => <option key={o.id} value={o.id}>{o.nombre}</option>)}</select></div> : <div className="text-xs text-[color:var(--institution-muted)]">Oficina · <b>{officeName || user?.office_nombre || "—"}</b></div>}
    </header>

    {isSuperAdmin && !officeId ? <div className="rounded-sm border bg-white p-10 text-center" style={{ borderColor: "var(--institution-border)" }}><CalendarDays className="mx-auto mb-3 text-[color:var(--institution-muted)]"/><h2 className="font-serif-display text-2xl">Seleccione oficina</h2><p className="mt-1 text-sm text-[color:var(--institution-muted)]">La agenda y el catálogo corresponden a una oficina.</p></div> :
     <div className="grid grid-cols-1 items-start gap-5">
      <section className="min-w-0 space-y-4">
        <div className="grid gap-3 sm:grid-cols-2">
          <div className="space-y-1.5"><Label htmlFor="alquiler-ambiente">Ambiente</Label><select id="alquiler-ambiente" value={ambienteId} onChange={(e) => { setAmbienteId(e.target.value); setTarifaId(""); setTarifas([]); setReservas([]); setDate(""); setStart(""); setEnd(""); setLastSaved(null); }} disabled={catalogLoading} className="h-10 w-full rounded-sm border border-input bg-white px-3 text-sm"><option value="">{catalogLoading ? "Cargando ambientes…" : "Seleccione un ambiente"}</option>{ambientes.map((a) => <option key={a.id} value={a.id}>{a.nombre}</option>)}</select></div>
          <div className="space-y-1.5"><Label htmlFor="alquiler-tarifa">Tarifa</Label><select id="alquiler-tarifa" value={tarifaId} onChange={(e) => { setTarifaId(e.target.value); setStart(""); setEnd(""); }} disabled={!ambienteId} className="h-10 w-full rounded-sm border border-input bg-white px-3 text-sm"><option value="">Seleccione tarifa</option>{tarifas.map((t) => <option key={t.id} value={t.id}>{t.nombre} · Bs. {formatMoney(t.monto)}</option>)}</select></div>
        </div>
        {ambiente && <div className="flex flex-wrap items-center justify-between gap-3 rounded-sm border bg-white px-4 py-3" style={{ borderColor: "var(--institution-border)" }}>
          <div><div className="text-xs uppercase tracking-widest text-[color:var(--institution-muted)]">Agenda semanal</div><div className="mt-1 font-medium">{ambiente.nombre}<span className="ml-2 text-xs font-normal text-[color:var(--institution-muted)]">{ambiente.office_nombre || officeName}</span></div></div>
           <div className="flex items-center gap-2"><Button variant="outline" size="icon" aria-label="Semana anterior" onClick={() => { setAnchor(fmtDate(addDays(parseDate(anchor), -7))); setDate(""); setStart(""); setEnd(""); }}><ChevronLeft size={16}/></Button><div className="min-w-32 text-center text-sm font-medium">{formatDate(dates[0])} – {formatDate(dates[6])}</div><Button variant="outline" size="icon" aria-label="Semana siguiente" onClick={() => { setAnchor(fmtDate(addDays(parseDate(anchor), 7))); setDate(""); setStart(""); setEnd(""); }}><ChevronRight size={16}/></Button><Button variant="ghost" size="icon" aria-label="Actualizar agenda" onClick={loadCalendar}><RefreshCw size={15}/></Button></div>
        </div>}
        {calendarError && <div role="alert" className="rounded-sm border border-red-200 bg-red-50 p-3 text-sm text-red-900">{calendarError}<Button variant="outline" size="sm" className="ml-2" onClick={loadCalendar}>Reintentar</Button></div>}
        <div className="overflow-x-auto rounded-sm border bg-white" style={{ borderColor: "var(--institution-border)" }}>
          {calendarLoading && <div className="h-1 animate-pulse bg-[color:var(--institution-burgundy)]"/>}
          <div className="min-w-[740px]">
            <div className="grid border-b" style={{ gridTemplateColumns: "62px repeat(7,minmax(88px,1fr))", borderColor: "var(--institution-border)" }}>
              <div className="p-2 text-[10px] uppercase tracking-wider text-[color:var(--institution-muted)]">Hora</div>
                {dates.map((day) => <button key={day} type="button" onClick={() => { setDate(day); if (tarifa && SHIFT_MODALITIES.includes(tarifa.modalidad)) { setStart(tarifa.desde || ""); setEnd(tarifa.hasta || ""); } else if (!selectable) { setStart(""); setEnd(""); } }} className={`border-l px-2 py-2 text-left transition-colors hover:bg-[color:var(--institution-cream)] ${day === date ? "bg-[color:var(--institution-cream)]" : ""}`} style={{ borderColor: "var(--institution-border)" }}><span className="block text-[10px] uppercase tracking-wider text-[color:var(--institution-muted)]">{prettyDate(day, { weekday: "short" })}</span><span className="font-medium">{formatDate(day)}</span></button>)}
            </div>
            <div className="max-h-[570px] overflow-y-auto">
              {slotTicks.slice(0, -1).map((slot) => <div key={slot} className="grid h-10 border-b last:border-0" style={{ gridTemplateColumns: "62px repeat(7,minmax(88px,1fr))", borderColor: "var(--institution-border)" }}>
                <div className="relative -top-2.5 pr-2 text-right text-[10px] tabular-nums text-[color:var(--institution-muted)]">{time(slot)}</div>
                 {dates.map((day) => {
                  const workBlock = scheduleFor(day).find((b) => slot >= mins(b.desde) && slot < mins(b.hasta));
                  const working = Boolean(workBlock);
                   const occupiedBooking = working ? reservationForSlot(day, slot, slot + 1) : null;
                   const busy = Boolean(occupiedBooking);
                   const paidSlot = occupiedBooking?.estado === "pagado";
                   const occupiedLabel = paidSlot ? "Pagado" : occupiedBooking ? "Reservado" : "";
                  const selectedSlot = day === date && start && slot === mins(start);
                    return <button key={day} type="button" disabled={!working || busy || !selectable} onClick={() => chooseSlot(day, time(slot))} aria-label={`${prettyDate(day, { weekday: "long" })} ${formatDate(day)}, ${time(slot)}${busy ? `, ${occupiedLabel.toLowerCase()}` : working ? ", disponible" : ", fuera de horario"}`} title={busy ? occupiedLabel : !working ? "Fuera del horario registrado" : selectable ? `Seleccionar ${time(slot)}` : "Elija una tarifa por hora o actividad para seleccionar horario"} className={`relative border-l text-left transition-colors focus-visible:z-10 focus-visible:outline focus-visible:outline-2 focus-visible:outline-[color:var(--institution-burgundy)] ${!working ? "bg-[color:var(--institution-cream)]/70" : paidSlot ? "cursor-not-allowed bg-[#e5eee8]" : busy ? "cursor-not-allowed bg-[#f3ead7]" : selectable ? "cursor-pointer hover:bg-[#edf3f0]" : "cursor-default"} ${selectedSlot ? "bg-[#e6efe9] ring-1 ring-inset ring-[#607c6c]" : ""}`} style={{ borderColor: "var(--institution-border)" }}>
                     {busy && <span className={`absolute inset-x-1 top-1/2 -translate-y-1/2 truncate rounded-sm px-1 py-0.5 text-center text-[9px] ${paidSlot ? "bg-[#425c4d] text-white" : "bg-[#826628] text-white"}`}>{occupiedLabel}</span>}
                    {selectedSlot && <span className="absolute inset-x-1 top-1/2 -translate-y-1/2 truncate text-center text-[9px] font-medium text-[#425c4d]">{time(slot)} inicio</span>}
                  </button>;
                })}
              </div>)}
              {!ambiente && !catalogLoading && <div className="p-10 text-center text-sm text-[color:var(--institution-muted)]">Seleccione un ambiente para consultar su disponibilidad.</div>}
            </div>
          </div>
        </div>
        <div className="flex flex-wrap gap-x-4 gap-y-2 text-xs text-[color:var(--institution-muted)]"><span className="inline-flex items-center gap-1.5"><i className="h-3 w-3 rounded-sm border bg-white"/>Disponible</span><span className="inline-flex items-center gap-1.5"><i className="h-3 w-3 rounded-sm bg-[#f3ead7]"/>Reservado · pendiente de pago</span><span className="inline-flex items-center gap-1.5"><i className="h-3 w-3 rounded-sm bg-[#e5eee8]"/>Pagado</span><span className="inline-flex items-center gap-1.5"><i className="h-3 w-3 rounded-sm bg-[color:var(--institution-cream)]"/>Fuera de horario</span></div>
        {ambiente && !ambiente.horarios?.length && <div className="rounded-sm border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900">Este ambiente no tiene horarios semanales registrados. Actualice su disponibilidad antes de reservar.</div>}
      </section>

      <aside className="space-y-4 rounded-sm border bg-white p-5" style={{ borderColor: "var(--institution-border)" }}>
        <div><div className="section-eyebrow">Nueva reserva</div><h2 className="mt-1 font-serif-display text-2xl">Datos del alquiler</h2></div>
        <div className="space-y-1.5"><Label htmlFor="rental-customer-search">Buscar cliente</Label><div className="relative"><Search size={15} className="absolute left-3 top-3 text-[color:var(--institution-muted)]"/><Input id="rental-customer-search" value={customerQuery} onChange={(e) => { setCustomerQuery(e.target.value); setCustomer(null); }} placeholder="Nombre o documento (mín. 2)" className="rounded-sm pl-9"/></div>
          {customerLoading && <p className="text-xs text-[color:var(--institution-muted)]">Buscando en el registro…</p>}
          {customerQuery.trim().length >= 2 && !customerLoading && <div className="max-h-48 divide-y overflow-y-auto rounded-sm border" style={{ borderColor: "var(--institution-border)" }}>{customers.length ? customers.map((item) => <button key={item.id} type="button" onClick={() => { setCustomer(item); setCustomerQuery(""); setCustomers([]); }} className="flex w-full items-center justify-between gap-2 px-3 py-2 text-left hover:bg-[color:var(--institution-cream)]"><span className="min-w-0"><span className="block truncate text-sm font-medium">{item.nombre}</span><span className="block text-xs text-[color:var(--institution-muted)]">Cliente · CI {item.ci || "—"}{item.cu ? ` · CU ${item.cu}` : ""}</span></span><Check size={15} className="shrink-0 opacity-0"/></button>) : <p className="p-3 text-sm text-[color:var(--institution-muted)]">{customerSearchFailed ? "No se pudo completar la búsqueda." : "No hay coincidencias para esta búsqueda."}</p>}</div>}
          {customerQuery.trim().length >= 2 && !customerLoading && !customerSearchFailed && customers.length === 0 && <div className="flex flex-wrap gap-2">
            <Button type="button" size="sm" variant="outline" className="rounded-sm" onClick={openNewClient} data-testid="rental-create-client">
              <Plus size={14} className="mr-1"/> Nuevo cliente
            </Button>
          </div>}
        </div>
        <ImportSelection kind="clientes" onSelect={(row) => { setNewClientForm(row); setNewClientOpen(true); }} />
        {customer && <div className="flex items-start justify-between gap-3 rounded-sm border p-3" style={{ borderColor: "var(--institution-border)", background: "var(--institution-cream)" }}><div><div className="text-[10px] uppercase tracking-widest text-[color:var(--institution-muted)]">Cliente</div><div className="mt-1 text-sm font-medium">{customer.nombre}</div><div className="text-xs text-[color:var(--institution-muted)]">CI {customer.ci || "—"}{customer.cu ? ` · CU ${customer.cu}` : ""}</div></div><Button variant="ghost" size="sm" onClick={() => setCustomer(null)}>Cambiar</Button></div>}
        <div className="space-y-1.5"><Label htmlFor="rental-date">Fecha de uso</Label><Input id="rental-date" type="date" value={date} onChange={(e) => { const value = e.target.value; setDate(value); setStart(""); setEnd(""); if (value) { const selectedDate = parseDate(value); selectedDate.setDate(selectedDate.getDate() - ((selectedDate.getDay() + 6) % 7)); setAnchor(fmtDate(selectedDate)); } }} className="rounded-sm"/></div>
        {tarifa && <div className="space-y-3 rounded-sm border p-3" style={{ borderColor: "var(--institution-border)" }}><div className="flex items-center justify-between gap-2"><div><div className="text-[10px] uppercase tracking-widest text-[color:var(--institution-muted)]">Horario</div><div className="mt-1 text-sm font-medium">{tarifa.modalidad === "dia" ? "Jornada completa" : SHIFT_MODALITIES.includes(tarifa.modalidad) ? `${SHIFT_LABELS[tarifa.modalidad]} · ${tarifa.desde}–${tarifa.hasta}` : start ? `${start}${end ? `–${end}` : " · seleccione fin"}` : "Seleccione inicio en agenda"}</div></div><Clock3 size={17} className="text-[color:var(--institution-muted)]"/></div>
          {tarifa.modalidad === "dia" && <p className="text-xs text-[color:var(--institution-muted)]">Se reservarán automáticamente todos los tramos del horario registrado para ese día.</p>}
          {SHIFT_MODALITIES.includes(tarifa.modalidad) && <p className="text-xs text-[color:var(--institution-muted)]">Se marcará el turno completo como reservado o pagado según la operación elegida.</p>}
          {selectable && start && <div className="space-y-1.5"><Label htmlFor="rental-end">Hora de término</Label><select id="rental-end" value={end} onChange={(e) => setEnd(e.target.value)} className="h-10 w-full rounded-sm border border-input bg-white px-3 text-sm"><option value="">Seleccione hora de término</option>{endOptions.map((value) => <option key={value} value={value}>{value}</option>)}</select><p className="text-xs text-[color:var(--institution-muted)]">Solo horas dentro del mismo tramo disponible.</p></div>}
          {date && selectedTramos.length > 0 && (!scheduleAllowsSelection || selectionOccupied) && <p role="alert" className="text-xs text-[#8f3d4e]">{selectionOccupied ? "El horario seleccionado ya no está disponible." : "La tarifa excede el horario de apertura registrado."}</p>}
        </div>}
        <div className="border-t pt-3" style={{ borderColor: "var(--institution-border)" }}><div className="flex items-center justify-between text-xs text-[color:var(--institution-muted)]"><span>{tarifa?.nombre || "Tarifa"}</span><span>{tarifa?.modalidad === "hora" && durationHours ? `${durationHours} h × Bs. ${formatMoney(tarifa.monto)}` : "Monto fijo"}</span></div><div className="mt-1 flex items-end justify-between"><span className="text-xs uppercase tracking-widest text-[color:var(--institution-muted)]">Total estimado</span><strong className="font-serif-display text-2xl" style={{ color: "var(--institution-burgundy)" }}>Bs. {formatMoney(estimated)}</strong></div><p className="mt-1 text-[10px] text-[color:var(--institution-muted)]">El monto final se confirma al guardar.</p></div>
        <div className="space-y-2"><Button type="button" disabled={saving || !customer || !date || !tarifa || (isWholeDay ? !selectedDaySchedule.length : (!start || !end)) || !scheduleAllowsSelection || selectionOccupied} onClick={() => createRental(false)} variant="outline" className="h-10 w-full rounded-sm" data-testid="rental-save-reservation">{saving ? "Guardando…" : "Guardar reserva · pagar después"}</Button><Button type="button" disabled={saving || !customer || !date || !tarifa || (isWholeDay ? !selectedDaySchedule.length : (!start || !end)) || !scheduleAllowsSelection || selectionOccupied} onClick={() => createRental(true)} className="h-11 w-full rounded-sm text-white" style={{ backgroundColor: "var(--institution-burgundy)" }} data-testid="rental-pay-now"><Printer size={16} className="mr-2"/>{saving ? "Procesando…" : "Pagar e imprimir comprobante"}</Button></div>
        {lastSaved && <div className="rounded-sm border p-3 text-sm" style={{ borderColor: "var(--institution-border)", background: "var(--institution-cream)" }}><div className="flex items-center justify-between gap-2"><div><span className={`rounded-full px-2 py-1 text-[10px] uppercase tracking-wider ${lastSaved.estado === "pagado" ? "bg-[#e5eee8] text-[#425c4d]" : "bg-[#f3ead7] text-[#826628]"}`}>{lastSaved.estado}</span><p className="mt-2 font-medium">{lastSaved.comprobante_display || lastSaved.comprobante_display === "" ? lastSaved.comprobante_display : `Reserva ${lastSaved.id}`}</p><p className="text-xs text-[color:var(--institution-muted)]">Bs. {formatMoney(lastSaved.total)}</p></div>{lastSaved.estado === "pagado" ? <Button variant="ghost" size="icon" aria-label="Imprimir comprobante" onClick={() => printAlquilerComprobante(lastSaved)}><Printer size={15}/></Button> : lastSaved.estado === "reservado" ? <Button size="sm" className="rounded-sm text-white" style={{ backgroundColor: "var(--institution-navy)" }} disabled={saving} onClick={() => payLater(lastSaved)}>Pagar ahora</Button> : null}</div></div>}
         <div className="border-t pt-4" style={{ borderColor: "var(--institution-border)" }}><h3 className="text-xs font-semibold uppercase tracking-widest text-[color:var(--institution-muted)]">Reservas de esta semana</h3><div className="mt-2 max-h-56 space-y-2 overflow-y-auto">{reservas.filter((r) => r.estado !== "cancelado").length ? reservas.filter((r) => r.estado !== "cancelado").map((r) => <div key={r.id} className="rounded-sm border p-2.5" style={{ borderColor: "var(--institution-border)" }}><div className="flex items-start justify-between gap-2"><div><div className="text-xs font-medium">{formatDate(r.fecha)} · {r.ambiente_nombre}</div><div className="mt-1 text-xs text-[color:var(--institution-muted)]">{(r.tramos || []).map((x) => `${x.desde}–${x.hasta}`).join(", ") || "Jornada completa"} · {r.cliente_nombre}</div></div><span className={`shrink-0 rounded-full px-2 py-0.5 text-[9px] uppercase ${r.estado === "pagado" ? "bg-[#e5eee8] text-[#425c4d]" : "bg-[#f3ead7] text-[#826628]"}`}>{r.estado}</span></div>{r.estado === "reservado" && <div className="mt-2 flex gap-2"><Button size="sm" className="h-7 rounded-sm text-white" style={{ backgroundColor: "var(--institution-navy)" }} disabled={saving} onClick={() => payLater(r)}>Pagar e imprimir</Button><Button size="sm" variant="outline" className="h-7 rounded-sm" disabled={saving} onClick={() => cancelReservation(r)}>Cancelar</Button></div>}</div>) : <p className="py-2 text-xs text-[color:var(--institution-muted)]">{calendarLoading ? "Cargando agenda…" : "No hay reservas activas esta semana."}</p>}</div></div>
      </aside>
    </div>}
    <Dialog open={newClientOpen} onOpenChange={(open) => {
      if (creatingClient && !open) return;
      setNewClientOpen(open);
    }}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>
            Nuevo cliente
          </DialogTitle>
        </DialogHeader>
        <form onSubmit={createNewClient} className="grid grid-cols-2 gap-4" data-testid="rental-new-client-form">
          <div className="col-span-2"><ImportSelection kind="clientes" onSelect={setNewClientForm} /></div>
          <div className="space-y-1.5">
            <Label htmlFor="rental-new-client-ci">C.I.</Label>
            <Input
              id="rental-new-client-ci"
              value={newClientForm.ci}
              onChange={(event) => setNewClientForm({ ...newClientForm, ci: event.target.value })}
              required={!newClientForm.cu.trim()}
              className="rounded-sm"
              autoComplete="off"
              data-testid="rental-new-client-ci"
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="rental-new-client-cu">C.U.</Label>
            <Input
              id="rental-new-client-cu"
              value={newClientForm.cu}
              onChange={(event) => setNewClientForm({ ...newClientForm, cu: event.target.value })}
              className="rounded-sm"
            />
          </div>
          <div className="col-span-2 space-y-1.5">
            <Label htmlFor="rental-new-client-name">Nombre completo</Label>
            <Input
              id="rental-new-client-name"
              value={newClientForm.nombre}
              onChange={(event) => setNewClientForm({ ...newClientForm, nombre: event.target.value })}
              required
              className="rounded-sm"
              data-testid="rental-new-client-name"
            />
          </div>
          <DialogFooter className="col-span-2">
            <Button
              type="button"
              variant="outline"
              onClick={() => setNewClientOpen(false)}
              disabled={creatingClient}
              className="rounded-sm"
            >
              Cancelar
            </Button>
            <Button
              type="submit"
              disabled={creatingClient}
              className="rounded-sm text-white"
              style={{ backgroundColor: "var(--institution-burgundy)" }}
              data-testid="rental-new-client-save"
            >
              {creatingClient ? "Registrando…" : "Registrar y seleccionar"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  </div>;
}