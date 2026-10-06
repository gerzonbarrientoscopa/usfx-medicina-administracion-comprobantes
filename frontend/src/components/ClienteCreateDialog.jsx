import React, { useState } from "react";
import { apiClient, formatApiError } from "@/lib/api";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from "@/components/ui/dialog";
import { ImportSelection } from "@/components/ImportSelection";

const EMPTY_CLIENT = { ci: "", cu: "", nombre: "" };

export function ClienteCreateDialog({
  open,
  onOpenChange,
  onSelect,
  formTestId,
  fieldTestIds = {},
}) {
  const [cliente, setCliente] = useState(EMPTY_CLIENT);
  const [saving, setSaving] = useState(false);

  const handleOpenChange = (nextOpen) => {
    if (saving && !nextOpen) return;
    if (nextOpen) setCliente(EMPTY_CLIENT);
    onOpenChange(nextOpen);
  };

  const createCliente = async (event) => {
    event.preventDefault();
    setSaving(true);
    try {
      const { data } = await apiClient.post("/clientes", {
        ci: cliente.ci,
        cu: cliente.cu,
        nombre: cliente.nombre,
      });
      onSelect(data);
      toast.success("Cliente registrado y seleccionado.");
      setCliente(EMPTY_CLIENT);
      onOpenChange(false);
    } catch (error) {
      toast.error(formatApiError(error) || "No se pudo registrar al cliente.");
    } finally {
      setSaving(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent className="rounded-sm sm:max-w-md">
        <DialogHeader>
          <DialogTitle className="font-serif-display text-2xl">Nuevo cliente</DialogTitle>
        </DialogHeader>
        <form onSubmit={createCliente} className="grid grid-cols-2 gap-4" data-testid={formTestId}>
          <div className="col-span-2">
            <ImportSelection
              kind="clientes"
              onSelect={(record) => setCliente({ ...EMPTY_CLIENT, ...record })}
            />
          </div>
          <div className="space-y-1.5">
            <Label className="text-xs uppercase tracking-widest text-[color:var(--institution-muted)]">C.I.</Label>
            <Input
              value={cliente.ci}
              onChange={(event) => setCliente({ ...cliente, ci: event.target.value })}
              required={!cliente.cu.trim()}
              className="rounded-sm"
              autoComplete="off"
              data-testid={fieldTestIds.ci}
            />
          </div>
          <div className="space-y-1.5">
            <Label className="text-xs uppercase tracking-widest text-[color:var(--institution-muted)]">C.U.</Label>
            <Input
              value={cliente.cu}
              onChange={(event) => setCliente({ ...cliente, cu: event.target.value })}
              className="rounded-sm"
              autoComplete="off"
              data-testid={fieldTestIds.cu}
            />
          </div>
          <div className="col-span-2 space-y-1.5">
            <Label className="text-xs uppercase tracking-widest text-[color:var(--institution-muted)]">Nombre completo</Label>
            <Input
              value={cliente.nombre}
              onChange={(event) => setCliente({ ...cliente, nombre: event.target.value })}
              required
              className="rounded-sm"
              autoComplete="name"
              data-testid={fieldTestIds.nombre}
            />
          </div>
          <DialogFooter className="col-span-2">
            <Button
              type="button"
              variant="outline"
              onClick={() => onOpenChange(false)}
              disabled={saving}
              className="rounded-sm"
            >
              Cancelar
            </Button>
            <Button
              type="submit"
              disabled={saving}
              className="rounded-sm text-white"
              style={{ backgroundColor: "var(--institution-burgundy)" }}
              data-testid={fieldTestIds.save}
            >
              {saving ? "Registrando…" : "Registrar y seleccionar"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
