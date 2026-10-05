import React, { useEffect, useState } from "react";
import { apiClient, formatApiError } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";

/** Select directory data first, then use the normal create form to save it. */
export function ImportSelection({ kind, onSelect }) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [retry, setRetry] = useState(0);
  const [page, setPage] = useState(1);

  useEffect(() => {
    if (!open) return undefined;
    let cancelled = false;
    setLoading(true);
    setError("");
    setRows([]);
    const timer = setTimeout(async () => {
      try {
        const { data } = await apiClient.get(`/${kind}/importacion`, { params: { q: query } });
        if (!cancelled) { setRows(data); setPage(1); }
      } catch (err) {
        if (!cancelled) setError(formatApiError(err));
      } finally {
        if (!cancelled) setLoading(false);
      }
    }, 250);
    return () => { cancelled = true; clearTimeout(timer); };
  }, [kind, open, query, retry]);

  return <>
    <Button type="button" variant="outline" className="rounded-sm" onClick={() => setOpen(true)}>
      Importar desde API
    </Button>
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogContent className="max-w-3xl rounded-sm">
        <DialogHeader><DialogTitle>Importar {kind}</DialogTitle></DialogHeader>
        <p className="text-sm text-[color:var(--institution-muted)]">
          Seleccione un registro para completar el formulario. Se guardará con un Id nuevo al confirmar.
        </p>
        <Input aria-label="Buscar en servicio de importación" placeholder="Buscar por nombre, documento o código..."
          value={query} onChange={(event) => setQuery(event.target.value)} />
        {loading ? <p role="status">Consultando servicio…</p> : error ? <div role="alert" className="space-y-3 text-sm">
          <p>{error}</p><Button type="button" variant="outline" onClick={() => setRetry(retry + 1)}>Reintentar</Button>
        </div> : <div className="max-h-96 overflow-auto">
          {!rows.length && <p className="p-4 text-sm">No se encontraron registros.</p>}
          {rows.slice((page - 1) * 25, page * 25).map((row, index) =>
            <button type="button" key={`${page}-${index}`} className="w-full border-b p-3 text-left hover:bg-muted"
              onClick={() => { setOpen(false); onSelect(row); }}>
              <span className="block font-medium">{row.nombre}</span>
              <span className="block text-sm text-[color:var(--institution-muted)]">
                {kind === "clientes"
                  ? `C.I.: ${row.ci || "—"} · C.U.: ${row.cu || "—"}`
                  : `Código: ${row.codigo} · ${row.email}`}
              </span>
            </button>)}
        </div>}
        {!loading && !error && rows.length > 25 && <div className="flex justify-between items-center">
          <Button variant="outline" disabled={page === 1} onClick={() => setPage(page - 1)}>Anterior</Button>
          <span>{page} / {Math.ceil(rows.length / 25)}</span>
          <Button variant="outline" disabled={page * 25 >= rows.length} onClick={() => setPage(page + 1)}>Siguiente</Button>
        </div>}
      </DialogContent>
    </Dialog>
  </>;
}
