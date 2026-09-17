import React, { useEffect, useState } from "react";
import { apiClient, formatMoney } from "@/lib/api";
import { useAuth } from "@/contexts/AuthContext";
import { Card, CardContent } from "@/components/ui/card";
import { GraduationCap, Tags, Receipt, CircleDollarSign } from "lucide-react";

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
    const [stats, setStats] = useState(null);

    useEffect(() => {
        apiClient
            .get("/dashboard/stats")
            .then((r) => setStats(r.data))
            .catch(() => {});
    }, []);

    return (
        <div className="space-y-8" data-testid="dashboard-page">
            <div>
                <div className="section-eyebrow">Panel general</div>
                <h1 className="font-serif-display text-4xl mt-1">Bienvenido, {user?.name}</h1>
                <p className="text-sm text-[color:var(--institution-muted)] mt-1">
                    Sistema de comprobantes de pago — vista general del día de hoy.
                </p>
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
                        Universidad Mayor, Real y Pontificia de San Francisco Xavier
                    </div>
                    <div className="font-serif-display text-lg" style={{ color: "var(--institution-burgundy)" }}>
                        Facultad de Medicina
                    </div>
                    <div className="text-xs uppercase tracking-widest text-[color:var(--institution-muted)] mt-1">
                        Administración · Sistema de Comprobantes
                    </div>
                </CardContent>
            </Card>
        </div>
    );
}
