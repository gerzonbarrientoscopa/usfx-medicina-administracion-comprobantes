import React, { useEffect, useState } from "react";
import { apiClient, formatApiError, formatMoney } from "@/lib/api";
import { useAuth } from "@/contexts/AuthContext";
import { Card, CardContent } from "@/components/ui/card";
import { GraduationCap, Tags, Receipt, CircleDollarSign } from "lucide-react";
import { useOfficeScope } from "@/hooks/useOfficeScope";
import { toast } from "sonner";
import { Label } from "@/components/ui/label";
import {
    Select,
    SelectTrigger,
    SelectValue,
    SelectContent,
    SelectItem,
} from "@/components/ui/select";

function StatCard({ label, value, icon: Icon, accent }) {
    return (
        <Card className="rounded-sm border-[color:var(--institution-border)] shadow-none">
            <CardContent className="p-6">
                <div className="flex items-start justify-between">
                    <div>
                        <div className="section-eyebrow">{label}</div>
                        <div className="font-serif-display text-4xl mt-2 font-mono-num" style={{ color: "var(--institution-text)" }}>
                            {value}
                        </div>
                    </div>
                    <div
                        className="w-10 h-10 flex items-center justify-center text-white"
                        style={{ backgroundColor: accent || "var(--institution-burgundy)" }}
                    >
                        <Icon size={20} strokeWidth={1.5} />
                    </div>
                </div>
            </CardContent>
        </Card>
    );
}

export default function DashboardPage() {
    const { user } = useAuth();
    const {
        isSuperAdmin,
        offices,
        officeId,
        officeName,
        selectedOfficeId,
        setSelectedOfficeId,
    } = useOfficeScope();
    const [stats, setStats] = useState(null);

    useEffect(() => {
        let cancelled = false;
        setStats(null);
        apiClient
            .get("/dashboard/stats", { params: officeId ? { office_id: officeId } : {} })
            .then((r) => {
                if (!cancelled) setStats(r.data);
            })
            .catch((error) => {
                if (!cancelled) toast.error(formatApiError(error));
            });
        return () => { cancelled = true; };
    }, [officeId]);

    const institution = stats?.institucion || {};
    const currentOfficeName = stats?.office_nombre || officeName;

    return (
        <div className="space-y-8" data-testid="dashboard-page">
            <div>
                <div className="section-eyebrow">Panel general</div>
                <h1 className="font-serif-display text-4xl mt-1">Bienvenido, {user?.nombre}</h1>
                <p className="text-sm text-[color:var(--institution-muted)] mt-1">
                    Sistema de comprobantes de pago — vista general del día de hoy.
                </p>
                <p className="text-sm text-[color:var(--institution-muted)] mt-1" data-testid="dashboard-office-context">
                    Oficina: {currentOfficeName}
                </p>
                {isSuperAdmin && (
                    <div className="space-y-1.5 max-w-sm mt-4">
                        <Label className="text-xs uppercase tracking-widest text-[color:var(--institution-muted)]">Oficina</Label>
                        <Select
                            value={selectedOfficeId || "all"}
                            onValueChange={(value) => setSelectedOfficeId(value === "all" ? "" : value)}
                        >
                            <SelectTrigger className="rounded-sm" data-testid="dashboard-office-select">
                                <SelectValue />
                            </SelectTrigger>
                            <SelectContent>
                                <SelectItem value="all">Todas las oficinas</SelectItem>
                                {offices.map((office) => (
                                    <SelectItem key={office.id} value={office.id}>{office.nombre}</SelectItem>
                                ))}
                            </SelectContent>
                        </Select>
                    </div>
                )}
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
                <StatCard
                    label="Estudiantes registrados"
                    value={stats?.estudiantes ?? "—"}
                    icon={GraduationCap}
                    accent="var(--institution-navy)"
                />
                <StatCard
                    label="Tipos de pago"
                    value={stats?.tipospagos ?? "—"}
                    icon={Tags}
                    accent="var(--institution-accent, #B9975B)"
                />
                <StatCard
                    label="Pagos del día"
                    value={stats?.pagos_hoy ?? "—"}
                    icon={Receipt}
                    accent="var(--institution-burgundy)"
                />
                <StatCard
                    label="Recaudado hoy (Bs.)"
                    value={stats ? formatMoney(stats.monto_hoy) : "—"}
                    icon={CircleDollarSign}
                    accent="var(--institution-success)"
                />
            </div>

            <Card className="rounded-sm border-[color:var(--institution-border)] shadow-none">
                <CardContent className="p-8">
                    <div className="section-eyebrow mb-2">Institución</div>
                    <div className="font-serif-display text-2xl leading-tight" style={{ color: "var(--institution-navy)" }}>
                        {institution.linea1 || "Universidad Mayor, Real y Pontificia de San Francisco Xavier"}
                    </div>
                    <div className="font-serif-display text-lg" style={{ color: "var(--institution-burgundy)" }}>
                        {institution.linea2 || currentOfficeName}
                    </div>
                    <div className="text-xs uppercase tracking-widest text-[color:var(--institution-muted)] mt-1">
                        {institution.linea3 || "Administración"} · Sistema de Comprobantes
                    </div>
                </CardContent>
            </Card>
        </div>
    );
}
