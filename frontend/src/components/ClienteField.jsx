import React, { useEffect, useState } from "react";
import { apiClient, formatApiError } from "@/lib/api";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import {
  Command,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from "@/components/ui/command";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";
import { Check, ChevronsUpDown, Plus } from "lucide-react";
import { ClienteCreateDialog } from "@/components/ClienteCreateDialog";

export function ClienteField({
  officeId,
  selectedCliente,
  onSelectCliente,
  disabled = false,
  searchInputId = "cliente-search-input",
  searchInputTestId = "cliente-search-input",
  selectorTestId = "cliente-select-btn",
  createButtonTestId = "add-new-cliente-btn",
  formTestId = "new-est-popup-form",
  fieldTestIds = {
    ci: "new-est-ci",
    cu: "new-est-cu",
    nombre: "new-est-nombre",
    save: "new-est-save",
  },
}) {
  const [clientes, setClientes] = useState([]);
  const [loading, setLoading] = useState(false);
  const [selectorOpen, setSelectorOpen] = useState(false);
  const [createOpen, setCreateOpen] = useState(false);

  useEffect(() => {
    if (!officeId) {
      setClientes([]);
      setLoading(false);
      return undefined;
    }

    let cancelled = false;
    const loadClientes = async () => {
      setLoading(true);
      try {
        const params = { office_id: officeId, pag: 1, tam: 100 };
        const { data: firstPage } = await apiClient.get("/clientes", { params });
        const remainingPages = await Promise.all(
          Array.from({ length: Math.max(0, (firstPage.pages || 1) - 1) }, (_, index) =>
            apiClient.get("/clientes", { params: { ...params, pag: index + 2 } }),
          ),
        );
        const items = [
          ...(firstPage.items || []),
          ...remainingPages.flatMap((response) => response.data.items || []),
        ];
        if (!cancelled) setClientes(items);
      } catch (error) {
        if (!cancelled) {
          setClientes([]);
          toast.error(formatApiError(error) || "No se pudieron cargar los clientes.");
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    };

    loadClientes();
    return () => { cancelled = true; };
  }, [officeId]);

  const selectCliente = (cliente) => {
    setClientes((current) => current.some((item) => item.id === cliente.id)
      ? current
      : [cliente, ...current]);
    onSelectCliente(cliente);
    setSelectorOpen(false);
  };

  return (
    <>
      <div className="space-y-1.5">
        <Label
          htmlFor={`${searchInputId}-button`}
          className="text-xs uppercase tracking-widest text-[color:var(--institution-muted)]"
        >
          Cliente
        </Label>
        <div className="flex gap-2">
          <Popover open={selectorOpen} onOpenChange={setSelectorOpen}>
            <PopoverTrigger asChild>
              <Button
                id={`${searchInputId}-button`}
                type="button"
                variant="outline"
                role="combobox"
                aria-expanded={selectorOpen}
                disabled={disabled || !officeId}
                className="flex-1 justify-between rounded-sm font-normal"
                data-testid={selectorTestId}
              >
                <span className="truncate">
                  {selectedCliente
                    ? `${selectedCliente.nombre} — CI: ${selectedCliente.ci || "—"}`
                    : "Buscar cliente…"}
                </span>
                <ChevronsUpDown size={14} className="ml-2 shrink-0 opacity-50" />
              </Button>
            </PopoverTrigger>
            <PopoverContent
              className="rounded-sm p-0"
              align="start"
              style={{ width: "var(--radix-popover-trigger-width)" }}
            >
              <Command>
                <CommandInput
                  id={searchInputId}
                  aria-label="Buscar cliente"
                  placeholder="Nombre, CI o CU…"
                  data-testid={searchInputTestId}
                />
                <CommandList>
                  <CommandEmpty>{loading ? "Cargando clientes…" : "Sin resultados."}</CommandEmpty>
                  <CommandGroup>
                    {clientes.map((cliente) => (
                      <CommandItem
                        key={cliente.id}
                        value={`${cliente.nombre} ${cliente.ci || ""} ${cliente.cu || ""}`}
                        onSelect={() => selectCliente(cliente)}
                        data-testid={`cliente-option-${cliente.id}`}
                      >
                        <Check
                          className={`mr-2 h-4 w-4 ${selectedCliente?.id === cliente.id ? "opacity-100" : "opacity-0"}`}
                        />
                        <div className="flex-1">
                          <div className="text-sm font-medium">{cliente.nombre}</div>
                          <div className="text-xs text-[color:var(--institution-muted)]">
                            CU: {cliente.cu || "—"} · CI: {cliente.ci || "—"}
                          </div>
                        </div>
                      </CommandItem>
                    ))}
                  </CommandGroup>
                </CommandList>
              </Command>
            </PopoverContent>
          </Popover>
          <Button
            type="button"
            variant="outline"
            className="rounded-sm"
            onClick={() => setCreateOpen(true)}
            disabled={disabled || !officeId}
            data-testid={createButtonTestId}
          >
            <Plus size={14} className="mr-1" /> Nuevo
          </Button>
        </div>
      </div>
      <ClienteCreateDialog
        open={createOpen}
        onOpenChange={setCreateOpen}
        onSelect={selectCliente}
        formTestId={formTestId}
        fieldTestIds={fieldTestIds}
      />
    </>
  );
}
