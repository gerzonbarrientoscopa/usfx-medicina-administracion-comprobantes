import React, { useEffect, useState } from "react";
import { apiClient, formatApiError } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";

/** Select directory data first, then use the normal create form to save it. */
export function ImportSelection({ kind, onSelect }) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [submittedQuery, setSubmittedQuery] = useState("");
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [retry, setRetry] = useState(0);
  const [page, setPage] = useState(1);
  const requestQuery = kind === "clientes" ? submittedQuery : query;

  const handleSearch = () => {
    const searchTerm = query.trim();
    if (searchTerm.length < 3) return;
    setSubmittedQuery(searchTerm);
    setRetry((current) => current + 1);
  };

  const handleSearchKeyDown = (event) => {
    if (event.key === "Enter") {
      event.preventDefault();
      handleSearch();
    }
  };

  const handleQueryChange = (event) => {
    const value = event.target.value;
    setQuery(value);
    if (kind === "clientes") {
      setSubmittedQuery("");
      setRows([]);
      setError("");
      setPage(1);
    }
  };

  const handleDialogOpenChange = (nextOpen) => {
    setOpen(nextOpen);
    if (!nextOpen && kind === "clientes") {
      setQuery("");
      setSubmittedQuery("");
      setRows([]);
      setError("");
      setPage(1);
    }
  };

  useEffect(() => {
    if (!open) return undefined;
    const searchTerm = requestQuery.trim();
    if (kind === "clientes" && searchTerm.length < 3) {
      setRows([]);
      setError("");
      setLoading(false);
      setPage(1);
      return undefined;
    }
    let cancelled = false;
    setLoading(true);
    setError("");
    setRows([]);
    const timer = setTimeout(async () => {
      try {
        const { data } = await apiClient.get(`/${kind}/importacion`, { params: { q: searchTerm } });
        if (!cancelled) { setRows(data); setPage(1); }
      } catch (err) {
        if (!cancelled) setError(formatApiError(err));
      } finally {
        if (!cancelled) setLoading(false);
      }
    }, 250);
    return () => { cancelled = true; clearTimeout(timer); };
  }, [kind, open, requestQuery, retry]);

  const searchInput = (
    <Input
      aria-label={kind === "clientes" ? "Buscar estudiantes" : "Buscar en servicio de importación"}
      placeholder={kind === "clientes" ? "Buscar estudiante por nombre o C.U..." : "Buscar por nombre, documento o código..."}
      value={query}
      onChange={handleQueryChange}
      onKeyDown={kind === "clientes" ? handleSearchKeyDown : undefined}
    />
  );

  return <>
    <Button type="button" variant="outline" className="rounded-sm" onClick={() => setOpen(true)}>
      {kind === "clientes" ? "Buscar Estudiantes" : "Importar desde API"}
    </Button>
    <Dialog open={open} onOpenChange={handleDialogOpenChange}>
      <DialogContent className="max-w-3xl rounded-sm">
        <DialogHeader>
          <DialogTitle>{kind === "clientes" ? "Buscar estudiantes" : `Importar ${kind}`}</DialogTitle>
        </DialogHeader>
        <p className="text-sm text-[color:var(--institution-muted)]">
          {kind === "clientes"
            ? "Escriba al menos 3 caracteres. Seleccione un estudiante para completar sus datos y guárdelo como cliente."
            : "Seleccione un registro para completar el formulario. Se guardará con un Id nuevo al confirmar."}
        </p>
        {kind === "clientes" ? (
          <div className="flex gap-2">
            {searchInput}
            <Button type="button" onClick={handleSearch} disabled={query.trim().length < 3 || loading}>
              Buscar
            </Button>
          </div>
        ) : searchInput}
        {loading ? <p role="status">Consultando servicio…</p> : error ? <div role="alert" className="space-y-3 text-sm">
          <p>{error}</p><Button type="button" variant="outline" onClick={() => setRetry(retry + 1)}>Reintentar</Button>
        </div> : <div className="max-h-96 overflow-auto">
          {!rows.length && <p className="p-4 text-sm">
            {kind === "clientes" && query.trim().length < 3
              ? "Escriba al menos 3 caracteres para buscar estudiantes."
              : kind === "clientes" && !submittedQuery
                ? "Pulse Buscar o Enter para consultar estudiantes."
              : "No se encontraron registros."}
          </p>}
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
